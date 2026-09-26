/* Svatá cesta – průvodce poutníka
   Vanilla JS + Leaflet, bez build kroku. */

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const STATUS_LABEL = { stoji: "stojí", replika: "replika", zanikla: "zaniklá" };
const MODE_LABEL = { pesky: "pěšky", kolo: "na kole" };
const START = { lat: 50.09079, lon: 14.437006 };
const POIS = [
  { kind: "start", lat: START.lat, lon: START.lon, title: "Poříčská brána", text: "Historický začátek Svaté cesty. Brána stála v místech dnešního náměstí Republiky (u ulice Na Poříčí). Poutníci sem přicházeli z katedrály sv. Víta, z Lorety nebo od sv. Jakuba." },
  { kind: "end", lat: 50.194591, lon: 14.67228, title: "Bazilika sv. Václava", text: "Místo mučednické smrti sv. Václava (28. 9. 935). Pod kostelem je románská krypta sv. Kosmy a Damiána. Hned vedle stojí románský kostel sv. Klimenta." },
  { kind: "end", lat: 50.196034, lon: 14.676585, title: "Bazilika Nanebevzetí Panny Marie", text: "Raně barokní poutní chrám z let 1613–1623, domov Palladia země české – cíl mariánských poutí a Svaté cesty." },
  { kind: "end", lat: 50.197362, lon: 14.678337, title: "Kaple bl. Podivena", text: "Kaple připomíná Podivena, věrného sluhu sv. Václava, který podle legendy ukryl Palladium." },
];
const STAGES = [
  { from: 0, to: 4.5, chapels: [1, 8], title: "Praha – Karlín – Libeň", text: "Od Poříčské brány (náměstí Republiky) Karlínem a přes Palmovku. Původní kaple ustoupily železnici a městu – dochovala se jen kaplička u Invalidovny (č. 4). Metro B: Florenc, Křižíkova, Invalidovna, Palmovka." },
  { from: 4.5, to: 8, chapels: [9, 13], title: "Vysočany – Klíčov", text: "Přes Rokytku do Vysočan a do kopce ulicemi Pod Krocínkou a Ke Klíčovu. Nahoře na poli stojí první kaple mezi poli (č. 12)." },
  { from: 8, to: 12.5, chapels: [14, 21], title: "Letňany – Kbely", text: "Nejlépe obnovený úsek: cyklostezka s alejí po stopě staré cesty, kaple 14, 15 a 17 a čtyři nové repliky v Kbelích. Dobré místo pro start zkrácené pouti (metro C Letňany)." },
  { from: 12.5, to: 17.5, chapels: [22, 29], title: "Vinoř", text: "Polní cestou ke kaplím 23 a 24 (tady se stará stezka dochovala jako mez mezi poli), pak Vinoří kolem kaple s nápisem Rosa Mystica (č. 26) až ke Svatokřížské kapli u rybníka." },
  { from: 17.5, to: 22, chapels: [30, 38], title: "Podolanka – Dřevčice", text: "Nejdelší řada dochovaných kaplí – 30, 32, 33, 35, 36 a 38 – v krajině otevřených polí. Cesta vede podél silnice, jděte opatrně." },
  { from: 22, to: 26, chapels: [39, 44], title: "Vrábí – Brandýs – Stará Boleslav", text: "Brandýsem kolem kaplí 41 a 42, přes Masarykovo náměstí, pod zámkem přes Labe a do Staré Boleslavi k oběma bazilikám." },
];

const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} },
};

const state = {
  chapels: [], byN: new Map(), route: null, prayers: null, events: null, photos: {},
  routes: [], routeGeo: {}, routeId: "cela", routeFilter: "all", stops: [],
  visited: new Set(store.get("vs-visited", [])),
  filter: "all", current: null, me: null, watchId: null, meKm: null, lastPos: null,
};

/* ============ Geometrie ============ */
const R = 6371000;
const toRad = (d) => (d * Math.PI) / 180;
function haversine(a, b) {
  const dLat = toRad(b.lat - a.lat), dLon = toRad(b.lon - a.lon);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(a.lat)) * Math.cos(toRad(b.lat)) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}
let routeXY = null, routeCum = null;
function prepRoute(coords) {
  const lat0 = toRad(coords[0][1]);
  routeXY = coords.map(([lon, lat]) => [toRad(lon) * R * Math.cos(lat0), toRad(lat) * R]);
  routeCum = [0];
  for (let i = 1; i < routeXY.length; i++) routeCum.push(routeCum[i - 1] + Math.hypot(routeXY[i][0] - routeXY[i - 1][0], routeXY[i][1] - routeXY[i - 1][1]));
  prepRoute.lat0 = lat0;
}
function projectOnRoute(lat, lon) {
  const p = [toRad(lon) * R * Math.cos(prepRoute.lat0), toRad(lat) * R];
  let best = { d: Infinity, along: 0 };
  for (let i = 0; i < routeXY.length - 1; i++) {
    const a = routeXY[i], b = routeXY[i + 1];
    const dx = b[0] - a[0], dy = b[1] - a[1];
    const L2 = dx * dx + dy * dy || 1e-9;
    const t = Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2));
    const d = Math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy));
    if (d < best.d) best = { d, along: routeCum[i] + t * Math.sqrt(L2) };
  }
  return best;
}
const fmtDist = (m) => (m < 1000 ? `${Math.round(m / 10) * 10} m` : `${(m / 1000).toFixed(m < 10000 ? 1 : 0).replace(".", ",")} km`);
const fmtKm = (km) => `${String(km.toFixed(1)).replace(".", ",")} km`;

/* ============ Data ============ */
async function loadJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(url);
  return r.json();
}
async function init() {
  const [chapels, route, prayers, events, photos, routes] = await Promise.all([
    loadJSON("data/chapels.json"), loadJSON("data/route.geojson"), loadJSON("data/prayers.json"),
    loadJSON("data/events.json"), loadJSON("data/photos.json"), loadJSON("data/routes.json"),
  ]);
  Object.assign(state, { chapels, route, prayers, events, photos, routes });
  chapels.forEach((c) => state.byN.set(c.n, c));
  prepRoute(route.geometry.coordinates);
  state.totalKm = routeCum.at(-1) / 1000;

  initNav();
  initMap();
  await setRoute(store.get("vs-route", "cela")).catch(() => setRoute("cela"));
  if (state.routeId !== "cela") fitRoute(false);
  initRoutes();
  renderList();
  renderPrayers();
  renderInfo();
  fillCredits();
  initSheet();
  route_();
  window.addEventListener("hashchange", route_);
  registerSW();
}

/* ============ Navigace (views) ============ */
const VIEWS = ["mapa", "trasy", "kaple", "modlitby", "historie", "info"];
function initNav() {
  const top = $(".topnav");
  top.innerHTML = $$(".tabbar a").map((a) => `<a href="${a.getAttribute("href")}" data-view="${a.dataset.view}">${a.querySelector("span").textContent}</a>`).join("");
}
function route_() {
  const h = decodeURIComponent(location.hash.slice(1));
  const m = h.match(/^k(\d+)$/);
  if (m && state.byN.has(+m[1])) {
    showView("mapa");
    focusChapel(+m[1], state.routed === true);
    openChapel(+m[1]);
    state.routed = true;
    return;
  }
  if (!$("#sheet").hidden) closeChapel();
  const t = h.match(/^trasa-([\w-]+)$/);
  if (t) {
    history.replaceState(null, "", "#mapa");
    selectRoute(t[1]);
    state.routed = true;
    return;
  }
  showView(VIEWS.includes(h) ? h : "mapa");
  state.routed = true;
}
function showView(v) {
  VIEWS.forEach((name) => ($(`#view-${name}`).hidden = name !== v));
  $$("[data-view]").forEach((a) => a.classList.toggle("is-on", a.dataset.view === v));
  document.title = v === "mapa" ? "Svatá cesta · Praha → Stará Boleslav" : `${$(`#view-${v}`).dataset.title} · Svatá cesta`;
  if (v === "mapa" && state.map) setTimeout(() => state.map.invalidateSize(), 0);
  if (v !== "mapa") window.scrollTo(0, 0);
  if (v === "kaple") renderList();
  if (v === "trasy") renderRoutes();
}

/* ============ Mapa ============ */
function isDark() {
  const t = document.documentElement.dataset.theme;
  return t ? t === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
}
function initMap() {
  const map = L.map("map", { zoomControl: false, zoomSnap: 0.25 }).setView([50.14, 14.55], 12);
  L.control.zoom({ position: "topleft" }).addTo(map);
  state.map = map;

  const osmAttr = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';
  const bases = {
    osm: L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: osmAttr, className: "tiles-dim" }),
    topo: L.tileLayer("https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png", {
      maxZoom: 17, subdomains: "abc", className: "tiles-dim",
      attribution: `${osmAttr}, SRTM | &copy; <a href="https://opentopomap.org">OpenTopoMap</a> (CC-BY-SA)`,
    }),
    sat: L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
      maxZoom: 19, attribution: "Letecké snímky &copy; Esri, Maxar, Earthstar Geographics",
    }),
  };
  let base = store.get("vs-base", "osm");
  if (!bases[base]) base = "osm";
  bases[base].addTo(map);
  $(`input[name=base][value=${base}]`).checked = true;
  $$("input[name=base]").forEach((r) => r.addEventListener("change", () => {
    Object.values(bases).forEach((l) => map.removeLayer(l));
    bases[r.value].addTo(map);
    store.set("vs-base", r.value);
  }));

  // Trasa
  const latlngs = state.route.geometry.coordinates.map(([lon, lat]) => [lat, lon]);
  const css = getComputedStyle(document.documentElement);
  state.routeCasing = L.polyline(latlngs, { color: "#fff", weight: 9, opacity: isDark() ? 0.15 : 0.9, interactive: false }).addTo(map);
  state.routeLine = L.polyline(latlngs, { color: css.getPropertyValue("--route").trim() || "#7a1f2b", weight: 5, opacity: 0.85, interactive: false }).addTo(map);

  // Historická stopa – spojnice původních poloh
  const hist = state.chapels.map((c) => c.orig || [c.lat, c.lon]);
  state.histLine = L.polyline([[START.lat, START.lon], ...hist], { color: css.getPropertyValue("--gold").trim(), weight: 2.5, dashArray: "2 7", lineCap: "round", interactive: false });
  $("#chk-hist").addEventListener("change", (e) => (e.target.checked ? state.histLine.addTo(map) : map.removeLayer(state.histLine)));

  // POI
  POIS.forEach((p) => {
    const icon = L.divIcon({ className: "", html: `<div class="mk-poi ${p.kind === "start" ? "mk-start" : ""}"><svg viewBox="0 0 32 32"><use href="#i-chapel"/></svg></div>`, iconSize: [34, 34], iconAnchor: [17, 17] });
    L.marker([p.lat, p.lon], { icon, title: p.title, zIndexOffset: 800 })
      .bindPopup(`<strong style="font-family:var(--serif);font-size:18px">${esc(p.title)}</strong><br><span style="font-size:13.5px">${esc(p.text)}</span>`)
      .addTo(map);
  });

  // Kaple
  state.markers = new Map();
  state.lostLayer = L.layerGroup().addTo(map);
  state.chapelLayer = L.layerGroup().addTo(map);
  state.chapels.forEach((c) => {
    const size = c.status === "zanikla" ? 24 : 30;
    const icon = L.divIcon({ className: "", html: markerHTML(c), iconSize: [size, size], iconAnchor: [size / 2, size / 2] });
    const m = L.marker([c.lat, c.lon], { icon, title: `${c.n}. ${c.name}`, zIndexOffset: c.status === "zanikla" ? 0 : 500, keyboard: true });
    m.bindTooltip(`${c.n}. ${c.name}`, { direction: "top", offset: [0, -14], className: "mk-tip" });
    m.on("click", () => openChapel(c.n));
    (c.status === "zanikla" ? state.lostLayer : state.chapelLayer).addLayer(m);
    state.markers.set(c.n, m);
  });
  $("#chk-lost").addEventListener("change", (e) => (e.target.checked && map.getZoom() >= 13 ? state.lostLayer.addTo(map) : map.removeLayer(state.lostLayer)));

  fitRoute(false);
  const onZoom = () => {
    const z = map.getZoom();
    map.getContainer().classList.toggle("z-low", z < 14);
    map.getContainer().classList.toggle("z-min", z < 12);
    if ($("#chk-lost").checked) (z >= 13 ? state.lostLayer.addTo(map) : map.removeLayer(state.lostLayer));
  };
  map.on("zoomend", onZoom);
  onZoom();

  // Ovládání
  $("#btn-fit").addEventListener("click", () => fitRoute());
  $("#btn-layers").addEventListener("click", (e) => {
    e.stopPropagation();
    const menu = $("#layers-menu");
    menu.hidden = !menu.hidden;
    $("#btn-layers").classList.toggle("is-on", !menu.hidden);
  });
  map.on("click", () => { $("#layers-menu").hidden = true; $("#btn-layers").classList.remove("is-on"); });
  $("#btn-locate").addEventListener("click", toggleLocate);
  $("#pc-next").addEventListener("click", () => state.nextN && (focusChapel(state.nextN), openChapel(state.nextN)));

  // Uvítání
  if (!store.get("vs-welcomed", false) && !location.hash.startsWith("#k") && !location.hash.startsWith("#trasa-")) {
    $("#welcome").hidden = false;
    $("#welcome-go").addEventListener("click", closeWelcome);
    $("#welcome a").addEventListener("click", closeWelcome);
  }
  renderEventPill();
}
function closeWelcome() { $("#welcome").hidden = true; store.set("vs-welcomed", true); }
function markerHTML(c) {
  return `<div class="mk mk-${c.status}${state.visited.has(c.n) ? " is-visited" : ""}" data-n="${c.n}">${c.n}</div>`;
}
function refreshMarker(n) {
  const c = state.byN.get(n), m = state.markers.get(n);
  const size = c.status === "zanikla" ? 24 : 30;
  m.setIcon(L.divIcon({ className: "", html: markerHTML(c), iconSize: [size, size], iconAnchor: [size / 2, size / 2] }));
}
function fitRoute(animate = true) {
  const wide = matchMedia("(min-width: 900px)").matches;
  state.map.fitBounds(state.routeLine.getBounds(), {
    animate: animate === true,
    paddingTopLeft: wide ? [60, 80] : [22, 70],
    paddingBottomRight: wide ? [60, 40] : [22, 22],
  });
}
function focusChapel(n, animate = true) {
  const c = state.byN.get(n);
  const map = state.map;
  if (!map) return;
  const z = Math.max(map.getZoom(), 16);
  let target = L.latLng(c.lat, c.lon);
  // na desktopu je vpravo panel s detailem – posuň kapli do volné části mapy
  if (matchMedia("(min-width: 900px)").matches) target = map.unproject(map.project(target, z).add([215, 0]), z);
  map.setView(target, z, { animate });
  $$(".mk.is-active").forEach((el) => el.classList.remove("is-active"));
  setTimeout(() => $(`.mk[data-n="${n}"]`)?.classList.add("is-active"), 50);
}

/* ============ Poloha ============ */
function toggleLocate() {
  const btn = $("#btn-locate");
  if (state.watchId != null) {
    navigator.geolocation.clearWatch(state.watchId);
    state.watchId = null;
    btn.classList.remove("is-on", "is-wait");
    state.meMarker && state.map.removeLayer(state.meMarker);
    state.meCircle && state.map.removeLayer(state.meCircle);
    state.meMarker = state.meCircle = null;
    $("#progress-card").hidden = true;
    state.me = state.lastPos = null;
    renderList();
    return;
  }
  if (!("geolocation" in navigator)) return toast("Tento prohlížeč neumí zjistit polohu.");
  btn.classList.add("is-wait");
  let first = true;
  state.watchId = navigator.geolocation.watchPosition(
    (pos) => {
      btn.classList.remove("is-wait");
      btn.classList.add("is-on");
      onPosition(pos, first);
      first = false;
    },
    (err) => {
      btn.classList.remove("is-wait", "is-on");
      navigator.geolocation.clearWatch(state.watchId);
      state.watchId = null;
      toast(err.code === 1 ? "Přístup k poloze je zakázaný – povolte ho v nastavení prohlížeče." : "Polohu se nepodařilo zjistit.");
    },
    { enableHighAccuracy: true, maximumAge: 10000, timeout: 20000 }
  );
}
function onPosition(pos, first) {
  const { latitude: lat, longitude: lon, accuracy } = pos.coords;
  state.me = { lat, lon };
  state.lastPos = pos;
  const ll = [lat, lon];
  if (!state.meMarker) {
    state.meCircle = L.circle(ll, { radius: accuracy, color: "#2f7cf6", weight: 1, fillOpacity: 0.08, interactive: false }).addTo(state.map);
    state.meMarker = L.marker(ll, { icon: L.divIcon({ className: "", html: '<div class="me-dot"></div>', iconSize: [18, 18], iconAnchor: [9, 9] }), zIndexOffset: 1000, interactive: false }).addTo(state.map);
  } else {
    state.meMarker.setLatLng(ll);
    state.meCircle.setLatLng(ll).setRadius(accuracy);
  }
  const proj = projectOnRoute(lat, lon);
  const onRoute = proj.d < 1500;
  state.meKm = onRoute ? proj.along / 1000 : null;
  if (first) state.map.setView(ll, onRoute ? 16 : Math.min(state.map.getZoom(), 13));

  // Další kaple (state.stops = kaple na aktivní trase a jejich km podél ní)
  let next, nextKm;
  if (onRoute) ({ c: next, km: nextKm } = state.stops.find((s) => s.km > state.meKm + 0.02) || { c: null });
  else next = [...state.chapels].sort((a, b) => haversine(state.me, a) - haversine(state.me, b))[0];
  state.nextN = next?.n;
  const card = $("#progress-card");
  card.hidden = false;
  if (next) {
    $("#pc-next").textContent = `${next.n}. ${next.name}`;
    const dist = onRoute ? (nextKm - state.meKm) * 1000 : haversine(state.me, next);
    $("#pc-dist").textContent = fmtDist(Math.max(dist, 0));
    $(".pc-label", card).textContent = onRoute ? "Další zastavení" : "Nejbližší kaple (jste mimo trasu)";
  } else {
    $("#pc-next").textContent = "Stará Boleslav – cíl";
    $("#pc-dist").textContent = fmtDist(Math.max((state.totalKm - state.meKm) * 1000, 0));
  }
  if (onRoute) {
    const pct = Math.min(100, (state.meKm / state.totalKm) * 100);
    $("#pc-bar").style.width = pct + "%";
    $("#pc-done").textContent = `ušli jste ${fmtKm(state.meKm)}`;
    $("#pc-left").textContent = `do cíle ${fmtKm(Math.max(0, state.totalKm - state.meKm))}`;
  } else {
    $("#pc-bar").style.width = "0";
    $("#pc-done").textContent = "";
    $("#pc-left").textContent = `od trasy ${fmtDist(proj.d)}`;
  }

  // Automatické odškrtnutí
  if (accuracy < 60) {
    state.chapels.forEach((c) => {
      if (c.status === "zanikla" || state.visited.has(c.n)) return;
      if (haversine(state.me, c) < 35) {
        setVisited(c.n, true);
        toast(`Jste u kaple č. ${c.n} – ${c.name}`);
      }
    });
  }
}

/* ============ Seznam kaplí ============ */
function renderList() {
  const list = $("#chapel-list");
  const items = state.chapels.filter((c) => state.filter === "all" || c.status === state.filter);
  list.innerHTML = items.map((c) => {
    const ph = c.photo && state.photos[c.photo];
    const thumb = ph ? `<img class="thumb" src="${ph.src}" alt="" loading="lazy">` : `<span class="thumb">${c.n}</span>`;
    const dist = state.me ? `<div>${fmtDist(haversine(state.me, c))}</div>` : `<div>km ${String(c.km).replace(".", ",")}</div>`;
    return `<li><button class="chapel-row ${c.status === "zanikla" ? "is-lost" : ""}" data-n="${c.n}">
      ${thumb}
      <span class="row-main">
        <span class="row-title"><span class="row-num">${c.n}.</span>${esc(c.name)}</span>
        <span class="row-meta"><span class="badge badge-${c.status}">${STATUS_LABEL[c.status]}</span>${esc(c.area)}</span>
      </span>
      <span class="row-side">${dist}${state.visited.has(c.n) ? '<span class="row-check" title="Navštíveno"><svg viewBox="0 0 24 24"><use href="#i-check"/></svg></span>' : ""}</span>
    </button></li>`;
  }).join("");
  const standing = state.chapels.filter((c) => c.status !== "zanikla");
  const v = standing.filter((c) => state.visited.has(c.n)).length;
  $("#visited-summary").innerHTML = `<p>Navštíveno <strong>${v}</strong> z ${standing.length} stojících kaplí a replik</p><div class="bar"><span style="width:${(v / standing.length) * 100}%"></span></div>`;
}
function initListEvents() {
  $("#chapel-list").addEventListener("click", (e) => {
    const b = e.target.closest("[data-n]");
    if (b) openChapel(+b.dataset.n);
  });
  $$("#view-kaple .chips .chip").forEach((ch) => ch.addEventListener("click", () => {
    $$("#view-kaple .chips .chip").forEach((x) => x.classList.toggle("is-on", x === ch));
    state.filter = ch.dataset.filter;
    renderList();
  }));
}

/* ============ Trasy ============ */
const geoOf = (id) => (id === "cela" ? state.route.geometry.coordinates : state.routeGeo[id]);
async function routeCoords(id) {
  if (!geoOf(id)) {
    const r = state.routes.find((x) => x.id === id);
    state.routeGeo[id] = (await loadJSON(r.file)).geometry.coordinates;
  }
  return geoOf(id);
}
async function setRoute(id) {
  const r = state.routes.find((x) => x.id === id) || state.routes.find((x) => x.id === "cela");
  const coords = await routeCoords(r.id);
  state.routeId = r.id;
  store.set("vs-route", r.id);
  const latlngs = coords.map(([lon, lat]) => [lat, lon]);
  state.routeCasing.setLatLngs(latlngs);
  state.routeLine.setLatLngs(latlngs);
  prepRoute(coords);
  state.totalKm = routeCum.at(-1) / 1000;
  // hlavní trasa: kilometráž z chapels.json; ostatní: kaple do 200 m od trasy, km podél ní
  state.stops = r.id === "cela"
    ? state.chapels.map((c) => ({ c, km: c.km }))
    : state.chapels.map((c) => { const p = projectOnRoute(c.lat, c.lon); return { c, km: p.along / 1000, d: p.d }; })
        .filter((s) => s.d < 200).sort((a, b) => a.km - b.km);
  $("#route-chip").hidden = r.id === "cela";
  $("#route-chip-name").textContent = r.short || r.name;
  if (state.lastPos) onPosition(state.lastPos, false);
  renderRoutes();
}
async function selectRoute(id) {
  try { await setRoute(id); } catch { return toast("Trasu se nepodařilo načíst."); }
  if (!$("#welcome").hidden) closeWelcome();
  if (location.hash !== "#mapa") location.hash = "mapa";
  else showView("mapa");
  setTimeout(() => { state.map.invalidateSize(); fitRoute(); }, 60);
}
function initRoutes() {
  $("#route-list").addEventListener("click", (e) => {
    const b = e.target.closest("[data-route]");
    if (b) selectRoute(b.dataset.route);
  });
  $$("#route-chips .chip").forEach((ch) => ch.addEventListener("click", () => {
    $$("#route-chips .chip").forEach((x) => x.classList.toggle("is-on", x === ch));
    state.routeFilter = ch.dataset.mode;
    renderRoutes();
  }));
  $("#route-chip-reset").addEventListener("click", () => setRoute("cela").then(() => fitRoute()));
  renderRoutes();
}
// náčrtky tras – všechny ve stejném výřezu, aby šly porovnat
let sketchLoad = null;
function sketchSVG(id) {
  if (!state.sketchBox) return `<span class="rc-sketch"></span>`;
  const { minLon, maxLat, kx, s, ox, oy } = state.sketchBox;
  const path = (coords) => {
    const step = Math.max(1, Math.ceil(coords.length / 90));
    const pts = coords.filter((_, i) => i % step === 0 || i === coords.length - 1);
    return pts.map(([lon, lat], i) => `${i ? "L" : "M"}${(ox + (lon - minLon) * kx * s).toFixed(1)} ${(oy + (maxLat - lat) * s).toFixed(1)}`).join("");
  };
  const xy = ([lon, lat]) => [(ox + (lon - minLon) * kx * s).toFixed(1), (oy + (maxLat - lat) * s).toFixed(1)];
  const c = geoOf(id), [ax, ay] = xy(c[0]), [bx, by] = xy(c.at(-1));
  return `<svg class="rc-sketch" viewBox="0 0 96 64" aria-hidden="true">
    ${id !== "cela" ? `<path class="rc-base" d="${path(geoOf("cela"))}"/>` : ""}
    <path class="rc-line" d="${path(c)}"/>
    <circle class="rc-a" cx="${ax}" cy="${ay}" r="3"/><circle class="rc-b" cx="${bx}" cy="${by}" r="3"/>
  </svg>`;
}
function loadSketches() {
  sketchLoad ||= Promise.all(state.routes.map((r) => routeCoords(r.id))).then(() => {
    const all = state.routes.flatMap((r) => geoOf(r.id));
    const lons = all.map((p) => p[0]), lats = all.map((p) => p[1]);
    const minLon = Math.min(...lons), maxLon = Math.max(...lons), minLat = Math.min(...lats), maxLat = Math.max(...lats);
    const kx = Math.cos(toRad((minLat + maxLat) / 2));
    const W = 96, H = 64, pad = 7;
    const s = Math.min((W - 2 * pad) / ((maxLon - minLon) * kx), (H - 2 * pad) / (maxLat - minLat));
    state.sketchBox = { minLon, maxLat, kx, s, ox: (W - (maxLon - minLon) * kx * s) / 2, oy: (H - (maxLat - minLat) * s) / 2 };
    renderRoutes();
  }).catch(() => {});
}
function renderRoutes() {
  const list = $("#route-list");
  if (!state.routes.length || !state.routeCasing) return;
  if (!state.sketchBox && !$("#view-trasy").hidden) loadSketches();
  const f = state.routeFilter;
  const items = state.routes.filter((r) => f === "all" || (f === "snadne" ? r.effort === 1 : r.mode === f));
  list.innerHTML = items.map((r) => {
    const on = r.id === state.routeId;
    const standing = r.chapels.filter((n) => state.byN.get(n)?.status !== "zanikla").length;
    return `<li><article class="route-card${on ? " is-on" : ""}">
      <div class="rc-head">
        ${sketchSVG(r.id)}
        <div class="row-main">
          <h3 class="rc-title">${esc(r.name)}</h3>
          <div class="row-meta"><span class="badge badge-${r.mode}">${MODE_LABEL[r.mode]}</span><span class="rc-effort effort-${r.effort}" title="obtížnost ${r.effort} ze 3"><i></i><i></i><i></i>${esc(r.difficulty)}</span></div>
        </div>
      </div>
      <div class="rc-stats">
        <span><b>${fmtKm(r.km)}</b></span><span>${esc(r.time)}</span>${r.elevation != null ? `<span title="celkové stoupání">↑ ${r.elevation} m</span>` : ""}
      </div>
      ${r.surface ? `<p class="rc-surface">${esc(r.surface)}</p>` : ""}
      <div class="rc-for"><span class="rc-for-label">Pro koho</span>${(r.suitableFor || []).map((t) => `<span class="rc-tag">${esc(t)}</span>`).join("")}</div>
      <p class="rc-text">${esc(r.text)}</p>
      <ul class="rc-hl">${r.highlights.map((h) => `<li>${esc(h)}</li>`).join("")}</ul>
      <dl class="rc-where">
        <div><dt>Start</dt><dd>${esc(r.start.name)} · ${esc(r.start.transport)}</dd></div>
        <div><dt>Cíl</dt><dd>${esc(r.end.name)}</dd></div>
        <div><dt>Kaple</dt><dd>${r.chapels.length} zastavení, z toho ${standing} stojících kaplí a replik</dd></div>
      </dl>
      <details class="rc-more">
        <summary>Praktické</summary>
        <dl>
          ${r.notFor ? `<div><dt>Pozor</dt><dd>${esc(r.notFor)}</dd></div>` : ""}
          ${r.breaks ? `<div><dt>Občerstvení</dt><dd>${esc(r.breaks)}</dd></div>` : ""}
          ${r.bailout ? `<div><dt>Zkrácení</dt><dd>${esc(r.bailout)}</dd></div>` : ""}
        </dl>
      </details>
      <div class="rc-actions">
        <button class="btn ${on ? "btn-ok" : "btn-primary"}" data-route="${r.id}"><svg viewBox="0 0 24 24"><use href="#i-${on ? "check" : "map"}"/></svg>${on ? "Vybráno · ukázat na mapě" : "Zobrazit na mapě"}</button>
      </div>
    </article></li>`;
  }).join("");
}

/* ============ Detail kaple ============ */
function initSheet() {
  initListEvents();
  $("#sheet-close").addEventListener("click", closeChapel);
  $("#sheet-backdrop").addEventListener("click", closeChapel);
  document.addEventListener("keydown", (e) => e.key === "Escape" && closeChapel());
  $("#sheet-body").addEventListener("click", (e) => {
    const t = e.target.closest("[data-act]");
    if (!t) return;
    const n = state.current;
    const act = t.dataset.act;
    if (act === "visit") { setVisited(n, !state.visited.has(n)); openChapel(n, true); }
    if (act === "go") { const k = +t.dataset.n; openChapel(k); if (!$("#view-mapa").hidden) focusChapel(k); }
    if (act === "map") { location.hash = "mapa"; setTimeout(() => { focusChapel(n); openChapel(n); }, 30); }
    if (act === "share") share(n);
  });
  // Stáhnout dolů pro zavření (mobil)
  let y0 = null;
  const sheet = $("#sheet");
  sheet.addEventListener("touchstart", (e) => { y0 = sheet.scrollTop <= 0 ? e.touches[0].clientY : null; }, { passive: true });
  sheet.addEventListener("touchmove", (e) => { if (y0 != null && e.touches[0].clientY - y0 > 90) { y0 = null; closeChapel(); } }, { passive: true });
}
function openChapel(n, keepScroll = false) {
  const c = state.byN.get(n);
  if (!c) return;
  state.current = n;
  const [la, cs] = state.prayers.litany[n - 1];
  const ph = c.photo && state.photos[c.photo];
  const prev = state.byN.get(n - 1), next = state.byN.get(n + 1);
  const dist = state.me ? ` · ${fmtDist(haversine(state.me, c))} od vás` : "";
  const mapyUrl = `https://mapy.cz/turisticka?q=${c.lat},${c.lon}&x=${c.lon}&y=${c.lat}&z=17`;
  const gUrl = `https://www.google.com/maps/dir/?api=1&destination=${c.lat},${c.lon}&travelmode=walking`;
  const visited = state.visited.has(n);

  const photo = ph
    ? `<div class="d-photo"><img src="${ph.src}" alt="${esc(c.name)}"><div class="credit-overlay">Foto: ${esc(ph.author)}, <a href="${ph.page}" target="_blank" rel="noopener">${esc(ph.license)}</a></div></div>`
    : `<div class="d-nophoto"><svg viewBox="0 0 32 32"><use href="#i-chapel"/></svg><span>${c.status === "zanikla"
        ? `Kaple se nedochovala.${c.approx ? " Přesné místo neznáme – poloha na mapě je jen odhad." : " Na mapě je vyznačeno její pravděpodobné místo."} I tady se můžete zastavit a pomodlit.`
        : "Fotografie zatím chybí."}</span></div>`;

  $("#sheet-body").innerHTML = `
    ${photo}
    <div class="d-head">
      <div class="d-num">${n}. zastavení</div>
      <h2 id="sheet-title">${esc(c.name)}</h2>
      <div class="d-tags"><span class="badge badge-${c.status}">${c.moved ? "stojí (přenesená)" : c.disputed ? "stojí (sporná)" : STATUS_LABEL[c.status]}</span><span>${esc(c.area)} · km ${String(c.km).replace(".", ",")}${dist}</span></div>
    </div>
    <div class="invocation">
      <div class="inv-la">${esc(la)}</div>
      <div class="inv-cs">${esc(cs)}</div>
      <div class="inv-resp">– oroduj za nás</div>
      <div class="inv-hint">${n}. invokace loretánské litanie · Zdrávas Maria…</div>
    </div>
    <div class="d-actions">
      <button class="btn ${visited ? "btn-ok" : "btn-ghost"}" data-act="visit"><svg viewBox="0 0 24 24"><use href="#i-check"/></svg>${visited ? "Navštíveno" : "Byl/a jsem tu"}</button>
      <a class="btn btn-primary" href="${mapyUrl}" target="_blank" rel="noopener"><svg viewBox="0 0 24 24"><use href="#i-nav"/></svg>Navigovat</a>
    </div>
    <div class="d-section"><p>${esc(c.text)}</p></div>
    ${c.photo2 && state.photos[c.photo2] ? `<figure class="d-photo2"><img src="${state.photos[c.photo2].src}" alt="" loading="lazy"><figcaption>Foto: ${esc(state.photos[c.photo2].author)}, <a href="${state.photos[c.photo2].page}" target="_blank" rel="noopener">${esc(state.photos[c.photo2].license)}</a></figcaption></figure>` : ""}
    <dl class="d-facts">
      <div><dt>Poutní místo</dt><dd>${esc(c.place)}</dd></div>
      <div><dt>Mariánský obraz</dt><dd>${esc(c.image)}</dd></div>
      <div><dt>Donátor</dt><dd>${esc(c.donor)}</dd></div>
    </dl>
    <div class="d-links">
      <a href="${mapyUrl}" target="_blank" rel="noopener">Mapy.cz</a>
      <a href="${gUrl}" target="_blank" rel="noopener">Google Maps</a>
      ${$("#view-mapa").hidden ? `<button data-act="map">Ukázat na mapě</button>` : `<button data-act="share">Sdílet</button>`}
    </div>
    <div class="d-pager">
      ${prev ? `<button data-act="go" data-n="${prev.n}"><svg viewBox="0 0 24 24"><use href="#i-prev"/></svg><span>předchozí<b>${prev.n}. ${esc(prev.name)}</b></span></button>` : "<span></span>"}
      ${next ? `<button data-act="go" data-n="${next.n}"><span>další<b>${next.n}. ${esc(next.name)}</b></span><svg viewBox="0 0 24 24"><use href="#i-next"/></svg></button>` : ""}
    </div>`;
  const sheet = $("#sheet");
  sheet.hidden = false;
  $("#sheet-backdrop").hidden = false;
  if (!keepScroll) sheet.scrollTop = 0;
  $$(".mk.is-active").forEach((el) => el.classList.remove("is-active"));
  $(`.mk[data-n="${n}"]`)?.classList.add("is-active");
}
function closeChapel() {
  $("#sheet").hidden = true;
  $("#sheet-backdrop").hidden = true;
  $$(".mk.is-active").forEach((el) => el.classList.remove("is-active"));
  state.current = null;
  if (/^#k\d+$/.test(location.hash)) history.replaceState(null, "", "#mapa");
}
function setVisited(n, on) {
  on ? state.visited.add(n) : state.visited.delete(n);
  store.set("vs-visited", [...state.visited]);
  refreshMarker(n);
  renderList();
}
async function share(n) {
  const c = state.byN.get(n);
  const url = `${location.origin}${location.pathname}#k${n}`;
  const data = { title: `${n}. ${c.name} · Svatá cesta`, text: `${n}. zastavení Svaté cesty z Prahy do Staré Boleslavi`, url };
  try {
    if (navigator.share) await navigator.share(data);
    else { await navigator.clipboard.writeText(url); toast("Odkaz zkopírován"); }
  } catch {}
}

/* ============ Modlitby ============ */
function renderPrayers() {
  const P = state.prayers;
  $("#pray-howto").textContent = P.howto;
  $("#prayer-list").innerHTML = P.prayers.map((p, i) => `
    <details class="prayer" id="p-${p.id}" ${i === 0 ? "open" : ""}>
      <summary><span class="p-title">${esc(p.title)}</span>${p.when ? `<span class="p-when">${esc(p.when)}</span>` : ""}</summary>
      <div class="p-body"><p class="p-text">${esc(p.text)}</p></div>
    </details>`).join("");
  $("#litany-list").innerHTML = P.litany.map(([la, cs], i) => {
    const c = state.byN.get(i + 1);
    return `<li><button data-n="${i + 1}">${esc(cs)} <em>– oroduj za nás</em><small>${esc(la)} · kaple ${esc(c.name)}</small></button></li>`;
  }).join("");
  $("#litany-list").addEventListener("click", (e) => {
    const b = e.target.closest("[data-n]");
    if (b) openChapel(+b.dataset.n);
  });
}

/* ============ Info ============ */
function activeSpecials() {
  const now = new Date();
  return (state.events.special || []).filter((e) => now >= new Date(e.showFrom) && now <= new Date(e.showUntil));
}
function renderEventPill() {
  const ev = activeSpecials()[0];
  const pill = $("#event-pill");
  if (!ev) return;
  pill.hidden = false;
  pill.outerHTML = `<a class="event-pill" id="event-pill" href="#info"><b>${esc(ev.title)}</b> · program</a>`;
}
function renderInfo() {
  $("#special-events").innerHTML = activeSpecials().map((ev) => `
    <section class="event-card">
      <p class="eyebrow">Právě se chystá</p>
      <h2>${esc(ev.title)}</h2>
      <p class="ev-sub">${esc(ev.subtitle)}</p>
      ${ev.days.map((d) => `<h4>${esc(d.day)}</h4><ul>${d.items.map(([t, txt, hl]) => `<li class="${hl ? "hl" : ""}"><b>${esc(t)}</b><span>${esc(txt)}</span></li>`).join("")}</ul>`).join("")}
      <p class="ev-note">${esc(ev.note)} <a href="${ev.source}" target="_blank" rel="noopener">Oficiální program ›</a></p>
    </section>`).join("");

  $("#calendar").innerHTML = state.events.recurring.map((e) => `
    <li><div class="c-date">${esc(e.date)}</div><div><div class="c-title">${esc(e.title)}</div><p>${esc(e.text)}</p></div></li>`).join("");

  $("#stages").innerHTML = STAGES.map((s) => {
    const cs = state.chapels.filter((c) => c.n >= s.chapels[0] && c.n <= s.chapels[1]);
    return `<li>
      <div class="st-km">km ${s.from} – ${s.to}</div>
      <div class="st-title">${esc(s.title)}</div>
      <p class="st-text">${esc(s.text)}</p>
      <div class="st-chips">${cs.map((c) => `<button class="${c.status !== "zanikla" ? "stoji" : ""}" data-n="${c.n}" title="${esc(c.name)} – ${STATUS_LABEL[c.status]}">${c.n}</button>`).join("")}</div>
    </li>`;
  }).join("");
  $("#stages").addEventListener("click", (e) => {
    const b = e.target.closest("[data-n]");
    if (b) openChapel(+b.dataset.n);
  });
}
function fillCredits() {
  $$(".credit[data-photo]").forEach((el) => {
    const p = state.photos[el.dataset.photo];
    if (p) el.innerHTML = `Foto: ${esc(p.author)}, <a href="${p.page}" target="_blank" rel="noopener">${esc(p.license)}</a>`;
  });
  $("#photo-credits").innerHTML = Object.entries(state.photos).map(([k, p]) =>
    `<li>${/^\d/.test(k) ? `Kaple č. ${parseInt(k)}` : esc(k)}: ${esc(p.author)} – <a href="${p.page}" target="_blank" rel="noopener">${esc(p.license)}</a></li>`).join("");
}

/* ============ Drobnosti ============ */
let toastT;
function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("is-on");
  clearTimeout(toastT);
  toastT = setTimeout(() => t.classList.remove("is-on"), 3200);
}
function registerSW() {
  const dev = ["localhost", "127.0.0.1"].includes(location.hostname) && !location.search.includes("sw");
  if ("serviceWorker" in navigator && location.protocol !== "file:" && !dev) {
    navigator.serviceWorker.register("sw.js").catch(() => {});
  }
}

init().catch((e) => {
  console.error(e);
  document.body.insertAdjacentHTML("beforeend", `<p style="position:fixed;inset:auto 16px 90px;z-index:2000;background:#7a1f2b;color:#fff;padding:12px 16px;border-radius:12px">Nepodařilo se načíst data. Zkuste stránku obnovit.</p>`);
});
