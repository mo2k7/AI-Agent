"""Port interface for plan storage.

Provides shared storage for plans that multiple tools need to access
(planner, plan_ops, apply_ops).
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class PlanStore(Protocol):
    """Abstract interface for plan storage and retrieval."""

    def get_plan(self, plan_id: str) -> dict[str, Any] | None:
        """Retrieve a plan by ID."""
        ...

    def store_plan(self, plan_id: str, plan: dict[str, Any]) -> None:
        """Store or update a plan."""
        ...

    def delete_plan(self, plan_id: str) -> bool:
        """Delete a plan. Returns True if it existed."""
        ...

    def prune_expired(self) -> int:
        """Remove expired plans. Returns count of removed plans."""
        ...

    def list_plans(self) -> list[str]:
        """List all active plan IDs."""
        ...
