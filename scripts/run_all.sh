#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

DURATION=30
CONCURRENCY=20
SEED=1337
RUN_ID=""
SKIP_FRONTEND=0
SKIP_FRONTEND_BUILD=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --duration)
      DURATION="${2:-30}"
      shift 2
      ;;
    --concurrency)
      CONCURRENCY="${2:-20}"
      shift 2
      ;;
    --seed)
      SEED="${2:-1337}"
      shift 2
      ;;
    --run-id)
      RUN_ID="${2:-}"
      shift 2
      ;;
    --skip-frontend)
      SKIP_FRONTEND=1
      shift
      ;;
    --skip-frontend-build)
      SKIP_FRONTEND_BUILD=1
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

_resolve_poetry_bin() {
  if command -v poetry >/dev/null 2>&1; then
    command -v poetry
    return 0
  fi
  if [[ -x "${HOME}/.local/bin/poetry" ]]; then
    printf "%s\n" "${HOME}/.local/bin/poetry"
    return 0
  fi
  if [[ -x "${HOME}/.poetry/bin/poetry" ]]; then
    printf "%s\n" "${HOME}/.poetry/bin/poetry"
    return 0
  fi
  return 1
}

POETRY_BIN=""
if POETRY_BIN="$(_resolve_poetry_bin)"; then
  :
else
  if ! command -v python3 >/dev/null 2>&1; then
    echo "[run_all] FATAL: Poetry missing and python3 unavailable for Poetry install." >&2
    exit 1
  fi
  echo "[run_all] Poetry not found; installing Poetry..." >&2
  python3 -m pip install --user "poetry>=1.8,<2.0" >&2
  hash -r
  if ! POETRY_BIN="$(_resolve_poetry_bin)"; then
    echo "[run_all] FATAL: Poetry install completed but poetry binary is still unavailable." >&2
    exit 1
  fi
fi

BACKEND_PID_FILE="${AI_AGENT_RUN_DIR}/backend.pid"
FRONTEND_PID_FILE="${AI_AGENT_RUN_DIR}/frontend.pid"
LOG_PID_FILE="${AI_AGENT_RUN_DIR}/log_stream.pid"
STATUS_FILE="${AI_AGENT_RUN_DIR}/run_status.txt"
REPORT_PATH="${AI_AGENT_RUN_DIR}/stress_report.json"

echo "run_id=${AI_AGENT_RUN_ID}"
echo "run_dir=${AI_AGENT_RUN_DIR}"
echo "backend_url=${AI_AGENT_BACKEND_URL}"

cleanup() {
  set +e
  for pid_file in "${FRONTEND_PID_FILE}" "${BACKEND_PID_FILE}" "${LOG_PID_FILE}"; do
    if [[ -f "${pid_file}" ]]; then
      pid="$(cat "${pid_file}")"
      if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
        # Try to terminate the full process group first (run_* scripts use setsid).
        kill -TERM -- "-${pid}" 2>/dev/null || true
        kill "${pid}" 2>/dev/null || true
        wait "${pid}" 2>/dev/null || true
      fi
    fi
  done
}
trap cleanup EXIT INT TERM

(
  cd "${PROJECT_ROOT}"
  bash scripts/run_backend.sh --run-id "${AI_AGENT_RUN_ID}" --background --pid-file "${BACKEND_PID_FILE}"
)

(
  cd "${PROJECT_ROOT}"
  bash scripts/log_stream.sh --run-id "${AI_AGENT_RUN_ID}" --background --pid-file "${LOG_PID_FILE}"
)

if [[ "${SKIP_FRONTEND}" -eq 0 ]]; then
  FRONTEND_ARGS=(scripts/run_frontend.sh --run-id "${AI_AGENT_RUN_ID}" --background --pid-file "${FRONTEND_PID_FILE}")
  if [[ "${SKIP_FRONTEND_BUILD}" -eq 1 ]]; then
    FRONTEND_ARGS+=(--skip-build)
  fi
  (
    cd "${PROJECT_ROOT}"
    bash "${FRONTEND_ARGS[@]}"
  )
fi

set +e
(
  cd "${PROJECT_ROOT}"
  "${POETRY_BIN}" run python scripts/stress_rpc.py \
    --backend-url "${AI_AGENT_BACKEND_URL}" \
    --auth-token "${AI_AGENT_IPC_AUTH_TOKEN}" \
    --duration "${DURATION}" \
    --concurrency "${CONCURRENCY}" \
    --seed "${SEED}" \
    --run-dir "${AI_AGENT_RUN_DIR}"
)
STRESS_EXIT=$?
set -e

if [[ "${STRESS_EXIT}" -ne 0 ]]; then
  echo "stress_failed" | tee "${STATUS_FILE}"
  if [[ -f "${REPORT_PATH}" ]]; then
    (
      cd "${PROJECT_ROOT}"
      "${POETRY_BIN}" run python scripts/repro_capture.py \
        --report "${REPORT_PATH}" \
        --run-dir "${AI_AGENT_RUN_DIR}" \
        --failure-index 0
    )
  fi
  echo "Harness failed. Artifacts: ${AI_AGENT_RUN_DIR}"
  exit 1
fi

echo "ok" | tee "${STATUS_FILE}"
echo "Harness completed successfully."
echo "Artifacts directory: ${AI_AGENT_RUN_DIR}"
echo "Backend log: ${AI_AGENT_RUN_DIR}/backend.log"
echo "Frontend log: ${AI_AGENT_RUN_DIR}/frontend.log"
echo "System log: ${AI_AGENT_RUN_DIR}/system.log"
echo "Protocol trace: ${AI_AGENT_RUN_DIR}/protocol_trace.jsonl"
echo "Stress report: ${AI_AGENT_RUN_DIR}/stress_report.json"
