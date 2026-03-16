"""Tool plugin: create_directory.

Creates a directory at the specified path, optionally accepting
``exist_ok`` to silently succeed when the directory already exists.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from agent_host.adapters.tools._path_security import normalize_user_path
from agent_host.contracts.types.errors import AgentError, ErrorCode
from agent_host.contracts.types.result import Failure, Result, Success


class CreateDirectoryPlugin:
    """Self-contained plugin for the ``create_directory`` tool."""

    def __init__(self, *, allowed_roots: Sequence[Path]) -> None:
        self._allowed_roots: list[Path] = [
            root.expanduser().resolve(strict=False) for root in allowed_roots
        ]

    # ------------------------------------------------------------------
    # ToolPlugin protocol
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "create_directory"

    @property
    def description(self) -> str:
        return "Create a directory at the specified path"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or user-relative path for the new directory",
                },
                "exist_ok": {
                    "type": "boolean",
                    "description": (
                        "If true (default), silently succeed when the directory "
                        "already exists. If false, fail when it already exists."
                    ),
                },
            },
            "required": ["path"],
        }

    def execute(self, arguments: Mapping[str, Any]) -> Result[dict[str, Any]]:
        """Create the directory, returning Success or Failure."""
        try:
            return self._execute_inner(arguments)
        except Exception as exc:
            return Failure(AgentError(
                code=ErrorCode.INTERNAL,
                message=f"Unexpected error in create_directory: {exc}",
                source="create_directory",
            ))

    def health_check(self) -> Result[bool]:
        return Success(True)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _execute_inner(self, arguments: Mapping[str, Any]) -> Result[dict[str, Any]]:
        # --- path ---
        path_raw = str(arguments.get("path", "")).strip()
        if not path_raw:
            return Failure(AgentError(
                code=ErrorCode.VALIDATION,
                message="create_directory requires a non-empty 'path'",
                source="create_directory",
            ))

        # --- exist_ok ---
        exist_ok_raw = arguments.get("exist_ok", True)
        exist_ok = self._parse_bool(exist_ok_raw)
        if exist_ok is None:
            return Failure(AgentError(
                code=ErrorCode.VALIDATION,
                message="create_directory 'exist_ok' must be a boolean",
                source="create_directory",
            ))

        # --- normalize & security-check path ---
        path_result = normalize_user_path(
            path_raw,
            allowed_roots=self._allowed_roots,
            must_exist=False,
        )
        if not path_result.is_ok:
            return path_result  # type: ignore[return-value]

        path: Path = path_result.unwrap()

        # --- pre-existence checks ---
        already_existed = path.exists()
        if already_existed and not exist_ok:
            return Failure(AgentError(
                code=ErrorCode.VALIDATION,
                message=f"Directory already exists: {path}",
                source="create_directory",
            ))
        if already_existed and not path.is_dir():
            return Failure(AgentError(
                code=ErrorCode.VALIDATION,
                message=f"Path exists but is not a directory: {path}",
                source="create_directory",
            ))

        # --- create ---
        try:
            path.mkdir(parents=True, exist_ok=exist_ok)
        except OSError as exc:
            return Failure(AgentError(
                code=ErrorCode.INTERNAL,
                message=f"Failed to create directory '{path}': {exc}",
                source="create_directory",
            ))

        return Success({
            "ok": True,
            "path": str(path),
            "created": not already_existed,
            "already_existed": already_existed,
        })

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_bool(value: Any) -> bool | None:
        """Parse a bool-ish value. Returns ``None`` on invalid input."""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
        return None
