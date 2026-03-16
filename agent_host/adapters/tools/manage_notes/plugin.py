"""Async plugin adapter for the ``manage_notes`` tool.

Wraps the existing handler function from ``agent_host.tools.manage_notes``
behind the ``AsyncNoteToolPlugin`` protocol so it can be dispatched by
the hexagonal orchestrator without the module-level registry.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping

from agent_host.contracts.types.errors import AgentError, ErrorCode
from agent_host.contracts.types.result import Failure, Result, Success

logger = logging.getLogger(__name__)


class ManageNotesPlugin:
    """Wraps the existing ``manage_notes`` handler as an async plugin.

    The handler is imported lazily inside :meth:`execute` so that
    module-level registration side-effects (``register_note_handler``)
    only fire when the plugin is actually used, not at import time.
    """

    @property
    def name(self) -> str:
        return "manage_notes"

    @property
    def description(self) -> str:
        return "Create, update, delete, and reorder notes"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["create", "update", "delete", "reorder"]},
                "note_id": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["action"],
        }

    async def execute(
        self, arguments: Mapping[str, Any], *, ctx: Any
    ) -> Result:
        """Execute the manage_notes tool with request-scoped context.

        Parameters
        ----------
        arguments:
            Tool call arguments (action, content, note_id, etc.).
        ctx:
            A :class:`~agent_host.contracts.types.tool_context.NoteToolContext`
            carrying per-request state.

        Returns
        -------
        Result
            ``Success(dict)`` on success, ``Failure(AgentError)`` on error.
        """
        from agent_host.adapters.tools.manage_notes.handler import handle as _handle

        try:
            output = await _handle(ctx, dict(arguments))
            return Success(output)
        except Exception as exc:
            logger.error("manage_notes failed: %s", exc, exc_info=True)
            return Failure(
                AgentError(
                    code=ErrorCode.INTERNAL,
                    message=str(exc),
                    source="manage_notes",
                )
            )

    def health_check(self) -> Result:
        """Verify the plugin can import its handler module."""
        try:
            from agent_host.adapters.tools.manage_notes import handler as _mod  # noqa: F401

            return Success(True)
        except Exception as exc:
            return Failure(
                AgentError(
                    code=ErrorCode.DEPENDENCY,
                    message=f"manage_notes handler not importable: {exc}",
                    source="manage_notes",
                )
            )
