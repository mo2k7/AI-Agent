"""Handler for the ``open_item`` tool."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:
    from agent_host.tools.executor import ToolExecutor

from agent_host.tools.executor import ToolExecutionError


def handle(executor: ToolExecutor, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Execute the open_item tool."""
    if not executor.enable_open_item:
        raise ToolExecutionError("open_item is disabled by configuration", error_type="permission")

    path_raw = str(arguments.get("path", ""))
    path = executor._normalize_user_path(path_raw, must_exist=True)

    # Application whitelist
    application_raw = arguments.get("application")
    command = ["open"]
    app_used: str | None = None
    if isinstance(application_raw, str) and application_raw.strip():
        app_name = application_raw.strip()
        if app_name.lower() not in executor._OPEN_ITEM_APP_WHITELIST:
            allowed = ", ".join(sorted(executor._OPEN_ITEM_APP_WHITELIST))
            raise ToolExecutionError(
                f"Application '{app_name}' is not in the allowed list. "
                f"Allowed applications: {allowed}",
                error_type="validation",
            )
        command.extend(["-a", app_name])
        app_used = app_name

    command.append(str(path))

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ToolExecutionError(
            f"open_item timed out for '{path}' after {exc.timeout} seconds",
            error_type="timeout",
            retryable=True,
        ) from exc
    except OSError as exc:
        raise ToolExecutionError(f"open_item failed to start: {exc}") from exc
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or "open command failed"
        raise ToolExecutionError(message)
    result: dict[str, Any] = {"ok": True, "path": str(path), "launched": True}
    if app_used:
        result["application"] = app_used
    return result
