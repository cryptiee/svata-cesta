# Svatá cesta · Praha → Stará Boleslav

Průvodce poutníka po **Svaté cestě (Via Sancta)** z Prahy do Staré Boleslavi – barokní poutní cestě se 44 výklenkovými kaplemi z let 1674–1680.

- 🗺️ mapa s pěší trasou (≈ 26 km) a všemi 44 kaplemi – stojícími, replikami i zaniklými
- 🥾 doporučené varianty tras – zkrácené pěší, rodinná, cyklopouť a svatováclavská cesta z Proseka
- 📍 „kde jsem“ – další zastavení, vzdálenost, ušlé km, automatické odškrtávání navštívených kaplí
- 🙏 modlitby na cestu; ke každé kapli její invokace loretánské litanie
- 📜 historie cesty a každé kaple, donátoři, mariánská poutní místa
- 📅 kalendář poutí + aktuální program Národní svatováclavské pouti
- 📶 funguje offline (PWA – „Přidat na plochu“)

Čistě statický web (HTML + CSS + vanilla JS + Leaflet), žádný build.

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

Po změně polohy kaple přepočítejte kilometráž: `python3 tools/add_km.py`.
Po změně hlavní trasy, kaplí nebo textů variant spusťte `python3 tools/build_routes.py` (přepíše `data/routes.json` a `data/routes/`).
Odkaz `#trasa-<id>` (např. `#trasa-letnany`) otevře mapu s danou variantou.
Po změně souborů zvyšte `VERSION` v `sw.js`, aby se offline cache obnovila.

**Každý rok:** přidejte do `data/events.json` → `special` program nové svatováclavské pouti (z plakátu na staraboleslav.com).

## Zdroje a licence

- Údaje o kaplích: Wikipedie, [Poutní cesta z Prahy do Staré Boleslavi](https://cs.wikipedia.org/wiki/Poutn%C3%AD_cesta_z_Prahy_do_Star%C3%A9_Boleslavi) (CC BY-SA 4.0), OpenStreetMap (ODbL). Texty jsou napsány vlastními slovy.
- Pěší trasa: [OSRM](https://routing.openstreetmap.de/) nad daty © přispěvatelé OpenStreetMap.
- Fotografie: Wikimedia Commons – autoři a licence u každé fotky (`data/photos.json`).
- Mapové podklady: © OpenStreetMap, OpenTopoMap, Esri.

Kód: MIT. Obsah (texty a data v `data/`): [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/deed.cs).
