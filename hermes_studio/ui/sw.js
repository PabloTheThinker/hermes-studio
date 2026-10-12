/* Hermes Studio · Edit page media worker.
   <video> and <img> can't send an Authorization header, so this worker adds the Edit page's token
   to same-origin requests for project files (/api/projects/<id>/media/..., /frame, /renders/.../file).
   The token lives in this worker's memory only: the page posts it after it gets it from the app
   (or the person pastes it), and it is never written to a URL, storage or a cookie (S3 §13.3). */
"use strict";
let token = "";

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));
self.addEventListener("message", (e) => {
  if (e.origin && e.origin !== self.location.origin) return;
  const t = e.data && e.data.token;
  if (typeof t === "string" && /^[0-9a-f]{64}$/.test(t)) token = t;
  if (e.data && e.data.clear) token = "";
  if (e.ports && e.ports[0]) e.ports[0].postMessage({ ok: !!token });
});

const MEDIA = /^\/api\/projects\/[^/]+\/(media\/[^/]+\/(proxy|thumbs|thumbs\.json|wave|words)|frame|renders\/[^/]+\/file)$/;

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (!token || url.origin !== self.location.origin || !MEDIA.test(url.pathname) || e.request.method !== "GET") return;
  if (e.request.headers.get("Authorization")) return;
  const headers = new Headers(e.request.headers);
  headers.set("Authorization", "Bearer " + token);
  e.respondWith(fetch(new Request(e.request.url, { method: "GET", headers, credentials: "omit", cache: "no-store" })));
});
