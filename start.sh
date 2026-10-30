#!/usr/bin/env bash
# One-command launcher for macOS / Linux. Run:  ./start.sh
set -euo pipefail
cd "$(dirname "$0")"

need() {
  command -v "$1" >/dev/null 2>&1 || { echo "✗ '$1' is not installed. $2"; exit 1; }
}
need python3 "Get it at https://www.python.org/downloads/"
need ffmpeg  "macOS: brew install ffmpeg   |   Ubuntu/Debian: sudo apt install ffmpeg"
need ffprobe "It comes with ffmpeg (see above)."

if [ ! -f frontend/dist/index.html ]; then
  need node "Get it at https://nodejs.org (needed once, to build the web interface)."
  echo "→ Building the web interface (first run only)…"
  (cd frontend && npm install --no-audit --no-fund --silent && npm run build --silent)
fi

if [ ! -d backend/.venv ]; then
  echo "→ Creating the Python environment (first run only)…"
  python3 -m venv backend/.venv
fi
echo "→ Checking Python packages…"
backend/.venv/bin/pip install -q -r backend/requirements.txt

URL="http://localhost:8000"
echo "✓ Ready. Opening $URL  (press Ctrl+C here to stop)"
open_browser() {
  sleep 2
  if command -v open >/dev/null 2>&1; then open "$URL"
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL"
  fi
}
open_browser >/dev/null 2>&1 &
cd backend
exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
