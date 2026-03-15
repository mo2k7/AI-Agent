from typing import Any, Dict, List, Optional
from ..base import BaseModeHandler

class DirectModeHandler(BaseModeHandler):
    """
    Handler for Direct Mode.
    Provides standard execution with minimal interference.
    """
    
    def get_system_prompt_addition(self) -> str:
        return (
            "## EXECUTION MODE\n\n"
            "Current mode: **DIRECT**.\n"
            "Execute tools when needed to complete the request safely.\n"
            "Using `plan_ops` is optional in this mode.\n"
        )
