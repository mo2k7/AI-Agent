"""Handler for the ``reorder_notes`` tool."""

from __future__ import annotations

import logging
import time
from typing import Any

from agent_host.tools.registry import NoteToolContext, register_note_handler

logger = logging.getLogger(__name__)


async def handle(ctx: NoteToolContext, arguments: dict[str, Any]) -> dict[str, object]:
    """Execute the reorder_notes tool."""
    raw_ids = arguments.get("note_ids_in_order", []) or []

    # Pre-fetch notes once for batch resolution
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

    base_ts = time.time()
    reorder_ok = True
    for idx, rid in enumerate(resolved_ids):
        # First note gets newest timestamp, each subsequent one is 1s older
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
            logger.warning("reorder_notes: failed to touch %s", rid[:8])
            reorder_ok = False

    return {
        "ok": reorder_ok,
        "output": (
            f"Reordered {len(resolved_ids)} notes."
            if reorder_ok
            else "Some notes could not be reordered."
        ),
    }


register_note_handler("reorder_notes", handle)
