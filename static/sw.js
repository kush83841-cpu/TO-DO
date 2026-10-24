/* ToDo service worker: caches static assets so the app shell works
   offline. Pages (tasks) are always fetched from the network so the
   task list is never stale. */

const CACHE = "todo-v1";
const ASSETS = ["/static/style.css", "/static/script.js"];

self.addEventListener("install", (event) => {
    event.waitUntil(
        caches
            .open(CACHE)
            .then((cache) => cache.addAll(ASSETS))
            .then(() => self.skipWaiting())
    );
});

self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches
            .keys()
            .then((keys) =>
                Promise.all(
                    keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))
                )
            )
            .then(() => self.clients.claim())
    );
});

self.addEventListener("fetch", (event) => {
    if (event.request.method !== "GET") return;
    const url = new URL(event.request.url);
    // Static assets: serve from cache when available, else fetch + cache.
    if (url.pathname.startsWith("/static/")) {
        event.respondWith(
            caches.match(event.request).then(
                (cached) =>
                    cached ||
                    fetch(event.request).then((response) => {
                        const copy = response.clone();
                        caches.open(CACHE).then((cache) => cache.put(event.request, copy));
                        return response;
                    })
            )
        );
    }
    // Everything else (pages): network only, tasks stay fresh.
});