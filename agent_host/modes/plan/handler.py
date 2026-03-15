import logging
from typing import Any, Dict, List, Optional
from ..base import BaseModeHandler
from .prompts import get_plan_mode_header, normalize_plan_mode_banner

logger = logging.getLogger(__name__)

class PlanModeHandler(BaseModeHandler):
    """
    Handler for Plan Mode.
    Controls tool access and preloads planning headers and restrictions.
    """
    
    def __init__(self):
        self._is_followup = False
        self._requires_unified_planning = False
        self._discovery_budget = 20
        self._allowed_tools: set[str] = set()

    def set_context(self, is_followup: bool, requires_unified_planning: bool, discovery_budget: int, allowed_tools: set[str]):
        """Inject context needed to format the Plan Mode prompt and restrict tools."""
        self._is_followup = is_followup
        self._requires_unified_planning = requires_unified_planning
        self._discovery_budget = discovery_budget
        self._allowed_tools = allowed_tools

    def get_system_prompt_addition(self) -> str:
        return get_plan_mode_header(
            is_followup=self._is_followup,
            requires_unified_planning=self._requires_unified_planning,
            discovery_budget=self._discovery_budget,
        )
        
    def filter_active_tools(self, available_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filters out non-discovery or non-planning tools based on allowed list."""
        if not self._allowed_tools:
            return available_tools
            
        return [
            tool for tool in available_tools
            if isinstance(tool, dict) and tool.get("name") in self._allowed_tools
        ]
        
    async def post_generation_hook(self, response_text: str, **kwargs) -> None:
        pass

    def should_show_tool_call_card(self) -> bool:
        return False

    def get_pre_generation_status_message(self) -> Optional[str]:
        return "Loading session context..."
