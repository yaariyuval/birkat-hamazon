// Offline cache: serve everything from cache, refresh it in the background.
const CACHE = 'bhm-v9';
const FILES = [
  './', 'index.html', 'style.css', 'app.js', 'text.js', 'calendar.js', 'manifest.webmanifest',
  'fonts/StamSiddur-nikud.woff2?v=4', 'fonts/StamSefarad-nikud.woff2?v=4', 'fonts/StamAshkenaz-nikud.woff2?v=4', 'fonts/SchwarzStamAri-nikud.woff2?v=4', 'fonts/KeterYG-Medium.woff2?v=4', 'fonts/FrankRuehlCLM-Medium.woff2?v=4',
  'icons/icon-192.png', 'icons/icon-512.png', 'icons/maskable-512.png',
];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(FILES.map(f => new Request(f, { cache: 'reload' })))).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  e.respondWith(caches.open(CACHE).then(async cache => {
    const hit = await cache.match(e.request, { ignoreSearch: true });
    const fresh = fetch(e.request, { cache: 'no-cache' }).then(r => { if (r.ok) cache.put(e.request, r.clone()); return r; }).catch(() => hit);
    return hit || fresh;
  }));
});
