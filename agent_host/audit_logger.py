"""JSONL audit logging for tracking agent operations.

This module provides audit logging functionality that records all
tool calls, errors, and validation failures to a JSONL file for
debugging, compliance, and security review purposes.
"""

import json
import logging
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional

from agent_host.redaction import redact_value

logger = logging.getLogger(__name__)


class AuditLogError(Exception):
    """Raised when audit logging fails."""
    pass


class EventType(str, Enum):
    """Types of events that can be logged."""
    
    TOOL_CALL = "TOOL_CALL"
    ERROR = "ERROR"
    VALIDATION_FAIL = "VALIDATION_FAIL"
    API_REQUEST = "API_REQUEST"
    API_RESPONSE = "API_RESPONSE"
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
    
    def __init__(self, log_path: Path) -> None:
        """Initialize the audit logger.
        
        Creates the log directory if it doesn't exist.
        
        Args:
            log_path: Path to the JSONL log file.
        
        Raises:
            AuditLogError: If the log directory cannot be created.
        """
        self.log_path = Path(log_path).expanduser()
        self._ensure_directory()
    
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
        
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                json.dump(event, f, default=self._json_serializer)
                f.write("\n")
            # Enforce least-privilege file permissions for on-disk audit data.
            self.log_path.chmod(0o600)
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
        except OSError as e:
            logger.error(f"Failed to read audit log: {e}")
        
        return events
    
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
