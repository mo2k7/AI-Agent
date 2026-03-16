"""Async plugin adapter for the ``generate_image`` tool.

Wraps the existing handler function from ``agent_host.tools.generate_image``
behind the ``AsyncNoteToolPlugin`` protocol so it can be dispatched by
the hexagonal orchestrator without the module-level registry.

.. note::

   Importing ``agent_host.tools.generate_image`` triggers a module-level
   ``register_note_handler("generate_image", handle)`` call.  This is
   harmless — the legacy registry still exists — but the plugin itself
   does **not** use the registry for dispatch.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping

from agent_host.contracts.types.errors import AgentError, ErrorCode
from agent_host.contracts.types.result import Failure, Result, Success

logger = logging.getLogger(__name__)


class GenerateImagePlugin:
    """Wraps the existing ``generate_image`` handler as an async plugin.

    The handler is imported lazily inside :meth:`execute` so that the
    module-level ``register_note_handler`` side-effect only fires on
    first use, not at adapter import time.
    """

    @property
    def name(self) -> str:
        return "generate_image"

    @property
    def description(self) -> str:
        return "Generate images via Gemini and optionally embed them in notes"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "num_images": {"type": "integer", "default": 1},
                "aspect_ratio": {"type": "string"},
            },
            "required": ["prompt"],
        }

    async def execute(
        self, arguments: Mapping[str, Any], *, ctx: Any
    ) -> Result:
        """Execute the generate_image tool with request-scoped context.

        Parameters
        ----------
        arguments:
            Tool call arguments (prompt, output_path, quality_tier, etc.).
        ctx:
            A :class:`~agent_host.contracts.types.tool_context.ImageToolContext`
            carrying per-request state (Gemini client, output root, etc.).

        Returns
        -------
        Result
            ``Success(dict)`` on success, ``Failure(AgentError)`` on error.
        """
        from agent_host.adapters.tools.generate_image.handler import handle as _handle

        try:
            output = await _handle(ctx, dict(arguments))
            return Success(output)
        except Exception as exc:
            logger.error("generate_image failed: %s", exc, exc_info=True)
            return Failure(
                AgentError(
                    code=ErrorCode.INTERNAL,
                    message=str(exc),
                    source="generate_image",
                )
            )

    def health_check(self) -> Result:
        """Verify the plugin can import its handler module."""
        try:
            from agent_host.adapters.tools.generate_image import handler as _mod  # noqa: F401

            return Success(True)
        except Exception as exc:
            return Failure(
                AgentError(
                    code=ErrorCode.DEPENDENCY,
                    message=f"generate_image handler not importable: {exc}",
                    source="generate_image",
                )
            )
