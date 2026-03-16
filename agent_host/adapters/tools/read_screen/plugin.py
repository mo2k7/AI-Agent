"""Async plugin adapter for the ``read_screen`` tool.

Wraps the existing handler function from ``agent_host.tools.read_screen``
behind the ``AsyncScreenToolPlugin`` protocol so it can be dispatched by
the hexagonal orchestrator without the module-level registry.

The ``read_screen`` handler returns ``(dict, bytes | None)`` — a result
dict plus optional screenshot image bytes.  The plugin preserves this
contract: :meth:`execute` returns ``(Result, bytes | None)``.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping

from agent_host.contracts.types.errors import AgentError, ErrorCode
from agent_host.contracts.types.result import Failure, Result, Success

logger = logging.getLogger(__name__)


class ReadScreenPlugin:
    """Wraps the existing ``read_screen`` handler as an async plugin.

    The handler is imported lazily inside :meth:`execute` so that the
    module-level ``register_screen_handler`` side-effect only fires on
    first use, not at adapter import time.
    """

    @property
    def name(self) -> str:
        return "read_screen"

    @property
    def description(self) -> str:
        return "Capture the user's screen and extract OCR text"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "purpose": {"type": "string"},
            },
        }

    async def execute(
        self, arguments: Mapping[str, Any], *, ctx: Any
    ) -> tuple[Result, bytes | None]:
        """Execute the read_screen tool with request-scoped context.

        Parameters
        ----------
        arguments:
            Tool call arguments (purpose, etc.).
        ctx:
            A :class:`~agent_host.contracts.types.tool_context.ScreenToolContext`
            carrying per-request state (IPC bridges, OCR config, etc.).

        Returns
        -------
        tuple[Result, bytes | None]
            ``(Success(dict), image_bytes)`` on success, or
            ``(Failure(AgentError), None)`` on error.
        """
        from agent_host.adapters.tools.read_screen.handler import handle as _handle

        try:
            execution_dict, image_bytes = await _handle(ctx, dict(arguments))
            return Success(execution_dict), image_bytes
        except Exception as exc:
            logger.error("read_screen failed: %s", exc, exc_info=True)
            return (
                Failure(
                    AgentError(
                        code=ErrorCode.INTERNAL,
                        message=str(exc),
                        source="read_screen",
                    )
                ),
                None,
            )

    def health_check(self) -> Result:
        """Verify the plugin can import its handler module."""
        try:
            from agent_host.adapters.tools.read_screen import handler as _mod  # noqa: F401

            return Success(True)
        except Exception as exc:
            return Failure(
                AgentError(
                    code=ErrorCode.DEPENDENCY,
                    message=f"read_screen handler not importable: {exc}",
                    source="read_screen",
                )
            )
