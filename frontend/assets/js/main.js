/* MAIN.JS - App Entry & Page Routing */
const MOCK_API = false;
const ANALYZE_API_BASE = window.__API_BASE__ || 'http://localhost:5000';

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

    try {
      const res = await fetch(ANALYZE_API_BASE + '/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ github_url: githubUrl })
      });

      let data = null;
      try { data = await res.json(); } catch (_) { data = null; }

      if (!res.ok) {
        const msg = (data && data.error) ? data.error : 'Server error (' + res.status + ')';
        throw new Error(msg);
      }

      if (typeof renderAll !== 'function') {
        throw new Error('renderAll() not found - check results.js');
      }

      hideLoading();
      renderAll(data);
    } catch (err) {
      console.error('[NAVIgit] /analyze failed:', err);
      hideLoading();
      showPage('input-page');
      const msg = err && err.message ? String(err.message) : '';
      showError(
        msg.includes('Failed to fetch')
          ? 'Cannot reach backend at ' + ANALYZE_API_BASE + '. Is it running?'
          : (msg || 'Analysis failed. Please try again.')
      );
    }
  }
});
