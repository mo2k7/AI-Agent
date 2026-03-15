#!/bin/bash
# AI Agent Backend Daemon Manager
# Usage: ./manage-daemon.sh [install|uninstall|start|stop|restart|status|logs]

set -euo pipefail

PLIST_NAME="com.aiagent.backend"
SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_SRC="$SCRIPTS_DIR/$PLIST_NAME.plist"
PLIST_DST="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"
ENV_FILE="$SCRIPTS_DIR/.env"
LOG_DIR="$HOME/Library/Logs/AIAgent"

case "${1:-help}" in
    install)
        # Check for .env file with API key
        if [[ ! -f "$ENV_FILE" ]]; then
            echo "⚠️  No .env file found at: $ENV_FILE"
            echo ""
            read -p "Enter your Gemini API key (GOOGLE_API_KEY): " api_key
            echo "GOOGLE_API_KEY=$api_key" > "$ENV_FILE"
            chmod 600 "$ENV_FILE"
            echo "✅ Saved API key to $ENV_FILE"
        fi

        mkdir -p "$HOME/Library/LaunchAgents" "$LOG_DIR"
        cp "$PLIST_SRC" "$PLIST_DST"
        launchctl load "$PLIST_DST"
        echo "✅ Daemon installed and started."
        echo "   The backend will auto-start on login and restart on crash."
        echo "   Logs: $LOG_DIR/"
        echo ""
        echo "   Use './manage-daemon.sh status' to check if it's running."
        ;;

    uninstall)
        if [[ -f "$PLIST_DST" ]]; then
            launchctl unload "$PLIST_DST" 2>/dev/null || true
            rm -f "$PLIST_DST"
            echo "✅ Daemon uninstalled."
        else
            echo "ℹ️  Daemon is not installed."
        fi
        ;;

    start)
        if [[ ! -f "$PLIST_DST" ]]; then
            echo "❌ Daemon not installed. Run './manage-daemon.sh install' first."
            exit 1
        fi
        launchctl start "$PLIST_NAME"
        echo "✅ Daemon started."
        ;;

    stop)
        launchctl stop "$PLIST_NAME" 2>/dev/null || true
        echo "✅ Daemon stopped."
        ;;

    restart)
        launchctl stop "$PLIST_NAME" 2>/dev/null || true
        sleep 1
        launchctl start "$PLIST_NAME"
        echo "✅ Daemon restarted."
        ;;

    status)
        if launchctl list | grep -q "$PLIST_NAME"; then
            pid=$(launchctl list | grep "$PLIST_NAME" | awk '{print $1}')
            if [[ "$pid" == "-" ]]; then
                echo "⚠️  Daemon is loaded but not running (may be restarting)."
            else
                echo "✅ Daemon is running (PID: $pid)"
            fi
        else
            echo "❌ Daemon is not loaded."
        fi
        ;;

    logs)
        echo "=== STDOUT ==="
        tail -30 "$LOG_DIR/backend-stdout.log" 2>/dev/null || echo "(empty)"
        echo ""
        echo "=== STDERR ==="
        tail -30 "$LOG_DIR/backend-stderr.log" 2>/dev/null || echo "(empty)"
        ;;

    *)
        echo "AI Agent Backend Daemon Manager"
        echo ""
        echo "Usage: $0 [command]"
        echo ""
        echo "Commands:"
        echo "  install     Install and start the background daemon"
        echo "  uninstall   Stop and remove the daemon"
        echo "  start       Start the daemon"
        echo "  stop        Stop the daemon"
        echo "  restart     Restart the daemon"
        echo "  status      Check if the daemon is running"
        echo "  logs        Show recent log output"
        ;;
esac
