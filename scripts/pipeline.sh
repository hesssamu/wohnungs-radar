#!/usr/bin/env bash
# Wartet auf die laufende Vollerhebung, liest sie ein und lädt danach die Mieten nach.
set -uo pipefail
cd "$(dirname "$0")/.."

echo "[$(date '+%H:%M')] warte auf die Vollerhebung …"
while pgrep -f "harvest_all.py" > /dev/null; do sleep 30; done
echo "[$(date '+%H:%M')] Vollerhebung fertig, lese ein …"

python3 scripts/ingest.py
python3 scripts/add_dad.py

echo "[$(date '+%H:%M')] starte Worker (Mieten nachladen) …"
python3 worker.py
echo "[$(date '+%H:%M')] Pipeline fertig."
