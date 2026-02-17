"""Handler for the ``summarize_note`` tool."""

from __future__ import annotations

from typing import Any

from agent_host.tools.registry import NoteToolContext, register_note_handler


async def handle(ctx: NoteToolContext, arguments: dict[str, Any]) -> dict[str, object]:
    """Execute the summarize_note tool."""
    raw_nid = arguments.get("note_id") or ""
    summary_level = arguments.get("level", "condensed") or "condensed"
    summary_content = arguments.get("content", "") or ""

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
    if not summary_content.strip():
        return {
            "ok": False,
            "output": "Summary content is empty.",
        }

    note_type = "summary" if summary_level != "key_points" else "key_points"
    type_tag = f"<!-- note-type:{note_type} -->\n"
    level_label = summary_level.replace("_", " ").title()
    title_line = f"**{level_label} Summary**\n"
    full_content = type_tag + title_line + summary_content

    created = await ctx.run_blocking(
        label="notes.create_summary",
        timeout_seconds=ctx.db_timeout_seconds,
        func=ctx.memory_manager.create_note,
        args=(ctx.session_id,),
        kwargs={"content": full_content, "source": "agent"},
        request_id=ctx.request_id,
        method=ctx.method,
    )
    return {
        "ok": True,
        "output": (
            f"Summary created (id={created['note_id'][:8]}). "
            f"Level: {summary_level}. Original note preserved (id={resolved_nid[:8]}). "
            "The summary is now visible in the user's notes panel."
        ),
    }


register_note_handler("summarize_note", handle)
