// Just enough service worker to make the page installable, and to open
// instantly when the VPS is slow to answer. Answers are never cached: a stale
// reply about where you are in a book is worse than no reply.

const CACHE = "somnia-v1";
const SHELL = [
  ".",
  "index.html",
  "style.css",
  "app.js",
  "manifest.webmanifest",
  "icon-192.png",
  "icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  // `includes` rather than `startsWith`: the app may be mounted under a path.
  if (event.request.method !== "GET" || url.pathname.includes("/api/")) return;

  // Serve the shell from cache, then refresh it in the background so a
  // redeployed page is picked up on the next launch.
  event.respondWith(
    caches.match(event.request).then((cached) => {
      const fresh = fetch(event.request)
        .then((response) => {
          if (response.ok) {
            const copy = response.clone();
            caches.open(CACHE).then((cache) => cache.put(event.request, copy));
          }
          return response;
        })
        .catch(() => cached);
      return cached || fresh;
    }),
  );
});
