let currentSessionId = null;
let websocket = null;

// Initialize the app
document.addEventListener('DOMContentLoaded', function() {
    loadSessions();

    document.getElementById('new-session-btn').addEventListener('click', createNewSession);
    document.getElementById('send-button').addEventListener('click', sendMessage);
    document.getElementById('message-input').addEventListener('keypress', handleKeyPress);
    const delBtn = document.getElementById('delete-session-btn');
    if (delBtn) delBtn.addEventListener('click', deleteCurrentSession);

    // Tabs
    const tabAssistant = document.getElementById('tab-assistant');
    const tabConfig = document.getElementById('tab-config');
    if (tabAssistant && tabConfig) {
        tabAssistant.addEventListener('click', () => switchTab('assistant'));
        tabConfig.addEventListener('click', () => switchTab('config'));
        // Default active
        setActiveTabButton('assistant');
    }

    // Config save
    const saveBtn = document.getElementById('config-save');
    if (saveBtn) saveBtn.addEventListener('click', saveConfig);
});

async function loadSessions() {
    try {
        const response = await fetch('/api/sessions');
        const sessions = await response.json();
        
        const sessionsList = document.getElementById('sessions-list');
        sessionsList.innerHTML = '';
        
        sessions.forEach(session => {
            const sessionDiv = document.createElement('div');
            sessionDiv.className = 'task';
            sessionDiv.innerHTML = `📄 ${session.title}`;
            sessionDiv.onclick = (event) => selectSession(session.id, session.title, event.currentTarget);
            sessionsList.appendChild(sessionDiv);
        });

        // Auto-select first session if none selected
        if (!currentSessionId && sessions.length > 0) {
            const first = sessions[0];
            const firstEl = sessionsList.firstElementChild;
            await selectSession(first.id, first.title, firstEl);
        }
    } catch (error) {
        console.error('Error loading sessions:', error);
    }
}

function switchTab(tab) {
    const assistantView = document.getElementById('tab-assistant-view');
    const configView = document.getElementById('tab-config-view');
    if (!assistantView || !configView) return;
    if (tab === 'assistant') {
        assistantView.style.display = 'flex';
        configView.style.display = 'none';
        // Restore scroll after layout change
        setTimeout(scrollMessagesToBottom, 0);
    } else {
        assistantView.style.display = 'none';
        configView.style.display = 'block';
    }
    setActiveTabButton(tab);
}

function scrollMessagesToBottom() {
    const messagesDiv = document.getElementById('messages');
    if (messagesDiv) {
        messagesDiv.scrollTop = messagesDiv.scrollHeight;
    }
}

function setActiveTabButton(tab) {
    const a = document.getElementById('tab-assistant');
    const c = document.getElementById('tab-config');
    if (a) a.classList.toggle('primary', tab === 'assistant');
    if (c) c.classList.toggle('primary', tab === 'config');
}

async function loadConfig() {
    if (!currentSessionId) return;
    try {
        const resp = await fetch(`/api/sessions/${currentSessionId}/config`);
        if (!resp.ok) throw new Error('Failed to load config');
        const cfg = await resp.json();
        const modelEl = document.getElementById('config-model');
        const toolVerEl = document.getElementById('config-tool-version');
        const maxTokEl = document.getElementById('config-max-tokens');
        const suffixEl = document.getElementById('config-system-suffix');
        if (modelEl) modelEl.value = cfg.model || '';
        if (toolVerEl) toolVerEl.value = cfg.tool_version || '';
        if (maxTokEl) maxTokEl.value = cfg.max_tokens ?? 4096;
        if (suffixEl) suffixEl.value = cfg.system_prompt_suffix || '';
    } catch (e) {
        console.error('Error loading config:', e);
    }
}

async function saveConfig() {
    if (!currentSessionId) return;
    try {
        const model = document.getElementById('config-model').value.trim();
        const tool_version = document.getElementById('config-tool-version').value.trim();
        const max_tokens = parseInt(document.getElementById('config-max-tokens').value, 10) || 4096;
        const system_prompt_suffix = document.getElementById('config-system-suffix').value;
        const payload = { model, tool_version, max_tokens, system_prompt_suffix };
        const resp = await fetch(`/api/sessions/${currentSessionId}/config`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (!resp.ok) throw new Error('Save failed');
        // Feedback
        const messagesDiv = document.getElementById('messages');
        if (messagesDiv) {
            const note = document.createElement('div');
            note.className = 'bubble agent-activity';
            note.textContent = 'Configuration saved.';
            messagesDiv.appendChild(note);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }
    } catch (e) {
        console.error('Error saving config:', e);
        alert('Failed to save config');
    }
}

async function createNewSession() {
    const title = prompt('Enter session title:');
    if (!title) return;

    try {
        const response = await fetch('/api/sessions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: title })
        });
        
        const session = await response.json();
        loadSessions();
        selectSession(session.id, session.title);
    } catch (error) {
        console.error('Error creating session:', error);
    }
}

async function selectSession(sessionId, title, targetElement) {
    currentSessionId = sessionId;
    document.getElementById('session-title').textContent = title;

    // Update active session styling
    document.querySelectorAll('.task').forEach(item => {
        item.style.background = '#fff'; // Reset background
    });
    if (targetElement) {
        targetElement.style.background = 'var(--muted)'; // Highlight selected
    }

    // Load messages and config
    await loadMessages();
    await loadConfig();

    // Setup WebSocket connection
    setupWebSocket();
}

async function deleteCurrentSession() {
    if (!currentSessionId) return;
    if (!confirm('Delete this session and all its messages?')) return;
    try {
        const resp = await fetch(`/api/sessions/${currentSessionId}`, { method: 'DELETE' });
        if (!resp.ok) throw new Error('Delete failed');
        currentSessionId = null;
        // Clear UI
        const messagesDiv = document.getElementById('messages');
        if (messagesDiv) messagesDiv.innerHTML = '';
        const title = document.getElementById('session-title');
        if (title) title.textContent = 'Legent AI';
        // Reload sessions list
        await loadSessions();
    } catch (e) {
        console.error('Error deleting session:', e);
        alert('Failed to delete session');
    }
}

async function loadMessages() {
    if (!currentSessionId) return;

    try {
        const response = await fetch(`/api/sessions/${currentSessionId}/messages`);
        const messages = await response.json();
        
        const messagesDiv = document.getElementById('messages');
        messagesDiv.innerHTML = '';
        
        messages.forEach(message => {
            const isUser = message.message_type === 'user';
            const raw = (message.content || '').trim();
            if (message.message_type === 'tool_result') {
                // Try to parse tool_result JSON to render screenshots
                try {
                    const payload = JSON.parse(raw || '{}');
                    if (payload && payload.image_url) {
                        const bubble = document.createElement('div');
                        bubble.className = 'bubble';
                        const img = document.createElement('img');
                        img.src = payload.image_url;
                        img.alt = 'Screenshot';
                        img.style.maxWidth = '100%';
                        img.style.borderRadius = '8px';
                        bubble.appendChild(img);
                        if (payload.output) {
                            const caption = document.createElement('div');
                            caption.style.marginTop = '6px';
                            caption.textContent = String(payload.output).slice(0, 500);
                            bubble.appendChild(caption);
                        }
                        messagesDiv.appendChild(bubble);
                        return;
                    }
                } catch (e) {
                    // fall through to default rendering
                }
            }
            const content = raw;
            if (!isUser && !content) return; // skip empty assistant bubbles
            const messageDiv = document.createElement('div');
            messageDiv.className = isUser ? 'bubble me' : 'bubble';
            messageDiv.textContent = content;
            messagesDiv.appendChild(messageDiv);
        });
        
        messagesDiv.scrollTop = messagesDiv.scrollHeight;
    } catch (error) {
        console.error('Error loading messages:', error);
    }
}

function setupWebSocket() {
    if (websocket) {
        websocket.close();
    }

    const wsScheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const wsUrl = `${wsScheme}://${window.location.host}/ws/${currentSessionId}`;
    websocket = new WebSocket(wsUrl);
    
    websocket.onmessage = function(event) {
        try {
            const data = JSON.parse(event.data);
        
            if (data.type === 'progress') {
                // Fully ignore progress events (no logs, no UI)
                return;
            } else if (data.type === 'message') {
                loadMessages(); // Reload messages on new message
            } else {
                // On any agent event (agent_block, agent_tool_result, screenshots), just reload messages
                loadMessages();
            }
        } catch (e) {
            console.error('WS parse error:', e);
        }
    };
    
    websocket.onerror = function(error) {
        console.error('WebSocket error:', error);
    };
}

async function sendMessage() {
    const input = document.getElementById('message-input');
    const message = input.value.trim();
    if (!message) return;
    if (!currentSessionId) {
        alert('Please select or create a session first.');
        return;
    }
    
    input.value = '';
    
    try {
        const response = await fetch('/api/tasks/execute', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: currentSessionId,
                task_description: message
            })
        });
        
        const result = await response.json();
        // Immediately show the user's message in the UI; all agent activity will appear as assistant messages
        await loadMessages();
    } catch (error) {
        console.error('Error sending message:', error);
    }
}

function handleKeyPress(event) {
    if (event.key === 'Enter') {
        sendMessage();
    }
}

function showProgress() { /* no-op: progress will be rendered as chat messages */ }

function hideProgress() { /* no-op */ }

function updateProgress(progressData) { /* no-op: progress UI removed */ }

function displayAgentActivity(data) { /* no-op: agent activity rendered via persisted messages */ }
