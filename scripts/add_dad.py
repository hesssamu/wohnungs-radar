#!/usr/bin/env python3
"""Insert the 14 flats Samuel's father sent on WhatsApp (06./08.08.2026), rented or not."""
import os, sys, json, re, glob

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import conn, parse_expose, qa, pictures, extract_array, courtage_pct

SCRATCH = "/private/tmp/claude-501/-Users-samuelhess/c26d427b-d040-44f1-a8c7-1668a5517a99/scratchpad"

# id -> (Bundesland, expected rent if the listing states none, note)
DAD = {
    "165123879": "bayern", "164425660": "bayern", "164424272": "bayern",
    "169141915": "bayern", "169406303": "bayern", "165445249": "bayern",
    "169283416": "bayern", "168299040": "bayern", "169482110": "bayern",
    "169314903": "bayern",
    "169534501": "baden-wuerttemberg", "166076396": "baden-wuerttemberg",
    "168988190": "baden-wuerttemberg", "169725315": "baden-wuerttemberg",
}


def money(s):
    if not s:
        return None
    s = re.sub(r"[^\d.,]", "", str(s)).replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def og_images(h):
    """Expose pages carry photo URLs inline; /usercontent/ is the agent's logo, not the flat."""
    raw = re.findall(r'pictures\.immobilienscout24\.de/listings/[^"\'\\ )]{20,180}', h)
    seen, out = set(), []
    for u in raw:
        u = u.replace("\\/", "/")
        u = re.sub(r"/ORIG/[^/]+/[^/]+", "/ORIG/resize/400x300%3E", u, count=1)
        u = "https://" + u
        key = u.split("/listings/")[1].split("/")[0]
        if key in seen:
            continue
        seen.add(key)
        out.append(u)
        if len(out) >= 6:
            break
    return out


c = conn()
added = 0
for eid, land in DAD.items():
    path = f"{SCRATCH}/is24/{eid}.html"
    if not os.path.exists(path):
        print(f"  kein Cache für {eid}")
        continue
    h = open(path, encoding="utf-8", errors="ignore").read()
    title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", (re.search(r"<title>(.*?)</title>", h, re.S) or [None, ""])[1])).strip()
    price = money(qa(h, "kaufpreis"))
    qm = money(qa(h, "wohnflaeche-ca"))
    rooms = money(qa(h, "zimmer"))
    if not price or not qm:
        print(f"  {eid}: Preis/Fläche fehlt")
        continue
    plz = (re.search(r'"postalCode":"(\d{5})"', h) or [None, ""])[1]
    city = (re.search(r'"city":"([^"]{1,60})"', h) or [None, ""])[1]
    quarter = (re.search(r'"quarter":"([^"]{1,60})"', h) or [None, ""])[1]
    street = (re.search(r'"street":"([^"]{1,60})"', h) or [None, ""])[1]
    prov = qa(h, "provision") or ""
    cp = 0.0357
    low = prov.lower()
    if "frei" in low or low.strip() in ("nein", "keine"):
        cp = 0.0
    else:
        m = re.search(r"(\d{1,2}[,.]\d{1,3})\s*%", prov) or re.search(r"(\d{1,2})\s*%", prov)
        if m:
            cp = float(m.group(1).replace(",", ".")) / 100
    imgs = og_images(h)
    p = parse_expose(h) or {}

    c.execute("""INSERT INTO listings
      (id,source,url,title,ort,quarter,plz,land,street,price,qm,rooms,bj,
       courtage_pct,courtage_txt,img,imgs,tags,rent,rent_evidence,rent_class,rent_status,
       hausgeld,denkmal,zustand,etage,multi,soll,is_dad,list_seen_at,expose_at)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,datetime('now'),datetime('now'))
      ON CONFLICT(id) DO UPDATE SET is_dad=1,
        img=COALESCE(listings.img, excluded.img),
        imgs=COALESCE(listings.imgs, excluded.imgs),
        title=excluded.title, land=excluded.land""",
              (eid, "is24", f"https://www.immobilienscout24.de/expose/{eid}", title[:180],
               city, quarter, plz, land, street, price, qm, rooms, p.get("bj"),
               cp, prov[:120], imgs[0] if imgs else None,
               json.dumps(imgs, ensure_ascii=False), json.dumps([], ensure_ascii=False),
               p.get("rent"), p.get("rent_evidence"), p.get("rent_class"),
               p.get("rent_status") or "none", p.get("hausgeld"), p.get("denkmal") or 0,
               p.get("zustand"), p.get("etage"), p.get("multi") or 0, p.get("soll") or 0))
    added += 1

c.commit()
n = c.execute("SELECT COUNT(*) n FROM listings WHERE is_dad=1").fetchone()["n"]
withrent = c.execute("SELECT COUNT(*) n FROM listings WHERE is_dad=1 AND rent IS NOT NULL").fetchone()["n"]
withimg = c.execute("SELECT COUNT(*) n FROM listings WHERE is_dad=1 AND img IS NOT NULL").fetchone()["n"]
print(f"{added} verarbeitet -> {n} Objekte von Papa in der DB ({withrent} mit Ist-Miete, {withimg} mit Bild)")
