// Just enough service worker to make the page installable and to open when
// the server is unreachable. Answers are never cached: a stale reply about
// where you are in a book is worse than no reply.
//
// The network comes first and the cache is only the fallback. Serving the
// cache first and refreshing behind it — the usual advice — meant every
// deployment took two reloads to appear, one to fetch it and another to show
// it. This page is a few kilobytes on a tailnet: fetching it is not the slow
// part of anything.

const CACHE = "somnia-v4";
const SHELL = [
  ".",
  "index.html",
  "style.css",
  "app.js",
  "manifest.webmanifest",
  "icon-192.png",
  "icon-512.png",
  // The page's serif, and the reason it is served from here rather than from a
  // font CDN. A cross-origin font comes back opaque, an opaque response cannot
  // go in this cache, and a shell that caches the stylesheet but not the face
  // it asks for opens the first offline night in whatever serif the phone has
  // and then reflows the whole page when the network comes back.
  "newsreader-latin.woff2",
  "newsreader-latin-italic.woff2",
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
      .then((keys) =>
        Promise.all(
          keys
            .filter((k) => k.startsWith("somnia-") && k !== CACHE)
            .map((k) => caches.delete(k)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  // `includes` rather than `startsWith`: the app may be mounted under a path.
  //
  // A ranged reply is a 206, `response.ok` is true for a 206, and the Cache API
  // refuses to store one — so a cached seek is an unhandled rejection on every
  // scrub. The audio lives under /api/ and is skipped by the test above; the
  // range check catches anything that asks for part of a file by another route.
  if (
    event.request.method !== "GET" ||
    url.pathname.includes("/api/") ||
    event.request.headers.has("range")
  )
    return;

  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put(event.request, copy));
        }
        return response;
      })
      // Offline, or the VPS is down: whatever was cached last is better than
      // the browser's own error page.
      .catch(() => caches.match(event.request)),
  );
});
