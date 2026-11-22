#!/usr/bin/env bash
cd "$(dirname "$0")"

# Activate venv if exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

echo "=========================================================="
echo " AUTOLEDGER // Autonomous Bank & UPI Tracker"
echo "=========================================================="
echo "Starting local server at http://localhost:5050"
echo "Press Ctrl+C to stop."

exec python3 -m uvicorn main:app --host 127.0.0.1 --port 5050
