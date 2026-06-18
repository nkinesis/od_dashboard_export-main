/**
 * Full-page loading overlay.
 * - finish() — loading GIF until data ready, then brief complete GIF (dashboard home).
 * - hideNow() — immediate dismiss (flows page).
 */
(function (global) {
  const ASSET_VER = '11';
  const ASSET_BASE = (function () {
    const p = window.location.pathname || '';
    if (p.includes('/')) {
      return p.substring(0, p.lastIndexOf('/') + 1) + 'assets/';
    }
    return 'assets/';
  })();

  const ASSETS = {
    loading: { original: 'original/gif-loading1.gif', fallback: 'gif-loading1-static.jpg' },
    complete: { original: 'original/loading-complete.gif', fallback: 'loading-complete-static.jpg' },
  };

  function assetUrl(rel) {
    return ASSET_BASE + rel + '?v=' + ASSET_VER;
  }

  function applyImg(img, key) {
    if (!img) return;
    const spec = ASSETS[key];
    img.onerror = function () {
      this.onerror = null;
      this.src = assetUrl(spec.fallback);
    };
    img.src = assetUrl(spec.original);
  }

  function ensureOverlay() {
    let root = document.getElementById('pageLoading');
    if (root) return root;
    root = document.createElement('div');
    root.id = 'pageLoading';
    root.className = 'page-loading';
    root.innerHTML =
      '<div class="page-loading-backdrop"></div>' +
      '<div class="page-loading-content">' +
      '<img id="loadingGif" class="page-loading-img active" alt="Loading">' +
      '<img id="loadingCompleteGif" class="page-loading-img" alt="Complete">' +
      '</div>';
    document.body.prepend(root);
    applyImg(document.getElementById('loadingGif'), 'loading');
    applyImg(document.getElementById('loadingCompleteGif'), 'complete');
    return root;
  }

  const PageLoading = {
    init() {
      ensureOverlay();
      return Promise.resolve();
    },

    show() {
      const root = ensureOverlay();
      root.classList.remove('hidden', 'fade-out');
      const loading = document.getElementById('loadingGif');
      const complete = document.getElementById('loadingCompleteGif');
      if (complete) complete.classList.remove('active');
      if (loading) {
        loading.classList.add('active');
        loading.src = assetUrl(ASSETS.loading.original) + '&_=' + Date.now();
      }
    },

    hideNow() {
      const root = ensureOverlay();
      root.classList.add('hidden', 'fade-out');
      const loading = document.getElementById('loadingGif');
      const complete = document.getElementById('loadingCompleteGif');
      if (loading) loading.classList.remove('active');
      if (complete) complete.classList.remove('active');
    },

    finish(completeMs) {
      const ms = completeMs == null ? 1100 : completeMs;
      return new Promise((resolve) => {
        const root = ensureOverlay();
        const loading = document.getElementById('loadingGif');
        const complete = document.getElementById('loadingCompleteGif');
        if (loading) loading.classList.remove('active');
        if (complete) {
          applyImg(complete, 'complete');
          complete.src = assetUrl(ASSETS.complete.original) + '&_=' + Date.now();
          complete.classList.add('active');
        }
        setTimeout(() => {
          root.classList.add('fade-out');
          setTimeout(() => {
            root.classList.add('hidden');
            root.classList.remove('fade-out');
            if (complete) complete.classList.remove('active');
            resolve();
          }, 380);
        }, ms);
      });
    },
  };

  global.PageLoading = PageLoading;
})(window);
