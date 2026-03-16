"""In-memory plan storage with TTL expiration.

Satisfies the ``PlanStore`` protocol from ``agent_host.contracts.ports``.
Provides shared state for the planner, plan_ops, and apply_ops plugins
that need to read/write plans concurrently.
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class InMemoryPlanStore:
    """In-memory plan storage with TTL-based expiration.

    This replaces the ``ToolExecutor._plans`` dict and related
    ``_prune_expired_plans()``, ``_MAX_PLANS``, ``_PLAN_TTL_SECONDS``
    attributes.  Injected into planner-related plugins via constructor.

    Example::

        store = InMemoryPlanStore(max_plans=50, ttl_seconds=600.0)
        store.store_plan("plan-123", {"ops": [...], "created_at": time.time()})
        plan = store.get_plan("plan-123")
    """

    def __init__(
        self,
        *,
        max_plans: int = 50,
        ttl_seconds: float = 600.0,
    ) -> None:
        self._plans: dict[str, dict[str, Any]] = {}
        self._max_plans = max_plans
        self._ttl_seconds = ttl_seconds

    def get_plan(self, plan_id: str) -> dict[str, Any] | None:
        """Retrieve a plan by ID, or None if not found / expired."""
        plan = self._plans.get(plan_id)
        if plan is None:
            return None
        # Check expiry inline.
        age = time.time() - plan.get("created_at", 0)
        if age > self._ttl_seconds:
            del self._plans[plan_id]
            return None
        return plan

    def store_plan(self, plan_id: str, plan: dict[str, Any]) -> None:
        """Store or update a plan.

        If the store is at capacity, expired plans are pruned first.
        If still at capacity after pruning, the oldest plan is evicted.
        """
        if len(self._plans) >= self._max_plans and plan_id not in self._plans:
            self.prune_expired()
            # If still at capacity, evict the oldest.
            if len(self._plans) >= self._max_plans:
                oldest_id = min(
                    self._plans,
                    key=lambda pid: self._plans[pid].get("created_at", 0),
                )
                del self._plans[oldest_id]
                logger.info("Evicted oldest plan %s to make room", oldest_id)

        self._plans[plan_id] = plan

    def delete_plan(self, plan_id: str) -> bool:
        """Delete a plan. Returns True if it existed."""
        return self._plans.pop(plan_id, None) is not None

    def prune_expired(self) -> int:
        """Remove plans older than TTL. Returns count of removed plans."""
        now = time.time()
        expired = [
            pid
            for pid, plan in self._plans.items()
            if (now - plan.get("created_at", 0)) > self._ttl_seconds
        ]
        for pid in expired:
            del self._plans[pid]
        if expired:
            logger.info("Pruned %d expired plans", len(expired))
        return len(expired)

    def list_plans(self) -> list[str]:
        """List all active (non-expired) plan IDs."""
        self.prune_expired()
        return list(self._plans.keys())

    @property
    def plan_count(self) -> int:
        """Number of active plans (before pruning)."""
        return len(self._plans)
