"""Oznámí vyhledávačům (Bing → ChatGPT/Copilot, Seznam, Yandex …) změněné stránky přes IndexNow.

Spouštějte AŽ PO nasazení webu (git push a dokončený build GitHub Pages) – vyhledávač si
nejdřív ověří klíč na https://<doména>/<klíč>.txt a pak stáhne oznámené stránky.

  python3 tools/indexnow.py           oznámí stránky s dnešním <lastmod> v sitemap.xml
  python3 tools/indexnow.py --all     oznámí všechny adresy ze sitemap.xml

Klíč je soubor <32 hex znaků>.txt v kořeni repozitáře (obsahuje sám sebe). Jen standardní knihovna.
"""
import datetime, json, pathlib, re, sys, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
keys = [f for f in ROOT.glob("*.txt") if re.fullmatch(r"[0-9a-f]{32}\.txt", f.name)]
if not keys:
    raise SystemExit("chybí soubor s klíčem IndexNow (<32 hex>.txt v kořeni)")
key = keys[0].stem

xml = (ROOT / "sitemap.xml").read_text()
entries = re.findall(r"<loc>(.*?)</loc><lastmod>(.*?)</lastmod>", xml)
today = datetime.date.today().isoformat()
urls = [u for u, d in entries if "--all" in sys.argv or d == today]
if not urls:
    raise SystemExit("žádné stránky s dnešním <lastmod>; pro všechny použijte --all")

host = re.match(r"https?://([^/]+)/", entries[0][0]).group(1)
body = json.dumps({"host": host, "key": key, "keyLocation": f"https://{host}/{key}.txt", "urlList": urls}).encode()
req = urllib.request.Request("https://api.indexnow.org/indexnow", data=body,
                             headers={"Content-Type": "application/json; charset=utf-8"})
with urllib.request.urlopen(req, timeout=30) as r:
    print(f"IndexNow: {r.status} – oznámeno {len(urls)} adres pro {host}")
