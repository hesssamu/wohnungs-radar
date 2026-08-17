#!/usr/bin/env bash
# Wartet, bis der Worker alle Exposés durch hat, rechnet die Einstufungen neu,
# baut die verschlüsselte Pages-Fassung und veröffentlicht sie.
# Baut zwischendurch alle 90 Minuten neu, damit die Seite nicht stundenlang veraltet.
set -uo pipefail
cd "$(dirname "$0")/.."

publish () {
  python3 lage.py                       > /dev/null 2>&1
  ./.venv/bin/python build_static.py    > /dev/null 2>&1
  if ! git diff --quiet docs/ 2>/dev/null; then
    git add docs/
    git -c user.name="Samuel Hess" -c user.email="samuel@dripagency.de" \
        commit -q -m "Datenstand aktualisiert: $(date '+%d.%m.%Y %H:%M')

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TR7RimvFAWWaKRAC2BAFp9" 2>/dev/null
    git push -q origin HEAD 2>/dev/null && echo "[$(date '+%H:%M')] veroeffentlicht"
  fi
}

echo "[$(date '+%H:%M')] warte auf den Worker …"
last=$(date +%s)
while pgrep -f "worker.py" > /dev/null; do
  sleep 60
  now=$(date +%s)
  if (( now - last >= 5400 )); then     # alle 90 Minuten Zwischenstand
    echo "[$(date '+%H:%M')] Zwischenstand wird veroeffentlicht"
    publish
    last=$now
  fi
done

echo "[$(date '+%H:%M')] Worker fertig, letzter Durchlauf"
publish

python3 - <<'PY'
import sys; sys.path.insert(0, '.')
from core import conn
c = conn(); g = lambda q: c.execute(q).fetchone()["n"]
rent = g("SELECT COUNT(*) n FROM listings WHERE rent IS NOT NULL AND rent_status<>'gone'")
band = g("SELECT COUNT(*) n FROM listings WHERE rent IS NOT NULL AND rent_status<>'gone' AND rent*12.0/price BETWEEN 0.05 AND 0.07")
hoch = g("SELECT COUNT(*) n FROM listings WHERE rent IS NOT NULL AND rent_status<>'gone' AND rent*12.0/price > 0.07")
gone = g("SELECT COUNT(*) n FROM listings WHERE rent_status='gone'")
print(f"FERTIG: {rent:,} Wohnungen mit belegter Ist-Miete "
      f"({band:,} im Band 5-7 %, {hoch:,} darueber), {gone:,} deaktivierte aussortiert")
PY
