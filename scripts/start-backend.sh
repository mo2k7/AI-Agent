#!/bin/bash
# AI Agent Backend Daemon Launcher
# Starts the Python IPC server for remote iOS connections via Tailscale.
# Used by launchd to run the backend independently of the Mac app.

set -euo pipefail

PROJECT_DIR="/Users/muhammadabdullah/AI Automation Agent macOS"
PYTHON="$PROJECT_DIR/.venv/bin/python3"
HOST="0.0.0.0"
PORT="8765"
LOG_DIR="$HOME/Library/Logs/AIAgent"
ENV_FILE="$PROJECT_DIR/scripts/.env"
RUNTIME_DIR="$HOME/Library/Application Support/AIAgent"
PAIRING_TOKEN_FILE="$RUNTIME_DIR/pairing-auth-token"

mkdir -p "$LOG_DIR"
mkdir -p "$RUNTIME_DIR"
chmod 700 "$RUNTIME_DIR" 2>/dev/null || true

# Load API key from .env file if it exists
if [[ -f "$ENV_FILE" ]]; then
    set -a
    source "$ENV_FILE"
    set +a
fi

# Require a valid API key
if [[ -z "${GOOGLE_API_KEY:-}" ]]; then
    echo "$(date): ERROR - GOOGLE_API_KEY not set." >&2
    echo "  Create $ENV_FILE with your key:" >&2
    echo "    echo 'GOOGLE_API_KEY=your-key-here' > \"$ENV_FILE\"" >&2
    echo "    chmod 600 \"$ENV_FILE\"" >&2
    exit 1
fi

# Use a stable pairing token so iOS can reconnect across backend restarts.
if [[ ! -s "$PAIRING_TOKEN_FILE" ]]; then
    uuidgen > "$PAIRING_TOKEN_FILE"
    chmod 600 "$PAIRING_TOKEN_FILE"
fi

PAIRING_TOKEN="$(tr -d '\r\n' < "$PAIRING_TOKEN_FILE")"
if [[ -z "$PAIRING_TOKEN" ]]; then
    echo "$(date): ERROR - pairing token file is empty: $PAIRING_TOKEN_FILE" >&2
    exit 1
fi

export AI_AGENT_IPC_AUTH_TOKEN="$PAIRING_TOKEN"
export AI_AGENT_IPC_HOST="$HOST"
export AI_AGENT_ENV="production"
export PYTHONUNBUFFERED=1

# TLS for iOS ATS compliance (Tailscale connections use wss://) and never
# silently downgrade this remote path back to plain ws://.
while IFS='=' read -r key value; do
    case "$key" in
        TLS_CERT_PATH) export AI_AGENT_TLS_CERT="$value" ;;
        TLS_KEY_PATH) export AI_AGENT_TLS_KEY="$value" ;;
    esac
done < <("$PROJECT_DIR/scripts/ensure-backend-tls.sh")

if [[ -z "${AI_AGENT_TLS_CERT:-}" || -z "${AI_AGENT_TLS_KEY:-}" ]]; then
    echo "$(date): ERROR - failed to provision backend TLS assets." >&2
    exit 1
fi
export AI_AGENT_REQUIRE_TLS="1"

echo "$(date): Starting AI Agent backend on $HOST:$PORT (PID $$)"

cd "$PROJECT_DIR"
exec "$PYTHON" -m agent_host.main --server --host "$HOST" --port "$PORT"
