from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from google.genai import types

class BaseModeHandler(ABC):
    """
    Base interface for Execution Mode handlers.
    Provides hooks into the core `_process_prompt` request lifecycle.
    """
    
    @abstractmethod
    def get_system_prompt_addition(self) -> str:
        """Returns mode-specific instructions to prepend to the system prompt."""
        pass
        
    def filter_active_tools(self, available_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Optionally filter out tools that shouldn't be used in this mode."""
        return available_tools
        
    def get_timeout_multiplier(self) -> float:
        """Returns the timeout multiplier for generating model responses in this mode."""
        return 1.0
        
    async def pre_generation_hook(self, **kwargs) -> Optional[bool]:
        """
        Executed before sending the prompt to the model.
        Can be used to handle clarification routing, unified planning bounds, etc.
        Return `True` to short-circuit and stop the request.
        """
        return False
        
    async def post_generation_hook(self, response_text: str, **kwargs) -> None:
        """
        Executed after the model completes its final response.
        Can be used to capture notes autonomously, parse tools, etc.
        """
        pass

    def should_show_tool_call_card(self) -> bool:
        """Determines if tool call cards should be shown to the user in the UI."""
        return True

    def get_chain_status_message(self, chain_depth: int) -> Optional[str]:
        """Provides an optional custom status message for the UI based on chain depth."""
        if chain_depth == 1:
            return "Analyzing your request..."
        elif chain_depth == 2:
            return "Evaluating initial findings..."
        else:
            return "Refining plan with new data..."

    def get_pre_generation_status_message(self) -> Optional[str]:
        """Provides an optional custom status message before generation begins."""
        return "Loading context..."
