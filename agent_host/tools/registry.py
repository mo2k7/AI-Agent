"""Constants and context re-exports for async tool handlers.

Canonical context dataclasses now live in
``agent_host.contracts.types.tool_context``.  This module re-exports
them for backward compatibility with existing tool handler modules.

The module-level handler registry (``_NOTE_HANDLERS``, ``_SCREEN_HANDLER``)
and dispatch functions (``dispatch_note_tool``, ``dispatch_screen_tool``)
have been removed — async tools are now dispatched via plugin classes
in ``agent_host.adapters.tools``.

Registration functions are kept as no-ops so that existing tool modules
that call ``register_note_handler`` / ``register_screen_handler`` at
import time do not break.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Teacher constants: canonical source is adapters.modes.teacher.config
from agent_host.adapters.modes.teacher.config import (  # noqa: E402
    TEACHER_DEFAULT_NOTE_TAGS,
    TEACHER_DEFAULT_NOTE_TYPE,
    TEACHER_NOTE_COMPLETION_TOOLS,
)

NOTE_TOOL_NAMES: frozenset[str] = frozenset(
    {"manage_notes", "generate_image"}
)


# ---------------------------------------------------------------------------
# Context re-exports (canonical definitions in contracts.types.tool_context)
# ---------------------------------------------------------------------------

from agent_host.contracts.types.tool_context import (  # noqa: E402,F401
    NoteToolContext,
    ImageToolContext,
    ScreenToolContext,
)


# ---------------------------------------------------------------------------
# Handler type aliases (kept for backward compat with tool module signatures)
# ---------------------------------------------------------------------------

NoteToolHandler = Callable[
    ["NoteToolContext", dict[str, Any]], Awaitable[dict[str, object]]
]

ScreenToolHandler = Callable[
    ["ScreenToolContext", dict[str, Any]],
    Awaitable[tuple[dict[str, object], bytes | None]],
]


# ---------------------------------------------------------------------------
# No-op registration (tool modules call these at import time)
# ---------------------------------------------------------------------------

def register_note_handler(
    tool_name: str,
    handler: NoteToolHandler,
) -> None:
    """No-op — kept for backward compat with tool module imports."""
    pass


def register_screen_handler(handler: ScreenToolHandler) -> None:
    """No-op — kept for backward compat with tool module imports."""
    pass
