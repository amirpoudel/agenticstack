#!/usr/bin/env python3
"""
AgenticStack Web Test Dashboard - Backend

Serves the test UI and proxies API requests to backend.
Usage: python test_web/main.py
Access: http://localhost:8888
"""

import asyncio
import httpx
from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
from pathlib import Path

app = FastAPI()

# Configuration
BACKEND_API = "http://localhost:8848"
DASHBOARD_PORT = 8888

# Serve static files
test_web_dir = Path(__file__).parent
app.mount("/static", StaticFiles(directory=test_web_dir), name="static")


@app.get("/")
async def root():
    """Serve the main dashboard HTML."""
    return FileResponse(test_web_dir / "index.html", media_type="text/html")


@app.post("/api/register")
async def api_register(data: dict):
    """Register app on backend."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BACKEND_API}/v1/apps/register",
                json={
                    "appName": data.get("appName"),
                    "description": data.get("description", ""),
                    "systemPrompt": data.get("systemPrompt"),
                    "tools": data.get("tools", []),
                    "state": data.get("state", {}),
                },
                timeout=30.0,
            )
            result = response.json()

            if response.status_code == 200:
                return {
                    "status": "success",
                    "appName": result.get("appName"),
                    "toolCount": result.get("toolCount", 0),
                    "message": "App registered successfully",
                }
            else:
                return {"status": "error", "error": result.get("detail", "Registration failed")}
    except Exception as e:
        return {"status": "error", "error": f"Connection failed: {str(e)}"}


@app.post("/api/chat")
async def api_chat(data: dict):
    """Send message to backend API."""
    try:
        app_id = data.get("appId")
        user_id = data.get("userId")
        message = data.get("message")
        
        if not all([app_id, user_id, message]):
            return {"status": "error", "error": "Missing required fields"}
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BACKEND_API}/v1/chat",
                json={
                    "app_id": app_id,
                    "user_id": user_id,
                    "message": message,
                    "mode": "sync"
                },
                timeout=60.0
            )
            result = response.json()
            
            if response.status_code == 200:
                return {
                    "status": result.get("status", "reply"),
                    "reply": result.get("reply"),
                    "toolCalls": result.get("tool_calls", []),
                    "turnId": result.get("turn_id"),
                }
            else:
                return {"status": "error", "error": result.get("detail", "Chat failed")}
    except Exception as e:
        return {"status": "error", "error": f"Connection failed: {str(e)}"}


@app.post("/api/tools")
async def api_tools(data: dict):
    """Execute tools on backend."""
    try:
        app_id = data.get("appId")
        user_id = data.get("userId")
        turn_id = data.get("turnId")
        tool_results = data.get("toolResults", [])
        
        if not all([app_id, user_id, turn_id]):
            return {"status": "error", "error": "Missing required fields"}
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BACKEND_API}/v1/chat/tools",
                json={
                    "app_id": app_id,
                    "user_id": user_id,
                    "turn_id": turn_id,
                    "tool_results": [
                        {
                            "call_id": tr.get("callId"),
                            "tool_name": tr.get("name"),
                            "result": tr.get("result")
                        }
                        for tr in tool_results
                    ],
                    "mode": "sync"
                },
                timeout=60.0
            )
            result = response.json()
            
            if response.status_code == 200:
                return {
                    "status": result.get("status", "reply"),
                    "reply": result.get("reply"),
                    "toolCalls": result.get("tool_calls", []),
                    "turnId": result.get("turn_id"),
                }
            else:
                return {"status": "error", "error": result.get("detail", "Tool execution failed")}
    except Exception as e:
        return {"status": "error", "error": f"Connection failed: {str(e)}"}


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("   AgenticStack Test Dashboard")
    print("=" * 60)
    print("\n📊 Dashboard:  http://localhost:8888")
    print("🔌 Backend:    http://localhost:8848")
    print("\n⚠️  Make sure backend is running!")
    print("   docker-compose -f docker-compose.local.yml up")
    print("\n" + "=" * 60 + "\n")
    
    uvicorn.run(app, host="0.0.0.0", port=DASHBOARD_PORT)
