"""Handler for the ``plan_ops`` tool."""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:
    from agent_host.tools.executor import ToolExecutor

from agent_host.tools.executor import ToolExecutionError


def handle(executor: ToolExecutor, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Execute the plan_ops tool."""
    executor._raise_if_planner_locked()
    # Prune expired plans and enforce max plan count
    executor._prune_expired_plans()
    if len(executor._plans) >= executor._MAX_PLANS:
        raise ToolExecutionError(
            f"Too many active plans ({len(executor._plans)}). "
            f"Execute or wait for existing plans to expire (TTL={int(executor._PLAN_TTL_SECONDS)}s)."
        )

    ops_raw = arguments.get("ops")
    if not isinstance(ops_raw, list) or not ops_raw:
        raise ToolExecutionError("plan_ops requires a non-empty 'ops' array")

    _VALID_OP_KINDS = {"move", "rename", "delete", "copy"}

    normalized_ops: list[dict[str, Any]] = []
    issues: list[str] = []
    for index, raw_op in enumerate(ops_raw):
        if not isinstance(raw_op, Mapping):
            issues.append(f"ops[{index}] must be an object")
            normalized_ops.append(
                {
                    "op": "",
                    "src": "",
                    "dest": None,
                    "issues": ["op entry must be an object"],
                    "valid": False,
                }
            )
            continue

        op_kind = str(raw_op.get("op", "")).strip().lower()
        src_raw = str(raw_op.get("src", "")).strip()
        dest_value = raw_op.get("dest")
        dest_raw = str(dest_value).strip() if dest_value is not None else ""
        overwrite_policy_raw = str(raw_op.get("overwrite_policy", "fail")).strip().lower()
        entry_issues: list[str] = []

        if op_kind not in _VALID_OP_KINDS:
            entry_issues.append(f"op must be one of {', '.join(sorted(_VALID_OP_KINDS))}")
        if not src_raw:
            entry_issues.append("src is required")
        if overwrite_policy_raw not in executor._OVERWRITE_POLICIES:
            allowed = ", ".join(sorted(executor._OVERWRITE_POLICIES))
            entry_issues.append(f"overwrite_policy must be one of {allowed}")
        try:
            src_path = executor._normalize_user_path(
                src_raw,
                must_exist=False,
                operate_on_symlink_path=(op_kind in ("delete", "move")),
            )
        except ToolExecutionError as exc:
            if src_raw and "\x00" not in src_raw:
                try:
                    src_path = Path(src_raw)
                except (OSError, RuntimeError, ValueError):
                    src_path = Path(".")
            else:
                src_path = Path(".")
            entry_issues.append(str(exc))

        dest_path: Path | None = None
        if op_kind != "delete":
            if not dest_raw:
                entry_issues.append(f"dest is required for {op_kind}")
            else:
                try:
                    dest_path = executor._normalize_user_path(dest_raw, must_exist=False)
                except ToolExecutionError as exc:
                    entry_issues.append(str(exc))

        normalized_ops.append(
            {
                "op": op_kind,
                "src": str(src_path),
                "dest": str(dest_path) if dest_path else None,
                "overwrite_policy": overwrite_policy_raw,
                "issues": entry_issues,
                "valid": not entry_issues,
            }
        )
        issues.extend(f"ops[{index}]: {issue}" for issue in entry_issues)

    dependency_edges = executor._infer_plan_dependencies(normalized_ops)
    abstract_steps = executor._planner_abstract_steps_from_normalized_ops(normalized_ops)
    complexity = executor._planner_analyze_complexity(
        steps=abstract_steps,
        dependency_count=len(dependency_edges),
    )
    planner_result = executor._planner_plan_order(
        step_count=len(normalized_ops),
        dependencies=dependency_edges,
    )
    ordered_indices_raw = planner_result.get("ordered_indices", [])
    if not isinstance(ordered_indices_raw, list):
        raise ToolExecutionError("Planner returned invalid ordered_indices payload")

    ordered_ops: list[dict[str, Any]] = []
    for planner_step, ordered_index in enumerate(ordered_indices_raw, start=1):
        if not isinstance(ordered_index, int):
            raise ToolExecutionError("Planner returned non-integer index")
        if ordered_index < 0 or ordered_index >= len(normalized_ops):
            raise ToolExecutionError("Planner returned out-of-range index")
        op_record = dict(normalized_ops[ordered_index])
        op_record["source_index"] = ordered_index
        op_record["planner_step"] = planner_step
        ordered_ops.append(op_record)

    plan_id = f"plan-{uuid.uuid4().hex[:12]}"
    executor._plans[plan_id] = {
        "created_at": time.time(),
        "ops": ordered_ops,
        "issues": issues,
        "complexity": complexity,
        "planner": planner_result,
    }
    return {
        "ok": not issues,
        "plan_id": plan_id,
        "ops": ordered_ops,
        "issues": issues,
        "complexity": complexity,
        "planner": planner_result,
        "privacy": executor._planner_privacy_payload(),
        "approval_required": True,
    }
