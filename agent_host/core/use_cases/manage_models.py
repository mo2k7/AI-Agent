"""Use case module for model listing and discovery.

Handles IPC requests related to Gemini model catalog.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from agent_host.contracts.types.ipc_messages import ErrorMessage, IncomingRequest, ResultMessage

logger = logging.getLogger(__name__)


class ModelsUseCases:
    """Handles model-related IPC requests."""

    def __init__(
        self,
        *,
        gemini_client: Any,
        format_exception_message: Any,
    ) -> None:
        self._gemini_client = gemini_client
        self._format_exception_message = format_exception_message

    async def handle_list(self, request: IncomingRequest, client: Any) -> None:
        """Return the live Gemini text-model catalog for the frontend."""
        from agent_host.contracts.types.errors import GeminiClientError

        force_refresh = bool(request.params.get("force_refresh"))
        try:
            models = await asyncio.to_thread(
                self._gemini_client.list_text_models,
                force_refresh=force_refresh,
            )
            default_model = await asyncio.to_thread(
                self._gemini_client.resolve_text_model,
            )
        except GeminiClientError as exc:
            await client.send(
                ErrorMessage.internal_error(
                    request.id,
                    self._format_exception_message(
                        exc, fallback="Failed to load Gemini model catalog"
                    ),
                ).to_bytes()
            )
            return

        payload = {
            "default_model": default_model,
            "models": models,
        }
        await client.send(
            ResultMessage.create(request.id, json.dumps(payload)).to_bytes()
        )
