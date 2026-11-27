// Network first, falls back to the last copy when offline.
const CACHE = 'sfbirds-v2';
self.addEventListener('install', e => { e.waitUntil(caches.open(CACHE).then(c => c.addAll(['./', 'index.html', 'archive.html'])).then(() => self.skipWaiting())); });
self.addEventListener('activate', e => { e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())); });
self.addEventListener('fetch', e => {
  // Only cache the app itself and its libraries, not map tiles (there are millions of them).
  const host = new URL(e.request.url).hostname;
  if (e.request.method !== 'GET' || (host !== self.location.hostname && host !== 'unpkg.com')) return;
  e.respondWith(fetch(e.request).then(res => { if (res.ok) { const c = res.clone(); caches.open(CACHE).then(ch => ch.put(e.request, c)); } return res; })
    .catch(() => caches.match(e.request)));
});
