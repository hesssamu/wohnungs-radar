#!/usr/bin/env python3
"""
Dubletten über Portale hinweg erkennen.

Dieselbe Wohnung steht oft bei ImmoScout UND Immowelt — der Makler inseriert
auf beiden. Es gibt keine gemeinsame Kennung, also wird über die harten Fakten
zusammengeführt: Postleitzahl, Wohnfläche, Kaufpreis, Zimmerzahl.

Die Fläche ist der zuverlässigste Anker (sie wird selten unterschiedlich
angegeben), der Preis der zweitzuverlässigste. Beide dürfen leicht abweichen,
weil Portale unterschiedlich runden.

Der Datensatz mit den meisten Angaben bleibt sichtbar, der andere bekommt
dup_of gesetzt und verschwindet aus der Suche.
"""
import os, sys, re
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import conn

QM_TOL = 1.0        # m² Toleranz
PRICE_TOL = 0.02    # 2 % Preistoleranz


def richness(r):
    """Wie vollständig ist ein Datensatz? Der reichere gewinnt."""
    s = 0
    for f in ("rent", "hausgeld", "bj", "rooms", "img", "rent_evidence", "quarter", "zustand"):
        if r[f] is not None and r[f] != "":
            s += 1
    if r["source"] == "is24":
        s += 1          # bei Gleichstand: ImmoScout hat die reicheren Rohdaten
    return s


def main():
    c = conn()
    try:
        c.execute("ALTER TABLE listings ADD COLUMN dup_of TEXT")
    except Exception:
        pass
    c.execute("UPDATE listings SET dup_of=NULL")

    rows = c.execute("""SELECT * FROM listings
                        WHERE price IS NOT NULL AND qm IS NOT NULL AND qm > 0
                          AND rent_status <> 'gone'""").fetchall()
    print(f"{len(rows):,} Objekte werden verglichen")

    # Grob vorsortieren: gleiche PLZ und gleiche gerundete Fläche landen im selben Korb.
    buckets = defaultdict(list)
    for r in rows:
        plz = (r["plz"] or "").strip()
        if not plz:
            continue
        for q in {round(r["qm"]), round(r["qm"] + QM_TOL), round(r["qm"] - QM_TOL)}:
            buckets[(plz, q)].append(r)

    pairs, checked = [], set()
    for key, group in buckets.items():
        if len(group) < 2:
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                if a["id"] == b["id"]:
                    continue
                pk = tuple(sorted((a["id"], b["id"])))
                if pk in checked:
                    continue
                checked.add(pk)
                if a["source"] == b["source"]:
                    continue                      # innerhalb eines Portals sind es echte Zwillinge
                if abs(a["qm"] - b["qm"]) > QM_TOL:
                    continue
                hi = max(a["price"], b["price"])
                if abs(a["price"] - b["price"]) / hi > PRICE_TOL:
                    continue
                if a["rooms"] and b["rooms"] and abs(a["rooms"] - b["rooms"]) > 0.6:
                    continue
                if a["bj"] and b["bj"] and abs(a["bj"] - b["bj"]) > 2:
                    continue
                pairs.append((a, b))

    n = 0
    for a, b in pairs:
        keep, drop = (a, b) if richness(a) >= richness(b) else (b, a)
        cur = c.execute("SELECT dup_of FROM listings WHERE id=?", (drop["id"],)).fetchone()
        if cur and cur["dup_of"]:
            continue
        c.execute("UPDATE listings SET dup_of=? WHERE id=?", (keep["id"], drop["id"]))
        # fehlende Angaben aus der Dublette uebernehmen — zwei halbe Inserate ergeben ein ganzes
        for f in ("rent", "hausgeld", "bj", "rooms", "img", "rent_evidence"):
            if keep[f] in (None, "") and drop[f] not in (None, ""):
                c.execute(f"UPDATE listings SET {f}=? WHERE id=?", (drop[f], keep["id"]))
        n += 1
    c.commit()

    tot = c.execute("SELECT COUNT(*) n FROM listings WHERE dup_of IS NULL AND rent_status<>'gone'").fetchone()["n"]
    iw = c.execute("SELECT COUNT(*) n FROM listings WHERE source='immowelt'").fetchone()["n"]
    print(f"{n:,} Dubletten zusammengefuehrt")
    print(f"Sichtbar bleiben {tot:,} Objekte ({iw:,} davon von Immowelt eingelesen)")


if __name__ == "__main__":
    main()
