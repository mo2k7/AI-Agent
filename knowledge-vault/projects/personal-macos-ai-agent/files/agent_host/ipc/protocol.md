# File Doc: `agent_host/ipc/protocol.py`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `agent_host/ipc/protocol.py` |
| Doc Path | `projects/personal-macos-ai-agent/files/agent_host/ipc/protocol.md` |
| Language | Python |
| File Role | IPC Protocol Definitions |
| Ownership | Core Team |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-01-18 |
| Last Major Edit (YYYY-MM-DD) | 2026-01-18 |
| Modified By | AI Agent (Codex) |
| WHY (Reason for last change) | Guard against non-dict params in IncomingRequest parsing |
| Lines of Code (LOC) | 272 |
| Cyclomatic Complexity | Low |
| Test Coverage | 0% |

---

## Purpose & Responsibilities

### What this file does
**Single-sentence summary:**
Defines the JSON-RPC 2.0 inspired message protocol for communication between the Python backend and SwiftUI frontend via Unix Domain Socket.

**Detailed responsibilities:**
- Defines enumeration types for message types (`MessageType`), agent status (`AgentStatus`), and tool call status (`ToolCallStatus`)
- Provides base `IPCMessage` dataclass with JSON serialization capabilities
- Implements `IncomingRequest` for parsing requests from the Swift frontend
- Implements `StatusUpdate` message type for status change notifications
- Implements `StreamChunk` for streaming response chunks with typewriter effect support
- Implements `ToolCallNotification` for tool call status updates
- Implements `ResultMessage` for final response delivery
- Implements `ErrorMessage` with standard JSON-RPC error codes

### What this file must NOT do (boundaries)
**Out of scope:**
- Actual network I/O operations (handled by `server.py`)
- Message routing or dispatching (handled by `server.py`)
- Streaming timing/delays (handled by `streaming.py`)
- Business logic or LLM integration

### Who/what calls it
| Caller | Purpose | Frequency | Error Handling |
|---|---|---|---|
| `agent_host/ipc/server.py` | Parse incoming requests, create response messages | On every IPC message | Returns error messages |
| `agent_host/ipc/streaming.py` | Create stream chunks | During streaming responses | N/A |
| `agent_host/main.py` | Create status updates and tool call notifications | On state changes | N/A |

### What it calls
| Callee | Purpose | Error Handling | Fallback Strategy |
|---|---|---|---|
| `dataclasses` | Dataclass decorators | N/A | N/A |
| `json` | JSON serialization | JSONEncodeError | N/A |
| `uuid` | Generate unique message IDs | N/A | N/A |

---

## Imports / Dependencies

### Internal Dependencies
| Import Path | What's Used | Why Needed | Coupling Level | Risk/Notes |
|---|---|---|---|---|
| N/A | N/A | N/A | N/A | N/A |

### External Dependencies
| Package | Version | License | What's Used | Why Needed | Security Risk | Alternatives |
|---|---|---|---|---|---|---|
| dataclasses | stdlib | PSF | `@dataclass`, `field`, `asdict` | Structured message types | None | attrs, pydantic |
| enum | stdlib | PSF | `Enum` | Type-safe constants | None | N/A |
| typing | stdlib | PSF | `Any`, `Optional` | Type hints | None | N/A |
| json | stdlib | PSF | `dumps`, `loads` | JSON serialization | None | orjson, ujson |
| uuid | stdlib | PSF | `uuid4` | Unique IDs | None | N/A |

### Dependency Risk Assessment
| Dependency | Maintenance Status | Security History | Breaking Change Risk | Replacement Plan |
|---|---|---|---|---|
| Standard Library | Active | Clean | None | N/A |

---

## Public Surface (Document EVERYTHING Exposed)

### Exports / Public Symbols
| Symbol | Type (func/class/const/type) | Visibility | Status | Brief Description |
|---|---|---|---|---|
| `JSONRPC_VERSION` | const | public | Stable | JSON-RPC version string "2.0" |
| `MessageType` | enum | public | Stable | Types of outgoing messages |
| `AgentStatus` | enum | public | Stable | Agent operational status values |
| `ToolCallStatus` | enum | public | Stable | Tool call execution status |
| `IPCMessage` | class | public | Stable | Base message dataclass |
| `IncomingRequest` | class | public | Stable | Request from frontend |
| `StatusUpdate` | class | public | Stable | Status change notification |
| `StreamChunk` | class | public | Stable | Streaming response chunk |
| `ToolCallNotification` | class | public | Stable | Tool call status notification |
| `ResultMessage` | class | public | Stable | Final result message |
| `ErrorMessage` | class | public | Stable | Error response message |

### API Stability
| Symbol | Introduced Version | Deprecated Version | Breaking Changes History |
|---|---|---|---|
| All symbols | 0.2.0 (Phase 2) | N/A | None |

---

## Types (Classes / Structs / Enums / Interfaces)

### `MessageType`
| Metadata | Value |
|---|---|
| Kind | enum |
| Purpose | Types of messages sent from backend to frontend |
| Thread-Safe | Yes (immutable) |
| Immutable | Yes |
| Serializable | Yes (via `.value`) |
| Related Types | `IPCMessage` |

#### Inheritance & Implementation
- **Extends:** `str`, `Enum`
- **Implements:** N/A
- **Used By:** All message classes, `server.py`, Swift `IPCMessageType`
- **Polymorphic Behavior:** String enum for JSON serialization

#### Fields / Properties
| Name | Type | Visibility | Default | Required | Mutable | Purpose | Validation | Notes |
|---|---|---|---|---|---|---|---|---|
| `STATUS` | str | public | `"status"` | N/A | No | Status update message type | N/A | |
| `STREAM` | str | public | `"stream"` | N/A | No | Streaming chunk message type | N/A | |
| `TOOL_CALL` | str | public | `"tool_call"` | N/A | No | Tool call notification type | N/A | |
| `RESULT` | str | public | `"result"` | N/A | No | Final result message type | N/A | |
| `ERROR` | str | public | `"error"` | N/A | No | Error message type | N/A | |

---

### `AgentStatus`
| Metadata | Value |
|---|---|
| Kind | enum |
| Purpose | Agent operational status values mirroring Swift `AgentStatus` |
| Thread-Safe | Yes (immutable) |
| Immutable | Yes |
| Serializable | Yes (via `.value`) |
| Related Types | `StatusUpdate` |

#### Fields / Properties
| Name | Type | Visibility | Default | Required | Mutable | Purpose | Validation | Notes |
|---|---|---|---|---|---|---|---|---|
| `IDLE` | str | public | `"idle"` | N/A | No | Ready and waiting | N/A | |
| `CONNECTING` | str | public | `"connecting"` | N/A | No | Establishing connection | N/A | |
| `THINKING` | str | public | `"thinking"` | N/A | No | Processing prompt | N/A | |
| `CALLING_TOOL` | str | public | `"calling_tool"` | N/A | No | Executing tool | N/A | |
| `STREAMING` | str | public | `"streaming"` | N/A | No | Streaming response | N/A | |
| `ERROR` | str | public | `"error"` | N/A | No | Error occurred | N/A | |
| `COMPLETE` | str | public | `"complete"` | N/A | No | Request completed | N/A | |

---

### `ToolCallStatus`
| Metadata | Value |
|---|---|
| Kind | enum |
| Purpose | Status of a tool call execution |
| Thread-Safe | Yes (immutable) |
| Immutable | Yes |
| Serializable | Yes (via `.value`) |
| Related Types | `ToolCallNotification` |

#### Fields / Properties
| Name | Type | Visibility | Default | Required | Mutable | Purpose | Validation | Notes |
|---|---|---|---|---|---|---|---|---|
| `PENDING` | str | public | `"pending"` | N/A | No | Tool call queued | N/A | |
| `EXECUTING` | str | public | `"executing"` | N/A | No | Tool executing | N/A | |
| `SUCCESS` | str | public | `"success"` | N/A | No | Tool completed successfully | N/A | |
| `FAILED` | str | public | `"failed"` | N/A | No | Tool execution failed | N/A | |

---

### `IPCMessage`
| Metadata | Value |
|---|---|
| Kind | dataclass |
| Purpose | Base class for all IPC messages |
| Thread-Safe | Yes (immutable by convention) |
| Immutable | No (but treated as such) |
| Serializable | Yes |
| Related Types | All message subclasses |

#### Inheritance & Implementation
- **Extends:** N/A
- **Implements:** N/A
- **Used By:** All message classes inherit from this
- **Polymorphic Behavior:** Base serialization methods

#### Fields / Properties
| Name | Type | Visibility | Default | Required | Mutable | Purpose | Validation | Notes |
|---|---|---|---|---|---|---|---|---|
| `jsonrpc` | str | public | `JSONRPC_VERSION` | No | Yes | Protocol version | N/A | Always "2.0" |
| `id` | str | public | `uuid4()` | No | Yes | Unique message identifier | N/A | Auto-generated |

#### Methods
| Method | Signature | Visibility | Parameters | Returns | Throws/Errors | Side Effects | Thread-Safe | Complexity | Notes |
|---|---|---|---|---|---|---|---|---|---|
| `to_json` | `() -> str` | public | None | JSON string with newline | N/A | None | Yes | O(n) | Includes `\n` delimiter |
| `to_bytes` | `() -> bytes` | public | None | UTF-8 encoded bytes | N/A | None | Yes | O(n) | For socket transmission |

---

### `IncomingRequest`
| Metadata | Value |
|---|---|
| Kind | dataclass |
| Purpose | Request message from frontend to backend |
| Thread-Safe | Yes |
| Immutable | No |
| Serializable | Yes (bidirectional) |
| Related Types | `IPCMessage` |

#### Inheritance & Implementation
- **Extends:** `IPCMessage`
- **Implements:** N/A
- **Used By:** `IPCServer._handle_message`
- **Polymorphic Behavior:** Adds `method` and `params` fields

#### Fields / Properties
| Name | Type | Visibility | Default | Required | Mutable | Purpose | Validation | Notes |
|---|---|---|---|---|---|---|---|---|
| `method` | str | public | `""` | No | Yes | RPC method name | N/A | e.g., "prompt", "cancel" |
| `params` | dict[str, Any] | public | `{}` | No | Yes | Method parameters | N/A | Arbitrary key-value pairs |

#### Static Members
| Member | Type | Purpose | Mutability | Thread-Safe |
|---|---|---|---|---|
| `from_json` | classmethod | Parse JSON string to request | N/A | Yes |

#### Example Usage
```python
# Parse incoming request
request = IncomingRequest.from_json('{"jsonrpc":"2.0","id":"abc","method":"prompt","params":{"text":"Hello"}}')
print(request.method)  # "prompt"
print(request.params["text"])  # "Hello"
```

---

### `StatusUpdate`
| Metadata | Value |
|---|---|
| Kind | dataclass |
| Purpose | Status update message sent to frontend |
| Thread-Safe | Yes |
| Immutable | No |
| Serializable | Yes |
| Related Types | `IPCMessage`, `AgentStatus` |

#### Inheritance & Implementation
- **Extends:** `IPCMessage`
- **Implements:** N/A
- **Used By:** `IPCServer`, `StreamingHandler`
- **Polymorphic Behavior:** Status-specific factory methods

#### Fields / Properties
| Name | Type | Visibility | Default | Required | Mutable | Purpose | Validation | Notes |
|---|---|---|---|---|---|---|---|---|
| `type` | str | public | `MessageType.STATUS.value` | No | Yes | Message type identifier | N/A | Always "status" |
| `status` | str | public | `AgentStatus.IDLE.value` | No | Yes | Current agent status | N/A | |
| `detail` | str | public | `""` | No | Yes | Optional detail (tool name, error) | N/A | |

#### Static Members
| Member | Type | Purpose | Mutability | Thread-Safe |
|---|---|---|---|---|
| `thinking` | classmethod | Create thinking status | N/A | Yes |
| `streaming` | classmethod | Create streaming status | N/A | Yes |
| `calling_tool` | classmethod | Create calling_tool status | N/A | Yes |
| `complete` | classmethod | Create complete status | N/A | Yes |
| `error` | classmethod | Create error status | N/A | Yes |

#### Example Usage
```python
# Create status updates
status = StatusUpdate.thinking("req-123", "Processing your request...")
await client.send(status.to_bytes())

status = StatusUpdate.calling_tool("req-123", "search_files")
await client.send(status.to_bytes())

status = StatusUpdate.complete("req-123")
await client.send(status.to_bytes())
```

---

### `StreamChunk`
| Metadata | Value |
|---|---|
| Kind | dataclass |
| Purpose | Streaming response chunk for typewriter effect |
| Thread-Safe | Yes |
| Immutable | No |
| Serializable | Yes |
| Related Types | `IPCMessage` |

#### Fields / Properties
| Name | Type | Visibility | Default | Required | Mutable | Purpose | Validation | Notes |
|---|---|---|---|---|---|---|---|---|
| `type` | str | public | `MessageType.STREAM.value` | No | Yes | Message type | N/A | Always "stream" |
| `delta` | str | public | `""` | No | Yes | Text chunk to append | N/A | Can be char, word, or chunk |
| `done` | bool | public | `False` | No | Yes | Whether this is the final chunk | N/A | |

#### Static Members
| Member | Type | Purpose | Mutability | Thread-Safe |
|---|---|---|---|---|
| `chunk` | classmethod | Create a stream chunk | N/A | Yes |
| `final` | classmethod | Create final chunk with done=True | N/A | Yes |

#### Example Usage
```python
# Stream text character by character
for char in "Hello":
    chunk = StreamChunk.chunk("req-123", char, done=False)
    await client.send(chunk.to_bytes())
    await asyncio.sleep(0.02)  # 20ms delay for typewriter effect

# Send final chunk
await client.send(StreamChunk.final("req-123").to_bytes())
```

---

### `ToolCallNotification`
| Metadata | Value |
|---|---|
| Kind | dataclass |
| Purpose | Notification about tool call status |
| Thread-Safe | Yes |
| Immutable | No |
| Serializable | Yes |
| Related Types | `IPCMessage`, `ToolCallStatus` |

#### Fields / Properties
| Name | Type | Visibility | Default | Required | Mutable | Purpose | Validation | Notes |
|---|---|---|---|---|---|---|---|---|
| `type` | str | public | `MessageType.TOOL_CALL.value` | No | Yes | Message type | N/A | Always "tool_call" |
| `tool` | dict[str, Any] | public | `{}` | No | Yes | Tool call details | N/A | Contains name, arguments, status, result, error |

#### Static Members
| Member | Type | Purpose | Mutability | Thread-Safe |
|---|---|---|---|---|
| `create` | classmethod | Create notification with all fields | N/A | Yes |
| `pending` | classmethod | Create pending notification | N/A | Yes |
| `executing` | classmethod | Create executing notification | N/A | Yes |
| `success` | classmethod | Create success notification | N/A | Yes |
| `failed` | classmethod | Create failed notification | N/A | Yes |

#### Example Usage
```python
# Notify tool call pending
notification = ToolCallNotification.pending(
    "req-123", "search_files", {"query": "*.py", "path": "/Documents"}
)
await client.send(notification.to_bytes())

# Notify tool executing
notification = ToolCallNotification.executing("req-123", "search_files", {"query": "*.py"})
await client.send(notification.to_bytes())

# Notify success
notification = ToolCallNotification.success(
    "req-123", "search_files", {"query": "*.py"}, "Found 15 files"
)
await client.send(notification.to_bytes())
```

---

### `ResultMessage`
| Metadata | Value |
|---|---|
| Kind | dataclass |
| Purpose | Final result message |
| Thread-Safe | Yes |
| Immutable | No |
| Serializable | Yes |
| Related Types | `IPCMessage` |

#### Fields / Properties
| Name | Type | Visibility | Default | Required | Mutable | Purpose | Validation | Notes |
|---|---|---|---|---|---|---|---|---|
| `type` | str | public | `MessageType.RESULT.value` | No | Yes | Message type | N/A | Always "result" |
| `result` | dict[str, Any] | public | `{}` | No | Yes | Result data | N/A | Contains content, tool_calls |

#### Static Members
| Member | Type | Purpose | Mutability | Thread-Safe |
|---|---|---|---|---|
| `create` | classmethod | Create result with content and optional tool_calls | N/A | Yes |

---

### `ErrorMessage`
| Metadata | Value |
|---|---|
| Kind | dataclass |
| Purpose | Error response following JSON-RPC error format |
| Thread-Safe | Yes |
| Immutable | No |
| Serializable | Yes |
| Related Types | `IPCMessage` |

#### Fields / Properties
| Name | Type | Visibility | Default | Required | Mutable | Purpose | Validation | Notes |
|---|---|---|---|---|---|---|---|---|
| `type` | str | public | `MessageType.ERROR.value` | No | Yes | Message type | N/A | Always "error" |
| `error` | dict[str, Any] | public | `{}` | No | Yes | Error details | N/A | Contains code, message |

#### Static Members
| Member | Type | Purpose | Mutability | Thread-Safe |
|---|---|---|---|---|
| `PARSE_ERROR` | int | Error code -32700 | Immutable | Yes |
| `INVALID_REQUEST` | int | Error code -32600 | Immutable | Yes |
| `METHOD_NOT_FOUND` | int | Error code -32601 | Immutable | Yes |
| `INVALID_PARAMS` | int | Error code -32602 | Immutable | Yes |
| `INTERNAL_ERROR` | int | Error code -32603 | Immutable | Yes |
| `create` | classmethod | Create error with code and message | N/A | Yes |
| `parse_error` | classmethod | Create parse error | N/A | Yes |
| `invalid_request` | classmethod | Create invalid request error | N/A | Yes |
| `method_not_found` | classmethod | Create method not found error | N/A | Yes |
| `internal_error` | classmethod | Create internal error | N/A | Yes |

#### Example Usage
```python
# Handle parse error
try:
    request = IncomingRequest.from_json(data)
except json.JSONDecodeError as e:
    error = ErrorMessage.parse_error("", str(e))
    await client.send(error.to_bytes())

# Handle unknown method
if method not in handlers:
    error = ErrorMessage.method_not_found(request.id, method)
    await client.send(error.to_bytes())
```

---

## State Management

### Module-Level State
| Variable | Type | Scope | Mutability | Thread-Safe | Purpose | Risk |
|---|---|---|---|---|---|---|
| `JSONRPC_VERSION` | str | Module | Immutable | Yes | Protocol version constant | None |

### State Transitions
```
IncomingRequest --parse--> handler
handler --status--> StatusUpdate(thinking)
handler --stream--> StreamChunk(delta)
handler --tool--> ToolCallNotification
handler --done--> StreamChunk(done=True)
handler --result--> ResultMessage
handler --error--> ErrorMessage
```

---

## Error Handling Strategy

### Error Categories
| Category | Examples | Default Behavior | User Action |
|---|---|---|---|
| Parse Errors | Invalid JSON | Return ErrorMessage.parse_error | Fix JSON format |
| Invalid Request | Missing method | Return ErrorMessage.invalid_request | Include method field |
| Method Not Found | Unknown method | Return ErrorMessage.method_not_found | Use valid method |
| Internal Errors | Runtime exceptions | Return ErrorMessage.internal_error | Report bug |

### Error Propagation
```
IncomingRequest.from_json() --JSONDecodeError--> ErrorMessage.parse_error()
Handler --Exception--> ErrorMessage.internal_error()
```

---

## Concurrency & Threading

### Concurrency Model
- **Thread Safety:** All classes are thread-safe (immutable enums, dataclass instances per-message)
- **Synchronization Primitives:** None required
- **Async Patterns:** Designed for async/await usage in server

### Potential Race Conditions
| Location | Description | Likelihood | Mitigation | Status |
|---|---|---|---|---|
| N/A | N/A | N/A | N/A | N/A |

---

## Performance Profile

### Performance Characteristics
| Metric | Value | Target | Acceptable Range |
|---|---|---|---|
| JSON Serialization | <1ms | <5ms | <10ms |
| Memory per Message | ~200 bytes | <1KB | <5KB |

---

## Security Analysis

### Trust Boundaries
| Boundary | Input Source | Validation Required | Sanitization |
|---|---|---|---|
| `IncomingRequest.from_json` | Swift UI | JSON schema validation | None (internal IPC) |

### Input Validation
| Input | Validation Rules | Sanitization | Attack Vectors |
|---|---|---|---|
| JSON data | Valid JSON format | None | JSON injection (mitigated by local-only socket) |
| method | String type | None | N/A |
| params | Dict type | None | N/A |

---

## Testing Documentation

### Unit Test Coverage
| Function/Class | Coverage | Test Location | Edge Cases Covered |
|---|---|---|---|
| All | 0% | `tests/unit/test_protocol.py` | None yet |

### Testing Gaps
| Untested Area | Risk | Reason | Plan to Address |
|---|---|---|---|
| All message types | Medium | New implementation | Add unit tests |
| JSON serialization | Low | Standard library | Add integration tests |

---

## Related Documentation

### Related Files
| File Path | Relationship | Why Related |
|---|---|---|
| `agent_host/ipc/server.py` | Uses | Creates and parses messages |
| `agent_host/ipc/streaming.py` | Uses | Creates StreamChunk messages |
| `ui/AIAgentUI/IPC/MessageProtocol.swift` | Mirror | Swift equivalent types |

---

## Maintainer Notes

### When to Update This Doc
- [ ] When adding new message types
- [ ] When adding new status values
- [ ] When changing JSON schema
- [ ] When adding error codes

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-01-18 | AI Assistant | Initial implementation | Created protocol definitions | New file |
| 2026-01-18 | AI Agent (Codex) | Input robustness | Coerce invalid params to empty dict to avoid request handling crashes | Medium |
