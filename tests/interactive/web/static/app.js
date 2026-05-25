const S = { appId: null, userId: null, appState: null, ws: null, msgCount: 0, toolCount: 0, currentTurn: null, cards: {} };

document.addEventListener('DOMContentLoaded', () => { loadDefaults(); checkHealth(); setInterval(checkHealth, 15000); });

// ── Config / registration ─────────────────────────────────────────────────────

async function loadDefaults() {
  const cfg = await fetch('/api/config').then(r => r.json());
  document.getElementById('appName').value   = cfg.appName || '';
  document.getElementById('sysPrompt').value = cfg.systemPrompt || '';
  document.getElementById('appState').value  = JSON.stringify(cfg.state || {}, null, 2);
  document.getElementById('appTools').value  = JSON.stringify(cfg.tools || [], null, 2);
}

async function checkHealth() {
  try {
    const h = await fetch('/api/health').then(r => r.json());
    const ok = h.status !== 'error';
    document.getElementById('backendDot').className = 'dot ' + (ok ? 'green' : 'red');
    document.getElementById('backendBadge').textContent = ok ? `${h.llmProvider} / ${h.llmModel}` : 'unreachable';
    document.getElementById('backendBadge').className = 'badge ' + (ok ? 'badge-green' : 'badge-red');
  } catch {
    document.getElementById('backendDot').className = 'dot red';
    document.getElementById('backendBadge').textContent = 'unreachable';
    document.getElementById('backendBadge').className = 'badge badge-red';
  }
}

async function registerApp() {
  let stateVal, toolsVal;
  try { stateVal = JSON.parse(document.getElementById('appState').value || '{}'); }
  catch { return setReg('⚠ Invalid JSON in Default State', 'red'); }
  try { toolsVal = JSON.parse(document.getElementById('appTools').value || '[]'); }
  catch { return setReg('⚠ Invalid JSON in Tools', 'red'); }

  const appName = document.getElementById('appName').value.trim();
  const userId  = document.getElementById('userId').value.trim();
  if (!appName || !userId) return setReg('⚠ App Name and User ID required', 'red');

  setReg('Registering...', 'orange');
  try {
    const d = await fetch('/api/register', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        appName,
        systemPrompt: document.getElementById('sysPrompt').value || null,
        state:        stateVal,
        tools:        toolsVal,
      }),
    }).then(r => r.json());

    if (d.status === 'success') {
      S.appId = appName; S.userId = userId; S.appState = stateVal;
      setReg(`✓ ${d.registrationStatus} — ${d.toolCount} tool(s)`, 'green');
      renderToolsList(toolsVal); connectWS(); updateDebug(); log('App registered', 'ok');
    } else {
      setReg(`✗ ${d.error}`, 'red'); log(`Register failed: ${d.error}`, 'err');
    }
  } catch (e) { setReg(`✗ ${e.message}`, 'red'); }
}

function setReg(msg, c) {
  const el = document.getElementById('regStatus');
  el.textContent = msg;
  el.style.color = c === 'green' ? 'var(--green)' : c === 'red' ? 'var(--red)' : 'var(--orange)';
}

// ── WebSocket ─────────────────────────────────────────────────────────────────

function connectWS() {
  if (S.ws) S.ws.close();
  S.ws = new WebSocket(`ws://${location.host}/ws/${encodeURIComponent(S.userId)}`);

  S.ws.onopen = () => {
    document.getElementById('chatDot').className = 'dot green';
    document.getElementById('appBadge').textContent = S.appId;
    document.getElementById('appBadge').className = 'badge badge-green';
    document.getElementById('msgInput').disabled = false;
    document.getElementById('sendBtn').disabled = false;
    clearChat(); addSys(`Connected · app="${S.appId}" · user="${S.userId}"`);
    setStatus('Ready'); log('WebSocket connected', 'ok');
    document.getElementById('dStatus').textContent = 'connected';
    document.getElementById('dStatus').className = 'badge badge-green';
  };

  S.ws.onmessage = e => onWsMsg(JSON.parse(e.data));

  S.ws.onclose = () => {
    document.getElementById('chatDot').className = 'dot red';
    document.getElementById('appBadge').textContent = 'disconnected';
    document.getElementById('appBadge').className = 'badge badge-red';
    document.getElementById('dStatus').textContent = 'disconnected';
    document.getElementById('dStatus').className = 'badge badge-red';
    setStatus('Disconnected'); log('WebSocket closed', 'err');
  };
}

// ── Messaging ─────────────────────────────────────────────────────────────────

function sendMsg() {
  const inp = document.getElementById('msgInput'), txt = inp.value.trim();
  if (!txt || !S.ws || S.ws.readyState !== WebSocket.OPEN) return;
  const systemPrompt = (document.getElementById('sysPrompt').value || '').trim();
  addMsg(txt, 'user'); S.msgCount++; inp.value = '';
  inp.disabled = true; document.getElementById('sendBtn').disabled = true;
  document.getElementById('dStatus').textContent = 'sending';
  document.getElementById('dStatus').className = 'badge badge-orange';
  setStatus('Sending…'); updateDebug();
  S.ws.send(JSON.stringify({
    type: 'chat',
    appId: S.appId,
    message: txt,
    state: S.appState,
    systemPrompt: systemPrompt || null,
  }));
}

function onWsMsg(msg) {
  if (msg.type === 'status') { setStatus(msg.text); log(msg.text); return; }

  if (msg.type === 'tool_calls_start') {
    S.currentTurn = msg.turnId;
    document.getElementById('dStatus').textContent = `${msg.count} tool(s) running`;
    document.getElementById('dStatus').className = 'badge badge-purple';
    document.getElementById('dTurn').textContent = msg.turnId ? (msg.turnId.slice(0, 12) + '…') : '—';
    setStatus(`Executing ${msg.count} tool(s)…`);
    log(`Turn ${(msg.turnId || '').slice(0, 8)} · ${msg.count} tool call(s)`, 'tool');
    return;
  }

  if (msg.type === 'tool_call') {
    S.toolCount++;
    const card = makeToolCard(msg.id, msg.name, msg.args);
    document.getElementById('messages').appendChild(card);
    S.cards[msg.id] = card; scroll(); updateDebug();
    log(`→ ${msg.name}(…)`, 'tool'); return;
  }

  if (msg.type === 'tool_result') {
    const card = S.cards[msg.id];
    if (card) {
      card.classList.remove('pending'); card.classList.add('done');
      const sp = card.querySelector('.spinner'); if (sp) sp.outerHTML = '<span style="font-size:14px;color:var(--green)">✓</span>';
      const b  = card.querySelector('.tbadge'); if (b) { b.textContent = 'done'; b.className = 'badge badge-green tbadge'; }
      const rd = card.querySelector('.res-section'); if (rd) { rd.style.display = 'block'; rd.querySelector('.tjson').textContent = JSON.stringify(msg.result, null, 2); }
    }
    log(`← ${msg.name} result`, 'ok'); return;
  }

  if (msg.type === 'reply') {
    addMsg(msg.text, 'agent'); S.msgCount++;
    document.getElementById('msgInput').disabled = false;
    document.getElementById('sendBtn').disabled = false;
    document.getElementById('msgInput').focus();
    document.getElementById('dStatus').textContent = 'ready';
    document.getElementById('dStatus').className = 'badge badge-green';
    setStatus('Ready'); updateDebug(); log('Agent replied', 'ok'); return;
  }

  if (msg.type === 'error') {
    addMsg(`⚠ ${msg.text}`, 'agent');
    document.getElementById('msgInput').disabled = false;
    document.getElementById('sendBtn').disabled = false;
    document.getElementById('dStatus').textContent = 'error';
    document.getElementById('dStatus').className = 'badge badge-red';
    setStatus('Error'); log(`Error: ${msg.text}`, 'err'); return;
  }
}

// ── DOM helpers ───────────────────────────────────────────────────────────────

function makeToolCard(id, name, args) {
  const d = document.createElement('div'); d.className = 'tool-card pending';
  d.innerHTML = `
    <div class="tool-card-header">
      <span style="font-size:14px">⚙</span>
      <span class="tool-name">${esc(name)}</span>
      <span class="badge badge-orange tbadge" style="margin-left:auto">running</span>
      <div class="spinner" style="margin-left:6px"></div>
    </div>
    <div class="tool-body">
      <div class="tlabel">Input</div>
      <pre class="tjson">${esc(JSON.stringify(args, null, 2))}</pre>
      <div class="res-section" style="display:none">
        <div class="tlabel" style="margin-top:4px">Result</div>
        <pre class="tjson res"></pre>
      </div>
    </div>`;
  return d;
}

function addMsg(text, type) {
  const c = document.getElementById('messages'), d = document.createElement('div');
  d.className = `msg ${type}`;
  d.innerHTML = `<div class="msg-label">${type === 'user' ? 'You' : type === 'agent' ? 'Agent' : ''}</div><div class="msg-bubble">${esc(text)}</div>`;
  c.appendChild(d); scroll();
}

function addSys(t) {
  const c = document.getElementById('messages'), d = document.createElement('div');
  d.className = 'msg sys'; d.innerHTML = `<div class="msg-bubble">${esc(t)}</div>`;
  c.appendChild(d); scroll();
}

function clearChat() { document.getElementById('messages').innerHTML = ''; S.msgCount = 0; S.toolCount = 0; S.cards = {}; updateDebug(); }
function scroll() { const e = document.getElementById('messages'); e.scrollTop = e.scrollHeight; }
function setStatus(t) { document.getElementById('statusBar').textContent = t; }

function updateDebug() {
  document.getElementById('dApp').textContent   = S.appId  || '—';
  document.getElementById('dUser').textContent  = S.userId || '—';
  document.getElementById('dMsgs').textContent  = S.msgCount;
  document.getElementById('dTools').textContent = S.toolCount;
  if (S.appState) document.getElementById('dState').textContent = JSON.stringify(S.appState, null, 2);
}

function renderToolsList(tools) {
  const el = document.getElementById('dToolsList');
  if (!tools || !tools.length) { el.innerHTML = '<span style="font-size:11px;color:var(--text2)">none</span>'; return; }
  el.innerHTML = tools.map(t => `<div class="tool-pill"><span class="tpname">${esc(t.name)}</span><span class="tpdesc">${esc(t.description || '')}</span></div>`).join('');
}

function log(text, cls = '') {
  const lg  = document.getElementById('eventLog');
  const now = new Date().toLocaleTimeString('en', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
  const d   = document.createElement('div'); d.className = 'ev';
  d.innerHTML = `<span class="ev-time">${now}</span><span class="ev-text ${cls}">${esc(text)}</span>`;
  lg.prepend(d); while (lg.children.length > 60) lg.removeChild(lg.lastChild);
}

function esc(s) { return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
