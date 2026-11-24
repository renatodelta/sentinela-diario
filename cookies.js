(function () {
  var STORAGE_KEY = 'sentinela_cookie_consent';
  if (localStorage.getItem(STORAGE_KEY)) return;

  var style = document.createElement('style');
  style.textContent = [
    '#sd-cookie-banner{position:fixed;bottom:20px;left:20px;right:20px;max-width:680px;margin:0 auto;background:#0b132b;color:#f8fafc;border:1px solid rgba(255,255,255,0.12);border-radius:14px;padding:18px 22px;box-shadow:0 20px 45px -12px rgba(11,19,43,0.45);z-index:9999;display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;font-family:Inter,-apple-system,BlinkMacSystemFont,sans-serif;font-size:0.88rem;line-height:1.5;}',
    '#sd-cookie-banner p{margin:0;flex:1 1 320px;color:#cbd5e1;}',
    '#sd-cookie-banner a{color:#34d399;text-decoration:underline;font-weight:600;}',
    '#sd-cookie-actions{display:flex;gap:10px;flex-shrink:0;}',
    '#sd-cookie-accept{background:#10b981;color:#fff;border:none;border-radius:8px;padding:9px 16px;font-weight:600;font-size:0.85rem;cursor:pointer;}',
    '#sd-cookie-accept:hover{background:#059669;}',
    '#sd-cookie-reject{background:transparent;color:#cbd5e1;border:1px solid rgba(255,255,255,0.22);border-radius:8px;padding:9px 14px;font-weight:600;font-size:0.85rem;cursor:pointer;}',
    '#sd-cookie-reject:hover{border-color:#94a3b8;color:#fff;}'
  ].join('');
  document.head.appendChild(style);

  var banner = document.createElement('div');
  banner.id = 'sd-cookie-banner';
  banner.setAttribute('role', 'dialog');
  banner.setAttribute('aria-label', 'Aviso de cookies');
  banner.innerHTML =
    '<p>Usamos cookies essenciais e de medição (Google Analytics) para melhorar sua experiência e acompanhar o desempenho do site. Veja nossa <a href="/privacidade.html">Política de Privacidade</a>.</p>' +
    '<div id="sd-cookie-actions">' +
      '<button type="button" id="sd-cookie-reject">Recusar</button>' +
      '<button type="button" id="sd-cookie-accept">Aceitar cookies</button>' +
    '</div>';

  function closeBanner(choice) {
    localStorage.setItem(STORAGE_KEY, choice);
    if (typeof window.gtag === 'function') {
      window.gtag('consent', 'update', {
        analytics_storage: choice === 'accepted' ? 'granted' : 'denied'
      });
    }
    banner.remove();
  }

  document.body.appendChild(banner);
  document.getElementById('sd-cookie-accept').addEventListener('click', function () {
    closeBanner('accepted');
  });
  document.getElementById('sd-cookie-reject').addEventListener('click', function () {
    closeBanner('rejected');
  });
})();
