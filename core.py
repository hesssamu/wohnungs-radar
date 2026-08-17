#!/usr/bin/env python3
"""Wohnungs-Radar — shared database, parsing and yield model."""
import json, os, re, sqlite3, html as _html

ROOT = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(ROOT, "data", "wohnungen.db")
CACHE = os.path.join(ROOT, "data", "cache")
UA = "WhatsApp/2.23.20.0"

SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
  id TEXT PRIMARY KEY,
  source TEXT NOT NULL DEFAULT 'is24',
  url TEXT,
  title TEXT,
  ort TEXT, quarter TEXT, plz TEXT, land TEXT, street TEXT,
  lat REAL, lon REAL,
  price REAL, qm REAL, rooms REAL, bj INTEGER,
  courtage_pct REAL, courtage_txt TEXT,
  img TEXT, imgs TEXT, tags TEXT,
  balcony INTEGER, lift INTEGER, cellar INTEGER, garden INTEGER, ebk INTEGER,
  rent REAL, rent_evidence TEXT, rent_class INTEGER,
  rent_status TEXT DEFAULT 'todo',      -- todo | ok | none | gone
  hausgeld REAL, denkmal INTEGER, zustand TEXT, etage TEXT,
  multi INTEGER DEFAULT 0, soll INTEGER DEFAULT 0,
  is_dad INTEGER DEFAULT 0,
  note TEXT, starred INTEGER DEFAULT 0,
  list_seen_at TEXT, expose_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_status ON listings(rent_status);
CREATE INDEX IF NOT EXISTS ix_price ON listings(price);
CREATE INDEX IF NOT EXISTS ix_rent ON listings(rent);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
"""


def conn():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    c = sqlite3.connect(DB, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.executescript(SCHEMA)
    return c


def setmeta(c, k, v):
    c.execute("INSERT INTO meta(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, str(v)))


def getmeta(c, k, d=None):
    r = c.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
    return r["v"] if r else d


# ---------------------------------------------------------------- parsing ---
def extract_array(h, key):
    """Pull a balanced JSON array out of an HTML blob."""
    i = h.find(f'"{key}":')
    if i < 0:
        return None
    j = h.find("[", i)
    if j < 0:
        return None
    depth = 0
    instr = esc = False
    for k in range(j, len(h)):
        c = h[k]
        if instr:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                instr = False
        else:
            if c == '"':
                instr = True
            elif c in "[{":
                depth += 1
            elif c in "]}":
                depth -= 1
                if depth == 0:
                    return h[j:k + 1]
    return None


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def courtage_pct(c):
    """IS24 courtage object -> buyer commission as a fraction."""
    if not isinstance(c, dict):
        return 0.0357, ""
    has = (c.get("hasCourtage") or "").upper()
    txt = c.get("courtage") or c.get("minimumCourtage") or ""
    if has == "NO":
        return 0.0, "provisionsfrei"
    if isinstance(txt, str) and txt:
        low = txt.lower()
        if "frei" in low or "keine" in low:
            return 0.0, txt
        m = re.search(r"(\d{1,2}[,.]\d{1,3})\s*%", txt)
        if m:
            return float(m.group(1).replace(",", ".")) / 100, txt
        m = re.search(r"(\d{1,2})\s*%", txt)
        if m:
            return float(m.group(1)) / 100, txt
    return 0.0357, (txt if isinstance(txt, str) else "")


def pictures(re_, w=400, h=300, limit=6):
    ga = re_.get("galleryAttachments") or {}
    att = ga.get("attachment")
    if isinstance(att, dict):
        att = [att]
    out = []
    for a in (att or []):
        if str(a.get("floorplan")).lower() == "true":
            continue
        urls = a.get("urls")
        if isinstance(urls, dict):
            urls = [urls]
        for u in (urls or []):
            uu = u.get("url")
            if isinstance(uu, dict):
                uu = [uu]
            for one in (uu or []):
                href = one.get("@href")
                if href:
                    out.append(href.replace("%WIDTH%", str(w)).replace("%HEIGHT%", str(h)))
                    break
            break
        if len(out) >= limit:
            break
    return out


def parse_search_page(h, land_slug):
    """Return list of listing dicts from one IS24 search-result page."""
    arr = extract_array(h, "resultlistEntry")
    if not arr:
        return []
    try:
        entries = json.loads(arr)
    except json.JSONDecodeError:
        return []
    if isinstance(entries, dict):
        entries = [entries]
    rows = []
    for e in entries:
        re_ = e.get("resultlist.realEstate") or {}
        eid = str(e.get("realEstateId") or re_.get("@id") or "")
        price = num((re_.get("price") or {}).get("value"))
        qm = num(re_.get("livingSpace"))
        if not eid or not price or not qm or qm < 15 or price < 5000:
            continue
        a = re_.get("address") or {}
        geo = a.get("wgs84Coordinate") or {}
        cp, ct = courtage_pct(re_.get("courtage"))
        imgs = pictures(re_)
        tags = ((e.get("realEstateTags") or {}).get("tag")) or []
        if isinstance(tags, str):
            tags = [tags]
        yes = lambda k: 1 if str(re_.get(k)).lower() == "true" else 0
        rows.append(dict(
            id=eid, source="is24",
            url=f"https://www.immobilienscout24.de/expose/{eid}",
            title=(re_.get("title") or "").strip()[:180],
            ort=(a.get("city") or "").strip(), quarter=(a.get("quarter") or "").strip(),
            plz=(a.get("postcode") or "").strip(), land=land_slug.split("/")[0],
            street=(a.get("street") or "").strip(),
            lat=num(geo.get("latitude")), lon=num(geo.get("longitude")),
            price=price, qm=qm, rooms=num(re_.get("numberOfRooms")),
            bj=int(num(re_.get("constructionYear")) or 0) or None,
            courtage_pct=cp, courtage_txt=ct[:120],
            img=imgs[0] if imgs else None, imgs=json.dumps(imgs, ensure_ascii=False),
            tags=json.dumps(tags, ensure_ascii=False),
            balcony=yes("balcony"), lift=yes("lift"), cellar=yes("cellar"),
            garden=yes("garden"), ebk=yes("builtInKitchen"),
        ))
    return rows


UPSERT = """
INSERT INTO listings (id,source,url,title,ort,quarter,plz,land,street,lat,lon,
  price,qm,rooms,bj,courtage_pct,courtage_txt,img,imgs,tags,
  balcony,lift,cellar,garden,ebk,list_seen_at)
VALUES (:id,:source,:url,:title,:ort,:quarter,:plz,:land,:street,:lat,:lon,
  :price,:qm,:rooms,:bj,:courtage_pct,:courtage_txt,:img,:imgs,:tags,
  :balcony,:lift,:cellar,:garden,:ebk,datetime('now'))
ON CONFLICT(id) DO UPDATE SET
  price=excluded.price, qm=excluded.qm, rooms=excluded.rooms,
  bj=COALESCE(excluded.bj, listings.bj),
  img=COALESCE(excluded.img, listings.img),
  imgs=COALESCE(excluded.imgs, listings.imgs),
  tags=excluded.tags, courtage_pct=excluded.courtage_pct,
  courtage_txt=excluded.courtage_txt, title=excluded.title,
  list_seen_at=datetime('now')
"""


# ------------------------------------------------------------ expose parse ---
COLD_KW = r"(?:netto)?kaltmiete|grundmiete|nettomiete"
NEUTRAL_KW = r"mieteinnahmen|mietertrag|ist[- ]?miete|bestandsmiete"
WEAK_KW = r"vermietet\s+(?:für|zu)|miete\s+beträgt"
AMOUNT = r"([\d.]{2,9},?\d{0,2})\s*(?:€|EUR)"
PATS = [
    (1, re.compile(rf"{AMOUNT}\s*(?:€|EUR)?\s*(?:{COLD_KW})", re.I)),
    (1, re.compile(rf"(?:{COLD_KW})[^0-9€]{{0,45}}{AMOUNT}", re.I)),
    (2, re.compile(rf"(?:{NEUTRAL_KW})[^0-9€]{{0,45}}{AMOUNT}", re.I)),
    (3, re.compile(rf"(?:{WEAK_KW})[^0-9€]{{0,25}}{AMOUNT}", re.I)),
]
WARM = re.compile(r"inkl\.?\s*(?:der\s*)?(?:neben|betriebs)kosten|inklusive\s+(?:neben|betriebs)kosten|warmmiete|gesamtmiete|bruttomiete|inkl\.?\s*NK", re.I)
ESTIMATE = re.compile(r"soll[- ]?miete|erzielbar|realistisch|mietpotenzial|potenzielle?\s+miete|angestrebt|nicht\s+vermietet|derzeit\s+leer|leerstehend|unvermietet|nach\s+sanierung", re.I)
ANNUAL = re.compile(r"p\.?\s?a\.?|pro\s+Jahr|jährlich|/\s?Jahr", re.I)
MULTI = re.compile(r"investmentpaket|doppelpack|\b[2-9]\s*(?:WE|Wohneinheiten|Wohnungen|Eigentumswohnungen)\b|paket\s+aus\s+\d", re.I)
SOLL = re.compile(r"neue\s+(?:netto)?kaltmiete|nachmieter|miethöhe\s+(?:wird\s+)?angepasst", re.I)
HG_PAT = re.compile(r"(?:hausgeld|wohngeld)[^0-9€]{0,45}([\d.]{2,7},?\d{0,2})\s*(?:€|EUR)", re.I)


def _money(s):
    try:
        return float(s.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def qa(h, key):
    m = re.search(rf'class="[^"]*is24qa-{re.escape(key)}(?![a-z-])[^"]*"[^>]*>(.*?)</', h, re.S)
    if not m:
        return None
    v = re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", m.group(1)))).strip()
    return v if v and v != "-" else None


def description(h):
    parts = []
    for fld in ("objectDescription", "otherNote", "furnishingNote", "locationDescription"):
        m = re.search(rf'"{fld}":"((?:[^"\\]|\\.)*)"', h)
        if m:
            try:
                parts.append(json.loads('"' + m.group(1) + '"'))
            except json.JSONDecodeError:
                pass
    return re.sub(r"\s+", " ", " ".join(parts))


YEARLY_PREFIX = re.compile(r"(?:jahres|jährliche?r?)\s*$", re.I)


def extract_rent(txt, qm=None):
    """
    Most explicitly labelled cold rent wins — never simply the biggest number.
    Annual figures appear both as a suffix ("340 € p.a.") and as a prefix
    ("Jahresnettokaltmiete 3.211,20 €"); both must be divided by 12.
    """
    hits = []
    for cls, pat in PATS:
        for m in pat.finditer(txt):
            v = _money(m.group(1))
            if v is None:
                continue
            near = txt[max(0, m.start() - 30):m.end() + 35]
            wide = txt[max(0, m.start() - 130):m.end() + 130]
            if ESTIMATE.search(wide):
                continue
            if cls > 1 and WARM.search(near):
                continue
            annual = bool(ANNUAL.search(txt[m.end():m.end() + 22]))
            # "Jahres…miete" / "jährliche Kaltmiete" — the marker sits before the keyword
            if not annual and YEARLY_PREFIX.search(txt[max(0, m.start() - 14):m.start() + 1]):
                annual = True
            if not annual:
                head = txt[max(0, m.start() - 20):m.start() + 40].lower()
                if "jahres" in head or "jährlich" in head:
                    annual = True
            if annual:
                v /= 12
            if not (120 <= v <= 4500):
                continue
            if qm and not (2.0 <= v / qm <= 30.0):   # implausible €/m² -> parse artefact
                continue
            hits.append((cls, m.start(), v, wide))
    if not hits:
        return None, None, None
    hits.sort(key=lambda t: (t[0], t[1]))
    cls, _, v, snip = hits[0]
    return v, snip[:190], cls


# A withdrawn listing still ships its full description and price, so it must be
# detected explicitly — otherwise a dead offer looks like a live bargain.
GONE_PAT = re.compile(r"Angebot wurde deaktiviert|Dieses Angebot ist nicht mehr verf|"
                      r"Angebot ist nicht mehr verf|wurde deaktiviert", re.I)


def is_gone(h):
    return bool(h) and bool(GONE_PAT.search(h))


def parse_expose(h, qm=None):
    if not h or "Ich bin kein Roboter" in h or len(h) < 40000:
        return None
    if is_gone(h):
        return dict(rent=None, rent_evidence=None, rent_class=None, rent_status="gone",
                    hausgeld=None, bj=None, denkmal=0, zustand=None, etage=None,
                    multi=0, soll=0)
    txt = description(h)
    rent, ev, cls = extract_rent(txt, qm)
    hg = None
    m = HG_PAT.search(txt)
    if m:
        v = _money(m.group(1))
        if v and 20 <= v <= 1200:
            hg = v
    if hg is None:
        v = qa(h, "hausgeld")
        if v:
            hg = _money(re.sub(r"[^\d.,]", "", v))
    bj = qa(h, "baujahr")
    return dict(
        rent=rent, rent_evidence=ev, rent_class=cls,
        rent_status="ok" if rent else "none",
        hausgeld=hg,
        bj=int(re.sub(r"[^\d]", "", bj)[:4]) if bj and re.sub(r"[^\d]", "", bj) else None,
        denkmal=1 if qa(h, "denkmalschutzobjekt") == "Ja" else 0,
        zustand=qa(h, "objektzustand"), etage=qa(h, "etage"),
        multi=1 if MULTI.search(txt[:1200]) else 0,
        soll=1 if (ev and SOLL.search(ev)) else 0,
    )


# ------------------------------------------------------------------ model ---
GREST = {"baden-wuerttemberg": .05, "bayern": .035, "berlin": .06, "brandenburg": .065,
         "bremen": .05, "hamburg": .055, "hessen": .06, "mecklenburg-vorpommern": .06,
         "niedersachsen": .05, "nordrhein-westfalen": .065, "rheinland-pfalz": .05,
         "saarland": .065, "sachsen": .055, "sachsen-anhalt": .05,
         "schleswig-holstein": .065, "thueringen": .05}

DEFAULTS = dict(ekq=.20, zins=.04, tilg=.02, tax=.425, hgf=4.0, hgn=.35, ausf=30.0, geb=.75)
