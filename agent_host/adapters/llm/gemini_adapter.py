"""Adapter wrapping GeminiClient to satisfy the LLMProvider protocol.

Thin delegation layer — all calls forwarded to the underlying client.
Defensive error boundaries ensure that only domain exceptions (GeminiAPIError
and subclasses) pass through; everything else is wrapped in AdapterError.
"""

from __future__ import annotations

import logging
from typing import Any

from agent_host.contracts.types.errors import AdapterError
from agent_host.gemini_client import (
    GeminiAPIError,
    GeminiClientError,
    GeminiRateLimitError,
    GeminiServerError,
)

logger = logging.getLogger(__name__)

_PASSTHROUGH = (GeminiAPIError, GeminiRateLimitError, GeminiServerError, GeminiClientError)


class GeminiAdapter:
    """Wraps ``GeminiClient`` to satisfy ``LLMProvider`` protocol."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def send_prompt_with_tools(
        self,
        prompt: str,
        tools: list[dict[str, Any]],
        *,
        system_instruction: str = "",
        model: str | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
        thinking_config: dict[str, Any] | None = None,
    ) -> Any:
        try:
            return self._client.send_prompt_with_tools(
                prompt,
                tools,
                system_instruction=system_instruction,
                model=model,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
                thinking_config=thinking_config,
            )
        except _PASSTHROUGH:
            raise
        except Exception as exc:
            logger.error("GeminiAdapter.send_prompt_with_tools failed: %s", exc)
            raise AdapterError(
                f"gemini.send_prompt_with_tools failed: {exc}",
                source="gemini",
                cause=exc,
            ) from exc

    def send_continuation(
        self,
        contents: list[Any],
        tools: list[dict[str, Any]],
        *,
        system_instruction: str = "",
        model: str | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
        thinking_config: dict[str, Any] | None = None,
    ) -> Any:
        try:
            return self._client.send_continuation(
                contents,
                tools,
                system_instruction=system_instruction,
                model=model,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
                thinking_config=thinking_config,
            )
        except _PASSTHROUGH:
            raise
        except Exception as exc:
            logger.error("GeminiAdapter.send_continuation failed: %s", exc)
            raise AdapterError(
                f"gemini.send_continuation failed: {exc}",
                source="gemini",
                cause=exc,
            ) from exc

    def resolve_text_model(self, model_override: str | None = None) -> str:
        try:
            return self._client.resolve_text_model(model_override)
        except _PASSTHROUGH:
            raise
        except Exception as exc:
            logger.error("GeminiAdapter.resolve_text_model failed: %s", exc)
            raise AdapterError(
                f"gemini.resolve_text_model failed: {exc}",
                source="gemini",
                cause=exc,
            ) from exc

    def list_models(self, *, filter_action: str | None = None) -> list[dict[str, Any]]:
        try:
            return self._client.list_models(filter_action=filter_action)
        except _PASSTHROUGH:
            raise
        except Exception as exc:
            logger.error("GeminiAdapter.list_models failed: %s", exc)
            raise AdapterError(
                f"gemini.list_models failed: {exc}",
                source="gemini",
                cause=exc,
            ) from exc

    def resolve_image_model(self, *, quality_tier: str = "standard") -> str:
        try:
            return self._client.resolve_image_model(quality_tier=quality_tier)
        except _PASSTHROUGH:
            raise
        except Exception as exc:
            logger.error("GeminiAdapter.resolve_image_model failed: %s", exc)
            raise AdapterError(
                f"gemini.resolve_image_model failed: {exc}",
                source="gemini",
                cause=exc,
            ) from exc

    def generate_image(
        self,
        *,
        prompt: str,
        model: str | None = None,
        aspect_ratio: str | None = None,
        num_images: int = 1,
        person_generation: str | None = None,
        negative_prompt: str | None = None,
    ) -> list[dict[str, Any]]:
        try:
            return self._client.generate_image(
                prompt=prompt,
                model=model,
                aspect_ratio=aspect_ratio,
                num_images=num_images,
                person_generation=person_generation,
                negative_prompt=negative_prompt,
            )
        except _PASSTHROUGH:
            raise
        except Exception as exc:
            logger.error("GeminiAdapter.generate_image failed: %s", exc)
            raise AdapterError(
                f"gemini.generate_image failed: {exc}",
                source="gemini",
                cause=exc,
            ) from exc

    # Expose underlying client attributes needed by callers.
    @property
    def model_name(self) -> str:
        return self._client.model_name

    @property
    def _client_inner(self) -> Any:
        """Access the underlying GeminiClient (for _supports_native_deep_think etc.)."""
        return self._client
