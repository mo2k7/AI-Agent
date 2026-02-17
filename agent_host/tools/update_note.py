"""Handler for the ``update_note`` tool."""

from __future__ import annotations

from typing import Any

from agent_host.tools.registry import NoteToolContext, register_note_handler


async def handle(ctx: NoteToolContext, arguments: dict[str, Any]) -> dict[str, object]:
    """Execute the update_note tool."""
    raw_nid = arguments.get("note_id") or ""
    new_content = arguments.get("content")
    new_pinned = arguments.get("is_pinned")

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

    updated = await ctx.run_blocking(
        label="notes.update",
        timeout_seconds=ctx.db_timeout_seconds,
        func=ctx.memory_manager.update_note,
        args=(ctx.session_id, resolved_nid),
        kwargs={"content": new_content, "is_pinned": new_pinned},
        request_id=ctx.request_id,
        method=ctx.method,
    )
    if updated is None:
        return {
            "ok": False,
            "output": f"Note '{raw_nid}' not found or already deleted.",
        }
    return {
        "ok": True,
        "output": f"Note updated (id={updated['note_id'][:8]}).",
    }


register_note_handler("update_note", handle)
