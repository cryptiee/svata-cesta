"""Vytvoří doporučené varianty trasy: data/routes.json + data/routes/<id>.geojson.

Varianty:
  cela     – celá pěší trasa (kopie data/route.geojson)
  letnany  – od metra C Letňany (pěší napojení přes OSRM) + zbytek hlavní trasy od kaple 14
  vinor    – hlavní trasa od kaple 25 ve Vinoři
  kolo     – cyklotrasa přes vybrané kaple (OSRM, profil bike)
  prosek   – starší svatováclavská cesta z Proseka (OSRM, profil foot)

Délka (km) a seznam kaplí na trase (do 150 m) se počítají z geometrie, celkové stoupání
(elevation, m) z výšek Open-Meteo. Texty, obtížnost (effort 1–3) a „pro koho“ jsou níže v ROUTES.
Souřadnice se zaokrouhlují na 5 desetinných míst. Skript lze pouštět opakovaně;
když OSRM neodpoví, ponechá se dříve uložená geometrie dané varianty.

Spuštění:  python3 tools/build_routes.py
"""
import json, math, pathlib, time, urllib.error, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data/routes"
MAIN = json.loads((ROOT / "data/route.geojson").read_text())
chapels = json.loads((ROOT / "data/chapels.json").read_text())
byN = {c["n"]: c for c in chapels}

OSRM = "https://routing.openstreetmap.de/routed-{profile}/route/v1/driving/{coords}?overview=full&geometries=geojson"
ELEV = "https://api.open-meteo.com/v1/elevation?latitude={lat}&longitude={lon}"
UA = "via-sancta-app/0.1"
R = 6371000.0
NEAR_M = 150

START = (50.09079, 14.437006)          # Poříčská brána (nám. Republiky)
BAZILIKA = (50.194591, 14.67228)       # Bazilika sv. Václava
LETNANY_METRO = (50.1264, 14.5162)


def ch(n):
    return (byN[n]["lat"], byN[n]["lon"])


# ---------- geometrie ----------
def to_xy(lon, lat, lat0):
    return (math.radians(lon) * R * math.cos(math.radians(lat0)), math.radians(lat) * R)


class Line:
    def __init__(self, coords):
        self.coords = coords
        self.lat0 = coords[0][1]
        self.pts = [to_xy(lon, lat, self.lat0) for lon, lat in coords]
        self.cum = [0.0]
        for a, b in zip(self.pts, self.pts[1:]):
            self.cum.append(self.cum[-1] + math.dist(a, b))

    @property
    def length(self):
        return self.cum[-1]

    def project(self, lat, lon):
        """(vzdálenost od trasy, vzdálenost podél trasy, index úseku, t)"""
        p = to_xy(lon, lat, self.lat0)
        best = (float("inf"), 0.0, 0, 0.0)
        for i, (a, b) in enumerate(zip(self.pts, self.pts[1:])):
            dx, dy = b[0] - a[0], b[1] - a[1]
            L2 = dx * dx + dy * dy or 1e-9
            t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
            d = math.dist(p, (a[0] + t * dx, a[1] + t * dy))
            if d < best[0]:
                best = (d, self.cum[i] + t * math.sqrt(L2), i, t)
        return best

    def slice_from(self, lat, lon):
        """Část trasy od bodu nejblíž (lat, lon) do konce."""
        _, _, i, t = self.project(lat, lon)
        (x1, y1), (x2, y2) = self.coords[i], self.coords[i + 1]
        first = [x1 + t * (x2 - x1), y1 + t * (y2 - y1)]
        return [first] + self.coords[i + 1:]


def rnd(coords):
    out = []
    for lon, lat in coords:
        p = [round(lon, 5), round(lat, 5)]
        if not out or out[-1] != p:
            out.append(p)
    return out


def osrm(profile, pts):
    coords = ";".join(f"{lon},{lat}" for lat, lon in pts)
    req = urllib.request.Request(OSRM.format(profile=profile, coords=coords), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.load(r)
    if d.get("code") != "Ok":
        raise RuntimeError(d.get("message", d.get("code")))
    return d["routes"][0]["geometry"]["coordinates"]


def ascent(coords, fallback=None):
    """Celkové stoupání v m: body po ~150 m, výšky z Open-Meteo (DEM 90 m), vyhlazení klouzavým průměrem."""
    line = Line(coords)
    step, targets, i = 150.0, [], 0
    for k in range(int(line.length // step) + 1):
        d = k * step
        while i < len(line.cum) - 2 and line.cum[i + 1] < d:
            i += 1
        seg = (line.cum[i + 1] - line.cum[i]) or 1e-9
        t = max(0.0, min(1.0, (d - line.cum[i]) / seg))
        (x1, y1), (x2, y2) = coords[i], coords[i + 1]
        targets.append((y1 + t * (y2 - y1), x1 + t * (x2 - x1)))
    targets.append((coords[-1][1], coords[-1][0]))
    try:
        elev = []
        for j in range(0, len(targets), 100):
            chunk = targets[j:j + 100]
            url = ELEV.format(lat=",".join(f"{a:.5f}" for a, _ in chunk), lon=",".join(f"{b:.5f}" for _, b in chunk))
            for attempt in range(4):  # Open-Meteo omezuje počet dotazů za minutu
                try:
                    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=60) as r:
                        elev += json.load(r)["elevation"]
                    break
                except urllib.error.HTTPError as e:
                    if e.code != 429 or attempt == 3:
                        raise
                    time.sleep(20)
            time.sleep(1)
    except Exception as e:
        print(f"  výšky se nepodařilo načíst ({e})")
        return fallback
    sm = [sum(elev[max(0, k - 1):k + 2]) / len(elev[max(0, k - 1):k + 2]) for k in range(len(elev))]
    up = sum(max(0.0, b - a) for a, b in zip(sm, sm[1:]))
    return int(round(up / 10) * 10)


def chapels_on(line):
    """Kaple do NEAR_M od trasy, seřazené podél trasy."""
    hits = []
    for c in chapels:
        d, along, _, _ = line.project(c["lat"], c["lon"])
        if d <= NEAR_M:
            hits.append((along, c["n"]))
    ns = [n for _, n in sorted(hits)]
    # zaniklé kaple mají jen přibližnou polohu – leží-li mezi dvěma sousedy na trase, patří k ní také
    on = set(ns)
    gaps = [c["n"] for c in chapels if c["status"] == "zanikla" and c["n"] not in on and {c["n"] - 1, c["n"] + 1} <= on]
    for g in gaps:
        ns.insert(ns.index(g + 1), g)
    return ns


# ---------- varianty ----------
main = MAIN["geometry"]["coordinates"]
main_line = Line(main)


def geom_cela():
    return main


def geom_letnany():
    # pěší napojení od metra na hlavní trasu u kaple 14, pak hlavní trasa
    rest = main_line.slice_from(*ch(14))
    link = osrm("foot", [LETNANY_METRO, (rest[0][1], rest[0][0])])
    return link + rest[1:]


def geom_vinor():
    return main_line.slice_from(*ch(25))


def geom_kolo():
    pts = [START] + [ch(n) for n in (4, 12, 14, 15, 18, 21, 23, 26, 30, 33, 36, 41, 42)] + [BAZILIKA]
    return osrm("bike", pts)


def geom_prosek():
    pts = [
        (50.1181531, 14.494527),   # kostel sv. Václava na Proseku
        (50.135, 14.515),          # jižní okraj Letňan
        (50.1632594, 14.5760577),  # Přezletice
        (50.1777141, 14.6252772),  # Popovice (přímější polní spojení z Přezletic router nezná)
        BAZILIKA,
    ]
    return osrm("foot", pts)


ROUTES = [
    {
        "id": "cela", "short": "Celá cesta", "name": "Celá Svatá cesta", "mode": "pesky", "time": "6–7 h", "difficulty": "náročná",
        "start": {"name": "Poříčská brána (nám. Republiky)", "transport": "metro B Náměstí Republiky"},
        "end": {"name": "Stará Boleslav, baziliky"},
        "text": "Historická trasa v celé délce, se všemi 44 zastaveními. První třetina vede městem přes Karlín, Libeň a Vysočany, kde se kaple většinou nedochovaly. Teprve za Klíčovem začínají pole a vesnice s řadou stojících kaplí. Celodenní pouť pro zdatné chodce.",
        "highlights": ["všech 44 zastavení", "Karlín a Libeň po stopě staré cesty", "nejdelší řada kaplí mezi Vinoří a Brandýsem", "obě baziliky ve Staré Boleslavi"],
        "effort": 3,
        "suitableFor": ["zdatní chodci"],
        "notFor": "Seniorům a rodinám s dětmi doporučujeme rozdělit ji na dva dny: 1. den Praha → Vinoř (asi 15 km), 2. den Vinoř → Stará Boleslav (asi 11 km).",
        "surface": "chodníky a ulice ve městě, pak zpevněná cyklostezka a polní cesty; od Vinoře z velké části podél silnice",
        "breaks": "Obchody a restaurace jsou v Karlíně, Libni, Vysočanech, Kbelích, Vinoři a Brandýse. V polních úsecích nic není, vezměte si s sebou vodu.",
        "bailout": "Pouť můžete ukončit u metra B (Karlín, Libeň), u metra C Letňany, ve Vinoři (autobus PID, vlak Praha-Kbely) nebo v Brandýse (autobusy do Prahy).",
        "build": geom_cela,
    },
    {
        "id": "letnany", "short": "Z Letňan", "name": "Z Letňan polní cestou", "mode": "pesky", "time": "4½–5 h", "difficulty": "střední",
        "start": {"name": "Letňany", "transport": "metro C Letňany"},
        "end": {"name": "Stará Boleslav, baziliky"},
        "text": "Nejhezčí část Svaté cesty, bez městského úvodu. Od Letňan se jde po cyklostezce s alejí, která drží stopu staré cesty, a dál polní krajinou a vesnicemi kolem kaplí 14 až 42.",
        "highlights": ["alej na cyklostezce Letňany – Kbely", "repliky kaplí v Kbelích", "kaple v polích u Vinoře", "Brandýs a přechod přes Labe"],
        "effort": 2,
        "suitableFor": ["běžný chodec", "senioři zvyklí chodit"],
        "notFor": "S kočárkem jen s obtížemi: polní cesty mohou být po dešti blátivé a od Vinoře se jde podél silnice.",
        "surface": "zpevněná cyklostezka s alejí a polní cesty; v závěru podél silnice a brandýskými ulicemi",
        "breaks": "Obchody a hospody v Kbelích, ve Vinoři a v Brandýse; mezi nimi polní úseky bez služeb.",
        "bailout": "Z Kbel, Vinoře, Brandýsa i Staré Boleslavi jezdí do Prahy autobusy PID.",
        "build": geom_letnany,
    },
    {
        "id": "vinor", "short": "Kaple v polích", "name": "Kaple v polích (rodinná)", "mode": "pesky", "time": "3 h", "difficulty": "snadná",
        "start": {"name": "Vinoř, Obergürgentálská kaple (č. 25)", "transport": "autobus PID (zastávka Vinořský zámek)"},
        "end": {"name": "Stará Boleslav, baziliky"},
        "text": "Krátká varianta s nejdelší řadou stojících kaplí: od Vinoře jich potkáte jedenáct. Cesta je rovinatá a nenáročná, zvládnou ji i rodiny s dětmi. Mezi Vinoří a Brandýsem ale vede podél silnice.",
        "highlights": ["11 stojících kaplí za sebou", "nápis Rosa Mystica v kapli č. 26", "rovinatá cesta, vhodná pro děti"],
        "effort": 1,
        "suitableFor": ["senioři", "rodiny s dětmi", "běžný chodec", "kočárky (opatrně)"],
        "notFor": "S kočárkem a malými dětmi opatrně – úseky podél silnice nemají všude chodník.",
        "surface": "téměř rovina; polní a zpevněné cesty, velká část podél silnice",
        "breaks": "Obchody a restaurace jsou ve Vinoři na startu a v Brandýse, mezi nimi jen kaple a pole. Vezměte si vodu a svačinu.",
        "bailout": "Zkrátit můžete v Brandýse, odkud jezdí autobusy PID do Prahy.",
        "build": geom_vinor,
    },
    {
        "id": "kolo", "short": "Cyklopouť", "name": "Cyklopouť", "mode": "kolo", "time": "2–2½ h", "difficulty": "střední",
        "start": {"name": "Poříčská brána (nám. Republiky)", "transport": "metro B Náměstí Republiky"},
        "end": {"name": "Stará Boleslav, bazilika sv. Václava"},
        "text": "Celá Svatá cesta na kole po cyklostezkách a silnicích. Tam, kde se po pěšině jet nedá, vede trasa jinudy. Letňany a Kbely projedete po nové cyklostezce A267. Každý rok 28. 9. pořádá svata-cesta.cz cyklopouť; termín a sraz si ověřte na jejich webu.",
        "highlights": ["cyklostezka A267 Letňany – Kbely", "zastávky u stojících kaplí a replik", "cyklopouť 28. 9. (svata-cesta.cz)"],
        "effort": 2,
        "suitableFor": ["běžní cyklisté", "trekking/gravel kolo", "městské kolo"],
        "notFor": "Na silniční kolo se moc nehodí. Část trasy vede po silnicích s provozem, s dětmi jeďte opatrně.",
        "surface": "městské ulice a cyklostezky, cyklostezka A267 přes Letňany a Kbely, dál silnice a zpevněné cesty",
        "breaks": "Obchody a restaurace v Kbelích, ve Vinoři a v Brandýse.",
        "bailout": "Veřejnou dopravou se můžete vrátit z Letňan, Kbel, Vinoře i Brandýsa. Přepravu kola si ověřte v pravidlech PID.",
        "build": geom_kolo,
    },
    {
        "id": "prosek", "short": "Z Proseka", "name": "Svatováclavská cesta z Proseka", "mode": "pesky", "time": "5–5½ h", "difficulty": "střední",
        "start": {"name": "Kostel sv. Václava na Proseku", "transport": "metro C Prosek"},
        "end": {"name": "Stará Boleslav, bazilika sv. Václava"},
        "text": "Starší, severnější varianta: středověká svatováclavská cesta, jak ji popisuje Miroslav Kuranda. Začíná u kostela sv. Václava na Proseku, jednoho z nejstarších v Praze. Podle tradice stojí v místě, kde roku 938 odpočíval průvod s Václavovým tělem. Barokních kaplí je tu málo, zato je cesta tišší. Vede polními cestami přes Přezletice a Popovice do Brandýsa a potkáte na ní několik křížků.",
        "highlights": ["kostel sv. Václava na Proseku", "polní cesty přes Přezletice a Popovice", "křížky u cesty", "Brandýs a přechod přes Labe"],
        "effort": 2,
        "suitableFor": ["běžný chodec", "kdo hledá ticho"],
        "notFor": "Po cestě je málo služeb a polní cesty mohou být po dešti blátivé. Pro kočárky se nehodí.",
        "surface": "ulice Proseka a Letňan, pak převážně polní a místní cesty přes Přezletice a Popovice; Brandýsem ulicemi",
        "breaks": "Obchody jsou na Proseku, v Letňanech a v Brandýse, v obcích po cestě jen omezeně. Vezměte si vodu.",
        "bailout": "Zkrátit můžete u metra C Letňany nebo v obcích po cestě, kam zajíždějí autobusy PID. Z Brandýsa jezdí autobusy do Prahy.",
        "build": geom_prosek,
    },
]


def main_():
    OUT.mkdir(parents=True, exist_ok=True)
    prev_file = ROOT / "data/routes.json"
    prev = {r["id"]: r for r in json.loads(prev_file.read_text())} if prev_file.exists() else {}
    out = []
    for r in ROUTES:
        path = OUT / f"{r['id']}.geojson"
        try:
            coords = rnd(r["build"]())
        except Exception as e:  # síť / OSRM nedostupné → ponech starou geometrii
            if not path.exists():
                raise
            print(f"{r['id']}: OSRM selhalo ({e}), ponechávám uloženou geometrii")
            coords = json.loads(path.read_text())["geometry"]["coordinates"]
        line = Line(coords)
        feat = {
            "type": "Feature",
            "properties": {"id": r["id"], "name": r["name"], "source": "OSRM (FOSSGIS) nad daty © OpenStreetMap"},
            "geometry": {"type": "LineString", "coordinates": coords},
        }
        path.write_text(json.dumps(feat, ensure_ascii=False, separators=(",", ":")) + "\n")
        entry = {k: v for k, v in r.items() if k != "build"}
        entry["km"] = round(line.length / 1000, 1)
        entry["chapels"] = chapels_on(line)
        entry["file"] = f"data/routes/{r['id']}.geojson"
        # pořadí klíčů pro čitelnost
        entry["elevation"] = ascent(coords, prev.get(r["id"], {}).get("elevation"))
        keys = ["id", "name", "short", "mode", "km", "time", "difficulty", "effort", "elevation", "suitableFor", "notFor",
                "surface", "start", "end", "text", "highlights", "breaks", "bailout", "chapels", "file"]
        out.append({k: entry[k] for k in keys if entry.get(k) is not None})
        print(f"{r['id']:8} {entry['km']:5.1f} km  ↑{entry['elevation']} m  {len(coords):5} bodů  kaple {entry['chapels']}")

    (ROOT / "data/routes.json").write_text(
        "[\n" + ",\n".join(json.dumps(e, ensure_ascii=False) for e in out) + "\n]\n"
    )


if __name__ == "__main__":
    main_()
