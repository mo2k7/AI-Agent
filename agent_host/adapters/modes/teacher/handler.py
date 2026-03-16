"""Teacher execution mode -- constructor-injected, no set_context().

Satisfies the ``ModeHandler`` protocol via structural typing.
No inheritance from ``BaseModeHandler`` required.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, Awaitable

from agent_host.adapters.modes.teacher.config import (
    TEACHER_DEFAULT_NOTE_TAGS,
    TEACHER_DEFAULT_NOTE_TYPE,
    TEACHER_NOTE_COMPLETION_TOOLS,
)
from agent_host.adapters.modes.teacher.note_capture import build_teacher_note_body

logger = logging.getLogger(__name__)


def _safe_env_float(key: str, default: float) -> float:
    """Read a float from an env var, falling back to *default*."""
    try:
        val = os.environ.get(key)
        return float(val) if val is not None else default
    except ValueError:
        return default


class TeacherModeHandler:
    """Handler for Teacher Mode.

    Provides automated study note capture and extended deep think
    timeouts.  All context is injected through the constructor --
    there is no ``set_context()`` method.
    """

    def __init__(
        self,
        *,
        memory_manager: Any = None,
        send_status: Callable[..., Awaitable[None]] | None = None,
        session_id: str | None = None,
    ) -> None:
        self._memory_manager = memory_manager
        self._send_status = send_status
        self._session_id = session_id
        self._note_captured = False
        self._teacher_multiplier = _safe_env_float(
            "AI_AGENT_TEACHER_MODEL_TIMEOUT_MULTIPLIER", 1.5
        )

    @property
    def name(self) -> str:
        return "teacher"

    def get_system_prompt_addition(self) -> str:
        return (
            "## EXECUTION MODE\n\n"
            "Current mode: **TEACHER**.\n"
            "You are the user's tutor and autonomous study-note assistant.\n"
            "Teach clearly, then ensure the turn produces structured notes with key highlights.\n"
            "If you call note tools, prefer concise study formatting and include key takeaways.\n"
            "Do not skip note capture in this mode.\n"
        )

    def filter_active_tools(
        self, available_tools: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        return available_tools

    def get_timeout_multiplier(self) -> float:
        return max(1.0, float(self._teacher_multiplier))

    async def pre_generation_hook(self, **kwargs: Any) -> bool | None:
        return False

    async def post_generation_hook(
        self, response_text: str, **kwargs: Any
    ) -> None:
        """Ensures a note is captured at the end of the Teacher turn."""
        if self._note_captured or not response_text.strip():
            return

        if not self._memory_manager or not self._session_id or not self._send_status:
            logger.warning(
                "TeacherModeHandler missing context objects; cannot auto-capture note."
            )
            return

        try:
            logger.info("Executing automatic teacher note capture...")
            await self._send_status("Synthesizing study notes...")
            note_body = build_teacher_note_body(response_text)

            # Using basic tagged content format based on previous db conventions
            tagged_content = (
                f"<!-- note-type:{TEACHER_DEFAULT_NOTE_TYPE} -->\n{note_body}"
            )

            # create_note is synchronous -- do not await.
            created_note = self._memory_manager.create_note(
                session_id=self._session_id,
                content=tagged_content,
                extra_tags=TEACHER_DEFAULT_NOTE_TAGS,
            )

            if created_note:
                logger.info(
                    "Auto-captured teacher note: %s", created_note["note_id"]
                )
                await self._send_status(
                    f"Teacher note saved (id={created_note['note_id'][:8]})"
                )
            self._note_captured = True
        except Exception as exc:
            logger.error("Teacher note auto-capture failed: %s", exc)
            await self._send_status(f"Teacher mode note capture failed: {exc}")

    def record_tool_call(self, tool_name: str) -> None:
        """Called by the main loop when a tool is executed to track manual note entry."""
        if tool_name in TEACHER_NOTE_COMPLETION_TOOLS:
            self._note_captured = True

    def should_show_tool_call_card(self) -> bool:
        return True

    def get_chain_status_message(self, chain_depth: int) -> str | None:
        if chain_depth == 1:
            return "Understanding your question..."
        elif chain_depth == 2:
            return "Preparing explanation and key highlights..."
        return "Refining explanation and study notes..."

    def get_pre_generation_status_message(self) -> str | None:
        return "Loading study context..."
