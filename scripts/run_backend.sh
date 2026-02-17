#!/usr/bin/env bash
# run_backend.sh — Start the Python backend server.
#
# Improvements:
# - Cleans stale socket before launch
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
SOCKET_PATH="${AI_AGENT_SOCKET_PATH}"
PROJECT_CACHE_ROOT="${PROJECT_ROOT}/.ai-agent-cache"
POETRY_DEPS_STAMP="${PROJECT_CACHE_ROOT}/poetry-deps.stamp"

mkdir -p "${AI_AGENT_RUN_DIR}"
mkdir -p "${PROJECT_CACHE_ROOT}"

# Clean stale socket only when the existing path is a socket node.
if [[ -e "${SOCKET_PATH}" ]]; then
  if [[ -S "${SOCKET_PATH}" ]]; then
    rm -f -- "${SOCKET_PATH}"
  else
    echo "[backend] FATAL: refusing to remove non-socket path: ${SOCKET_PATH}" >&2
    exit 1
  fi
fi

_resolve_poetry_bin() {
  if [[ -n "${VIRTUAL_ENV:-}" ]] && [[ -x "${VIRTUAL_ENV}/bin/poetry" ]]; then
    printf "%s\n" "${VIRTUAL_ENV}/bin/poetry"
    return 0
  fi
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
  poetry_version="$("${POETRY_BIN}" --version 2>/dev/null | tr -s ' ' || printf "unknown")"
  python_version="$(
    cd "${PROJECT_ROOT}" \
      && "${POETRY_BIN}" run python -c "import sys; print('.'.join(map(str, sys.version_info[:3])))" 2>/dev/null \
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
      && "${POETRY_BIN}" run python -c "import agent_host"
  ) >/dev/null 2>&1
}

POETRY_BIN=""
if POETRY_BIN="$(_resolve_poetry_bin)"; then
  :
else
  if ! command -v python3 >/dev/null 2>&1; then
    echo "[backend] FATAL: Poetry missing and python3 not available for Poetry install." >&2
    exit 1
  fi
  echo "[backend] Poetry not found; installing Poetry..." >&2
  if [[ -n "${VIRTUAL_ENV:-}" ]]; then
    python3 -m pip install "poetry>=1.8,<2.0" >&2
  else
    python3 -m pip install --user "poetry>=1.8,<2.0" >&2
  fi
  hash -r
  if ! POETRY_BIN="$(_resolve_poetry_bin)"; then
    echo "[backend] FATAL: Poetry install completed but binary still unavailable." >&2
    exit 1
  fi
fi

POETRY_DEPS_FINGERPRINT="$(_compute_poetry_deps_fingerprint)"
if [[ -f "${POETRY_DEPS_STAMP}" ]] \
  && [[ "$(cat "${POETRY_DEPS_STAMP}")" == "${POETRY_DEPS_FINGERPRINT}" ]] \
  && _poetry_env_ready; then
  echo "[backend] Using cached Poetry environment."
elif ! _poetry_env_ready; then
  echo "[backend] WARNING: agent_host not importable — running poetry install" >&2
  (cd "${PROJECT_ROOT}" && "${POETRY_BIN}" install --no-interaction --quiet)
  POETRY_DEPS_FINGERPRINT="$(_compute_poetry_deps_fingerprint)"
  printf "%s" "${POETRY_DEPS_FINGERPRINT}" > "${POETRY_DEPS_STAMP}"
else
  # Env is usable but dependency metadata changed; mark the current fingerprint.
  printf "%s" "${POETRY_DEPS_FINGERPRINT}" > "${POETRY_DEPS_STAMP}"
fi

echo "backend_socket_path=${SOCKET_PATH}"
echo "backend_log=${LOG_FILE}"

_env_bool_true() {
  local raw="${1:-}"
  local lowered
  lowered="$(printf "%s" "${raw}" | tr '[:upper:]' '[:lower:]')"
  [[ "${lowered}" != "0" && "${lowered}" != "false" && "${lowered}" != "no" && "${lowered}" != "off" ]]
}

_ensure_required_spacy_model() {
  local preload_required="${AI_AGENT_PLAN_MODE_NLP_PRELOAD_REQUIRED:-1}"
  local model_name="${AI_AGENT_PLAN_MODE_NLP_MODEL:-en_core_web_trf}"
  local model_key model_stamp_file model_fingerprint
  model_name="$(printf "%s" "${model_name}" | xargs)"
  [[ -z "${model_name}" ]] && model_name="en_core_web_trf"
  model_key="$(printf "%s" "${model_name}" | tr -cs 'A-Za-z0-9._-' '_')"
  model_stamp_file="${PROJECT_CACHE_ROOT}/spacy-model-${model_key}.stamp"

  if ! _env_bool_true "${preload_required}"; then
    return 0
  fi

  model_fingerprint="$(
    cd "${PROJECT_ROOT}" \
      && AI_AGENT_PLAN_MODE_NLP_MODEL="${model_name}" \
      "${POETRY_BIN}" run python -c "import os,spacy,sys; print(f\"model={os.environ['AI_AGENT_PLAN_MODE_NLP_MODEL']}\\nspacy={spacy.__version__}\\npython={'.'.join(map(str, sys.version_info[:3]))}\")" 2>/dev/null \
      || printf "model=%s\nspacy=unknown\npython=unknown\n" "${model_name}"
  )"

  if [[ -f "${model_stamp_file}" ]] \
    && [[ "$(cat "${model_stamp_file}")" == "${model_fingerprint}" ]] \
    && (
      cd "${PROJECT_ROOT}" \
      && AI_AGENT_PLAN_MODE_NLP_MODEL="${model_name}" \
        "${POETRY_BIN}" run python -c "import importlib.util,os,sys; sys.exit(0 if importlib.util.find_spec(os.environ['AI_AGENT_PLAN_MODE_NLP_MODEL']) else 1)"
    ) >/dev/null 2>&1; then
    echo "[backend] Using cached spaCy model: ${model_name}"
    return 0
  fi

  echo "[backend] Verifying required spaCy model: ${model_name}"
  if (
    cd "${PROJECT_ROOT}" \
    && AI_AGENT_PLAN_MODE_NLP_MODEL="${model_name}" \
      "${POETRY_BIN}" run python -c "import os,spacy;spacy.load(os.environ['AI_AGENT_PLAN_MODE_NLP_MODEL'])"
  ) >/dev/null 2>&1; then
    printf "%s" "${model_fingerprint}" > "${model_stamp_file}"
    return 0
  fi

  echo "[backend] Installing required spaCy model: ${model_name}" >&2
  (cd "${PROJECT_ROOT}" && "${POETRY_BIN}" run python -m spacy download "${model_name}") >&2

  if ! (
    cd "${PROJECT_ROOT}" \
    && AI_AGENT_PLAN_MODE_NLP_MODEL="${model_name}" \
      "${POETRY_BIN}" run python -c "import os,spacy;spacy.load(os.environ['AI_AGENT_PLAN_MODE_NLP_MODEL'])"
  ) >/dev/null 2>&1; then
    echo "[backend] FATAL: Required spaCy model '${model_name}' is not loadable after install." >&2
    exit 1
  fi
  model_fingerprint="$(
    cd "${PROJECT_ROOT}" \
      && AI_AGENT_PLAN_MODE_NLP_MODEL="${model_name}" \
      "${POETRY_BIN}" run python -c "import os,spacy,sys; print(f\"model={os.environ['AI_AGENT_PLAN_MODE_NLP_MODEL']}\\nspacy={spacy.__version__}\\npython={'.'.join(map(str, sys.version_info[:3]))}\")" 2>/dev/null \
      || printf "model=%s\nspacy=unknown\npython=unknown\n" "${model_name}"
  )"
  printf "%s" "${model_fingerprint}" > "${model_stamp_file}"
}

_ensure_required_spacy_model

# Generate IPC auth token if not already set (mirrors BackendLauncher.swift).
if [[ -z "${AI_AGENT_IPC_AUTH_TOKEN:-}" ]]; then
  export AI_AGENT_IPC_AUTH_TOKEN
  AI_AGENT_IPC_AUTH_TOKEN="$(uuidgen)"
fi

cmd=("${POETRY_BIN}" run python -m agent_host.main --server --socket-path "${SOCKET_PATH}" --verbose)

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
  while [[ ! -S "${SOCKET_PATH}" && ${SECONDS} -lt ${deadline} ]]; do
    if ! kill -0 "${BACKEND_PID}" 2>/dev/null; then
      break
    fi
    sleep 0.1
  done
  if [[ ! -S "${SOCKET_PATH}" ]]; then
    if ! kill -0 "${BACKEND_PID}" 2>/dev/null; then
      echo "Backend process exited before creating socket: ${SOCKET_PATH}" >&2
    else
      echo "Backend failed to create socket within 60s: ${SOCKET_PATH}" >&2
    fi
    # Dump last 20 lines of log for debugging
    tail -20 "${LOG_FILE}" 2>/dev/null || true
    exit 1
  fi
  exit 0
fi

cd "${PROJECT_ROOT}"
exec "${cmd[@]}" >>"${LOG_FILE}" 2>&1
