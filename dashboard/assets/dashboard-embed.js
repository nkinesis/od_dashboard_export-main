/** Embed-mode helpers for dashboard views loaded inside the SPA host iframe. */
(function () {
  var IS_EMBED = new URLSearchParams(window.location.search).get('embed') === '1';
  if (IS_EMBED) document.documentElement.classList.add('dash-embed');

  function pageName() {
    return (document.body && document.body.dataset.dashPage) || '';
  }

  function notifyReady() {
    if (IS_EMBED && window.parent !== window) {
      window.parent.postMessage({ type: 'dash-ready', page: pageName() }, '*');
    }
  }

  function notifyDataReady(detail) {
    if (IS_EMBED && window.parent !== window) {
      window.parent.postMessage(
        { type: 'dash-data-ready', page: pageName(), detail: detail || null },
        '*'
      );
    }
  }

  function syncHint() {
    if (!IS_EMBED || window.parent === window) return;
    var live = document.getElementById('liveHint');
    var hint = document.getElementById('hint');
    var text = '';
    if (live && live.textContent) text = live.textContent.trim();
    if (!text && hint) {
      var tmp = document.createElement('div');
      tmp.innerHTML = hint.innerHTML || hint.textContent || '';
      text = (tmp.textContent || '').trim();
    }
    if (text) {
      window.parent.postMessage({ type: 'dash-hint', page: pageName(), text: text }, '*');
    }
  }

  function bindShow(handler) {
    window.addEventListener('message', function (e) {
      if (e.data && e.data.type === 'dash-show' && IS_EMBED && typeof handler === 'function') {
        handler();
      }
    });
  }

  window.DashEmbed = {
    isEmbed: IS_EMBED,
    notifyReady: notifyReady,
    notifyDataReady: notifyDataReady,
    syncHint: syncHint,
    bindShow: bindShow,
  };
})();
