"""Port interface for LLM providers.

Abstracts the concrete LLM client (currently GeminiClient) so the core
domain never depends on a specific API SDK.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    """Abstract interface for language model providers."""

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
        """Send a prompt with tool definitions and return the model response."""
        ...

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
        """Continue a multi-turn conversation with tool results."""
        ...

    def resolve_text_model(self, model_override: str | None = None) -> str:
        """Resolve the best available text model name."""
        ...

    def list_models(self, *, filter_action: str | None = None) -> list[dict[str, Any]]:
        """List available models, optionally filtered by action."""
        ...

    def resolve_image_model(self, *, quality_tier: str = "standard") -> str:
        """Resolve the best available image generation model."""
        ...

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
        """Generate images from a text prompt."""
        ...
