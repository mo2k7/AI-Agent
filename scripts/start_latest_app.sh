#!/usr/bin/env bash
# start_latest_app.sh — Complete clean-build startup for the AI Agent.
#
# Guarantees every launch runs against freshly compiled code with no
# stale threads, sockets, caches, or derived data from previous runs.
#
# Safety:  SIGTERM first, SIGKILL only after grace period.
#          Process-group kill so child trees die too.
#          Lock-file prevents concurrent startup races.
# Perf:   Parallel poetry-install + swift-clean when both are needed.
#          Artifact rotation keeps disk bounded.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ──────────────────────────────────────────────────────────────
# Arguments
# ──────────────────────────────────────────────────────────────
RUN_ID=""
SKIP_BACKEND=0
KEEP_ARTIFACTS=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-id)
      RUN_ID="${2:-}"
      shift 2
      ;;
    --skip-backend)
      SKIP_BACKEND=1
      shift
      ;;
    --keep-artifacts)
      KEEP_ARTIFACTS=1
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      echo "Usage: bash scripts/start_latest_app.sh [--run-id <id>] [--skip-backend] [--keep-artifacts]" >&2
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

export AI_AGENT_BOOTSTRAPPED=1

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

POETRY_BIN=""
if POETRY_BIN="$(_resolve_poetry_bin)"; then
  :
elif [[ "${SKIP_BACKEND}" -eq 0 ]]; then
  if ! command -v python3 >/dev/null 2>&1; then
    echo "[prereq] Poetry missing and python3 unavailable for Poetry install." >&2
    exit 1
  fi
  echo "[prereq] Poetry not found; installing Poetry..." >&2
  if [[ -n "${VIRTUAL_ENV:-}" ]]; then
    python3 -m pip install "poetry>=1.8,<2.0" >&2
  else
    python3 -m pip install --user "poetry>=1.8,<2.0" >&2
  fi
  hash -r
  if ! POETRY_BIN="$(_resolve_poetry_bin)"; then
    echo "[prereq] Poetry install completed but poetry binary is still unavailable." >&2
    exit 1
  fi
fi

# ──────────────────────────────────────────────────────────────
# Lock file — prevent concurrent startup races
# ──────────────────────────────────────────────────────────────
LOCK_FILE="${AI_AGENT_LOCK_FILE:-/tmp/ai-agent-start-latest.lock}"

_read_lock_pid() {
  local raw
  raw="$(cat "${LOCK_FILE}" 2>/dev/null || true)"
  raw="${raw%%[^0-9]*}"
  printf "%s" "${raw}"
}

# ──────────────────────────────────────────────────────────────
# PID collection — finds ALL related processes (including children)
# ──────────────────────────────────────────────────────────────
TARGET_PIDS=()
TARGET_PGIDS=()

CURRENT_PGID="$(ps -o pgid= -p "$$" 2>/dev/null | tr -d '[:space:]' || true)"

_pid_command() {
  local pid="${1:-}"
  [[ -z "${pid}" ]] && return 0
  ps -p "${pid}" -o command= 2>/dev/null | head -n 1 || true
}

_is_agent_process_command() {
  local cmd="${1:-}"
  [[ -z "${cmd}" ]] && return 1
  [[ "${cmd}" == *"${PROJECT_ROOT}/scripts/start_latest_app.sh"* ]] && return 0
  [[ "${cmd}" == *"${PROJECT_ROOT}/scripts/run_backend.sh"* ]] && return 0
  [[ "${cmd}" == *"${PROJECT_ROOT}/scripts/run_frontend.sh"* ]] && return 0
  [[ "${cmd}" == *"agent_host.main"* ]] && return 0
  [[ "${cmd}" == *"swift run --package-path ui"* ]] && return 0
  [[ "${cmd}" == *"AIAgentApp"* ]] && return 0
  [[ "${cmd}" == *"${AI_AGENT_RUN_DIR}"* ]] && return 0
  return 1
}

_has_target_pid() {
  local needle="$1"
  local pid
  for pid in "${TARGET_PIDS[@]:-}"; do
    [[ "${pid}" == "${needle}" ]] && return 0
  done
  return 1
}

_add_target_pid() {
  local candidate="${1:-}"
  candidate="${candidate//[^0-9]/}"
  [[ -z "${candidate}" ]] && return
  [[ "${candidate}" == "$$" ]] && return
  _has_target_pid "${candidate}" && return
  TARGET_PIDS+=("${candidate}")
}

_add_target_pid_if_agent() {
  local candidate="${1:-}"
  candidate="${candidate//[^0-9]/}"
  [[ -z "${candidate}" ]] && return
  [[ "${candidate}" == "$$" ]] && return
  kill -0 "${candidate}" 2>/dev/null || return 0
  local cmd
  cmd="$(_pid_command "${candidate}")"
  _is_agent_process_command "${cmd}" || return 0
  _add_target_pid "${candidate}"
}

_has_target_pgid() {
  local needle="$1"
  local pgid
  for pgid in "${TARGET_PGIDS[@]:-}"; do
    [[ "${pgid}" == "${needle}" ]] && return 0
  done
  return 1
}

_collect_target_pgids() {
  local pid pgid
  for pid in "${TARGET_PIDS[@]:-}"; do
    pgid="$(ps -o pgid= -p "${pid}" 2>/dev/null | tr -d '[:space:]' || true)"
    [[ -z "${pgid}" ]] && continue
    [[ "${pgid}" == "${CURRENT_PGID}" ]] && continue
    _has_target_pgid "${pgid}" && continue
    TARGET_PGIDS+=("${pgid}")
  done
}

_collect_pids_from_pid_files() {
  local pid_file pid
  shopt -s nullglob
  for pid_file in "${PROJECT_ROOT}"/artifacts/*/*.pid; do
    pid="$(cat "${pid_file}" 2>/dev/null || true)"
    _add_target_pid_if_agent "${pid}"
  done
  shopt -u nullglob
  if [[ -f "${LOCK_FILE}" ]]; then
    _add_target_pid_if_agent "$(_read_lock_pid)"
  fi
  return 0
}

_collect_pids_by_substring() {
  local needle="$1"
  local line pid cmd
  while IFS= read -r line; do
    pid="${line%% *}"
    cmd="${line#* }"
    pid="${pid//[^0-9]/}"
    [[ -z "${pid}" ]] && continue
    [[ "${cmd}" == *"${needle}"* ]] && _add_target_pid "${pid}"
  done < <(ps -axo pid=,command= 2>/dev/null || true)
  return 0
}

# Collect descendants of every collected PID (recursive BFS).
_collect_child_pids() {
  local queue=("${TARGET_PIDS[@]:-}")
  local parent child
  while [[ ${#queue[@]} -gt 0 ]]; do
    parent="${queue[0]}"
    queue=("${queue[@]:1}")
    while IFS= read -r child; do
      child="${child//[^0-9]/}"
      [[ -z "${child}" ]] && continue
      if ! _has_target_pid "${child}"; then
        _add_target_pid "${child}"
        queue+=("${child}")
      fi
    done < <(pgrep -P "${parent}" 2>/dev/null || true)
  done
  return 0
}

_collect_pids_from_sockets() {
  command -v lsof >/dev/null 2>&1 || return 0
  local sock pid
  shopt -s nullglob
  for sock in /tmp/ai-agent-*.sock; do
    while IFS= read -r pid; do
      _add_target_pid_if_agent "${pid}"
    done < <(lsof -t -- "${sock}" 2>/dev/null || true)
  done
  shopt -u nullglob
  return 0
}

_collect_related_pids() {
  TARGET_PIDS=()
  TARGET_PGIDS=()
  _collect_pids_from_pid_files
  _collect_pids_from_sockets
  _collect_pids_by_substring "${PROJECT_ROOT}/scripts/start_latest_app.sh"
  _collect_pids_by_substring "${PROJECT_ROOT}/scripts/run_backend.sh"
  _collect_pids_by_substring "${PROJECT_ROOT}/scripts/run_frontend.sh"
  _collect_pids_by_substring "-m agent_host.main"
  _collect_pids_by_substring "swift run --package-path ui AIAgentApp"
  _collect_pids_by_substring "swift run AIAgentApp"
  _collect_pids_by_substring "AIAgentApp"
  # Also catch poetry-spawned python subprocesses
  _collect_pids_by_substring "agent_host.main --server"
  # Walk the process tree to catch nested children
  _collect_child_pids
  _collect_target_pgids
  return 0
}

# ──────────────────────────────────────────────────────────────
# Process termination — SIGTERM → grace → SIGKILL
# ──────────────────────────────────────────────────────────────
_terminate_collected_pids() {
  local target_pids=()
  local target_pgids=()
  local pid
  local pgid

  if [[ "${TARGET_PIDS+x}" == "x" ]]; then
    for pid in "${TARGET_PIDS[@]-}"; do
      [[ -n "${pid:-}" ]] && target_pids+=("${pid}")
    done
  fi
  if [[ "${TARGET_PGIDS+x}" == "x" ]]; then
    for pgid in "${TARGET_PGIDS[@]-}"; do
      [[ -n "${pgid:-}" ]] && target_pgids+=("${pgid}")
    done
  fi
  [[ ${#target_pids[@]} -eq 0 && ${#target_pgids[@]} -eq 0 ]] && return

  if [[ ${#target_pgids[@]} -gt 0 ]]; then
    echo "[cleanup] Stopping process groups: ${target_pgids[*]}"
    for pgid in "${target_pgids[@]}"; do
      kill -TERM -- "-${pgid}" 2>/dev/null || true
    done
  fi
  if [[ ${#target_pids[@]} -gt 0 ]]; then
    echo "[cleanup] Stopping ${#target_pids[@]} AI Agent process(es): ${target_pids[*]}"
    kill "${target_pids[@]}" 2>/dev/null || true
  fi

  local alive=()
  local alive_groups=()
  for _ in {1..30}; do
    alive=()
    for pid in ${target_pids[@]+"${target_pids[@]}"}; do
      kill -0 "${pid}" 2>/dev/null && alive+=("${pid}")
    done
    alive_groups=()
    for pgid in ${target_pgids[@]+"${target_pgids[@]}"}; do
      pgrep -g "${pgid}" >/dev/null 2>&1 && alive_groups+=("${pgid}")
    done
    [[ ${#alive[@]} -eq 0 && ${#alive_groups[@]} -eq 0 ]] && break
    sleep 0.2
  done

  if [[ ${#alive_groups[@]} -gt 0 ]]; then
    echo "[cleanup] Force-killing stubborn process groups: ${alive_groups[*]}"
    for pgid in "${alive_groups[@]}"; do
      kill -9 -- "-${pgid}" 2>/dev/null || true
    done
    sleep 0.3
  fi
  if [[ ${#alive[@]} -gt 0 ]]; then
    echo "[cleanup] Force-killing stubborn processes: ${alive[*]}"
    kill -9 "${alive[@]}" 2>/dev/null || true
    sleep 0.3
  fi
}

# ──────────────────────────────────────────────────────────────
# Stale socket cleanup
# ──────────────────────────────────────────────────────────────
_clean_stale_sockets() {
  local sock
  shopt -s nullglob
  for sock in /tmp/ai-agent-*.sock; do
    echo "[cleanup] Removing stale socket: ${sock}"
    rm -f "${sock}"
  done
  shopt -u nullglob
}

# ──────────────────────────────────────────────────────────────
# Python bytecache flush
# ──────────────────────────────────────────────────────────────
_clean_python_cache() {
  find "${PROJECT_ROOT}" \
    -path "${PROJECT_ROOT}/.venv" -prune -o \
    -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
  find "${PROJECT_ROOT}" \
    -path "${PROJECT_ROOT}/.venv" -prune -o \
    -name "*.pyc" -delete 2>/dev/null || true
  rm -rf "${PROJECT_ROOT}/.pytest_cache" "${PROJECT_ROOT}/.mypy_cache" "${PROJECT_ROOT}/.ruff_cache" 2>/dev/null || true
  echo "[clean] Purged Python caches"
}

_clean_swift_build_dir() {
  local build_dir="$1"
  [[ -d "${build_dir}" ]] || return 0

  local attempt
  for attempt in {1..6}; do
    rm -rf "${build_dir}" 2>/dev/null || true
    if [[ ! -e "${build_dir}" ]]; then
      return 0
    fi
    # If files were left read-only or created mid-delete, retry.
    chmod -R u+w "${build_dir}" 2>/dev/null || true
    sleep 0.2
  done

  echo "[build] FATAL: Unable to remove Swift build dir: ${build_dir}" >&2
  return 1
}

# ──────────────────────────────────────────────────────────────
# Artifact rotation — keep only the N most recent run dirs
# ──────────────────────────────────────────────────────────────
MAX_ARTIFACT_RUNS="${AI_AGENT_MAX_ARTIFACT_RUNS:-10}"

_rotate_artifacts() {
  [[ "${KEEP_ARTIFACTS}" -eq 1 ]] && return
  local artifact_root="${PROJECT_ROOT}/artifacts"
  [[ ! -d "${artifact_root}" ]] && return

  local dirs=()
  while IFS= read -r d; do
    dirs+=("${d}")
  done < <(ls -1dt "${artifact_root}"/*/ 2>/dev/null || true)

  local count=${#dirs[@]}
  if [[ ${count} -gt ${MAX_ARTIFACT_RUNS} ]]; then
    local excess=$(( count - MAX_ARTIFACT_RUNS ))
    echo "[clean] Rotating ${excess} old artifact dir(s)"
    for (( i = count - excess; i < count; i++ )); do
      rm -rf "${dirs[${i}]}"
    done
  fi
}

# ──────────────────────────────────────────────────────────────
# Full pre-launch cleanup
# ──────────────────────────────────────────────────────────────
_fresh_start_cleanup() {
  _collect_related_pids
  _terminate_collected_pids

  rm -f "${LOCK_FILE}"

  local pid_file
  shopt -s nullglob
  for pid_file in "${PROJECT_ROOT}"/artifacts/*/*.pid; do
    rm -f "${pid_file}"
  done
  shopt -u nullglob

  _clean_stale_sockets
  _clean_python_cache
  _rotate_artifacts
}

echo "================================================================"
echo "  AI Agent — Clean Build Startup"
echo "================================================================"
echo ""

_fresh_start_cleanup

# ──────────────────────────────────────────────────────────────
# Startup lock acquisition
# ──────────────────────────────────────────────────────────────
_acquire_startup_lock() {
  ( set -o noclobber; printf "%s\n" "$$" > "${LOCK_FILE}" ) 2>/dev/null
}

if ! _acquire_startup_lock; then
  existing_pid="$(_read_lock_pid)"
  if [[ -n "${existing_pid}" ]] && [[ "${existing_pid}" != "$$" ]] && kill -0 "${existing_pid}" 2>/dev/null; then
    echo "[lock] Replacing active startup process (pid=${existing_pid})."
    kill "${existing_pid}" 2>/dev/null || true
    for _ in {1..25}; do
      kill -0 "${existing_pid}" 2>/dev/null || break
      sleep 0.2
    done
    kill -0 "${existing_pid}" 2>/dev/null && kill -9 "${existing_pid}" 2>/dev/null || true
  else
    echo "[lock] Removing stale lock file."
  fi

  rm -f "${LOCK_FILE}"
  if ! _acquire_startup_lock; then
    echo "[lock] FATAL: Failed to acquire startup lock." >&2
    exit 1
  fi
fi

# ──────────────────────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────────────────────
BACKEND_PID_FILE="${AI_AGENT_RUN_DIR}/startup_backend.pid"
BUILD_LOG="${AI_AGENT_RUN_DIR}/startup_build.log"

cleanup() {
  set +e
  if [[ -f "${LOCK_FILE}" ]] && [[ "$(cat "${LOCK_FILE}" 2>/dev/null || true)" == "$$" ]]; then
    rm -f "${LOCK_FILE}"
  fi
  if [[ "${SKIP_BACKEND}" -eq 0 ]] && [[ -f "${BACKEND_PID_FILE}" ]]; then
    pid="$(cat "${BACKEND_PID_FILE}" 2>/dev/null || true)"
    if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
      kill -TERM -- "-${pid}" 2>/dev/null || true
      kill "${pid}" 2>/dev/null || true
      wait "${pid}" 2>/dev/null || true
    fi
  fi
}
trap cleanup EXIT INT TERM

# ──────────────────────────────────────────────────────────────
# Prerequisites
# ──────────────────────────────────────────────────────────────
if ! command -v swift >/dev/null 2>&1; then
  echo "[prereq] swift is required but was not found in PATH." >&2
  exit 1
fi
if [[ "${SKIP_BACKEND}" -eq 0 ]] && [[ -z "${POETRY_BIN}" ]]; then
  echo "[prereq] poetry is required but was not found in PATH or standard install locations." >&2
  exit 1
fi

mkdir -p "${AI_AGENT_RUN_DIR}"
echo "[config] run_id    = ${AI_AGENT_RUN_ID}"
echo "[config] run_dir   = ${AI_AGENT_RUN_DIR}"
echo "[config] socket    = ${AI_AGENT_SOCKET_PATH}"
echo "[config] build_log = ${BUILD_LOG}"

PROJECT_CACHE_ROOT="${PROJECT_ROOT}/.ai-agent-cache"
POETRY_DEPS_STAMP="${PROJECT_CACHE_ROOT}/poetry-deps.stamp"
mkdir -p "${PROJECT_CACHE_ROOT}"

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

# Toolchain cache dirs pinned to run artifacts for deterministic permissions.
CACHE_ROOT="${AI_AGENT_RUN_DIR}/toolchain-cache"
CLANG_CACHE_DIR="${CACHE_ROOT}/clang-module-cache"
SWIFT_CACHE_DIR="${CACHE_ROOT}/swift-module-cache"
mkdir -p "${CLANG_CACHE_DIR}" "${SWIFT_CACHE_DIR}"
export CLANG_MODULE_CACHE_PATH="${CLANG_CACHE_DIR}"
export SWIFT_MODULE_CACHE_PATH="${SWIFT_CACHE_DIR}"

# ──────────────────────────────────────────────────────────────
# Phase 1: Clean build (parallel where possible)
# ──────────────────────────────────────────────────────────────
echo ""
echo "[build] Starting clean build…"
BUILD_FAILED=0

# Clean Swift build artifacts for a truly fresh compile
SWIFT_BUILD_DIR="${PROJECT_ROOT}/ui/.build"
if [[ -d "${SWIFT_BUILD_DIR}" ]]; then
  echo "[build] Cleaning Swift derived data…"
  if ! _clean_swift_build_dir "${SWIFT_BUILD_DIR}"; then
    BUILD_FAILED=1
  fi
fi

# Sync poetry deps in background while Swift clean-builds
POETRY_INSTALL_REQUIRED=0
POETRY_DEPS_FINGERPRINT=""
if [[ "${SKIP_BACKEND}" -eq 0 ]]; then
  POETRY_DEPS_FINGERPRINT="$(_compute_poetry_deps_fingerprint)"
  if [[ -f "${POETRY_DEPS_STAMP}" ]] \
    && [[ "$(cat "${POETRY_DEPS_STAMP}")" == "${POETRY_DEPS_FINGERPRINT}" ]] \
    && _poetry_env_ready; then
    echo "[build] Python dependencies unchanged; using cached Poetry environment."
  else
    POETRY_INSTALL_REQUIRED=1
    echo "[build] Syncing Python dependencies (background)…"
    (
      cd "${PROJECT_ROOT}"
      "${POETRY_BIN}" install --no-interaction --sync --quiet 2>&1 \
        || "${POETRY_BIN}" install --no-interaction --quiet 2>&1
    ) > "${AI_AGENT_RUN_DIR}/poetry_install.log" 2>&1 &
    POETRY_PID=$!
  fi
fi

# Swift clean build (foreground — this is the long pole)
echo "[build] Compiling Swift frontend (clean)…"
BUILD_START_TS=$(date +%s)
if ! (
  cd "${PROJECT_ROOT}"
  swift build --package-path ui -c debug 2>&1
) | tee "${BUILD_LOG}"; then
  BUILD_FAILED=1
fi
BUILD_END_TS=$(date +%s)
BUILD_ELAPSED=$(( BUILD_END_TS - BUILD_START_TS ))
echo "[build] Swift build finished in ${BUILD_ELAPSED}s"

# Wait for poetry install if running
if [[ "${SKIP_BACKEND}" -eq 0 ]] && [[ "${POETRY_INSTALL_REQUIRED}" -eq 1 ]] && [[ -n "${POETRY_PID:-}" ]]; then
  if ! wait "${POETRY_PID}"; then
    echo "[build] FATAL: poetry dependency sync failed — see ${AI_AGENT_RUN_DIR}/poetry_install.log" >&2
    BUILD_FAILED=1
  else
    POETRY_DEPS_FINGERPRINT="$(_compute_poetry_deps_fingerprint)"
    printf "%s" "${POETRY_DEPS_FINGERPRINT}" > "${POETRY_DEPS_STAMP}"
    echo "[build] Python dependencies synced"
  fi
fi

if [[ "${BUILD_FAILED}" -eq 1 ]]; then
  echo ""
  echo "[build] FATAL: clean build/bootstrap failed." >&2
  echo "[build] See Swift log: ${BUILD_LOG}" >&2
  if [[ "${SKIP_BACKEND}" -eq 0 ]]; then
    echo "[build] See Poetry log: ${AI_AGENT_RUN_DIR}/poetry_install.log" >&2
  fi
  exit 1
fi

# ──────────────────────────────────────────────────────────────
# Phase 2: Launch backend
# ──────────────────────────────────────────────────────────────
export AI_AGENT_PING_TIMEOUT_MS="${AI_AGENT_PING_TIMEOUT_MS:-5000}"

# Generate IPC auth token for this run so both backend and frontend share it.
if [[ -z "${AI_AGENT_IPC_AUTH_TOKEN:-}" ]]; then
  export AI_AGENT_IPC_AUTH_TOKEN
  AI_AGENT_IPC_AUTH_TOKEN="$(uuidgen)"
fi

if [[ "${SKIP_BACKEND}" -eq 0 ]]; then
  echo ""
  echo "[launch] Starting Python backend…"
  (
    cd "${PROJECT_ROOT}"
    bash scripts/run_backend.sh \
      --run-id "${AI_AGENT_RUN_ID}" \
      --background \
      --pid-file "${BACKEND_PID_FILE}"
  )
  echo "[launch] Backend is ready"
fi

# ──────────────────────────────────────────────────────────────
# Phase 3: Launch frontend
# ──────────────────────────────────────────────────────────────
echo ""
echo "[launch] Starting Swift frontend…"
(
  cd "${PROJECT_ROOT}"
  bash scripts/run_frontend.sh --run-id "${AI_AGENT_RUN_ID}" --skip-build
)
