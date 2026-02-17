"""Handler for the ``planner`` tool."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:
    from agent_host.tools.executor import ToolExecutor

from agent_host.tools.executor import ToolExecutionError


def handle(executor: ToolExecutor, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Execute the planner tool."""
    executor._raise_if_planner_locked()
    mode = str(arguments.get("mode", "analyze")).strip().lower()
    if mode not in {"create", "replan", "analyze"}:
        raise ToolExecutionError("planner mode must be one of: create, replan, analyze")

    goal = str(arguments.get("goal", "")).strip()
    if not goal:
        raise ToolExecutionError("planner requires non-empty 'goal'")

    ops_raw = arguments.get("ops")
    if mode in {"create", "replan"}:
        if isinstance(ops_raw, list) and ops_raw:
            plan_payload = executor._plan_ops({"ops": ops_raw})
            plan_payload["mode"] = mode
            plan_payload["goal"] = goal
            prior_plan_id = str(arguments.get("prior_plan_id", "")).strip()
            if prior_plan_id:
                plan_payload["prior_plan_id"] = prior_plan_id
            constraints = arguments.get("constraints")
            if isinstance(constraints, Mapping):
                plan_payload["constraints"] = dict(constraints)
            return plan_payload

        # Accept create/replan without ops for non-file planning prompts.
        # This returns advisory planner output instead of failing the tool call.
        abstract_steps: list[tuple[int, int, bool]] = []
        complexity = executor._planner_analyze_complexity(
            steps=abstract_steps,
            dependency_count=0,
        )
        advisory_payload: dict[str, Any] = {
            "ok": True,
            "mode": mode,
            "goal": goal,
            "op_count": 0,
            "advisory_only": True,
            "requires_ops_for_execution": True,
            "complexity": complexity,
            "privacy": executor._planner_privacy_payload(),
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
        return advisory_payload

    if not isinstance(ops_raw, list):
        ops_raw = []
    abstract_steps = executor._planner_abstract_steps_from_raw_ops(ops_raw)
    complexity = executor._planner_analyze_complexity(
        steps=abstract_steps,
        dependency_count=0,
    )
    return {
        "ok": True,
        "mode": mode,
        "goal": goal,
        "op_count": len(ops_raw),
        "complexity": complexity,
        "privacy": executor._planner_privacy_payload(),
    }
