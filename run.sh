#!/usr/bin/env bash
# Wohnungs-Radar starten. Optional: ./run.sh --worker  (lädt zusätzlich Mieten nach)
set -euo pipefail
cd "$(dirname "$0")"

PORT="${PORT:-8840}"

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Läuft bereits -> http://localhost:$PORT"
  exit 0
fi

if [[ "${1:-}" == "--worker" ]]; then
  echo "Starte Hintergrund-Worker (Mieten nachladen) …"
  nohup python3 worker.py > data/worker.log 2>&1 &
  echo "  Log: data/worker.log"
fi

exec python3 -u server.py
