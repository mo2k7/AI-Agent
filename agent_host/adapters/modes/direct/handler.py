"""Direct execution mode -- standard execution with minimal interference.

Satisfies the ``ModeHandler`` protocol via structural typing.
No inheritance from ``BaseModeHandler`` required.
"""

from __future__ import annotations

from typing import Any


class DirectModeHandler:
    """Handler for Direct Mode.

    Provides standard execution with minimal interference.
    All protocol methods have sensible defaults.
    """

    @property
    def name(self) -> str:
        return "direct"

    def get_system_prompt_addition(self) -> str:
        return (
            "## EXECUTION MODE\n\n"
            "Current mode: **DIRECT**.\n"
            "Execute tools when needed to complete the request safely.\n"
            "Using `plan_ops` is optional in this mode.\n"
        )

    def filter_active_tools(
        self, available_tools: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        return available_tools

    def get_timeout_multiplier(self) -> float:
        return 1.0

    async def pre_generation_hook(self, **kwargs: Any) -> bool | None:
        return False

    async def post_generation_hook(
        self, response_text: str, **kwargs: Any
    ) -> None:
        pass

    def should_show_tool_call_card(self) -> bool:
        return True

    def get_chain_status_message(self, chain_depth: int) -> str | None:
        if chain_depth == 1:
            return "Analyzing your request..."
        elif chain_depth == 2:
            return "Evaluating initial findings..."
        return "Refining plan with new data..."

    def get_pre_generation_status_message(self) -> str | None:
        return "Loading context..."
