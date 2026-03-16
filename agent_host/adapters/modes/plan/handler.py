"""Plan execution mode -- constructor-injected, no set_context().

Satisfies the ``ModeHandler`` protocol via structural typing.
No inheritance from ``BaseModeHandler`` required.
"""

from __future__ import annotations

import logging
from typing import Any

from agent_host.adapters.modes.plan.prompts import get_plan_mode_header

logger = logging.getLogger(__name__)


class PlanModeHandler:
    """Handler for Plan Mode.

    Controls tool access and preloads planning headers and restrictions.
    All context is injected through the constructor -- there is no
    ``set_context()`` method.
    """

    def __init__(
        self,
        *,
        is_followup: bool = False,
        requires_unified_planning: bool = False,
        discovery_budget: int = 20,
        allowed_tools: set[str] | None = None,
    ) -> None:
        self._is_followup = is_followup
        self._requires_unified_planning = requires_unified_planning
        self._discovery_budget = discovery_budget
        self._allowed_tools: set[str] = allowed_tools or set()

    @property
    def name(self) -> str:
        return "plan"

    def get_system_prompt_addition(self) -> str:
        return get_plan_mode_header(
            is_followup=self._is_followup,
            requires_unified_planning=self._requires_unified_planning,
            discovery_budget=self._discovery_budget,
        )

    def filter_active_tools(
        self, available_tools: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Filters out non-discovery or non-planning tools based on allowed list."""
        if not self._allowed_tools:
            return available_tools
        return [
            tool
            for tool in available_tools
            if isinstance(tool, dict) and tool.get("name") in self._allowed_tools
        ]

    def get_timeout_multiplier(self) -> float:
        return 1.0

    async def pre_generation_hook(self, **kwargs: Any) -> bool | None:
        return False

    async def post_generation_hook(
        self, response_text: str, **kwargs: Any
    ) -> None:
        pass

    def should_show_tool_call_card(self) -> bool:
        return False

    def get_chain_status_message(self, chain_depth: int) -> str | None:
        if chain_depth == 1:
            return "Analyzing your request..."
        elif chain_depth == 2:
            return "Evaluating initial findings..."
        return "Refining plan with new data..."

    def get_pre_generation_status_message(self) -> str | None:
        return "Loading session context..."
