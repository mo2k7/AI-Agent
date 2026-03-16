"""Port interface for execution mode handlers.

Abstracts the mode handler (Direct, Plan, Teacher) so modes can be
added, removed, or modified independently.  This protocol replaces
the ``BaseModeHandler(ABC)`` in ``modes/base.py`` and removes the
``google.genai`` dependency from the contracts layer.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ModeHandler(Protocol):
    """Abstract interface for an execution mode handler.

    Each mode (Direct, Plan, Teacher) implements this protocol.
    Modes are registered in the Composition Root and resolved by name.
    """

    @property
    def name(self) -> str:
        """Unique mode identifier (e.g., 'direct', 'plan', 'teacher')."""
        ...

    def get_system_prompt_addition(self) -> str:
        """Returns mode-specific instructions to prepend to the system prompt."""
        ...

    def filter_active_tools(
        self, available_tools: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Optionally filter tools that shouldn't be used in this mode."""
        ...

    def get_timeout_multiplier(self) -> float:
        """Returns timeout multiplier for model response generation."""
        ...

    async def pre_generation_hook(self, **kwargs: Any) -> bool | None:
        """Hook executed before sending prompt to model.

        Return True to short-circuit the request.
        """
        ...

    async def post_generation_hook(self, response_text: str, **kwargs: Any) -> None:
        """Hook executed after model completes its final response."""
        ...

    def should_show_tool_call_card(self) -> bool:
        """Whether tool call cards should be shown in the UI."""
        ...

    def get_chain_status_message(self, chain_depth: int) -> str | None:
        """Optional status message for the UI based on chain depth."""
        ...

    def get_pre_generation_status_message(self) -> str | None:
        """Optional status message before generation begins."""
        ...
