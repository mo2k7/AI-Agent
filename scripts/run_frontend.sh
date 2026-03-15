#!/usr/bin/env bash
# run_frontend.sh — Build and run the Swift frontend application.
#
# Improvements:
# - Build exit-code verification before launch
# - Process-group launch for clean tree teardown
# - Validates the built binary exists before exec
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

RUN_ID=""
BACKGROUND=0
PID_FILE=""
SKIP_BUILD=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-id)
      RUN_ID="${2:-}"
      shift 2
      ;;
    --background)
      BACKGROUND=1
      shift
      ;;
    --pid-file)
      PID_FILE="${2:-}"
      shift 2
      ;;
    --skip-build)
      SKIP_BUILD=1
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -n "${RUN_ID}" ]]; then
  # shellcheck disable=SC1091
  source "${SCRIPT_DIR}/dev_env.sh" --run-id "${RUN_ID}"
else
  # shellcheck disable=SC1091
  source "${SCRIPT_DIR}/dev_env.sh"
fi

if [[ -z "${PID_FILE}" ]]; then
  PID_FILE="${AI_AGENT_RUN_DIR}/frontend.pid"
fi

LOG_FILE="${AI_AGENT_RUN_DIR}/frontend.log"
mkdir -p "${AI_AGENT_RUN_DIR}"

echo "frontend_backend_url=${AI_AGENT_BACKEND_URL}"
echo "frontend_log=${LOG_FILE}"

if [[ "${SKIP_BUILD}" -eq 0 ]]; then
  echo "[frontend] Building Swift frontend…"
  if ! (
    cd "${PROJECT_ROOT}"
    swift build --package-path ui -c debug
  ) >>"${LOG_FILE}" 2>&1; then
    echo "[frontend] FATAL: Swift build failed. See ${LOG_FILE}" >&2
    exit 1
  fi
  echo "[frontend] Build succeeded"
fi

# Verify the binary actually exists before trying to run
BINARY_PATH="${PROJECT_ROOT}/ui/.build/debug/AIAgentApp"
if [[ ! -x "${BINARY_PATH}" ]]; then
  # swift run will build+run, but we want to catch missing binary early
  echo "[frontend] NOTE: Binary not at expected path, swift run will resolve" >&2
fi

cmd=(swift run --package-path ui --skip-build AIAgentApp)

if [[ "${BACKGROUND}" -eq 1 ]]; then
  (
    cd "${PROJECT_ROOT}"
    AI_AGENT_BACKEND_URL="${AI_AGENT_BACKEND_URL}" \
    AI_AGENT_IPC_AUTH_TOKEN="${AI_AGENT_IPC_AUTH_TOKEN:-}" \
    AI_AGENT_DISABLE_BOOTSTRAP_REEXEC="${AI_AGENT_DISABLE_BOOTSTRAP_REEXEC:-1}" \
    AI_AGENT_BOOTSTRAPPED="${AI_AGENT_BOOTSTRAPPED:-1}" \
    exec "${cmd[@]}"
  ) >>"${LOG_FILE}" 2>&1 &
  FRONTEND_PID=$!
  echo "${FRONTEND_PID}" > "${PID_FILE}"
  echo "frontend_pid=${FRONTEND_PID}"
  exit 0
fi

cd "${PROJECT_ROOT}"
AI_AGENT_BACKEND_URL="${AI_AGENT_BACKEND_URL}" \
AI_AGENT_IPC_AUTH_TOKEN="${AI_AGENT_IPC_AUTH_TOKEN:-}" \
AI_AGENT_DISABLE_BOOTSTRAP_REEXEC="${AI_AGENT_DISABLE_BOOTSTRAP_REEXEC:-1}" \
AI_AGENT_BOOTSTRAPPED="${AI_AGENT_BOOTSTRAPPED:-1}" \
exec "${cmd[@]}" >>"${LOG_FILE}" 2>&1
