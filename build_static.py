#!/usr/bin/env python3
"""
Build the static GitHub-Pages version into docs/.

GitHub Pages serves files, not programs — so the whole model runs in the browser
and the data ships as one JSON file. Re-run this whenever the worker has found
more rents, then commit and push.
"""
import json, os, shutil, sys, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import conn, ROOT

DOCS = os.path.join(ROOT, "docs")
STATIC = os.path.join(ROOT, "static")


def export_rows():
    c = conn()
    rows = c.execute("""
        SELECT * FROM listings
        WHERE rent_status <> 'gone'
          AND (rent IS NOT NULL OR is_dad = 1)
        ORDER BY (rent * 12.0 / price) DESC
    """).fetchall()
    out = []
    for r in rows:
        out.append({
            "id": r["id"], "o": r["ort"] or "", "q": r["quarter"] or "",
            "l": r["land"] or "", "z": r["plz"] or "",
            "t": (r["title"] or "")[:120],
            "p": round(r["price"]), "m2": round(r["qm"], 1),
            "zi": r["rooms"], "bj": r["bj"],
            "r": round(r["rent"]) if r["rent"] else None,
            "hg": round(r["hausgeld"]) if r["hausgeld"] else None,
            "ct": round(r["courtage_pct"] or .0357, 5),
            "img": r["img"], "be": (r["rent_evidence"] or "")[:170] or None,
            "dk": 1 if r["denkmal"] else 0,
            "mu": 1 if r["multi"] else 0,
            "so": 1 if r["soll"] else 0,
            "dad": 1 if r["is_dad"] else 0,
            "bal": r["balcony"] or 0, "lif": r["lift"] or 0,
            "kel": r["cellar"] or 0, "ebk": r["ebk"] or 0,
        })
    stats = {
        "total": c.execute("SELECT COUNT(*) n FROM listings").fetchone()["n"],
        "orte": c.execute("SELECT COUNT(DISTINCT ort) n FROM listings").fetchone()["n"],
        "todo": c.execute("SELECT COUNT(*) n FROM listings WHERE rent_status='todo'").fetchone()["n"],
        "shown": len(out),
        "stand": datetime.date.today().strftime("%d.%m.%Y"),
    }
    return out, stats


def main():
    os.makedirs(DOCS, exist_ok=True)
    rows, stats = export_rows()
    with open(os.path.join(DOCS, "data.json"), "w", encoding="utf-8") as f:
        json.dump({"stats": stats, "items": rows}, f, ensure_ascii=False, separators=(",", ":"))
    shutil.copy(os.path.join(STATIC, "style.css"), os.path.join(DOCS, "style.css"))
    open(os.path.join(DOCS, ".nojekyll"), "w").close()
    size = os.path.getsize(os.path.join(DOCS, "data.json")) / 1024
    print(f"docs/data.json: {len(rows):,} Objekte, {size:.0f} KB")
    print(f"Datenbank: {stats['total']:,} Objekte, {stats['todo']:,} noch abzurufen")


if __name__ == "__main__":
    main()
