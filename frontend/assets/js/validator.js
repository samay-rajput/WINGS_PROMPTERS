/* ══════════════════════════════════════════════════════
   VALIDATOR.JS — GitHub URL Validation
   Codebase Intelligence Agent
══════════════════════════════════════════════════════ */

const GITHUB_PREFIX = 'https://github.com/';

/**
 * Validates a GitHub repository URL.
 * Must match pattern: https://github.com/user/repo
 *
 * @param {string} url - The URL string to validate.
 * @returns {{ valid: boolean, msg?: string, name?: string }}
 *   - valid: whether the URL is a valid GitHub repo URL
 *   - msg:   error message if invalid
 *   - name:  "user/repo" extracted from the URL if valid
 */
function isValidGitHubUrl(url) {
  const trimmed = (url || '').trim();

  if (!trimmed) {
    return {
      valid: false,
      msg: 'Please enter a GitHub repository URL.'
    };
  }

  if (!trimmed.startsWith(GITHUB_PREFIX)) {
    return {
      valid: false,
      msg: 'URL must start with https://github.com/'
    };
  }

  // Extract the path after github.com/
  const path = trimmed
    .replace(GITHUB_PREFIX, '')
    .replace(/\/+$/, '');            // strip trailing slashes

  const parts = path.split('/').filter(Boolean);

  if (parts.length < 2) {
    return {
      valid: false,
      msg: 'Please provide a valid repository path (user/repo).'
    };
  }

  return {
    valid: true,
    name: parts[0] + '/' + parts[1]
  };
}
