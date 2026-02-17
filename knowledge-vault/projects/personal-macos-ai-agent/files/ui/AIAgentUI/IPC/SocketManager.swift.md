# File Doc: `ui/AIAgentUI/IPC/SocketManager.swift`

## File Metadata
| Field | Value |
|---|---|
| Project | personal-macos-ai-agent |
| Code File Path | `ui/AIAgentUI/IPC/SocketManager.swift` |
| Doc Path | `projects/personal-macos-ai-agent/files/ui/AIAgentUI/IPC/SocketManager.swift.md` |
| Language | Swift 6 |
| File Role | networking |
| Ownership | @individual-developer |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-01-18 |
| Last Major Edit (YYYY-MM-DD) | 2026-01-18 |
| Modified By | AI Agent (Codex) |
| WHY (Reason for last change) | Updated test coverage path reference |
| Lines of Code (LOC) | 316 |
| Cyclomatic Complexity | Medium |
| Test Coverage | 0% (Tests/AIAgentUITests/IPCTests/) |

---

## Purpose & Responsibilities

### What this file does
**Single-sentence summary:** Manages Unix Domain Socket connections to the Python backend using Apple's Network framework (NWConnection).

**Detailed responsibilities:**
- Establishes and maintains Unix socket connection to Python backend
- Handles connection lifecycle (connect, disconnect, reconnect)
- Sends requests (prompts, cancellation) to backend
- Receives and buffers incoming data
- Integrates with `StreamingParser` for message framing
- Dispatches parsed messages via `MessageDispatcher`
- Handles network errors and connection failures

### What this file must NOT do (boundaries)
**Out of scope:**
- Does NOT spawn the backend process (see `BackendLauncher.swift`)
- Does NOT parse message content/semantics (see `MessageProtocol.swift`)
- Does NOT manage application state (see `AppState.swift`)

### Who/what calls it
| Caller | Purpose | Frequency | Error Handling |
|---|---|---|---|
| `IPCClient.swift` | Higher-level IPC abstraction | On every IPC operation | Propagates errors |
| `AppState.swift` | Connection management | On connect/disconnect | Updates connection state |

### What it calls
| Callee | Purpose | Error Handling | Fallback Strategy |
|---|---|---|---|
| `NWConnection` | Network I/O | Error callbacks | Reports to caller |
| `StreamingParser` | Message framing | Error callback | Reports parsing errors |
| `MessageDispatcher` | Message routing | N/A | N/A |

---

## Imports / Dependencies

### External Dependencies
| Package | Version | License | What's Used | Why Needed | Security Risk | Alternatives |
|---|---|---|---|---|---|---|
| Foundation | System | Apple | FileManager, Data, DispatchQueue | File operations, data handling, threading | Low | None |
| Network | System | Apple | NWConnection, NWEndpoint, NWParameters | Modern async networking | Low | BSD sockets |

---

## Public Surface (Document EVERYTHING Exposed)

### Exports / Public Symbols
| Symbol | Type | Visibility | Status | Brief Description |
|---|---|---|---|---|
| `SocketManager` | class | internal | Stable | Unix socket connection manager |
| `SocketManager.ConnectionState` | enum | internal | Stable | Connection lifecycle states |
| `SocketError` | enum | internal | Stable | Socket operation errors |

---

## Types (Classes / Structs / Enums / Interfaces)

### `SocketManager`
| Metadata | Value |
|---|---|
| Kind | class |
| Purpose | Manages Unix Domain Socket connections |
| Thread-Safe | Yes (@unchecked Sendable with internal queue) |
| Immutable | No |
| Serializable | No |
| Related Types | `ConnectionState`, `SocketError`, `StreamingParser`, `MessageDispatcher` |

#### Inheritance & Implementation
- **Extends:** None
- **Implements:** `@unchecked Sendable` (thread-safe via internal dispatch queue)
- **Used By:** `IPCClient`, `AppState`
- **Polymorphic Behavior:** None

#### Fields / Properties
| Name | Type | Visibility | Default | Required | Mutable | Purpose |
|---|---|---|---|---|---|---|
| `state` | `ConnectionState` | private(set) | `.disconnected` | Yes | Yes | Current connection state |
| `connection` | `NWConnection?` | private | `nil` | No | Yes | Network connection |
| `queue` | `DispatchQueue` | private | `DispatchQueue(label:qos:)` | Yes | No | Network operations queue |
| `socketPathTemplate` | `String` | private | `"/tmp/ai-agent-%d.sock"` | Yes | No | Socket path pattern |
| `currentSocketPath` | `String?` | private | `nil` | No | Yes | Active socket path |
| `parser` | `StreamingParser` | private | `StreamingParser()` | Yes | No | Message framing |
| `dispatcher` | `MessageDispatcher` | internal | `MessageDispatcher()` | Yes | No | Message routing |
| `onStateChange` | closure | internal | `nil` | No | Yes | State change callback |
| `onDataReceived` | closure | internal | `nil` | No | Yes | Data received callback |
| `onError` | closure | internal | `nil` | No | Yes | Error callback |

#### Methods
| Method | Visibility | Parameters | Returns | Throws | Side Effects | Notes |
|---|---|---|---|---|---|---|
| `connect(pid:)` | internal | `Int?` | Void | `SocketError` | Creates connection | Async, finds socket if no PID |
| `connect(toPath:)` | internal | `String` | Void | `SocketError` | Creates connection | Async, specific path |
| `disconnect()` | internal | None | Void | None | Cancels connection | Synchronous |
| `reconnect()` | internal | None | Void | `SocketError` | Reconnects | Async |
| `send(_:)` (Data) | internal | `Data` | Void | `SocketError` | Network I/O | Async |
| `send(_:)` (String) | internal | `String` | Void | `SocketError` | Network I/O | Adds newline |
| `sendPrompt(_:)` | internal | `String` | `String` | `SocketError` | Network I/O | Returns request ID |
| `sendCancel()` | internal | None | Void | `SocketError` | Network I/O | Cancels streaming |

### `SocketManager.ConnectionState`
| Metadata | Value |
|---|---|
| Kind | enum |
| Purpose | Represents socket connection lifecycle |
| Thread-Safe | Yes (value type) |
| Immutable | Yes |

#### Cases
| Case | Associated Values | Description |
|---|---|---|
| `.disconnected` | None | No active connection |
| `.connecting` | None | Connection in progress |
| `.connected` | None | Successfully connected |
| `.failed(_:)` | `String` | Connection failed with error |

### `SocketError`
| Metadata | Value |
|---|---|
| Kind | enum |
| Purpose | Error types for socket operations |
| Thread-Safe | Yes |
| Immutable | Yes |
| Serializable | No |

#### Cases
| Case | Associated Values | Description |
|---|---|---|
| `.noAvailableSocket` | None | No backend socket found |
| `.alreadyConnecting` | None | Connection already in progress |
| `.connectionFailed(_:)` | `String` | Connection failed with reason |
| `.connectionTimeout` | None | Connection timed out |
| `.notConnected` | None | Operation requires connection |
| `.sendFailed(_:)` | `String` | Send operation failed |
| `.receiveError(_:)` | `String` | Receive operation failed |
| `.encodingError` | None | Message encoding failed |
| `.parsingError(_:)` | `String` | Response parsing failed |

---

## Concurrency & Threading

### Concurrency Model
- **Thread Safety:** `@unchecked Sendable` - manual thread safety via internal dispatch queue
- **Synchronization Primitives:** `DispatchQueue` for all network operations
- **Async Patterns:** `async/await` with `withCheckedThrowingContinuation` for bridging

### Swift 6 Concurrency Fix Applied
| Before | After | Reason |
|---|---|---|
| `final class SocketManager` | `final class SocketManager: @unchecked Sendable` | Class is accessed from `@MainActor` contexts (AppState, IPCClient) while performing background work |

### Why @unchecked Sendable is Safe
1. All network operations happen on private `queue` (serial dispatch queue)
2. State updates dispatch to main thread via `DispatchQueue.main.async`
3. `NWConnection` has its own internal thread safety
4. No mutable state accessed concurrently without queue protection

---

## Integration Points

### Unix Domain Socket Protocol
| Aspect | Details |
|---|---|
| Path Pattern | `/tmp/ai-agent-{pid}.sock` |
| Message Format | Newline-delimited JSON |
| Request Types | `PromptRequest`, `CancelRequest` |
| Response Types | `StreamChunk`, `ToolCall`, `Complete`, `Error` |

---

## Related Documentation

### Related Files
| File Path | Relationship | Why Related |
|---|---|---|
| `ui/AIAgentUI/IPC/BackendLauncher.swift` | Related | Creates the socket |
| `ui/AIAgentUI/IPC/IPCClient.swift` | Uses this | Higher-level abstraction |
| `ui/AIAgentUI/IPC/StreamingParser.swift` | Uses this | Message framing |
| `ui/AIAgentUI/IPC/MessageProtocol.swift` | Uses this | Request/response types |
| `agent_host/main.py` | Connects to | Python backend |

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-01-18 | AI Agent (Claude) | Initial creation | Created SocketManager for Unix socket IPC | High |
| 2026-01-18 | AI Agent (Claude) | Swift 6 concurrency | Added @unchecked Sendable for cross-actor access | Medium |
