/* Service worker – offline průvodce.
   Aplikace a data: stale-while-revalidate. Mapové dlaždice: cache při prohlížení (omezený počet).
   Statické stránky (kaple/, trasy/ … z tools/build_pages.py) se nepředukládají – uloží se při první
   návštěvě a offline pak fungují; nenavštívená stránka offline ukáže odkaz na průvodce. */
const VERSION = "v7";
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
    if (req.mode === "navigate") return offlineFallback(c, url);
    return new Response("", { status: 504 });
  })());
});

// Offline a stránka není v cache: aplikace jen pro kořen webu, jinak krátká offline stránka
// (index.html má relativní cesty, v podadresáři by se rozbil).
async function offlineFallback(c, url) {
  const scope = new URL(self.registration.scope);
  if (url.pathname === scope.pathname || url.pathname === `${scope.pathname}index.html`) {
    return (await c.match("index.html")) || new Response("", { status: 504 });
  }
  const html = `<!doctype html><html lang="cs"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Offline · Svatá cesta</title><link rel="stylesheet" href="${scope.href}css/app.css"></head>
<body><main style="padding-top:0"><div class="page prose"><header class="page-head"><p class="eyebrow">Offline</p><h1>Jste bez připojení</h1></header>
<p>Tuto stránku jste zatím neotevřeli s připojením, proto není uložená. Mapa, kaple a modlitby v průvodci fungují i offline.</p>
<p><a class="btn btn-primary" href="${scope.href}">Otevřít průvodce</a></p></div></main></body></html>`;
  return new Response(html, { status: 503, headers: { "Content-Type": "text/html; charset=utf-8" } });
}

let trimming = false;
async function trimTiles(c) {
  if (trimming) return;
  trimming = true;
  try {
    const keys = await c.keys();
    for (let i = 0; i < keys.length - MAX_TILES; i++) await c.delete(keys[i]);
  } finally { trimming = false; }
}
