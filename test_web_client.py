#!/usr/bin/env python3
"""
AgenticStack — Web Test Client

Visual web dashboard that mocks a real external service consuming AgenticStack.
Streams tool calls and results in real-time via WebSocket.

Usage:  python3 test_web_client.py [--port 8889] [--backend http://localhost:8848]
Access: http://localhost:8889
"""

import argparse
import json
import logging

import httpx
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

BACKEND_API = "http://localhost:8848"
CLIENT_PORT = 8889

DEFAULT_APP_CONFIG = {
    "appName": "property_agent",
    "description": (
        "You are a helpful real estate assistant for Nepal. "
        "Help users search for properties, get details, and shortlist options. "
        "Always clarify property type (house/apartment/land) and listing type "
        "(sale/rent) before searching."
    ),
    "systemPrompt": None,
    "state": {"domain": "real_estate", "currency": "NPR", "language": "en"},
    "tools": [
        {
            "name": "search_properties",
            "description": "Search for properties matching criteria.",
            "parameters": {
                "type": "object",
                "properties": {
                    "propertyType": {"type": "string", "enum": ["house", "apartment", "land", "commercial"], "description": "Type of property"},
                    "listingType": {"type": "string", "enum": ["sale", "rent"], "description": "Buy or rent"},
                    "location": {"type": "string", "description": "City or area name"},
                    "maxPrice": {"type": "number", "description": "Max price in NPR"},
                    "minBedrooms": {"type": "integer", "description": "Min bedrooms"},
                },
                "required": ["propertyType", "listingType"],
            },
            "required": ["propertyType", "listingType"],
        },
        {
            "name": "get_property_details",
            "description": "Get full details of a specific property by its slug.",
            "parameters": {
                "type": "object",
                "properties": {"slug": {"type": "string", "description": "Property slug"}},
                "required": ["slug"],
            },
            "required": ["slug"],
        },
        {
            "name": "shortlist_property",
            "description": "Save a property to the user shortlist.",
            "parameters": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string", "description": "Property slug"},
                    "note": {"type": "string", "description": "Optional note"},
                },
                "required": ["slug"],
            },
            "required": ["slug"],
        },
        {
            "name": "get_shortlist",
            "description": "Retrieve the user shortlisted properties.",
            "parameters": {"type": "object", "properties": {}, "required": []},
            "required": [],
        },
    ],
}

MOCK_PROPERTIES = [
    {"slug": "modern-house-kathmandu-001", "title": "Modern 4BHK House in Baluwatar", "propertyType": "house", "listingType": "sale", "location": "Baluwatar, Kathmandu", "price": 35_000_000, "bedrooms": 4, "area": "12 aana", "description": "Newly built modern house with parking and garden."},
    {"slug": "apartment-rent-patan-002", "title": "2BHK Apartment for Rent in Patan", "propertyType": "apartment", "listingType": "rent", "location": "Patan, Lalitpur", "price": 25_000, "bedrooms": 2, "area": "900 sqft", "description": "Fully furnished apartment near Patan Dhoka."},
    {"slug": "house-rent-thamel-003", "title": "3BHK House for Rent in Thamel", "propertyType": "house", "listingType": "rent", "location": "Thamel, Kathmandu", "price": 45_000, "bedrooms": 3, "area": "10 aana", "description": "Spacious house in tourist hub with roof terrace."},
    {"slug": "land-pokhara-004", "title": "Ropani Land in Lakeside Pokhara", "propertyType": "land", "listingType": "sale", "location": "Lakeside, Pokhara", "price": 8_000_000, "bedrooms": 0, "area": "4 ropani", "description": "Prime land plot close to Fewa Lake."},
    {"slug": "apartment-sale-lalitpur-005", "title": "Luxury 3BHK Apartment in Lalitpur", "propertyType": "apartment", "listingType": "sale", "location": "Sanepa, Lalitpur", "price": 22_000_000, "bedrooms": 3, "area": "1400 sqft", "description": "High-rise apartment with city views and gym."},
]

_shortlists: dict = {}


def execute_tool(name: str, args: dict, user_id: str) -> str:
    sl = _shortlists.setdefault(user_id, [])
    if name == "search_properties":
        ptype = (args.get("propertyType") or "").lower()
        ltype = (args.get("listingType") or "").lower()
        loc = (args.get("location") or "").lower()
        max_p = args.get("maxPrice")
        min_b = args.get("minBedrooms") or 0
        res = [p for p in MOCK_PROPERTIES
               if (not ptype or p["propertyType"] == ptype)
               and (not ltype or p["listingType"] == ltype)
               and (not loc or loc in p["location"].lower())
               and (max_p is None or p["price"] <= max_p)
               and p["bedrooms"] >= min_b]
        return json.dumps({"found": len(res), "properties": res})
    elif name == "get_property_details":
        slug = args.get("slug", "")
        prop = next((p for p in MOCK_PROPERTIES if p["slug"] == slug), None)
        return json.dumps(prop if prop else {"error": f"Not found: {slug}"})
    elif name == "shortlist_property":
        slug = args.get("slug", "")
        note = args.get("note", "")
        if not any(s["slug"] == slug for s in sl):
            sl.append({"slug": slug, "note": note})
        return json.dumps({"shortlisted": slug, "total": len(sl)})
    elif name == "get_shortlist":
        return json.dumps({"shortlist": sl, "total": len(sl)})
    return json.dumps({"error": f"Unknown tool: {name}"})


app = FastAPI()


@app.get("/")
async def index():
    return HTMLResponse(HTML)


@app.get("/api/config")
async def get_config():
    return DEFAULT_APP_CONFIG


@app.post("/api/register")
async def api_register(data: dict):
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{BACKEND_API}/v1/apps/register",
                json={
                    "appName": data.get("appName"),
                    "description": data.get("description", ""),
                    "systemPrompt": data.get("systemPrompt") or None,
                    "tools": data.get("tools", []),
                    "state": data.get("state", {}),
                },
                timeout=30.0,
            )
            result = resp.json()
            if resp.status_code in (200, 409):
                reg_status = "already_registered" if resp.status_code == 409 else "registered"
                return {"status": "success", "registrationStatus": reg_status, "toolCount": result.get("toolCount", len(data.get("tools", [])))}
            return {"status": "error", "error": result.get("detail", "Registration failed")}
    except Exception as e:
        return {"status": "error", "error": f"Connection failed: {e}"}


@app.get("/api/health")
async def api_health():
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{BACKEND_API}/v1/health", timeout=5.0)
            return resp.json()
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.websocket("/ws/{user_id}")
async def ws_chat(websocket: WebSocket, user_id: str):
    await websocket.accept()

    async def send(event: dict):
        await websocket.send_json(event)

    async def process(result: dict):
        status = result.get("status")
        if status == "reply":
            await send({"type": "reply", "text": result.get("reply", "")})
            return
        if status == "tool_calls":
            calls = result.get("toolCalls") or []
            turn_id = result.get("turnId")
            await send({"type": "tool_calls_start", "turnId": turn_id, "count": len(calls)})
            tool_results = []
            for tc in calls:
                name = tc.get("name", "")
                args = tc.get("args") or {}
                call_id = tc.get("id", "")
                await send({"type": "tool_call", "id": call_id, "name": name, "args": args})
                result_str = execute_tool(name, args, user_id)
                try:
                    result_data = json.loads(result_str)
                except Exception:
                    result_data = result_str
                await send({"type": "tool_result", "id": call_id, "name": name, "result": result_data})
                tool_results.append({"callId": call_id, "name": name, "result": result_str})
            await send({"type": "status", "text": "Sending tool results..."})
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{BACKEND_API}/v1/chat/tools",
                    json={"appId": user_id.split("__")[0] if "__" in user_id else "property_agent",
                          "userId": user_id, "turnId": turn_id, "toolResults": tool_results},
                    timeout=60.0,
                )
                resp.raise_for_status()
                await process(resp.json())
            return
        if status == "error":
            await send({"type": "error", "text": result.get("error", "Unknown error")})
            return
        await send({"type": "error", "text": f"Unexpected status: {status}"})

    try:
        async with httpx.AsyncClient() as client:
            while True:
                data = await websocket.receive_json()
                if data.get("type") != "chat":
                    continue
                message = data.get("message", "")
                app_id = data.get("appId", "")
                state = data.get("state") or None
                payload: dict = {"appId": app_id, "userId": user_id, "message": message}
                if state:
                    payload["state"] = state
                await send({"type": "status", "text": "Sending to AgenticStack..."})
                try:
                    resp = await client.post(f"{BACKEND_API}/v1/chat", json=payload, timeout=60.0)
                    resp.raise_for_status()
                    await process(resp.json())
                except httpx.HTTPStatusError as e:
                    await send({"type": "error", "text": f"HTTP {e.response.status_code}: {e.response.text}"})
                except Exception as e:
                    await send({"type": "error", "text": str(e)})
    except WebSocketDisconnect:
        pass


HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AgenticStack — Test Client</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
:root {
  --bg: #0d1117; --surface: #161b22; --surface2: #21262d; --border: #30363d;
  --text: #e6edf3; --text2: #8b949e;
  --blue: #58a6ff; --green: #3fb950; --orange: #d29922;
  --red: #f85149; --purple: #bc8cff; --cyan: #39d353;
  --radius: 8px; --font: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}
body { font-family: var(--font); background: var(--bg); color: var(--text); height: 100vh; overflow: hidden; }
.layout { display: grid; grid-template-columns: 340px 1fr 360px; height: 100vh; gap: 1px; background: var(--border); }
.panel { background: var(--bg); display: flex; flex-direction: column; overflow: hidden; }
.panel-header { padding: 13px 16px; border-bottom: 1px solid var(--border); background: var(--surface); display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.panel-header h2 { font-size: 13px; font-weight: 600; }
.dot { width: 8px; height: 8px; border-radius: 50%; background: var(--text2); flex-shrink: 0; transition: background .3s; }
.dot.green { background: var(--green); box-shadow: 0 0 6px var(--green); }
.dot.red { background: var(--red); }
.dot.orange { background: var(--orange); }
.panel-body { flex: 1; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 10px; }
.panel-body::-webkit-scrollbar { width: 4px; }
.panel-body::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }
.section { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 12px; }
.section-title { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .8px; color: var(--text2); margin-bottom: 8px; }
label { font-size: 12px; color: var(--text2); display: block; margin-bottom: 3px; }
input, textarea {
  width: 100%; background: var(--bg); border: 1px solid var(--border); color: var(--text);
  border-radius: 6px; padding: 7px 10px; font-size: 12px; font-family: var(--font); transition: border-color .15s;
}
input:focus, textarea:focus { outline: none; border-color: var(--blue); }
textarea { resize: vertical; }
.form-row { margin-bottom: 8px; }
.btn { border: none; border-radius: 6px; cursor: pointer; font-size: 12px; font-weight: 600; padding: 8px 16px; transition: opacity .15s, transform .1s; }
.btn:hover { opacity: .85; } .btn:active { transform: scale(.97); } .btn:disabled { opacity: .4; cursor: not-allowed; }
.btn-primary { background: var(--blue); color: #0d1117; }
.btn-success { background: var(--green); color: #0d1117; }
.btn-ghost { background: var(--surface2); color: var(--text); border: 1px solid var(--border); }
.btn-row { display: flex; gap: 6px; }
.badge { display: inline-flex; align-items: center; gap: 4px; font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 12px; }
.badge-blue { background: rgba(88,166,255,.15); color: var(--blue); border: 1px solid rgba(88,166,255,.3); }
.badge-green { background: rgba(63,185,80,.15); color: var(--green); border: 1px solid rgba(63,185,80,.3); }
.badge-orange { background: rgba(210,153,34,.15); color: var(--orange); border: 1px solid rgba(210,153,34,.3); }
.badge-red { background: rgba(248,81,73,.15); color: var(--red); border: 1px solid rgba(248,81,73,.3); }
.badge-purple { background: rgba(188,140,255,.15); color: var(--purple); border: 1px solid rgba(188,140,255,.3); }
/* status bar */
#statusBar { font-size: 11px; padding: 6px 14px; background: var(--surface); border-top: 1px solid var(--border); color: var(--text2); flex-shrink: 0; }
/* messages */
#messages { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 10px; }
#messages::-webkit-scrollbar { width: 4px; }
#messages::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }
.msg { max-width: 76%; display: flex; flex-direction: column; gap: 3px; animation: fadein .2s ease; }
@keyframes fadein { from { opacity:0; transform: translateY(6px); } to { opacity:1; transform: none; } }
.msg.user { align-self: flex-end; }
.msg.agent { align-self: flex-start; }
.msg.sys { align-self: center; max-width: 92%; }
.msg-label { font-size: 10px; color: var(--text2); }
.msg.user .msg-label { text-align: right; }
.msg-bubble { padding: 10px 14px; border-radius: 12px; font-size: 13px; line-height: 1.6; white-space: pre-wrap; word-break: break-word; }
.msg.user .msg-bubble { background: var(--blue); color: #0d1117; border-bottom-right-radius: 4px; }
.msg.agent .msg-bubble { background: var(--surface2); border: 1px solid var(--border); border-bottom-left-radius: 4px; }
.msg.sys .msg-bubble { background: transparent; color: var(--text2); font-size: 11px; text-align: center; border: 1px dashed var(--border); border-radius: 6px; padding: 6px 12px; }
/* tool cards */
.tool-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; animation: fadein .2s ease; width: 100%; max-width: 520px; align-self: flex-start; }
.tool-card-header { display: flex; align-items: center; gap: 8px; padding: 8px 12px; background: var(--surface2); border-bottom: 1px solid var(--border); }
.tool-name { font-size: 12px; font-weight: 700; color: var(--purple); font-family: monospace; }
.tool-body { padding: 10px 12px; display: flex; flex-direction: column; gap: 6px; }
.tlabel { font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: .6px; color: var(--text2); }
.tjson { background: var(--bg); border: 1px solid var(--border); border-radius: 4px; padding: 6px 8px; font-size: 11px; font-family: monospace; white-space: pre-wrap; word-break: break-all; color: var(--cyan); max-height: 130px; overflow-y: auto; }
.tjson.res { color: var(--green); }
.tool-card.pending .tool-card-header { border-left: 3px solid var(--orange); }
.tool-card.done .tool-card-header { border-left: 3px solid var(--green); }
.spinner { width: 12px; height: 12px; border: 2px solid var(--border); border-top-color: var(--orange); border-radius: 50%; animation: spin .7s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
/* chat input */
.chat-input-row { display: flex; gap: 8px; padding: 12px 16px; border-top: 1px solid var(--border); background: var(--surface); flex-shrink: 0; }
#msgInput { flex: 1; background: var(--bg); border: 1px solid var(--border); color: var(--text); border-radius: 8px; padding: 9px 12px; font-size: 13px; font-family: var(--font); }
#msgInput:focus { outline: none; border-color: var(--blue); }
/* right panel */
.kv { display: flex; justify-content: space-between; align-items: center; font-size: 12px; padding: 4px 0; border-bottom: 1px solid var(--border); }
.kv:last-child { border-bottom: none; }
.kk { color: var(--text2); }
.kv-val { font-family: monospace; font-size: 11px; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.json-view { background: var(--bg); border: 1px solid var(--border); border-radius: 6px; padding: 8px; font-family: monospace; font-size: 11px; white-space: pre-wrap; color: var(--cyan); max-height: 150px; overflow-y: auto; }
.tool-pill { display: flex; align-items: flex-start; gap: 6px; padding: 6px 8px; background: var(--bg); border: 1px solid var(--border); border-radius: 6px; margin-bottom: 4px; font-size: 11px; flex-direction: column; }
.tpname { font-weight: 700; color: var(--purple); font-family: monospace; }
.tpdesc { color: var(--text2); font-size: 10px; }
.event-log { display: flex; flex-direction: column; gap: 4px; }
.ev { display: flex; gap: 8px; font-size: 11px; align-items: flex-start; }
.ev-time { color: var(--text2); flex-shrink: 0; font-family: monospace; font-size: 10px; }
.ev-text { color: var(--text); } .ev-text.tool { color: var(--purple); } .ev-text.ok { color: var(--green); } .ev-text.err { color: var(--red); }
</style>
</head>
<body>
<div class="layout">

<!-- LEFT: CONFIG -->
<div class="panel">
  <div class="panel-header">
    <div class="dot" id="backendDot"></div>
    <h2>Configuration</h2>
    <span id="backendBadge" class="badge badge-orange" style="margin-left:auto;font-size:10px">checking...</span>
  </div>
  <div class="panel-body">
    <div class="section">
      <div class="section-title">App Registration</div>
      <div class="form-row"><label>App Name</label><input id="appName" value="property_agent"></div>
      <div class="form-row"><label>Description</label><textarea id="appDesc" rows="3">Real estate property search assistant for Nepal</textarea></div>
      <div class="form-row"><label>System Prompt <span style="color:var(--text2);font-size:10px">(optional)</span></label><textarea id="sysPrompt" rows="2" placeholder="Leave empty to auto-build"></textarea></div>
      <div class="form-row"><label>User ID</label><input id="userId" value="test_user_001"></div>
    </div>
    <div class="section">
      <div class="section-title">Default State <span style="color:var(--text2);text-transform:none;font-size:10px;letter-spacing:0">(merged into every turn)</span></div>
      <textarea id="appState" rows="4" style="font-family:monospace;font-size:11px"></textarea>
    </div>
    <div class="section">
      <div class="section-title">Tools <span style="color:var(--text2);text-transform:none;font-size:10px;letter-spacing:0">(JSON array of tool schemas)</span></div>
      <textarea id="appTools" rows="10" style="font-family:monospace;font-size:11px"></textarea>
    </div>
    <div class="btn-row">
      <button class="btn btn-primary" style="flex:1" onclick="registerApp()">⚡ Register App</button>
      <button class="btn btn-ghost" onclick="loadDefaults()">Reset</button>
    </div>
    <div id="regStatus" style="font-size:11px;text-align:center;margin-top:2px"></div>
  </div>
</div>

<!-- CENTER: CHAT -->
<div class="panel">
  <div class="panel-header">
    <div class="dot" id="chatDot"></div>
    <h2>Chat</h2>
    <span id="appBadge" class="badge badge-orange" style="margin-left:auto">not connected</span>
  </div>
  <div id="messages">
    <div class="msg sys"><div class="msg-bubble">Register an app on the left to start chatting</div></div>
  </div>
  <div class="chat-input-row">
    <input id="msgInput" placeholder="Type a message… (Enter to send)" disabled
      onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();sendMsg()}">
    <button class="btn btn-success" id="sendBtn" onclick="sendMsg()" disabled>Send</button>
  </div>
  <div id="statusBar">Idle</div>
</div>

<!-- RIGHT: DEBUG -->
<div class="panel">
  <div class="panel-header"><h2>🔍 Live Debug</h2></div>
  <div class="panel-body">
    <div class="section">
      <div class="section-title">Session</div>
      <div class="kv"><span class="kk">App</span><span class="kv-val" id="dApp">—</span></div>
      <div class="kv"><span class="kk">User</span><span class="kv-val" id="dUser">—</span></div>
      <div class="kv"><span class="kk">Turn ID</span><span class="kv-val" id="dTurn">—</span></div>
      <div class="kv"><span class="kk">Status</span><span id="dStatus" class="badge badge-orange">idle</span></div>
      <div class="kv"><span class="kk">Messages</span><span class="kv-val" id="dMsgs">0</span></div>
      <div class="kv"><span class="kk">Tool calls total</span><span class="kv-val" id="dTools">0</span></div>
    </div>
    <div class="section">
      <div class="section-title">Active State</div>
      <div class="json-view" id="dState">—</div>
    </div>
    <div class="section">
      <div class="section-title">Registered Tools</div>
      <div id="dToolsList"><span style="font-size:11px;color:var(--text2)">—</span></div>
    </div>
    <div class="section" style="flex:1;min-height:120px">
      <div class="section-title">Event Log</div>
      <div class="event-log" id="eventLog"></div>
    </div>
  </div>
</div>

</div>
<script>
const S = { appId:null, userId:null, appState:null, ws:null, msgCount:0, toolCount:0, currentTurn:null, cards:{} };

document.addEventListener('DOMContentLoaded', () => { loadDefaults(); checkHealth(); setInterval(checkHealth, 15000); });

async function loadDefaults() {
  const cfg = await fetch('/api/config').then(r=>r.json());
  document.getElementById('appName').value = cfg.appName||'';
  document.getElementById('appDesc').value = cfg.description||'';
  document.getElementById('sysPrompt').value = cfg.systemPrompt||'';
  document.getElementById('appState').value = JSON.stringify(cfg.state||{}, null, 2);
  document.getElementById('appTools').value = JSON.stringify(cfg.tools||[], null, 2);
}

async function checkHealth() {
  try {
    const h = await fetch('/api/health').then(r=>r.json());
    const ok = h.status !== 'error';
    document.getElementById('backendDot').className = 'dot '+(ok?'green':'red');
    document.getElementById('backendBadge').textContent = ok ? `${h.llmProvider} / ${h.llmModel}` : 'unreachable';
    document.getElementById('backendBadge').className = 'badge '+(ok?'badge-green':'badge-red');
  } catch { document.getElementById('backendDot').className='dot red'; document.getElementById('backendBadge').textContent='unreachable'; document.getElementById('backendBadge').className='badge badge-red'; }
}

async function registerApp() {
  let stateVal, toolsVal;
  try { stateVal = JSON.parse(document.getElementById('appState').value||'{}'); } catch { return setReg('⚠ Invalid JSON in Default State','red'); }
  try { toolsVal = JSON.parse(document.getElementById('appTools').value||'[]'); } catch { return setReg('⚠ Invalid JSON in Tools','red'); }
  const appName = document.getElementById('appName').value.trim();
  const userId = document.getElementById('userId').value.trim();
  if (!appName||!userId) return setReg('⚠ App Name and User ID required','red');
  setReg('Registering...','orange');
  try {
    const d = await fetch('/api/register', { method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ appName, description: document.getElementById('appDesc').value,
        systemPrompt: document.getElementById('sysPrompt').value||null, state: stateVal, tools: toolsVal })
    }).then(r=>r.json());
    if (d.status==='success') {
      S.appId=appName; S.userId=userId; S.appState=stateVal;
      setReg(`✓ ${d.registrationStatus} — ${d.toolCount} tool(s)`,'green');
      renderToolsList(toolsVal); connectWS(); updateDebug(); log('App registered','ok');
    } else { setReg(`✗ ${d.error}`,'red'); log(`Register failed: ${d.error}`,'err'); }
  } catch(e) { setReg(`✗ ${e.message}`,'red'); }
}

function setReg(msg,c) {
  const el=document.getElementById('regStatus');
  el.textContent=msg;
  el.style.color = c==='green'?'var(--green)':c==='red'?'var(--red)':'var(--orange)';
}

function connectWS() {
  if (S.ws) S.ws.close();
  S.ws = new WebSocket(`ws://${location.host}/ws/${encodeURIComponent(S.userId)}`);
  S.ws.onopen = () => {
    document.getElementById('chatDot').className='dot green';
    document.getElementById('appBadge').textContent=S.appId;
    document.getElementById('appBadge').className='badge badge-green';
    document.getElementById('msgInput').disabled=false;
    document.getElementById('sendBtn').disabled=false;
    clearChat(); addSys(`Connected · app="${S.appId}" · user="${S.userId}"`);
    setStatus('Ready'); log('WebSocket connected','ok');
    // update dStatus
    document.getElementById('dStatus').textContent='connected';
    document.getElementById('dStatus').className='badge badge-green';
  };
  S.ws.onmessage = e => onWsMsg(JSON.parse(e.data));
  S.ws.onclose = () => {
    document.getElementById('chatDot').className='dot red';
    document.getElementById('appBadge').textContent='disconnected';
    document.getElementById('appBadge').className='badge badge-red';
    document.getElementById('dStatus').textContent='disconnected';
    document.getElementById('dStatus').className='badge badge-red';
    setStatus('Disconnected'); log('WebSocket closed','err');
  };
}

function sendMsg() {
  const inp=document.getElementById('msgInput'), txt=inp.value.trim();
  if (!txt||!S.ws||S.ws.readyState!==WebSocket.OPEN) return;
  addMsg(txt,'user'); S.msgCount++; inp.value='';
  inp.disabled=true; document.getElementById('sendBtn').disabled=true;
  document.getElementById('dStatus').textContent='sending'; document.getElementById('dStatus').className='badge badge-orange';
  setStatus('Sending…'); updateDebug();
  S.ws.send(JSON.stringify({type:'chat', appId:S.appId, message:txt, state:S.appState}));
}

function onWsMsg(msg) {
  if (msg.type==='status') { setStatus(msg.text); log(msg.text); return; }
  if (msg.type==='tool_calls_start') {
    S.currentTurn=msg.turnId;
    document.getElementById('dStatus').textContent=`${msg.count} tool(s) running`;
    document.getElementById('dStatus').className='badge badge-purple';
    document.getElementById('dTurn').textContent=msg.turnId?(msg.turnId.slice(0,12)+'…'):'—';
    setStatus(`Executing ${msg.count} tool(s)…`);
    log(`Turn ${(msg.turnId||'').slice(0,8)} · ${msg.count} tool call(s)`,'tool');
    return;
  }
  if (msg.type==='tool_call') {
    S.toolCount++;
    const card=makeToolCard(msg.id, msg.name, msg.args);
    document.getElementById('messages').appendChild(card);
    S.cards[msg.id]=card; scroll(); updateDebug();
    log(`→ ${msg.name}(…)`,'tool'); return;
  }
  if (msg.type==='tool_result') {
    const card=S.cards[msg.id];
    if (card) {
      card.classList.remove('pending'); card.classList.add('done');
      const sp=card.querySelector('.spinner'); if(sp) sp.outerHTML='<span style="font-size:14px;color:var(--green)">✓</span>';
      const b=card.querySelector('.tbadge'); if(b){b.textContent='done';b.className='badge badge-green tbadge';}
      const rd=card.querySelector('.res-section'); if(rd){ rd.style.display='block'; rd.querySelector('.tjson').textContent=JSON.stringify(msg.result,null,2); }
    }
    log(`← ${msg.name} result`,'ok'); return;
  }
  if (msg.type==='reply') {
    addMsg(msg.text,'agent'); S.msgCount++;
    document.getElementById('msgInput').disabled=false; document.getElementById('sendBtn').disabled=false;
    document.getElementById('msgInput').focus();
    document.getElementById('dStatus').textContent='ready'; document.getElementById('dStatus').className='badge badge-green';
    setStatus('Ready'); updateDebug(); log('Agent replied','ok'); return;
  }
  if (msg.type==='error') {
    addMsg(`⚠ ${msg.text}`,'agent');
    document.getElementById('msgInput').disabled=false; document.getElementById('sendBtn').disabled=false;
    document.getElementById('dStatus').textContent='error'; document.getElementById('dStatus').className='badge badge-red';
    setStatus('Error'); log(`Error: ${msg.text}`,'err'); return;
  }
}

function makeToolCard(id, name, args) {
  const d=document.createElement('div'); d.className='tool-card pending';
  d.innerHTML=`<div class="tool-card-header">
    <span style="font-size:14px">⚙</span>
    <span class="tool-name">${esc(name)}</span>
    <span class="badge badge-orange tbadge" style="margin-left:auto">running</span>
    <div class="spinner" style="margin-left:6px"></div>
  </div>
  <div class="tool-body">
    <div class="tlabel">Input</div>
    <pre class="tjson">${esc(JSON.stringify(args,null,2))}</pre>
    <div class="res-section" style="display:none">
      <div class="tlabel" style="margin-top:4px">Result</div>
      <pre class="tjson res"></pre>
    </div>
  </div>`;
  return d;
}

function addMsg(text,type) {
  const c=document.getElementById('messages'), d=document.createElement('div');
  d.className=`msg ${type}`;
  d.innerHTML=`<div class="msg-label">${type==='user'?'You':type==='agent'?'Agent':''}</div><div class="msg-bubble">${esc(text)}</div>`;
  c.appendChild(d); scroll();
}
function addSys(t) {
  const c=document.getElementById('messages'),d=document.createElement('div');
  d.className='msg sys'; d.innerHTML=`<div class="msg-bubble">${esc(t)}</div>`;
  c.appendChild(d); scroll();
}
function clearChat() { document.getElementById('messages').innerHTML=''; S.msgCount=0; S.toolCount=0; S.cards={}; updateDebug(); }
function scroll() { const e=document.getElementById('messages'); e.scrollTop=e.scrollHeight; }
function setStatus(t) { document.getElementById('statusBar').textContent=t; }
function updateDebug() {
  document.getElementById('dApp').textContent=S.appId||'—';
  document.getElementById('dUser').textContent=S.userId||'—';
  document.getElementById('dMsgs').textContent=S.msgCount;
  document.getElementById('dTools').textContent=S.toolCount;
  if (S.appState) document.getElementById('dState').textContent=JSON.stringify(S.appState,null,2);
}
function renderToolsList(tools) {
  const el=document.getElementById('dToolsList');
  if (!tools||!tools.length) { el.innerHTML='<span style="font-size:11px;color:var(--text2)">none</span>'; return; }
  el.innerHTML=tools.map(t=>`<div class="tool-pill"><span class="tpname">${esc(t.name)}</span><span class="tpdesc">${esc(t.description||'')}</span></div>`).join('');
}
function log(text,cls='') {
  const lg=document.getElementById('eventLog');
  const now=new Date().toLocaleTimeString('en',{hour12:false,hour:'2-digit',minute:'2-digit',second:'2-digit'});
  const d=document.createElement('div'); d.className='ev';
  d.innerHTML=`<span class="ev-time">${now}</span><span class="ev-text ${cls}">${esc(text)}</span>`;
  lg.prepend(d); while(lg.children.length>60)lg.removeChild(lg.lastChild);
}
function esc(s) { return String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
</script>
</body>
</html>
"""

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=CLIENT_PORT)
    parser.add_argument("--backend", default=BACKEND_API)
    args = parser.parse_args()
    BACKEND_API = args.backend.rstrip("/")
    logging.basicConfig(level=logging.WARNING)
    print(f"\nAgenticStack Web Test Client")
    print(f"  Dashboard : http://localhost:{args.port}")
    print(f"  Backend   : {BACKEND_API}\n")
    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="warning")
