// PWA manifest読み込みの条件分岐（Cloudflare Access CSPエラー回避）
// localhost または pi-camera 環境でのみPWA機能を有効化
(function() {
  const hostname = window.location.hostname;
  if (hostname === 'localhost' || hostname === '127.0.0.1' || hostname.includes('pi-camera')) {
    const manifestLink = document.createElement('link');
    manifestLink.rel = 'manifest';
    manifestLink.href = '/manifest.json';
    document.head.appendChild(manifestLink);
    console.log('✅ PWA manifest loaded for local/pi-camera environment');
  } else {
    console.log('ℹ️ PWA manifest skipped for Cloudflare Access environment (CSP compatibility)');
  }
})();
