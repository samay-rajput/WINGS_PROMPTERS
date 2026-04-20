/* CHAT.JS - AI Chat Logic (Mock and API modes) */
const RAG_API_BASES = buildRagApiBaseCandidates(window.__RAG_API_BASE__ || window.__API_BASE__, [
  'http://127.0.0.1:8000',
  'http://localhost:8000',
  'http://localhost:5000',
  'http://127.0.0.1:5000'
]);

let currentMode = 'B3';
let ragReady = false;

function buildRagApiBaseCandidates(primary, fallbacks) {
  const unique = [];
  const add = (value) => {
    if (!value) return;
    const normalized = String(value).trim().replace(/\/+$/, '');
    if (normalized && !unique.includes(normalized)) unique.push(normalized);
  };

  add(primary);
  fallbacks.forEach(add);
  return unique;
}

async function fetchRagWithFallback(path, options) {
  let lastErr = null;

  for (const base of RAG_API_BASES) {
    try {
      const res = await fetch(base + path, options);
      if (res.status === 404) continue;
      return { res, base };
    } catch (err) {
      lastErr = err;
    }
  }

  if (lastErr) throw lastErr;
  throw new Error('Failed to fetch');
}

// DOM REFERENCES
const chatFab = document.getElementById('chat-fab');
const chatOverlay = document.getElementById('chat-overlay');
const chatPanel = document.getElementById('chat-panel');
const chatCloseBtn = document.getElementById('chat-close-btn');
const chatMessages = document.getElementById('chat-messages');
const chatInput = document.getElementById('chat-input');
const chatSendBtn = document.getElementById('chat-send-btn');
const chatEmpty = document.getElementById('chat-empty');

let firstMessageSent = false;

function initModeButtons() {
  const modeBtns = document.querySelectorAll('.chat-mode-btn');
  modeBtns.forEach((btn) => {
    btn.addEventListener('click', () => {
      modeBtns.forEach((b) => b.classList.remove('active'));
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
  if (chatEmpty) chatEmpty.style.display = '';
}
window.resetRagState = resetRagState;

// OPEN / CLOSE PANEL
function openChatPanel() {
  if (chatInput) chatInput.disabled = !ragReady;
  if (chatSendBtn) chatSendBtn.disabled = !ragReady;
  if (chatPanel) chatPanel.classList.add('open');
  if (chatOverlay) chatOverlay.classList.add('open');
  if (chatInput) chatInput.focus();
}

function closeChatPanel() {
  if (chatPanel) chatPanel.classList.remove('open');
  if (chatOverlay) chatOverlay.classList.remove('open');
}

if (chatFab) chatFab.addEventListener('click', openChatPanel);
if (chatCloseBtn) chatCloseBtn.addEventListener('click', closeChatPanel);
if (chatOverlay) chatOverlay.addEventListener('click', closeChatPanel);

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && chatPanel && chatPanel.classList.contains('open')) {
    closeChatPanel();
  }
});

// SEND MESSAGE
function sendMessage() {
  if (!chatInput) return;

  const text = chatInput.value.trim();
  if (!text) return;

  if (!firstMessageSent) {
    firstMessageSent = true;
    if (chatEmpty) chatEmpty.style.display = 'none';
  }

  appendMessage('user', text);
  chatInput.value = '';

  const aiMessage = createMessageShell('ai');
  aiMessage.bubble.classList.add('is-streaming');
  aiMessage.bubble.textContent = 'Thinking...';

  fetchAIReply(text)
    .then(async (result) => {
      const answer = result.answer || 'No answer returned.';
      await streamWordsIntoBubble(aiMessage.bubble, answer);
      aiMessage.bubble.classList.remove('is-streaming');
      aiMessage.bubble.classList.add('ai-formatted');
      aiMessage.bubble.innerHTML = formatAiOutput(answer);
      appendSources(aiMessage.wrapper, result.sources || []);
    })
    .catch((err) => {
      aiMessage.bubble.classList.remove('is-streaming');
      aiMessage.bubble.classList.add('ai-formatted');
      const msg = err && err.message ? err.message : 'Could not connect to AI. Please try again.';
      aiMessage.bubble.innerHTML = formatAiOutput(msg);
    });
}

if (chatSendBtn) chatSendBtn.addEventListener('click', sendMessage);
if (chatInput) {
  chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') sendMessage();
  });
}

// RENDER MESSAGES
function createMessageShell(role) {
  const wrapper = document.createElement('div');
  wrapper.className = `chat-msg ${role}`;

  const label = document.createElement('span');
  label.className = 'chat-msg-label';
  label.textContent = role === 'user' ? 'You' : 'AI';

  const bubble = document.createElement('div');
  bubble.className = 'chat-msg-bubble';

  wrapper.appendChild(label);
  wrapper.appendChild(bubble);

  if (chatMessages) chatMessages.appendChild(wrapper);
  scrollChatToBottom();

  return { wrapper, bubble };
}

function appendMessage(role, text, sources = []) {
  const msg = createMessageShell(role);

  if (role === 'ai') {
    msg.bubble.classList.add('ai-formatted');
    msg.bubble.innerHTML = formatAiOutput(text || 'No answer returned.');
  } else {
    msg.bubble.textContent = text;
  }

  if (role === 'ai' && sources && sources.length > 0) {
    appendSources(msg.wrapper, sources);
  }
}

function appendSources(wrapper, sources) {
  if (!wrapper || !sources || !sources.length) return;

  const sourcesEl = document.createElement('div');
  sourcesEl.className = 'chat-sources';

  const sourcesLabel = document.createElement('span');
  sourcesLabel.className = 'chat-sources-label';
  sourcesLabel.textContent = 'Sources:';
  sourcesEl.appendChild(sourcesLabel);

  sources.forEach((src) => {
    const badge = document.createElement('span');
    badge.className = 'chat-source-badge';
    badge.textContent = src.split('/').pop();
    badge.title = src;
    sourcesEl.appendChild(badge);
  });

  wrapper.appendChild(sourcesEl);
}

function scrollChatToBottom() {
  if (chatMessages) chatMessages.scrollTop = chatMessages.scrollHeight;
}

// STREAM + FORMAT
async function streamWordsIntoBubble(bubble, fullText) {
  const source = String(fullText || '').trim();
  if (!source) {
    bubble.textContent = '';
    return;
  }

  const chunks = source.match(/\S+\s*/g) || [source];
  const targetDurationMs = 2100;
  const baseDelayMs = Math.max(10, Math.min(30, Math.floor(targetDurationMs / chunks.length)));

  let acc = '';
  for (let i = 0; i < chunks.length; i += 1) {
    acc += chunks[i];
    bubble.textContent = acc;

    const chunk = chunks[i];
    const hasPausePunctuation = /[.!?:]\s*$/.test(chunk);
    const delay = hasPausePunctuation ? baseDelayMs + 35 : baseDelayMs;
    await sleep(delay);
  }
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function formatAiOutput(text) {
  const raw = String(text || '').replace(/\r\n/g, '\n').trim();
  if (!raw) return '<p>No answer returned.</p>';

  const codeBlocks = [];
  const withPlaceholders = raw.replace(/```([\s\S]*?)```/g, (_, block) => {
    const idx = codeBlocks.push(block) - 1;
    return `@@CODE_BLOCK_${idx}@@`;
  });

  const escaped = escapeHtml(withPlaceholders);
  const blocks = escaped.split(/\n{2,}/).map((b) => b.trim()).filter(Boolean);

  let html = blocks.map((block) => renderFormattedBlock(block)).join('');

  html = html.replace(/@@CODE_BLOCK_(\d+)@@/g, (_, indexText) => {
    const index = Number(indexText);
    const rendered = renderCodeBlock(codeBlocks[index] || '');
    return rendered;
  });

  return html;
}

function renderFormattedBlock(block) {
  if (!block) return '';
  if (/^@@CODE_BLOCK_\d+@@$/.test(block)) return block;

  const lines = block.split('\n').map((line) => line.trim()).filter(Boolean);

  if (lines.length && lines.every((line) => /^[-*]\s+/.test(line))) {
    const items = lines
      .map((line) => line.replace(/^[-*]\s+/, ''))
      .map((line) => `<li>${applyInlineFormat(line)}</li>`)
      .join('');
    return `<ul>${items}</ul>`;
  }

  if (lines.length && lines.every((line) => /^\d+\.\s+/.test(line))) {
    const items = lines
      .map((line) => line.replace(/^\d+\.\s+/, ''))
      .map((line) => `<li>${applyInlineFormat(line)}</li>`)
      .join('');
    return `<ol>${items}</ol>`;
  }

  if (lines.length === 1 && /^#{1,4}\s+/.test(lines[0])) {
    const title = lines[0].replace(/^#{1,4}\s+/, '');
    return `<h4>${applyInlineFormat(title)}</h4>`;
  }

  const paragraph = applyInlineFormat(block).replace(/\n/g, '<br/>');
  return `<p>${paragraph}</p>`;
}

function applyInlineFormat(text) {
  let out = String(text || '');
  out = out.replace(/`([^`]+)`/g, '<code>$1</code>');
  out = out.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  out = out.replace(/\*([^*]+)\*/g, '<em>$1</em>');
  return out;
}

function renderCodeBlock(rawBlock) {
  const clean = String(rawBlock || '').replace(/^\n+|\n+$/g, '');
  const lines = clean.split('\n');

  let lang = '';
  let code = clean;

  if (lines.length > 1 && /^[a-zA-Z0-9_+.-]+$/.test(lines[0].trim())) {
    lang = lines[0].trim();
    code = lines.slice(1).join('\n');
  }

  const codeEscaped = escapeHtml(code);
  const langAttr = lang ? ` data-lang="${escapeHtml(lang)}"` : '';
  return `<pre><code${langAttr}>${codeEscaped}</code></pre>`;
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

async function fetchAIReply(message) {
  const { res, base } = await fetchRagWithFallback('/rag/chat', {
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
  console.log('[NAVIgit] /rag/chat success from', base);

  return {
    answer: data.answer || 'No answer returned.',
    sources: data.sources || []
  };
}

// SHOW / HIDE FAB
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
