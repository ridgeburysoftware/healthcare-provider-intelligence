// Basic production pageviews only. Shared with the CMS and provider frontends.
(() => {
  const domains = ['ridgeburysoftware.com', 'www.ridgeburysoftware.com'];
  const website = '23e89d4c-5d40-4bef-8d81-f2eec259ffd8';
  if (location.protocol !== 'https:' || !domains.includes(location.hostname) || window.top !== window.self) return;
  if (navigator.doNotTrack === '1' || navigator.globalPrivacyControl === true) return;
  try { if (localStorage.getItem('umami.disabled')) return; } catch { /* Storage can be unavailable. */ }
  if (document.querySelector(`script[data-website-id="${website}"]`)) return;

  window.ridgeburyAnalyticsBeforeSend = (type, payload) => {
    if (type !== 'event' || !payload || typeof payload.url !== 'string' || payload.name) return false;
    let url;
    try { url = new URL(payload.url, location.origin); } catch { return false; }
    if (!domains.includes(url.hostname)) return false;
    const path = url.pathname;
    const area = /^\/demos\/policy(?:\/|$)/.test(path) ? 'cms'
      : /^\/demos\/providers(?:\/|$)/.test(path) ? 'provider' : 'site';
    let referrer = '';
    try {
      const source = new URL(payload.referrer || document.referrer, location.origin);
      if (payload.referrer || document.referrer) referrer = source.origin;
    } catch { /* Ignore invalid referrers. */ }
    // Reconstruct the payload: no query/hash, record titles, form contents, or custom data.
    return {
      website, hostname: location.hostname, url: path, referrer, tag: area,
      title: area === 'cms' ? 'CMS Policy Rule Builder'
        : area === 'provider' ? 'Healthcare Provider Intelligence' : 'Ridgebury Software',
      screen: `${screen.width}x${screen.height}`, language: navigator.language,
    };
  };

  const script = document.createElement('script');
  script.defer = true;
  script.src = 'https://cloud.umami.is/script.js';
  script.referrerPolicy = 'no-referrer';
  script.dataset.websiteId = website;
  script.dataset.hostUrl = 'https://gateway.umami.is';
  script.dataset.domains = domains.join(',');
  script.dataset.excludeSearch = 'true';
  script.dataset.excludeHash = 'true';
  script.dataset.doNotTrack = 'true';
  script.dataset.beforeSend = 'ridgeburyAnalyticsBeforeSend';
  document.head.append(script);
})();
