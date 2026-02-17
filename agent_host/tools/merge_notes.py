"""Handler for the ``merge_notes`` tool."""

from __future__ import annotations

import logging
from typing import Any

from agent_host.tools.registry import NoteToolContext, register_note_handler

logger = logging.getLogger(__name__)


async def handle(ctx: NoteToolContext, arguments: dict[str, Any]) -> dict[str, object]:
    """Execute the merge_notes tool."""
    raw_ids = arguments.get("note_ids", []) or []
    merged_content = arguments.get("merged_content", "") or ""
    merge_title = arguments.get("title", "") or ""
    merge_note_type = arguments.get("note_type", "") or ""

    if merge_note_type:
        merged_content = f"<!-- note-type:{merge_note_type} -->\n{merged_content}"
    if merge_title:
        merged_content = f"**{merge_title}**\n{merged_content}"

    # Pre-fetch notes once for batch resolution
    notes_cache = await ctx.run_blocking(
        label="notes.list_for_merge_resolve",
        timeout_seconds=ctx.db_timeout_seconds,
        func=ctx.memory_manager.list_notes,
        args=(ctx.session_id,),
        kwargs={"limit": 200},
        request_id=ctx.request_id,
        method=ctx.method,
    )

    # Resolve all source note IDs
    resolved_ids: list[str] = []
    unresolved: list[str] = []
    for raw_nid in raw_ids:
        rid = await ctx.resolve_note_id(
            ctx.session_id,
            raw_nid,
            ctx.memory_manager,
            ctx.db_timeout_seconds,
            ctx.request_id,
            ctx.method,
            notes_cache=notes_cache,
        )
        if rid is None:
            unresolved.append(raw_nid)
        else:
            resolved_ids.append(rid)

    if unresolved:
        return {
            "ok": False,
            "output": f"Could not resolve note IDs: {', '.join(unresolved)}.",
        }

    # Create the merged note
    created = await ctx.run_blocking(
        label="notes.merge_create",
        timeout_seconds=ctx.db_timeout_seconds,
        func=ctx.memory_manager.create_note,
        args=(ctx.session_id,),
        kwargs={"content": merged_content, "source": "agent"},
        request_id=ctx.request_id,
        method=ctx.method,
    )

    # Soft-delete source notes
    deleted_count = 0
    for rid in resolved_ids:
        try:
            d = await ctx.run_blocking(
                label="notes.merge_delete",
                timeout_seconds=ctx.db_timeout_seconds,
                func=ctx.memory_manager.delete_note,
                args=(ctx.session_id, rid),
                request_id=ctx.request_id,
                method=ctx.method,
            )
            if d:
                deleted_count += 1
        except Exception:
            logger.warning("merge_notes: failed to delete source %s", rid[:8])

    total = len(resolved_ids)
    if deleted_count == total:
        deletion_msg = "Source notes removed."
    elif deleted_count > 0:
        deletion_msg = (
            f"{deleted_count}/{total} source notes removed (some failed)."
        )
    else:
        deletion_msg = "Source notes could not be removed."

    return {
        "ok": True,
        "output": (
            f"Merged {total} notes into new note "
            f"(id={created['note_id'][:8]}). "
            f"{deletion_msg}"
        ),
    }


register_note_handler("merge_notes", handle)
