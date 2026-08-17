#!/usr/bin/env python3
"""
Background worker: fetch expose pages and fill in the rent.

Fetches run in a small thread pool whose size adapts to how ImmoScout responds:
it grows while everything comes back clean and collapses to a single, slow lane
the moment blocked answers appear. Parsing and writing stay on the main thread,
because SQLite wants one writer.

  python3 worker.py            # everything still open
  python3 worker.py 500        # only 500 this run
  WORKERS=2 python3 worker.py  # fixed ceiling
"""
import os, sys, time, subprocess, threading
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import conn, parse_expose, is_gone, CACHE, UA, setmeta

MAX_WORKERS = int(os.environ.get("WORKERS", "2"))
MIN_WORKERS = 1
CHUNK = 60                      # listings handed to the pool per round


class Pace:
    """Adaptive concurrency: back off hard on blocks, creep back up when clean."""

    def __init__(self):
        self.n = 2
        self.clean = 0
        self.blocked = 0
        self.lock = threading.Lock()
        self.pause_until = 0.0

    def ok(self):
        with self.lock:
            self.clean += 1
            if self.clean >= 250 and self.n < MAX_WORKERS:
                self.n += 1
                self.clean = 0

    def blocked_hit(self):
        with self.lock:
            self.blocked += 1
            self.clean = 0
            self.n = max(MIN_WORKERS, self.n // 2)
            self.pause_until = time.time() + 30

    def wait_if_paused(self):
        d = self.pause_until - time.time()
        if d > 0:
            time.sleep(d)


PACE = Pace()


def fetch(eid):
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, f"{eid}.html")
    if os.path.exists(p) and os.path.getsize(p) > 40000:
        return eid, open(p, encoding="utf-8", errors="ignore").read()
    url = f"https://www.immobilienscout24.de/expose/{eid}"
    for attempt in range(3):
        PACE.wait_if_paused()
        subprocess.run(["curl", "-s", "-m", "35", "--compressed", "-A", UA, "-o", p, url],
                       check=False)
        try:
            h = open(p, encoding="utf-8", errors="ignore").read()
        except OSError:
            h = ""
        if len(h) > 40000 and "Ich bin kein Roboter" not in h:
            PACE.ok()
            return eid, h
        PACE.blocked_hit()
        time.sleep(5 * (attempt + 1))
    return eid, ""


def main(limit=None):
    c = conn()
    q = """SELECT id, qm FROM listings WHERE rent_status='todo'
           ORDER BY is_dad DESC, (price/qm) ASC"""
    if limit:
        q += f" LIMIT {int(limit)}"
    todo = [(r["id"], r["qm"]) for r in c.execute(q).fetchall()]
    total = len(todo)
    print(f"{total:,} Exposés abzurufen", flush=True)

    ok = none = gone = fail = 0
    t0 = time.time()
    qm_of = dict(todo)

    for start in range(0, total, CHUNK):
        batch = todo[start:start + CHUNK]
        with ThreadPoolExecutor(max_workers=max(1, PACE.n)) as ex:
            results = list(ex.map(lambda t: fetch(t[0]), batch))

        for eid, h in results:
            if not h:
                fail += 1
                continue
            if is_gone(h):
                c.execute("UPDATE listings SET rent_status='gone', expose_at=datetime('now') WHERE id=?", (eid,))
                gone += 1
                continue
            p = parse_expose(h, qm_of.get(eid))
            if not p:
                fail += 1
                continue
            c.execute("""UPDATE listings SET rent=?, rent_evidence=?, rent_class=?, rent_status=?,
                         hausgeld=COALESCE(?,hausgeld), bj=COALESCE(?,bj), denkmal=?,
                         zustand=COALESCE(?,zustand), etage=COALESCE(?,etage),
                         multi=?, soll=?, expose_at=datetime('now') WHERE id=?""",
                      (p["rent"], p["rent_evidence"], p["rent_class"], p["rent_status"],
                       p["hausgeld"], p["bj"], p["denkmal"], p["zustand"], p["etage"],
                       p["multi"], p["soll"], eid))
            ok += 1 if p["rent"] else 0
            none += 0 if p["rent"] else 1

        done = start + len(batch)
        c.commit()
        setmeta(c, "worker_progress", f"{done}/{total}")
        c.commit()
        el = time.time() - t0
        rate = done / el if el else 0
        rest = (total - done) / rate / 3600 if rate else 0
        print(f"  {done:,}/{total:,}  Miete {ok:,} | ohne {none:,} | weg {gone} | Fehler {fail} "
              f"| {rate:.2f}/s | {PACE.n} Verbindungen | noch ~{rest:.1f} h", flush=True)

    c.commit()
    tot = c.execute("SELECT COUNT(*) n FROM listings WHERE rent IS NOT NULL AND rent_status<>'gone'").fetchone()["n"]
    print(f"\nFertig. Neu mit Miete: {ok:,} | insgesamt mit Miete: {tot:,}", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else None)
