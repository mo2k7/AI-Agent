# File Doc: `ui/AIAgentUI/IPC/IPCClient.swift`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `ui/AIAgentUI/IPC/IPCClient.swift` |
| Doc Path | `projects/personal-macos-ai-agent/files/ui/AIAgentUI/IPC/IPCClient.md` |
| Language | Swift |
| File Role | High-Level IPC Communication Interface |
| Ownership | Core Team |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-01-18 |
| Last Major Edit (YYYY-MM-DD) | 2026-01-18 |
| Modified By | AI Agent (Codex) |
| WHY (Reason for last change) | Updated test path references to Tests/ layout |
| Lines of Code (LOC) | 272 |
| Cyclomatic Complexity | Medium |
| Test Coverage | 0% |

---

## Purpose & Responsibilities

### What this file does
**Single-sentence summary:**
High-level async interface for communicating with the Python backend over Unix Domain Socket IPC.

**Detailed responsibilities:**
- Wraps `SocketManager` with a clean async API
- Provides callback-based event handling for status, streaming, tool calls, completion, and errors
- Manages connection lifecycle (connect, disconnect, reconnect)
- Sends prompt and cancel requests to backend
- Converts low-level socket events to typed callbacks
- Handles connection state tracking

### What this file must NOT do (boundaries)
**Out of scope:**
- Low-level socket operations (delegated to `SocketManager`)
- Message parsing (handled by `MessageProtocol`)
- State management (handled by `AppState`)
- UI rendering

### Who/what calls it
| Caller | Purpose | Frequency | Error Handling |
|---|---|---|---|
| `AppState` | Communication with backend | On user actions | Via error callback |

### What it calls
| Callee | Purpose | Error Handling | Fallback Strategy |
|---|---|---|---|
| `SocketManager` | Socket operations | SocketError passed to callback | Reconnection |
| `MessageProtocol` | Request creation | N/A | N/A |

---

## Imports / Dependencies

### Framework Dependencies
| Framework | What's Used | Why Needed |
|---|---|---|
| Foundation | Basic types | Core functionality |
| Combine | Publishers | Event handling (optional) |

### Internal Dependencies
| Import Path | What's Used | Why Needed | Coupling Level |
|---|---|---|---|
| Same module | `SocketManager`, `PromptRequest`, `CancelRequest` | IPC layer | High |
| Same module | `ToolCall`, `AgentStatus` | Type definitions | Medium |

---

## Public Surface (Document EVERYTHING Exposed)

### Exports / Public Symbols
| Symbol | Type (func/class/const/type) | Visibility | Status | Brief Description |
|---|---|---|---|---|
| `IPCClient` | class | public | Stable | High-level IPC interface |

---

## Types (Classes / Structs / Enums / Interfaces)

### `IPCClient`
| Metadata | Value |
|---|---|
| Kind | class |
| Purpose | High-level async interface for backend communication |
| Thread-Safe | No (use from MainActor) |
| Immutable | No |
| Serializable | No |
| Related Types | `SocketManager`, `AppState` |

#### Fields / Properties
| Name | Type | Visibility | Default | Required | Mutable | Purpose | Validation | Notes |
|---|---|---|---|---|---|---|---|---|
| `socketManager` | SocketManager | private | `SocketManager()` | No | No | Low-level socket | N/A | |
| `isConnected` | Bool | public | `false` | N/A | Yes | Connection state | N/A | Read-only externally |
| `onStatusChange` | `((String, String?) -> Void)?` | public | `nil` | No | Yes | Status update callback | N/A | (status, detail) |
| `onStreamUpdate` | `((String) -> Void)?` | public | `nil` | No | Yes | Stream chunk callback | N/A | (delta) |
| `onToolCall` | `((ToolCall) -> Void)?` | public | `nil` | No | Yes | Tool call callback | N/A | |
| `onComplete` | `((String?) -> Void)?` | public | `nil` | No | Yes | Completion callback | N/A | (result) |
| `onError` | `((String) -> Void)?` | public | `nil` | No | Yes | Error callback | N/A | (message) |
| `onConnectionChange` | `((Bool) -> Void)?` | public | `nil` | No | Yes | Connection state callback | N/A | (connected) |

#### Methods
| Method | Signature | Visibility | Parameters | Returns | Throws/Errors | Side Effects | Thread-Safe | Complexity | Notes |
|---|---|---|---|---|---|---|---|---|---|
| `connect` | `() async` | public | None | None | Never | Starts socket connection | No | O(1) | |
| `disconnect` | `() async` | public | None | None | Never | Closes connection | No | O(1) | |
| `reconnect` | `() async` | public | None | None | Never | Disconnect + connect | No | O(1) | |
| `send` | `(prompt: String) async` | public | User prompt | None | Never | Sends to backend | No | O(1) | |
| `cancel` | `() async` | public | None | None | Never | Sends cancel request | No | O(1) | |
| `setupSocketCallbacks` | `() private` | private | None | None | Never | Wires socket events | No | O(1) | Called in init |

#### Callbacks Detail

##### `onStatusChange`
```swift
var onStatusChange: ((String, String?) -> Void)?

// Called with:
// - status: Raw status string ("idle", "thinking", "calling_tool", etc.)
// - detail: Optional context (tool name for "calling_tool", error message for "error")

// Example:
client.onStatusChange = { status, detail in
    let agentStatus = AgentStatus.from(rawStatus: status, detail: detail)
    appState.status = agentStatus
}
```

##### `onStreamUpdate`
```swift
var onStreamUpdate: ((String) -> Void)?

// Called with:
// - delta: The text chunk to append

// Example:
client.onStreamUpdate = { delta in
    appState.streamingText += delta
}
```

##### `onToolCall`
```swift
var onToolCall: ((ToolCall) -> Void)?

// Called with:
// - toolCall: Complete ToolCall struct with name, arguments, status

// Example:
client.onToolCall = { toolCall in
    appState.currentToolCall = toolCall
}
```

##### `onComplete`
```swift
var onComplete: ((String?) -> Void)?

// Called with:
// - result: Optional final result content

// Example:
client.onComplete = { result in
    appState.finalizeMessage()
    appState.status = .idle
}
```

##### `onError`
```swift
var onError: ((String) -> Void)?

// Called with:
// - message: Error description

// Example:
client.onError = { message in
    appState.lastError = message
    appState.status = .error(message: message)
}
```

---

## Example Usage

### Basic Setup
```swift
let client = IPCClient()

// Set up callbacks
client.onStatusChange = { status, detail in
    print("Status: \(status), Detail: \(detail ?? "none")")
}

client.onStreamUpdate = { delta in
    print("Received: \(delta)", terminator: "")
}

client.onToolCall = { toolCall in
    print("Tool call: \(toolCall.name)")
}

client.onComplete = { result in
    print("Complete: \(result ?? "no result")")
}

client.onError = { error in
    print("Error: \(error)")
}

// Connect
await client.connect()

// Send prompt
await client.send(prompt: "Hello, AI!")

// Later: disconnect
await client.disconnect()
```

### Integration with AppState
```swift
// In AppState.swift
private func setupIPCCallbacks() {
    ipcClient.onStatusChange = { [weak self] status, detail in
        Task { @MainActor in
            self?.status = AgentStatus.from(rawStatus: status, detail: detail)
        }
    }
    
    ipcClient.onStreamUpdate = { [weak self] delta in
        Task { @MainActor in
            self?.streamingText += delta
        }
    }
    
    ipcClient.onToolCall = { [weak self] toolCall in
        Task { @MainActor in
            self?.currentToolCall = toolCall
        }
    }
    
    ipcClient.onComplete = { [weak self] result in
        Task { @MainActor in
            self?.finalizeStreamingMessage()
            self?.status = .complete
        }
    }
    
    ipcClient.onError = { [weak self] error in
        Task { @MainActor in
            self?.lastError = error
            self?.status = .error(message: error)
        }
    }
    
    ipcClient.onConnectionChange = { [weak self] connected in
        Task { @MainActor in
            self?.isConnected = connected
        }
    }
}
```

---

## Connection Lifecycle

### State Machine
```
[Disconnected] --connect()--> [Connecting] --success--> [Connected]
                                   |
                                 failure
                                   |
                              [Disconnected]

[Connected] --disconnect()--> [Disconnected]
[Connected] --error--> [Disconnected] --auto-reconnect?--> [Connecting]
```

### Auto-Discovery
The client uses `SocketManager` which auto-discovers socket files:
```
/tmp/ai-agent-*.sock
```

If multiple socket files exist, it connects to the most recent one.

---

## Error Handling Strategy

### Error Categories
| Category | Source | Handling | User Feedback |
|---|---|---|---|
| Socket Not Found | SocketManager | onError callback | "Server not running" |
| Connection Refused | SocketManager | onError callback | "Connection refused" |
| Parse Error | MessageProtocol | Log, ignore | None |
| Backend Error | Python server | onError callback | Error message displayed |

### Reconnection
```swift
// Manual reconnection
await client.reconnect()

// Automatic reconnection (in AppState)
client.onConnectionChange = { connected in
    if !connected {
        Task {
            try await Task.sleep(for: .seconds(2))
            await client.reconnect()
        }
    }
}
```

---

## Testing Documentation

### Unit Test Coverage
| Function/Class | Coverage | Test Location | Edge Cases Covered |
|---|---|---|---|
| All | 0% | `Tests/AIAgentUITests/IPCTests/` | None yet |

### Mock Implementation
```swift
class MockIPCClient: IPCClient {
    var lastSentPrompt: String?
    var connectCalled = false
    var disconnectCalled = false
    
    override func connect() async {
        connectCalled = true
        isConnected = true
        onConnectionChange?(true)
    }
    
    override func send(prompt: String) async {
        lastSentPrompt = prompt
        // Simulate response
        onStatusChange?("thinking", nil)
    }
}
```

---

## Related Documentation

### Related Files
| File Path | Relationship | Why Related |
|---|---|---|
| `ui/AIAgentUI/IPC/SocketManager.swift` | Uses | Low-level socket |
| `ui/AIAgentUI/IPC/MessageProtocol.swift` | Uses | Request creation |
| `ui/AIAgentUI/State/AppState.swift` | Used by | Primary consumer |
| `agent_host/ipc/server.py` | Server | Backend socket server |

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-01-18 | AI Assistant | Initial implementation | Created IPC client | New file |
| 2026-01-18 | AI Agent (Codex) | Ping handling | Await ping responses with timeout and isolate from prompt completion flow | Medium |
