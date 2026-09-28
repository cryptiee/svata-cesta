"""Vygeneruje statické HTML stránky pro vyhledávače (SEO) a sdílení.

Aplikace (index.html + js/app.js) přepíná pohledy přes #hash, takže ji vyhledávače vidí
jako jedinou stránku. Tento skript z dat v data/*.json a z textů v index.html vytvoří
samostatné stránky s vlastní adresou, titulkem, popisem, canonical, Open Graph a JSON-LD:

  kaple/                      seznam 44 kaplí      kaple/<n>-<slug>/   detail kaple
  trasy/                      varianty tras        trasy/<id>/         detail trasy
  modlitby/                   všechny modlitby     modlitby/<slug>/    jednotlivé modlitby
  modlitby/loretanska-litanie/                     historie/, info/, svatovaclavska-pout/
  otazky/                     časté otázky (FAQPage)
  404.html, sitemap.xml (s obrázky), robots.txt (vč. AI crawlerů), llms.txt, llms-full.txt

a přepíše blok <!-- build:head --> … <!-- /build:head --> v hlavičce index.html
(titulek, popis, canonical, OG, JSON-LD).

Jediný zdroj textů: historie, praktické informace a úvod litanie se berou z index.html
mezi značkami <!-- build:historie -->, <!-- build:info --> a <!-- build:litanie -->;
úvody přehledů (eyebrow, nadpis, perex) z <header class="page-head"> příslušného pohledu;
úseky cesty (STAGES) z js/app.js.

Všechny odkazy uvnitř stránek jsou RELATIVNÍ (../../css/app.css), takže web funguje
v podadresáři (/svata-cesta/) i v kořeni domény. Absolutní adresy (canonical, og:*,
sitemap) se skládají z SITE_URL. Výjimkou je 404.html – GitHub Pages ho vrací
pro libovolnou adresu, proto má absolutní odkazy.

Skript lze pouštět opakovaně; smaže jen stránky, které sám dřív vytvořil a už neplatí.
Spuštění (po add_km.py a build_routes.py):  python3 tools/build_pages.py
"""
import datetime, html, json, math, pathlib, re, unicodedata

# ---------- nastavení ----------
SITE_URL = "https://poutdoboleslavi.cz/"   # jediné místo, které se mění při stěhování webu (s lomítkem na konci)
SITE_NAME = "Svatá cesta"
SITE_TAGLINE = "Praha → Stará Boleslav"
PUBLISHER_NAME = "Mše v Praze"
PUBLISHER_URL = "https://www.msevpraze.cz/"
PUBLISHER_EMAIL = "info@msevpraze.cz"

ROOT = pathlib.Path(__file__).resolve().parent.parent
TODAY = datetime.date.today()
GENERATED = "<!-- Vygenerováno nástrojem tools/build_pages.py – needitujte ručně, změny se přepíšou. -->"

INDEX = (ROOT / "index.html").read_text()
APPJS = (ROOT / "js/app.js").read_text()
load = lambda p: json.loads((ROOT / p).read_text())
chapels = load("data/chapels.json")
byN = {c["n"]: c for c in chapels}
routes = load("data/routes.json")
prayers = load("data/prayers.json")
events = load("data/events.json")
photos = load("data/photos.json")

STATUS_LABEL = {"stoji": "stojí", "replika": "replika", "zanikla": "zaniklá"}
MODE_LABEL = {"pesky": "pěšky", "kolo": "na kole"}
MSE = "https://www.msevpraze.cz"


# ---------- pomocné funkce ----------
def esc(s):
    return html.escape(str(s if s is not None else ""), quote=True)


def slugify(s):
    """Stejně jako slugify() v js/app.js: bez diakritiky, malá písmena, pomlčky."""
    s = "".join(ch for ch in unicodedata.normalize("NFD", str(s)) if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def chapel_path(c):
    return f"kaple/{c['n']}-{slugify(c['name'])}/"


def prayer_path(p):
    return f"modlitby/{slugify(p['title'])}/"


LITANY_PATH = "modlitby/loretanska-litanie/"


def num(x):
    """Číslo jako v JS String(x) s desetinnou čárkou (15.6 → 15,6; 26.0 → 26)."""
    return ("%g" % x).replace(".", ",")


def fmt_km(x):
    return f"{x:.1f}".replace(".", ",") + " km"


def clip(s, n=160):
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) <= n:
        return s
    cut = s[: n - 1].rsplit(" ", 1)[0].rstrip(",;:–-")
    return cut + "…"


def first_fit(cands, n=160):
    for c in cands:
        if len(c) <= n:
            return c
    return clip(cands[-1], n)


def haversine(a, b):
    R = 6371000.0
    dlat, dlon = math.radians(b[0] - a[0]), math.radians(b[1] - a[1])
    h = math.sin(dlat / 2) ** 2 + math.cos(math.radians(a[0])) * math.cos(math.radians(b[0])) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def jpeg_size(path):
    """(šířka, výška) z hlavičky JPEG – bez knihoven."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        m = data[i + 1]
        if m in (0xD8, 0x01, 0xFF) or 0xD0 <= m <= 0xD7:
            i += 2 if m != 0xFF else 1
            continue
        L = int.from_bytes(data[i + 2:i + 4], "big")
        if m in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            return int.from_bytes(data[i + 7:i + 9], "big"), int.from_bytes(data[i + 5:i + 7], "big")
        i += 2 + L
    return None


def img_size(src):
    return jpeg_size(ROOT / src) or (900, 675)


def credit_html(p):
    return f'Foto: {esc(p["author"])}, <a href="{esc(p["page"])}" target="_blank" rel="noopener">{esc(p["license"])}</a>'


# ---------- texty z index.html a app.js ----------
def block(name):
    m = re.search(r"<!-- build:%s -->\n?(.*?)[ \t]*<!-- /build:%s -->" % (name, name), INDEX, re.S)
    if not m:
        raise SystemExit(f"index.html: chybí značky <!-- build:{name} --> … <!-- /build:{name} -->")
    return m.group(1)


def view_head(view):
    """eyebrow, nadpis a perex z <header class="page-head"> pohledu #view-<view>."""
    sec = re.search(r'<section id="view-%s".*?<header class="page-head">(.*?)</header>' % view, INDEX, re.S).group(1)
    get = lambda pat: (m.group(1).strip() if (m := re.search(pat, sec, re.S)) else "")
    return {"eyebrow": get(r'<p class="eyebrow">(.*?)</p>'), "title": get(r"<h2>(.*?)</h2>"),
            "lead": get(r'<p class="lead"[^>]*>(.*?)</p>')}


def js_const(name):
    """Pole z js/app.js (const NAME = [...];) převedené na JSON; None, když se nepovede."""
    m = re.search(r"const %s = (\[.*?\n\]);" % name, APPJS, re.S)
    if not m:
        return None
    txt = re.sub(r'([{,]\s*)([A-Za-z_]\w*)\s*:', r'\1"\2":', m.group(1))
    txt = re.sub(r",\s*([\]}])", r"\1", txt)
    try:
        return json.loads(txt)
    except ValueError:
        print(f"  varování: {name} z js/app.js se nepodařilo přečíst")
        return None


STAGES = js_const("STAGES")
HEAD_LINES = [l.strip() for l in INDEX.splitlines() if "fonts.googleapis.com" in l or "fonts.gstatic.com" in l]
THEME_LINES = [l.strip() for l in INDEX.splitlines() if 'name="theme-color"' in l]
SPRITE = re.search(r'<svg width="0" height="0".*?\n</svg>', INDEX, re.S).group(0)
TABS = re.findall(r'<a href="#(\w+)" data-view="\w+"><svg viewBox="0 0 24 24"><use href="#(i-[\w-]+)"/></svg><span>(.*?)</span></a>', INDEX)
TAB_PATH = {"mapa": "", "trasy": "trasy/", "kaple": "kaple/", "modlitby": "modlitby/", "historie": "historie/", "info": "info/"}


def relink(frag, prefix, extra=None):
    """Přepíše relativní odkazy fragmentu z index.html pro stránku v podadresáři."""
    hashes = {k: prefix + v for k, v in TAB_PATH.items()}
    hashes.update(extra or {})

    def fix(m):
        attr, q, url = m.groups()
        if url.startswith("#"):
            new = hashes.get(url[1:], url)
        elif re.match(r"^([a-z][a-z0-9+.-]*:|//|/)", url):
            new = url
        else:
            new = prefix + url
        return f"{attr}={q}{new}{q}"
    frag = re.sub(r'\b(href|src)=(["\'])(.*?)\2', fix, frag)
    # nadpisy h3 → h2 (na statické stránce je h1 nadpis stránky)
    frag = re.sub(r"<h3(\s[^>]*)?>", lambda m: f'<h2 class="sp-h"{m.group(1) or ""}>', frag).replace("</h3>", "</h2>")
    # autoři fotek
    frag = re.sub(r'<span class="credit" data-photo="([^"]+)"></span>',
                  lambda m: f'<span class="credit">{credit_html(photos[m.group(1)])}</span>' if m.group(1) in photos else "", frag)
    return frag


def active_specials():
    now = datetime.datetime.now(datetime.timezone.utc)
    out = []
    for e in events.get("special", []):
        a = datetime.datetime.fromisoformat(e["showFrom"])
        b = datetime.datetime.fromisoformat(e["showUntil"])
        a = a if a.tzinfo else a.replace(tzinfo=datetime.timezone.utc)
        b = b if b.tzinfo else b.replace(tzinfo=datetime.timezone.utc)
        if a <= now <= b:
            out.append(e)
    return out


# ---------- JSON-LD ----------
ORG_ID = PUBLISHER_URL + "#organization"
ORG = {"@type": "Organization", "@id": ORG_ID, "name": PUBLISHER_NAME, "url": PUBLISHER_URL, "email": PUBLISHER_EMAIL,
       "logo": SITE_URL + "icons/icon-512.png"}
EN_NAME = "Holy Way (Via Sancta) from Prague to Stará Boleslav"
WEBSITE = {"@type": "WebSite", "@id": SITE_URL + "#website", "url": SITE_URL, "name": SITE_NAME,
           "alternateName": [f"{SITE_NAME} {SITE_TAGLINE}", "Pouť do Staré Boleslavi", "Via Sancta", EN_NAME],
           "inLanguage": "cs", "publisher": {"@id": ORG_ID}}
TRAIL = {"@type": "Place", "name": "Svatá cesta z Prahy do Staré Boleslavi", "alternateName": ["Via Sancta", EN_NAME], "url": SITE_URL}
ROBOTS_META = '<meta name="robots" content="index, follow, max-image-preview:large, max-snippet:-1, max-video-preview:-1">'


def ld_script(items):
    data = {"@context": "https://schema.org", "@graph": items}
    txt = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return f'<script type="application/ld+json">{txt}</script>'


def breadcrumb_ld(crumbs):
    return {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "name": name, "item": SITE_URL + path}
        for i, (name, path) in enumerate(crumbs)]}


def chapel_ld_ref(c):
    return {"@type": "Place" if c["status"] == "zanikla" else "TouristAttraction",
            "name": f"{c['n']}. {c['name']}", "url": SITE_URL + chapel_path(c)}


# ---------- šablona stránky ----------
OG_DEFAULT = ("img/og.jpg", "Svatá cesta z Prahy do Staré Boleslavi")


def head_meta(title, desc, url, og_img, og_alt, og_type="website"):
    w, h = img_size(og_img)
    abs_img = SITE_URL + og_img
    return "\n".join([
        f"<title>{esc(title)}</title>",
        f'<meta name="description" content="{esc(desc)}">',
        f'<link rel="canonical" href="{esc(url)}">',
        ROBOTS_META,
        f'<meta property="og:type" content="{og_type}">',
        f'<meta property="og:site_name" content="{SITE_NAME}">',
        '<meta property="og:locale" content="cs_CZ">',
        f'<meta property="og:title" content="{esc(title)}">',
        f'<meta property="og:description" content="{esc(desc)}">',
        f'<meta property="og:url" content="{esc(url)}">',
        f'<meta property="og:image" content="{esc(abs_img)}">',
        f'<meta property="og:image:width" content="{w}">',
        f'<meta property="og:image:height" content="{h}">',
        f'<meta property="og:image:alt" content="{esc(og_alt)}">',
        '<meta name="twitter:card" content="summary_large_image">',
        f'<meta name="twitter:title" content="{esc(title)}">',
        f'<meta name="twitter:description" content="{esc(desc)}">',
        f'<meta name="twitter:image" content="{esc(abs_img)}">',
    ])


def crumbs_html(crumbs, prefix):
    items = []
    for i, (name, path) in enumerate(crumbs):
        if i == len(crumbs) - 1:
            items.append(f'<li><span aria-current="page">{esc(name)}</span></li>')
        else:
            items.append(f'<li><a href="{prefix}{path}">{esc(name)}</a></li>')
    return f'<nav class="crumbs" aria-label="Drobečková navigace"><ol>{"".join(items)}</ol></nav>'


def hub_links(prefix):
    links = [("kaple/", "Kaple"), ("trasy/", "Trasy"), ("modlitby/", "Modlitby"), (LITANY_PATH, "Loretánská litanie"),
             ("historie/", "Historie"), ("info/", "Praktické informace"), ("otazky/", "Časté otázky"),
             ("svatovaclavska-pout/", "Svatováclavská pouť")]
    return "".join(f'<li><a href="{prefix}{p}">{t}</a></li>' for p, t in links)


def render(path, *, title, desc, body, section=None, crumbs=None, ld=(), og_img=None, og_alt=None,
           og_type="website", absolute=False, noindex=False, script="", extra_meta=""):
    """Složí celou stránku. path = '' | 'kaple/' | 'kaple/26-…/' | '404.html'."""
    depth = path.count("/")
    prefix = SITE_URL if absolute else "../" * depth
    url = SITE_URL + path
    og_img, og_alt = og_img or OG_DEFAULT[0], og_alt or OG_DEFAULT[1]
    crumbs = crumbs or []
    graph = list(ld) + ([breadcrumb_ld(crumbs)] if crumbs else [])
    on = ' class="is-on"'
    topnav = "".join(f'<a href="{prefix}{TAB_PATH[v]}"{on if v == section else ""}>{esc(label)}</a>' for v, _, label in TABS)
    tabbar = "".join(
        f'<a href="{prefix}{TAB_PATH[v]}"{on if v == section else ""}>'
        f'<svg viewBox="0 0 24 24" aria-hidden="true"><use href="#{icon}"/></svg><span>{esc(label)}</span></a>'
        for v, icon, label in TABS)
    meta = head_meta(title, desc, url, og_img, og_alt, og_type)
    if noindex:
        meta = "\n".join(l for l in meta.splitlines() if 'rel="canonical"' not in l and "og:url" not in l and l != ROBOTS_META)
        meta += '\n<meta name="robots" content="noindex">'
    if extra_meta:
        meta += "\n" + extra_meta
    doc = f"""<!doctype html>
<html lang="cs">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
{meta}
{chr(10).join(THEME_LINES)}
<link rel="manifest" href="{prefix}manifest.webmanifest">
<link rel="icon" href="{prefix}icons/icon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="{prefix}icons/apple-touch-icon.png">
{chr(10).join(HEAD_LINES)}
<link rel="stylesheet" href="{prefix}css/app.css">
{ld_script(graph) if graph else ""}
</head>
<body class="sp">
{GENERATED}
<header class="topbar">
  <a href="{prefix}" class="brand" aria-label="Svatá cesta – interaktivní mapa">
    <svg class="brand-mark" viewBox="0 0 32 32" aria-hidden="true"><use href="#i-chapel"/></svg>
    <span class="brand-text">
      <strong>{SITE_NAME}</strong>
      <small>{SITE_TAGLINE}</small>
    </span>
  </a>
  <nav class="topnav" aria-label="Hlavní navigace">{topnav}</nav>
</header>

<main>
<div class="view-page">
{body}
<footer class="page sp-foot">
  <nav aria-label="Stránky průvodce"><ul>{hub_links(prefix)}</ul></nav>
  <p class="small">Svatá cesta je nekomerční vedlejší projekt webu <a href="{PUBLISHER_URL}">{PUBLISHER_NAME}</a>. Našli jste chybu, nebo znáte něco, co by tu nemělo chybět? Napište na <a href="mailto:{PUBLISHER_EMAIL}">{PUBLISHER_EMAIL}</a>.</p>
</footer>
</div>
</main>

<nav class="tabbar" aria-label="Navigace">{tabbar}</nav>

{SPRITE}
{script}
</body>
</html>
"""
    # drobečková navigace patří do .page – vloží se na začátek prvního .page v těle
    if crumbs:
        nav = crumbs_html(crumbs, prefix)
        doc = re.sub(r'(<(?:div|article) class="page[^"]*">)', lambda m: m.group(1) + "\n" + nav, doc, count=1)
    out = ROOT / (path if path.endswith(".html") else path + "index.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    if not out.exists() or out.read_text() != doc:
        out.write_text(doc)
        CHANGED.add(path)
    imgs = [og_img] if og_img != OG_DEFAULT[0] else []
    imgs += re.findall(r'<img [^>]*src="(?:\.\./)*(img/[^"]+)"', body)
    IMAGES[path] = list(dict.fromkeys(imgs))
    WRITTEN.append((path, title, desc))
    return doc


WRITTEN = []
CHANGED = set()   # stránky, jejichž obsah se tímto buildem změnil → nové <lastmod>
IMAGES = {}       # obrázky stránky pro image sitemap


# ---------- společné kousky ----------
def status_label(c):
    return "stojí (přenesená)" if c.get("moved") else "stojí (sporná)" if c.get("disputed") else STATUS_LABEL[c["status"]]


def chapel_row(c, prefix, side=None):
    """Řádek seznamu kaplí – stejné třídy jako v aplikaci (renderList)."""
    ph = photos.get(c.get("photo") or "")
    thumb = (f'<img class="thumb" src="{prefix}{ph["src"]}" alt="" width="64" height="64" loading="lazy">'
             if ph else f'<span class="thumb">{c["n"]}</span>')
    side = side if side is not None else f'km {num(c["km"])}'
    return (f'<li><a class="chapel-row{" is-lost" if c["status"] == "zanikla" else ""}" href="{prefix}{chapel_path(c)}">'
            f'{thumb}<span class="row-main"><span class="row-title"><span class="row-num">{c["n"]}.</span>{esc(c["name"])}</span>'
            f'<span class="row-meta"><span class="badge badge-{c["status"]}">{STATUS_LABEL[c["status"]]}</span>{esc(c["area"])}</span></span>'
            f'<span class="row-side"><div>{esc(side)}</div></span></a></li>')


def mapy_url(c):
    return f'https://mapy.cz/turisticka?q={c["lat"]},{c["lon"]}&x={c["lon"]}&y={c["lat"]}&z=17'


def gmaps_url(c):
    return f'https://www.google.com/maps/dir/?api=1&destination={c["lat"]},{c["lon"]}&travelmode=walking'


# náčrtky tras – všechny ve stejném výřezu (jako sketchSVG v app.js)
ROUTE_GEO = {r["id"]: load(r["file"])["geometry"]["coordinates"] for r in routes}
_all = [p for cs in ROUTE_GEO.values() for p in cs]
BOX = (min(p[0] for p in _all), max(p[0] for p in _all), min(p[1] for p in _all), max(p[1] for p in _all))


def sketch(rid, W=96, H=64, pad=7, maxpts=90, cls="rc-sketch", dots=False, label=None):
    minLon, maxLon, minLat, maxLat = BOX
    kx = math.cos(math.radians((minLat + maxLat) / 2))
    s = min((W - 2 * pad) / ((maxLon - minLon) * kx), (H - 2 * pad) / (maxLat - minLat))
    ox, oy = (W - (maxLon - minLon) * kx * s) / 2, (H - (maxLat - minLat) * s) / 2
    xy = lambda lon, lat: (ox + (lon - minLon) * kx * s, oy + (maxLat - lat) * s)

    def path(cs):
        step = max(1, math.ceil(len(cs) / maxpts))
        pts = [p for i, p in enumerate(cs) if i % step == 0 or i == len(cs) - 1]
        return "".join(f'{"L" if i else "M"}{x:.1f} {y:.1f}' for i, (x, y) in enumerate(xy(*p) for p in pts))
    c = ROUTE_GEO[rid]
    (ax, ay), (bx, by) = xy(*c[0]), xy(*c[-1])
    r = 3 if W < 200 else 5
    out = [f'<svg class="{cls}" viewBox="0 0 {W} {H}"' + (f' role="img" aria-label="{esc(label)}">' if label else ' aria-hidden="true">')]
    if rid != "cela":
        out.append(f'<path class="rc-base" d="{path(ROUTE_GEO["cela"])}"/>')
    out.append(f'<path class="rc-line" d="{path(c)}"/>')
    if dots:
        route = next(x for x in routes if x["id"] == rid)
        for n in route["chapels"]:
            ch = byN[n]
            x, y = xy(ch["lon"], ch["lat"])
            out.append(f'<circle class="{"sp-dot-lost" if ch["status"] == "zanikla" else "sp-dot"}" cx="{x:.1f}" cy="{y:.1f}" r="2.4"/>')
    out.append(f'<circle class="rc-a" cx="{ax:.1f}" cy="{ay:.1f}" r="{r}"/><circle class="rc-b" cx="{bx:.1f}" cy="{by:.1f}" r="{r}"/></svg>')
    return "".join(out)


# ---------- kaple ----------
def chapel_desc(c):
    cs = prayers["litany"][c["n"] - 1][1]
    st = {"stoji": "Kaple stojí.", "replika": "Stojí replika kaple.", "zanikla": "Kaple se nedochovala."}[c["status"]]
    base = f'{c["name"]}: {c["n"]}. zastavení Svaté cesty z Prahy do Staré Boleslavi ({c["area"]}, km {num(c["km"])}). {st}'
    return first_fit([f"{base} Invokace „{cs}“, poutní místo {c['place']}.", f"{base} Invokace „{cs}“.", base])


def chapel_page(c):
    n, path, prefix = c["n"], chapel_path(c), "../../"
    la, cs = prayers["litany"][n - 1]
    ph = photos.get(c.get("photo") or "")
    lost = c["status"] == "zanikla"
    if ph:
        w, h = img_size(ph["src"])
        photo = (f'<div class="d-photo"><img src="{prefix}{ph["src"]}" alt="{esc(c["name"])} – {n}. zastavení Svaté cesty" width="{w}" height="{h}">'
                 f'<div class="credit-overlay">{credit_html(ph)}</div></div>')
    else:
        txt = (f'Kaple se nedochovala.{" Přesné místo neznáme, poloha na&nbsp;mapě je jen odhad." if c.get("approx") else " Na&nbsp;mapě je vyznačeno její pravděpodobné místo."} I&nbsp;tady se můžete zastavit a&nbsp;pomodlit.'
               if lost else "Fotografie zatím chybí.")
        photo = f'<div class="d-nophoto"><svg viewBox="0 0 32 32" aria-hidden="true"><use href="#i-chapel"/></svg><span>{txt}</span></div>'
    p2 = photos.get(c.get("photo2") or "")
    photo2 = ""
    if p2:
        w, h = img_size(p2["src"])
        photo2 = (f'<figure class="d-photo2"><img src="{prefix}{p2["src"]}" alt="{esc(c["name"])} – detail" width="{w}" height="{h}" loading="lazy" style="height:auto">'
                  f'<figcaption>{credit_html(p2)}</figcaption></figure>')
    church = (f'<a class="d-church" href="{esc(c["church"]["url"])}" target="_blank" rel="noopener"><span class="dc-label">Originál najdete v Praze</span>'
              f'<span class="dc-name">{esc(c["church"]["name"])}</span><span class="dc-cta">Časy mší na msevpraze.cz ›</span></a>') if c.get("church") else ""
    on_routes = [r for r in routes if n in r["chapels"]]
    routes_html = ""
    if on_routes:
        routes_html = ('<h2 class="sp-h">Trasy, které vedou kolem kaple</h2><ul class="links">' +
                       "".join(f'<li><a href="{prefix}trasy/{r["id"]}/">{esc(r["name"])}</a> – {fmt_km(r["km"])}, {esc(r["time"])}, {MODE_LABEL[r["mode"]]}</li>' for r in on_routes) +
                       "</ul>")
    near = sorted((x for x in chapels if abs(x["n"] - n) > 1), key=lambda x: haversine((c["lat"], c["lon"]), (x["lat"], x["lon"])))[:3]
    near_html = ('<h2 class="sp-h">Další kaple v&nbsp;okolí</h2><ol class="chapel-list">' +
                 "".join(chapel_row(x, prefix, f'{fmt_km(haversine((c["lat"], c["lon"]), (x["lat"], x["lon"])) / 1000)} vzdušnou čarou') for x in near) + "</ol>")
    prev, nxt = byN.get(n - 1), byN.get(n + 1)
    pager = ((f'<a href="{prefix}{chapel_path(prev)}" rel="prev"><svg viewBox="0 0 24 24" aria-hidden="true"><use href="#i-prev"/></svg><span>předchozí<b>{prev["n"]}. {esc(prev["name"])}</b></span></a>' if prev else "<span></span>") +
             (f'<a href="{prefix}{chapel_path(nxt)}" rel="next"><span>další<b>{nxt["n"]}. {esc(nxt["name"])}</b></span><svg viewBox="0 0 24 24" aria-hidden="true"><use href="#i-next"/></svg></a>' if nxt else ""))
    body = f"""<article class="page sp-detail">
{photo}
<div class="d-head">
  <div class="d-num">{n}. zastavení</div>
  <h1>{esc(c["name"])}</h1>
  <div class="d-tags"><span class="badge badge-{c["status"]}">{status_label(c)}</span><span>{esc(c["area"])} · km {num(c["km"])}</span></div>
</div>
<div class="invocation">
  <div class="inv-la" lang="la">{esc(la)}</div>
  <div class="inv-cs">{esc(cs)}</div>
  <div class="inv-resp">– oroduj za nás</div>
  <div class="inv-hint">{n}. invokace <a href="{prefix}{LITANY_PATH}">loretánské litanie</a> · Zdrávas Maria…</div>
</div>
<div class="d-actions">
  <a class="btn btn-primary" href="{prefix}#k{n}"><svg viewBox="0 0 24 24" aria-hidden="true"><use href="#i-map"/></svg>Otevřít na mapě</a>
  <a class="btn btn-ghost" href="{esc(mapy_url(c))}" target="_blank" rel="noopener"><svg viewBox="0 0 24 24" aria-hidden="true"><use href="#i-nav"/></svg>Navigovat</a>
</div>
<div class="d-section"><p>{esc(c["text"])}</p></div>
{photo2}
<dl class="d-facts">
  <div><dt>Poutní místo</dt><dd>{esc(c["place"])}</dd></div>
  <div><dt>Mariánský obraz</dt><dd>{esc(c["image"])}</dd></div>
  <div><dt>Donátor</dt><dd>{esc(c["donor"])}</dd></div>
</dl>
{church}
<div class="d-links">
  <a href="{esc(mapy_url(c))}" target="_blank" rel="noopener">Mapy.cz</a>
  <a href="{esc(gmaps_url(c))}" target="_blank" rel="noopener">Google Maps</a>
  <a href="{prefix}#k{n}">Otevřít v&nbsp;interaktivní mapě</a>
</div>
{routes_html}
{near_html}
<nav class="d-pager" aria-label="Předchozí a další kaple">{pager}</nav>
</article>"""
    desc = chapel_desc(c)
    url = SITE_URL + path
    ent = {"@type": "Place" if lost else "TouristAttraction", "@id": url + "#place", "name": c["name"],
           "alternateName": f"{n}. zastavení Svaté cesty", "description": desc, "url": url,
           "geo": {"@type": "GeoCoordinates", "latitude": c["lat"], "longitude": c["lon"]},
           "address": {"@type": "PostalAddress", "addressLocality": c["area"], "addressCountry": "CZ"},
           "containedInPlace": TRAIL, "hasMap": mapy_url(c)}
    if ph:
        ent["image"] = SITE_URL + ph["src"]
    if not lost:
        ent["isAccessibleForFree"] = True
    title = f'{c["name"]} ({n}. zastavení) – Svatá cesta Praha → Stará Boleslav'
    geo = (f'<meta name="geo.region" content="CZ">\n<meta name="geo.placename" content="{esc(c["area"])}">\n'
           f'<meta name="geo.position" content="{c["lat"]};{c["lon"]}">\n<meta name="ICBM" content="{c["lat"]}, {c["lon"]}">')
    render(path, title=title, desc=desc, body=body, section="kaple",
           crumbs=[("Svatá cesta", ""), ("Kaple", "kaple/"), (f'{n}. {c["name"]}', path)],
           ld=[ent], og_img=ph["src"] if ph else None, og_alt=c["name"] if ph else None, extra_meta=geo)


def chapels_hub():
    prefix, vh = "../", view_head("kaple")
    cnt = {k: sum(1 for c in chapels if c["status"] == k) for k in STATUS_LABEL}
    groups = []
    if STAGES:
        for s in STAGES:
            cs = [c for c in chapels if s["chapels"][0] <= c["n"] <= s["chapels"][1]]
            groups.append((f'{s["title"]}', f'km {num(s["from"])} – {num(s["to"])} · kaple {s["chapels"][0]}–{s["chapels"][1]}', cs))
    else:  # záloha: po sobě jdoucí oblasti
        for c in chapels:
            if not groups or groups[-1][0] != c["area"]:
                groups.append((c["area"], "", []))
            groups[-1][2].append(c)
    sections = "".join(
        f'<section><h2 class="sp-h">{esc(t)}</h2>{"<p class=small>" + esc(sub) + "</p>" if sub else ""}'
        f'<ol class="chapel-list">{"".join(chapel_row(c, prefix) for c in cs)}</ol></section>' for t, sub, cs in groups)
    body = f"""<div class="page">
<header class="page-head">
  <p class="eyebrow">{vh["eyebrow"]}</p>
  <h1>{vh["title"]}</h1>
  <p class="lead">{vh["lead"]}</p>
</header>
<div class="facts">
  <div><strong>{cnt["stoji"]}</strong><span>stojících kaplí</span></div>
  <div><strong>{cnt["replika"]}</strong><span>replik</span></div>
  <div><strong>{cnt["zanikla"]}</strong><span>zaniklých kaplí</span></div>
</div>
<div class="sp-lead-actions" style="margin-top:14px"><a class="btn btn-primary" href="{prefix}#kaple"><svg viewBox="0 0 24 24" aria-hidden="true"><use href="#i-map"/></svg>Otevřít interaktivní mapu</a></div>
{sections}
</div>"""
    desc = (f"Všech 44 barokních kaplí Svaté cesty z Prahy do Staré Boleslavi: {cnt['stoji']} stojících, {cnt['replika']} replik "
            f"a {cnt['zanikla']} zaniklých. Poloha, historie, invokace litanie.")
    items = {"@type": "ItemList", "name": "Kaple Svaté cesty", "numberOfItems": len(chapels), "itemListElement": [
        {"@type": "ListItem", "position": c["n"], "url": SITE_URL + chapel_path(c), "name": f'{c["n"]}. {c["name"]}'} for c in chapels]}
    render("kaple/", title="Kaple Svaté cesty – všech 44 zastavení z Prahy do Staré Boleslavi", desc=clip(desc), body=body,
           section="kaple", crumbs=[("Svatá cesta", ""), ("Kaple", "kaple/")], ld=[WEBSITE, ORG, items])


# ---------- trasy ----------
def route_desc(r):
    return first_fit([
        f'{r["name"]}: {fmt_km(r["km"])}, {r["time"]}, {MODE_LABEL[r["mode"]]}, obtížnost {r["difficulty"]}. '
        f'Start {r["start"]["name"]}, cíl {r["end"]["name"]}. {len(r["chapels"])} zastavení Svaté cesty.',
        f'{r["name"]}: {fmt_km(r["km"])}, {r["time"]}, {MODE_LABEL[r["mode"]]}, obtížnost {r["difficulty"]}. '
        f'{len(r["chapels"])} zastavení Svaté cesty do Staré Boleslavi.',
        f'{r["name"]}: {fmt_km(r["km"])}, {r["time"]}, {MODE_LABEL[r["mode"]]}. Trasa Svaté cesty do Staré Boleslavi.'])


def route_stats(r):
    return (f'<div class="rc-stats"><span><b>{fmt_km(r["km"])}</b></span><span>{esc(r["time"])}</span>'
            + (f'<span title="celkové stoupání">↑ {r["elevation"]} m</span>' if r.get("elevation") is not None else "") + "</div>"
            + (f'<p class="rc-surface">{esc(r["surface"])}</p>' if r.get("surface") else "")
            + '<div class="rc-for"><span class="rc-for-label">Pro koho</span>'
            + "".join(f'<span class="rc-tag">{esc(t)}</span>' for t in r.get("suitableFor", [])) + "</div>")


def route_meta(r):
    return (f'<div class="row-meta"><span class="badge badge-{r["mode"]}">{MODE_LABEL[r["mode"]]}</span>'
            f'<span class="rc-effort effort-{r["effort"]}" title="obtížnost {r["effort"]} ze 3"><i></i><i></i><i></i>{esc(r["difficulty"])}</span></div>')


def standing_text(k):
    if k == 1:
        return "1 stojící kaple či replika"
    if 2 <= k <= 4:
        return f"{k} stojící kaple a&nbsp;repliky"
    return f"{k} stojících kaplí a&nbsp;replik"


def route_where(r, prefix):
    standing = sum(1 for n in r["chapels"] if byN[n]["status"] != "zanikla")
    mass = (f' · <a href="{MSE}/kostely/sv-petra-na-porici" target="_blank" rel="noopener">mše u sv. Petra na Poříčí</a>'
            if r["id"] in ("cela", "kolo") else "")
    return (f'<dl class="rc-where"><div><dt>Start</dt><dd>{esc(r["start"]["name"])} · {esc(r["start"]["transport"])}{mass}</dd></div>'
            f'<div><dt>Cíl</dt><dd>{esc(r["end"]["name"])}</dd></div>'
            f'<div><dt>Kaple</dt><dd>{len(r["chapels"])} zastavení, z&nbsp;toho {standing_text(standing)}</dd></div></dl>')


def route_practical(r):
    rows = [("Pozor", r.get("notFor")), ("Občerstvení", r.get("breaks")), ("Zkrácení", r.get("bailout"))]
    return "".join(f"<div><dt>{t}</dt><dd>{esc(v)}</dd></div>" for t, v in rows if v)


def trip_ld(r, with_id=True):
    url = SITE_URL + f'trasy/{r["id"]}/'
    d = {"@type": "TouristTrip", "name": r["name"], "url": url, "description": route_desc(r),
         "touristType": r.get("suitableFor", []), "tripOrigin": {"@type": "Place", "name": r["start"]["name"]},
         "itinerary": {"@type": "ItemList", "numberOfItems": len(r["chapels"]), "itemListElement": [
             {"@type": "ListItem", "position": i + 1, "item": chapel_ld_ref(byN[n])} for i, n in enumerate(r["chapels"])]}}
    if with_id:
        d["@id"] = url + "#trip"
    return d


def route_page(r):
    path, prefix = f'trasy/{r["id"]}/', "../../"
    chapel_side = (lambda c: f'km {num(c["km"])}') if r["id"] == "cela" else (lambda c: "")
    others = [x for x in routes if x["id"] != r["id"]]
    body = f"""<article class="page">
<header class="page-head">
  <p class="eyebrow">Trasa · {MODE_LABEL[r["mode"]]}</p>
  <h1>{esc(r["name"])}</h1>
  {route_meta(r)}
</header>
{sketch(r["id"], 300, 200, 14, 300, "rc-sketch sp-sketch", True, f'Náčrt trasy {r["name"]}: start {r["start"]["name"]}, cíl {r["end"]["name"]}; tečky označují kaple')}
{route_stats(r)}
<p class="rc-text">{esc(r["text"])}</p>
<ul class="rc-hl">{"".join(f"<li>{esc(h)}</li>" for h in r["highlights"])}</ul>
{route_where(r, prefix)}
<div class="sp-lead-actions"><a class="btn btn-primary" href="{prefix}#trasa-{r["id"]}"><svg viewBox="0 0 24 24" aria-hidden="true"><use href="#i-map"/></svg>Otevřít trasu v mapě</a></div>
<h2 class="sp-h">Praktické</h2>
<dl class="d-facts">{route_practical(r)}</dl>
<h2 class="sp-h">Kaple na trase ({len(r["chapels"])})</h2>
<ol class="chapel-list">{"".join(chapel_row(byN[n], prefix, chapel_side(byN[n])) for n in r["chapels"])}</ol>
<h2 class="sp-h">Další trasy</h2>
<ul class="links">{"".join(f'<li><a href="{prefix}trasy/{x["id"]}/">{esc(x["name"])}</a> – {fmt_km(x["km"])}, {esc(x["time"])}</li>' for x in others)}</ul>
</article>"""
    render(path, title=f'{r["name"]} ({fmt_km(r["km"])}) – trasa Svaté cesty do Staré Boleslavi', desc=route_desc(r),
           body=body, section="trasy", crumbs=[("Svatá cesta", ""), ("Trasy", "trasy/"), (r["name"], path)], ld=[trip_ld(r)])


def routes_hub():
    prefix, vh = "../", view_head("trasy")
    cards = []
    for r in routes:
        cards.append(f"""<li><article class="route-card">
  <div class="rc-head">{sketch(r["id"])}<div class="row-main"><h2 class="rc-title"><a href="{r["id"]}/">{esc(r["name"])}</a></h2>{route_meta(r)}</div></div>
  {route_stats(r)}
  <p class="rc-text">{esc(r["text"])}</p>
  <ul class="rc-hl">{"".join(f"<li>{esc(h)}</li>" for h in r["highlights"])}</ul>
  {route_where(r, prefix)}
  <details class="rc-more"><summary>Praktické</summary><dl>{route_practical(r)}</dl></details>
  <div class="rc-actions">
    <a class="btn btn-primary" href="{prefix}#trasa-{r["id"]}"><svg viewBox="0 0 24 24" aria-hidden="true"><use href="#i-map"/></svg>Zobrazit na mapě</a>
    <a class="btn btn-ghost" href="{r["id"]}/">Podrobnosti a kaple</a>
  </div>
</article></li>""")
    body = f"""<div class="page">
<header class="page-head">
  <p class="eyebrow">{vh["eyebrow"]}</p>
  <h1>{vh["title"]}</h1>
  <p class="lead">{vh["lead"]}</p>
</header>
<ol class="route-list">{"".join(cards)}</ol>
</div>"""
    lst = {"@type": "ItemList", "name": "Trasy Svaté cesty", "numberOfItems": len(routes), "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "item": trip_ld(r, False)} for i, r in enumerate(routes)]}
    kms = sorted(r["km"] for r in routes)
    desc = (f'{len(routes)} tras po Svaté cestě z Prahy do Staré Boleslavi pěšky i na kole, od {fmt_km(kms[0])} do {fmt_km(kms[-1])}: '
            ', '.join(r["short"][:1].lower() + r["short"][1:] for r in routes[1:]) + '.')
    render("trasy/", title="Trasy Svaté cesty – pěšky i na kole z Prahy do Staré Boleslavi", desc=clip(desc), body=body,
           section="trasy", crumbs=[("Svatá cesta", ""), ("Trasy", "trasy/")], ld=[WEBSITE, ORG, lst])


# ---------- modlitby ----------
def litany_items(prefix):
    return "".join(
        f'<li><a href="{prefix}{chapel_path(byN[i + 1])}">{esc(cs)} <em>– oroduj za nás</em><small><span lang="la">{esc(la)}</span> · kaple {esc(byN[i + 1]["name"])}</small></a></li>'
        for i, (la, cs) in enumerate(prayers["litany"]))


def litany_body(prefix):
    frag = relink(block("litanie"), prefix)
    return frag.replace('<ol class="litany-list" id="litany-list"></ol>', f'<ol class="litany-list">{litany_items(prefix)}</ol>')


LITANY_SUMMARY = re.search(r'<details class="prayer litany" id="litany">\s*<summary><span class="p-title">(.*?)</span><span class="p-when">(.*?)</span>', INDEX, re.S)
LITANY_TITLE, LITANY_WHEN = LITANY_SUMMARY.group(1), LITANY_SUMMARY.group(2)


def prayer_card(p, prefix, link=True):
    t = f'<a href="{prefix}{prayer_path(p)}">{esc(p["title"])}</a>' if link else esc(p["title"])
    return (f'<section class="prayer sp-prayer" id="p-{p["id"]}"><header class="sp-prayer-head"><h2 class="p-title">{t}</h2>'
            + (f'<span class="p-when">{esc(p["when"])}</span>' if p.get("when") else "")
            + f'</header><div class="p-body"><p class="p-text">{esc(p["text"])}</p></div></section>')


def creative_ld(name, text, url, about=None):
    d = {"@type": "CreativeWork", "name": name, "text": text, "url": url, "inLanguage": "cs",
         "isPartOf": {"@id": SITE_URL + "#website"}, "publisher": {"@id": ORG_ID}}
    if about:
        d["about"] = about
    return d


def prayers_hub():
    prefix, vh = "../", view_head("modlitby")
    body = f"""<div class="page">
<header class="page-head">
  <p class="eyebrow">{vh["eyebrow"]}</p>
  <h1>{vh["title"]}</h1>
  <p class="lead">{esc(prayers["howto"])}</p>
</header>
<div class="prayer-list">{"".join(prayer_card(p, prefix) for p in prayers["prayers"])}</div>
<section class="prayer sp-prayer litany" id="litanie"><header class="sp-prayer-head"><h2 class="p-title"><a href="{prefix}{LITANY_PATH}">{LITANY_TITLE}</a></h2><span class="p-when">{LITANY_WHEN}</span></header>
<div class="p-body">{litany_body(prefix)}</div></section>
</div>"""
    desc = "Modlitby na pouť z Prahy do Staré Boleslavi: Svatováclavský chorál, modlitba ke sv. Václavu, Pod ochranu tvou, Anděl Páně a loretánská litanie ke 44 kaplím."
    render("modlitby/", title="Modlitby na pouť do Staré Boleslavi – Svatá cesta", desc=clip(desc), body=body, section="modlitby",
           crumbs=[("Svatá cesta", ""), ("Modlitby", "modlitby/")], ld=[WEBSITE, ORG])


def prayer_page(p):
    path, prefix = prayer_path(p), "../../"
    others = [x for x in prayers["prayers"] if x["id"] != p["id"]]
    body = f"""<article class="page">
<header class="page-head">
  <p class="eyebrow">Modlitba na Svatou cestu</p>
  <h1>{esc(p["title"])}</h1>
  {f'<p class="lead">{esc(p["when"])}</p>' if p.get("when") else ""}
</header>
<div class="prayer sp-prayer"><div class="p-body" style="padding-top:18px"><p class="p-text">{esc(p["text"])}</p></div></div>
<div class="sp-lead-actions" style="margin-top:18px"><a class="btn btn-primary" href="{prefix}"><svg viewBox="0 0 24 24" aria-hidden="true"><use href="#i-map"/></svg>Otevřít mapu Svaté cesty</a><a class="btn btn-ghost" href="{prefix}modlitby/">Všechny modlitby</a></div>
<h2 class="sp-h">Další modlitby na cestu</h2>
<ul class="links"><li><a href="{prefix}{LITANY_PATH}">{LITANY_TITLE}</a> – {LITANY_WHEN}</li>{"".join(f'<li><a href="{prefix}{prayer_path(x)}">{esc(x["title"])}</a></li>' for x in others)}</ul>
</article>"""
    first = p["text"].split("\n")[0]
    desc = first_fit([f'{p["title"]} – celý text modlitby. {p["when"]}.' if p.get("when") else f'{p["title"]} – celý text modlitby: {first}',
                      f'{p["title"]} – celý text modlitby na pouť po Svaté cestě z Prahy do Staré Boleslavi.'])
    title = f'{p["title"]} – text modlitby | Svatá cesta' if p["id"] != "choral" else f'{p["title"]} – text písně „Svatý Václave“ | Svatá cesta'
    render(path, title=title, desc=desc, body=body, section="modlitby", og_type="article",
           crumbs=[("Svatá cesta", ""), ("Modlitby", "modlitby/"), (p["title"], path)],
           ld=[creative_ld(p["title"], p["text"], SITE_URL + path)])


def litany_page():
    path, prefix = LITANY_PATH, "../../"
    body = f"""<article class="page">
<header class="page-head">
  <p class="eyebrow">{LITANY_WHEN}</p>
  <h1>{LITANY_TITLE}</h1>
  <p class="lead">{esc(prayers["howto"])}</p>
</header>
<div class="prayer sp-prayer litany"><div class="p-body" style="padding-top:6px">{litany_body(prefix)}</div></div>
<div class="sp-lead-actions" style="margin-top:18px"><a class="btn btn-primary" href="{prefix}#kaple"><svg viewBox="0 0 24 24" aria-hidden="true"><use href="#i-map"/></svg>Otevřít mapu 44 kaplí</a><a class="btn btn-ghost" href="{prefix}modlitby/">Všechny modlitby</a></div>
</article>"""
    text = "\n".join(f"{cs} – oroduj za nás." for _, cs in prayers["litany"])
    desc = "Loretánská litanie ve znění ze 17. století: 44 invokací latinsky i česky. Každá patří jedné ze 44 kaplí Svaté cesty z Prahy do Staré Boleslavi."
    render(path, title="Loretánská litanie – 44 invokací a 44 kaplí Svaté cesty", desc=clip(desc), body=body, section="modlitby",
           og_type="article", crumbs=[("Svatá cesta", ""), ("Modlitby", "modlitby/"), (LITANY_TITLE, path)],
           ld=[creative_ld(LITANY_TITLE, text, SITE_URL + path)])


# ---------- historie a info ----------
def history_page():
    prefix, vh = "../", view_head("historie")
    frag = relink(block("historie"), prefix, {"info": prefix + "info/#zdroje"})
    body = f"""<article class="page prose">
<header class="page-head">
  <p class="eyebrow">{vh["eyebrow"]}</p>
  <h1>{vh["title"]}</h1>
</header>
{frag}
<div class="sp-lead-actions"><a class="btn btn-primary" href="{prefix}"><svg viewBox="0 0 24 24" aria-hidden="true"><use href="#i-map"/></svg>Otevřít mapu Svaté cesty</a><a class="btn btn-ghost" href="{prefix}kaple/">Všech 44 kaplí</a></div>
</article>"""
    imgs = [SITE_URL + m for m in re.findall(r'src="(img/[^"]+)"', block("historie"))]
    desc = "Historie Svaté cesty z Prahy do Staré Boleslavi: svatý Václav, Palladium země české, jezuité a 44 barokních kaplí z let 1674–1680, jejich zánik a obnova."
    art = {"@type": "Article", "headline": vh["title"], "name": f'{vh["title"]} – historie Svaté cesty', "description": clip(desc),
           "url": SITE_URL + "historie/", "mainEntityOfPage": SITE_URL + "historie/", "inLanguage": "cs", "image": imgs,
           "author": {"@id": ORG_ID}, "publisher": {"@id": ORG_ID}, "about": TRAIL}
    render("historie/", title="Historie Svaté cesty z Prahy do Staré Boleslavi – 44 barokních kaplí", desc=clip(desc), body=body,
           section="historie", og_type="article", crumbs=[("Svatá cesta", ""), ("Historie", "historie/")], ld=[WEBSITE, ORG, art])


def calendar_items():
    return "".join(f'<li><div class="c-date">{esc(e["date"])}</div><div><div class="c-title">{esc(e["title"])}</div><p>{esc(e["text"])}</p></div></li>'
                   for e in events["recurring"])


def stages_items(prefix):
    out = []
    for s in STAGES or []:
        cs = [c for c in chapels if s["chapels"][0] <= c["n"] <= s["chapels"][1]]
        chips = "".join(f'<a class="{"stoji" if c["status"] != "zanikla" else ""}" href="{prefix}{chapel_path(c)}" title="{esc(c["name"])} – {STATUS_LABEL[c["status"]]}">{c["n"]}</a>' for c in cs)
        out.append(f'<li><div class="st-km">km {num(s["from"])} – {num(s["to"])}</div><div class="st-title">{esc(s["title"])}</div>'
                   f'<p class="st-text">{esc(s["text"])}</p><div class="st-chips">{chips}</div></li>')
    return "".join(out)


def special_link(prefix):
    sp = active_specials()
    if not sp:
        return ""
    ev = sp[0]
    return (f'<section class="event-card" data-until="{esc(ev["showUntil"])}" data-start="{esc(ev["startDate"])}" data-end="{esc(ev["endDate"])}">'
            f'<p class="eyebrow ev-when">Právě se chystá</p><h2>{esc(ev["title"])}</h2>'
            f'<p class="ev-sub">{esc(ev["subtitle"])}</p><p class="ev-note"><a href="{prefix}svatovaclavska-pout/">Program pouti ›</a></p></section>')


UNTIL_SCRIPT = ('<script>document.querySelectorAll("[data-until]").forEach(function(e){if(new Date()>new Date(e.getAttribute("data-until")))e.hidden=true;});'
                # statické stránky: „právě probíhá“ a dnešní den programu
                '(function(){var d=new Date(),t=d.getFullYear()+"-"+("0"+(d.getMonth()+1)).slice(-2)+"-"+("0"+d.getDate()).slice(-2);'
                'document.querySelectorAll(".event-card[data-start]").forEach(function(c){var w=c.querySelector(".ev-when");'
                'if(w&&t>=c.getAttribute("data-start")&&t<=c.getAttribute("data-end"))w.textContent="Právě probíhá";'
                'c.querySelectorAll("[data-date]").forEach(function(h){if(h.getAttribute("data-date")===t){h.classList.add("is-today");h.textContent+=" · dnes";}});});})();</script>')


def info_page():
    prefix, vh = "../", view_head("info")
    frag = relink(block("info"), prefix, {"zdroje": "#zdroje"})
    frag = frag.replace('<ol class="stages" id="stages"></ol>', f'<ol class="stages">{stages_items(prefix)}</ol>')
    frag = frag.replace('<ul class="calendar" id="calendar"></ul>', f'<ul class="calendar">{calendar_items()}</ul>')
    label = lambda k: f"Kaple č. {int(re.match(r'[0-9]+', k).group())}" if k[:1].isdigit() else esc(k)
    credits = "".join(f'<li>{label(k)}: {esc(p["author"])} – '
                      f'<a href="{esc(p["page"])}" target="_blank" rel="noopener">{esc(p["license"])}</a></li>' for k, p in photos.items())
    frag = frag.replace('<ul class="photo-credits small" id="photo-credits"></ul>', f'<ul class="photo-credits small">{credits}</ul>')
    body = f"""<div class="page prose">
{special_link(prefix)}
<header class="page-head">
  <p class="eyebrow">{vh["eyebrow"]}</p>
  <h1>{vh["title"]}</h1>
</header>
{frag}
</div>"""
    desc = "Praktické informace pro poutníky na Svaté cestě z Prahy do Staré Boleslavi: úseky cesty, tipy, doprava zpět, kalendář poutí, mše před poutí a zdroje."
    render("info/", title="Praktické informace pro poutníky – Svatá cesta Praha → Stará Boleslav", desc=clip(desc), body=body,
           section="info", crumbs=[("Svatá cesta", ""), ("Praktické informace", "info/")], ld=[WEBSITE, ORG], script=UNTIL_SCRIPT)


# ---------- Národní svatováclavská pouť ----------
def event_dates(ev):
    """startDate/endDate z events.json; záloha: dny programu („Pondělí 28. 9.“) + rok z showUntil."""
    if ev.get("startDate") and ev.get("endDate"):
        return ev["startDate"], ev["endDate"]
    year = int(ev["showUntil"][:4])
    ds = []
    for d in ev.get("days", []):
        m = re.search(r"(\d{1,2})\.\s*(\d{1,2})\.", d["day"])
        if m:
            ds.append(datetime.date(year, int(m.group(2)), int(m.group(1))).isoformat())
    return (ds[0], ds[-1]) if ds else (None, None)


def event_card(ev):
    days = "".join(f'<h3 class="ev-day" data-date="{esc(d.get("date", ""))}">{esc(d["day"])}</h3><ul>' + "".join(
        f'<li class="{"hl" if len(it) > 2 and it[2] else ""}"><b>{esc(it[0])}</b><span>{esc(it[1])}</span></li>' for it in d["items"]) + "</ul>"
        for d in ev["days"])
    return (f'<section class="event-card" data-until="{esc(ev["showUntil"])}" data-start="{esc(ev["startDate"])}" data-end="{esc(ev["endDate"])}">'
            f'<p class="eyebrow">Program</p><h2>{esc(ev["title"])}</h2>'
            f'<p class="ev-sub">{esc(ev["subtitle"])}</p>{days}'
            f'<p class="ev-note">{esc(ev["note"])} <a href="{esc(ev["source"])}" target="_blank" rel="noopener">Oficiální program ›</a></p></section>')


def pout_page():
    path, prefix = "svatovaclavska-pout/", "../"
    rec = next((e for e in events["recurring"] if "svatováclavská" in e["title"].lower()), None)
    sp = active_specials()
    ev = sp[0] if sp else None
    route_items = "".join(
        f'<li><a href="{prefix}trasy/{r["id"]}/">{esc(r["name"])}</a> – {fmt_km(r["km"])}, {esc(r["time"])}, {MODE_LABEL[r["mode"]]}; start {esc(r["start"]["name"])}</li>'
        for r in routes)
    by_id = {p["id"]: p for p in prayers["prayers"]}
    pray = "".join(f'<li><a href="{prefix}{prayer_path(by_id[i])}">{esc(by_id[i]["title"])}</a></li>' for i in ("choral", "vaclav", "palladium") if i in by_id)
    source = ev["source"] if ev else "https://www.staraboleslav.com/"
    body = f"""<article class="page prose">
<header class="page-head">
  <p class="eyebrow">{esc(rec["date"]) if rec else "28. 9."} · Stará Boleslav</p>
  <h1>Národní svatováclavská pouť</h1>
  {f'<p class="lead">{esc(rec["text"])}</p>' if rec else ""}
</header>
{event_card(ev) if ev else ""}
<p>Program pouti každý rok vydává poutní místo Stará Boleslav. Platný program najdete vždy na <a href="{esc(source)}" target="_blank" rel="noopener">staraboleslav.com</a>.</p>
<h2 class="sp-h">Pěšky nebo na kole z&nbsp;Prahy</h2>
<p>Do Staré Boleslavi vede Svatá cesta se 44 barokními kaplemi. Můžete jít celou cestu od Poříčské brány, nebo si vybrat kratší variantu:</p>
<ul class="links">{route_items}</ul>
<h2 class="sp-h">Na cestu</h2>
<ul>
<li><strong>Za tmy podél silnice:</strong> kdo jde na ranní mši z&nbsp;Prahy, prochází úsek Vinoř – Brandýs ještě za šera. Cesta vede z&nbsp;velké části podél silnice, jděte proti směru jízdy a&nbsp;vezměte si reflexní vestu a&nbsp;čelovku. Za světla se silnici můžete vyhnout polní cestou z&nbsp;Podolanky přes Cvrčovice a&nbsp;Popovice (<a href="{prefix}trasy/polni/">Z Vinoře polní cestou mimo silnici</a>), vynecháte ale kaple 31 až 41.</li>
<li><strong>Voda a jídlo:</strong> v&nbsp;polních úsecích nic není, obchody jsou v&nbsp;Kbelích, ve Vinoři a&nbsp;v&nbsp;Brandýse.</li>
<li><strong>Zpět do Prahy:</strong> ze Staré Boleslavi a&nbsp;Brandýsa jezdí autobusy PID (např. na Černý Most nebo do Letňan). Po poutní mši bývají plné, počítejte s&nbsp;čekáním. Spojení najdete na <a href="https://pid.cz" target="_blank" rel="noopener">pid.cz</a> nebo <a href="https://idos.cz" target="_blank" rel="noopener">idos.cz</a>.</li>
</ul>
<div class="sp-lead-actions"><a class="btn btn-primary" href="{prefix}"><svg viewBox="0 0 24 24" aria-hidden="true"><use href="#i-map"/></svg>Otevřít mapu Svaté cesty</a><a class="btn btn-ghost" href="{prefix}info/">Praktické informace</a></div>
<h2 class="sp-h">Modlitby na pouť</h2>
<ul class="links">{pray}</ul>
<h2 class="sp-h">Proč Stará Boleslav</h2>
<p>Stará Boleslav je místem mučednické smrti svatého Václava a&nbsp;domovem Palladia země české. <a href="{prefix}historie/">Příběh Svaté cesty</a> · <a href="{prefix}info/#zdroje">Zdroje</a></p>
</article>"""
    ld = [WEBSITE, ORG]
    year = ""
    if ev:
        start, end = event_dates(ev)
        year = " " + ev["title"].split()[-1] if ev["title"].split()[-1].isdigit() else ""
        if start:
            ld.append({"@type": "Event", "name": ev["title"], "description": clip(f'{ev["subtitle"]}. {rec["text"] if rec else ""}'),
                       "startDate": start, "endDate": end, "url": SITE_URL + path,
                       "eventStatus": "https://schema.org/EventScheduled",
                       "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
                       "location": {"@type": "Place", "name": ev.get("location", "Mariánské náměstí a baziliky, Stará Boleslav"),
                                    "address": {"@type": "PostalAddress", "streetAddress": "Mariánské náměstí",
                                                "addressLocality": "Brandýs nad Labem-Stará Boleslav", "addressCountry": "CZ"}},
                       "organizer": {"@type": "Organization", "name": "Poutní místo Stará Boleslav", "url": "https://www.staraboleslav.com/"},
                       "image": [SITE_URL + "img/bazilika.jpg", SITE_URL + "img/og.jpg"]})
    desc = (f'Národní svatováclavská pouť{year} ve Staré Boleslavi, 28. září: program, poutní mše na Mariánském náměstí '
            f'a jak dojít pěšky nebo dojet na kole z Prahy po Svaté cestě.')
    render(path, title=f"Národní svatováclavská pouť{year} – Stará Boleslav, 28. září", desc=clip(desc), body=body,
           section="info", crumbs=[("Svatá cesta", ""), ("Národní svatováclavská pouť", path)], ld=ld,
           og_img="img/bazilika.jpg", og_alt="Bazilika sv. Václava ve Staré Boleslavi", script=UNTIL_SCRIPT)


# ---------- časté otázky ----------
def faq_items(prefix):
    """(otázka, odpověď – prostý text, odkaz (cesta, text) | None). Čísla se berou z dat."""
    cela = next(r for r in routes if r["id"] == "cela")
    kolo = next((r for r in routes if r["mode"] == "kolo"), None)
    short = [r for r in routes if r["id"] != "cela" and r["mode"] == "pesky"]
    cnt = {k: sum(1 for c in chapels if c["status"] == k) for k in STATUS_LABEL}
    nsp = next((e for e in events["recurring"] if "svatováclavská" in e["title"].lower()), None)
    items = [
        ("Co je Svatá cesta z Prahy do Staré Boleslavi?",
         f"Barokní poutní cesta (Via Sancta) z Prahy do Staré Boleslavi, místa mučednické smrti svatého Václava a domova Palladia země "
         f"české. V letech 1674–1680 ji dali jezuité ozdobit {len(chapels)} výklenkovými kaplemi, tolik, kolik má loretánská litanie invokací.",
         ("historie/", "Historie Svaté cesty")),
        ("Jak dlouhá je Svatá cesta a jak dlouho se jde?",
         f"Celá cesta měří asi {num(round(cela['km']))} km a pěšky trvá {cela['time']} včetně zastávek. Celkové stoupání je asi "
         f"{cela.get('elevation', 160)} m. {cela.get('notFor', '')}".strip(),
         ("trasy/cela/", cela["name"])),
        ("Kde Svatá cesta začíná a kde končí?",
         f"Začíná u Poříčské brány na náměstí Republiky v Praze ({cela['start']['transport']}) a končí u bazilik ve Staré Boleslavi.",
         (f"kaple/", "Všech 44 kaplí po pořadí")),
        ("Kolik kaplí Svaté cesty se dochovalo?",
         f"Z {len(chapels)} kaplí dnes stojí {cnt['stoji']}, dalších {cnt['replika']} nahradily repliky a {cnt['zanikla']} zaniklo. "
         f"Na místech mnoha zaniklých kaplí stojí očíslované dřevěné kříže.",
         ("kaple/", "Přehled kaplí")),
        ("Existuje kratší varianta Svaté cesty?",
         "Ano. " + " ".join(f"{r['name']}: {fmt_km(r['km'])}, {r['time']}, start {r['start']['name']}." for r in short),
         ("trasy/", "Všechny trasy")),
    ]
    if kolo:
        items.append(("Dá se Svatá cesta projet na kole?",
                      f"Ano. {kolo['name']} měří {fmt_km(kolo['km'])} a trvá {kolo['time']}." + (f" Povrch: {kolo['surface']}." if kolo.get("surface") else ""),
                      (f"trasy/{kolo['id']}/", kolo["name"])))
    items += [
        ("Jak se dostanu ze Staré Boleslavi zpět do Prahy?",
         "Ze Staré Boleslavi a Brandýsa nad Labem jezdí autobusy PID do Prahy, například na Černý Most nebo do Letňan. "
         "Aktuální spojení najdete na pid.cz nebo idos.cz.", ("info/", "Praktické informace")),
        ("Kde se po cestě najíst a napít?", cela.get("breaks", ""), ("info/", "Tipy na cestu")),
    ]
    if nsp:
        items.append(("Kdy je Národní svatováclavská pouť do Staré Boleslavi?",
                      f"Každý rok {nsp['date']} ve Staré Boleslavi. {nsp['text']}", ("svatovaclavska-pout/", "Program pouti")))
    items += [
        ("Kdy je nejlepší vydat se na Svatou cestu?",
         "Kdykoli během roku. Zvláštní význam mají tyto dny: " +
         "; ".join(f"{e['date']} {e['title']}" for e in events["recurring"]) + ".",
         ("info/", "Kalendář poutí")),
        ("Proč má Svatá cesta právě 44 kaplí?",
         f"Každá kaple odpovídá jedné ze {len(prayers['litany'])} invokací loretánské litanie ve znění ze 17. století a připomíná jedno "
         "české nebo moravské mariánské poutní místo. Poutníci se u každé kaple modlí příslušnou invokaci a Zdrávas Maria.",
         (LITANY_PATH, "Loretánská litanie ke kaplím")),
        ("Funguje průvodce bez signálu?",
         "Ano. Průvodce je zdarma a jde přidat na plochu telefonu. Texty, modlitby a fotografie jsou pak k dispozici i offline, "
         "mapa se uloží pro oblasti, které si jednou prohlédnete. Navštívené kaple si můžete odškrtávat.", ("", "Otevřít mapu")),
    ]
    return items


FAQ_PATH = "otazky/"


def faq_page():
    prefix = "../"
    items = faq_items(prefix)
    qa = "".join(
        f'<section class="faq-item"><h2 class="sp-h">{esc(q)}</h2><p>{esc(a)}'
        + (f' <a href="{prefix}{lp}">{esc(lt)} ›</a>' if link else "") + "</p></section>"
        for q, a, link in items for lp, lt in [link or ("", "")])
    body = f"""<article class="page prose">
<header class="page-head">
  <p class="eyebrow">Svatá cesta · Via Sancta</p>
  <h1>Časté otázky o&nbsp;Svaté cestě</h1>
  <p class="lead">Krátké odpovědi na to, na co se poutníci ptají nejčastěji: délka, začátek a&nbsp;konec cesty, kratší varianty, kolo, doprava zpět a&nbsp;svatováclavská pouť.</p>
</header>
{qa}
<div class="sp-lead-actions"><a class="btn btn-primary" href="{prefix}"><svg viewBox="0 0 24 24" aria-hidden="true"><use href="#i-map"/></svg>Otevřít mapu Svaté cesty</a><a class="btn btn-ghost" href="{prefix}info/">Praktické informace</a></div>
</article>"""
    ld = {"@type": "FAQPage", "@id": SITE_URL + FAQ_PATH + "#faq", "url": SITE_URL + FAQ_PATH, "inLanguage": "cs",
          "isPartOf": {"@id": SITE_URL + "#website"}, "about": TRAIL,
          "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a, _ in items]}
    desc = "Časté otázky o Svaté cestě z Prahy do Staré Boleslavi: jak je dlouhá, kde začíná, kratší trasy, kolo, cesta zpět a Národní svatováclavská pouť."
    render(FAQ_PATH, title="Časté otázky – Svatá cesta z Prahy do Staré Boleslavi", desc=clip(desc), body=body, section="info",
           crumbs=[("Svatá cesta", ""), ("Časté otázky", FAQ_PATH)], ld=[WEBSITE, ORG, ld])
    return items


# ---------- 404 ----------
def page_404():
    body = f"""<div class="page">
<header class="page-head">
  <p class="eyebrow">Chyba 404</p>
  <h1>Stránka nenalezena</h1>
  <p class="lead">Tuto stránku jsme nenašli, možná se změnila její adresa. Zkuste mapu nebo některou z&nbsp;těchto stránek:</p>
</header>
<div class="sp-lead-actions"><a class="btn btn-primary" href="{SITE_URL}"><svg viewBox="0 0 24 24" aria-hidden="true"><use href="#i-map"/></svg>Otevřít mapu Svaté cesty</a></div>
<ul class="links">{hub_links(SITE_URL)}</ul>
</div>"""
    render("404.html", title="Stránka nenalezena – Svatá cesta", desc="Tuto stránku jsme nenašli.", body=body, absolute=True, noindex=True)


# ---------- hlavička index.html ----------
def home_head():
    cela = next(r for r in routes if r["id"] == "cela")
    title = "Svatá cesta z Prahy do Staré Boleslavi – mapa 44 barokních kaplí, trasy, modlitby"
    desc = "Průvodce poutníka po Svaté cestě (Via Sancta) z Prahy do Staré Boleslavi: mapa 44 barokních kaplí, navigace, modlitby, historie a praktické informace."
    trip = {"@type": "TouristTrip", "@id": SITE_URL + "#trip", "name": "Svatá cesta z Prahy do Staré Boleslavi",
            "alternateName": "Via Sancta", "url": SITE_URL, "description": desc, "inLanguage": "cs",
            "touristType": ["poutníci", "pěší turisté", "cyklisté"],
            "tripOrigin": {"@type": "Place", "name": cela["start"]["name"]},
            "itinerary": {"@type": "ItemList", "numberOfItems": len(chapels), "itemListElement": [
                {"@type": "ListItem", "position": c["n"], "item": chapel_ld_ref(c)} for c in chapels]},
            "subTrip": [{"@type": "TouristTrip", "name": r["name"], "url": SITE_URL + f'trasy/{r["id"]}/'} for r in routes]}
    meta = head_meta(title, desc, SITE_URL, *OG_DEFAULT)
    new = f"{meta}\n{ld_script([WEBSITE, ORG, trip])}\n"
    global INDEX
    start, end = "<!-- build:head", "<!-- /build:head -->"
    i = INDEX.index("\n", INDEX.index(start)) + 1
    j = INDEX.index(end)
    out = INDEX[:i] + new + INDEX[j:]
    if out != INDEX:
        (ROOT / "index.html").write_text(out)
        INDEX = out
        CHANGED.add("")
    IMAGES[""] = [OG_DEFAULT[0]]
    WRITTEN.append(("", title, desc))


# ---------- sitemap, robots, úklid ----------
# Roboti vyhledávačů a AI asistentů, kterým web výslovně povoluje přístup (ChatGPT, Claude, Perplexity,
# Gemini, Copilot, Apple Intelligence, Seznam …). Výčet je jen signál – „User-agent: *“ platí pro všechny ostatní.
AI_BOTS = ["GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot", "Claude-User", "Claude-SearchBot", "anthropic-ai",
           "PerplexityBot", "Perplexity-User", "Google-Extended", "GoogleOther", "Applebot", "Applebot-Extended",
           "Bingbot", "DuckAssistBot", "Amazonbot", "meta-externalagent", "MistralAI-User", "cohere-ai", "CCBot",
           "YouBot", "SeznamBot"]


def sitemap():
    urls = sorted({p for p, _, _ in WRITTEN if not p.endswith(".html")}, key=lambda p: (p != "", p.count("/"), p))
    try:
        old = dict(re.findall(r"<loc>(.*?)</loc>\s*<lastmod>(.*?)</lastmod>", (ROOT / "sitemap.xml").read_text()))
    except OSError:
        old = {}
    today = TODAY.isoformat()
    mod = {p: today if p in CHANGED or SITE_URL + p not in old else old[SITE_URL + p] for p in urls}
    # úvodní stránka = aplikace: změní se i úpravou index.html, app.js nebo CSS mimo build
    app_mtime = max(datetime.date.fromtimestamp((ROOT / f).stat().st_mtime) for f in ("index.html", "js/app.js", "css/app.css"))
    mod[""] = max([mod.get("", today), app_mtime.isoformat()] + list(mod.values()))
    xml = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">']
    for p in urls:
        imgs = "".join(f"<image:image><image:loc>{esc(SITE_URL + i)}</image:loc></image:image>" for i in IMAGES.get(p, []))
        xml.append(f"  <url><loc>{esc(SITE_URL + p)}</loc><lastmod>{mod[p]}</lastmod>{imgs}</url>")
    xml.append("</urlset>")
    (ROOT / "sitemap.xml").write_text("\n".join(xml) + "\n")
    robots = ["# Vyhledávače i AI asistenti jsou vítáni – obsah průvodce smí číst, citovat a odkazovat.",
              f"# Shrnutí webu pro jazykové modely: {SITE_URL}llms.txt (celý text: {SITE_URL}llms-full.txt)", "",
              "User-agent: *", "Allow: /", ""]
    for b in AI_BOTS:
        robots += [f"User-agent: {b}", "Allow: /", ""]
    robots.append(f"Sitemap: {SITE_URL}sitemap.xml")
    (ROOT / "robots.txt").write_text("\n".join(robots) + "\n")
    return len(urls)


# ---------- llms.txt (shrnutí pro AI asistenty, https://llmstxt.org) ----------
def html_to_md(frag):
    """Hrubý převod HTML fragmentu (už s absolutními odkazy) na Markdown."""
    t = re.sub(r"<!--.*?-->", "", frag, flags=re.S)
    t = re.sub(r"<(script|style|svg|figure)\b.*?</\1>", "", t, flags=re.S)
    t = re.sub(r"<h[1-6][^>]*>(.*?)</h[1-6]>", lambda m: "\n\n### " + m.group(1) + "\n\n", t, flags=re.S)
    t = re.sub(r'<a [^>]*href="([^"]+)"[^>]*>(.*?)</a>', lambda m: f"[{m.group(2)}]({m.group(1)})", t, flags=re.S)
    t = re.sub(r"<li[^>]*>", "\n- ", t)
    t = re.sub(r"<(strong|b)>(.*?)</\1>", r"**\2**", t, flags=re.S)
    t = re.sub(r"</(p|div|ul|ol|dl|section|header)>|<br\s*/?>", "\n\n", t)
    t = re.sub(r"<(dt)[^>]*>", "\n\n", t)
    t = re.sub(r"<span[^>]*>", " ", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = html.unescape(t).replace("\xa0", " ")
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n[ \t]+", "\n", t)
    t = re.sub(r"\[\s+", "[", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def llms(faq):
    cela = next(r for r in routes if r["id"] == "cela")
    cnt = {k: sum(1 for c in chapels if c["status"] == k) for k in STATUS_LABEL}
    summary = (f"Průvodce poutníka po Svaté cestě (Via Sancta), barokní poutní cestě z Prahy do Staré Boleslavi. "
               f"Asi {num(round(cela['km']))} km od Poříčské brány k bazilikám ve Staré Boleslavi, {len(chapels)} výklenkových kaplí "
               f"z let 1674–1680 ({cnt['stoji']} stojí, {cnt['replika']} replik, {cnt['zanikla']} zaniklých), interaktivní mapa, "
               f"{len(routes)} tras pěšky i na kole, modlitby, loretánská litanie, historie a kalendář poutí.")
    english = (f"English: {SITE_URL} is a free Czech-language pilgrim guide to the Holy Way (Via Sancta), a Baroque pilgrimage route "
               f"(~{round(cela['km'])} km) from Prague to Stará Boleslav, where St. Wenceslas was martyred and the Palladium of Bohemia "
               f"is kept. It covers all {len(chapels)} wayside chapels built by the Jesuits in 1674–1680 (one for each invocation of the "
               f"Litany of Loreto), walking and cycling routes, prayers, history and the National St. Wenceslas Pilgrimage (28 September).")
    link = lambda path, name, note="": f"- [{name}]({SITE_URL}{path})" + (f": {note}" if note else "")
    out = [f"# {SITE_NAME} z Prahy do Staré Boleslavi (Via Sancta)", "", f"> {summary}", "", english, "",
           f"Web provozuje {PUBLISHER_NAME} ({PUBLISHER_URL}), kontakt {PUBLISHER_EMAIL}. Nekomerční projekt, obsah je zdarma. "
           f"Při citování prosím odkazujte na konkrétní stránku.", "",
           "## Hlavní stránky", "",
           link("", "Interaktivní mapa", "mapa trasy a všech 44 kaplí, navigace „Kde jsem“"),
           link(FAQ_PATH, "Časté otázky", "délka, začátek a konec, kratší trasy, kolo, doprava zpět"),
           link("trasy/", "Trasy", ", ".join(f"{r['name']} ({fmt_km(r['km'])})" for r in routes)),
           link("kaple/", "Kaple", "přehled všech 44 zastavení po úsecích"),
           link("historie/", "Historie", "sv. Václav, Palladium země české, jezuité, zánik a obnova kaplí"),
           link("info/", "Praktické informace", "úseky cesty, tipy, doprava, kalendář poutí, zdroje"),
           link("svatovaclavska-pout/", "Národní svatováclavská pouť", "28. září ve Staré Boleslavi"),
           link("modlitby/", "Modlitby", "modlitby na pouť"), link(LITANY_PATH, "Loretánská litanie", "44 invokací ke 44 kaplím"),
           "", "## Trasy", ""]
    out += [link(f"trasy/{r['id']}/", r["name"], route_desc(r)) for r in routes]
    out += ["", "## Kaple", ""]
    out += [link(chapel_path(c), f"{c['n']}. {c['name']}", f"{c['area']}, km {num(c['km'])}, {status_label(c)}") for c in chapels]
    out += ["", "## Modlitby", ""]
    out += [link(prayer_path(x), x["title"]) for x in prayers["prayers"]]
    out += ["", "## Optional", "", f"- [Celý text průvodce v jednom souboru]({SITE_URL}llms-full.txt)",
            f"- [Mapa webu]({SITE_URL}sitemap.xml)"]
    (ROOT / "llms.txt").write_text("\n".join(out) + "\n")

    # llms-full.txt – celý obsah průvodce jako Markdown
    full = out[:out.index("## Hlavní stránky")]
    full += ["## Časté otázky", ""]
    for q, a, _ in faq:
        full += [f"### {q}", "", a, ""]
    full += ["## Trasy", ""]
    for r in routes:
        full += [f"### {r['name']}", "", f"URL: {SITE_URL}trasy/{r['id']}/", "",
                 f"- Délka: {fmt_km(r['km'])}, čas: {r['time']}, {MODE_LABEL[r['mode']]}, obtížnost: {r['difficulty']}"
                 + (f", stoupání {r['elevation']} m" if r.get("elevation") is not None else ""),
                 f"- Start: {r['start']['name']} ({r['start']['transport']}); cíl: {r['end']['name']}",
                 f"- Pro koho: {', '.join(r.get('suitableFor', []))}"]
        full += [f"- {t}: {r[k]}" for t, k in (("Povrch", "surface"), ("Pozor", "notFor"), ("Občerstvení", "breaks"), ("Zkrácení", "bailout")) if r.get(k)]
        full += [f"- Kaple na trase: {', '.join(str(n) for n in r['chapels'])}", "", r["text"], ""]
    full += ["## Kaple", ""]
    for c in chapels:
        la, cs = prayers["litany"][c["n"] - 1]
        full += [f"### {c['n']}. {c['name']}", "", f"URL: {SITE_URL}{chapel_path(c)}", "",
                 f"- Stav: {status_label(c)}; {c['area']}, km {num(c['km'])} od Poříčské brány; GPS {c['lat']}, {c['lon']}",
                 f"- Poutní místo: {c['place']}; mariánský obraz: {c['image']}", f"- Donátor: {c['donor']}",
                 f"- Invokace loretánské litanie: {la} – {cs}, oroduj za nás", "", c["text"], ""]
    full += ["## Historie", "", html_to_md(relink(block("historie"), SITE_URL, {"info": SITE_URL + "info/#zdroje"})), ""]
    info = relink(block("info"), SITE_URL, {"zdroje": SITE_URL + "info/#zdroje"})
    info = re.sub(r'<ol class="stages" id="stages"></ol>', "<ul>" + "".join(
        f"<li>km {num(st['from'])}–{num(st['to'])}, {esc(st['title'])} (kaple {st['chapels'][0]}–{st['chapels'][1]}): {esc(st['text'])}</li>"
        for st in STAGES or []) + "</ul>", info)
    info = info.replace('<ul class="calendar" id="calendar"></ul>', "<ul>" + "".join(
        f"<li>{esc(e['date'])} – {esc(e['title'])}: {esc(e['text'])}</li>" for e in events["recurring"]) + "</ul>")
    full += ["## Praktické informace", "", html_to_md(info), ""]
    full += ["## Modlitby", "", prayers["howto"], ""]
    for x in prayers["prayers"]:
        full += [f"### {x['title']}", ""] + ([f"_{x['when']}_", ""] if x.get("when") else []) + [x["text"], ""]
    full += [f"### {html_to_md(LITANY_TITLE)}", "", f"URL: {SITE_URL}{LITANY_PATH}", ""]
    full += [f"{i + 1}. {cs} – oroduj za nás ({la}; kaple {byN[i + 1]['name']})" for i, (la, cs) in enumerate(prayers["litany"])]
    full += ["", "## Zdroje a licence", "",
             "Údaje o kaplích: Wikipedie, Poutní cesta z Prahy do Staré Boleslavi (CC BY-SA 4.0), OpenStreetMap (ODbL), "
             "svata-cesta.cz, via-sancta.cz; texty jsou napsány vlastními slovy. Fotografie: Wikimedia Commons. "
             "Polohy zaniklých kaplí jsou pravděpodobné, ne jisté.", ""]
    txt = re.sub(r"\n{3,}", "\n\n", "\n".join(full))
    (ROOT / "llms-full.txt").write_text(txt)


def cleanup():
    """Smaže dříve vygenerované stránky, které už neexistují (např. po přejmenování kaple)."""
    keep = {(ROOT / (p + "index.html")).resolve() for p, _, _ in WRITTEN if not p.endswith(".html")}
    for d in ("kaple", "trasy", "modlitby", "historie", "info", "otazky", "svatovaclavska-pout"):
        for f in sorted((ROOT / d).rglob("index.html"), reverse=True) if (ROOT / d).exists() else []:
            if f.resolve() not in keep and GENERATED in f.read_text():
                f.unlink()
                print(f"  smazáno {f.relative_to(ROOT)}")
                try:
                    f.parent.rmdir()
                except OSError:
                    pass


def main():
    for c in chapels:
        chapel_page(c)
    chapels_hub()
    for r in routes:
        route_page(r)
    routes_hub()
    for p in prayers["prayers"]:
        prayer_page(p)
    litany_page()
    prayers_hub()
    history_page()
    info_page()
    pout_page()
    faq = faq_page()
    page_404()
    home_head()
    cleanup()
    n = sitemap()
    llms(faq)
    long = [(p, len(d)) for p, _, d in WRITTEN if len(d) > 160]
    titles = [t for _, t, _ in WRITTEN]
    print(f"{len(WRITTEN)} stránek (+ index.html), sitemap: {n} adres, SITE_URL = {SITE_URL}")
    if long:
        print("  varování: popis delší než 160 znaků:", long)
    if len(set(titles)) != len(titles):
        print("  varování: duplicitní titulky")


if __name__ == "__main__":
    main()
