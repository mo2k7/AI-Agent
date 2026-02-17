"""Handler for the ``delete_note`` tool."""

from __future__ import annotations

from typing import Any

from agent_host.tools.registry import NoteToolContext, register_note_handler


async def handle(ctx: NoteToolContext, arguments: dict[str, Any]) -> dict[str, object]:
    """Execute the delete_note tool."""
    raw_nid = arguments.get("note_id") or ""

    resolved_nid = await ctx.resolve_note_id(
        ctx.session_id,
        raw_nid,
        ctx.memory_manager,
        ctx.db_timeout_seconds,
        ctx.request_id,
        ctx.method,
    )
    if resolved_nid is None:
        return {
            "ok": False,
            "output": f"No note found matching id prefix '{raw_nid}'.",
        }

    deleted = await ctx.run_blocking(
        label="notes.delete",
        timeout_seconds=ctx.db_timeout_seconds,
        func=ctx.memory_manager.delete_note,
        args=(ctx.session_id, resolved_nid),
        request_id=ctx.request_id,
        method=ctx.method,
    )
    return {
        "ok": bool(deleted),
        "output": (
            f"Note deleted (id={resolved_nid[:8]})."
            if deleted
            else f"Note '{resolved_nid[:8]}' could not be deleted."
        ),
    }


register_note_handler("delete_note", handle)
