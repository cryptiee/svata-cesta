"""Doplní do data/chapels.json pole `km` – vzdálenost od začátku pěší trasy.

Každá kaple se promítne na nejbližší bod trasy (data/route.geojson).
Spuštění:  python3 tools/add_km.py
"""
import json, math, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
route = json.loads((ROOT / "data/route.geojson").read_text())["geometry"]["coordinates"]
chapels = json.loads((ROOT / "data/chapels.json").read_text())

R = 6371000.0

def to_xy(lon, lat, lat0):
    return (math.radians(lon) * R * math.cos(math.radians(lat0)), math.radians(lat) * R)

lat0 = route[0][1]
pts = [to_xy(lon, lat, lat0) for lon, lat in route]
cum = [0.0]
for a, b in zip(pts, pts[1:]):
    cum.append(cum[-1] + math.dist(a, b))

def project(lat, lon):
    p = to_xy(lon, lat, lat0)
    best = (float("inf"), 0.0)
    for i, (a, b) in enumerate(zip(pts, pts[1:])):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy or 1e-9
        t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
        q = (a[0] + t * dx, a[1] + t * dy)
        d = math.dist(p, q)
        if d < best[0]:
            best = (d, cum[i] + t * math.sqrt(L2))
    return best

last = 0.0
for c in chapels:
    off, along = project(c["lat"], c["lon"])
    along = max(along, last)  # trasa je monotónní, kaple jdou po sobě
    last = along
    c["km"] = round(along / 1000, 1)
    c["offRoute"] = round(off)

(ROOT / "data/chapels.json").write_text(
    "[\n" + ",\n".join(json.dumps(c, ensure_ascii=False) for c in chapels) + "\n]\n"
)
print(f"trasa {cum[-1]/1000:.1f} km")
for c in chapels:
    print(c["n"], c["km"], "km", f"(mimo trasu {c['offRoute']} m)" if c["offRoute"] > 60 else "")
