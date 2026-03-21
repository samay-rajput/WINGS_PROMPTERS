/* ══════════════════════════════════════════════════════
   CHAT.JS — AI Chat Logic (Mock & API modes)
   Codebase Intelligence Agent
══════════════════════════════════════════════════════ */
const RAG_API_BASE = window.__RAG_API_BASE__ || 'http://localhost:5000';
let currentMode = 'B3';
let ragReady = false;

// ── DOM REFERENCES ──────────────────────────────────
const chatFab       = document.getElementById('chat-fab');
const chatOverlay   = document.getElementById('chat-overlay');
const chatPanel     = document.getElementById('chat-panel');
const chatCloseBtn  = document.getElementById('chat-close-btn');
const chatMessages  = document.getElementById('chat-messages');
const chatInput     = document.getElementById('chat-input');
const chatSendBtn   = document.getElementById('chat-send-btn');
const chatModeSelector = document.getElementById('chat-mode-selector');
const chatEmpty     = document.getElementById('chat-empty');

let firstMessageSent = false;

function initModeButtons() {
  const modeBtns = document.querySelectorAll('.chat-mode-btn');
  modeBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      modeBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentMode = btn.dataset.mode;
    });
  });
}

function onRagIndexReady() {
  ragReady = true;
  const statusEl = document.getElementById('rag-index-status');
  const statusText = document.getElementById('rag-status-text');
  if (statusEl) statusEl.classList.add('ready');
  if (statusText) statusText.textContent = 'Repository indexed. AI chat ready.';
  if (chatInput) chatInput.disabled = false;
  if (chatSendBtn) chatSendBtn.disabled = false;
  setTimeout(() => {
    if (statusEl) statusEl.classList.add('hidden');
  }, 3000);
}
window.onRagIndexReady = onRagIndexReady;

function resetRagState() {
  ragReady = false;
  const statusEl = document.getElementById('rag-index-status');
  const statusText = document.getElementById('rag-status-text');
  if (statusEl) statusEl.classList.remove('ready', 'hidden');
  if (statusText) statusText.textContent = 'Indexing repository for AI chat...';
  if (chatInput) chatInput.disabled = true;
  if (chatSendBtn) chatSendBtn.disabled = true;
  firstMessageSent = false;
  if (chatMessages) chatMessages.innerHTML = '';
  const emptyEl = document.getElementById('chat-empty');
  if (emptyEl) emptyEl.style.display = '';
}
window.resetRagState = resetRagState;

// ── OPEN / CLOSE PANEL ──────────────────────────────
function openChatPanel() {
  if (chatInput) chatInput.disabled = !ragReady;
  if (chatSendBtn) chatSendBtn.disabled = !ragReady;
  chatPanel.classList.add('open');
  chatOverlay.classList.add('open');
  chatInput.focus();
}

function closeChatPanel() {
  chatPanel.classList.remove('open');
  chatOverlay.classList.remove('open');
}

chatFab.addEventListener('click', openChatPanel);
chatCloseBtn.addEventListener('click', closeChatPanel);
chatOverlay.addEventListener('click', closeChatPanel);

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && chatPanel.classList.contains('open')) {
    closeChatPanel();
  }
});

// ── SEND MESSAGE ────────────────────────────────────
function sendMessage() {
  const text = chatInput.value.trim();
  if (!text) return;

  // Hide empty state on first message
  if (!firstMessageSent) {
    firstMessageSent = true;
    if (chatEmpty) chatEmpty.style.display = 'none';
  }

  appendMessage('user', text);
  chatInput.value = '';

  const typingEl = showTypingIndicator();
  fetchAIReply(text)
    .then(result => {
      removeTypingIndicator(typingEl);
      appendMessage('ai', result.answer, result.sources);
    })
    .catch(err => {
      removeTypingIndicator(typingEl);
      appendMessage('ai', err.message || 'Could not connect to AI. Please try again.', []);
    });
}
chatSendBtn.addEventListener('click', sendMessage);
chatInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') sendMessage();
});

// ── RENDER MESSAGES ─────────────────────────────────
function appendMessage(role, text, sources = []) {
  const wrapper = document.createElement('div');
  wrapper.className = `chat-msg ${role}`;

  const label = document.createElement('span');
  label.className = 'chat-msg-label';
  label.textContent = role === 'user' ? 'You' : 'AI';

  const bubble = document.createElement('div');
  bubble.className = 'chat-msg-bubble';
  bubble.textContent = text;

  wrapper.appendChild(label);
  wrapper.appendChild(bubble);

  if (role === 'ai' && sources && sources.length > 0) {
    const sourcesEl = document.createElement('div');
    sourcesEl.className = 'chat-sources';

    const sourcesLabel = document.createElement('span');
    sourcesLabel.className = 'chat-sources-label';
    sourcesLabel.textContent = 'Sources:';
    sourcesEl.appendChild(sourcesLabel);

    sources.forEach(src => {
      const badge = document.createElement('span');
      badge.className = 'chat-source-badge';
      badge.textContent = src.split('/').pop();
      badge.title = src;
      sourcesEl.appendChild(badge);
    });

    wrapper.appendChild(sourcesEl);
  }

  chatMessages.appendChild(wrapper);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

// ── TYPING INDICATOR ────────────────────────────────
function showTypingIndicator() {
  const wrapper = document.createElement('div');
  wrapper.className = 'chat-msg ai';

  const label = document.createElement('span');
  label.className = 'chat-msg-label';
  label.textContent = 'AI';

  const dots = document.createElement('div');
  dots.className = 'typing-dots';
  dots.innerHTML = '<span></span><span></span><span></span>';

  wrapper.appendChild(label);
  wrapper.appendChild(dots);
  chatMessages.appendChild(wrapper);
  chatMessages.scrollTop = chatMessages.scrollHeight;

  return wrapper;
}

function removeTypingIndicator(el) {
  if (el && el.parentNode) el.parentNode.removeChild(el);
}

async function fetchAIReply(message) {
  const res = await fetch(RAG_API_BASE + '/rag/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      question: message,
      mode: currentMode
    })
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || 'Chat request failed.');
  }
  const data = await res.json();
  return {
    answer: data.answer || 'No answer returned.',
    sources: data.sources || []
  };
}

// ── SHOW / HIDE FAB ─────────────────────────────────
function showChatButton() {
  if (!window._ragIndexReady && !ragReady) {
    resetRagState();
  }
  if (chatFab) chatFab.classList.add('visible');
}

function hideChatButton() {
  if (chatFab) chatFab.classList.remove('visible');
  closeChatPanel();
}

initModeButtons();



