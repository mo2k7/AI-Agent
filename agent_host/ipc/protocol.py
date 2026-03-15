"""
IPC Protocol definitions for communication with SwiftUI frontend.

Uses JSON-RPC 2.0 inspired message format over WebSocket transport.
Each WebSocket frame carries one JSON payload.
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Optional
import json
import uuid


# JSON-RPC version
JSONRPC_VERSION = "2.0"

# Protocol version for compatibility checking
PROTOCOL_VERSION = "2.0.0"


def _normalize_error_message(
    message: Any,
    *,
    fallback: str = "Unknown backend error",
) -> str:
    """Return a non-empty string error message for IPC payloads."""
    if isinstance(message, str):
        normalized = message.strip()
    elif message is None:
        normalized = ""
    else:
        normalized = str(message).strip()
    return normalized or fallback


class MessageType(str, Enum):
    """Types of messages sent from backend to frontend."""
    
    STATUS = "status"
    STREAM = "stream"
    TOOL_CALL = "tool_call"
    RESULT = "result"
    ERROR = "error"
    SYSTEM = "system"  # System-level messages (version, reload, etc.)


class AgentStatus(str, Enum):
    """Agent operational status values."""
    
    IDLE = "idle"
    CONNECTING = "connecting"
    THINKING = "thinking"
    PLANNING = "planning"
    PLAN_READY = "plan_ready"
    AWAITING_APPROVAL = "awaiting_approval"
    EXECUTING_PLAN = "executing_plan"
    CALLING_TOOL = "calling_tool"
    CAPTURING_SCREEN = "capturing_screen"
    STREAMING = "streaming"
    ERROR = "error"
    COMPLETE = "complete"


class ToolCallStatus(str, Enum):
    """Status of a tool call execution."""
    
    PENDING = "pending"
    EXECUTING = "executing"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass
class IPCMessage:
    """Base class for all IPC messages."""
    
    jsonrpc: str = JSONRPC_VERSION
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    
    def to_json(self) -> str:
        """Converts the message to a JSON string with newline delimiter."""
        return json.dumps(asdict(self)) + "\n"
    
    def to_bytes(self) -> bytes:
        """Converts the message to bytes for socket transmission."""
        return self.to_json().encode("utf-8")


@dataclass
class IncomingRequest(IPCMessage):
    """Request message from frontend to backend."""
    
    method: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_json(cls, data: str) -> "IncomingRequest":
        """Parses a JSON string into an IncomingRequest."""
        parsed = json.loads(data)
        if not isinstance(parsed, dict):
            raise ValueError("Request payload must be a JSON object")

        method = parsed.get("method", "")
        if not isinstance(method, str) or not method.strip():
            raise ValueError("Request method must be a non-empty string")

        raw_id = parsed.get("id", str(uuid.uuid4()))
        if raw_id is None:
            request_id = str(uuid.uuid4())
        elif isinstance(raw_id, str) and raw_id.strip():
            request_id = raw_id
        else:
            raise ValueError("Request id must be a non-empty string when provided")

        params = parsed.get("params", {})
        if not isinstance(params, dict):
            params = {}
        return cls(
            jsonrpc=parsed.get("jsonrpc", JSONRPC_VERSION),
            id=request_id,
            method=method,
            params=params,
        )


@dataclass
class StatusUpdate(IPCMessage):
    """Status update message sent to frontend."""
    
    type: str = MessageType.STATUS.value
    status: str = AgentStatus.IDLE.value
    detail: str = ""
    
    @classmethod
    def thinking(cls, request_id: str, detail: str = "Processing...") -> "StatusUpdate":
        """Creates a thinking status update."""
        return cls(id=request_id, status=AgentStatus.THINKING.value, detail=detail)

    @classmethod
    def planning(cls, request_id: str, detail: str = "Building plan...") -> "StatusUpdate":
        """Creates a planning status update."""
        return cls(id=request_id, status=AgentStatus.PLANNING.value, detail=detail)

    @classmethod
    def plan_ready(cls, request_id: str, detail: str = "Plan ready") -> "StatusUpdate":
        """Creates a plan_ready status update."""
        return cls(id=request_id, status=AgentStatus.PLAN_READY.value, detail=detail)

    @classmethod
    def awaiting_approval(
        cls,
        request_id: str,
        detail: str = "Awaiting approval for destructive operation",
    ) -> "StatusUpdate":
        """Creates an awaiting_approval status update."""
        return cls(id=request_id, status=AgentStatus.AWAITING_APPROVAL.value, detail=detail)

    @classmethod
    def executing_plan(
        cls,
        request_id: str,
        detail: str = "Executing approved plan",
    ) -> "StatusUpdate":
        """Creates an executing_plan status update."""
        return cls(id=request_id, status=AgentStatus.EXECUTING_PLAN.value, detail=detail)
    
    @classmethod
    def capturing_screen(
        cls,
        request_id: str,
        detail: str = "Reading screen contents...",
    ) -> "StatusUpdate":
        """Creates a capturing_screen status update."""
        return cls(id=request_id, status=AgentStatus.CAPTURING_SCREEN.value, detail=detail)

    @classmethod
    def streaming(cls, request_id: str) -> "StatusUpdate":
        """Creates a streaming status update."""
        return cls(id=request_id, status=AgentStatus.STREAMING.value)
    
    @classmethod
    def calling_tool(cls, request_id: str, tool_name: str) -> "StatusUpdate":
        """Creates a calling_tool status update."""
        return cls(
            id=request_id,
            status=AgentStatus.CALLING_TOOL.value,
            detail=tool_name,
        )
    
    @classmethod
    def complete(cls, request_id: str) -> "StatusUpdate":
        """Creates a complete status update."""
        return cls(id=request_id, status=AgentStatus.COMPLETE.value)
    
    @classmethod
    def error(cls, request_id: str, message: str) -> "StatusUpdate":
        """Creates an error status update."""
        return cls(
            id=request_id,
            status=AgentStatus.ERROR.value,
            detail=_normalize_error_message(message),
        )


@dataclass
class StreamChunk(IPCMessage):
    """Streaming response chunk sent to frontend."""
    
    type: str = MessageType.STREAM.value
    delta: str = ""
    done: bool = False
    
    @classmethod
    def chunk(cls, request_id: str, text: str, done: bool = False) -> "StreamChunk":
        """Creates a stream chunk."""
        return cls(id=request_id, delta=text, done=done)
    
    @classmethod
    def final(cls, request_id: str, text: str = "") -> "StreamChunk":
        """Creates a final stream chunk."""
        return cls(id=request_id, delta=text, done=True)


@dataclass
class ToolCallNotification(IPCMessage):
    """Tool call notification sent to frontend."""
    
    type: str = MessageType.TOOL_CALL.value
    tool: dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def create(
        cls,
        request_id: str,
        name: str,
        arguments: dict[str, Any],
        status: ToolCallStatus = ToolCallStatus.PENDING,
        result: Optional[str] = None,
        error: Optional[str] = None,
    ) -> "ToolCallNotification":
        """Creates a tool call notification."""
        tool_data = {
            "name": name,
            "arguments": arguments,
            "status": status.value,
        }
        if result is not None:
            tool_data["result"] = result
        if error is not None:
            tool_data["error"] = error
        
        return cls(id=request_id, tool=tool_data)
    
    @classmethod
    def pending(
        cls, request_id: str, name: str, arguments: dict[str, Any]
    ) -> "ToolCallNotification":
        """Creates a pending tool call notification."""
        return cls.create(request_id, name, arguments, ToolCallStatus.PENDING)
    
    @classmethod
    def executing(
        cls, request_id: str, name: str, arguments: dict[str, Any]
    ) -> "ToolCallNotification":
        """Creates an executing tool call notification."""
        return cls.create(request_id, name, arguments, ToolCallStatus.EXECUTING)
    
    @classmethod
    def success(
        cls, request_id: str, name: str, arguments: dict[str, Any], result: str
    ) -> "ToolCallNotification":
        """Creates a successful tool call notification."""
        return cls.create(
            request_id, name, arguments, ToolCallStatus.SUCCESS, result=result
        )
    
    @classmethod
    def failed(
        cls, request_id: str, name: str, arguments: dict[str, Any], error: str
    ) -> "ToolCallNotification":
        """Creates a failed tool call notification."""
        return cls.create(
            request_id, name, arguments, ToolCallStatus.FAILED, error=error
        )


@dataclass
class ResultMessage(IPCMessage):
    """Final result message sent to frontend."""
    
    type: str = MessageType.RESULT.value
    result: dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def create(
        cls,
        request_id: str,
        content: str,
        tool_calls: Optional[list[dict[str, Any]]] = None,
    ) -> "ResultMessage":
        """Creates a result message."""
        result_data: dict[str, Any] = {"content": content}
        if tool_calls:
            result_data["tool_calls"] = tool_calls
        return cls(id=request_id, result=result_data)


@dataclass
class ErrorMessage(IPCMessage):
    """Error message sent to frontend."""
    
    type: str = MessageType.ERROR.value
    error: dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def create(
        cls,
        request_id: str,
        code: int,
        message: str,
        *,
        data: Optional[dict[str, Any]] = None,
    ) -> "ErrorMessage":
        """Creates an error message."""
        payload: dict[str, Any] = {
            "code": code,
            "message": _normalize_error_message(message),
        }
        if data:
            payload["data"] = data
        return cls(id=request_id, error=payload)
    
    # Standard error codes
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
    AUTH_REQUIRED = -32010
    AUTH_FAILED = -32011
    PROTOCOL_MISMATCH = -32012
    RATE_LIMITED = -32013
    REQUEST_TIMEOUT = -32014
    
    @classmethod
    def parse_error(cls, request_id: str, detail: str = "") -> "ErrorMessage":
        """Creates a parse error message."""
        msg = "Parse error"
        if detail:
            msg += f": {detail}"
        return cls.create(request_id, cls.PARSE_ERROR, msg)
    
    @classmethod
    def invalid_request(cls, request_id: str, detail: str = "") -> "ErrorMessage":
        """Creates an invalid request error message."""
        msg = "Invalid request"
        if detail:
            msg += f": {detail}"
        return cls.create(request_id, cls.INVALID_REQUEST, msg)
    
    @classmethod
    def method_not_found(cls, request_id: str, method: str) -> "ErrorMessage":
        """Creates a method not found error message."""
        return cls.create(request_id, cls.METHOD_NOT_FOUND, f"Method not found: {method}")

    @classmethod
    def auth_required(cls, request_id: str, detail: str = "") -> "ErrorMessage":
        """Creates an authentication required error message."""
        msg = "Authentication required"
        if detail:
            msg += f": {detail}"
        return cls.create(request_id, cls.AUTH_REQUIRED, msg)

    @classmethod
    def auth_failed(cls, request_id: str, detail: str = "") -> "ErrorMessage":
        """Creates an authentication failed error message."""
        msg = "Authentication failed"
        if detail:
            msg += f": {detail}"
        return cls.create(request_id, cls.AUTH_FAILED, msg)

    @classmethod
    def protocol_mismatch(cls, request_id: str, detail: str = "") -> "ErrorMessage":
        """Creates a protocol mismatch error message."""
        msg = "Protocol mismatch"
        if detail:
            msg += f": {detail}"
        return cls.create(request_id, cls.PROTOCOL_MISMATCH, msg)

    @classmethod
    def rate_limited(cls, request_id: str, detail: str = "") -> "ErrorMessage":
        """Creates a rate limited error message."""
        msg = "Rate limited"
        if detail:
            msg += f": {detail}"
        return cls.create(request_id, cls.RATE_LIMITED, msg)

    @classmethod
    def internal_error(cls, request_id: str, detail: str = "") -> "ErrorMessage":
        """Creates an internal error message."""
        msg = "Internal error"
        if detail:
            msg += f": {detail}"
        return cls.create(request_id, cls.INTERNAL_ERROR, msg)


@dataclass
class SystemMessage(IPCMessage):
    """System-level message for version info, reload status, etc."""
    
    type: str = MessageType.SYSTEM.value
    system: dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def version_info(
        cls,
        request_id: str,
        protocol_version: str = PROTOCOL_VERSION,
        code_version: int = 0,
        features: Optional[list[str]] = None,
    ) -> "SystemMessage":
        """Creates a version info message."""
        return cls(
            id=request_id,
            system={
                "event": "version",
                "protocol_version": protocol_version,
                "code_version": code_version,
                "features": features or ["prompt", "cancel", "ping", "reload", "version"],
            },
        )
    
    @classmethod
    def reload_started(cls, request_id: str, trigger: str) -> "SystemMessage":
        """Creates a reload started notification."""
        return cls(
            id=request_id,
            system={
                "event": "reload_started",
                "trigger": trigger,
            },
        )
    
    @classmethod
    def reload_complete(
        cls,
        request_id: str,
        success: bool,
        new_version: int,
        error: Optional[str] = None,
    ) -> "SystemMessage":
        """Creates a reload complete notification."""
        data = {
            "event": "reload_complete",
            "success": success,
            "new_version": new_version,
        }
        if error:
            data["error"] = error
        return cls(id=request_id, system=data)
    
    @classmethod
    def code_changed(cls, request_id: str, files: list[str]) -> "SystemMessage":
        """Creates a code change notification (for auto-reload scenarios)."""
        return cls(
            id=request_id,
            system={
                "event": "code_changed",
                "changed_files": files,
            },
        )

    @classmethod
    def lifecycle_event(
        cls,
        request_id: str,
        *,
        domain: str,
        action: str,
        payload: dict[str, Any] | None = None,
    ) -> "SystemMessage":
        """Creates a generic lifecycle event for realtime UI synchronization."""
        return cls(
            id=request_id,
            system={
                "event": "lifecycle",
                "domain": domain,
                "action": action,
                "payload": payload or {},
            },
        )

    @classmethod
    def session_event(
        cls,
        request_id: str,
        *,
        action: str,
        session: dict[str, Any],
    ) -> "SystemMessage":
        """Creates a session lifecycle event."""
        return cls.lifecycle_event(
            request_id,
            domain="session",
            action=action,
            payload={"session": session},
        )

    @classmethod
    def notes_event(
        cls,
        request_id: str,
        *,
        action: str,
        session_id: str,
        note: dict[str, Any] | None = None,
        note_id: str | None = None,
    ) -> "SystemMessage":
        """Creates a notes lifecycle event."""
        payload: dict[str, Any] = {"session_id": session_id}
        if note is not None:
            payload["note"] = note
        if note_id is not None:
            payload["note_id"] = note_id
        return cls.lifecycle_event(
            request_id,
            domain="notes",
            action=action,
            payload=payload,
        )

    @classmethod
    def memory_event(
        cls,
        request_id: str,
        *,
        action: str,
        session_id: str,
        memory_id: str | None = None,
    ) -> "SystemMessage":
        """Creates a semantic-memory lifecycle event."""
        payload: dict[str, Any] = {"session_id": session_id}
        if memory_id is not None:
            payload["memory_id"] = memory_id
        return cls.lifecycle_event(
            request_id,
            domain="memory",
            action=action,
            payload=payload,
        )
