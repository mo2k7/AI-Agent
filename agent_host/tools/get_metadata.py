"""Handler for the ``get_metadata`` tool."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:
    from agent_host.tools.executor import ToolExecutor

from agent_host.tools.executor import ToolExecutionError


def handle(executor: ToolExecutor, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Execute the get_metadata tool."""
    raw_paths = arguments.get("paths")
    if not isinstance(raw_paths, list) or not raw_paths:
        raise ToolExecutionError("get_metadata requires a non-empty 'paths' array")

    records: list[dict[str, Any]] = []
    for raw in raw_paths:
        raw_str = str(raw)
        try:
            candidate = executor._normalize_user_path(raw_str, must_exist=False)
        except ToolExecutionError as exc:
            records.append({"path": raw_str, "exists": False, "error": str(exc)})
            continue

        if not candidate.exists():
            records.append({"path": str(candidate), "exists": False})
            continue
        records.append(executor._serialize_stat(candidate))

    return {"ok": True, "items": records}
