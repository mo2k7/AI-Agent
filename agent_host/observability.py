"""Structured logging and request-context helpers."""

from __future__ import annotations

import contextvars
import json
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from agent_host.redaction import redact_value

_correlation_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "ai_agent_correlation_id",
    default=None,
)
_request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "ai_agent_request_id",
    default=None,
)
_method_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "ai_agent_method",
    default=None,
)


@dataclass(frozen=True)
class RequestContextTokens:
    correlation_token: contextvars.Token[str | None]
    request_token: contextvars.Token[str | None]
    method_token: contextvars.Token[str | None]


def generate_correlation_id() -> str:
    return str(uuid.uuid4())


def set_request_context(
    *,
    correlation_id: str | None,
    request_id: str | None,
    method: str | None,
) -> RequestContextTokens:
    return RequestContextTokens(
        correlation_token=_correlation_id_var.set(correlation_id),
        request_token=_request_id_var.set(request_id),
        method_token=_method_var.set(method),
    )


def reset_request_context(tokens: RequestContextTokens) -> None:
    _correlation_id_var.reset(tokens.correlation_token)
    _request_id_var.reset(tokens.request_token)
    _method_var.reset(tokens.method_token)


def get_request_context() -> dict[str, str | None]:
    return {
        "correlation_id": _correlation_id_var.get(),
        "request_id": _request_id_var.get(),
        "method": _method_var.get(),
    }


class RequestContextFilter(logging.Filter):
    """Inject request context fields into each LogRecord."""

    def filter(self, record: logging.LogRecord) -> bool:
        context = get_request_context()
        if getattr(record, "correlation_id", None) is None:
            setattr(record, "correlation_id", context["correlation_id"])
        if getattr(record, "request_id", None) is None:
            setattr(record, "request_id", context["request_id"])
        if getattr(record, "method", None) is None:
            setattr(record, "method", context["method"])
        if getattr(record, "component", None) is None:
            setattr(record, "component", record.name)
        return True


class JsonLineFormatter(logging.Formatter):
    """Format log records as redacted JSON lines."""

    _RESERVED = {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
    }

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()
        payload: dict[str, Any] = {
            "timestamp": timestamp,
            "level": record.levelname,
            "component": getattr(record, "component", record.name),
            "correlation_id": getattr(record, "correlation_id", None),
            "request_id": getattr(record, "request_id", None),
            "method": getattr(record, "method", None),
            "duration_ms": getattr(record, "duration_ms", None),
            "error_type": getattr(record, "error_type", None),
            "error_message": getattr(record, "error_message", None),
            "message": record.getMessage(),
        }

        if record.exc_info:
            exc_type = record.exc_info[0].__name__ if record.exc_info[0] else "Exception"
            payload["error_type"] = payload["error_type"] or exc_type
            payload["error_message"] = payload["error_message"] or self.formatException(record.exc_info)

        extras: dict[str, Any] = {}
        for key, value in record.__dict__.items():
            if key in self._RESERVED:
                continue
            if key in payload:
                continue
            extras[key] = value
        if extras:
            payload["extra"] = extras

        return json.dumps(redact_value(payload), ensure_ascii=False, separators=(",", ":"))


def is_json_logging_enabled() -> bool:
    return os.environ.get("AI_AGENT_DEBUG_JSON_LOGS", "0").strip() == "1"


def configure_logging(*, verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)

    handler = logging.StreamHandler()
    if is_json_logging_enabled():
        handler.setFormatter(JsonLineFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
    context_filter = RequestContextFilter()
    handler.addFilter(context_filter)
    root.addHandler(handler)
