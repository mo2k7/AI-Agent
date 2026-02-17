# File Doc: `ui/AIAgentUI/IPC/IPCClient.swift`

## File Metadata
| Field | Value |
|---|---|
| Project | personal-macos-ai-agent |
| Code File Path | `ui/AIAgentUI/IPC/IPCClient.swift` |
| Doc Path | `projects/personal-macos-ai-agent/files/ui/AIAgentUI/IPC/IPCClient.swift.md` |
| Language | Swift 6 |
| File Role | IPC Client Wrapper |
| Ownership | @individual-developer |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-01-18 |
| Last Major Edit (YYYY-MM-DD) | 2025-12 |
| Modified By | AI Agent (Codex) |
| WHY (Reason for last change) | Updated test coverage path reference |
| Lines of Code (LOC) | 278 |
| Cyclomatic Complexity | Medium |
| Test Coverage | 0% (Tests/AIAgentUITests/IPCTests/) |

---

## Purpose & Responsibilities

### What this file does
**Single-sentence summary:** High-level IPC client that provides a clean async/await interface for communicating with the Python backend via Unix Domain Sockets, with `@MainActor` isolation and `@Published` state for SwiftUI binding.

**Detailed responsibilities:**
- Wrap `SocketManager` with `@MainActor` isolation for UI-safe state updates
- Provide async/await interface for backend communication
- Manage connection lifecycle (connect, disconnect, reconnect)
- Send prompts to backend and track request IDs
- Handle streaming responses with incremental text updates
- Dispatch status updates, tool calls, and completion events via callbacks
- Publish connection state, streaming text, and errors for SwiftUI binding
- Filter responses by request ID to avoid mixing different prompts

### What this file must NOT do (boundaries)
**Out of scope:**
- Does NOT manage Unix socket I/O directly (handled by `SocketManager`)
- Does NOT parse JSON messages (handled by `MessageProtocol` and `StreamingParser`)
- Does NOT manage the backend process lifecycle (handled by `BackendLauncher`)
- Does NOT implement UI rendering (consumed by `AppState` and views)

### Who/what calls it
| Caller | Purpose | Frequency | Error Handling |
|---|---|---|---|
| `AppState` | Backend communication | Per user prompt | Updates `@Published` error state |
| `ConnectionSettingsView` | Manual reconnect | User-driven | Displays error in UI |

### What it calls
| Callee | Purpose | Error Handling | Fallback Strategy |
|---|---|---|---|
| `SocketManager` | Unix socket I/O | Catches errors, updates state | Disconnects and notifies |
| `MessageDispatcher` | Route parsed messages | N/A | N/A |

---

## Imports / Dependencies

### Internal Dependencies
| Import Path | What's Used | Why Needed | Coupling Level | Risk/Notes |
|---|---|---|---|---|
| Foundation | Core types | Swift standard library | High | System framework |
| Combine | `ObservableObject`, `AnyCancellable` | Reactive state management | High | System framework |

### External Dependencies
| Package | Version | License | What's Used | Why Needed | Security Risk | Alternatives |
|---|---|---|---|---|---|---|
| Foundation | System | Apple | All | Swift standard library | Low | None |
| Combine | System | Apple | ObservableObject | Reactive bindings | Low | None |

---

## Public Surface (Document EVERYTHING Exposed)

### Exports / Public Symbols
| Symbol | Type (func/class/const/type) | Visibility | Status | Brief Description |
|---|---|---|---|---|
| `IPCClient` | class | internal | Stable | Main IPC client class |
| `IPCClient.mock` | static var | internal (DEBUG) | Stable | Mock disconnected client for previews |
| `IPCClient.mockConnected` | static var | internal (DEBUG) | Stable | Mock connected client for previews |

---

## Types (Classes / Structs / Enums / Interfaces)

### `IPCClient`
| Metadata | Value |
|---|---|
| Kind | class |
| Purpose | High-level IPC client with SwiftUI bindings |
| Thread-Safe | Yes (@MainActor isolated) |
| Immutable | No |
| Serializable | No |
| Related Types | SocketManager, MessageDispatcher, AgentStatus, ToolCall |

#### Inheritance & Implementation
- **Extends:** None
- **Implements:** `ObservableObject` (Combine)
- **Used By:** `AppState`
- **Polymorphic Behavior:** None

#### Invariants & Constraints
| Invariant | Enforcement | Violation Consequences |
|---|---|---|
| All state updates on main thread | `@MainActor` | Compile-time error |
| Only one active request at a time | `currentRequestId` tracking | Old responses ignored |
| Connection state synced with SocketManager | Combine subscription | Automatic |

#### Fields / Properties (@Published)
| Name | Type | Visibility | Default | Required | Mutable | Purpose | Validation | Notes |
|---|---|---|---|---|---|---|---|---|
| `isConnected` | `Bool` | private(set) | `false` | Yes | Yes | Connection status | N/A | Bound from SocketManager |
| `lastError` | `String?` | private(set) | `nil` | No | Yes | Most recent error | N/A | Displayed in UI |
| `streamingText` | `String` | private(set) | `""` | Yes | Yes | Accumulated response text | N/A | For active request only |
| `isStreaming` | `Bool` | private(set) | `false` | Yes | Yes | Whether streaming active | N/A | Controls UI state |

#### Fields / Properties (Private)
| Name | Type | Visibility | Default | Required | Mutable | Purpose | Validation | Notes |
|---|---|---|---|---|---|---|---|---|
| `socketManager` | `SocketManager` | private | `SocketManager()` | Yes | No | Underlying socket connection | N/A | `@unchecked Sendable` |
| `currentRequestId` | `String?` | private | `nil` | No | Yes | Active request tracker | N/A | For response filtering |
| `cancellables` | `Set<AnyCancellable>` | private | `[]` | Yes | Yes | Combine subscriptions | N/A | Auto-cleanup |

#### Fields / Properties (Callbacks)
| Name | Type | Visibility | Default | Required | Mutable | Purpose | Validation | Notes |
|---|---|---|---|---|---|---|---|---|
| `onStatusChange` | `((AgentStatus) -> Void)?` | public | `nil` | No | Yes | Agent status updates | N/A | Set by AppState |
| `onStreamUpdate` | `((String, Bool) -> Void)?` | public | `nil` | No | Yes | Streaming text + isDone flag | N/A | Set by AppState |
| `onToolCall` | `((ToolCall) -> Void)?` | public | `nil` | No | Yes | Tool execution notifications | N/A | Set by AppState |
| `onComplete` | `((String?) -> Void)?` | public | `nil` | No | Yes | Final response content | N/A | Set by AppState |
| `onError` | `((String) -> Void)?` | public | `nil` | No | Yes | Error notifications | N/A | Set by AppState |

#### Constructors
| Signature | Parameters | Preconditions | Postconditions | Throws/Errors |
|---|---|---|---|---|
| `init()` | None | None | `socketManager` initialized, callbacks set up | None |

#### Methods
| Method | Signature | Visibility | Parameters | Returns | Throws/Errors | Side Effects | Thread-Safe | Complexity | Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| `connect` | `func connect() async` | public | None | Void | None | Establishes socket connection | Yes | O(1) | Auto-discovers socket |
| `connect(toSocketPath:)` | `func connect(toSocketPath: String) async throws` | public | path | Void | Yes | Connects to specific socket | Yes | O(1) | Explicit path |
| `disconnect` | `func disconnect()` | public | None | Void | None | Closes socket | Yes | O(1) | Synchronous |
| `send(prompt:)` | `func send(prompt: String) async -> String?` | public | prompt | Request ID | None | Sends prompt to backend | Yes | O(1) | Returns nil on error |
| `cancel` | `func cancel() async` | public | None | Void | None | Cancels active request | Yes | O(1) | Sends cancel message |
| `reconnect` | `func reconnect() async` | public | None | Void | None | Disconnect + connect | Yes | O(1) | Convenience method |

#### Private Methods (Handlers)
| Method | Purpose | Parameters | Complexity |
|---|---|---|---|
| `setupCallbacks()` | Initialize SocketManager event handlers | None | O(1) |
| `handleStateChange(_:)` | Process socket state changes | SocketManager.ConnectionState | O(1) |
| `handleStatusUpdate(_:requestId:)` | Process agent status updates | AgentStatus, String | O(1) |
| `handleStreamingUpdate(requestId:text:isDone:)` | Process streaming chunks | String, String, Bool | O(1) |
| `handleToolCall(_:requestId:)` | Process tool call notifications | ToolCall, String | O(1) |
| `handleComplete(requestId:content:)` | Process completion | String, String? | O(1) |
| `handleError(_:requestId:code:)` | Process errors | String, String?, Int? | O(1) |

---

## Architecture & Design

### Layer Hierarchy
```
SwiftUI Views (@MainActor)
    ↓
AppState (@MainActor)
    ↓
IPCClient (@MainActor) ← This file
    ├── @Published properties → SwiftUI bindings
    └── Callbacks → AppState handlers
    ↓
SocketManager (@unchecked Sendable)
    ├── MessageDispatcher
    └── StreamingParser
    ↓
Unix Domain Socket (/tmp/ai-agent-*.sock)
    ↓
Python Backend (agent_host/main.py)
```

### Callback Flow
```
SocketManager (background thread)
    → onStateChange/onError callbacks
    → Task { @MainActor in ... }
        → handleStateChange/handleError
            → Update @Published properties
            → Call client callbacks (onStatusChange, onStreamUpdate, etc.)
                → AppState handlers
                    → Update UI state
```

### Request ID Filtering
```
send(prompt:) → currentRequestId = UUID
                    ↓
Backend Response → requestId in message
                    ↓
handleXXX checks: requestId == currentRequestId?
                    ↓ YES        ↓ NO
            Process response   Ignore (old request)
```

---

## State Management

### State Machine (Connection)
```
.disconnected ← Initial state
    ↓ connect()
.connecting
    ↓ onStateChange(.connected)
.connected
    ↓ send(prompt:)
.connected + isStreaming=true
    ↓ onComplete or onError
.connected + isStreaming=false
    ↓ disconnect()
.disconnected
```

### State Synchronization
| Source | Destination | Mechanism |
|---|---|---|
| SocketManager.connectionState | IPCClient.isConnected | Combine subscription |
| SocketManager.onError | IPCClient.lastError | Callback |
| MessageDispatcher.onStreamingUpdate | IPCClient.streamingText | Callback |

---

## Concurrency & Threading

### Swift 6 Concurrency
| Pattern | Location | Purpose |
|---|---|---|
| `@MainActor` | `IPCClient` class | All state updates on main thread |
| `@Published` | State properties | SwiftUI reactive bindings |
| `Task { @MainActor in }` | SocketManager callbacks | Actor hop to main thread |
| `async/await` | Public methods | Async communication |

### Thread Safety Mechanisms
- **@MainActor Isolation**: All public methods and properties main-thread-only
- **Callback Wrapping**: SocketManager callbacks wrapped in `Task { @MainActor in }`
- **No Data Races**: Single-threaded access to all mutable state

### Async Patterns
```swift
// Async methods for UI-friendly APIs
func connect() async { ... }
func send(prompt: String) async -> String? { ... }

// Callbacks wrapped for main-thread execution
socketManager.onStateChange = { [weak self] state in
    Task { @MainActor in
        self?.handleStateChange(state)
    }
}
```

---

## Error Handling Strategy

### Error Categories
| Category | Examples | Default Behavior | User Action |
|---|---|---|---|
| Connection Errors | Socket not found, connection refused | Update lastError, call onError | Check backend status, retry |
| Request Errors | Backend error response | Call onError, update status | Rephrase prompt |
| Timeout Errors | No response | Call onError | Check backend logs |

### Error Propagation
```
SocketManager.onError
    → IPCClient.handleError()
        → Update lastError @Published
        → Call onError callback
            → AppState.lastError
                → UI error banner
```

### Recovery Strategies
| Error Type | Recovery | Fallback | User Impact |
|---|---|---|---|
| Socket not found | Try reconnect() | Manual connection | Visible error message |
| Backend crash | Detect via socket close | Restart backend | Startup modal reappears |
| Malformed response | Log and ignore | Skip message | Possible incomplete response |

---

## Mock Support (Debug Only)

### `IPCClient.mock`
```swift
#if DEBUG
static var mock: IPCClient {
    let client = IPCClient()
    return client  // Disconnected, no backend
}
#endif
```

**Usage**: SwiftUI previews with disconnected state

### `IPCClient.mockConnected`
```swift
#if DEBUG
static var mockConnected: IPCClient {
    let client = IPCClient()
    // Note: Real implementation would inject fake SocketManager
    return client
}
#endif
```

**Usage**: SwiftUI previews with connected state (future enhancement)

---

## Related Documentation

### Related Files
| File Path | Relationship | Why Related |
|---|---|---|
| `ui/AIAgentUI/IPC/SocketManager.swift` | Uses | Low-level Unix socket I/O |
| `ui/AIAgentUI/IPC/MessageProtocol.swift` | Uses | JSON-RPC message type definitions |
| `ui/AIAgentUI/IPC/StreamingParser.swift` | Uses | Incremental JSON parsing |
| `ui/AIAgentUI/State/AppState.swift` | Used by | Main consumer of IPCClient |
| `ui/AIAgentUI/State/AgentStatus.swift` | Uses | Status enum type |
| `ui/AIAgentUI/State/Message.swift` | Uses | ToolCall type |

---

## Technical Decisions

### Decision: ObservableObject vs Actor
**Chosen**: `@MainActor class` (ObservableObject)

**Rationale**:
- SwiftUI requires `@Published` properties for reactive bindings
- All UI state must update on main thread anyway
- Actor would require `await` for every property access
- `@MainActor` isolation prevents data races while keeping API simple
- Direct property binding: `@ObservedObject var ipcClient`

### Decision: Callback Closures + @Published
**Chosen**: Hybrid approach (both patterns)

**Rationale**:
- **@Published**: Best for simple state (`isConnected`, `lastError`)
  - Direct SwiftUI binding with `$ipcClient.isConnected`
  - Automatic re-renders on change
- **Callbacks**: Better for events (`onStatusChange`, `onToolCall`)
  - Allows custom handling in AppState
  - Can trigger complex logic (update messages, log events)
  - More flexible than Combine publishers for event streams

### Decision: Request ID Filtering
**Rationale**:
- Backend may send late responses from cancelled/previous requests
- Prevents mixing content from different prompts
- `currentRequestId` tracks active request
- `nil` check allows processing when no request tracked (edge case)

Example:
```
User sends "Find Python files" → requestId=A
  → Backend starts processing
User cancels, sends "Open Safari" → requestId=B
  → Backend finishes A, sends response
  → handleComplete checks: "A" == "B"? NO → Ignore
```

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2025-12 | AI Agent | Initial implementation | Created high-level IPC client wrapper with @MainActor isolation | High - Core IPC layer |
| 2026-01-18 | AI Agent (Claude) | Documentation | Created comprehensive documentation with proper table format | None - Docs only |
