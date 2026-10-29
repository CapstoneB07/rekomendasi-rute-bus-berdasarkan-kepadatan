// Service worker TJ Lega: cangkang aplikasi offline. Data rute/bus tidak pernah di-cache (harus selalu segar).
const VERSI = 'tj-lega-v1';
const HALAMAN_OFFLINE = '/offline.html';
const ASET_AWAL = [HALAMAN_OFFLINE, '/icon-192.png', '/logo-transjakarta.png'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(VERSI).then((c) => c.addAll(ASET_AWAL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches
      .keys()
      .then((nama) => Promise.all(nama.filter((n) => n !== VERSI).map((n) => caches.delete(n))))
      .then(() => self.clients.claim()),
  );
});

async function cacheLaluJaringan(req) {
  const c = await caches.open(VERSI);
  const ada = await c.match(req);
  if (ada) return ada;
  const res = await fetch(req);
  if (res.ok) c.put(req, res.clone());
  return res;
}

async function segarkanSambilPakaiCache(req) {
  const c = await caches.open(VERSI);
  const ada = await c.match(req);
  const dariJaringan = fetch(req)
    .then((res) => {
      if (res.ok) c.put(req, res.clone());
      return res;
    })
    .catch(() => ada);
  return ada ?? dariJaringan;
}

self.addEventListener('fetch', (e) => {
  const req = e.request;
  const url = new URL(req.url);
  if (req.method !== 'GET' || url.origin !== self.location.origin) return;

  if (req.mode === 'navigate') {
    e.respondWith(fetch(req).catch(() => caches.match(HALAMAN_OFFLINE)));
  } else if (url.pathname.startsWith('/_next/static/')) {
    // Nama berkas ber-hash, jadi aman di-cache selamanya.
    e.respondWith(cacheLaluJaringan(req));
  } else if (/\.(png|svg|ico|woff2?)$/.test(url.pathname)) {
    e.respondWith(segarkanSambilPakaiCache(req));
  }
});
