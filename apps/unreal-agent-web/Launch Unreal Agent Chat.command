#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_FILE="$SCRIPT_DIR/.data/web-launch.log"
mkdir -p "$SCRIPT_DIR/.data"

resolve_python() {
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return 0
  fi
  if [ -x /usr/bin/python3 ]; then
    echo "/usr/bin/python3"
    return 0
  fi
  if command -v xcrun >/dev/null 2>&1; then
    local p
    p="$(xcrun -f python3 2>/dev/null || true)"
    if [ -n "$p" ]; then
      echo "$p"
      return 0
    fi
  fi
  return 1
}

PYTHON_BIN="$(resolve_python || true)"
if [ -z "$PYTHON_BIN" ]; then
  echo "Failed to find python3. Install Python and retry." | tee -a "$LOG_FILE"
  osascript -e 'display dialog "Unreal Agent Chat launch failed: python3 not found." buttons {"OK"} default button "OK"' || true
  exit 1
fi

if ! pgrep -f "$SCRIPT_DIR/server.py" >/dev/null 2>&1; then
  nohup "$PYTHON_BIN" "$SCRIPT_DIR/server.py" >> "$LOG_FILE" 2>&1 &
fi

# Wait briefly for the server to become responsive.
for _ in {1..20}; do
  if curl -fsS "http://127.0.0.1:8787/api/health" >/dev/null 2>&1; then
    open "http://127.0.0.1:8787"
    exit 0
  fi
  sleep 0.25
done

echo "Server did not become ready. See log: $LOG_FILE" | tee -a "$LOG_FILE"
osascript -e "display dialog \"Unreal Agent Chat failed to start. Check log:\n$LOG_FILE\" buttons {\"OK\"} default button \"OK\"" || true
exit 1
