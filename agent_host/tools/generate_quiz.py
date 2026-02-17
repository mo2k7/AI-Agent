"""Handler for the ``generate_quiz`` tool."""

from __future__ import annotations

from typing import Any

from agent_host.tools.registry import NoteToolContext, register_note_handler


async def handle(ctx: NoteToolContext, arguments: dict[str, Any]) -> dict[str, object]:
    """Execute the generate_quiz tool."""
    source_ids_raw = arguments.get("source_note_ids", []) or []
    quiz_type = arguments.get("quiz_type", "flashcards") or "flashcards"
    quiz_content = arguments.get("content", "") or ""
    num_q_raw = arguments.get("num_questions", 10)
    try:
        num_q = max(1, min(30, int(num_q_raw if num_q_raw is not None else 10)))
    except (TypeError, ValueError):
        num_q = 10
    difficulty = arguments.get("difficulty", "intermediate") or "intermediate"

    # Pre-fetch notes once for batch resolution
    notes_cache = await ctx.run_blocking(
        label="notes.list_for_quiz_resolve",
        timeout_seconds=ctx.db_timeout_seconds,
        func=ctx.memory_manager.list_notes,
        args=(ctx.session_id,),
        kwargs={"limit": 200},
        request_id=ctx.request_id,
        method=ctx.method,
    )

    # Resolve all source note IDs to verify they exist
    resolved_source_ids: list[str] = []
    missing_ids: list[str] = []
    for raw_sid in source_ids_raw:
        rid = await ctx.resolve_note_id(
            ctx.session_id,
            raw_sid,
            ctx.memory_manager,
            ctx.db_timeout_seconds,
            ctx.request_id,
            ctx.method,
            notes_cache=notes_cache,
        )
        if rid is None:
            missing_ids.append(raw_sid)
        else:
            resolved_source_ids.append(rid)

    if missing_ids:
        return {
            "ok": False,
            "output": f"Could not find notes matching: {', '.join(missing_ids)}.",
        }
    if not quiz_content.strip():
        return {
            "ok": False,
            "output": "Quiz content is empty.",
        }

    # Map quiz_type to note_type
    note_type = "flashcards" if quiz_type == "flashcards" else "study_guide"
    type_tag = f"<!-- note-type:{note_type} -->\n"
    title_line = (
        f"**{quiz_type.replace('_', ' ').title()} "
        f"— {difficulty.title()} ({num_q}Q)**\n"
    )
    full_content = type_tag + title_line + quiz_content

    created = await ctx.run_blocking(
        label="notes.create_quiz",
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
            f"Quiz created (id={created['note_id'][:8]}). "
            f"Type: {quiz_type}, {num_q} questions at {difficulty} level. "
            "It is now visible in the user's notes panel."
        ),
    }


register_note_handler("generate_quiz", handle)
