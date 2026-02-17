"""Handler for the ``run_automation`` tool."""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:
    from agent_host.tools.executor import ToolExecutor

from agent_host.tools.executor import ToolExecutionError

_AUTOMATION_ENV_ALLOWLIST = {
    "HOME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "LOGNAME",
    "PATH",
    "PWD",
    "SHELL",
    "TMPDIR",
    "USER",
}
_AUTOMATION_EXTRA_ENV_VAR = "AI_AGENT_AUTOMATION_ENV_ALLOWLIST"
_ENV_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_GRACEFUL_SHUTDOWN_SECONDS = 5


def _graceful_terminate(process: subprocess.Popen[str]) -> None:
    """Terminate a process tree: SIGTERM → grace period → SIGKILL.

    Requires *start_new_session=True* on the Popen so that child processes
    spawned by shell scripts share a process group we can signal.
    """
    try:
        pgid = os.getpgid(process.pid)
        os.killpg(pgid, signal.SIGTERM)
    except OSError:
        # Process already exited or group unavailable — fall back to direct signal.
        process.terminate()


def _build_automation_env() -> dict[str, str]:
    """Construct a least-privilege environment for automation scripts."""
    env: dict[str, str] = {}

    for key in _AUTOMATION_ENV_ALLOWLIST:
        value = os.environ.get(key)
        if value is not None:
            env[key] = value

    extra_raw = os.environ.get(_AUTOMATION_EXTRA_ENV_VAR, "")
    if extra_raw.strip():
        for candidate in extra_raw.split(","):
            key = candidate.strip()
            if not key or not _ENV_NAME_PATTERN.fullmatch(key):
                continue
            value = os.environ.get(key)
            if value is not None:
                env[key] = value

    return env


def handle(executor: ToolExecutor, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Execute the run_automation tool."""
    name = str(arguments.get("name", "")).strip()
    if not name:
        raise ToolExecutionError("run_automation requires a non-empty 'name'", error_type="validation")

    if not executor.automations_dir.exists() or not executor.automations_dir.is_dir():
        raise ToolExecutionError(
            f"Automations directory is unavailable: {executor.automations_dir}"
        )
    script_raw, matched_via = executor._resolve_automation_script(name)
    script = script_raw.resolve(strict=True)
    if script.parent != executor.automations_dir:
        raise ToolExecutionError(
            f"Automation script must be directly inside {executor.automations_dir}: {script}"
        )

    env = _build_automation_env()
    inputs = arguments.get("inputs", {})
    if inputs is None:
        inputs_map: dict[str, Any] = {}
    elif isinstance(inputs, Mapping):
        inputs_map = dict(inputs)
    else:
        raise ToolExecutionError("run_automation 'inputs' must be an object when provided", error_type="validation")

    # Validate input values: only primitives allowed (no nested objects/arrays)
    for key, value in inputs_map.items():
        if not isinstance(key, str):
            raise ToolExecutionError(f"run_automation input key must be a string, got: {type(key).__name__}")
        if not isinstance(value, (str, int, float, bool, type(None))):
            raise ToolExecutionError(
                f"run_automation input '{key}' must be a primitive (string, number, boolean, null), "
                f"got {type(value).__name__}"
            )

    serialized_inputs = json.dumps(inputs_map, separators=(",", ":"))
    if len(serialized_inputs.encode("utf-8")) > executor._AUTOMATION_MAX_INPUT_SIZE_BYTES:
        raise ToolExecutionError(
            f"run_automation inputs exceed maximum size "
            f"({executor._AUTOMATION_MAX_INPUT_SIZE_BYTES} bytes)"
        )
    env["AI_AGENT_AUTOMATION_INPUTS"] = serialized_inputs

    if script.suffix == ".sh":
        command = ["/bin/zsh", str(script)]
    else:
        command = ["osascript", str(script)]
    timeout_seconds = 30

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            start_new_session=True,
        )
    except OSError as exc:
        raise ToolExecutionError(f"Failed to launch automation '{name}': {exc}") from exc

    timed_out = False
    try:
        stdout_raw, stderr_raw = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        # Stage 1: SIGTERM to process group for graceful shutdown
        _graceful_terminate(process)
        try:
            # Stage 2: Wait for graceful exit while draining remaining output
            stdout_raw, stderr_raw = process.communicate(
                timeout=_GRACEFUL_SHUTDOWN_SECONDS,
            )
        except subprocess.TimeoutExpired:
            # Stage 3: Force kill the entire process group
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except OSError:
                process.kill()
            stdout_raw, stderr_raw = process.communicate()

    stdout_value, stdout_truncated, stdout_total_chars = executor._truncate_text(
        (stdout_raw or "").strip(),
        limit=executor._AUTOMATION_OUTPUT_CHAR_LIMIT,
    )
    stderr_value, stderr_truncated, stderr_total_chars = executor._truncate_text(
        (stderr_raw or "").strip(),
        limit=executor._AUTOMATION_OUTPUT_CHAR_LIMIT,
    )

    if timed_out:
        return {
            "ok": False,
            "name": name,
            "matched_via": matched_via,
            "script": str(script),
            "command": command,
            "exit_code": process.returncode,
            "timed_out": True,
            "timeout_seconds": timeout_seconds,
            "error": f"Automation timed out after {timeout_seconds} seconds",
            "stdout": stdout_value,
            "stderr": stderr_value,
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
            "stdout_total_chars": stdout_total_chars,
            "stderr_total_chars": stderr_total_chars,
        }

    return {
        "ok": process.returncode == 0,
        "name": name,
        "matched_via": matched_via,
        "script": str(script),
        "command": command,
        "exit_code": process.returncode,
        "timed_out": False,
        "stdout": stdout_value,
        "stderr": stderr_value,
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
        "stdout_total_chars": stdout_total_chars,
        "stderr_total_chars": stderr_total_chars,
    }
