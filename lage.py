#!/usr/bin/env python3
"""
Lage- und Risikoeinstufung — Fassung 2, gebaut auf recherchierte Fachpraxis
statt auf selbst gesetzte Gewichte.

Drei Befunde aus der Recherche, die diese Fassung praegen:

1. MIKROLAGE IST UEBER PLZ NICHT AUFLOESBAR. Messung an 60.000 Hamburger
   Adressen: 68,6 % der Postleitzahlen enthalten beide Wohnlagenklassen,
   mehrere praktisch haelftig. Eine Lagenote je PLZ waere Scheingenauigkeit.
   Deshalb gibt es hier bewusst KEINE Mikrolagenote.

2. DAS MARKTNIVEAU-PERZENTIL IST ENDOGEN. Der Median-Kaufpreis je m2 ist ein
   Marktergebnis, kein Ursachenindikator — er erklaert den Preis durch den
   Preis. Der Gutachterausschuss Duisburg schliesst den Bodenrichtwert aus
   der Wohnlagenklassifikation genau deshalb aus. In Fassung 1 hatte dieser
   Wert vollen Rang; jetzt zaehlt er nur noch zusammen mit anderen Signalen
   und ist als Naeherung gekennzeichnet.

3. RENDITESCHWELLEN GEHOEREN RELATIV ZUM ORT. Absolute Grenzen bestrafen
   guenstige Regionen und uebersehen Ausreisser in teuren. Deshalb zusaetzlich
   der Vergleich gegen den Median des jeweiligen Ortes.

Ohne belegte Ist-Miete gibt es KEIN Risikoband, sondern "nicht bewertbar".

Datenstand-Warnung: das Gemeindeverzeichnis in data/ hat Stand 31.12.2011 und
liegt damit vor der Zensus-2022-Korrektur. Fuer Groessenklassen brauchbar, fuer
Bevoelkerungsentwicklung nicht. Der amtliche Gemeindeschluessel (AGS) wird
mitgeschrieben — er ist der Schluessel zu INKAR, Regionalstatistik und Zensus,
ueber den die noch fehlenden Marktindikatoren nachgezogen werden koennen.
"""
import os, re, sys, glob, statistics

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import conn, ROOT

GV = os.path.join(ROOT, "data", "gemeindeverzeichnis-master", "data")

SIZE_CLASSES = [(500_000, "metropole", "Metropole"), (100_000, "grossstadt", "Großstadt"),
                (20_000, "mittelstadt", "Mittelstadt"), (5_000, "kleinstadt", "Kleinstadt"),
                (0, "land", "Landgemeinde")]

BANDS = [(25, "niedrig"), (45, "mittel"), (65, "erhöht"), (10**9, "hoch")]


def norm(s):
    s = (s or "").lower().strip()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(a, b)
    s = re.sub(r"\b(stadt|gemeinde|markt|kreisfreie)\b", "", s)
    return re.sub(r"[^a-z0-9]+", "", s)


def load_gemeinden():
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
        entry = (ew, d.get("Amtl.Gemeindeschlüssel", ""), d.get("Kreisname", ""))
        m = re.match(r"(\d{5})\s+(.*)", d.get("PLZ Gemeindenamen", ""))
        if m:
            if by_plz.get(m.group(1), (0,))[0] < ew:
                by_plz[m.group(1)] = entry
            n = norm(m.group(2).split(",")[0])
            if n and by_name.get(n, (0,))[0] < ew:
                by_name[n] = entry
        m2 = re.match(r"(\d{5})\s+", d.get("PLZ Ort", ""))
        if m2 and m2.group(1) not in by_plz:
            by_plz[m2.group(1)] = entry
    return by_plz, by_name


def size_of(ew):
    for lim, key, _ in SIZE_CLASSES:
        if ew >= lim:
            return key
    return "land"


def ort_stats(c):
    """Je Ort: Median-Kaufpreis/m2, Median-Bruttorendite, Median-Miete/m2, Anzahl."""
    rows = c.execute("""SELECT ort, price, qm, rent FROM listings
                        WHERE ort<>'' AND qm>0 AND rent_status<>'gone'""").fetchall()
    pq, bar, mq, cnt = {}, {}, {}, {}
    for r in rows:
        cnt[r["ort"]] = cnt.get(r["ort"], 0) + 1
        pq.setdefault(r["ort"], []).append(r["price"] / r["qm"])
        if r["rent"]:
            bar.setdefault(r["ort"], []).append(r["rent"] * 12 / r["price"])
            mq.setdefault(r["ort"], []).append(r["rent"] / r["qm"])
    med_pq = {o: statistics.median(v) for o, v in pq.items() if len(v) >= 3}
    med_bar = {o: statistics.median(v) for o, v in bar.items() if len(v) >= 5}
    med_mq = {o: statistics.median(v) for o, v in mq.items() if len(v) >= 5}
    ordered = sorted(med_pq.values())

    def pct(x):
        lo, hi = 0, len(ordered)
        while lo < hi:
            mid = (lo + hi) // 2
            if ordered[mid] < x:
                lo = mid + 1
            else:
                hi = mid
        return lo / len(ordered) if ordered else None

    return med_pq, {o: pct(v) for o, v in med_pq.items()}, med_bar, med_mq, cnt


def score(r, ags, ew, pqm, med_pq, med_bar, med_mq, n_ort):
    """Punkte nach der recherchierten Systematik. Jeder Punkt mit Begruendung."""
    pts, why = 0, []
    rent, price, qm = r["rent"], r["price"], r["qm"]
    ort = r["ort"]

    # --- Block A: Ertrags- und Preisplausibilitaet ---------------------------
    if rent:
        bar = rent * 12 / price
        if bar > .09:
            pts += 30; why.append(f"Bruttorendite {bar*100:.1f} % — weit über allem, was in den 68 untersuchten Wohnmärkten vorkommt (Core dort 2,1–3,7 %)")
        elif bar > .08:
            pts += 22; why.append(f"Bruttorendite {bar*100:.1f} %")
        elif bar > .07:
            pts += 12; why.append(f"Bruttorendite {bar*100:.1f} %")
        mb = med_bar.get(ort)
        if mb and bar > 1.6 * mb:
            pts += 10; why.append(f"Rendite {bar/mb:.1f}-fach über dem Ortsmedian — im Ort selbst ein Ausreißer")
        mm = med_mq.get(ort)
        if mm and (rent / qm) > 1.35 * mm:
            pts += 8; why.append(f"Miete {rent/qm:.1f} €/m² liegt {((rent/qm)/mm-1)*100:.0f} % über dem Ortsmedian — Lagesprünge erklären typisch nur rund 26 %")
        hg = r["hausgeld"]
        if hg:
            q = hg / rent
            if q > .40:
                pts += 14; why.append(f"Hausgeld frisst {q*100:.0f} % der Miete")
            elif q > .30:
                pts += 7; why.append(f"Hausgeld {q*100:.0f} % der Miete")
    nk = (r["courtage_pct"] or 0) + 0.0175 + {"bayern": .035, "berlin": .06, "hamburg": .055,
        "hessen": .06, "nordrhein-westfalen": .065, "brandenburg": .065, "saarland": .065,
        "schleswig-holstein": .065, "sachsen": .055}.get(r["land"], .05)
    if nk > .11:
        pts += 4; why.append(f"Kaufnebenkosten {nk*100:.1f} % — allein deren Amortisation dauert über zehn Jahre")

    # --- Block B: Objekt ------------------------------------------------------
    bj, zu = r["bj"], (r["zustand"] or "").lower()
    saniert = any(w in zu for w in ("saniert", "modernis", "neuwertig", "erstbezug"))
    if bj and bj < 1950 and not saniert:
        pts += 12; why.append("Baujahr vor 1950 ohne ausgewiesene Sanierung — Stränge, Elektrik, Fenster, Dach")
    elif bj and 1950 <= bj <= 1978 and not saniert:
        pts += 8; why.append("Nachkriegsbau ohne ausgewiesene Sanierung, ungedämmte Hülle")
    if r["denkmal"]:
        pts += 8; why.append("Denkmalschutz — bessere AfA, aber Auflagen und Genehmigungsvorbehalt")
    if r["multi"]:
        pts += 6; why.append("Paketangebot, Preis nicht auf die Einheit umrechenbar")
    et = (r["etage"] or "").lower()
    if re.search(r"\beg\b|erdgesch|souterrain|tiefpart", et) and not r["garden"]:
        pts += 4; why.append("Erdgeschoss ohne Garten")
    if re.search(r"dachgesch|\bdg\b", et) and not r["lift"]:
        pts += 4; why.append("Dachgeschoss ohne Aufzug")

    # --- Block C: Datenqualitaet ---------------------------------------------
    if r["soll"]:
        pts += 10; why.append("Miete ist eine Soll-Angabe, kein laufender Vertrag")
    if r["rent_class"] == 3:
        pts += 8; why.append("Miete nur schwach belegt")
    elif r["rent_class"] == 2:
        pts += 4; why.append("Miete indirekt belegt")
    if r["hausgeld"] is None:
        pts += 8; why.append("Hausgeld steht nicht im Inserat")
    if not ags:
        pts += 5; why.append("Ort nicht im Gemeindeverzeichnis gefunden")
    if n_ort < 3:
        pts += 5; why.append("weniger als drei Vergleichsangebote im Ort")
    if (r["courtage_pct"] or 0) > .035:
        pts += 4; why.append("hohe Käufercourtage")

    # --- Block D: Markt (nur was ohne Zusatzquelle geht) ----------------------
    mp = med_pq.get(ort)
    if mp is not None:
        if mp < 800:
            pts += 12; why.append(f"Ortsniveau {mp:,.0f} €/m² — struktureller Abschwung")
        elif mp < 1200:
            pts += 6; why.append(f"Ortsniveau {mp:,.0f} €/m²")
    if ew is not None:
        if ew < 5_000:
            pts += 8; why.append("Landgemeinde, dünner Mietermarkt")
        elif ew < 20_000:
            pts += 4; why.append("Kleinstadt")

    pts = min(100, pts)
    for lim, name in BANDS:
        if pts < lim:
            return pts, name, why
    return pts, "hoch", why


def main():
    c = conn()
    for col, typ in (("ew", "INTEGER"), ("ags", "TEXT"), ("ortgroesse", "TEXT"),
                     ("marktniveau", "REAL"), ("med_pqm", "REAL"), ("risiko", "INTEGER"),
                     ("risiko_band", "TEXT"), ("risiko_gruende", "TEXT"), ("kreis", "TEXT")):
        try:
            c.execute(f"ALTER TABLE listings ADD COLUMN {col} {typ}")
        except Exception:
            pass

    by_plz, by_name = load_gemeinden()
    med_pq, pctl, med_bar, med_mq, cnt = ort_stats(c)
    print(f"Gemeindeverzeichnis (Stand 31.12.2011): {len(by_plz):,} PLZ, {len(by_name):,} Ortsnamen")
    print(f"Ortsstatistik: {len(med_pq):,} Orte mit Preismedian, {len(med_bar):,} mit Renditemedian")

    rows = c.execute("SELECT * FROM listings WHERE price IS NOT NULL AND qm > 0").fetchall()
    hit = nb = 0
    for r in rows:
        e = by_plz.get((r["plz"] or "").strip()) or by_name.get(norm(r["ort"]))
        ew, ags, kreis = (e[0], e[1], e[2]) if e else (None, None, None)
        hit += 1 if e else 0
        pqm = r["price"] / r["qm"]
        if not r["rent"] or r["rent_status"] == "gone":
            # Ohne belegte Miete traegt Block A nicht — dann kein Band behaupten.
            c.execute("""UPDATE listings SET ew=?, ags=?, kreis=?, ortgroesse=?, marktniveau=?,
                         med_pqm=?, risiko=NULL, risiko_band='nicht bewertbar',
                         risiko_gruende='Ohne belegte Ist-Miete lässt sich das Ertragsrisiko nicht beurteilen.'
                         WHERE id=?""",
                      (ew, ags, kreis, size_of(ew) if ew else "unbekannt",
                       pctl.get(r["ort"]), med_pq.get(r["ort"]), r["id"]))
            nb += 1
            continue
        pts, band, why = score(r, ags, ew, pqm, med_pq, med_bar, med_mq, cnt.get(r["ort"], 0))
        c.execute("""UPDATE listings SET ew=?, ags=?, kreis=?, ortgroesse=?, marktniveau=?,
                     med_pqm=?, risiko=?, risiko_band=?, risiko_gruende=? WHERE id=?""",
                  (ew, ags, kreis, size_of(ew) if ew else "unbekannt", pctl.get(r["ort"]),
                   med_pq.get(r["ort"]), pts, band, " · ".join(why) or "keine Auffälligkeiten", r["id"]))
    c.commit()
    print(f"Ort zugeordnet: {hit:,} von {len(rows):,} | ohne Miete, daher nicht bewertbar: {nb:,}")
    for b in ("niedrig", "mittel", "erhöht", "hoch"):
        n = c.execute("SELECT COUNT(*) n FROM listings WHERE risiko_band=?", (b,)).fetchone()["n"]
        print(f"  {b:<10}{n:,}")


if __name__ == "__main__":
    main()
