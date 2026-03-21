/* ══════════════════════════════════════════════════════
   UI.JS — DOM Manipulation & Page Transitions
   Codebase Intelligence Agent
══════════════════════════════════════════════════════ */

/**
 * Show a specific page by ID, hiding all others.
 * @param {string} pageId - The ID of the page element to show.
 */
function showPage(pageId) {
  const pages = document.querySelectorAll('.page');
  pages.forEach(page => page.classList.add('hidden'));

  const target = document.getElementById(pageId);
  if (target) {
    target.classList.remove('hidden');
  }

  // Show/hide Ask AI button based on active page
  if (pageId === 'results-page') {
    if (typeof showChatButton === 'function') showChatButton();
  } else {
    if (typeof hideChatButton === 'function') hideChatButton();
  }
}

/**
 * Display a validation error on the input page.
 * @param {string} msg - The error message to display.
 */
function showError(msg) {
  const errorEl = document.getElementById('error-msg');
  const wrapper = document.getElementById('input-wrapper');

  if (errorEl) errorEl.textContent = msg;
  if (wrapper) wrapper.classList.add('error');
}

/**
 * Clear any visible validation error.
 */
function clearError() {
  const errorEl = document.getElementById('error-msg');
  const wrapper = document.getElementById('input-wrapper');

  if (errorEl) errorEl.innerHTML = '&nbsp;';
  if (wrapper) wrapper.classList.remove('error');
}

/**
 * Enter the loading state on the analyze button.
 */
function showLoading() {
  const btn     = document.getElementById('btn-analyze');
  const btnText = document.getElementById('btn-text');
  const spinner = document.getElementById('btn-spinner');

  if (btn)     btn.disabled = true;
  if (btnText) btnText.textContent = 'Analyzing...';
  if (spinner) spinner.classList.remove('hidden');
}

/**
 * Exit the loading state on the analyze button.
 */
function hideLoading() {
  const btn     = document.getElementById('btn-analyze');
  const btnText = document.getElementById('btn-text');
  const spinner = document.getElementById('btn-spinner');

  if (btn)     btn.disabled = false;
  if (btnText) btnText.textContent = 'Analyze Repository →';
  if (spinner) spinner.classList.add('hidden');
}

/**
 * Set the repository display name in the results header.
 * @param {string} name - The "user/repo" string to display.
 */
function setRepoDisplayName(name) {
  const el = document.getElementById('repo-display-name');
  if (el) el.textContent = name;
}

/**
 * Re-trigger card entrance animations by resetting
 * the animation property on each card.
 */
function resetCardAnimations() {
  const cards = document.querySelectorAll('.cards-grid .card');
  cards.forEach(card => {
    card.style.animation = 'none';
    card.offsetHeight;            // force reflow
    card.style.animation = '';
  });
}

window.showPage            = showPage;
window.showError           = showError;
window.clearError          = clearError;
window.showLoading         = showLoading;
window.hideLoading         = hideLoading;
window.setRepoDisplayName  = setRepoDisplayName;
window.resetCardAnimations = resetCardAnimations;

function showDiagramPage() {
  const repoName = document.getElementById('repo-display-name').textContent;
  document.getElementById('diagram-repo-name').textContent = repoName;
  showPage('diagram-page');
  if (window._lastApiResponse) {
    renderDependencyGraph(window._lastApiResponse.m3_nodes, window._lastApiResponse.m3_edges);
  }
}

window.showDiagramPage = showDiagramPage;

function showM1Page() {
  const repoName = document.getElementById('repo-display-name').textContent;
  document.getElementById('m1-repo-name').textContent = repoName;
  showPage('m1-page');
  if (window._lastApiResponse) {
    renderM1Full(window._lastApiResponse.m1_folder_explanation);
  }
}

function showM2Page() {
  const repoName = document.getElementById('repo-display-name').textContent;
  document.getElementById('m2-repo-name').textContent = repoName;
  document.getElementById('m2-entry-label').textContent =
    'Entry: ' + (window._lastApiResponse?.m2_entry_analysis?.entry_file || '—');
  showPage('m2-page');
  if (window._lastApiResponse) {
    renderM2Full(window._lastApiResponse.m2_entry_analysis);
  }
}

window.showM1Page = showM1Page;
window.showM2Page = showM2Page;
