/// <reference lib="webworker" />
// Eigener Service Worker: Offline-Lesen (N-07) und Ziel im Teilen-Menü (D-LINK)
import { CacheableResponsePlugin } from "workbox-cacheable-response";
import { clientsClaim } from "workbox-core";
import { ExpirationPlugin } from "workbox-expiration";
import { cleanupOutdatedCaches, createHandlerBoundToURL, precacheAndRoute } from "workbox-precaching";
import { NavigationRoute, registerRoute } from "workbox-routing";
import { CacheFirst, NetworkFirst } from "workbox-strategies";

declare let self: ServiceWorkerGlobalScope;

const SHARE_CACHE = "geteilt";

// Teilen-Ziel: Formular aus dem Teilen-Menü abfangen, ablegen und die Importvorschau öffnen
self.addEventListener("fetch", (event: FetchEvent) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "POST" || url.pathname !== "/teilen") return;
  event.respondWith(
    (async () => {
      const form = await event.request.formData();
      const text = (k: string) => {
        const v = form.get(k);
        return typeof v === "string" ? v : "";
      };
      const cache = await caches.open(SHARE_CACHE);
      await cache.put(
        "/geteilt/daten",
        new Response(JSON.stringify({ title: text("title"), text: text("text"), url: text("url") }), {
          headers: { "Content-Type": "application/json" },
        }),
      );
      const files = form.getAll("bilder").filter((f): f is File => f instanceof File).slice(0, 4);
      await Promise.all(files.map((f, i) => cache.put(`/geteilt/bild-${i}`, new Response(f))));
      return Response.redirect("/neu?geteilt=1", 303);
    })(),
  );
});

self.skipWaiting();
clientsClaim();

precacheAndRoute(self.__WB_MANIFEST);
cleanupOutdatedCaches();

registerRoute(
  new NavigationRoute(createHandlerBoundToURL("/index.html"), {
    denylist: [/^\/api\//, /^\/teilen/],
  }),
);

// Lesende Aufrufe: erst Netz, ohne Empfang der letzte Stand (Plan und Rezepte der Woche)
registerRoute(
  ({ url, request }) =>
    request.method === "GET" &&
    url.pathname.startsWith("/api/v1/") &&
    !url.pathname.startsWith("/api/v1/images/") &&
    !url.pathname.startsWith("/api/v1/imports") &&
    !url.pathname.startsWith("/api/v1/export"),
  new NetworkFirst({
    cacheName: "api",
    networkTimeoutSeconds: 4,
    plugins: [
      new CacheableResponsePlugin({ statuses: [200] }),
      new ExpirationPlugin({ maxEntries: 400, maxAgeSeconds: 60 * 60 * 24 * 30 }),
    ],
  }),
);

registerRoute(
  ({ url }) => url.pathname.startsWith("/api/v1/images/"),
  new CacheFirst({
    cacheName: "bilder",
    plugins: [
      new CacheableResponsePlugin({ statuses: [200] }),
      new ExpirationPlugin({ maxEntries: 300, maxAgeSeconds: 60 * 60 * 24 * 60 }),
    ],
  }),
);
