"""Port interface for async tool plugins.

Async tools (manage_notes, generate_image, read_screen) require
request-scoped context (session IDs, closures, IPC bridges) that
cannot be injected at construction time.  They receive a context
object per invocation alongside the arguments.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable

from agent_host.contracts.types.result import Result


@runtime_checkable
class AsyncNoteToolPlugin(Protocol):
    """Async tool plugin that operates on notes/images."""

    @property
    def name(self) -> str:
        """Unique identifier for the tool."""
        ...

    @property
    def description(self) -> str:
        """Human-readable description."""
        ...

    async def execute(
        self, arguments: Mapping[str, Any], *, ctx: Any
    ) -> Result:
        """Execute the tool with arguments and request-scoped context.

        ``ctx`` is a ``NoteToolContext`` or ``ImageToolContext``.
        """
        ...

    def health_check(self) -> Result:
        """Verify the tool is operational."""
        ...


@runtime_checkable
class AsyncScreenToolPlugin(Protocol):
    """Async tool plugin for screen capture."""

    @property
    def name(self) -> str:
        """Unique identifier for the tool."""
        ...

    @property
    def description(self) -> str:
        """Human-readable description."""
        ...

    async def execute(
        self, arguments: Mapping[str, Any], *, ctx: Any
    ) -> tuple[Result, bytes | None]:
        """Execute screen capture.

        Returns ``(Result, image_bytes)`` where image_bytes may be None.
        ``ctx`` is a ``ScreenToolContext``.
        """
        ...

    def health_check(self) -> Result:
        """Verify the tool is operational."""
        ...
