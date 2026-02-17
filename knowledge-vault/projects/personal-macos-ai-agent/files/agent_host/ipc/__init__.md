# File Doc: `agent_host/ipc/__init__.py`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `agent_host/ipc/__init__.py` |
| Doc Path | `projects/personal-macos-ai-agent/files/agent_host/ipc/__init__.md` |
| Language | Python |
| File Role | Module Initialization |
| Ownership | Core Team |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-01-18 |
| Last Major Edit (YYYY-MM-DD) | 2026-01-18 |
| Modified By | AI Assistant |
| WHY (Reason for last change) | Initial implementation for IPC module |
| Lines of Code (LOC) | 30 |
| Cyclomatic Complexity | None (imports only) |
| Test Coverage | N/A |

---

## Purpose & Responsibilities

### What this file does
**Single-sentence summary:**
Module initialization file that exports the public API of the IPC subsystem for Unix Domain Socket communication.

**Detailed responsibilities:**
- Exports `IPCServer` and `IPCServerManager` from `server.py`
- Exports all protocol types (`MessageType`, `AgentStatus`, `ToolCallStatus`, message classes) from `protocol.py`
- Exports `StreamingHandler`, `ResponseAccumulator`, `StreamingConfig` from `streaming.py`
- Defines `__all__` for explicit public API
- Provides convenient single-import access to the IPC subsystem

### What this file must NOT do (boundaries)
**Out of scope:**
- Implementation logic (delegated to submodules)
- Additional exports beyond the core IPC functionality
- Version-specific imports or conditional loading

---

## Imports / Dependencies

### Internal Dependencies
| Import Path | What's Used | Why Needed | Coupling Level | Risk/Notes |
|---|---|---|---|---|
| `.server` | `IPCServer`, `IPCServerManager`, `ClientConnection` | Server functionality | High | Core module |
| `.protocol` | All message types and enums | Protocol definitions | High | Core module |
| `.streaming` | Streaming utilities | Typewriter effect | Medium | Feature module |

---

## Public Surface (Document EVERYTHING Exposed)

### Exports / Public Symbols
| Symbol | Type (func/class/const/type) | Visibility | Status | Brief Description |
|---|---|---|---|---|
| `IPCServer` | class | public | Stable | Async Unix socket server |
| `IPCServerManager` | class | public | Stable | Server lifecycle manager |
| `ClientConnection` | class | public | Stable | Per-client connection wrapper |
| `MessageType` | enum | public | Stable | Message type identifiers |
| `AgentStatus` | enum | public | Stable | Agent status values |
| `ToolCallStatus` | enum | public | Stable | Tool call status values |
| `IPCMessage` | class | public | Stable | Base message class |
| `IncomingRequest` | class | public | Stable | Frontend request message |
| `StatusUpdate` | class | public | Stable | Status notification message |
| `StreamChunk` | class | public | Stable | Streaming response chunk |
| `ToolCallNotification` | class | public | Stable | Tool call notification |
| `ResultMessage` | class | public | Stable | Final result message |
| `ErrorMessage` | class | public | Stable | Error response message |
| `StreamingHandler` | class | public | Stable | Typewriter streaming utility |
| `ResponseAccumulator` | class | public | Stable | Chunk accumulator |
| `StreamingConfig` | class | public | Stable | Streaming configuration |

### `__all__` Definition
```python
__all__ = [
    # Server
    "IPCServer",
    "IPCServerManager",
    "ClientConnection",
    # Protocol - Enums
    "MessageType",
    "AgentStatus",
    "ToolCallStatus",
    # Protocol - Messages
    "IPCMessage",
    "IncomingRequest",
    "StatusUpdate",
    "StreamChunk",
    "ToolCallNotification",
    "ResultMessage",
    "ErrorMessage",
    # Streaming
    "StreamingHandler",
    "ResponseAccumulator",
    "StreamingConfig",
]
```

---

## Example Usage

### Basic Server Setup
```python
from agent_host.ipc import (
    IPCServer,
    IPCServerManager,
    StatusUpdate,
    ResultMessage,
    ErrorMessage,
)

async def main():
    async with IPCServerManager() as server:
        server.register_handler("prompt", handle_prompt)
        await server.serve_forever()
```

### Streaming Response
```python
from agent_host.ipc import StreamingHandler, StreamingConfig

config = StreamingConfig(char_delay=0.02)
handler = StreamingHandler(client, request_id, config)
await handler.stream_text("Hello, world!")
```

### Creating Messages
```python
from agent_host.ipc import (
    StatusUpdate,
    StreamChunk,
    ToolCallNotification,
    ResultMessage,
)

# Status updates
status = StatusUpdate.thinking(request_id, "Processing...")
status = StatusUpdate.calling_tool(request_id, "search_files")

# Tool notifications
notification = ToolCallNotification.executing(request_id, "search_files", {"query": "*.py"})
notification = ToolCallNotification.success(request_id, "search_files", {"query": "*.py"}, "Found 10 files")

# Final result
result = ResultMessage.create(request_id, "Here is your answer...")
```

---

## Related Documentation

### Related Files
| File Path | Relationship | Why Related |
|---|---|---|
| `agent_host/ipc/server.py` | Exports | IPCServer, IPCServerManager |
| `agent_host/ipc/protocol.py` | Exports | Message types |
| `agent_host/ipc/streaming.py` | Exports | Streaming utilities |
| `agent_host/main.py` | Used by | Imports IPC module |

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-01-18 | AI Assistant | Initial implementation | Created module init | New file |
