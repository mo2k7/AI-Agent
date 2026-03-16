"""JSONL audit logging for tracking agent operations.

This module provides audit logging functionality that records all
tool calls, errors, and validation failures to a JSONL file for
debugging, compliance, and security review purposes.

Encrypted mode (opt-in via ``encrypt=True`` or ``AI_AGENT_AUDIT_ENCRYPT=true``)
encrypts each JSONL line with AES-256-GCM using the Keychain master key before
writing to disk.
"""

import json
import logging
import os
import hashlib
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional

from agent_host.redaction import redact_value

logger = logging.getLogger(__name__)


# Canonical definition in contracts/types/errors.py; re-exported for backward compat.
from agent_host.contracts.types.errors import AuditLogError  # noqa: F401


class EventType(str, Enum):
    """Types of events that can be logged."""
    
    TOOL_CALL = "TOOL_CALL"
    ERROR = "ERROR"
    VALIDATION_FAIL = "VALIDATION_FAIL"
    API_REQUEST = "API_REQUEST"
    API_RESPONSE = "API_RESPONSE"
    TOOL_RESULT = "TOOL_RESULT"
    STARTUP = "STARTUP"
    SHUTDOWN = "SHUTDOWN"
    
    def __str__(self) -> str:
        return self.value


class AuditLogger:
    """JSONL audit logger for agent operations.
    
    Records events to a JSONL (JSON Lines) file where each line is
    a complete JSON object. This format is ideal for append-only logs
    and easy parsing.
    
    Attributes:
        log_path: Path to the JSONL audit log file.
    
    Example:
        >>> logger = AuditLogger(Path("~/.local/share/ai-agent/audit.log"))
        >>> logger.log_event(EventType.TOOL_CALL, {"tool": "search_files", "args": {}})
    """
    
    _AUDIT_AAD = b"audit-log-entry"
    _INTEGRITY_VERSION = "sha256-chain-v1"

    def __init__(
        self, log_path: Path, *, encrypt: bool | None = None
    ) -> None:
        """Initialize the audit logger.

        Creates the log directory if it doesn't exist.

        Args:
            log_path: Path to the JSONL log file.
            encrypt: Encrypt log lines at rest. ``None`` reads from
                ``AI_AGENT_AUDIT_ENCRYPT`` env var. ``True`` raises
                ``KeychainError`` if the master key is unavailable.

        Raises:
            AuditLogError: If the log directory cannot be created.
            KeychainError: If ``encrypt=True`` but Keychain access fails.
        """
        self.log_path = Path(log_path).expanduser()
        self._ensure_directory()

        if encrypt is None:
            encrypt = os.environ.get(
                "AI_AGENT_AUDIT_ENCRYPT", ""
            ).strip().lower() in {"1", "true", "yes", "on"}

        self._crypto_box = None
        if encrypt:
            from agent_host.memory.keychain import get_or_create_master_key
            from agent_host.memory.crypto import CryptoBox
            master = get_or_create_master_key()
            self._crypto_box = CryptoBox(master.raw)

        self.rotate_log()
        self._last_entry_hash = self._load_last_entry_hash()
        retention_days = self._resolve_retention_days()
        if retention_days > 0:
            self.prune_older_than(days=retention_days)
    
    def _ensure_directory(self) -> None:
        """Ensure the log directory exists.
        
        Creates the directory with appropriate permissions if needed.
        
        Raises:
            AuditLogError: If directory creation fails.
        """
        try:
            log_dir = self.log_path.parent
            if not log_dir.exists():
                log_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
                logger.info(f"Created audit log directory: {log_dir}")
            else:
                # Enforce least-privilege permissions for audit data.
                log_dir.chmod(0o700)
        except OSError as e:
            raise AuditLogError(f"Failed to create log directory: {e}") from e
    
    def log_event(
        self,
        event_type: EventType | str,
        data: Dict[str, Any],
        timestamp: Optional[datetime] = None,
    ) -> None:
        """Append an event to the audit log.
        
        Writes a single JSON object as a line in the JSONL file.
        Each event includes a timestamp, event type, and associated data.
        
        Args:
            event_type: Type of event (EventType enum or string).
            data: Dictionary of event data to log.
            timestamp: Optional timestamp (defaults to current UTC time).
        
        Raises:
            AuditLogError: If writing to the log file fails.
        
        Example:
            >>> logger.log_event(
            ...     EventType.TOOL_CALL,
            ...     {"tool": "search_files", "args": {"query": "python"}}
            ... )
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        
        # Convert EventType enum to string
        event_type_str = str(event_type) if isinstance(event_type, EventType) else event_type
        
        event = {
            "timestamp": timestamp.isoformat(),
            "event": event_type_str,
            "data": redact_value(data),
        }
        payload_for_hash = json.dumps(event, default=self._json_serializer, sort_keys=True)
        prev_hash = self._last_entry_hash
        entry_hash = hashlib.sha256(
            (prev_hash + "|" + payload_for_hash).encode("utf-8")
        ).hexdigest()
        event["integrity"] = {
            "version": self._INTEGRITY_VERSION,
            "prev_hash": prev_hash,
            "entry_hash": entry_hash,
        }

        try:
            line = json.dumps(event, default=self._json_serializer)
            if self._crypto_box is not None:
                line = self._crypto_box.encrypt_text(line, aad=self._AUDIT_AAD)
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(line)
                f.write("\n")
            # Enforce least-privilege file permissions for on-disk audit data.
            self.log_path.chmod(0o600)
            self._last_entry_hash = entry_hash
        except OSError as e:
            raise AuditLogError(f"Failed to write to audit log: {e}") from e
        except TypeError as e:
            raise AuditLogError(f"Failed to serialize event data: {e}") from e
        
        logger.debug(f"Logged event: {event_type_str}")
    
    def log_tool_call(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        user_prompt: Optional[str] = None,
        validated: bool = True,
    ) -> None:
        """Log a tool call event.
        
        Convenience method for logging TOOL_CALL events with
        commonly needed fields.
        
        Args:
            tool_name: Name of the tool being called.
            arguments: Arguments passed to the tool.
            user_prompt: Optional original user prompt.
            validated: Whether the arguments were validated.
        
        Example:
            >>> logger.log_tool_call(
            ...     "search_files",
            ...     {"query": "python"},
            ...     user_prompt="Find my Python files"
            ... )
        """
        data: Dict[str, Any] = {
            "tool": tool_name,
            "arguments": arguments,
            "validated": validated,
        }
        if user_prompt is not None:
            data["prompt"] = user_prompt
        
        self.log_event(EventType.TOOL_CALL, data)
    
    def log_error(
        self,
        error_type: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log an error event.
        
        Convenience method for logging ERROR events.
        
        Args:
            error_type: Type/category of the error.
            message: Error message.
            details: Optional additional error details.
        
        Example:
            >>> logger.log_error(
            ...     "API_ERROR",
            ...     "Rate limit exceeded",
            ...     {"status_code": 429}
            ... )
        """
        data: Dict[str, Any] = {
            "error_type": error_type,
            "message": message,
        }
        if details is not None:
            data["details"] = details
        
        self.log_event(EventType.ERROR, data)
    
    def log_validation_fail(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        errors: list[str],
    ) -> None:
        """Log a validation failure event.
        
        Convenience method for logging VALIDATION_FAIL events.
        
        Args:
            tool_name: Name of the tool with invalid arguments.
            arguments: The invalid arguments.
            errors: List of validation error messages.
        
        Example:
            >>> logger.log_validation_fail(
            ...     "search_files",
            ...     {},
            ...     ["'query' is a required property"]
            ... )
        """
        data = {
            "tool": tool_name,
            "arguments": arguments,
            "errors": errors,
        }
        self.log_event(EventType.VALIDATION_FAIL, data)
    
    def _json_serializer(self, obj: Any) -> Any:
        """Custom JSON serializer for complex objects.
        
        Handles serialization of objects that json.dump doesn't
        support by default.
        
        Args:
            obj: Object to serialize.
        
        Returns:
            JSON-serializable representation.
        
        Raises:
            TypeError: If object cannot be serialized.
        """
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, Path):
            return str(obj)
        if isinstance(obj, bytes):
            return obj.decode("utf-8", errors="replace")
        if hasattr(obj, "__dict__"):
            return obj.__dict__
        if hasattr(obj, "to_dict"):
            return obj.to_dict()
        
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
    
    def read_events(
        self,
        event_type: Optional[EventType | str] = None,
        limit: Optional[int] = None,
    ) -> list[Dict[str, Any]]:
        """Read events from the audit log.
        
        Parses the JSONL file and returns events, optionally filtered
        by type and limited to a certain count.
        
        Args:
            event_type: Optional filter by event type.
            limit: Optional maximum number of events to return.
        
        Returns:
            List of event dictionaries.
        
        Example:
            >>> events = logger.read_events(EventType.TOOL_CALL, limit=10)
            >>> print(len(events))
            10
        """
        events: list[Dict[str, Any]] = []
        
        if not self.log_path.exists():
            return events
        
        event_type_str = str(event_type) if event_type else None
        
        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        if self._crypto_box is not None:
                            line = self._crypto_box.decrypt_text(line, aad=self._AUDIT_AAD)
                        event = json.loads(line)

                        # Apply filter
                        if event_type_str and event.get("event") != event_type_str:
                            continue

                        events.append(event)

                        # Apply limit
                        if limit and len(events) >= limit:
                            break
                    except json.JSONDecodeError:
                        logger.warning(f"Skipping malformed log line: {line[:50]}...")
                    except Exception as exc:
                        logger.warning("Skipping undecryptable log line: %s", exc)
        except OSError as e:
            logger.error(f"Failed to read audit log: {e}")
        
        return events

    def verify_integrity_chain(self) -> tuple[bool, str]:
        """Verify append-only hash-chain integrity for audit events."""
        events = self.read_events()
        prev_hash = ""
        for index, event in enumerate(events, start=1):
            integrity = event.get("integrity", {})
            if not isinstance(integrity, dict):
                return False, f"Missing integrity payload at event #{index}."
            if integrity.get("version") != self._INTEGRITY_VERSION:
                return False, f"Unexpected integrity version at event #{index}."
            if integrity.get("prev_hash", "") != prev_hash:
                return False, f"Hash-chain mismatch at event #{index}."
            event_copy = {
                "timestamp": event.get("timestamp"),
                "event": event.get("event"),
                "data": event.get("data"),
            }
            payload_for_hash = json.dumps(event_copy, default=self._json_serializer, sort_keys=True)
            expected = hashlib.sha256((prev_hash + "|" + payload_for_hash).encode("utf-8")).hexdigest()
            if integrity.get("entry_hash") != expected:
                return False, f"Entry hash mismatch at event #{index}."
            prev_hash = expected
        return True, "ok"

    def prune_older_than(self, *, days: int) -> int:
        """Remove audit events older than the retention window."""
        if days <= 0 or not self.log_path.exists():
            return 0
        threshold = datetime.now(timezone.utc) - timedelta(days=days)
        kept_lines: list[str] = []
        removed = 0
        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                for raw_line in f:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        decoded = (
                            self._crypto_box.decrypt_text(line, aad=self._AUDIT_AAD)
                            if self._crypto_box is not None
                            else line
                        )
                        payload = json.loads(decoded)
                        timestamp_raw = payload.get("timestamp")
                        if timestamp_raw:
                            event_time = datetime.fromisoformat(
                                str(timestamp_raw).replace("Z", "+00:00")
                            )
                            if event_time.tzinfo is None:
                                event_time = event_time.replace(tzinfo=timezone.utc)
                            if event_time < threshold:
                                removed += 1
                                continue
                    except Exception:
                        # Preserve malformed lines for forensic review.
                        pass
                    kept_lines.append(raw_line)
            if removed:
                with open(self.log_path, "w", encoding="utf-8") as f:
                    f.writelines(kept_lines)
                self.log_path.chmod(0o600)
                self._last_entry_hash = self._load_last_entry_hash()
        except OSError as exc:
            logger.warning("Failed pruning audit log retention window: %s", exc)
            return 0
        return removed
    
    def get_log_size(self) -> int:
        """Get the size of the audit log file in bytes.
        
        Returns:
            Size in bytes, or 0 if file doesn't exist.
        """
        if not self.log_path.exists():
            return 0
        return self.log_path.stat().st_size
    
    def rotate_log(
        self,
        max_size_bytes: int = 10 * 1024 * 1024,  # 10 MB default
    ) -> Optional[Path]:
        """Rotate the log file if it exceeds the maximum size.
        
        Renames the current log file with a timestamp suffix and
        creates a new empty log file.
        
        Args:
            max_size_bytes: Maximum file size before rotation.
        
        Returns:
            Path to the rotated file if rotation occurred, None otherwise.
        """
        if self.get_log_size() < max_size_bytes:
            return None
        
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        rotated_path = self.log_path.with_suffix(f".{timestamp}.jsonl")
        
        try:
            self.log_path.rename(rotated_path)
            logger.info(f"Rotated audit log to: {rotated_path}")
            return rotated_path
        except OSError as e:
            logger.error(f"Failed to rotate log: {e}")
            return None

    def _load_last_entry_hash(self) -> str:
        if not self.log_path.exists():
            return ""
        last_hash = ""
        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        decoded = (
                            self._crypto_box.decrypt_text(line, aad=self._AUDIT_AAD)
                            if self._crypto_box is not None
                            else line
                        )
                        payload = json.loads(decoded)
                        integrity = payload.get("integrity", {})
                        if isinstance(integrity, dict):
                            last_hash = str(integrity.get("entry_hash", "")) or last_hash
                    except Exception:
                        continue
        except OSError:
            return ""
        return last_hash

    def _resolve_retention_days(self) -> int:
        raw_env = os.environ.get("AI_AGENT_AUDIT_RETENTION_DAYS")
        if raw_env:
            try:
                return int(raw_env)
            except ValueError:
                logger.warning("Invalid AI_AGENT_AUDIT_RETENTION_DAYS=%r; falling back.", raw_env)
        # Best effort: align with browse compliance retention policy when present.
        policy_path = (
            Path(__file__).resolve().parent
            / "tools"
            / "data"
            / "browse_compliance_policy.json"
        )
        try:
            with open(policy_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            retention = payload.get("retention", {})
            return int(retention.get("audit_retention_days", 30))
        except Exception:
            return 30
