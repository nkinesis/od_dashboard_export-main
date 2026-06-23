/** Standalone OD pages → SPA host (/?view=…) unless embedded in iframe. */
(function () {
  try {
    if (new URLSearchParams(window.location.search).get('embed') === '1') return;
  } catch (_) {
    return;
  }
  var path = (window.location.pathname || '').split('/').pop() || '';
  var viewByPath = {
    'od.html': 'zones',
    'od-buildings.html': 'buildings',
    'od-flows.html': 'flows',
  };
  var view = viewByPath[path];
  if (!view) return;
  var params = new URLSearchParams(window.location.search);
  params.set('view', view);
  try {
    if (params.get('attribution') !== 'dest' && sessionStorage.getItem('dashAttribution') === 'dest') {
      params.set('attribution', 'dest');
    }
  } catch (_) { /* empty */ }
  var target = (window.DashConfig && typeof DashConfig.spaHistoryUrl === 'function')
    ? DashConfig.spaHistoryUrl(params)
    : ('/' + (params.toString() ? '?' + params.toString() : ''));
  window.location.replace(target);
})();
