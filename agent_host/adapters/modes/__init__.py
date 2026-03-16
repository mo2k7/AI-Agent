"""Execution mode adapters with mode registry.

Each mode handler satisfies the ``ModeHandler`` protocol defined in
``agent_host.contracts.ports.mode_handler`` via structural typing --
no inheritance required.
"""

from __future__ import annotations

from typing import Any


class ModeRegistry:
    """Manages execution mode handler instances by name.

    Handlers are registered under their canonical lowercase name
    (``"direct"``, ``"plan"``, ``"teacher"``).  Lookup accepts both
    plain strings and ``Enum`` instances whose ``.value`` attribute
    contains the string key.
    """

    def __init__(self) -> None:
        self._modes: dict[str, Any] = {}  # name -> ModeHandler

    def register(self, mode_name: str, handler: Any) -> None:
        """Register *handler* under the given *mode_name*."""
        self._modes[mode_name.strip().lower()] = handler

    def get(self, mode_name: str | Any) -> Any | None:
        """Look up a handler by name (supports Enum values)."""
        raw = getattr(mode_name, "value", mode_name)
        normalized = str(raw).strip().lower()
        return self._modes.get(normalized)

    def list(self) -> list[str]:
        """Return the sorted list of registered mode names."""
        return sorted(self._modes.keys())
