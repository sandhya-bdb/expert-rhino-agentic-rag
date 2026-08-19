// Session & Config
const sessionId = 'session_' + Math.random().toString(36).substring(2, 11);

// DOM Elements
const chatForm = document.getElementById('chat-form');
const chatInput = document.getElementById('chat-input');
const chatHistory = document.getElementById('chat-history');
const dbPointsCount = document.getElementById('db-points-count');
const dbStatusText = document.getElementById('db-status');
const ingestForm = document.getElementById('ingest-form');
const ingestUrlInput = document.getElementById('ingest-url');
const ingestLogBox = document.getElementById('ingest-log-box');
const ingestLogText = document.getElementById('ingest-log-text');
const ingestSubmitBtn = document.getElementById('ingest-submit-btn');

// Init
document.addEventListener('DOMContentLoaded', () => {
    fetchStats();
    setupEventListeners();
    chatInput.focus();
});

// Event Listeners
function setupEventListeners() {
    // Chat submit
    chatForm.addEventListener('submit', (e) => {
        e.preventDefault();
        sendMessage();
    });

    // Auto-resize chat textarea
    chatInput.addEventListener('input', () => {
        chatInput.style.height = 'auto';
        chatInput.style.height = (chatInput.scrollHeight - 4) + 'px';
    });

    // Handle Enter to submit (Shift+Enter for newline)
    chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            chatForm.dispatchEvent(new Event('submit'));
        }
    });

    // Suggestion buttons
    document.querySelectorAll('.suggestion-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const query = btn.getAttribute('data-query');
            chatInput.value = query;
            chatInput.style.height = 'auto';
            chatForm.dispatchEvent(new Event('submit'));
        });
    });

    // Ingest submit
    ingestForm.addEventListener('submit', (e) => {
        e.preventDefault();
        ingestUrl();
    });
}

// Fetch Database Stats
async function fetchStats() {
    try {
        const res = await fetch('/api/stats');
        if (res.ok) {
            const data = await res.json();
            dbPointsCount.textContent = data.points_count;
            dbStatusText.textContent = data.status;
            dbStatusText.style.color = '#2ec4b6';
        } else {
            dbStatusText.textContent = 'Error';
            dbStatusText.style.color = '#ff3366';
        }
    } catch (err) {
        console.error('Failed to fetch stats:', err);
        dbStatusText.textContent = 'Offline';
        dbStatusText.style.color = '#ff3366';
        dbPointsCount.textContent = '0';
    }
}

// Ingest custom URL
async function ingestUrl() {
    const url = ingestUrlInput.value.trim();
    if (!url) return;

    // Show log box & status
    ingestLogBox.classList.remove('hidden');
    ingestLogText.textContent = 'Initializing ingester agent...\nConnecting to fetch & vector store MCP services...';
    ingestSubmitBtn.disabled = true;
    ingestSubmitBtn.textContent = 'Ingesting...';

    // Show busy state on indicator
    const indicator = document.querySelector('.indicator-dot');
    indicator.className = 'indicator-dot busy';
    document.querySelector('.indicator-text').textContent = 'Agent Busy Ingesting';

    try {
        // We will call the backend API
        ingestLogText.textContent += `\nCrawl initiated for: ${url}\nRunning OpenAI Ingester Agent...`;
        
        const response = await fetch('/api/ingest', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url })
        });

        const data = await response.json();
        
        if (response.ok) {
            ingestLogText.textContent += `\nSuccess: ${data.message}`;
            ingestUrlInput.value = '';
            // Refresh stats
            fetchStats();
        } else {
            ingestLogText.textContent += `\nError: ${data.detail || 'Failed to ingest URL.'}`;
        }
    } catch (err) {
        ingestLogText.textContent += `\nConnection failed: ${err.message}`;
    } finally {
        ingestSubmitBtn.disabled = false;
        ingestSubmitBtn.textContent = 'Ingest & Memorize';
        
        // Reset indicator
        indicator.className = 'indicator-dot connected';
        document.querySelector('.indicator-text').textContent = 'Agent System Active';
    }
}

// Send chat message
async function sendMessage() {
    const message = chatInput.value.trim();
    if (!message) return;

    // Add User Bubble
    appendMessage(message, 'user');
    chatInput.value = '';
    chatInput.style.height = 'auto';

    // Scroll to bottom
    scrollToBottom();

    // Show typing bubble
    const typingBubble = showTypingIndicator();
    scrollToBottom();

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message, session_id: sessionId })
        });

        const data = await response.json();
        typingBubble.remove();

        if (response.ok) {
            appendMessage(data.output, 'assistant');
        } else {
            appendMessage(`System Error: ${data.detail || 'Failed to get response.'}`, 'assistant');
        }
    } catch (err) {
        typingBubble.remove();
        appendMessage(`Connection failed: ${err.message}`, 'assistant');
    }

    scrollToBottom();
    chatInput.focus();
}

// Append Chat Bubble
function appendMessage(text, role) {
    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${role}-message`;
    
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    
    if (role === 'assistant') {
        contentDiv.innerHTML = parseMarkdown(text);
    } else {
        const p = document.createElement('p');
        p.textContent = text;
        contentDiv.appendChild(p);
    }
    
    msgDiv.appendChild(contentDiv);
    chatHistory.appendChild(msgDiv);
}

// Show Typing Indicator
function showTypingIndicator() {
    const typingDiv = document.createElement('div');
    typingDiv.className = 'typing-bubble';
    
    for (let i = 0; i < 3; i++) {
        const dot = document.createElement('div');
        dot.className = 'typing-dot';
        typingDiv.appendChild(dot);
    }
    
    chatHistory.appendChild(typingDiv);
    return typingDiv;
}

// Auto scroll chat
function scrollToBottom() {
    chatHistory.scrollTop = chatHistory.scrollHeight;
}

// Simple Markdown Parser (RegEx)
function parseMarkdown(text) {
    let html = text;
    
    // Escape HTML to prevent XSS (except for safe characters)
    html = html.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    
    // Bold: **text**
    html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    
    // Italic: *text*
    html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');
    
    // Inline code: `code`
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    
    // Headers: ### text -> <h3>text</h3>
    html = html.replace(/^###\s+(.+)$/gm, '<h3>$1</h3>');
    html = html.replace(/^##\s+(.+)$/gm, '<h2>$1</h2>');
    html = html.replace(/^#\s+(.+)$/gm, '<h1>$1</h1>');

    // Bullet points: - text or * text
    html = html.replace(/^\s*[-*]\s+(.+)$/gm, '<li>$1</li>');
    // Wrap lists (rough check, works well enough for standard outputs)
    html = html.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');
    
    // Paragraph double newlines
    html = html.replace(/\n\n/g, '</p><p>');
    
    // Single newlines within paragraphs
    html = html.replace(/\n/g, '<br>');

    // Wrap with paragraph tags if not starting with block element
    if (!html.startsWith('<p>') && !html.startsWith('<h3>') && !html.startsWith('<h2>') && !html.startsWith('<ul>')) {
        html = '<p>' + html + '</p>';
    }
    
    // Fix empty paragraph tags
    html = html.replace(/<p><\/p>/g, '');
    
    // Parse links: [text](url) -> <a href="url" target="_blank">text</a>
    html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');

    return html;
}
