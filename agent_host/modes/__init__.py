import logging
from .base import BaseModeHandler
from .direct.handler import DirectModeHandler
from .plan.handler import PlanModeHandler
from .teacher.handler import TeacherModeHandler

logger = logging.getLogger(__name__)

def get_mode_handler(execution_mode: str) -> BaseModeHandler:
    """Returns the appropriate ModeHandler singleton for the given execution mode."""
    if execution_mode == "TEACHER":
        return TeacherModeHandler()
    elif execution_mode == "PLAN":
        return PlanModeHandler()
    else:
        return DirectModeHandler()
