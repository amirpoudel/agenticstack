"""
FastAPI server for the interactive test client.

Routes:
  GET  /                      — Serve the dashboard UI
  GET  /api/config            — Return DEFAULT_APP_CONFIG (pre-fills the UI form)
  GET  /api/health            — Proxy to AgenticStack /v1/health
  POST /api/register          — Proxy to AgenticStack /v1/apps/register
  POST /callback/{user_id}    — Webhook receiver (AgenticStack POSTs results here)
  WS   /ws/{user_id}          — WebSocket chat loop (sends to backend, executes mock tools)

Flow:
  1. WS sends message → POST /v1/chat with callbackUrl=http://self/callback/{user_id}
  2. AgenticStack returns {status: "accepted"} immediately
  3. AgenticStack POSTs result to /callback/{user_id}
  4. WS loop picks result from asyncio.Queue and processes it
"""

import asyncio
import json
from pathlib import Path

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from tests.interactive.web.config import DEFAULT_APP_CONFIG
from tests.interactive.web.tools import execute_tool

BACKEND_API = "http://localhost:8848"   # overridden by main.py at startup
SELF_URL    = "http://localhost:8889"   # overridden by main.py at startup

_STATIC = Path(__file__).parent / "static"

# Per-user asyncio queues: user_id → Queue of webhook event dicts
_queues: dict[str, asyncio.Queue] = {}

app = FastAPI(docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=_STATIC), name="static")


def _get_queue(user_id: str) -> asyncio.Queue:
    if user_id not in _queues:
        _queues[user_id] = asyncio.Queue()
    return _queues[user_id]


# ── HTTP routes ───────────────────────────────────────────────────────────────

@app.get("/")
async def index() -> FileResponse:
    return FileResponse(_STATIC / "index.html")


@app.get("/api/config")
async def get_config() -> dict:
    return DEFAULT_APP_CONFIG


@app.get("/api/health")
async def api_health() -> dict:
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{BACKEND_API}/v1/health", timeout=5.0)
            return resp.json()
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


@app.post("/api/register")
async def api_register(data: dict) -> dict:
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{BACKEND_API}/v1/apps/register",
                json={
                    "appName":      data.get("appName"),
                    "description":  "",
                    "systemPrompt": data.get("systemPrompt") or None,
                    "tools":        data.get("tools", []),
                    "state":        data.get("state", {}),
                },
                timeout=30.0,
            )
            result = resp.json()
            if resp.status_code in (200, 409):
                reg_status = "already_registered" if resp.status_code == 409 else "registered"
                return {
                    "status": "success",
                    "registrationStatus": reg_status,
                    "toolCount": result.get("toolCount", len(data.get("tools", []))),
                }
            return {"status": "error", "error": result.get("detail", "Registration failed")}
    except Exception as exc:
        return {"status": "error", "error": f"Connection failed: {exc}"}


@app.post("/callback/{user_id}")
async def webhook_callback(user_id: str, event: dict) -> dict:
    """Receive async webhook events from AgenticStack and forward to the WS loop."""
    await _get_queue(user_id).put(event)
    return {"ok": True}


# ── WebSocket chat loop ───────────────────────────────────────────────────────

@app.websocket("/ws/{user_id}")
async def ws_chat(websocket: WebSocket, user_id: str) -> None:
    await websocket.accept()
    queue = _get_queue(user_id)

    async def send(event: dict) -> None:
        await websocket.send_json(event)

    async def wait_for_result() -> dict:
        """Block until AgenticStack POSTs to /callback/{user_id}."""
        return await asyncio.wait_for(queue.get(), timeout=120.0)

    async def process(result: dict) -> None:
        """Recursively handle a webhook event (reply / tool_calls / error)."""
        event  = result.get("event") or result.get("status")
        app_id = result.get("appId") or DEFAULT_APP_CONFIG["appName"]

        if event == "reply":
            await send({"type": "reply", "text": result.get("reply", "")})
            return

        if event == "tool_calls":
            calls   = result.get("toolCalls") or []
            turn_id = result.get("turnId")
            await send({"type": "tool_calls_start", "turnId": turn_id, "count": len(calls)})

            tool_results = []
            for tc in calls:
                name     = tc.get("name", "")
                args     = tc.get("args") or {}
                call_id  = tc.get("id", "")
                await send({"type": "tool_call", "id": call_id, "name": name, "args": args})
                result_str = execute_tool(name, args, user_id)
                try:
                    result_data = json.loads(result_str)
                except Exception:
                    result_data = result_str
                await send({"type": "tool_result", "id": call_id, "name": name, "result": result_data})
                tool_results.append({"callId": call_id, "name": name, "result": result_str})

            await send({"type": "status", "text": "Sending tool results..."})
            callback_url = f"{SELF_URL}/callback/{user_id}"
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{BACKEND_API}/v1/chat/tools",
                    json={
                        "appId":       app_id,
                        "userId":      user_id,
                        "turnId":      turn_id,
                        "toolResults": tool_results,
                        "callbackUrl": callback_url,
                    },
                    timeout=30.0,
                )
                resp.raise_for_status()

            next_event = await wait_for_result()
            await process(next_event)
            return

        if event == "error":
            await send({"type": "error", "text": result.get("error", "Unknown error")})
            return

        await send({"type": "error", "text": f"Unexpected event: {event}"})

    try:
        async with httpx.AsyncClient() as client:
            while True:
                data    = await websocket.receive_json()
                if data.get("type") != "chat":
                    continue
                message      = data.get("message", "")
                app_id       = data.get("appId", "")
                state        = data.get("state") or None
                system_prompt = data.get("systemPrompt") or None
                callback_url = f"{SELF_URL}/callback/{user_id}"

                payload: dict = {
                    "appId":       app_id,
                    "userId":      user_id,
                    "message":     message,
                    "callbackUrl": callback_url,
                }
                if state:
                    payload["state"] = state
                if system_prompt:
                    payload["systemPrompt"] = system_prompt

                await send({"type": "status", "text": "Sending to AgenticStack..."})
                try:
                    resp = await client.post(
                        f"{BACKEND_API}/v1/chat", json=payload, timeout=30.0
                    )
                    resp.raise_for_status()
                    # Backend returns {status: "accepted"} — wait for webhook
                    result = await wait_for_result()
                    await process(result)
                except asyncio.TimeoutError:
                    await send({"type": "error", "text": "Timeout: no response from AgenticStack within 120s"})
                except httpx.HTTPStatusError as exc:
                    await send({"type": "error", "text": f"HTTP {exc.response.status_code}: {exc.response.text}"})
                except Exception as exc:
                    await send({"type": "error", "text": str(exc)})
    except WebSocketDisconnect:
        _queues.pop(user_id, None)
