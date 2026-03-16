"""Shared path normalization and security utilities for tool plugins.

Extracted from ``ToolExecutor._normalize_user_path`` to enable
self-contained tool plugins without coupling to the executor.

This module lives in the adapter layer because it performs filesystem
I/O (``Path.resolve()``, ``Path.stat()``).
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any, Sequence

from agent_host.contracts.types.errors import AgentError, ErrorCode
from agent_host.contracts.types.result import Failure, Result, Success


def normalize_user_path(
    raw_path: str,
    *,
    allowed_roots: Sequence[Path],
    must_exist: bool,
    operate_on_symlink_path: bool = False,
    check_target_root: bool = True,
) -> Result[Path]:
    """Normalize and security-validate a user-provided path.

    Mirrors the logic of ``ToolExecutor._normalize_user_path`` but as a
    standalone function that receives ``allowed_roots`` explicitly.

    Returns ``Success(normalized_path)`` or ``Failure(AgentError)``
    depending on validation outcome.
    """
    if not raw_path.strip():
        return Failure(AgentError(
            ErrorCode.VALIDATION, "Path cannot be empty",
            source="path_security",
        ))
    if "\x00" in raw_path:
        return Failure(AgentError(
            ErrorCode.VALIDATION, "Path contains invalid null byte",
            source="path_security",
        ))
    try:
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        resolved = candidate.resolve(strict=must_exist)
    except (OSError, RuntimeError, ValueError) as exc:
        return Failure(AgentError(
            ErrorCode.VALIDATION, f"Invalid path '{raw_path}': {exc}",
            source="path_security",
        ))

    # Check resolved target is within allowed roots.
    if check_target_root:
        if not path_within_roots(resolved, allowed_roots):
            roots_str = ", ".join(str(r) for r in allowed_roots)
            return Failure(AgentError(
                ErrorCode.PERMISSION,
                f"Path '{resolved}' is outside allowed roots: {roots_str}",
                source="path_security",
            ))

    # Lexical path for the link itself.
    lexical_path = Path(os.path.normpath(candidate))
    if not check_target_root:
        if not path_within_roots(lexical_path, allowed_roots):
            return Failure(AgentError(
                ErrorCode.PERMISSION,
                f"Path '{lexical_path}' is outside allowed roots",
                source="path_security",
            ))
        # Verify PARENT directory is safe (prevents symlink-parent traversal).
        try:
            parent_resolved = lexical_path.parent.resolve(strict=must_exist)
            if not path_within_roots(parent_resolved, allowed_roots):
                return Failure(AgentError(
                    ErrorCode.PERMISSION,
                    f"Path parent '{parent_resolved}' resolves outside allowed roots",
                    source="path_security",
                ))
        except (OSError, RuntimeError, ValueError) as exc:
            if must_exist:
                return Failure(AgentError(
                    ErrorCode.VALIDATION,
                    f"Could not resolve parent of '{raw_path}': {exc}",
                    source="path_security",
                ))

    # Symlink TOCTOU mitigation.
    if operate_on_symlink_path and candidate.is_symlink():
        link_target = candidate.resolve(strict=False)
        if check_target_root and not path_within_roots(link_target, allowed_roots):
            return Failure(AgentError(
                ErrorCode.PERMISSION,
                f"Symlink '{candidate}' resolves to '{link_target}' "
                f"which is outside allowed roots",
                source="path_security",
            ))

    return Success(lexical_path)


def path_within_roots(path: Path, allowed_roots: Sequence[Path]) -> bool:
    """Check if a resolved path falls within any of the allowed roots."""
    for root in allowed_roots:
        if path == root or root in path.parents:
            return True
    return False


def serialize_stat(path: Path) -> dict[str, Any]:
    """Return stat metadata dict for a path."""
    data = path.stat()
    mode = stat.S_IMODE(data.st_mode)
    return {
        "path": str(path),
        "exists": True,
        "is_file": path.is_file(),
        "is_dir": path.is_dir(),
        "size_bytes": int(data.st_size),
        "permissions_octal": oct(mode),
        "created_at": float(data.st_ctime),
        "modified_at": float(data.st_mtime),
    }
