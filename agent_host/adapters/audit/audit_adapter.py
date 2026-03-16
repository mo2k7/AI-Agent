"""Adapter wrapping AuditLogger to satisfy the AuditPort protocol.

Thin delegation layer — all calls forwarded to the underlying logger.
Defensive error boundaries ensure that only domain exceptions (AuditLogError)
pass through; everything else is wrapped in AdapterError.
"""

from __future__ import annotations

import logging
from typing import Any

from agent_host.contracts.types.errors import AdapterError
from agent_host.audit_logger import AuditLogError

logger = logging.getLogger(__name__)

_PASSTHROUGH = (AuditLogError,)


class AuditAdapter:
    """Wraps ``AuditLogger`` to satisfy ``AuditPort`` protocol."""

    def __init__(self, logger_instance: Any) -> None:
        self._logger = logger_instance

    def log_event(
        self,
        event_type: str,
        data: dict[str, Any],
    ) -> None:
        try:
            self._logger.log_event(event_type, data)
        except _PASSTHROUGH:
            raise
        except Exception as exc:
            logger.error("AuditAdapter.log_event failed: %s", exc)
            raise AdapterError(
                f"audit.log_event failed: {exc}",
                source="audit",
                cause=exc,
            ) from exc

    def log_error(
        self,
        error_type: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        try:
            self._logger.log_error(error_type, message, details)
        except _PASSTHROUGH:
            raise
        except Exception as exc:
            logger.error("AuditAdapter.log_error failed: %s", exc)
            raise AdapterError(
                f"audit.log_error failed: {exc}",
                source="audit",
                cause=exc,
            ) from exc
