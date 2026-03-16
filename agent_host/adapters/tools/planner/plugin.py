"""Tool plugin: planner.

Analyzes, creates, or replans file operation plans using the unified
planning engine.  Shares plan state via an ``InMemoryPlanStore``
injected through the constructor.

When ``mode`` is ``create`` or ``replan`` **and** ``ops`` are provided,
this plugin delegates to ``PlanOpsPlugin`` internally (via a local
import to avoid circular dependency) to produce a full plan.
When no ``ops`` are supplied, advisory-only output is returned.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping, Sequence

from pathlib import Path

from agent_host.adapters.tools._path_security import normalize_user_path
from agent_host.contracts.types.errors import AgentError, ErrorCode
from agent_host.contracts.types.result import Failure, Result, Success

from agent_host.planning import (
    UnifiedPlanningEngine,
    UnifiedPlanningSecurityError,
    UnifiedPlanningUnavailableError,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants (mirrored from ToolExecutor)
# ---------------------------------------------------------------------------
_PLANNER_OP_CODES: dict[str, int] = {
    "move": 1,
    "rename": 2,
    "delete": 3,
    "copy": 4,
}

_PLANNER_PRIVACY_POLICY_VERSION = "v2-strict-no-text"


# ---------------------------------------------------------------------------
# Shared utility helpers
# ---------------------------------------------------------------------------

def _planner_op_code(op_kind: str) -> int:
    return int(_PLANNER_OP_CODES.get(str(op_kind).strip().lower(), 0))


def _abstract_steps_from_raw_ops(
    raw_ops: Sequence[Any],
) -> list[tuple[int, int, bool]]:
    """Convert raw op dicts to abstract (index, op_code, valid) tuples.

    No path strings leave this function -- only numeric/bool data.
    """
    steps: list[tuple[int, int, bool]] = []
    for index, raw in enumerate(raw_ops):
        if not isinstance(raw, Mapping):
            steps.append((index, 0, False))
            continue
        op_kind = str(raw.get("op", "")).strip().lower()
        op_code = _planner_op_code(op_kind)
        has_src = isinstance(raw.get("src"), str) and bool(str(raw.get("src")).strip())
        requires_dest = op_kind in {"move", "rename", "copy"}
        has_dest = isinstance(raw.get("dest"), str) and bool(str(raw.get("dest")).strip())
        is_valid = bool(op_code) and has_src and (not requires_dest or has_dest)
        steps.append((index, op_code, is_valid))
    return steps


def _abstract_steps_from_normalized_ops(
    ops: Sequence[Mapping[str, Any]],
) -> list[tuple[int, int, bool]]:
    """Convert normalized op dicts to abstract (index, op_code, valid) tuples."""
    steps: list[tuple[int, int, bool]] = []
    for index, op in enumerate(ops):
        op_kind = str(op.get("op", "")).strip().lower()
        op_code = _planner_op_code(op_kind)
        is_valid = bool(op.get("valid", False))
        steps.append((index, op_code, is_valid))
    return steps


def _assert_no_text_boundary_payload(payload: Any, *, context: str) -> None:
    """Ensure no string/binary values leak across the planner boundary."""
    if isinstance(payload, str):
        raise ValueError(f"{context} must not contain string values")
    if isinstance(payload, (bytes, bytearray, memoryview)):
        raise ValueError(f"{context} must not contain binary values")
    if payload is None:
        return
    if isinstance(payload, bool):
        return
    if isinstance(payload, int):
        return
    if isinstance(payload, (list, tuple, set, frozenset)):
        for value in payload:
            _assert_no_text_boundary_payload(value, context=context)
        return
    raise ValueError(
        f"{context} contains unsupported type for planner boundary: {type(payload).__name__}"
    )


# ---------------------------------------------------------------------------
# Plugin
# ---------------------------------------------------------------------------


class PlannerPlugin:
    """Self-contained plugin for the ``planner`` tool.

    Delegates to the unified planning engine for complexity analysis.
    Shares plan state with ``PlanOpsPlugin`` and ``ApplyOpsPlugin``
    through the injected ``plan_store``.
    """

    def __init__(
        self,
        *,
        planner_engine: Any,
        plan_store: Any,
        allowed_roots: Sequence[Path],
    ) -> None:
        self._planner = planner_engine
        self._plan_store = plan_store
        self._allowed_roots: list[Path] = [
            r.expanduser().resolve(strict=False) for r in allowed_roots
        ]
        self._planner_lock_reason: str = ""

    # ------------------------------------------------------------------
    # ToolPlugin protocol
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "planner"

    @property
    def description(self) -> str:
        return (
            "Analyze, create, or replan file operation plans using the "
            "unified planning engine"
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["analyze", "create", "replan"],
                    "description": (
                        "Planning mode. 'analyze' returns complexity analysis. "
                        "'create' produces a new executable plan. "
                        "'replan' revises an existing plan."
                    ),
                },
                "goal": {
                    "type": "string",
                    "description": "Human-readable goal for the plan",
                },
                "ops": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Array of file operation objects",
                },
                "prior_plan_id": {
                    "type": "string",
                    "description": "When replanning, the ID of the prior plan",
                },
                "constraints": {
                    "type": "object",
                    "description": "Optional constraints for planning",
                },
            },
            "required": ["goal"],
        }

    def execute(self, arguments: Mapping[str, Any]) -> Result[dict[str, Any]]:
        """Execute the planner tool, returning Success or Failure."""
        try:
            return self._execute_inner(arguments)
        except Exception as exc:
            return Failure(AgentError(
                code=ErrorCode.INTERNAL,
                message=f"Unexpected error in planner: {exc}",
                source="planner",
            ))

    def health_check(self) -> Result[bool]:
        return Success(True)

    # ------------------------------------------------------------------
    # Engine construction (patch target for tests)
    # ------------------------------------------------------------------

    @staticmethod
    def _build_default_engine() -> UnifiedPlanningEngine:
        """Build a default planner engine.

        Exists as a static method so tests can monkeypatch it.
        """
        try:
            return UnifiedPlanningEngine()
        except (UnifiedPlanningUnavailableError, UnifiedPlanningSecurityError) as exc:
            raise RuntimeError(
                "Secure unified-planning engine initialization failed. "
                "Install and configure 'unified-planning' (Apache-2.0) "
                f"before running the agent. Details: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _raise_if_locked(self) -> Result[None] | None:
        """Return ``Failure`` if the planner is security-locked."""
        if self._planner_lock_reason:
            return Failure(AgentError(
                code=ErrorCode.PERMISSION,
                message=(
                    "Planner is security-locked for this session due to a "
                    f"prior policy violation: {self._planner_lock_reason}"
                ),
                source="planner",
            ))
        return None

    def _privacy_payload(self) -> dict[str, Any]:
        """Build the privacy disclosure dict for planner responses."""
        policy_checksum = getattr(self._planner, "policy_checksum", "")
        package_hash = getattr(self._planner, "package_hash", "")
        return {
            "policy_version": _PLANNER_PRIVACY_POLICY_VERSION,
            "boundary_payload_mode": "numeric_boolean_only",
            "string_payload_blocked": True,
            "binary_payload_blocked": True,
            "path_data_sent_to_unified_planning": False,
            "network_disabled_during_planning": True,
            "planner_security_locked": bool(self._planner_lock_reason),
            "policy_checksum": str(policy_checksum),
            "policy_attestation_verified": bool(
                getattr(self._planner, "policy_attestation_verified", False)
            ),
            "package_hash": str(package_hash),
            "package_hash_verified": bool(
                getattr(self._planner, "package_hash_verified", False)
            ),
            "package_hash_pinned": bool(
                getattr(self._planner, "package_hash_pinned", False)
            ),
            "package_hash_auto_rotate_enabled": bool(
                getattr(self._planner, "package_hash_auto_rotate_enabled", False)
            ),
        }

    def _analyze_complexity(
        self,
        *,
        steps: list[tuple[int, int, bool]],
        dependency_count: int,
    ) -> Result[dict[str, Any]]:
        """Call the planner engine's ``analyze_complexity``.

        Returns ``Failure`` on security or availability errors, and
        locks the planner on security violations.
        """
        locked = self._raise_if_locked()
        if locked is not None:
            return locked  # type: ignore[return-value]

        try:
            _assert_no_text_boundary_payload(steps, context="planner steps")
            _assert_no_text_boundary_payload(dependency_count, context="planner dependency_count")
        except ValueError as exc:
            return Failure(AgentError(
                code=ErrorCode.VALIDATION,
                message=str(exc),
                source="planner",
            ))

        try:
            result = self._planner.analyze_complexity(
                steps=steps,
                dependency_count=dependency_count,
            )
            return Success(result)
        except UnifiedPlanningSecurityError as exc:
            self._planner_lock_reason = str(exc).strip() or exc.__class__.__name__
            return Failure(AgentError(
                code=ErrorCode.PERMISSION,
                message="Planner security policy violation detected; planner has been locked for this session",
                source="planner",
            ))
        except UnifiedPlanningUnavailableError as exc:
            return Failure(AgentError(
                code=ErrorCode.DEPENDENCY,
                message=f"Planner unavailable: {exc}",
                source="planner",
            ))

    def _execute_inner(self, arguments: Mapping[str, Any]) -> Result[dict[str, Any]]:
        locked = self._raise_if_locked()
        if locked is not None:
            return locked  # type: ignore[return-value]

        mode = str(arguments.get("mode", "analyze")).strip().lower()
        if mode not in {"create", "replan", "analyze"}:
            return Failure(AgentError(
                code=ErrorCode.VALIDATION,
                message="planner mode must be one of: create, replan, analyze",
                source="planner",
            ))

        goal = str(arguments.get("goal", "")).strip()
        if not goal:
            return Failure(AgentError(
                code=ErrorCode.VALIDATION,
                message="planner requires non-empty 'goal'",
                source="planner",
            ))

        ops_raw = arguments.get("ops")

        # ----------------------------------------------------------
        # create / replan WITH ops → delegate to PlanOpsPlugin logic
        # ----------------------------------------------------------
        if mode in {"create", "replan"}:
            if isinstance(ops_raw, list) and ops_raw:
                # Build a PlanOpsPlugin and delegate.
                from agent_host.adapters.tools.plan_ops.plugin import PlanOpsPlugin

                plan_ops_plugin = PlanOpsPlugin(
                    planner_engine=self._planner,
                    plan_store=self._plan_store,
                    allowed_roots=self._allowed_roots,
                )
                # Share lock state.
                plan_ops_plugin._planner_lock_reason = self._planner_lock_reason

                plan_result = plan_ops_plugin.execute({"ops": ops_raw})
                if plan_result.is_err:
                    return plan_result

                plan_payload = dict(plan_result.unwrap())
                plan_payload["mode"] = mode
                plan_payload["goal"] = goal

                prior_plan_id = str(arguments.get("prior_plan_id", "")).strip()
                if prior_plan_id:
                    plan_payload["prior_plan_id"] = prior_plan_id

                constraints = arguments.get("constraints")
                if isinstance(constraints, Mapping):
                    plan_payload["constraints"] = dict(constraints)

                return Success(plan_payload)

            # create / replan WITHOUT ops → advisory only
            abstract_steps: list[tuple[int, int, bool]] = []
            complexity_result = self._analyze_complexity(
                steps=abstract_steps,
                dependency_count=0,
            )
            if complexity_result.is_err:
                return complexity_result  # type: ignore[return-value]
            complexity = complexity_result.unwrap()

            advisory_payload: dict[str, Any] = {
                "ok": True,
                "mode": mode,
                "goal": goal,
                "op_count": 0,
                "advisory_only": True,
                "requires_ops_for_execution": True,
                "complexity": complexity,
                "privacy": self._privacy_payload(),
                "issues": [
                    "No structured 'ops' were provided.",
                    "Returned advisory planning analysis only; provide file ops to create executable plan_id.",
                ],
            }
            prior_plan_id = str(arguments.get("prior_plan_id", "")).strip()
            if prior_plan_id:
                advisory_payload["prior_plan_id"] = prior_plan_id
            constraints = arguments.get("constraints")
            if isinstance(constraints, Mapping):
                advisory_payload["constraints"] = dict(constraints)
            return Success(advisory_payload)

        # ----------------------------------------------------------
        # analyze mode
        # ----------------------------------------------------------
        if not isinstance(ops_raw, list):
            ops_raw = []
        abstract_steps = _abstract_steps_from_raw_ops(ops_raw)
        complexity_result = self._analyze_complexity(
            steps=abstract_steps,
            dependency_count=0,
        )
        if complexity_result.is_err:
            return complexity_result  # type: ignore[return-value]
        complexity = complexity_result.unwrap()

        return Success({
            "ok": True,
            "mode": mode,
            "goal": goal,
            "op_count": len(ops_raw),
            "complexity": complexity,
            "privacy": self._privacy_payload(),
        })
