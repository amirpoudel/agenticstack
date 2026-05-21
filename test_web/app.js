/**
 * AgenticStack Test Dashboard - Frontend Logic
 */

// ==================== STATE ====================
const state = {
    currentApp: null,
    currentUserId: null,
    currentTurnId: null,
    currentState: null,
    messageCount: 0,
    toolCallCount: 0,
    messages: [],
    activeToolCalls: [],
};

// ==================== INITIALIZATION ====================
document.addEventListener('DOMContentLoaded', () => {
    console.log('Dashboard initialized');
});

// ==================== APP REGISTRATION ====================
async function registerApp() {
    const appName = document.getElementById('appName').value.trim();
    const userId = document.getElementById('userId').value.trim();
    
    if (!appName || !userId) {
        showStatus('App name and User ID are required', 'error');
        return;
    }
    
    showStatus('Registering app...', 'info');
    
    let parsedState = {};
    let parsedTools = [];
    try {
        parsedState = JSON.parse(document.getElementById('appState').value || '{}');
    } catch (e) {
        showStatus('Invalid JSON in Default State', 'error');
        return;
    }
    try {
        parsedTools = JSON.parse(document.getElementById('appTools').value || '[]');
    } catch (e) {
        showStatus('Invalid JSON in Tools', 'error');
        return;
    }

    try {
        const response = await fetch('/api/register', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                appName: appName,
                description: document.getElementById('appDescription').value,
                systemPrompt: document.getElementById('systemPrompt').value || null,
                state: parsedState,
                tools: parsedTools,
            })
        });

        const data = await response.json();

        if (data.status === 'success') {
            state.currentApp = appName;
            state.currentUserId = userId;
            state.currentState = parsedState;

            showStatus(`✓ App registered: ${appName} (${data.toolCount || 0} tools)`, 'success');
            enableChatUI();
            updateDebugInfo();
            clearMessages();
            renderToolsList(parsedTools);

            addSystemMessage(`App "${appName}" registered. Tools: ${data.toolCount || 0}. Ready to chat!`);
        } else {
            showStatus(`✗ Error: ${data.error}`, 'error');
        }
    } catch (error) {
        showStatus(`✗ Failed: ${error.message}`, 'error');
    }
}

function renderToolsList(tools) {
    const el = document.getElementById('toolsList');
    if (!tools || tools.length === 0) {
        el.innerHTML = '<p class="text-muted">No tools registered</p>';
        return;
    }
    el.innerHTML = tools.map(t =>
        `<div class="tool-item"><strong>${t.name}</strong><br><small>${t.description || ''}</small></div>`
    ).join('');
}

// ==================== CHAT ====================
async function sendMessage() {
    const input = document.getElementById('messageInput');
    const message = input.value.trim();
    
    if (!message || !state.currentApp) return;
    
    // Add user message
    addMessage(message, 'user');
    state.messageCount++;
    input.value = '';
    
    // Disable input while processing
    input.disabled = true;
    document.querySelector('.btn-send').disabled = true;
    updateConversationStatus('sending');
    
    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                appId: state.currentApp,
                userId: state.currentUserId,
                message: message
            })
        });
        
        const data = await response.json();
        displayRawResponse(data);
        
        if (data.status === 'error') {
            addMessage(`⚠️ Error: ${data.error}`, 'agent');
        } else if (data.status === 'tool_calls' && data.toolCalls && data.toolCalls.length > 0) {
            state.currentTurnId = data.turnId;
            state.activeToolCalls = data.toolCalls;
            state.toolCallCount++;
            
            addMessage('🔧 Tool call detected', 'tool-call');
            
            for (const tool of data.toolCalls) {
                const argsStr = JSON.stringify(tool.args || {}, null, 2);
                addMessage(`<strong>${tool.name}</strong>\n\nInput:\n${argsStr}`, 'tool-call');
            }
            
            addToolExecutionButton();
            updateConversationStatus('waiting_for_tool_execution');
        } else {
            addMessage(data.reply || 'No response', 'agent');
            updateConversationStatus('idle');
            input.disabled = false;
            document.querySelector('.btn-send').disabled = false;
        }
        
        updateDebugInfo();
    } catch (error) {
        addMessage(`❌ Connection error: ${error.message}`, 'agent');
        input.disabled = false;
        document.querySelector('.btn-send').disabled = false;
        updateConversationStatus('error');
    }
}

async function executeTools() {
    if (!state.currentTurnId || state.activeToolCalls.length === 0) {
        addMessage('No active tool calls to execute', 'system');
        return;
    }
    
    const input = document.getElementById('messageInput');
    input.disabled = true;
    document.querySelector('.btn-send').disabled = true;
    updateConversationStatus('executing_tools');
    
    try {
        const response = await fetch('/api/tools', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                appId: state.currentApp,
                userId: state.currentUserId,
                turnId: state.currentTurnId,
                toolResults: [
                    {
                        callId: `call_${Date.now()}`,
                        name: 'mock_result',
                        result: 'Mock tool execution result - Found 3 matching properties'
                    }
                ]
            })
        });
        
        const data = await response.json();
        displayRawResponse(data);
        
        if (data.status === 'error') {
            addMessage(`⚠️ Error: ${data.error}`, 'agent');
        } else if (data.status === 'tool_calls' && data.toolCalls && data.toolCalls.length > 0) {
            state.currentTurnId = data.turnId;
            state.activeToolCalls = data.toolCalls;
            state.toolCallCount++;
            
            addMessage('🔧 More tools to call', 'tool-call');
            for (const tool of data.toolCalls) {
                const argsStr = JSON.stringify(tool.args || {}, null, 2);
                addMessage(`<strong>${tool.name}</strong>\n\nInput:\n${argsStr}`, 'tool-call');
            }
            
            addToolExecutionButton();
            updateConversationStatus('waiting_for_tool_execution');
        } else {
            addMessage(data.reply || 'Tool execution complete', 'agent');
            state.activeToolCalls = [];
            updateConversationStatus('idle');
            input.disabled = false;
            document.querySelector('.btn-send').disabled = false;
        }
        
        updateDebugInfo();
    } catch (error) {
        addMessage(`❌ Connection error: ${error.message}`, 'agent');
        input.disabled = false;
        document.querySelector('.btn-send').disabled = false;
        updateConversationStatus('error');
    }
}

// ==================== MESSAGE MANAGEMENT ====================
function addMessage(text, type) {
    const container = document.getElementById('messagesContainer');
    
    // Remove welcome message if exists
    const welcome = container.querySelector('.welcome-message');
    if (welcome) welcome.remove();
    
    const msg = document.createElement('div');
    msg.className = `message message-${type}`;
    msg.innerHTML = text.replace(/\n/g, '<br>');
    container.appendChild(msg);
    container.scrollTop = container.scrollHeight;
}

function addSystemMessage(text) {
    addMessage(text, 'system');
}

function clearMessages() {
    document.getElementById('messagesContainer').innerHTML = `
        <div class="welcome-message">
            <h3>💬 Ready to chat</h3>
            <p>App registered and ready for messages</p>
        </div>
    `;
    state.messageCount = 0;
    state.toolCallCount = 0;
}

function addToolExecutionButton() {
    const container = document.getElementById('messagesContainer');
    const btn = document.createElement('button');
    btn.className = 'btn btn-send';
    btn.textContent = '⚙️ Execute & Continue';
    btn.onclick = executeTools;
    
    const wrapper = document.createElement('div');
    wrapper.style.display = 'flex';
    wrapper.style.justifyContent = 'center';
    wrapper.style.marginTop = '8px';
    wrapper.appendChild(btn);
    
    container.appendChild(wrapper);
    container.scrollTop = container.scrollHeight;
}

// ==================== UI UPDATES ====================
function showStatus(msg, type = 'info') {
    const status = document.getElementById('regStatus');
    status.textContent = msg;
    status.className = `status-box ${type}`;
}

function enableChatUI() {
    document.getElementById('messageInput').disabled = false;
    document.querySelector('.btn-send').disabled = false;
    document.getElementById('appStatus').textContent = `Connected: ${state.currentApp}`;
    document.getElementById('appStatus').className = 'badge badge-success';
}

function updateConversationStatus(status) {
    const statusMap = {
        'idle': 'Idle',
        'sending': '📤 Sending...',
        'waiting_for_tool_execution': '⏳ Waiting for tool execution',
        'executing_tools': '⚙️ Executing tools...',
        'error': '❌ Error'
    };
    document.getElementById('conversationStatus').textContent = statusMap[status] || status;
}

// ==================== DEBUG INFO ====================
function updateDebugInfo() {
    // Update turn info
    document.getElementById('turnId').textContent = state.currentTurnId ? state.currentTurnId.substring(0, 12) + '...' : '-';
    document.getElementById('currentAppId').textContent = state.currentApp || '-';
    document.getElementById('currentUserId').textContent = state.currentUserId || '-';
    
    // Update state
    if (state.currentState) {
        document.getElementById('currentState').textContent = JSON.stringify(state.currentState, null, 2);
    }
    
    // Update tool calls
    if (state.activeToolCalls.length > 0) {
        const toolInfo = state.activeToolCalls.map(tc => {
            return `• ${tc.name}\n  Input: ${JSON.stringify(tc.args || {})}`;
        }).join('\n\n');
        document.getElementById('toolCallsInfo').textContent = toolInfo;
    } else {
        document.getElementById('toolCallsInfo').innerHTML = '<p class="text-muted">No active tool calls</p>';
    }
    
    // Update stats
    document.getElementById('messageCount').textContent = state.messageCount;
    document.getElementById('toolCallCount').textContent = state.toolCallCount;
}

function displayRawResponse(data) {
    const raw = document.getElementById('rawResponse');
    raw.textContent = JSON.stringify(data, null, 2);
}
