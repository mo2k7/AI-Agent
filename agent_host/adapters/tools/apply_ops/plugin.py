"""Tool plugin: apply_ops.

Executes a previously-created plan (from ``PlanOpsPlugin``) by applying
file operations (move, rename, copy, delete) with conflict resolution,
trash-based deletion, verification, and idempotency support.

Reads plans from the shared ``InMemoryPlanStore`` and performs real
filesystem mutations.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import uuid
from pathlib import Path
from typing import Any, Mapping, Sequence

from agent_host.adapters.tools._path_security import (
    normalize_user_path,
    path_within_roots,
)
from agent_host.contracts.types.errors import AgentError, ErrorCode
from agent_host.contracts.types.result import Failure, Result, Success

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants (mirrored from ToolExecutor)
# ---------------------------------------------------------------------------
_OVERWRITE_POLICIES = {"fail", "rename", "overwrite"}
_HARD_DELETE_ENV_VAR = "AI_AGENT_ENABLE_HARD_DELETE"
_TRASH_COLLISION_ATTEMPTS = 100
_APPLY_IDEMPOTENCY_CACHE_MAX = 200


# ---------------------------------------------------------------------------
# Plugin
# ---------------------------------------------------------------------------


class ApplyOpsPlugin:
    """Self-contained plugin for the ``apply_ops`` tool.

    Executes an ordered plan of file operations stored in the shared
    plan store.  Supports dry-run mode, stop-on-error, post-op
    verification, and idempotency keys.
    """

    def __init__(
        self,
        *,
        plan_store: Any,
        allowed_roots: Sequence[Path],
        enable_open_item: bool = False,
    ) -> None:
        self._plan_store = plan_store
        self._allowed_roots: list[Path] = [
            r.expanduser().resolve(strict=False) for r in allowed_roots
        ]
        self._planner_lock_reason: str = ""
        self._idempotency_cache: dict[str, dict] = {}
        self._enable_open_item = enable_open_item

    # ------------------------------------------------------------------
    # ToolPlugin protocol
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "apply_ops"

    @property
    def description(self) -> str:
        return (
            "Execute a previously-created file operation plan with "
            "conflict resolution and verification"
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "plan_id": {
                    "type": "string",
                    "description": "The plan ID returned by plan_ops",
                },
                "dry_run": {
                    "type": "boolean",
                    "description": (
                        "If true, preview what would happen without "
                        "executing any operations"
                    ),
                },
                "stop_on_error": {
                    "type": "boolean",
                    "description": (
                        "If true, stop processing remaining ops after "
                        "the first failure"
                    ),
                },
                "verify_after": {
                    "type": "boolean",
                    "description": (
                        "If true (default), verify each operation "
                        "completed successfully"
                    ),
                },
                "idempotency_key": {
                    "type": "string",
                    "description": (
                        "Optional key for idempotent replay. If the same "
                        "key is submitted again, the cached result is returned."
                    ),
                },
            },
            "required": ["plan_id"],
        }

    def execute(self, arguments: Mapping[str, Any]) -> Result[dict[str, Any]]:
        """Execute the apply_ops tool, returning Success or Failure."""
        try:
            return self._execute_inner(arguments)
        except Exception as exc:
            return Failure(AgentError(
                code=ErrorCode.INTERNAL,
                message=f"Unexpected error in apply_ops: {exc}",
                source="apply_ops",
            ))

    def health_check(self) -> Result[bool]:
        return Success(True)

    # ------------------------------------------------------------------
    # Internal — lock check
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
                source="apply_ops",
            ))
        return None

    # ------------------------------------------------------------------
    # Internal — trash helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _trash_directory() -> Path:
        return Path.home().expanduser().resolve(strict=False) / ".Trash"

    def _trash_directory_candidates(self, *, src_path: Path) -> list[Path]:
        candidates: list[Path] = [self._trash_directory()]
        src_resolved = src_path.expanduser().resolve(strict=False)
        for root in self._allowed_roots:
            if src_resolved == root or root in src_resolved.parents:
                candidate = root / ".ai-agent-trash"
                if candidate not in candidates:
                    candidates.append(candidate)
                break
        return candidates

    @staticmethod
    def _next_available_trash_path(name: str, *, trash_dir: Path) -> Path:
        preferred = trash_dir / name
        if not preferred.exists():
            return preferred

        source = Path(name)
        suffix = "".join(source.suffixes)
        stem = source.name[: -len(suffix)] if suffix else source.name
        stem = stem.rstrip() or "item"

        for index in range(1, _TRASH_COLLISION_ATTEMPTS + 1):
            candidate = trash_dir / f"{stem} {index}{suffix}"
            if not candidate.exists():
                return candidate

        return trash_dir / f"{stem}-{uuid.uuid4().hex}{suffix}"

    def _move_path_to_trash(self, src_path: Path) -> Path:
        """Move a path to trash, trying candidates in order.

        Returns the final trash path on success.
        Raises ``OSError`` if all candidates fail.
        """
        src_resolved = src_path.resolve(strict=False)
        move_errors: list[OSError] = []

        for trash_dir in self._trash_directory_candidates(src_path=src_path):
            try:
                trash_dir.mkdir(parents=True, exist_ok=True)
                trash_resolved = trash_dir.resolve(strict=False)
            except OSError as exc:
                move_errors.append(exc)
                continue

            if src_resolved.parent == trash_resolved:
                return src_resolved

            destination = self._next_available_trash_path(
                src_path.name, trash_dir=trash_dir
            )
            try:
                shutil.move(str(src_path), str(destination))
                return destination
            except OSError as exc:
                move_errors.append(exc)
                continue

        if move_errors:
            raise move_errors[-1]
        raise OSError("No writable trash directory available")

    # ------------------------------------------------------------------
    # Internal — destination resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _next_available_destination_path(destination: Path) -> Path:
        if not destination.exists():
            return destination

        suffix = "".join(destination.suffixes)
        stem = destination.name[: -len(suffix)] if suffix else destination.name
        stem = stem.rstrip() or "item"
        for index in range(1, 1001):
            candidate = destination.parent / f"{stem} {index}{suffix}"
            if not candidate.exists():
                return candidate
        return destination.parent / f"{stem}-{uuid.uuid4().hex}{suffix}"

    def _resolve_destination_with_policy(
        self,
        *,
        destination: Path,
        overwrite_policy: str,
    ) -> tuple[Path, bool]:
        """Resolve destination path according to conflict policy.

        Returns ``(resolved_destination, destination_already_exists)``.
        Raises ``ValueError`` on fail-policy conflict.
        """
        destination_exists = destination.exists()
        if not destination_exists:
            return destination, False

        if overwrite_policy == "rename":
            return self._next_available_destination_path(destination), True
        if overwrite_policy == "overwrite":
            return destination, True
        raise ValueError(
            f"Destination already exists: {destination} (overwrite_policy=fail)"
        )

    # ------------------------------------------------------------------
    # Internal — post-op verification
    # ------------------------------------------------------------------

    @staticmethod
    def _verify_apply_result(
        *,
        op_kind: str,
        src_path: Path,
        dest_path: Path | None,
    ) -> str | None:
        """Verify an operation completed successfully.

        Returns ``None`` on success or an error message string.
        """
        if op_kind in {"move", "rename"}:
            if dest_path is None:
                return "Verification failed: destination path missing"
            if src_path.exists():
                return (
                    f"Verification failed: source still exists "
                    f"after {op_kind}: {src_path}"
                )
            if not dest_path.exists():
                return (
                    f"Verification failed: destination missing "
                    f"after {op_kind}: {dest_path}"
                )
            return None
        if op_kind == "copy":
            if dest_path is None:
                return "Verification failed: destination path missing"
            if not src_path.exists():
                return (
                    f"Verification failed: source missing after copy: {src_path}"
                )
            if not dest_path.exists():
                return (
                    f"Verification failed: destination missing "
                    f"after copy: {dest_path}"
                )
            return None
        if op_kind == "delete":
            if src_path.exists():
                return (
                    f"Verification failed: source still exists "
                    f"after delete: {src_path}"
                )
            return None
        return None

    # ------------------------------------------------------------------
    # Internal — env var helper
    # ------------------------------------------------------------------

    @staticmethod
    def _is_enabled_env_var(name: str) -> bool:
        raw = os.getenv(name)
        if raw is None:
            return False
        return raw.strip().lower() in {"1", "true", "yes", "on"}

    # ------------------------------------------------------------------
    # Internal — main execution
    # ------------------------------------------------------------------

    def _execute_inner(  # noqa: C901 — faithful reproduction of apply_ops logic
        self,
        arguments: Mapping[str, Any],
    ) -> Result[dict[str, Any]]:
        locked = self._raise_if_locked()
        if locked is not None:
            return locked  # type: ignore[return-value]

        plan_id = str(arguments.get("plan_id", "")).strip()
        if not plan_id:
            return Failure(AgentError(
                code=ErrorCode.VALIDATION,
                message="apply_ops requires 'plan_id'",
                source="apply_ops",
            ))

        # Prune expired plans, then look up.
        self._plan_store.prune_expired()
        plan = self._plan_store.get_plan(plan_id)
        if plan is None:
            return Failure(AgentError(
                code=ErrorCode.NOT_FOUND,
                message=f"Unknown or expired plan_id: {plan_id}",
                source="apply_ops",
            ))

        # ----- Parse boolean flags -----
        dry_run_raw = arguments.get("dry_run", False)
        if not isinstance(dry_run_raw, bool):
            return Failure(AgentError(
                code=ErrorCode.VALIDATION,
                message="apply_ops 'dry_run' must be a boolean when provided",
                source="apply_ops",
            ))
        dry_run: bool = dry_run_raw

        stop_on_error_raw = arguments.get("stop_on_error", False)
        if not isinstance(stop_on_error_raw, bool):
            return Failure(AgentError(
                code=ErrorCode.VALIDATION,
                message="apply_ops 'stop_on_error' must be a boolean when provided",
                source="apply_ops",
            ))
        stop_on_error: bool = stop_on_error_raw

        verify_after_raw = arguments.get("verify_after", True)
        if not isinstance(verify_after_raw, bool):
            return Failure(AgentError(
                code=ErrorCode.VALIDATION,
                message="apply_ops 'verify_after' must be a boolean when provided",
                source="apply_ops",
            ))
        verify_after: bool = verify_after_raw

        # ----- Idempotency key -----
        idempotency_key_raw = arguments.get("idempotency_key")
        if idempotency_key_raw is None:
            idempotency_key = ""
        elif isinstance(idempotency_key_raw, str):
            idempotency_key = idempotency_key_raw.strip()
            if not idempotency_key:
                return Failure(AgentError(
                    code=ErrorCode.VALIDATION,
                    message="apply_ops 'idempotency_key' cannot be empty",
                    source="apply_ops",
                ))
        else:
            return Failure(AgentError(
                code=ErrorCode.VALIDATION,
                message="apply_ops 'idempotency_key' must be a string when provided",
                source="apply_ops",
            ))

        # Check idempotency cache.
        if idempotency_key and idempotency_key in self._idempotency_cache:
            cached = self._idempotency_cache[idempotency_key]
            replay = json.loads(json.dumps(cached))
            replay["idempotency_key"] = idempotency_key
            replay["idempotent_replay"] = True
            return Success(replay)

        # ----- Execute ops -----
        ops = plan.get("ops", [])
        if not isinstance(ops, list):
            return Failure(AgentError(
                code=ErrorCode.INTERNAL,
                message=f"Invalid plan data for {plan_id}",
                source="apply_ops",
            ))

        results: list[dict[str, Any]] = []
        failures = 0
        applied = 0
        skipped = 0
        stop_processing = False
        hard_delete_enabled = self._is_enabled_env_var(_HARD_DELETE_ENV_VAR)

        for index, op in enumerate(ops):
            operation_index = index
            if isinstance(op, Mapping):
                raw_source_index = op.get("source_index")
                if isinstance(raw_source_index, int) and raw_source_index >= 0:
                    operation_index = raw_source_index

            # Skip remaining ops after a prior failure when stop_on_error.
            if stop_processing:
                skipped += 1
                results.append({
                    "index": operation_index,
                    "ok": False,
                    "skipped": True,
                    "error": (
                        "Skipped because stop_on_error=true after prior failure"
                    ),
                })
                continue

            if not isinstance(op, Mapping):
                failures += 1
                results.append({
                    "index": operation_index,
                    "ok": False,
                    "error": "Invalid op record",
                })
                if stop_on_error:
                    stop_processing = True
                continue

            if op.get("issues"):
                failures += 1
                results.append({
                    "index": operation_index,
                    "op": op.get("op"),
                    "ok": False,
                    "error": "; ".join(
                        str(issue) for issue in op.get("issues", [])
                    ),
                })
                if stop_on_error:
                    stop_processing = True
                continue

            op_kind = str(op.get("op", ""))
            src_raw = str(op.get("src", ""))
            dest_raw = op.get("dest")
            overwrite_policy_raw = str(
                op.get("overwrite_policy", "fail")
            ).strip().lower()

            if overwrite_policy_raw not in _OVERWRITE_POLICIES:
                failures += 1
                results.append({
                    "index": operation_index,
                    "op": op_kind,
                    "ok": False,
                    "src": src_raw,
                    "dest": (
                        str(dest_raw) if isinstance(dest_raw, str) else None
                    ),
                    "error": (
                        f"Invalid overwrite_policy: {overwrite_policy_raw} "
                        f"(expected one of: "
                        f"{', '.join(sorted(_OVERWRITE_POLICIES))})"
                    ),
                })
                if stop_on_error:
                    stop_processing = True
                continue

            # Re-validate paths at execution time (TOCTOU mitigation).
            is_link_op = op_kind in ("delete", "move")
            src_path_result = normalize_user_path(
                src_raw,
                allowed_roots=self._allowed_roots,
                must_exist=False,
                operate_on_symlink_path=is_link_op,
                check_target_root=not is_link_op,
            )
            if src_path_result.is_err:
                failures += 1
                results.append({
                    "index": operation_index,
                    "op": op_kind,
                    "ok": False,
                    "src": src_raw,
                    "error": src_path_result.error.message,
                })
                if stop_on_error:
                    stop_processing = True
                continue
            src_path: Path = src_path_result.unwrap()

            dest_path: Path | None = None
            if isinstance(dest_raw, str) and dest_raw:
                dest_path_result = normalize_user_path(
                    dest_raw,
                    allowed_roots=self._allowed_roots,
                    must_exist=False,
                )
                if dest_path_result.is_err:
                    failures += 1
                    results.append({
                        "index": operation_index,
                        "op": op_kind,
                        "ok": False,
                        "src": str(src_path),
                        "dest": dest_raw,
                        "error": dest_path_result.error.message,
                    })
                    if stop_on_error:
                        stop_processing = True
                    continue
                dest_path = dest_path_result.unwrap()

            try:
                if op_kind in {"move", "rename"}:
                    self._apply_move_rename(
                        op_kind=op_kind,
                        src_path=src_path,
                        dest_path=dest_path,
                        overwrite_policy_raw=overwrite_policy_raw,
                        dry_run=dry_run,
                        verify_after=verify_after,
                        operation_index=operation_index,
                        results=results,
                    )
                    if not dry_run:
                        applied += 1

                elif op_kind == "copy":
                    self._apply_copy(
                        src_path=src_path,
                        dest_path=dest_path,
                        overwrite_policy_raw=overwrite_policy_raw,
                        dry_run=dry_run,
                        verify_after=verify_after,
                        operation_index=operation_index,
                        results=results,
                    )
                    if not dry_run:
                        applied += 1

                elif op_kind == "delete":
                    delete_ok = self._apply_delete(
                        src_path=src_path,
                        hard_delete_enabled=hard_delete_enabled,
                        dry_run=dry_run,
                        verify_after=verify_after,
                        operation_index=operation_index,
                        stop_on_error=stop_on_error,
                        results=results,
                    )
                    if delete_ok is None:
                        # Trash failure was handled inside _apply_delete.
                        failures += 1
                        if stop_on_error:
                            stop_processing = True
                        continue
                    if not dry_run:
                        applied += 1

                else:
                    raise _OpError(f"Unsupported operation kind: {op_kind}")

            except _OpError as op_exc:
                failures += 1
                results.append({
                    "index": operation_index,
                    "op": op_kind,
                    "ok": False,
                    "src": str(src_path),
                    "dest": str(dest_path) if dest_path else None,
                    "error": str(op_exc),
                    "error_type": op_exc.error_type,
                    "retryable": op_exc.retryable,
                })
                if stop_on_error:
                    stop_processing = True

            except Exception as exc:
                failures += 1
                results.append({
                    "index": operation_index,
                    "op": op_kind,
                    "ok": False,
                    "src": str(src_path),
                    "dest": str(dest_path) if dest_path else None,
                    "error": str(exc),
                })
                if stop_on_error:
                    stop_processing = True

        # ----- Build result payload -----
        result_payload: dict[str, Any] = {
            "ok": failures == 0,
            "plan_id": plan_id,
            "dry_run": dry_run,
            "stop_on_error": stop_on_error,
            "verify_after": verify_after,
            "idempotency_key": idempotency_key or None,
            "idempotent_replay": False,
            "applied": (
                applied
                if not dry_run
                else len([row for row in results if row.get("ok")])
            ),
            "failed": failures,
            "skipped": skipped,
            "results": results,
        }

        # Store idempotency cache entry.
        if idempotency_key:
            while (
                len(self._idempotency_cache) >= _APPLY_IDEMPOTENCY_CACHE_MAX
                and idempotency_key not in self._idempotency_cache
            ):
                oldest_key = next(iter(self._idempotency_cache))
                self._idempotency_cache.pop(oldest_key, None)
            self._idempotency_cache[idempotency_key] = json.loads(
                json.dumps(result_payload)
            )

        return Success(result_payload)

    # ------------------------------------------------------------------
    # Per-op execution helpers
    # ------------------------------------------------------------------

    def _apply_move_rename(
        self,
        *,
        op_kind: str,
        src_path: Path,
        dest_path: Path | None,
        overwrite_policy_raw: str,
        dry_run: bool,
        verify_after: bool,
        operation_index: int,
        results: list[dict[str, Any]],
    ) -> None:
        """Apply a move or rename operation."""
        if dest_path is None:
            raise _OpError("Missing destination path")
        if not src_path.exists():
            raise _OpError(f"Source does not exist: {src_path}")

        try:
            resolved_dest, destination_conflict = (
                self._resolve_destination_with_policy(
                    destination=dest_path,
                    overwrite_policy=overwrite_policy_raw,
                )
            )
        except ValueError as exc:
            raise _OpError(str(exc)) from exc

        overwrite_details: dict[str, Any] = {}

        if dry_run:
            will_overwrite = bool(
                destination_conflict and overwrite_policy_raw == "overwrite"
            )
            results.append({
                "index": operation_index,
                "op": op_kind,
                "ok": True,
                "dry_run": True,
                "src": str(src_path),
                "dest": str(resolved_dest),
                "overwrite_policy": overwrite_policy_raw,
                "destination_conflict": destination_conflict,
                "will_overwrite": will_overwrite,
            })
            return

        if destination_conflict and overwrite_policy_raw == "overwrite":
            try:
                overwritten_trashed = self._move_path_to_trash(resolved_dest)
            except (PermissionError, OSError) as overwrite_exc:
                raise _OpError(
                    f"Overwrite destination cleanup failed: {overwrite_exc}"
                ) from overwrite_exc
            overwrite_details = {
                "overwritten_destination": str(resolved_dest),
                "overwritten_destination_trashed_to": str(overwritten_trashed),
            }

        resolved_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src_path), str(resolved_dest))

        verification_error = (
            self._verify_apply_result(
                op_kind=op_kind,
                src_path=src_path,
                dest_path=resolved_dest,
            )
            if verify_after
            else None
        )
        if verification_error:
            raise _OpError(
                f"{verification_error} "
                f"(Note: the {op_kind} from '{src_path}' to "
                f"'{resolved_dest}' was already executed.)"
            )

        result_entry: dict[str, Any] = {
            "index": operation_index,
            "op": op_kind,
            "ok": True,
            "src": str(src_path),
            "dest": str(resolved_dest),
            "overwrite_policy": overwrite_policy_raw,
        }
        result_entry.update(overwrite_details)
        results.append(result_entry)

    def _apply_copy(
        self,
        *,
        src_path: Path,
        dest_path: Path | None,
        overwrite_policy_raw: str,
        dry_run: bool,
        verify_after: bool,
        operation_index: int,
        results: list[dict[str, Any]],
    ) -> None:
        """Apply a copy operation."""
        if dest_path is None:
            raise _OpError("Missing destination path")
        if not src_path.exists():
            raise _OpError(f"Source does not exist: {src_path}")

        try:
            resolved_dest, destination_conflict = (
                self._resolve_destination_with_policy(
                    destination=dest_path,
                    overwrite_policy=overwrite_policy_raw,
                )
            )
        except ValueError as exc:
            raise _OpError(str(exc)) from exc

        overwrite_details: dict[str, Any] = {}

        if dry_run:
            will_overwrite = bool(
                destination_conflict and overwrite_policy_raw == "overwrite"
            )
            results.append({
                "index": operation_index,
                "op": "copy",
                "ok": True,
                "dry_run": True,
                "src": str(src_path),
                "dest": str(resolved_dest),
                "overwrite_policy": overwrite_policy_raw,
                "destination_conflict": destination_conflict,
                "will_overwrite": will_overwrite,
            })
            return

        if destination_conflict and overwrite_policy_raw == "overwrite":
            try:
                overwritten_trashed = self._move_path_to_trash(resolved_dest)
            except (PermissionError, OSError) as overwrite_exc:
                raise _OpError(
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
            self._verify_apply_result(
                op_kind="copy",
                src_path=src_path,
                dest_path=resolved_dest,
            )
            if verify_after
            else None
        )
        if verification_error:
            raise _OpError(
                f"{verification_error} "
                f"(Note: the copy from '{src_path}' to "
                f"'{resolved_dest}' was already executed.)"
            )

        result_entry: dict[str, Any] = {
            "index": operation_index,
            "op": "copy",
            "ok": True,
            "src": str(src_path),
            "dest": str(resolved_dest),
            "overwrite_policy": overwrite_policy_raw,
        }
        result_entry.update(overwrite_details)
        results.append(result_entry)

    def _apply_delete(
        self,
        *,
        src_path: Path,
        hard_delete_enabled: bool,
        dry_run: bool,
        verify_after: bool,
        operation_index: int,
        stop_on_error: bool,
        results: list[dict[str, Any]],
    ) -> bool | None:
        """Apply a delete operation.

        Returns ``True`` on success, ``None`` on trash failure
        (caller should count as failure and possibly stop).
        """
        if not src_path.exists():
            raise _OpError(f"Source does not exist: {src_path}")

        if dry_run:
            delete_mode = "hard" if hard_delete_enabled else "trash"
            results.append({
                "index": operation_index,
                "op": "delete",
                "ok": True,
                "dry_run": True,
                "src": str(src_path),
                "delete_mode": delete_mode,
                "is_dir": src_path.is_dir(),
            })
            return True

        if hard_delete_enabled:
            if src_path.is_symlink():
                src_path.unlink()
            elif src_path.is_dir():
                shutil.rmtree(src_path)
            else:
                src_path.unlink()

            verification_error = (
                self._verify_apply_result(
                    op_kind="delete",
                    src_path=src_path,
                    dest_path=None,
                )
                if verify_after
                else None
            )
            if verification_error:
                raise _OpError(
                    f"{verification_error} "
                    f"(Note: the delete of '{src_path}' was already executed.)"
                )

            results.append({
                "index": operation_index,
                "op": "delete",
                "ok": True,
                "src": str(src_path),
                "delete_mode": "hard",
                "hard_delete_env_var": _HARD_DELETE_ENV_VAR,
            })
            return True

        # Soft delete (trash).
        try:
            trashed_path = self._move_path_to_trash(src_path)
            verification_error = (
                self._verify_apply_result(
                    op_kind="delete",
                    src_path=src_path,
                    dest_path=None,
                )
                if verify_after
                else None
            )
            if verification_error:
                raise _OpError(
                    f"{verification_error} "
                    f"(Note: the delete of '{src_path}' was already executed.)"
                )
            results.append({
                "index": operation_index,
                "op": "delete",
                "ok": True,
                "src": str(src_path),
                "delete_mode": "trash",
                "trash_path": str(trashed_path),
                "hard_delete_env_var": _HARD_DELETE_ENV_VAR,
            })
            return True

        except (PermissionError, OSError) as trash_exc:
            # Safety: do NOT silently fall back to hard delete.
            results.append({
                "index": operation_index,
                "op": "delete",
                "ok": False,
                "src": str(src_path),
                "error": (
                    f"Trash failed: {trash_exc}. "
                    f"Set {_HARD_DELETE_ENV_VAR}=true to enable "
                    f"permanent deletion."
                ),
            })
            return None


# ---------------------------------------------------------------------------
# Internal exception for op-level errors (never crosses plugin boundary)
# ---------------------------------------------------------------------------


class _OpError(Exception):
    """Operation-level error raised inside per-op helpers.

    Caught at the plugin boundary and converted to result entries.
    Mirrors ``ToolExecutionError`` attributes for error reporting.
    """

    def __init__(
        self,
        message: str,
        *,
        error_type: str = "internal",
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.retryable = retryable
