#!/usr/bin/env bash
set -euo pipefail

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
HOST="${HOST:-127.0.0.1}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

# Use the currently available Python (including an activated Conda environment)
if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found. Please activate your Python/Conda environment and retry." >&2
  exit 1
fi

PYTHON_BIN="python3"

# Check npm
if ! command -v npm >/dev/null 2>&1; then
  echo "npm not found. Install Node.js and retry." >&2
  exit 1
fi

# Install frontend dependencies if needed
if [[ ! -d "$ROOT_DIR/frontend/node_modules" ]]; then
  echo "Installing frontend dependencies..."
  (cd "$ROOT_DIR/frontend" && npm install)
fi

export PYTHONPATH="$ROOT_DIR/backend"

# Free ports if already in use by stale processes
lsof -ti :"$BACKEND_PORT" | xargs kill -9 >/dev/null 2>&1 || true
lsof -ti :"$FRONTEND_PORT" | xargs kill -9 >/dev/null 2>&1 || true

# Start backend
"$PYTHON_BIN" -m uvicorn app.main:app \
  --app-dir backend \
  --host "$HOST" \
  --port "$BACKEND_PORT" &

BACKEND_PID=$!

# Start frontend
(
  cd "$ROOT_DIR/frontend"
  npm run dev -- --host "$HOST" --port "$FRONTEND_PORT"
) &

FRONTEND_PID=$!

echo "RecoverIQ is starting..."
echo "Backend : http://$HOST:$BACKEND_PORT"
echo "Frontend: http://$HOST:$FRONTEND_PORT"
echo "Press Ctrl+C to stop both processes."

cleanup() {
  kill "$BACKEND_PID" "$FRONTEND_PID" >/dev/null 2>&1 || true
}

trap cleanup EXIT INT TERM

wait "$BACKEND_PID" "$FRONTEND_PID"