"""Handler for the unified ``manage_notes`` tool."""

from __future__ import annotations

import logging
import time
from typing import Any

from agent_host.adapters.tools._helpers import (
    _build_teacher_note_body,
    _normalize_note_tags,
)
from agent_host.tools.registry import (
    NoteToolContext,
    TEACHER_DEFAULT_NOTE_TAGS,
    TEACHER_DEFAULT_NOTE_TYPE,
    register_note_handler,
)

logger = logging.getLogger(__name__)


def _compose_tab_content(
    *,
    content: str,
    title: str,
    note_type: str,
    note_tags: list[str],
    include_metadata_comments: bool,
) -> str:
    result = content
    if include_metadata_comments and note_type:
        result = f"<!-- note-type:{note_type} -->\n{result}"
    if include_metadata_comments and note_tags:
        result = f"<!-- tags:{','.join(note_tags)} -->\n{result}"
    if title:
        result = f"## {title}\n{result}"
    return result.strip()


def _append_markdown(existing: str, addition: str) -> str:
    existing_trimmed = existing.strip()
    addition_trimmed = addition.strip()
    if not existing_trimmed:
        return addition_trimmed
    if not addition_trimmed:
        return existing_trimmed
    return f"{existing_trimmed}\n\n---\n\n{addition_trimmed}"


async def handle(ctx: NoteToolContext, arguments: dict[str, Any]) -> dict[str, object]:
    """Execute the unified manage_notes tool."""
    action = str(arguments.get("action", "")).strip().lower()

    if action == "create":
        return await _handle_create(ctx, arguments)
    elif action == "update":
        return await _handle_update(ctx, arguments)
    elif action == "delete":
        return await _handle_delete(ctx, arguments)
    elif action == "reorder":
        return await _handle_reorder(ctx, arguments)
    else:
        return {"ok": False, "output": f"Unknown action: '{action}'"}


async def _handle_create(ctx: NoteToolContext, arguments: dict[str, Any]) -> dict[str, object]:
    raw_note_content = arguments.get("content", "")
    note_content = str(raw_note_content) if raw_note_content is not None else ""

    raw_note_title = arguments.get("title", "")
    note_title = str(raw_note_title).strip() if isinstance(raw_note_title, str) else ""

    raw_note_type = arguments.get("note_type", "")
    note_type = str(raw_note_type).strip().lower() if isinstance(raw_note_type, str) else ""

    raw_note_tags = arguments.get("tags", [])
    raw_target = arguments.get("target", "session_pad")
    target = str(raw_target).strip() if isinstance(raw_target, str) else "session_pad"

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

    if target.lower() == "new_tab":
        final_title = note_title or "New Tab"
        tab_content = _compose_tab_content(
            content=note_content,
            title="",
            note_type=note_type,
            note_tags=note_tags,
            include_metadata_comments=True,
        )
        created = await ctx.run_blocking(
            label="notes.create_tab",
            timeout_seconds=ctx.db_timeout_seconds,
            func=ctx.memory_manager.create_note,
            args=(ctx.session_id,),
            kwargs={
                "content": tab_content,
                "source": "agent",
                "title": final_title,
                "workspace_kind": "tab",
            },
            request_id=ctx.request_id,
            method=ctx.method,
        )
        return {
            "ok": True,
            "output": f"Created a new notes tab '{created['title']}' (id={created['note_id'][:8]}).",
        }

    target_note_id = target if target else "session_pad"
    resolved_nid = await ctx.resolve_note_id(
        ctx.session_id, target_note_id, ctx.memory_manager, 
        ctx.db_timeout_seconds, ctx.request_id, ctx.method
    )
    if resolved_nid is None:
        return {"ok": False, "output": f"No note found matching target '{target_note_id}'."}

    existing = await ctx.run_blocking(
        label="notes.fetch_target",
        timeout_seconds=ctx.db_timeout_seconds,
        func=ctx.memory_manager.get_note,
        args=(ctx.session_id, resolved_nid),
        request_id=ctx.request_id,
        method=ctx.method,
    )
    if existing is None:
        return {"ok": False, "output": f"Note target '{target_note_id}' was not found."}

    appended_block = _compose_tab_content(
        content=note_content,
        title=note_title,
        note_type=note_type,
        note_tags=note_tags,
        include_metadata_comments=not bool(existing.get("is_default_tab")),
    )
    updated_content = _append_markdown(str(existing.get("content", "")), appended_block)
    updated = await ctx.run_blocking(
        label="notes.append",
        timeout_seconds=ctx.db_timeout_seconds,
        func=ctx.memory_manager.update_note,
        args=(ctx.session_id, resolved_nid),
        kwargs={"content": updated_content},
        request_id=ctx.request_id,
        method=ctx.method,
    )
    return {
        "ok": True,
        "output": f"Updated '{updated['title']}' (id={updated['note_id'][:8]}). The notes panel now reflects the latest session notes.",
    }


async def _handle_update(ctx: NoteToolContext, arguments: dict[str, Any]) -> dict[str, object]:
    raw_nid = arguments.get("note_id") or "session_pad"
    new_content = arguments.get("content")
    new_pinned = arguments.get("is_pinned")
    new_title = arguments.get("title")

    resolved_nid = await ctx.resolve_note_id(
        ctx.session_id, raw_nid, ctx.memory_manager, 
        ctx.db_timeout_seconds, ctx.request_id, ctx.method
    )
    if resolved_nid is None:
        return {"ok": False, "output": f"No note found matching id '{raw_nid}'."}

    updated = await ctx.run_blocking(
        label="notes.update",
        timeout_seconds=ctx.db_timeout_seconds,
        func=ctx.memory_manager.update_note,
        args=(ctx.session_id, resolved_nid),
        kwargs={"content": new_content, "is_pinned": new_pinned, "title": new_title},
        request_id=ctx.request_id,
        method=ctx.method,
    )
    if updated is None:
        return {"ok": False, "output": f"Note '{raw_nid}' not found or already deleted."}
    return {"ok": True, "output": f"Note updated (id={updated['note_id'][:8]})."}


async def _handle_delete(ctx: NoteToolContext, arguments: dict[str, Any]) -> dict[str, object]:
    raw_nid = arguments.get("note_id") or ""
    if not raw_nid:
        return {"ok": False, "output": "delete action requires a non-empty 'note_id'."}

    resolved_nid = await ctx.resolve_note_id(
        ctx.session_id, raw_nid, ctx.memory_manager, 
        ctx.db_timeout_seconds, ctx.request_id, ctx.method
    )
    if resolved_nid is None:
        return {"ok": False, "output": f"No note found matching id '{raw_nid}'."}

    deleted = await ctx.run_blocking(
        label="notes.delete",
        timeout_seconds=ctx.db_timeout_seconds,
        func=ctx.memory_manager.delete_note,
        args=(ctx.session_id, resolved_nid),
        request_id=ctx.request_id,
        method=ctx.method,
    )
    return {"ok": bool(deleted), "output": f"Note deleted (id={resolved_nid[:8]})." if deleted else "Could not delete note."}


async def _handle_reorder(ctx: NoteToolContext, arguments: dict[str, Any]) -> dict[str, object]:
    raw_ids = arguments.get("note_ids_in_order", []) or []
    if not raw_ids:
        return {"ok": False, "output": "reorder action requires a non-empty 'note_ids_in_order' array."}

    notes_cache = await ctx.run_blocking(
        label="notes.list_for_reorder_resolve",
        timeout_seconds=ctx.db_timeout_seconds,
        func=ctx.memory_manager.list_notes,
        args=(ctx.session_id,),
        kwargs={"limit": 200},
        request_id=ctx.request_id,
        method=ctx.method,
    )

    resolved_ids: list[str] = []
    unresolved: list[str] = []
    for raw_nid in raw_ids:
        rid = await ctx.resolve_note_id(
            ctx.session_id, raw_nid, ctx.memory_manager, 
            ctx.db_timeout_seconds, ctx.request_id, ctx.method, notes_cache=notes_cache
        )
        if rid is None:
            unresolved.append(raw_nid)
        else:
            resolved_ids.append(rid)

    if unresolved:
        return {"ok": False, "output": f"Could not resolve note IDs: {', '.join(unresolved)}."}

    base_ts = time.time()
    reorder_ok = True
    for idx, rid in enumerate(resolved_ids):
        fake_ts = base_ts - idx
        try:
            await ctx.run_blocking(
                label="notes.reorder_touch",
                timeout_seconds=ctx.db_timeout_seconds,
                func=ctx.memory_manager.update_note,
                args=(ctx.session_id, rid),
                kwargs={"touch_timestamp": fake_ts},
                request_id=ctx.request_id,
                method=ctx.method,
            )
        except Exception:
            logger.warning("manage_notes(reorder): failed to touch %s", rid[:8])
            reorder_ok = False

    return {"ok": reorder_ok, "output": f"Reordered {len(resolved_ids)} notes." if reorder_ok else "Some notes could not be reordered."}

register_note_handler("manage_notes", handle)
