"""Port interface for tool plugins.

Every tool in the system implements this protocol.  The plugin registry
and tool executor depend only on this interface, never on concrete
tool implementations.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable

from agent_host.contracts.types.result import Result


@runtime_checkable
class ToolPlugin(Protocol):
    """Abstract interface for a tool plugin."""

    @property
    def name(self) -> str:
        """Unique identifier for the tool."""
        ...

    @property
    def description(self) -> str:
        """Human-readable description of the tool."""
        ...

    @property
    def input_schema(self) -> dict[str, Any]:
        """JSON Schema defining expected input format."""
        ...

    def execute(self, arguments: Mapping[str, Any]) -> Result:
        """Execute the tool with validated arguments."""
        ...

    def health_check(self) -> Result:
        """Verify the tool and its dependencies are operational."""
        ...
