"""Tool plugin: open_item.

Opens a file or directory using the macOS ``open`` command, optionally
targeting a whitelisted application.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Mapping, Sequence

from agent_host.adapters.tools._path_security import normalize_user_path
from agent_host.contracts.types.errors import AgentError, ErrorCode
from agent_host.contracts.types.result import Failure, Result, Success


class OpenItemPlugin:
    """Self-contained plugin for the ``open_item`` tool."""

    _APP_WHITELIST: frozenset[str] = frozenset({
        "textedit",
        "preview",
        "finder",
        "safari",
        "xcode",
        "visual studio code",
        "sublime text",
        "quicktime player",
        "pages",
        "numbers",
        "keynote",
        "music",
        "photos",
        "calendar",
        "reminders",
        "mail",
    })

    def __init__(
        self,
        *,
        allowed_roots: Sequence[Path],
        enable: bool = False,
    ) -> None:
        self._allowed_roots: list[Path] = [
            root.expanduser().resolve(strict=False) for root in allowed_roots
        ]
        self._enable = enable

    # ------------------------------------------------------------------
    # ToolPlugin protocol
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "open_item"

    @property
    def description(self) -> str:
        return "Open a file or directory using the macOS open command"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or user-relative path to open",
                },
                "application": {
                    "type": "string",
                    "description": (
                        "Optional application name to open the item with "
                        "(must be in the whitelist)"
                    ),
                },
            },
            "required": ["path"],
        }

    def execute(self, arguments: Mapping[str, Any]) -> Result[dict[str, Any]]:
        """Open the item, returning Success or Failure."""
        try:
            return self._execute_inner(arguments)
        except Exception as exc:
            return Failure(AgentError(
                code=ErrorCode.INTERNAL,
                message=f"Unexpected error in open_item: {exc}",
                source="open_item",
            ))

    def health_check(self) -> Result[bool]:
        return Success(True)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _execute_inner(self, arguments: Mapping[str, Any]) -> Result[dict[str, Any]]:
        # --- feature gate ---
        if not self._enable:
            return Failure(AgentError(
                code=ErrorCode.PERMISSION,
                message="open_item is disabled by configuration",
                source="open_item",
            ))

        # --- path ---
        path_raw = str(arguments.get("path", "")).strip()
        if not path_raw:
            return Failure(AgentError(
                code=ErrorCode.VALIDATION,
                message="open_item requires a non-empty 'path'",
                source="open_item",
            ))

        path_result = normalize_user_path(
            path_raw,
            allowed_roots=self._allowed_roots,
            must_exist=True,
        )
        if not path_result.is_ok:
            return path_result  # type: ignore[return-value]

        path: Path = path_result.unwrap()

        # --- application whitelist ---
        application_raw = arguments.get("application")
        command: list[str] = ["open"]
        app_used: str | None = None

        if isinstance(application_raw, str) and application_raw.strip():
            app_name = application_raw.strip()
            if app_name.lower() not in self._APP_WHITELIST:
                allowed = ", ".join(sorted(self._APP_WHITELIST))
                return Failure(AgentError(
                    code=ErrorCode.VALIDATION,
                    message=(
                        f"Application '{app_name}' is not in the allowed list. "
                        f"Allowed applications: {allowed}"
                    ),
                    source="open_item",
                ))
            command.extend(["-a", app_name])
            app_used = app_name

        command.append(str(path))

        # --- execute ---
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return Failure(AgentError(
                code=ErrorCode.TIMEOUT,
                message=f"open_item timed out for '{path}' after 10 seconds",
                source="open_item",
                retryable=True,
            ))
        except OSError as exc:
            return Failure(AgentError(
                code=ErrorCode.INTERNAL,
                message=f"open_item failed to start: {exc}",
                source="open_item",
            ))

        if completed.returncode != 0:
            message = (
                completed.stderr.strip()
                or completed.stdout.strip()
                or "open command failed"
            )
            return Failure(AgentError(
                code=ErrorCode.INTERNAL,
                message=message,
                source="open_item",
            ))

        result: dict[str, Any] = {
            "ok": True,
            "path": str(path),
            "launched": True,
        }
        if app_used:
            result["application"] = app_used
        return Success(result)
