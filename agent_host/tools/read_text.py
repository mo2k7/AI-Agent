"""Handler for the ``read_text`` tool."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:
    from agent_host.tools.executor import ToolExecutor

from agent_host.tools.executor import ToolExecutionError


def handle(executor: ToolExecutor, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Execute the read_text tool."""
    path_raw = str(arguments.get("path", ""))
    path = executor._normalize_user_path(path_raw, must_exist=True)
    if not path.is_file():
        raise ToolExecutionError(f"Path is not a file: {path}")

    file_size = path.stat().st_size
    selected_start = 0
    selected_end = file_size

    byte_range = arguments.get("byte_range")
    if byte_range is not None:
        if (
            not isinstance(byte_range, list)
            or len(byte_range) != 2
            or not all(isinstance(value, int) and not isinstance(value, bool) for value in byte_range)
        ):
            raise ToolExecutionError("byte_range must be [start, end] integers")
        start, end = int(byte_range[0]), int(byte_range[1])
        if start < 0 or end < 0 or end < start:
            raise ToolExecutionError("byte_range must satisfy 0 <= start <= end")
        selected_start = min(start, file_size)
        selected_end = min(end, file_size)

    chunk_size = max(0, selected_end - selected_start)

    # Safety: enforce maximum read size to prevent OOM
    if chunk_size > executor._MAX_READ_BYTES:
        raise ToolExecutionError(
            f"Requested read segment ({chunk_size} bytes) exceeds maximum "
            f"({executor._MAX_READ_BYTES} bytes). Use byte_range to read in smaller chunks."
        )

    chunk = b""
    if chunk_size > 0:
        try:
            with path.open("rb") as handle:
                handle.seek(selected_start)
                chunk = handle.read(chunk_size)
        except OSError as exc:
            raise ToolExecutionError(f"Failed to read file '{path}': {exc}") from exc
    text = chunk.decode("utf-8", errors="replace")
    return {
        "ok": True,
        "path": str(path),
        "encoding": "utf-8",
        "byte_range": [selected_start, selected_end],
        "content": text,
    }
