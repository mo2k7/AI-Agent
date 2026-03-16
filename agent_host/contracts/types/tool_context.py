"""Request-scoped context types for async tool plugins.

These dataclasses carry per-request state (session IDs, closures,
timeouts) that async tool plugins need for execution.  They are
defined in the contracts layer because they are shared between the
orchestrator (which creates them) and the plugins (which consume them).

The ``Any`` typing for ``memory_manager`` and ``gemini_client`` avoids
coupling to concrete implementations — these are injected at runtime
by the composition root.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable


@dataclass
class NoteToolContext:
    """Request-scoped context for note/quiz tool plugins.

    Constructed per tool-call dispatch.  The callable fields are closures
    carrying event-loop and session-scoped state.
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
    specifics.
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
    send_capture_request: Callable[..., Awaitable[None]]
    client_capabilities: Callable[[str], set[str]]
    resolved_user_prompt: str
    read_screen_ocr_max_chars: int
    read_screen_ocr_max_lines: int
