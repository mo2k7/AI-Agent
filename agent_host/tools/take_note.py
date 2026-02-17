"""Handler for the ``take_note`` tool."""

from __future__ import annotations

from typing import Any

from agent_host.tools._helpers import (
    _build_teacher_note_body,
    _normalize_note_tags,
)
from agent_host.tools.registry import (
    NoteToolContext,
    TEACHER_DEFAULT_NOTE_TAGS,
    TEACHER_DEFAULT_NOTE_TYPE,
    register_note_handler,
)

async def handle(ctx: NoteToolContext, arguments: dict[str, Any]) -> dict[str, object]:
    """Execute the take_note tool."""
    raw_note_content = arguments.get("content", "")
    note_content = str(raw_note_content) if isinstance(raw_note_content, str) else ""

    raw_note_title = arguments.get("title", "")
    note_title = str(raw_note_title).strip() if isinstance(raw_note_title, str) else ""

    raw_note_type = arguments.get("note_type", "")
    note_type = str(raw_note_type).strip().lower() if isinstance(raw_note_type, str) else ""

    raw_note_tags = arguments.get("tags", [])

    # ExecutionMode is a str enum — direct string comparison works.
    if ctx.execution_mode == "teacher":
        note_content = _build_teacher_note_body(
            prompt=ctx.resolved_user_prompt,
            response_text=note_content,
        )
        note_type = note_type or TEACHER_DEFAULT_NOTE_TYPE
        note_tags = _normalize_note_tags(
            raw_note_tags,
            extra_tags=TEACHER_DEFAULT_NOTE_TAGS,
        )
        note_title = ""
    else:
        note_tags = _normalize_note_tags(raw_note_tags)

    if note_type:
        note_content = f"<!-- note-type:{note_type} -->\n{note_content}"
    if note_tags:
        note_content = f"<!-- tags:{','.join(note_tags)} -->\n{note_content}"
    if note_title:
        note_content = f"**{note_title}**\n{note_content}"

    created = await ctx.run_blocking(
        label="notes.create",
        timeout_seconds=ctx.db_timeout_seconds,
        func=ctx.memory_manager.create_note,
        args=(ctx.session_id,),
        kwargs={"content": note_content, "source": "agent"},
        request_id=ctx.request_id,
        method=ctx.method,
    )
    return {
        "ok": True,
        "output": (
            f"Note saved (id={created['note_id'][:8]}). "
            "It is now visible in the user's notes panel."
        ),
    }


register_note_handler("take_note", handle)
