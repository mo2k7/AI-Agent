#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

RUN_ID=""
BACKGROUND=0
PID_FILE=""
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
  PID_FILE="${AI_AGENT_RUN_DIR}/log_stream.pid"
fi

LOG_FILE="${AI_AGENT_RUN_DIR}/system.log"
PREDICATE='(process == "AIAgentApp") OR (eventMessage CONTAINS[c] "ai-agent") OR (subsystem == "com.apple.network")'

echo "system_log=${LOG_FILE}"
echo "system_predicate=${PREDICATE}"

cmd=(log stream --style compact --color none --predicate "${PREDICATE}")

if [[ "${BACKGROUND}" -eq 1 ]]; then
  "${cmd[@]}" >>"${LOG_FILE}" 2>&1 &
  LOG_PID=$!
  echo "${LOG_PID}" > "${PID_FILE}"
  echo "log_stream_pid=${LOG_PID}"
  exit 0
fi

exec "${cmd[@]}" >>"${LOG_FILE}" 2>&1
