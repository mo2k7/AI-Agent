#!/usr/bin/env bash
# run_backend.sh — Start the Python backend server.
#
# Improvements:
# - Uses WebSocket IPC over loopback
# - Uses Poetry deterministically for environment/runtime
# - Avoids non-portable setsid dependency on macOS
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

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
  PID_FILE="${AI_AGENT_RUN_DIR}/backend.pid"
fi

LOG_FILE="${AI_AGENT_RUN_DIR}/backend.log"
BACKEND_HOST="${AI_AGENT_BACKEND_HOST}"
BACKEND_PORT="${AI_AGENT_BACKEND_PORT}"
BACKEND_URL="${AI_AGENT_BACKEND_URL}"
PROJECT_CACHE_ROOT="${PROJECT_ROOT}/.ai-agent-cache"
POETRY_DEPS_STAMP="${PROJECT_CACHE_ROOT}/poetry-deps.stamp"

mkdir -p "${AI_AGENT_RUN_DIR}"
mkdir -p "${PROJECT_CACHE_ROOT}"

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

_resolve_runtime_python() {
  if [[ -x "${PROJECT_ROOT}/.venv/bin/python" ]]; then
    printf "%s\n" "${PROJECT_ROOT}/.venv/bin/python"
    return 0
  fi
  if [[ -n "${VIRTUAL_ENV:-}" ]] && [[ -x "${VIRTUAL_ENV}/bin/python" ]]; then
    printf "%s\n" "${VIRTUAL_ENV}/bin/python"
    return 0
  fi
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return 0
  fi
  return 1
}

_refresh_runtime_python() {
  if [[ -n "${RUNTIME_PYTHON:-}" ]] && [[ -x "${RUNTIME_PYTHON}" ]]; then
    return 0
  fi
  RUNTIME_PYTHON="$(_resolve_runtime_python || true)"
  if [[ -n "${RUNTIME_PYTHON}" ]]; then
    return 0
  fi
  if [[ -n "${POETRY_BIN:-}" ]]; then
    local poetry_env
    poetry_env="$("${POETRY_BIN}" env info -p 2>/dev/null || true)"
    if [[ -n "${poetry_env}" ]] && [[ -x "${poetry_env}/bin/python" ]]; then
      RUNTIME_PYTHON="${poetry_env}/bin/python"
      return 0
    fi
  fi
  return 1
}

_compute_file_sha256() {
  local path="$1"
  if [[ -f "${path}" ]]; then
    shasum -a 256 "${path}" | awk '{print $1}'
    return 0
  fi
  printf "missing\n"
}

_compute_poetry_deps_fingerprint() {
  local poetry_version python_version lock_hash pyproject_hash
  poetry_version="$("${POETRY_BIN:-poetry-missing}" --version 2>/dev/null | tr -s ' ' || printf "unknown")"
  python_version="$(
    cd "${PROJECT_ROOT}" \
      && [[ -n "${RUNTIME_PYTHON}" ]] \
      && "${RUNTIME_PYTHON}" -c "import sys; print('.'.join(map(str, sys.version_info[:3])))" 2>/dev/null \
      || printf "unknown"
  )"
  lock_hash="$(_compute_file_sha256 "${PROJECT_ROOT}/poetry.lock")"
  pyproject_hash="$(_compute_file_sha256 "${PROJECT_ROOT}/pyproject.toml")"
  printf "poetry=%s\npython=%s\nlock=%s\npyproject=%s\n" \
    "${poetry_version}" "${python_version}" "${lock_hash}" "${pyproject_hash}"
}

_poetry_env_ready() {
  (
    cd "${PROJECT_ROOT}" \
      && [[ -n "${RUNTIME_PYTHON}" ]] \
      && "${RUNTIME_PYTHON}" -c "import importlib; [importlib.import_module(name) for name in ('agent_host','google.genai','jsonschema','dotenv','cryptography','unified_planning','spacy','bs4','websockets')]"
  ) >/dev/null 2>&1
}

RUNTIME_PYTHON="$(_resolve_runtime_python || true)"

POETRY_BIN=""
if POETRY_BIN="$(_resolve_poetry_bin)"; then
  :
else
  if [[ -n "${RUNTIME_PYTHON}" ]]; then
    :
  elif ! command -v python3 >/dev/null 2>&1; then
    echo "[backend] FATAL: Poetry missing and python3 not available for Poetry install." >&2
    exit 1
  else
    echo "[backend] Poetry not found; installing Poetry..." >&2
    python3 -m pip install --user "poetry>=1.8,<2.0" >&2
    hash -r
    if ! POETRY_BIN="$(_resolve_poetry_bin)"; then
      echo "[backend] FATAL: Poetry install completed but binary still unavailable." >&2
      exit 1
    fi
  fi
fi

POETRY_DEPS_FINGERPRINT="$(_compute_poetry_deps_fingerprint)"
if [[ -f "${POETRY_DEPS_STAMP}" ]] \
  && [[ "$(cat "${POETRY_DEPS_STAMP}")" == "${POETRY_DEPS_FINGERPRINT}" ]] \
  && _poetry_env_ready; then
  echo "[backend] Using cached Poetry environment."
elif ! _poetry_env_ready; then
  echo "[backend] Python environment incomplete — running poetry install" >&2
  (cd "${PROJECT_ROOT}" && "${POETRY_BIN}" install --no-interaction --sync)
  _refresh_runtime_python || true
  POETRY_DEPS_FINGERPRINT="$(_compute_poetry_deps_fingerprint)"
  printf "%s" "${POETRY_DEPS_FINGERPRINT}" > "${POETRY_DEPS_STAMP}"
else
  echo "[backend] Python environment validated; reusing installed Poetry environment."
  printf "%s" "${POETRY_DEPS_FINGERPRINT}" > "${POETRY_DEPS_STAMP}"
fi

if ! _refresh_runtime_python; then
  echo "[backend] FATAL: no usable project Python runtime found." >&2
  exit 1
fi

echo "backend_url=${BACKEND_URL}"
echo "backend_log=${LOG_FILE}"

_env_bool_true() {
  local raw="${1:-}"
  local lowered
  lowered="$(printf "%s" "${raw}" | tr '[:upper:]' '[:lower:]')"
  [[ "${lowered}" != "0" && "${lowered}" != "false" && "${lowered}" != "no" && "${lowered}" != "off" ]]
}

# Generate IPC auth token if not already set (mirrors BackendLauncher.swift).
if [[ -z "${AI_AGENT_IPC_AUTH_TOKEN:-}" ]]; then
  export AI_AGENT_IPC_AUTH_TOKEN
  AI_AGENT_IPC_AUTH_TOKEN="$(uuidgen)"
fi

cmd=("${RUNTIME_PYTHON}" -m agent_host.main --server --host "${BACKEND_HOST}" --port "${BACKEND_PORT}" --verbose)

if [[ "${BACKGROUND}" -eq 1 ]]; then
  # Launch backend in background (portable across macOS/Linux).
  (
    cd "${PROJECT_ROOT}"
    exec "${cmd[@]}"
  ) >>"${LOG_FILE}" 2>&1 &
  BACKEND_PID=$!
  echo "${BACKEND_PID}" > "${PID_FILE}"
  echo "backend_pid=${BACKEND_PID}"

  deadline=$((SECONDS + 60))
  while [[ ${SECONDS} -lt ${deadline} ]]; do
    if ! kill -0 "${BACKEND_PID}" 2>/dev/null; then
      break
    fi
    if python3 - <<'PY' "${BACKEND_HOST}" "${BACKEND_PORT}" >/dev/null 2>&1
import socket, sys
host = sys.argv[1]
port = int(sys.argv[2])
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.settimeout(0.2)
    sock.connect((host, port))
PY
    then
      break
    fi
    sleep 0.1
  done
  if ! python3 - <<'PY' "${BACKEND_HOST}" "${BACKEND_PORT}" >/dev/null 2>&1
import socket, sys
host = sys.argv[1]
port = int(sys.argv[2])
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.settimeout(0.2)
    sock.connect((host, port))
PY
  then
    if ! kill -0 "${BACKEND_PID}" 2>/dev/null; then
      echo "Backend process exited before listening on ${BACKEND_URL}" >&2
    else
      echo "Backend failed to listen within 60s: ${BACKEND_URL}" >&2
    fi
    # Dump last 20 lines of log for debugging
    tail -20 "${LOG_FILE}" 2>/dev/null || true
    exit 1
  fi
  exit 0
fi

cd "${PROJECT_ROOT}"
exec "${cmd[@]}" >>"${LOG_FILE}" 2>&1
