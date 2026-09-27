# Svatá cesta · Praha → Stará Boleslav

Průvodce poutníka po **Svaté cestě (Via Sancta)** z Prahy do Staré Boleslavi, barokní poutní cestě se 44 výklenkovými kaplemi z let 1674–1680.

- 🗺️ mapa s pěší trasou (≈ 26 km) a všemi 44 kaplemi: stojícími, replikami i zaniklými
- 🥾 doporučené varianty tras: zkrácené pěší, rodinná, cyklopouť a svatováclavská cesta z Proseka
- 📍 „Kde jsem“: další zastavení, vzdálenost, ušlé km a automatické odškrtávání navštívených kaplí
- 🙏 modlitby na cestu; ke každé kapli její invokace loretánské litanie
- 📜 historie cesty a každé kaple, donátoři, mariánská poutní místa
- 📅 kalendář poutí a aktuální program Národní svatováclavské pouti
- 📶 funguje offline (PWA, „Přidat na plochu“)

Čistě statický web (HTML + CSS + vanilla JS + Leaflet). Aplikace nepotřebuje žádný build; statické stránky pro vyhledávače generuje `tools/build_pages.py` (viz níže).

## Lokální spuštění

```bash
python3 -m http.server 8321
```

a otevřít <http://localhost:8321>. Service worker se na localhostu nezapíná (pro test offline režimu přidejte `?sw`).

## Úpravy obsahu

| Soubor | Obsah |
| --- | --- |
| `data/chapels.json` | 44 kaplí – poloha, stav (`stoji` / `replika` / `zanikla`), texty, donátoři |
| `data/prayers.json` | modlitby a loretánská litanie (pořadí = čísla kaplí) |
| `data/events.json` | kalendář poutí; `special` = program konkrétního roku, zobrazí se jen mezi `showFrom` a `showUntil` |
| `data/photos.json` | fotografie a jejich autoři/licence |
| `data/route.geojson` | pěší trasa |
| `data/routes.json` | doporučené varianty tras (záložka Trasy) – texty, obtížnost, pro koho, km, stoupání, kaple na trase |
| `data/routes/<id>.geojson` | geometrie jednotlivých variant (`cela` = kopie `route.geojson`) |
| `tools/build_routes.py` | generátor variant: trasy přes OSRM, km, stoupání (Open-Meteo) a kaple do 150 m; texty variant se upravují přímo v něm |
| `tools/build_pages.py` | generátor statických stránek pro vyhledávače (SEO) – viz níže |

Po změně polohy kaple přepočítejte kilometráž: `python3 tools/add_km.py`.
Po změně hlavní trasy, kaplí nebo textů variant spusťte `python3 tools/build_routes.py` (přepíše `data/routes.json` a `data/routes/`).
Po **jakékoli** změně dat nebo textů spusťte nakonec `python3 tools/build_pages.py`.

Pořadí nástrojů: `add_km.py` → `build_routes.py` → `build_pages.py`.
Odkaz `#trasa-<id>` (např. `#trasa-letnany`) otevře mapu s danou variantou.
Po změně souborů zvyšte `VERSION` v `sw.js`, aby se offline cache obnovila.

**Každý rok:** přidejte do `data/events.json` → `special` program nové svatováclavské pouti (z plakátu na staraboleslav.com) včetně `startDate` a `endDate` (YYYY-MM-DD, použijí se ve strukturovaných datech Event) a spusťte `python3 tools/build_pages.py`. Statické stránky zobrazí program jen tehdy, když je build spuštěn mezi `showFrom` a `showUntil` – po pouti je proto dobré build pustit znovu.

## Statické stránky a SEO (`tools/build_pages.py`)

Aplikace přepíná pohledy přes `#hash`, vyhledávače ji tedy vidí jako jedinou stránku. `tools/build_pages.py` (python3, jen standardní knihovna) proto z dat vygeneruje samostatné stránky s vlastní adresou, titulkem, popisem, canonical, Open Graph a strukturovanými daty (JSON-LD):

| Adresa | Obsah |
| --- | --- |
| `kaple/`, `kaple/<n>-<slug>/` | přehled a 44 stránek kaplí (např. `kaple/26-pakenska-kaple/`) |
| `trasy/`, `trasy/<id>/` | přehled a 5 variant tras |
| `modlitby/`, `modlitby/<slug>/`, `modlitby/loretanska-litanie/` | všechny modlitby, každá modlitba zvlášť, litanie s odkazy na kaple |
| `historie/`, `info/` | text z `index.html` (značky `<!-- build:historie -->`, `<!-- build:info -->`) |
| `svatovaclavska-pout/` | Národní svatováclavská pouť – kalendář + aktuální program z `events.json` |
| `otazky/` | časté otázky (FAQPage), odpovědi se skládají z dat |
| `404.html`, `sitemap.xml`, `robots.txt` | chybová stránka, mapa webu s obrázky (`lastmod` se mění jen u stránek, které se opravdu změnily), pravidla pro roboty vč. výslovného povolení AI crawlerů (GPTBot, ClaudeBot, PerplexityBot, Google-Extended, SeznamBot …) |
| `llms.txt`, `llms-full.txt` | shrnutí webu a celý text průvodce v Markdownu pro AI asistenty ([llmstxt.org](https://llmstxt.org)) |

Skript také přepíše blok `<!-- build:head -->` v hlavičce `index.html` (titulek, popis, canonical, OG, JSON-LD) – ten needitujte ručně. Texty historie, informací a úvodu litanie upravujte v `index.html` mezi značkami `build:…`; úseky cesty v `STAGES` v `js/app.js`. Vygenerované stránky needitujte, přepíšou se.

- `SITE_URL` na začátku skriptu je jediné místo s adresou webu (canonical, `og:*`, sitemap). Odkazy uvnitř stránek jsou relativní, takže web funguje v podadresáři (`/svata-cesta/` na GitHub Pages) i v kořeni domény. Výjimkou je `404.html` s absolutními odkazy.
- Seznamy v aplikaci (kaple, litanie, úseky, tlačítka tras) jsou skutečné odkazy na tyto stránky; aplikace běžné kliknutí zachytí a otevře detail jako dřív, Ctrl/Cmd+klik otevře statickou stránku.
- Service worker statické stránky nepředukládá; uloží je při první návštěvě.
- **IndexNow** (Bing → ChatGPT a Copilot, Seznam, Yandex): po nasazení spusťte `python3 tools/indexnow.py` (oznámí stránky s dnešním `lastmod`; `--all` oznámí všechny). Klíč je soubor `<32 hex>.txt` v kořeni, nemažte ho.

## Vlastní doména

1. V `tools/build_pages.py` nastavte `SITE_URL` (např. `https://poutdoboleslavi.cz/`) a spusťte `python3 tools/build_pages.py`.
2. Do kořene repozitáře přidejte soubor `CNAME` s jediným řádkem `poutdoboleslavi.cz`.
3. DNS u registrátora: záznamy `A` pro `@` → `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153` (případně `AAAA` `2606:50c0:8000::153` … `8003::153`) a `CNAME` pro `www` → `cryptiee.github.io`.
4. GitHub → Settings → Pages: vyplňte Custom domain, počkejte na certifikát a zapněte **Enforce HTTPS**.
5. Google Search Console: přidejte doménovou službu (ověření TXT záznamem), odešlete `https://poutdoboleslavi.cz/sitemap.xml`; totéž v Bing Webmaster Tools (z Bingu čerpá vyhledávání ChatGPT a Copilot) a v Seznam Webmaster (webmaster.seznam.cz).
6. Staré adresy `cryptiee.github.io/svata-cesta/…` GitHub po nastavení domény sám přesměruje.

## Zdroje a licence

- Údaje o kaplích: Wikipedie, [Poutní cesta z Prahy do Staré Boleslavi](https://cs.wikipedia.org/wiki/Poutn%C3%AD_cesta_z_Prahy_do_Star%C3%A9_Boleslavi) (CC BY-SA 4.0), OpenStreetMap (ODbL). Texty jsou napsány vlastními slovy.
- Pěší trasa: [OSRM](https://routing.openstreetmap.de/) nad daty © přispěvatelé OpenStreetMap.
- Fotografie: Wikimedia Commons – autoři a licence u každé fotky (`data/photos.json`).
- Mapové podklady: © OpenStreetMap, OpenTopoMap, Esri.

Kód: MIT. Obsah (texty a data v `data/`): [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/deed.cs).
