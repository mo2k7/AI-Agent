"""Handler for the ``create_directory`` tool."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:
    from agent_host.tools.executor import ToolExecutor

from agent_host.tools.executor import ToolExecutionError


def handle(executor: ToolExecutor, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Execute the create_directory tool."""
    path_raw = str(arguments.get("path", "")).strip()
    if not path_raw:
        raise ToolExecutionError("create_directory requires a non-empty 'path'")

    exist_ok_raw = arguments.get("exist_ok", True)
    if isinstance(exist_ok_raw, bool):
        exist_ok = exist_ok_raw
    elif isinstance(exist_ok_raw, str):
        normalized = exist_ok_raw.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            exist_ok = True
        elif normalized in {"0", "false", "no", "off"}:
            exist_ok = False
        else:
            raise ToolExecutionError(
                "create_directory 'exist_ok' must be a boolean",
                error_type="validation",
            )
    else:
        raise ToolExecutionError(
            "create_directory 'exist_ok' must be a boolean",
            error_type="validation",
        )

    path = executor._normalize_user_path(path_raw, must_exist=False)

    already_existed = path.exists()
    if already_existed and not exist_ok:
        raise ToolExecutionError(f"Directory already exists: {path}")
    if already_existed and not path.is_dir():
        raise ToolExecutionError(f"Path exists but is not a directory: {path}")

    try:
        path.mkdir(parents=True, exist_ok=exist_ok)
    except OSError as exc:
        raise ToolExecutionError(f"Failed to create directory '{path}': {exc}") from exc

    return {
        "ok": True,
        "path": str(path),
        "created": not already_existed,
        "already_existed": already_existed,
    }
