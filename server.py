#!/usr/bin/env python3
"""Wohnungs-Radar — local web app. Stdlib only, no dependencies."""
import base64, hmac, json, os, sys, re, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import conn, ROOT, GREST, DEFAULTS, getmeta

PORT = int(os.environ.get("PORT", "8840"))
STATIC = os.path.join(ROOT, "static")

# --- HTTP Basic Auth -------------------------------------------------------
# Credentials come from ~/.config/secrets/wohnungs-radar.env (never from the repo).
# With no password configured the app stays open on localhost only.
SECRETS = os.path.expanduser("~/.config/secrets/wohnungs-radar.env")
AUTH_USER, AUTH_PASS = os.environ.get("RADAR_USER"), os.environ.get("RADAR_PASS")
if not AUTH_PASS and os.path.exists(SECRETS):
    for line in open(SECRETS, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip().strip('"').strip("'")
        if k.strip() == "RADAR_USER":
            AUTH_USER = AUTH_USER or v
        elif k.strip() == "RADAR_PASS":
            AUTH_PASS = AUTH_PASS or v
AUTH_USER = AUTH_USER or "papa"
AUTH_ON = bool(AUTH_PASS)


def check_auth(header):
    if not AUTH_ON:
        return True
    if not header or not header.startswith("Basic "):
        return False
    try:
        raw = base64.b64decode(header[6:]).decode("utf-8", "replace")
    except (ValueError, UnicodeDecodeError):
        return False
    u, _, p = raw.partition(":")
    return hmac.compare_digest(u, AUTH_USER) and hmac.compare_digest(p, AUTH_PASS)

SORTS = {
    "brutto": "brutto DESC", "cf": "cf DESC", "ekr": "ekr DESC",
    "price_asc": "price ASC", "price_desc": "price DESC",
    "ek": "ekb ASC", "faktor": "faktor ASC", "pqm": "pqm ASC",
    "qm_desc": "qm DESC", "new": "list_seen_at DESC",
}


def f(qs, k, d=None, cast=float):
    v = qs.get(k, [None])[0]
    if v in (None, "", "null"):
        return d
    try:
        return cast(v)
    except (TypeError, ValueError):
        return d


def compute(row, a):
    price, qm, rent = row["price"], row["qm"], row["rent"]
    grest = GREST.get(row["land"] or "", .055)
    mk = row["courtage_pct"] if row["courtage_pct"] is not None else .0357
    nk = price * (grest + .015 + .005 + mk)
    ek = price * a["ekq"]
    fin = price - ek
    ekb = ek + nk
    rate = fin * (a["zins"] + a["tilg"]) / 12
    bj = row["bj"] or 1970
    afa = .03 if bj >= 2023 else (.025 if bj < 1925 else .02)
    afa_e = price * a["geb"] * afa / 12 * a["tax"]
    zins_e = fin * a["zins"] * a["tax"] / 12
    hg_total = row["hausgeld"] if row["hausgeld"] is not None else qm * a["hgf"]
    cf = (rent - rate - hg_total * a["hgn"] - a["ausf"] + afa_e + zins_e) if rent else None
    return dict(
        nk=nk, ekb=ekb, rate=rate, hg=hg_total, cf=cf,
        brutto=(rent * 12 / price) if rent else None,
        faktor=(price / (rent * 12)) if rent else None,
        ekr=(cf * 12 / ekb) if (rent and ekb > 0) else None,
        pqm=price / qm if qm else None,
        afa=afa,
    )


def search(qs):
    a = {k: f(qs, k, v) for k, v in DEFAULTS.items()}
    c = conn()
    where, args = ["1=1"], []

    if not f(qs, "showgone", 0, int):
        where.append("rent_status <> 'gone'")
    if not f(qs, "showdups", 0, int):
        where.append("(dup_of IS NULL)")
    if f(qs, "onlyrent", 1, int):
        where.append("rent IS NOT NULL")
    if f(qs, "dad", 0, int):
        where.append("is_dad=1")
    if f(qs, "starred", 0, int):
        where.append("starred=1")
    for key, col, op in (("pmin", "price", ">="), ("pmax", "price", "<="),
                         ("qmin", "qm", ">="), ("qmax", "qm", "<="),
                         ("zmin", "rooms", ">="), ("bjmin", "bj", ">=")):
        v = f(qs, key)
        if v is not None:
            where.append(f"{col} {op} ?")
            args.append(v)
    land = qs.get("land", [""])[0]
    if land:
        where.append("land = ?")
        args.append(land)
    q = (qs.get("q", [""])[0] or "").strip()
    if q:
        where.append("(ort LIKE ? OR quarter LIKE ? OR plz LIKE ? OR title LIKE ?)")
        args += [f"%{q}%"] * 4
    for flag in ("balcony", "lift", "cellar", "ebk", "garden"):
        if f(qs, flag, 0, int):
            where.append(f"{flag}=1")
    if f(qs, "nocourtage", 0, int):
        where.append("courtage_pct = 0")
    if f(qs, "nomulti", 0, int):
        where.append("multi = 0")
    og = qs.get("ortgroesse", [""])[0]
    if og:
        where.append("ortgroesse IN (%s)" % ",".join("?" * len(og.split(","))))
        args += og.split(",")
    rmax = f(qs, "risikomax")
    if rmax is not None:
        where.append("risiko <= ?")
        args.append(rmax)
    mn = f(qs, "marktmin")
    if mn is not None:
        where.append("marktniveau >= ?")
        args.append(mn / 100.0)

    rows = c.execute(f"SELECT * FROM listings WHERE {' AND '.join(where)}", args).fetchall()

    rmin = f(qs, "rmin")
    cfmin = f(qs, "cfmin")
    ekmax = f(qs, "ekmax")
    out = []
    for r in rows:
        m = compute(r, a)
        if rmin is not None and (m["brutto"] is None or m["brutto"] * 100 < rmin):
            continue
        if cfmin is not None and (m["cf"] is None or m["cf"] < cfmin):
            continue
        if ekmax is not None and m["ekb"] > ekmax:
            continue
        d = dict(r)
        d.pop("imgs", None)
        d["m"] = {k: (round(v, 6) if isinstance(v, float) else v) for k, v in m.items()}
        try:
            d["taglist"] = json.loads(r["tags"] or "[]")
        except json.JSONDecodeError:
            d["taglist"] = []
        d.pop("tags", None)
        out.append(d)

    order = qs.get("sort", ["brutto"])[0]
    keyf = {
        "brutto": lambda x: -(x["m"]["brutto"] or -9), "cf": lambda x: -(x["m"]["cf"] or -9e9),
        "ekr": lambda x: -(x["m"]["ekr"] or -9), "price_asc": lambda x: x["price"],
        "price_desc": lambda x: -x["price"], "ek": lambda x: x["m"]["ekb"],
        "faktor": lambda x: (x["m"]["faktor"] or 9e9), "pqm": lambda x: (x["m"]["pqm"] or 9e9),
        "qm_desc": lambda x: -x["qm"], "new": lambda x: (x["list_seen_at"] or ""),
    }.get(order, lambda x: -(x["m"]["brutto"] or -9))
    out.sort(key=keyf, reverse=(order == "new"))

    total = len(out)
    page = int(f(qs, "page", 1, int) or 1)
    per = min(int(f(qs, "per", 25, int) or 25), 100)
    return {"total": total, "page": page, "per": per,
            "items": out[(page - 1) * per: page * per]}


def stats():
    c = conn()
    g = lambda q: c.execute(q).fetchone()["n"]
    return {
        "total": g("SELECT COUNT(*) n FROM listings"),
        "with_rent": g("SELECT COUNT(*) n FROM listings WHERE rent IS NOT NULL"),
        "todo": g("SELECT COUNT(*) n FROM listings WHERE rent_status='todo'"),
        "orte": g("SELECT COUNT(DISTINCT ort) n FROM listings"),
        "dad": g("SELECT COUNT(*) n FROM listings WHERE is_dad=1"),
        "starred": g("SELECT COUNT(*) n FROM listings WHERE starred=1"),
        "gone": g("SELECT COUNT(*) n FROM listings WHERE rent_status='gone'"),
        "groessen": [dict(r) for r in conn().execute(
            "SELECT ortgroesse k, COUNT(*) n FROM listings WHERE ortgroesse IS NOT NULL GROUP BY ortgroesse")],
        "laender": [dict(r) for r in c.execute(
            "SELECT land, COUNT(*) n FROM listings WHERE land<>'' GROUP BY land ORDER BY land")],
        "progress": getmeta(c, "worker_progress", ""),
    }


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _guard(self):
        """Return True if the request may proceed; otherwise answer 401 itself."""
        if check_auth(self.headers.get("Authorization")):
            return True
        body = b"Passwort erforderlich."
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Wohnungs-Radar", charset="UTF-8"')
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return False

    def do_GET(self):
        if not self._guard():
            return
        u = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(u.query)
        if u.path == "/api/search":
            return self._send(200, search(qs))
        if u.path == "/api/stats":
            return self._send(200, stats())
        if u.path == "/api/detail":
            c = conn()
            r = c.execute("SELECT * FROM listings WHERE id=?", (qs.get("id", [""])[0],)).fetchone()
            if not r:
                return self._send(404, {"error": "not found"})
            d = dict(r)
            try:
                d["imglist"] = json.loads(r["imgs"] or "[]")
            except json.JSONDecodeError:
                d["imglist"] = []
            return self._send(200, d)
        path = "index.html" if u.path in ("/", "") else u.path.lstrip("/")
        fp = os.path.normpath(os.path.join(STATIC, path))
        if not fp.startswith(STATIC) or not os.path.isfile(fp):
            return self._send(404, "not found", "text/plain")
        ctype = {"html": "text/html; charset=utf-8", "css": "text/css; charset=utf-8",
                 "js": "application/javascript; charset=utf-8",
                 "svg": "image/svg+xml", "ico": "image/x-icon"}.get(fp.rsplit(".", 1)[-1], "application/octet-stream")
        with open(fp, "rb") as fh:
            return self._send(200, fh.read(), ctype)

    def do_POST(self):
        if not self._guard():
            return
        u = urllib.parse.urlparse(self.path)
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            body = {}
        c = conn()
        if u.path == "/api/star":
            c.execute("UPDATE listings SET starred=? WHERE id=?",
                      (1 if body.get("on") else 0, body.get("id")))
            c.commit()
            return self._send(200, {"ok": True})
        if u.path == "/api/note":
            c.execute("UPDATE listings SET note=? WHERE id=?", (body.get("note", ""), body.get("id")))
            c.commit()
            return self._send(200, {"ok": True})
        return self._send(404, {"error": "unknown"})


def tailscale_ip():
    """The 100.x address of this machine, if Tailscale is up — reachable from Samuel's
    other devices only, never from the open internet."""
    import subprocess
    for exe in ("/Applications/Tailscale.app/Contents/MacOS/Tailscale", "tailscale"):
        try:
            out = subprocess.run([exe, "ip", "-4"], capture_output=True, text=True, timeout=5)
            ip = (out.stdout or "").strip().splitlines()
            if ip and ip[0].startswith("100."):
                return ip[0].strip()
        except (OSError, subprocess.SubprocessError):
            continue
    return None


if __name__ == "__main__":
    import threading

    hosts = []
    override = os.environ.get("HOST")
    if override:
        hosts = [override]
    else:
        hosts = ["127.0.0.1"]
        ts = tailscale_ip()
        if ts:
            hosts.append(ts)

    st = stats()
    servers = []
    for h in hosts:
        try:
            servers.append(ThreadingHTTPServer((h, PORT), H))
        except OSError as e:
            print(f"  {h}:{PORT} nicht möglich ({e})")

    if not servers:
        raise SystemExit(f"Port {PORT} ist belegt. Anderen Port: PORT=8850 ./run.sh")

    print("Wohnungs-Radar" + ("  [Passwort aktiv]" if AUTH_ON else "  [ohne Passwort]"))
    for s in servers:
        a = s.server_address[0]
        print(f"  http://{'localhost' if a == '127.0.0.1' else a}:{PORT}"
              + ("   <- von deinem MacBook / iPhone über Tailscale" if a.startswith("100.") else ""))
    print(f"{st['total']:,} Objekte | {st['with_rent']:,} mit Miete | {st['todo']:,} werden noch geladen")

    for s in servers[1:]:
        threading.Thread(target=s.serve_forever, daemon=True).start()
    servers[0].serve_forever()
