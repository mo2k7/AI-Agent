"""Handler for the ``apply_ops`` tool."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:
    from agent_host.tools.executor import ToolExecutor

from agent_host.tools.executor import ToolExecutionError


def handle(executor: ToolExecutor, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Execute the apply_ops tool."""
    executor._raise_if_planner_locked()
    plan_id = str(arguments.get("plan_id", "")).strip()
    if not plan_id:
        raise ToolExecutionError("apply_ops requires 'plan_id'")

    # Check plan TTL
    executor._prune_expired_plans()
    plan = executor._plans.get(plan_id)
    if plan is None:
        raise ToolExecutionError(f"Unknown or expired plan_id: {plan_id}")

    # Dry-run mode: preview what would happen without executing.
    dry_run_raw = arguments.get("dry_run", False)
    if not isinstance(dry_run_raw, bool):
        raise ToolExecutionError("apply_ops 'dry_run' must be a boolean when provided")
    dry_run = dry_run_raw

    stop_on_error_raw = arguments.get("stop_on_error", False)
    if not isinstance(stop_on_error_raw, bool):
        raise ToolExecutionError("apply_ops 'stop_on_error' must be a boolean when provided")
    stop_on_error = stop_on_error_raw

    verify_after_raw = arguments.get("verify_after", True)
    if not isinstance(verify_after_raw, bool):
        raise ToolExecutionError("apply_ops 'verify_after' must be a boolean when provided")
    verify_after = verify_after_raw

    idempotency_key_raw = arguments.get("idempotency_key")
    if idempotency_key_raw is None:
        idempotency_key = ""
    elif isinstance(idempotency_key_raw, str):
        idempotency_key = idempotency_key_raw.strip()
        if not idempotency_key:
            raise ToolExecutionError("apply_ops 'idempotency_key' cannot be empty")
    else:
        raise ToolExecutionError("apply_ops 'idempotency_key' must be a string when provided")

    if idempotency_key and idempotency_key in executor._apply_idempotency_cache:
        cached = executor._apply_idempotency_cache[idempotency_key]
        replay = json.loads(json.dumps(cached))
        replay["idempotency_key"] = idempotency_key
        replay["idempotent_replay"] = True
        return replay

    ops = plan.get("ops", [])
    if not isinstance(ops, list):
        raise ToolExecutionError(f"Invalid plan data for {plan_id}")

    results: list[dict[str, Any]] = []
    failures = 0
    applied = 0
    skipped = 0
    stop_processing = False
    hard_delete_enabled = executor._is_enabled_env_var(executor._HARD_DELETE_ENV_VAR)
    for index, op in enumerate(ops):
        operation_index = index
        if isinstance(op, Mapping):
            raw_source_index = op.get("source_index")
            if isinstance(raw_source_index, int) and raw_source_index >= 0:
                operation_index = raw_source_index
        if stop_processing:
            skipped += 1
            results.append(
                {
                    "index": operation_index,
                    "ok": False,
                    "skipped": True,
                    "error": "Skipped because stop_on_error=true after prior failure",
                }
            )
            continue

        if not isinstance(op, Mapping):
            failures += 1
            results.append({"index": operation_index, "ok": False, "error": "Invalid op record"})
            if stop_on_error:
                stop_processing = True
            continue
        if op.get("issues"):
            failures += 1
            results.append(
                {
                    "index": operation_index,
                    "op": op.get("op"),
                    "ok": False,
                    "error": "; ".join(str(issue) for issue in op.get("issues", [])),
                }
            )
            if stop_on_error:
                stop_processing = True
            continue

        op_kind = str(op.get("op", ""))
        src_raw = str(op.get("src", ""))
        dest_raw = op.get("dest")
        overwrite_policy_raw = str(op.get("overwrite_policy", "fail")).strip().lower()
        if overwrite_policy_raw not in executor._OVERWRITE_POLICIES:
            failures += 1
            results.append(
                {
                    "index": operation_index,
                    "op": op_kind,
                    "ok": False,
                    "src": src_raw,
                    "dest": str(dest_raw) if isinstance(dest_raw, str) else None,
                    "error": (
                        "Invalid overwrite_policy: "
                        f"{overwrite_policy_raw} "
                        f"(expected one of: {', '.join(sorted(executor._OVERWRITE_POLICIES))})"
                    ),
                }
            )
            if stop_on_error:
                stop_processing = True
            continue

        # Re-validate paths at execution time to prevent TOCTOU attacks
        # (paths were validated at plan time but may have changed since).
        try:
            # For delete/move, we operate on the link itself, so we don't enforce
            # that the link target is within allowed roots (we might be deleting a broken link).
            is_link_op = op_kind in ("delete", "move")
            src_path = executor._normalize_user_path(
                src_raw,
                must_exist=False,
                operate_on_symlink_path=is_link_op,
                check_target_root=not is_link_op,
            )
        except ToolExecutionError as exc:
            failures += 1
            results.append({
                "index": operation_index, "op": op_kind, "ok": False,
                "src": src_raw, "error": str(exc),
            })
            if stop_on_error:
                stop_processing = True
            continue

        dest_path: Path | None = None
        if isinstance(dest_raw, str) and dest_raw:
            try:
                dest_path = executor._normalize_user_path(dest_raw, must_exist=False)
            except ToolExecutionError as exc:
                failures += 1
                results.append({
                    "index": operation_index, "op": op_kind, "ok": False,
                    "src": str(src_path),
                    "dest": dest_raw,
                    "error": str(exc),
                })
                if stop_on_error:
                    stop_processing = True
                continue

        try:
            if op_kind in {"move", "rename"}:
                if dest_path is None:
                    raise ToolExecutionError("Missing destination path")
                if not src_path.exists():
                    raise ToolExecutionError(f"Source does not exist: {src_path}")
                resolved_dest, destination_conflict = executor._resolve_destination_with_policy(
                    destination=dest_path,
                    overwrite_policy=overwrite_policy_raw,
                )
                overwrite_details: dict[str, Any] = {}
                if dry_run:
                    will_overwrite = bool(
                        destination_conflict and overwrite_policy_raw == "overwrite"
                    )
                    results.append({
                        "index": operation_index, "op": op_kind, "ok": True, "dry_run": True,
                        "src": str(src_path), "dest": str(resolved_dest),
                        "overwrite_policy": overwrite_policy_raw,
                        "destination_conflict": destination_conflict,
                        "will_overwrite": will_overwrite,
                    })
                else:
                    if destination_conflict and overwrite_policy_raw == "overwrite":
                        try:
                            overwritten_trashed = executor._move_path_to_trash(resolved_dest)
                        except (PermissionError, OSError) as overwrite_exc:
                            raise ToolExecutionError(
                                f"Overwrite destination cleanup failed: {overwrite_exc}"
                            ) from overwrite_exc
                        overwrite_details = {
                            "overwritten_destination": str(resolved_dest),
                            "overwritten_destination_trashed_to": str(overwritten_trashed),
                        }
                    resolved_dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(src_path), str(resolved_dest))
                    verification_error = (
                        executor._verify_apply_result(
                            op_kind=op_kind,
                            src_path=src_path,
                            dest_path=resolved_dest,
                        )
                        if verify_after
                        else None
                    )
                    if verification_error:
                        raise ToolExecutionError(
                            f"{verification_error} "
                            f"(Note: the {op_kind} from '{src_path}' to '{resolved_dest}' was already executed.)"
                        )
                    result_entry = {
                        "index": operation_index, "op": op_kind, "ok": True,
                        "src": str(src_path), "dest": str(resolved_dest),
                        "overwrite_policy": overwrite_policy_raw,
                    }
                    result_entry.update(overwrite_details)
                    results.append(result_entry)
                    applied += 1
            elif op_kind == "copy":
                if dest_path is None:
                    raise ToolExecutionError("Missing destination path")
                if not src_path.exists():
                    raise ToolExecutionError(f"Source does not exist: {src_path}")
                resolved_dest, destination_conflict = executor._resolve_destination_with_policy(
                    destination=dest_path,
                    overwrite_policy=overwrite_policy_raw,
                )
                overwrite_details = {}
                if dry_run:
                    will_overwrite = bool(
                        destination_conflict and overwrite_policy_raw == "overwrite"
                    )
                    results.append({
                        "index": operation_index, "op": op_kind, "ok": True, "dry_run": True,
                        "src": str(src_path), "dest": str(resolved_dest),
                        "overwrite_policy": overwrite_policy_raw,
                        "destination_conflict": destination_conflict,
                        "will_overwrite": will_overwrite,
                    })
                else:
                    if destination_conflict and overwrite_policy_raw == "overwrite":
                        try:
                            overwritten_trashed = executor._move_path_to_trash(resolved_dest)
                        except (PermissionError, OSError) as overwrite_exc:
                            raise ToolExecutionError(
                                f"Overwrite destination cleanup failed: {overwrite_exc}"
                            ) from overwrite_exc
                        overwrite_details = {
                            "overwritten_destination": str(resolved_dest),
                            "overwritten_destination_trashed_to": str(overwritten_trashed),
                        }
                    resolved_dest.parent.mkdir(parents=True, exist_ok=True)
                    if src_path.is_dir():
                        shutil.copytree(
                            str(src_path),
                            str(resolved_dest),
                            dirs_exist_ok=False,
                        )
                    else:
                        shutil.copy2(str(src_path), str(resolved_dest))
                    verification_error = (
                        executor._verify_apply_result(
                            op_kind=op_kind,
                            src_path=src_path,
                            dest_path=resolved_dest,
                        )
                        if verify_after
                        else None
                    )
                    if verification_error:
                        raise ToolExecutionError(
                            f"{verification_error} "
                            f"(Note: the {op_kind} from '{src_path}' to '{resolved_dest}' was already executed.)"
                        )
                    result_entry = {
                        "index": operation_index, "op": op_kind, "ok": True,
                        "src": str(src_path), "dest": str(resolved_dest),
                        "overwrite_policy": overwrite_policy_raw,
                    }
                    result_entry.update(overwrite_details)
                    results.append(result_entry)
                    applied += 1
            elif op_kind == "delete":
                if not src_path.exists():
                    raise ToolExecutionError(f"Source does not exist: {src_path}")
                if dry_run:
                    delete_mode = "hard" if hard_delete_enabled else "trash"
                    results.append({
                        "index": operation_index, "op": op_kind, "ok": True, "dry_run": True,
                        "src": str(src_path), "delete_mode": delete_mode,
                        "is_dir": src_path.is_dir(),
                    })
                elif hard_delete_enabled:
                    if src_path.is_symlink():
                        src_path.unlink()
                    elif src_path.is_dir():
                        shutil.rmtree(src_path)
                    else:
                        src_path.unlink()
                    verification_error = (
                        executor._verify_apply_result(
                            op_kind=op_kind,
                            src_path=src_path,
                            dest_path=None,
                        )
                        if verify_after
                        else None
                    )
                    if verification_error:
                        raise ToolExecutionError(
                            f"{verification_error} "
                            f"(Note: the {op_kind} of '{src_path}' was already executed.)"
                        )
                    results.append({
                        "index": operation_index, "op": op_kind, "ok": True,
                        "src": str(src_path), "delete_mode": "hard",
                        "hard_delete_env_var": executor._HARD_DELETE_ENV_VAR,
                    })
                    applied += 1
                else:
                    try:
                        trashed_path = executor._move_path_to_trash(src_path)
                        verification_error = (
                            executor._verify_apply_result(
                                op_kind=op_kind,
                                src_path=src_path,
                                dest_path=None,
                            )
                            if verify_after
                            else None
                        )
                        if verification_error:
                            raise ToolExecutionError(
                                f"{verification_error} "
                                f"(Note: the {op_kind} of '{src_path}' was already executed.)"
                            )
                        results.append({
                            "index": operation_index, "op": op_kind, "ok": True,
                            "src": str(src_path), "delete_mode": "trash",
                            "trash_path": str(trashed_path),
                            "hard_delete_env_var": executor._HARD_DELETE_ENV_VAR,
                        })
                        applied += 1
                    except (PermissionError, OSError) as trash_exc:
                        # Safety: do NOT silently fall back to hard delete.
                        # Surface the error so the user can decide.
                        failures += 1
                        results.append({
                            "index": operation_index, "op": op_kind, "ok": False,
                            "src": str(src_path),
                            "error": (
                                f"Trash failed: {trash_exc}. "
                                f"Set {executor._HARD_DELETE_ENV_VAR}=true to enable permanent deletion."
                            ),
                        })
                        if stop_on_error:
                            stop_processing = True
                        continue
            else:
                raise ToolExecutionError(f"Unsupported operation kind: {op_kind}")
        except ToolExecutionError as tool_exc:
            failures += 1
            results.append({
                "index": operation_index, "op": op_kind, "ok": False,
                "src": str(src_path),
                "dest": str(dest_path) if dest_path else None,
                "error": str(tool_exc),
                "error_type": tool_exc.error_type,
                "retryable": tool_exc.retryable,
            })
            if stop_on_error:
                stop_processing = True
        except Exception as exc:
            failures += 1
            results.append({
                "index": operation_index, "op": op_kind, "ok": False,
                "src": str(src_path),
                "dest": str(dest_path) if dest_path else None,
                "error": str(exc),
            })
            if stop_on_error:
                stop_processing = True

    result_payload = {
        "ok": failures == 0,
        "plan_id": plan_id,
        "dry_run": dry_run,
        "stop_on_error": stop_on_error,
        "verify_after": verify_after,
        "idempotency_key": idempotency_key or None,
        "idempotent_replay": False,
        "applied": applied if not dry_run else len([row for row in results if row.get("ok")]),
        "failed": failures,
        "skipped": skipped,
        "results": results,
    }
    if idempotency_key:
        while (
            len(executor._apply_idempotency_cache) >= executor._APPLY_IDEMPOTENCY_CACHE_MAX
            and idempotency_key not in executor._apply_idempotency_cache
        ):
            oldest_key = next(iter(executor._apply_idempotency_cache))
            executor._apply_idempotency_cache.pop(oldest_key, None)
        executor._apply_idempotency_cache[idempotency_key] = json.loads(
            json.dumps(result_payload)
        )
    return result_payload
