"""Error codes and structured error types for the agent system.

Provides a machine-readable error hierarchy that replaces string-based
error messages at architectural boundaries.  All domain exception classes
are defined here so that core/ can import them without depending on
infrastructure modules.

Original source modules re-export these for backward compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, List


class ErrorCode(str, Enum):
    """Machine-readable error categories."""

    VALIDATION = "validation"
    NOT_FOUND = "not_found"
    PERMISSION = "permission"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    CONFIGURATION = "configuration"
    DEPENDENCY = "dependency"
    INTERNAL = "internal"
    CANCELLED = "cancelled"
    TRANSIENT = "transient"


class ErrorSeverity(str, Enum):
    """How serious the error is."""

    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class AgentError:
    """Structured error for cross-boundary error reporting.

    Attributes:
        code: Machine-readable error category.
        message: Human-readable explanation.
        source: Which module/adapter generated the error.
        retryable: Whether the caller should retry.
        severity: How serious the error is.
        context: Optional debugging data.
    """

    code: ErrorCode
    message: str
    source: str = ""
    retryable: bool = False
    severity: ErrorSeverity = ErrorSeverity.ERROR
    context: dict[str, Any] = field(default_factory=dict)

    def with_context(self, **kwargs: Any) -> AgentError:
        """Return a copy with additional context."""
        merged = {**self.context, **kwargs}
        return AgentError(
            code=self.code,
            message=self.message,
            source=self.source,
            retryable=self.retryable,
            severity=self.severity,
            context=merged,
        )


class AdapterError(Exception):
    """Raised when an adapter catches an unexpected (non-domain) exception.

    This prevents raw framework exceptions (``sqlite3.OperationalError``,
    ``google.api_core.exceptions.GoogleAPIError``, etc.) from leaking
    across architectural boundaries.

    Domain exceptions (``GeminiAPIError``, ``MemoryStoreError``, etc.)
    are NOT wrapped -- they pass through unchanged because callers
    depend on them for flow control.
    """

    def __init__(self, message: str, *, source: str = "", cause: BaseException | None = None):
        super().__init__(message)
        self.source = source
        self.cause = cause


# ---------------------------------------------------------------------------
# Tool execution errors (canonical: tools/executor.py)
# ---------------------------------------------------------------------------


class ToolExecutionError(RuntimeError):
    """Raised when a tool call cannot be executed safely.

    Attributes:
        error_type: Categorised error kind for structured reporting.
            Common values: ``"validation"``, ``"not_found"``, ``"permission"``,
            ``"timeout"``, ``"dependency"``, ``"internal"``.
        retryable: Hint for the caller -- ``True`` when the error may be
            transient (e.g. a timeout or temporary lock).
    """

    def __init__(
        self,
        message: str,
        *,
        error_type: str = "internal",
        retryable: bool = False,
    ):
        super().__init__(message)
        self.error_type = error_type
        self.retryable = retryable


# ---------------------------------------------------------------------------
# Memory store errors (canonical: memory/store.py)
# ---------------------------------------------------------------------------


class MemoryStoreError(RuntimeError):
    """Raised for storage-layer failures."""


# ---------------------------------------------------------------------------
# Gemini client errors (canonical: gemini_client.py)
# ---------------------------------------------------------------------------


class GeminiClientError(Exception):
    """Base exception for Gemini client errors."""
    pass


class GeminiAPIError(GeminiClientError):
    """Raised when the Gemini API returns an error."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class GeminiRateLimitError(GeminiAPIError):
    """Raised when rate limited (HTTP 429)."""
    pass


class GeminiServerError(GeminiAPIError):
    """Raised when server error occurs (HTTP 5xx)."""
    pass


# ---------------------------------------------------------------------------
# Schema validator errors (canonical: schema_validator.py)
# ---------------------------------------------------------------------------


class SchemaValidatorError(Exception):
    """Base exception for schema validator errors."""
    pass


class SchemaLoadError(SchemaValidatorError):
    """Raised when a schema cannot be loaded."""
    pass


class SchemaNotFoundError(SchemaValidatorError):
    """Raised when a requested schema does not exist."""
    pass


class ValidationFailedError(SchemaValidatorError):
    """Raised when validation fails."""

    def __init__(self, message: str, errors: Optional[List[str]] = None):
        super().__init__(message)
        self.errors = errors or []


# ---------------------------------------------------------------------------
# Tool parser errors (canonical: tool_parser.py)
# ---------------------------------------------------------------------------


class ToolParserError(Exception):
    """Base exception for tool parser errors."""
    pass


class MalformedResponseError(ToolParserError):
    """Raised when response structure is malformed."""
    pass


# ---------------------------------------------------------------------------
# System prompt errors (canonical: system_prompt.py)
# ---------------------------------------------------------------------------


class SystemPromptLoadError(RuntimeError):
    """Raised when the system prompt cannot be loaded safely."""


# ---------------------------------------------------------------------------
# Audit logger errors (canonical: audit_logger.py)
# ---------------------------------------------------------------------------


class AuditLogError(Exception):
    """Raised when audit logging fails."""
    pass
