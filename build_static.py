#!/usr/bin/env python3
"""
Build the static GitHub-Pages version into docs/.

GitHub Pages serves files, not programs — so the whole model runs in the browser
and the data ships as one JSON file. Re-run this whenever the worker has found
more rents, then commit and push.
"""
import base64, hashlib, json, os, secrets, shutil, sys, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import conn, ROOT

DOCS = os.path.join(ROOT, "docs")
STATIC = os.path.join(ROOT, "static")
SECRETS = os.path.expanduser("~/.config/secrets/wohnungs-radar.env")
ITER = 600_000


def read_pass():
    """Die Passphrase steht nur lokal, nie im Repo."""
    if os.environ.get("PAGES_PASS"):
        return os.environ["PAGES_PASS"]
    if not os.path.exists(SECRETS):
        return None
    for line in open(SECRETS, encoding="utf-8"):
        if line.startswith("PAGES_PASS="):
            return line.split("=", 1)[1].strip().strip("'\"")
    return None


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
            "ew": r["ew"], "og": r["ortgroesse"], "mn": round(r["marktniveau"], 3) if r["marktniveau"] is not None else None,
            "rk": r["risiko"], "rb": r["risiko_band"], "rg": r["risiko_gruende"],
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
    payload = json.dumps({"stats": stats, "items": rows},
                         ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    pw = read_pass()
    if pw:
        # AES-256-GCM, Schluessel aus der Passphrase. Ohne Passwort liegt auf GitHub
        # nur Kauderwelsch — anders als bei einer Abfrage, die man im Quelltext liest.
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        salt, iv = secrets.token_bytes(16), secrets.token_bytes(12)
        key = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, ITER, dklen=32)
        ct = AESGCM(key).encrypt(iv, payload, None)
        b64 = lambda b: base64.b64encode(b).decode()
        with open(os.path.join(DOCS, "data.enc"), "w") as f:
            json.dump({"v": 1, "iter": ITER, "salt": b64(salt), "iv": b64(iv), "ct": b64(ct)}, f)
        for stale in ("data.json",):
            sp = os.path.join(DOCS, stale)
            if os.path.exists(sp):
                os.remove(sp)
        print(f"verschluesselt -> docs/data.enc ({len(ct)/1024:.0f} KB)")
    else:
        with open(os.path.join(DOCS, "data.json"), "w", encoding="utf-8") as f:
            f.write(payload.decode())
        print("WARNUNG: kein PAGES_PASS gesetzt, Daten liegen unverschluesselt")
    shutil.copy(os.path.join(STATIC, "style.css"), os.path.join(DOCS, "style.css"))
    open(os.path.join(DOCS, ".nojekyll"), "w").close()
    print(f"{len(rows):,} Objekte exportiert")
    print(f"Datenbank: {stats['total']:,} Objekte, {stats['todo']:,} noch abzurufen")


if __name__ == "__main__":
    main()
