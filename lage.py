#!/usr/bin/env python3
"""
Lage- und Risikoeinstufung.

Zwei Quellen, beide belastbar:
  1. Gemeindeverzeichnis des Statistischen Bundesamts (data/gemeindeverzeichnis-master)
     -> Einwohnerzahl und Gemeindetyp, daraus die Ortsgrößenklasse.
  2. Der eigene Datenbestand -> Median-Kaufpreis je m² im Ort, als Perzentil
     gegen ganz Deutschland. Das ist der ehrlichste Näherungswert für
     wirtschaftliche Stärke, den man aus Inseraten ziehen kann: wo Wohnungen
     für 800 €/m² weggehen, schrumpft der Markt; wo sie 5.000 kosten, boomt er.

Was hier NICHT behauptet wird: eine Konjunkturprognose. Arbeitslosenquote und
Bevölkerungsentwicklung stecken nicht drin — die brauchen eine eigene Quelle.
"""
import os, re, sys, glob, statistics

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import conn, ROOT

GV = os.path.join(ROOT, "data", "gemeindeverzeichnis-master", "data")

SIZE_CLASSES = [
    (500_000, "metropole", "Metropole"),
    (100_000, "grossstadt", "Großstadt"),
    (20_000, "mittelstadt", "Mittelstadt"),
    (5_000, "kleinstadt", "Kleinstadt"),
    (0, "land", "Landgemeinde"),
]


def norm(s):
    s = (s or "").lower().strip()
    s = s.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    s = re.sub(r"\b(stadt|gemeinde|markt|kreisfreie)\b", "", s)
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s


def load_gemeinden():
    """PLZ -> Einwohner und Ortsname -> Einwohner. Ohne YAML-Bibliothek: die
    Dateien sind flache 'Schlüssel: Wert'-Listen."""
    by_plz, by_name = {}, {}
    for f in glob.glob(os.path.join(GV, "*.yaml")):
        d = {}
        try:
            with open(f, encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    if ":" not in line or line.startswith("---"):
                        continue
                    k, _, v = line.partition(":")
                    d[k.strip()] = v.strip().strip("'\"")
        except OSError:
            continue
        try:
            ew = int(d.get("Einwohner gesamt", "") or 0)
        except ValueError:
            continue
        if ew <= 0:
            continue
        typ = d.get("Gemeindetyp", "")
        entry = (ew, typ, d.get("Kreisname", ""), d.get("Bundesland", ""))
        m = re.match(r"(\d{5})\s+(.*)", d.get("PLZ Gemeindenamen", ""))
        if m:
            plz, name = m.group(1), m.group(2)
            if by_plz.get(plz, (0,))[0] < ew:
                by_plz[plz] = entry
            n = norm(name.split(",")[0])
            if n and by_name.get(n, (0,))[0] < ew:
                by_name[n] = entry
        m2 = re.match(r"(\d{5})\s+(.*)", d.get("PLZ Ort", ""))
        if m2 and m2.group(1) not in by_plz:
            by_plz[m2.group(1)] = entry
    return by_plz, by_name


def size_of(ew):
    for lim, key, label in SIZE_CLASSES:
        if ew >= lim:
            return key, label
    return "land", "Landgemeinde"


def market_levels(c):
    """Median €/m² je Ort (ab 3 Angeboten) und dessen Perzentil bundesweit."""
    rows = c.execute("SELECT ort, price, qm FROM listings WHERE ort<>'' AND qm>0").fetchall()
    per_ort = {}
    for r in rows:
        per_ort.setdefault(r["ort"], []).append(r["price"] / r["qm"])
    med = {o: statistics.median(v) for o, v in per_ort.items() if len(v) >= 3}
    if not med:
        return {}, {}
    ordered = sorted(med.values())
    def pct(x):
        lo, hi = 0, len(ordered)
        while lo < hi:
            mid = (lo + hi) // 2
            if ordered[mid] < x:
                lo = mid + 1
            else:
                hi = mid
        return lo / len(ordered)
    return med, {o: pct(v) for o, v in med.items()}


def risk(row, ew, pqm, med_pqm):
    """0 = ruhig, 100 = heikel. Jeder Punkt hat einen nachvollziehbaren Grund."""
    s, why = 0, []
    rent = row["rent"]
    if rent:
        br = rent * 12 / row["price"]
        if br > .09:
            s += 30; why.append("Bruttorendite über 9 % — so etwas hat fast immer einen Grund")
        elif br > .08:
            s += 22; why.append("Bruttorendite über 8 %")
        elif br > .07:
            s += 12; why.append("Bruttorendite über 7 %")
        hg = row["hausgeld"]
        if hg and hg / rent > .40:
            s += 14; why.append("Hausgeld frisst über 40 % der Miete")
        elif hg and hg / rent > .30:
            s += 7; why.append("Hausgeld über 30 % der Miete")
    if pqm < 800:
        s += 20; why.append("unter 800 €/m² — struktureller Abschwung")
    elif pqm < 1200:
        s += 11; why.append("unter 1.200 €/m²")
    if ew is not None:
        if ew < 5_000:
            s += 18; why.append("Landgemeinde, dünner Mietermarkt")
        elif ew < 20_000:
            s += 10; why.append("Kleinstadt")
    else:
        s += 5; why.append("Ort nicht im Gemeindeverzeichnis gefunden")
    bj = row["bj"]
    zu = (row["zustand"] or "").lower()
    if bj and bj < 1950 and not any(w in zu for w in ("saniert", "modernis", "neuwertig")):
        s += 12; why.append("Baujahr vor 1950 ohne ausgewiesene Sanierung")
    if row["hausgeld"] is None:
        s += 8; why.append("Hausgeld steht nicht im Inserat")
    if row["denkmal"]:
        s += 8; why.append("Denkmalschutz — bessere AfA, aber Sanierungsauflagen")
    if row["multi"]:
        s += 6; why.append("Paket aus mehreren Einheiten")
    if row["soll"]:
        s += 10; why.append("Miete ist eine Soll-Angabe, kein laufender Vertrag")
    if (row["courtage_pct"] or 0) > .035:
        s += 4; why.append("hohe Käufercourtage")
    return min(100, s), why


def band(s):
    if s < 25:
        return "niedrig"
    if s < 45:
        return "mittel"
    if s < 65:
        return "erhöht"
    return "hoch"


def main():
    c = conn()
    for col, typ in (("ew", "INTEGER"), ("ortgroesse", "TEXT"), ("marktniveau", "REAL"),
                     ("med_pqm", "REAL"), ("risiko", "INTEGER"), ("risiko_band", "TEXT"),
                     ("risiko_gruende", "TEXT"), ("kreis", "TEXT")):
        try:
            c.execute(f"ALTER TABLE listings ADD COLUMN {col} {typ}")
        except Exception:
            pass

    by_plz, by_name = load_gemeinden()
    print(f"Gemeindeverzeichnis: {len(by_plz):,} PLZ, {len(by_name):,} Ortsnamen")
    med, pctl = market_levels(c)
    print(f"Marktniveau berechnet für {len(med):,} Orte (ab 3 Angeboten)")

    rows = c.execute("SELECT * FROM listings").fetchall()
    hit = miss = 0
    for r in rows:
        e = by_plz.get((r["plz"] or "").strip()) or by_name.get(norm(r["ort"]))
        ew = e[0] if e else None
        kreis = e[2] if e else None
        hit += 1 if e else 0
        miss += 0 if e else 1
        key, _ = size_of(ew) if ew else ("unbekannt", "unbekannt")
        pqm = r["price"] / r["qm"] if r["qm"] else 0
        sc, why = risk(r, ew, pqm, med.get(r["ort"]))
        c.execute("""UPDATE listings SET ew=?, ortgroesse=?, marktniveau=?, med_pqm=?,
                     risiko=?, risiko_band=?, risiko_gruende=?, kreis=? WHERE id=?""",
                  (ew, key, pctl.get(r["ort"]), med.get(r["ort"]), sc, band(sc),
                   " · ".join(why), kreis, r["id"]))
    c.commit()
    print(f"Ort zugeordnet: {hit:,} | nicht gefunden: {miss:,}")
    for b in ("niedrig", "mittel", "erhöht", "hoch"):
        n = c.execute("SELECT COUNT(*) n FROM listings WHERE risiko_band=? AND rent IS NOT NULL", (b,)).fetchone()["n"]
        print(f"  Risiko {b:<8} {n:,} Objekte mit Miete")
    for k, lab in [(k, l) for _, k, l in SIZE_CLASSES]:
        n = c.execute("SELECT COUNT(*) n FROM listings WHERE ortgroesse=?", (k,)).fetchone()["n"]
        print(f"  {lab:<14} {n:,}")


if __name__ == "__main__":
    main()
