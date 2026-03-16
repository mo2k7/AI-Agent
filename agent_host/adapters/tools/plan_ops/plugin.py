"""Tool plugin: plan_ops.

Validates and orders a list of file operations into an executable plan.
Uses the unified planning engine for dependency-aware ordering and
complexity analysis.  Stores the resulting plan in the shared
``InMemoryPlanStore`` so ``ApplyOpsPlugin`` can later execute it.
"""

from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path
from typing import Any, Mapping, Sequence

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
_VALID_OP_KINDS = {"move", "rename", "delete", "copy"}
_OVERWRITE_POLICIES = {"fail", "rename", "overwrite"}

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


def _infer_plan_dependencies(
    ops: Sequence[dict[str, Any]],
) -> list[tuple[int, int]]:
    """Build abstract dependency edges using local path comparisons.

    Only returns integer edges -- no path strings are sent to the
    external planner engine.
    """
    edges: set[tuple[int, int]] = set()
    for i, left in enumerate(ops):
        left_src = str(left.get("src", "")).strip()
        left_dest = str(left.get("dest") or "").strip()
        for j in range(i + 1, len(ops)):
            right = ops[j]
            right_src = str(right.get("src", "")).strip()
            right_dest = str(right.get("dest") or "").strip()
            if left_dest and right_src and left_dest == right_src:
                edges.add((i, j))
            if left_src and right_src and left_src == right_src:
                edges.add((i, j))
            if left_dest and right_dest and left_dest == right_dest:
                edges.add((i, j))
    return sorted(edges)


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
        f"{context} contains unsupported type for planner boundary: "
        f"{type(payload).__name__}"
    )


# ---------------------------------------------------------------------------
# Plugin
# ---------------------------------------------------------------------------


class PlanOpsPlugin:
    """Self-contained plugin for the ``plan_ops`` tool.

    Validates a list of file operations, normalizes paths, infers
    dependencies, and delegates ordering to the unified planning
    engine.  The resulting plan is stored in the shared plan store.
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
        return "plan_ops"

    @property
    def description(self) -> str:
        return (
            "Validate and order file operations into an executable plan "
            "with dependency-aware ordering"
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "ops": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "op": {
                                "type": "string",
                                "enum": ["move", "rename", "delete", "copy"],
                            },
                            "src": {"type": "string"},
                            "dest": {"type": "string"},
                            "overwrite_policy": {
                                "type": "string",
                                "enum": ["fail", "rename", "overwrite"],
                            },
                        },
                        "required": ["op", "src"],
                    },
                    "description": "Array of file operation objects",
                },
            },
            "required": ["ops"],
        }

    def execute(self, arguments: Mapping[str, Any]) -> Result[dict[str, Any]]:
        """Execute the plan_ops tool, returning Success or Failure."""
        try:
            return self._execute_inner(arguments)
        except Exception as exc:
            return Failure(AgentError(
                code=ErrorCode.INTERNAL,
                message=f"Unexpected error in plan_ops: {exc}",
                source="plan_ops",
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
                source="plan_ops",
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
        """Call the planner engine's ``analyze_complexity``."""
        locked = self._raise_if_locked()
        if locked is not None:
            return locked  # type: ignore[return-value]

        try:
            _assert_no_text_boundary_payload(steps, context="planner steps")
            _assert_no_text_boundary_payload(
                dependency_count, context="planner dependency_count"
            )
        except ValueError as exc:
            return Failure(AgentError(
                code=ErrorCode.VALIDATION,
                message=str(exc),
                source="plan_ops",
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
                message=(
                    "Planner security policy violation detected; "
                    "planner has been locked for this session"
                ),
                source="plan_ops",
            ))
        except UnifiedPlanningUnavailableError as exc:
            return Failure(AgentError(
                code=ErrorCode.DEPENDENCY,
                message=f"Planner unavailable: {exc}",
                source="plan_ops",
            ))

    def _plan_order(
        self,
        *,
        step_count: int,
        dependencies: list[tuple[int, int]],
    ) -> Result[dict[str, Any]]:
        """Call the planner engine's ``plan_order``."""
        locked = self._raise_if_locked()
        if locked is not None:
            return locked  # type: ignore[return-value]

        try:
            _assert_no_text_boundary_payload(
                step_count, context="planner step_count"
            )
            _assert_no_text_boundary_payload(
                dependencies, context="planner dependencies"
            )
        except ValueError as exc:
            return Failure(AgentError(
                code=ErrorCode.VALIDATION,
                message=str(exc),
                source="plan_ops",
            ))

        try:
            result = self._planner.plan_order(
                step_count=step_count,
                dependencies=dependencies,
            )
            return Success(result)
        except UnifiedPlanningSecurityError as exc:
            self._planner_lock_reason = str(exc).strip() or exc.__class__.__name__
            return Failure(AgentError(
                code=ErrorCode.PERMISSION,
                message=(
                    "Planner security policy violation detected; "
                    "planner has been locked for this session"
                ),
                source="plan_ops",
            ))
        except UnifiedPlanningUnavailableError as exc:
            return Failure(AgentError(
                code=ErrorCode.DEPENDENCY,
                message=f"Planner unavailable: {exc}",
                source="plan_ops",
            ))

    def _normalize_path(
        self,
        raw_path: str,
        *,
        must_exist: bool = False,
        operate_on_symlink_path: bool = False,
    ) -> Result[Path]:
        """Normalize a user path with security checks."""
        return normalize_user_path(
            raw_path,
            allowed_roots=self._allowed_roots,
            must_exist=must_exist,
            operate_on_symlink_path=operate_on_symlink_path,
        )

    def _execute_inner(self, arguments: Mapping[str, Any]) -> Result[dict[str, Any]]:
        locked = self._raise_if_locked()
        if locked is not None:
            return locked  # type: ignore[return-value]

        # Prune expired plans and enforce capacity.
        self._plan_store.prune_expired()
        if self._plan_store.plan_count >= self._plan_store._max_plans:
            return Failure(AgentError(
                code=ErrorCode.RATE_LIMITED,
                message=(
                    f"Too many active plans ({self._plan_store.plan_count}). "
                    f"Execute or wait for existing plans to expire "
                    f"(TTL={int(self._plan_store._ttl_seconds)}s)."
                ),
                source="plan_ops",
            ))

        ops_raw = arguments.get("ops")
        if not isinstance(ops_raw, list) or not ops_raw:
            return Failure(AgentError(
                code=ErrorCode.VALIDATION,
                message="plan_ops requires a non-empty 'ops' array",
                source="plan_ops",
            ))

        normalized_ops: list[dict[str, Any]] = []
        issues: list[str] = []

        for index, raw_op in enumerate(ops_raw):
            if not isinstance(raw_op, Mapping):
                issues.append(f"ops[{index}] must be an object")
                normalized_ops.append({
                    "op": "",
                    "src": "",
                    "dest": None,
                    "issues": ["op entry must be an object"],
                    "valid": False,
                })
                continue

            op_kind = str(raw_op.get("op", "")).strip().lower()
            src_raw = str(raw_op.get("src", "")).strip()
            dest_value = raw_op.get("dest")
            dest_raw = str(dest_value).strip() if dest_value is not None else ""
            overwrite_policy_raw = str(
                raw_op.get("overwrite_policy", "fail")
            ).strip().lower()
            entry_issues: list[str] = []

            if op_kind not in _VALID_OP_KINDS:
                entry_issues.append(
                    f"op must be one of {', '.join(sorted(_VALID_OP_KINDS))}"
                )
            if not src_raw:
                entry_issues.append("src is required")
            if overwrite_policy_raw not in _OVERWRITE_POLICIES:
                allowed = ", ".join(sorted(_OVERWRITE_POLICIES))
                entry_issues.append(
                    f"overwrite_policy must be one of {allowed}"
                )

            # Normalize source path.
            src_path_result = normalize_user_path(
                src_raw,
                allowed_roots=self._allowed_roots,
                must_exist=False,
                operate_on_symlink_path=(op_kind in ("delete", "move")),
            )
            if src_path_result.is_ok:
                src_path = src_path_result.unwrap()
            else:
                # Fallback: keep raw path for error reporting.
                if src_raw and "\x00" not in src_raw:
                    try:
                        src_path = Path(src_raw)
                    except (OSError, RuntimeError, ValueError):
                        src_path = Path(".")
                else:
                    src_path = Path(".")
                entry_issues.append(src_path_result.error.message)

            # Normalize destination path (not needed for delete).
            dest_path: Path | None = None
            if op_kind != "delete":
                if not dest_raw:
                    entry_issues.append(f"dest is required for {op_kind}")
                else:
                    dest_path_result = normalize_user_path(
                        dest_raw,
                        allowed_roots=self._allowed_roots,
                        must_exist=False,
                    )
                    if dest_path_result.is_ok:
                        dest_path = dest_path_result.unwrap()
                    else:
                        entry_issues.append(dest_path_result.error.message)

            normalized_ops.append({
                "op": op_kind,
                "src": str(src_path),
                "dest": str(dest_path) if dest_path else None,
                "overwrite_policy": overwrite_policy_raw,
                "issues": entry_issues,
                "valid": not entry_issues,
            })
            issues.extend(f"ops[{index}]: {issue}" for issue in entry_issues)

        # Dependency inference and complexity analysis.
        dependency_edges = _infer_plan_dependencies(normalized_ops)
        abstract_steps = _abstract_steps_from_normalized_ops(normalized_ops)

        complexity_result = self._analyze_complexity(
            steps=abstract_steps,
            dependency_count=len(dependency_edges),
        )
        if complexity_result.is_err:
            return complexity_result  # type: ignore[return-value]
        complexity = complexity_result.unwrap()

        # Plan ordering via the planner engine.
        planner_result = self._plan_order(
            step_count=len(normalized_ops),
            dependencies=dependency_edges,
        )
        if planner_result.is_err:
            return planner_result  # type: ignore[return-value]
        planner_output = planner_result.unwrap()

        ordered_indices_raw = planner_output.get("ordered_indices", [])
        if not isinstance(ordered_indices_raw, list):
            return Failure(AgentError(
                code=ErrorCode.INTERNAL,
                message="Planner returned invalid ordered_indices payload",
                source="plan_ops",
            ))

        ordered_ops: list[dict[str, Any]] = []
        for planner_step, ordered_index in enumerate(ordered_indices_raw, start=1):
            if not isinstance(ordered_index, int):
                return Failure(AgentError(
                    code=ErrorCode.INTERNAL,
                    message="Planner returned non-integer index",
                    source="plan_ops",
                ))
            if ordered_index < 0 or ordered_index >= len(normalized_ops):
                return Failure(AgentError(
                    code=ErrorCode.INTERNAL,
                    message="Planner returned out-of-range index",
                    source="plan_ops",
                ))
            op_record = dict(normalized_ops[ordered_index])
            op_record["source_index"] = ordered_index
            op_record["planner_step"] = planner_step
            ordered_ops.append(op_record)

        # Store plan.
        plan_id = f"plan-{uuid.uuid4().hex[:12]}"
        self._plan_store.store_plan(plan_id, {
            "created_at": time.time(),
            "ops": ordered_ops,
            "issues": issues,
            "complexity": complexity,
            "planner": planner_output,
        })

        return Success({
            "ok": not issues,
            "plan_id": plan_id,
            "ops": ordered_ops,
            "issues": issues,
            "complexity": complexity,
            "planner": planner_output,
            "privacy": self._privacy_payload(),
            "approval_required": True,
        })
