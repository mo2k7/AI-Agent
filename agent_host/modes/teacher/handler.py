import logging
from typing import Any, Dict, List, Optional
from ..base import BaseModeHandler
from .prompts import TEACHER_DEFAULT_NOTE_TYPE, TEACHER_DEFAULT_NOTE_TAGS, _build_teacher_note_body, TEACHER_NOTE_COMPLETION_TOOLS
import os

logger = logging.getLogger(__name__)

def _safe_env_float(key: str, default: float) -> float:
    try:
        val = os.environ.get(key)
        return float(val) if val is not None else default
    except ValueError:
        return default

class TeacherModeHandler(BaseModeHandler):
    """
    Handler for Teacher Mode.
    Provides automated study note capture and extended deep think timeouts.
    """
    
    def __init__(self):
        self._note_captured = False
        self._teacher_multiplier = _safe_env_float("AI_AGENT_TEACHER_MODEL_TIMEOUT_MULTIPLIER", 1.5)
        self._memory_manager = None
        self._send_status = None
        self._session_id = None
        
    def set_context(self, memory_manager, send_status, session_id):
        """Allows injecting request-specific objects into the handler."""
        self._memory_manager = memory_manager
        self._send_status = send_status
        self._session_id = session_id
        
    def get_system_prompt_addition(self) -> str:
        return (
            "## EXECUTION MODE\n\n"
            "Current mode: **TEACHER**.\n"
            "You are the user's tutor and autonomous study-note assistant.\n"
            "Teach clearly, then ensure the turn produces structured notes with key highlights.\n"
            "If you call note tools, prefer concise study formatting and include key takeaways.\n"
            "Do not skip note capture in this mode.\n"
        )
        
    def get_timeout_multiplier(self) -> float:
        return max(1.0, float(self._teacher_multiplier))
        
    def record_tool_call(self, tool_name: str):
        """Called by the main loop when a tool is executed to track manual note entry."""
        if tool_name in TEACHER_NOTE_COMPLETION_TOOLS:
            self._note_captured = True
            
    async def post_generation_hook(self, response_text: str, **kwargs) -> None:
        """
        Ensures a note is captured at the end of the Teacher turn.
        """
        if self._note_captured or not response_text.strip():
            return
            
        if not self._memory_manager or not self._session_id or not self._send_status:
            logger.warning("TeacherModeHandler missing context objects; cannot auto-capture note.")
            return

        try:
            logger.info("Executing automatic teacher note capture...")
            await self._send_status("Synthesizing study notes...", "thinking")
            note_body = _build_teacher_note_body(response_text)
            
            # Using basic tagged content format based on previous db conventions
            tagged_content = f"<!-- note-type:{TEACHER_DEFAULT_NOTE_TYPE} -->\n{note_body}"
            
            created_note = await self._memory_manager.create_note(
                session_id=self._session_id,
                content=tagged_content,
                extra_tags=TEACHER_DEFAULT_NOTE_TAGS,
            )
            
            if created_note:
                logger.info(f"Auto-captured teacher note: {created_note['note_id']}")
                await self._send_status(
                    f"Teacher note saved (id={created_note['note_id'][:8]}) ",
                    "complete",
                )
            self._note_captured = True
        except Exception as exc:
            logger.error(f"Teacher note auto-capture failed: {exc}")
            await self._send_status(f"Teacher mode requires note capture and failed: {exc}", "error")

    def get_chain_status_message(self, chain_depth: int) -> Optional[str]:
        if chain_depth == 1:
            return "Understanding your question..."
        elif chain_depth == 2:
            return "Preparing explanation and key highlights..."
        else:
            return "Refining explanation and study notes..."

    def get_pre_generation_status_message(self) -> Optional[str]:
        return "Loading study context..."
