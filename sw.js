/* Service worker – offline průvodce.
   Aplikace a data: stale-while-revalidate. Mapové dlaždice: cache při prohlížení (omezený počet). */
const VERSION = "v6";
const APP = `svata-cesta-app-${VERSION}`;
const TILES = "svata-cesta-tiles";
const MAX_TILES = 1500;

const SHELL = [
  "./", "index.html", "css/app.css", "js/app.js",
  "data/chapels.json", "data/route.geojson", "data/prayers.json", "data/events.json", "data/photos.json",
  "data/routes.json", ...["cela", "letnany", "vinor", "kolo", "prosek"].map((id) => `data/routes/${id}.geojson`),
  "manifest.webmanifest", "icons/icon.svg", "icons/icon-192.png",
  "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css",
  "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js",
];
const PHOTOS = ["4", "12", "14", "15", "17", "19", "23", "24", "25", "26", "26b", "29", "30", "32", "33", "35", "36", "38", "41", "42", "palladium", "bazilika", "libenveduta"].map((k) => `img/${k}.jpg`);

self.addEventListener("install", (e) => {
  e.waitUntil((async () => {
    const c = await caches.open(APP);
    await c.addAll(SHELL);
    // fotky best-effort, ať instalace nespadne kvůli jedné
    await Promise.allSettled(PHOTOS.map((u) => c.add(u)));
    self.skipWaiting();
  })());
});

self.addEventListener("activate", (e) => {
  e.waitUntil((async () => {
    for (const k of await caches.keys()) if (k.startsWith("svata-cesta-app-") && k !== APP) await caches.delete(k);
    await self.clients.claim();
  })());
});

const isTile = (url) => /tile\.openstreetmap\.org|tile\.opentopomap\.org|arcgisonline\.com/.test(url.hostname);

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);

  if (isTile(url)) {
    e.respondWith((async () => {
      const c = await caches.open(TILES);
      const hit = await c.match(req);
      if (hit) return hit;
      try {
        const res = await fetch(req);
        if (res.ok || res.type === "opaque") {
          c.put(req, res.clone());
          trimTiles(c);
        }
        return res;
      } catch {
        return new Response("", { status: 504 });
      }
    })());
    return;
  }

  const sameOrigin = url.origin === self.location.origin;
  const cacheable = sameOrigin || /cdnjs\.cloudflare\.com|fonts\.(googleapis|gstatic)\.com/.test(url.hostname);
  if (!cacheable) return;

  e.respondWith((async () => {
    const c = await caches.open(APP);
    const hit = await c.match(req, { ignoreSearch: sameOrigin });
    const net = fetch(req).then((res) => {
      if (res.ok) c.put(req, res.clone());
      return res;
    }).catch(() => null);
    if (hit) { e.waitUntil(net); return hit; }
    const res = await net;
    if (res) return res;
    if (req.mode === "navigate") return c.match("index.html");
    return new Response("", { status: 504 });
  })());
});

let trimming = false;
async function trimTiles(c) {
  if (trimming) return;
  trimming = true;
  try {
    const keys = await c.keys();
    for (let i = 0; i < keys.length - MAX_TILES; i++) await c.delete(keys[i]);
  } finally { trimming = false; }
}
