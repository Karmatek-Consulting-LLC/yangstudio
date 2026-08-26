#!/usr/bin/env bash
# Start YANG Studio for development.
#
# Ports are chosen at startup rather than hard-coded: 8000 and 5173 are
# commonly already in use, and a silent collision is worse than a shifted port.
# Override with YANGSTUDIO_PORT / YANGSTUDIO_UI_PORT.
set -euo pipefail
cd "$(dirname "$0")"

# Print the first free port at or after $1.
free_port_from() {
  local port=$1
  while [ "$port" -lt 65535 ]; do
    if ! (ss -ltn 2>/dev/null || netstat -ltn 2>/dev/null) \
        | awk '/LISTEN/{print $4}' | sed 's/.*://' | grep -qx "$port"; then
      echo "$port"
      return 0
    fi
    port=$((port + 1))
  done
  echo "No free port found from $1" >&2
  return 1
}

API_PORT="${YANGSTUDIO_PORT:-$(free_port_from 8420)}"
UI_PORT="${YANGSTUDIO_UI_PORT:-$(free_port_from 5173)}"
export YANGSTUDIO_PORT="$API_PORT"
export YANGSTUDIO_UI_PORT="$UI_PORT"

if [ ! -d backend/.venv ]; then
  echo "==> Creating backend virtualenv"
  (cd backend && uv venv --python 3.12 && uv pip install -e ".[dev]")
fi
if [ ! -d frontend/node_modules ]; then
  echo "==> Installing frontend dependencies"
  (cd frontend && npm install)
fi

# Shut both halves down together on Ctrl-C.
trap 'kill 0' EXIT INT TERM

echo "==> API   http://127.0.0.1:${API_PORT}  (docs at /docs)"
(cd backend && YANGSTUDIO_RELOAD=1 ./.venv/bin/python -m uvicorn yangstudio.app:app \
  --host 127.0.0.1 --port "$API_PORT" --reload) &

echo "==> UI    http://localhost:${UI_PORT}"
(cd frontend && npm run dev) &

echo
echo "    Open the UI, not the API. Ctrl-C stops both."
wait
