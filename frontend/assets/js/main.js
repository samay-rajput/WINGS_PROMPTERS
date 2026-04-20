/* MAIN.JS - App Entry & Page Routing */
const MOCK_API = false;

const ANALYZE_API_BASES = buildApiBaseCandidates(window.__API_BASE__, [
  'http://127.0.0.1:8000',
  'http://localhost:8000',
  'http://localhost:5000',
  'http://127.0.0.1:5000'
]);

function buildApiBaseCandidates(primary, fallbacks) {
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

async function fetchWithFallback(path, options) {
  let lastErr = null;

  for (const base of ANALYZE_API_BASES) {
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

document.addEventListener('DOMContentLoaded', () => {
  const repoUrlInput = document.getElementById('repo-url');
  const btnAnalyze = document.getElementById('btn-analyze');
  const btnNewAnalysis = document.getElementById('btn-new-analysis');

  if (!repoUrlInput || !btnAnalyze) {
    console.error('[NAVIgit] Missing required input/analyze elements');
    return;
  }

  showPage('input-page');

  repoUrlInput.addEventListener('input', () => clearError());
  btnAnalyze.addEventListener('click', handleAnalyze);

  repoUrlInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') handleAnalyze();
  });

  if (btnNewAnalysis) {
    btnNewAnalysis.addEventListener('click', () => {
      showPage('input-page');
      repoUrlInput.value = '';
      clearError();
      repoUrlInput.focus();
    });
  }

  const m1Card = document.getElementById('card-m1-clickable');
  if (m1Card) m1Card.addEventListener('click', () => {
    if (typeof showM1Page === 'function') showM1Page();
  });

  const m2Card = document.getElementById('card-m2-clickable');
  if (m2Card) m2Card.addEventListener('click', () => {
    if (typeof showM2Page === 'function') showM2Page();
  });

  const m3Card = document.getElementById('card-m3-clickable');
  if (m3Card) m3Card.addEventListener('click', () => {
    if (typeof showDiagramPage === 'function') showDiagramPage();
  });

  const btnBack = document.getElementById('btn-back-to-results');
  if (btnBack) btnBack.addEventListener('click', () => showPage('results-page'));

  const btnBackM1 = document.getElementById('btn-back-from-m1');
  if (btnBackM1) btnBackM1.addEventListener('click', () => showPage('results-page'));

  const btnBackM2 = document.getElementById('btn-back-from-m2');
  if (btnBackM2) btnBackM2.addEventListener('click', () => showPage('results-page'));

  async function handleAnalyze() {
    clearError();

    const result = isValidGitHubUrl(repoUrlInput.value);
    if (!result.valid) {
      showError(result.msg);
      return;
    }

    const githubUrl = repoUrlInput.value.trim();

    showLoading();
    showSkeletons();
    showPage('results-page');
    setRepoDisplayName(result.name);
    resetCardAnimations();

    // Fire both pipelines simultaneously.
    if (typeof resetRagState === 'function') resetRagState();
    triggerRagIndex(githubUrl);

    let analysisOk = false;

    try {
      const { res, base } = await fetchWithFallback('/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ github_url: githubUrl })
      });

      let data = null;
      try { data = await res.json(); } catch (_) { data = null; }

      if (!res.ok) {
        const msg = (data && data.error) ? data.error : 'Server error (' + res.status + ')';
        throw new Error('HTTP_ERROR: ' + msg);
      }

      if (typeof renderAll !== 'function') {
        throw new Error('HTTP_ERROR: renderAll() not found - check results.js');
      }

      analysisOk = true;
      hideLoading();
      console.log('[NAVIgit] /analyze success from', base, 'Raw data:', data);

      try {
        renderAll(data);
      } catch (renderErr) {
        console.error('[NAVIgit] renderAll threw:', renderErr);
      }

    } catch (err) {
      console.error('[NAVIgit] /analyze failed:', err);
      hideLoading();

      if (!analysisOk) {
        showPage('input-page');
        const msg = err && err.message ? String(err.message).replace('HTTP_ERROR: ', '') : '';
        showError(
          msg.includes('Failed to fetch')
            ? 'Cannot reach backend. Tried: ' + ANALYZE_API_BASES.join(', ')
            : (msg || 'Analysis failed. Please try again.')
        );
      }
    }
  }

  async function triggerRagIndex(githubUrl) {
    console.log('[NAVIgit] Starting RAG indexing for:', githubUrl);
    try {
      const { res, base } = await fetchWithFallback('/rag/index', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ github_url: githubUrl })
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        console.warn('[NAVIgit] RAG indexing failed:', err.detail || res.status);
        return;
      }

      const stats = await res.json();
      console.log('[NAVIgit] RAG indexed via', base + ':', stats.files_indexed, 'files,', stats.chunks_indexed, 'chunks');
      if (typeof onRagIndexReady === 'function') onRagIndexReady();
    } catch (err) {
      console.warn('[NAVIgit] RAG index error (chat unavailable):', err.message);
    }
  }
});
