"""Port interfaces (abstract boundaries) for the Hexagonal Architecture.

Each port is a ``typing.Protocol`` that defines what the core domain needs
from the outside world.  Concrete adapters in ``agent_host.adapters``
implement these protocols.  The core never imports any adapter.
"""

from agent_host.contracts.ports.audit import AuditPort
from agent_host.contracts.ports.event_bus import EventBus
from agent_host.contracts.ports.ipc import IPCPort
from agent_host.contracts.ports.llm_provider import LLMProvider
from agent_host.contracts.ports.memory_store import MemoryPort
from agent_host.contracts.ports.mode_handler import ModeHandler
from agent_host.contracts.ports.nlp import NLPClassifierPort
from agent_host.contracts.ports.plan_store import PlanStore
from agent_host.contracts.ports.tool import ToolPlugin
from agent_host.contracts.ports.async_tool import AsyncNoteToolPlugin, AsyncScreenToolPlugin

__all__ = [
    "AsyncNoteToolPlugin",
    "AsyncScreenToolPlugin",
    "AuditPort",
    "EventBus",
    "IPCPort",
    "LLMProvider",
    "MemoryPort",
    "ModeHandler",
    "NLPClassifierPort",
    "PlanStore",
    "ToolPlugin",
]
