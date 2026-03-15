#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "[browse-security] validating anti-bot signatures..."
python scripts/refresh_anti_bot_signatures.py --validate

echo "[browse-security] running browse-web security regression suite..."
poetry run pytest \
  tests/unit/test_browse_web_security.py \
  tests/unit/test_tool_executor_hardening_precision.py \
  -q

echo "[browse-security] done"
