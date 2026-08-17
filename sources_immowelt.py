#!/usr/bin/env python3
"""
Immowelt als zweite Quelle.

Bundesweite Kapitalanlage-Suche (~18.000 Angebote, 27 je Seite, Blaettern ueber ?sp=N).
Laeuft parallel zum ImmoScout-Worker, weil es eine andere Seite mit eigener
Drosselung ist — die beiden bremsen sich nicht gegenseitig.

  python3 sources_immowelt.py ids        # nur die Trefferliste einsammeln
  python3 sources_immowelt.py exposes    # Exposés nachladen
  python3 sources_immowelt.py            # beides nacheinander
"""
import html as _html
import json, os, re, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import conn, ROOT, UA, setmeta

BASE = "https://www.immowelt.de/suche/kaufen/immobilien/kapitalanlage/deutschland/ad02de1"
CACHE = os.path.join(ROOT, "data", "iw")
DELAY = 2.0
UUID = re.compile(r"expose/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})")


def get(url, path, tries=3):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path) and os.path.getsize(path) > 60000:
        return open(path, encoding="utf-8", errors="ignore").read()
    for i in range(tries):
        subprocess.run(["curl", "-s", "-m", "35", "--compressed", "-A", UA, "-o", path, url],
                       check=False)
        try:
            h = open(path, encoding="utf-8", errors="ignore").read()
        except OSError:
            h = ""
        if len(h) > 60000 and "captcha" not in h.lower():
            return h
        time.sleep(10 * (i + 1))
    return ""


def text_of(h):
    t = re.sub(r"<[^>]+>", " ", h)
    return _html.unescape(re.sub(r"\s+", " ", t))


def money(s):
    try:
        return float(s.replace(".", "").replace(",", "."))
    except (ValueError, AttributeError):
        return None


def parse_expose(uid, h):
    """Kaufpreis, Flaeche, Zimmer, PLZ und Ort stehen im ld+json, der Rest im Text."""
    if not h or len(h) < 60000:
        return None
    d = {"id": "iw-" + uid, "source": "immowelt",
         "url": f"https://www.immowelt.de/expose/{uid}"}

    name = None
    for m in re.finditer(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', h, re.S):
        try:
            j = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(j, dict) and j.get("@type") == "RealEstateListing":
            name = j.get("name") or j.get("description")
    # "Wohnung 45 m² 170000 € zum Kauf Köpenick,Berlin (12557)"
    if name:
        m = re.search(r"([\d.,]+)\s*m²\s*([\d.]+)\s*€.*?zum Kauf\s*(.*?)\s*\((\d{5})\)", name)
        if m:
            d["qm"] = money(m.group(1))
            d["price"] = money(m.group(2))
            loc = m.group(3).split(",")
            d["quarter"] = loc[0].strip() if len(loc) > 1 else ""
            d["ort"] = loc[-1].strip()
            d["plz"] = m.group(4)

    t = text_of(h)
    if not d.get("price"):
        m = re.search(r"Kaufpreis\s*([\d.]+)\s*€", t)
        if m:
            d["price"] = money(m.group(1))
    if not d.get("qm"):
        m = re.search(r"([\d.,]+)\s*m²\s*Wohnfläche|Wohnfläche\s*([\d.,]+)\s*m²", t)
        if m:
            d["qm"] = money(m.group(1) or m.group(2))
    m = re.search(r"([\d,]+)\s*Zimmer", t)
    if m:
        d["rooms"] = money(m.group(1))
    m = re.search(r"Baujahr\s*(1[89]\d\d|20[0-3]\d)", t)
    if m:
        d["bj"] = int(m.group(1))
    m = re.search(r"Hausgeld\s*([\d.]+)\s*€", t)
    if m:
        d["hausgeld"] = money(m.group(1))
    d["courtage_pct"] = 0.0 if re.search(r"provisionsfrei|keine Provision|Provision.{0,12}0\s*%", t, re.I) else 0.0357
    mt = re.search(r"<title>(.*?)</title>", h, re.S)
    d["title"] = re.sub(r"\s*[-|]\s*immowelt.*$", "", text_of(mt.group(1)))[:180] if mt else ""
    m = re.search(r"https://media\.immowelt\.org/[^\"'\\ )]{10,120}", h)
    d["img"] = m.group(0) if m else None

    # Miete: dieselbe Logik wie bei ImmoScout, nur auf den Beschreibungstext
    from core import extract_rent
    rent, ev, cls = extract_rent(t, d.get("qm"))
    d["rent"], d["rent_evidence"], d["rent_class"] = rent, ev, cls
    d["rent_status"] = "ok" if rent else "none"
    if not d.get("price") or not d.get("qm"):
        return None
    return d


def collect_ids(max_pages=680):
    c = conn()
    seen = set()
    for pg in range(1, max_pages + 1):
        url = BASE + (f"?sp={pg}" if pg > 1 else "")
        h = get(url, os.path.join(CACHE, "s", f"{pg}.html"))
        if not h:
            print(f"  Seite {pg} nicht ladbar", flush=True)
            continue
        ids = set(UUID.findall(h))
        new = ids - seen
        seen |= ids
        for uid in new:
            c.execute("""INSERT OR IGNORE INTO listings (id, source, url, rent_status, list_seen_at)
                         VALUES (?, 'immowelt', ?, 'todo', datetime('now'))""",
                      ("iw-" + uid, f"https://www.immowelt.de/expose/{uid}"))
        if pg % 25 == 0:
            c.commit()
            print(f"  Seite {pg}: {len(seen):,} Angebote gefunden", flush=True)
        if not ids:
            print(f"  Seite {pg} leer — Ende", flush=True)
            break
        time.sleep(DELAY)
    c.commit()
    print(f"Immowelt: {len(seen):,} Angebote in der Liste", flush=True)


def fetch_exposes(limit=None):
    c = conn()
    q = "SELECT id FROM listings WHERE source='immowelt' AND rent_status='todo' AND price IS NULL"
    if limit:
        q += f" LIMIT {int(limit)}"
    ids = [r["id"] for r in c.execute(q).fetchall()]
    print(f"{len(ids):,} Immowelt-Exposés abzurufen", flush=True)
    ok = fail = 0
    for i, rid in enumerate(ids, 1):
        uid = rid[3:]
        h = get(f"https://www.immowelt.de/expose/{uid}", os.path.join(CACHE, "e", f"{uid}.html"))
        d = parse_expose(uid, h) if h else None
        if not d:
            c.execute("UPDATE listings SET rent_status='gone' WHERE id=?", (rid,))
            fail += 1
        else:
            c.execute("""UPDATE listings SET title=?, ort=?, quarter=?, plz=?, price=?, qm=?,
                         rooms=?, bj=?, hausgeld=?, courtage_pct=?, img=?, rent=?,
                         rent_evidence=?, rent_class=?, rent_status=?, expose_at=datetime('now')
                         WHERE id=?""",
                      (d.get("title"), d.get("ort"), d.get("quarter"), d.get("plz"),
                       d.get("price"), d.get("qm"), d.get("rooms"), d.get("bj"),
                       d.get("hausgeld"), d.get("courtage_pct"), d.get("img"), d.get("rent"),
                       d.get("rent_evidence"), d.get("rent_class"), d["rent_status"], rid))
            ok += 1
        if i % 50 == 0:
            c.commit()
            mit = c.execute("SELECT COUNT(*) n FROM listings WHERE source='immowelt' AND rent IS NOT NULL").fetchone()["n"]
            print(f"  {i:,}/{len(ids):,} | brauchbar {ok:,} | verworfen {fail:,} | mit Miete {mit:,}", flush=True)
        time.sleep(DELAY)
    c.commit()
    print(f"Fertig: {ok:,} uebernommen, {fail:,} verworfen", flush=True)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    if mode in ("ids", "all"):
        collect_ids()
    if mode in ("exposes", "all"):
        fetch_exposes()
