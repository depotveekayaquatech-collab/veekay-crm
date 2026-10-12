// Vendor app service worker. Deliberately small: it makes the app installable and keeps the app shell available
// offline. It never caches API responses (they hold private data) and only handles requests under /vendor/ scope.
const SHELL = "vendor-shell-v1";

self.addEventListener("install", () => self.skipWaiting());

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== SHELL).map((k) => caches.delete(k)))).then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  const url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== location.origin || url.pathname.startsWith("/api/")) return;

  // Pages: always try the network (fresh deploys), fall back to the last shell when offline.
  if (req.mode === "navigate") {
    event.respondWith(
      fetch(req)
        .then((res) => {
          const copy = res.clone();
          caches.open(SHELL).then((c) => c.put("/vendor/", copy));
          return res;
        })
        .catch(() => caches.match("/vendor/").then((r) => r || Response.error())),
    );
    return;
  }

  // Built assets are fingerprinted, so cache-first is safe.
  if (url.pathname.startsWith("/assets/") || url.pathname.startsWith("/vendor/icon")) {
    event.respondWith(
      caches.match(req).then(
        (hit) =>
          hit ||
          fetch(req).then((res) => {
            if (res.ok) {
              const copy = res.clone();
              caches.open(SHELL).then((c) => c.put(req, copy));
            }
            return res;
          }),
      ),
    );
  }
});
