"""Central registry and dispatcher for async tool handlers.

Provides context dataclasses and a dispatch mechanism for the async tools
that currently live inline in main.py's prompt handler.  Each per-tool
module (e.g. ``take_note.py``) registers itself here via
:func:`register_note_handler`.  ``main.py`` then calls
:func:`dispatch_note_tool` to execute them.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants (moved from main.py)
# ---------------------------------------------------------------------------

TEACHER_DEFAULT_NOTE_TYPE: str = "study_guide"
TEACHER_DEFAULT_NOTE_TAGS: tuple[str, ...] = (
    "teacher-mode",
    "autonomous",
    "key-highlights",
)
TEACHER_NOTE_COMPLETION_TOOLS: frozenset[str] = frozenset(
    {
        "take_note",
        "update_note",
        "format_note",
        "merge_notes",
        "generate_quiz",
        "summarize_note",
    }
)

NOTE_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "take_note",
        "update_note",
        "delete_note",
        "format_note",
        "merge_notes",
        "reorder_notes",
        "generate_image",
        "generate_quiz",
        "summarize_note",
    }
)


# ---------------------------------------------------------------------------
# Context dataclasses
# ---------------------------------------------------------------------------


@dataclass
class NoteToolContext:
    """Shared async context passed to every note/quiz/image tool handler.

    Constructed by ``main.py`` once per tool-call dispatch. The two callable
    fields (``run_blocking`` and ``resolve_note_id``) are closures defined in
    ``main.py`` that carry the event-loop and session-scoped state.
    """

    session_id: str
    memory_manager: Any  # MemoryManager — avoids circular import
    db_timeout_seconds: float
    request_id: str
    method: str  # IPC request method (e.g. "prompt.send")
    execution_mode: Any  # ExecutionMode enum value
    resolved_user_prompt: str
    run_blocking: Callable[..., Awaitable[Any]]
    resolve_note_id: Callable[..., Awaitable[str | None]]


@dataclass
class ImageToolContext(NoteToolContext):
    """Extended context for the ``generate_image`` tool.

    Inherits all :class:`NoteToolContext` fields and adds image-generation
    specifics.  ``main.py`` constructs this instead of ``NoteToolContext``
    when dispatching ``generate_image``.
    """

    gemini_client: Any = None  # GeminiClient instance
    image_output_root: Path = field(default_factory=lambda: Path("."))
    image_timeout_seconds: float = 60.0
    image_model_override: str | None = None
    config_allowed_roots: list[Path] = field(default_factory=list)


@dataclass
class ScreenToolContext:
    """Context for the ``read_screen`` tool.

    Separate from :class:`NoteToolContext` because ``read_screen`` has a
    fundamentally different dispatch pattern (IPC delegation + binary image
    return) and does not share the note-tool wiring.
    """

    request_id: str
    client_address: str
    pending_screen_captures: dict[str, tuple[str, asyncio.Future[dict | None]]]
    send_status: Callable[..., Awaitable[None]]
    resolved_user_prompt: str
    read_screen_ocr_max_chars: int
    read_screen_ocr_max_lines: int


# ---------------------------------------------------------------------------
# Handler type aliases
# ---------------------------------------------------------------------------

# async def handle(ctx: NoteToolContext, arguments: dict) -> dict[str, object]
NoteToolHandler = Callable[
    [NoteToolContext, dict[str, Any]], Awaitable[dict[str, object]]
]

# async def handle(ctx: ScreenToolContext, arguments: dict)
#     -> tuple[dict[str, object], bytes | None]
ScreenToolHandler = Callable[
    [ScreenToolContext, dict[str, Any]],
    Awaitable[tuple[dict[str, object], bytes | None]],
]


# ---------------------------------------------------------------------------
# Handler registry
# ---------------------------------------------------------------------------

_NOTE_HANDLERS: dict[str, NoteToolHandler] = {}
_SCREEN_HANDLER: ScreenToolHandler | None = None


def register_note_handler(
    tool_name: str,
    handler: NoteToolHandler,
) -> None:
    """Register an async handler for a note/quiz/image tool."""
    if tool_name in _NOTE_HANDLERS:
        logger.warning("Overwriting note handler for '%s'", tool_name)
    _NOTE_HANDLERS[tool_name] = handler


def register_screen_handler(handler: ScreenToolHandler) -> None:
    """Register the async handler for read_screen."""
    global _SCREEN_HANDLER
    _SCREEN_HANDLER = handler


# ---------------------------------------------------------------------------
# Dispatchers
# ---------------------------------------------------------------------------


async def dispatch_note_tool(
    tool_name: str,
    ctx: NoteToolContext,
    arguments: dict[str, Any],
) -> dict[str, object]:
    """Dispatch a note/quiz/image tool call to the registered handler.

    Returns ``{"ok": bool, "output": ...}``  — the same shape that
    ``main.py`` currently produces inline for each note tool.
    """
    handler = _NOTE_HANDLERS.get(tool_name)
    if handler is None:
        logger.error("No handler registered for note tool '%s'", tool_name)
        return {"ok": False, "output": f"Unknown note tool: {tool_name}"}
    return await handler(ctx, arguments)


async def dispatch_screen_tool(
    ctx: ScreenToolContext,
    arguments: dict[str, Any],
) -> tuple[dict[str, object], bytes | None]:
    """Dispatch a read_screen call to the registered handler.

    Returns ``(execution_dict, screen_image_bytes)`` where the image bytes
    may be ``None`` if the capture failed or was not returned.
    """
    if _SCREEN_HANDLER is None:
        logger.error("No handler registered for read_screen")
        return {"ok": False, "output": "read_screen handler not registered"}, None
    return await _SCREEN_HANDLER(ctx, arguments)
