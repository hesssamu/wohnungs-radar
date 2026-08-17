#!/usr/bin/env python3
"""Load every cached IS24 page already on disk into the database."""
import os, sys, json, glob, re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import conn, parse_search_page, parse_expose, UPSERT, setmeta

SCRATCH = "/private/tmp/claude-501/-Users-samuelhess/c26d427b-d040-44f1-a8c7-1668a5517a99/scratchpad"

# city -> Bundesland for the older, city-scoped search cache
CITY_LAND = {}
try:
    for c in json.load(open(f"{SCRATCH}/cities_ok.json")):
        CITY_LAND[c["city"]] = c["land"]
except OSError:
    pass


def load_searches(c):
    n = 0
    # nationwide, per-Bundesland cache
    for f in sorted(glob.glob(f"{SCRATCH}/all/*.html")):
        base = os.path.basename(f)
        land = re.sub(r"_\d+\.html$", "", base).replace("berlin_berlin", "berlin").replace("hamburg_hamburg", "hamburg")
        try:
            h = open(f, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        rows = parse_search_page(h, land)
        for r in rows:
            c.execute(UPSERT, r)
        n += len(rows)
    # older city-scoped cache
    for f in sorted(glob.glob(f"{SCRATCH}/srch/*.html")):
        base = os.path.basename(f)
        city = re.sub(r"_\d+\.html$", "", base)
        land = CITY_LAND.get(city, "")
        try:
            h = open(f, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        rows = parse_search_page(h, land)
        for r in rows:
            c.execute(UPSERT, r)
        n += len(rows)
    return n


def load_exposes(c):
    n = 0
    for d in (f"{SCRATCH}/exp", f"{SCRATCH}/is24"):
        for f in glob.glob(f"{d}/*.html"):
            eid = os.path.basename(f).replace(".html", "")
            if not eid.isdigit():
                continue
            try:
                h = open(f, encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            row = c.execute("SELECT id, qm FROM listings WHERE id=?", (eid,)).fetchone()
            if not row:
                continue
            p = parse_expose(h, row["qm"])
            if not p:
                continue
            c.execute("""UPDATE listings SET rent=?, rent_evidence=?, rent_class=?, rent_status=?,
                         hausgeld=COALESCE(?,hausgeld), bj=COALESCE(?,bj), denkmal=?,
                         zustand=COALESCE(?,zustand), etage=COALESCE(?,etage),
                         multi=?, soll=?, expose_at=datetime('now') WHERE id=?""",
                      (p["rent"], p["rent_evidence"], p["rent_class"], p["rent_status"],
                       p["hausgeld"], p["bj"], p["denkmal"], p["zustand"], p["etage"],
                       p["multi"], p["soll"], eid))
            n += 1
    return n


DAD_IDS = ["165123879", "164425660", "164424272", "169141915", "169406303", "165445249",
           "169283416", "168299040", "169482110", "169314903",
           "169534501", "166076396", "168988190", "169725315"]


def mark_dad(c):
    for i in DAD_IDS:
        c.execute("UPDATE listings SET is_dad=1 WHERE id=?", (i,))
    return c.execute("SELECT COUNT(*) n FROM listings WHERE is_dad=1").fetchone()["n"]


if __name__ == "__main__":
    c = conn()
    s = load_searches(c)
    c.commit()
    e = load_exposes(c)
    d = mark_dad(c)
    setmeta(c, "last_ingest", "ok")
    c.commit()
    tot = c.execute("SELECT COUNT(*) n FROM listings").fetchone()["n"]
    ok = c.execute("SELECT COUNT(*) n FROM listings WHERE rent_status='ok'").fetchone()["n"]
    todo = c.execute("SELECT COUNT(*) n FROM listings WHERE rent_status='todo'").fetchone()["n"]
    orte = c.execute("SELECT COUNT(DISTINCT ort) n FROM listings").fetchone()["n"]
    img = c.execute("SELECT COUNT(*) n FROM listings WHERE img IS NOT NULL").fetchone()["n"]
    print(f"Trefferlisten-Zeilen verarbeitet: {s:,}")
    print(f"Exposés eingelesen:               {e:,}")
    print(f"Papas Objekte markiert:           {d}")
    print(f"---")
    print(f"Objekte in der DB:  {tot:,}  ({orte:,} Orte, {img:,} mit Bild)")
    print(f"davon mit Miete:    {ok:,}")
    print(f"noch abzurufen:     {todo:,}")
