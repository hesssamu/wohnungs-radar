#!/usr/bin/env python3
"""
Background worker: fetch expose pages and fill in the rent.

Resumable and polite. Priority: father's listings, then cheapest per m²
(that is where the yield is). Stops nothing if throttled — it just backs off.

  python3 worker.py            # run until nothing is left
  python3 worker.py 500        # only 500 this run
"""
import os, sys, time, subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import conn, parse_expose, CACHE, UA, setmeta

DELAY = 1.9
BACKOFF = [20, 45, 90, 180]


def fetch(eid):
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, f"{eid}.html")
    if os.path.exists(p) and os.path.getsize(p) > 40000:
        return open(p, encoding="utf-8", errors="ignore").read()
    url = f"https://www.immobilienscout24.de/expose/{eid}"
    for i, wait in enumerate([0] + BACKOFF):
        if wait:
            time.sleep(wait)
        subprocess.run(["curl", "-s", "-m", "35", "--compressed", "-A", UA, "-o", p, url], check=False)
        try:
            h = open(p, encoding="utf-8", errors="ignore").read()
        except OSError:
            h = ""
        if len(h) > 40000 and "Ich bin kein Roboter" not in h:
            return h
        if h and len(h) < 8000 and "nicht mehr verf" in h.lower():
            return "GONE"
    return ""


def main(limit=None):
    c = conn()
    q = """SELECT id, qm FROM listings WHERE rent_status='todo'
           ORDER BY is_dad DESC, (price/qm) ASC"""
    if limit:
        q += f" LIMIT {int(limit)}"
    ids = [(r["id"], r["qm"]) for r in c.execute(q).fetchall()]
    print(f"{len(ids):,} Exposés abzurufen", flush=True)
    ok = none = gone = fail = 0
    for i, (eid, qm) in enumerate(ids, 1):
        h = fetch(eid)
        if h == "GONE":
            c.execute("UPDATE listings SET rent_status='gone', expose_at=datetime('now') WHERE id=?", (eid,))
            gone += 1
        elif not h:
            fail += 1
            time.sleep(30)                      # hard throttle: cool down, retry next run
        else:
            p = parse_expose(h, qm)
            if p:
                c.execute("""UPDATE listings SET rent=?, rent_evidence=?, rent_class=?, rent_status=?,
                             hausgeld=COALESCE(?,hausgeld), bj=COALESCE(?,bj), denkmal=?,
                             zustand=COALESCE(?,zustand), etage=COALESCE(?,etage),
                             multi=?, soll=?, expose_at=datetime('now') WHERE id=?""",
                          (p["rent"], p["rent_evidence"], p["rent_class"], p["rent_status"],
                           p["hausgeld"], p["bj"], p["denkmal"], p["zustand"], p["etage"],
                           p["multi"], p["soll"], eid))
                ok += 1 if p["rent"] else 0
                none += 0 if p["rent"] else 1
            else:
                fail += 1
            time.sleep(DELAY)
        if i % 50 == 0:
            c.commit()
            setmeta(c, "worker_progress", f"{i}/{len(ids)}")
            c.commit()
            print(f"  {i:,}/{len(ids):,}  Miete gefunden {ok:,} | ohne Miete {none:,} | weg {gone} | Fehler {fail}", flush=True)
    c.commit()
    tot = c.execute("SELECT COUNT(*) n FROM listings WHERE rent IS NOT NULL").fetchone()["n"]
    print(f"\nFertig. Neu mit Miete: {ok:,} | insgesamt mit Miete: {tot:,}", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else None)
