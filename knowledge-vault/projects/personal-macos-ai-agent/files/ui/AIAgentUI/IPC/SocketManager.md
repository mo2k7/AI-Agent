# File Doc: `ui/AIAgentUI/IPC/SocketManager.swift`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `ui/AIAgentUI/IPC/SocketManager.swift` |
| Doc Path | `projects/personal-macos-ai-agent/files/ui/AIAgentUI/IPC/SocketManager.md` |
| Language | Swift |
| File Role | Low-Level Unix Socket Communication |
| Ownership | Core Team |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-01-18 |
| Last Major Edit (YYYY-MM-DD) | 2026-01-18 |
| Modified By | AI Agent (Codex) |
| WHY (Reason for last change) | Updated test path references to Tests/ layout |
| Lines of Code (LOC) | 316 |
| Cyclomatic Complexity | Medium |
| Test Coverage | 0% |

---

## Purpose & Responsibilities

### What this file does
**Single-sentence summary:**
Low-level Unix Domain Socket manager using Apple's Network framework for IPC communication with the Python backend.

**Detailed responsibilities:**
- Manages `NWConnection` for Unix Domain Socket communication
- Auto-discovers socket files in `/tmp/ai-agent-*.sock`
- Handles connection state transitions
- Sends newline-delimited JSON messages
- Receives and parses incoming messages
- Provides typed error handling via `SocketError`
- Supports reconnection and graceful disconnection

### What this file must NOT do (boundaries)
**Out of scope:**
- Message parsing/routing (handled by `MessageProtocol`)
- High-level API (handled by `IPCClient`)
- State management (handled by `AppState`)
- Protocol definitions

### Who/what calls it
| Caller | Purpose | Frequency | Error Handling |
|---|---|---|---|
| `IPCClient` | All socket operations | On every IPC operation | SocketError |

### What it calls
| Callee | Purpose | Error Handling | Fallback Strategy |
|---|---|---|---|
| `Network.NWConnection` | Socket I/O | NWError to SocketError | Reconnection |
| `FileManager` | Socket file discovery | Ignore missing files | Return nil |
| `StreamingParser` | Parse incoming data | Parse errors logged | N/A |

---

## Imports / Dependencies

### Framework Dependencies
| Framework | What's Used | Why Needed |
|---|---|---|
| Foundation | FileManager, Data | File operations |
| Network | NWConnection, NWEndpoint | Socket communication |

### Internal Dependencies
| Import Path | What's Used | Why Needed | Coupling Level |
|---|---|---|---|
| Same module | `StreamingParser` | Parse incoming messages | Medium |

---

## Public Surface (Document EVERYTHING Exposed)

### Exports / Public Symbols
| Symbol | Type (func/class/const/type) | Visibility | Status | Brief Description |
|---|---|---|---|---|
| `SocketManager` | class | public | Stable | Unix socket manager |
| `ConnectionState` | enum | public | Stable | Socket connection states |
| `SocketError` | enum | public | Stable | Socket error types |

---

## Types (Classes / Structs / Enums / Interfaces)

### `ConnectionState`
| Metadata | Value |
|---|---|
| Kind | enum |
| Purpose | Represents the socket connection state |
| Thread-Safe | Yes (immutable) |
| Immutable | Yes |
| Serializable | No |

#### Cases
| Case | Purpose | Transitions To |
|---|---|---|
| `disconnected` | Not connected | connecting |
| `connecting` | Connection in progress | connected, failed |
| `connected` | Active connection | disconnected |
| `failed(SocketError)` | Connection failed | disconnected, connecting |

---

### `SocketError`
| Metadata | Value |
|---|---|
| Kind | enum |
| Purpose | Typed socket errors with localized descriptions |
| Thread-Safe | Yes (immutable) |
| Immutable | Yes |
| Serializable | No |

#### Inheritance & Implementation
- **Extends:** N/A
- **Implements:** `Error`, `LocalizedError`

#### Cases
| Case | Associated Value | Description | User Message |
|---|---|---|---|
| `socketNotFound` | None | No socket file exists | "AI Agent server is not running" |
| `connectionFailed(String)` | Error message | Connection attempt failed | "Connection failed: {message}" |
| `connectionLost` | None | Connection dropped | "Connection to server was lost" |
| `sendFailed(String)` | Error message | Failed to send data | "Failed to send: {message}" |
| `receiveFailed(String)` | Error message | Failed to receive data | "Failed to receive: {message}" |
| `invalidData` | None | Received unparseable data | "Received invalid data" |

#### LocalizedError Implementation
```swift
var errorDescription: String? {
    switch self {
    case .socketNotFound:
        return "AI Agent server is not running. Please start the server first."
    case .connectionFailed(let msg):
        return "Connection failed: \(msg)"
    case .connectionLost:
        return "Connection to the AI Agent server was lost."
    case .sendFailed(let msg):
        return "Failed to send message: \(msg)"
    case .receiveFailed(let msg):
        return "Failed to receive message: \(msg)"
    case .invalidData:
        return "Received invalid data from server."
    }
}
```

---

### `SocketManager`
| Metadata | Value |
|---|---|
| Kind | class |
| Purpose | Manages Unix Domain Socket connection |
| Thread-Safe | No (use from single queue) |
| Immutable | No |
| Serializable | No |
| Related Types | `ConnectionState`, `SocketError`, `NWConnection` |

#### Fields / Properties
| Name | Type | Visibility | Default | Required | Mutable | Purpose | Validation | Notes |
|---|---|---|---|---|---|---|---|---|
| `connection` | NWConnection? | private | `nil` | No | Yes | Active connection | N/A | |
| `state` | ConnectionState | public | `.disconnected` | N/A | Yes | Current state | N/A | Observable |
| `socketPath` | String? | private | `nil` | No | Yes | Discovered socket path | N/A | |
| `queue` | DispatchQueue | private | `.main` | N/A | No | Callback queue | N/A | |
| `parser` | StreamingParser | private | `StreamingParser()` | N/A | No | Message parser | N/A | |
| `onMessage` | `((Data) -> Void)?` | public | `nil` | No | Yes | Message callback | N/A | |
| `onStateChange` | `((ConnectionState) -> Void)?` | public | `nil` | No | Yes | State callback | N/A | |
| `onError` | `((SocketError) -> Void)?` | public | `nil` | No | Yes | Error callback | N/A | |

#### Methods
| Method | Signature | Visibility | Parameters | Returns | Throws/Errors | Side Effects | Thread-Safe | Complexity | Notes |
|---|---|---|---|---|---|---|---|---|---|
| `connect` | `()` | public | None | None | Never (callbacks) | Starts connection | No | O(1) | Async via callbacks |
| `disconnect` | `()` | public | None | None | Never | Closes connection | No | O(1) | |
| `sendPrompt` | `(text: String)` | public | Prompt text | None | Never (callbacks) | Sends to socket | No | O(n) | |
| `sendCancel` | `()` | public | None | None | Never | Sends cancel | No | O(1) | |
| `send` | `(data: Data)` | public | Raw data | None | Never (callbacks) | Sends bytes | No | O(n) | |
| `discoverSocket` | `() -> String?` | private | None | Socket path | Never | Searches /tmp | No | O(n) | |
| `setupConnection` | `(endpoint: NWEndpoint)` | private | Endpoint | None | Never | Creates NWConnection | No | O(1) | |
| `receiveMessages` | `()` | private | None | None | Never | Starts receive loop | No | O(1) | |
| `handleReceived` | `(data: Data)` | private | Received bytes | None | Never | Parses messages | No | O(n) | |

---

## Socket Discovery

### Socket Path Pattern
```
/tmp/ai-agent-{pid}.sock
```

### Discovery Algorithm
```swift
private func discoverSocket() -> String? {
    let fileManager = FileManager.default
    let tmpDir = "/tmp"
    
    do {
        let files = try fileManager.contentsOfDirectory(atPath: tmpDir)
        
        // Find all matching socket files
        let socketFiles = files
            .filter { $0.hasPrefix("ai-agent-") && $0.hasSuffix(".sock") }
            .map { "\(tmpDir)/\($0)" }
        
        // Return most recent (highest modification date)
        return socketFiles
            .compactMap { path -> (String, Date)? in
                guard let attrs = try? fileManager.attributesOfItem(atPath: path),
                      let date = attrs[.modificationDate] as? Date else {
                    return nil
                }
                return (path, date)
            }
            .sorted { $0.1 > $1.1 }
            .first?.0
    } catch {
        return nil
    }
}
```

---

## Connection Lifecycle

### State Transitions
```
[disconnected] --connect()--> [connecting]
                                   |
                    +------+-------+-------+
                    |                      |
                success                 failure
                    |                      |
              [connected]         [failed(error)]
                    |                      |
         disconnect() or error      connect() retry
                    |                      |
              [disconnected] <-------------+
```

### Connection Setup
```swift
func connect() {
    guard state == .disconnected || state.isFailed else { return }
    
    state = .connecting
    onStateChange?(.connecting)
    
    guard let path = discoverSocket() else {
        let error = SocketError.socketNotFound
        state = .failed(error)
        onError?(error)
        onStateChange?(.failed(error))
        return
    }
    
    socketPath = path
    let endpoint = NWEndpoint.unix(path: path)
    setupConnection(endpoint: endpoint)
}
```

### NWConnection Configuration
```swift
private func setupConnection(endpoint: NWEndpoint) {
    let parameters = NWParameters()
    parameters.allowLocalEndpointReuse = true
    
    connection = NWConnection(to: endpoint, using: parameters)
    
    connection?.stateUpdateHandler = { [weak self] newState in
        self?.handleStateUpdate(newState)
    }
    
    connection?.start(queue: queue)
}

private func handleStateUpdate(_ newState: NWConnection.State) {
    switch newState {
    case .ready:
        state = .connected
        onStateChange?(.connected)
        receiveMessages()
        
    case .failed(let error):
        let socketError = SocketError.connectionFailed(error.localizedDescription)
        state = .failed(socketError)
        onError?(socketError)
        onStateChange?(.failed(socketError))
        
    case .cancelled:
        state = .disconnected
        onStateChange?(.disconnected)
        
    default:
        break
    }
}
```

---

## Message Protocol

### Send Format
```
{"jsonrpc": "2.0", "id": "uuid", "method": "prompt", "params": {"text": "Hello"}}\n
```

### Receive Format
Messages are newline-delimited JSON. The `StreamingParser` accumulates partial data and emits complete messages.

### Send Implementation
```swift
func send(data: Data) {
    guard state == .connected, let connection = connection else {
        onError?(.connectionLost)
        return
    }
    
    // Ensure newline delimiter
    var sendData = data
    if !data.last.map({ $0 == 0x0A }) ?? false {
        sendData.append(0x0A)
    }
    
    connection.send(content: sendData, completion: .contentProcessed { [weak self] error in
        if let error = error {
            self?.onError?(.sendFailed(error.localizedDescription))
        }
    })
}
```

---

## Error Handling Strategy

### Error Mapping
| NWError | SocketError | Recovery |
|---|---|---|
| `posix(.ENOENT)` | `.socketNotFound` | Wait for server |
| `posix(.ECONNREFUSED)` | `.connectionFailed` | Retry |
| `posix(.EPIPE)` | `.connectionLost` | Reconnect |
| Other | `.connectionFailed` | Log and retry |

### Error Recovery
```swift
// In IPCClient
func handleError(_ error: SocketError) {
    switch error {
    case .socketNotFound:
        // Server not running - show UI message
        break
        
    case .connectionLost:
        // Try to reconnect after delay
        DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
            self.socketManager.connect()
        }
        
    case .connectionFailed:
        // Try again after delay
        DispatchQueue.main.asyncAfter(deadline: .now() + 5) {
            self.socketManager.connect()
        }
        
    default:
        break
    }
}
```

---

## Testing Documentation

### Unit Test Coverage
| Function/Class | Coverage | Test Location | Edge Cases Covered |
|---|---|---|---|
| All | 0% | `Tests/AIAgentUITests/IPCTests/` | None yet |

### Testing Strategies
- Mock NWConnection for unit tests
- Use local Unix socket for integration tests
- Test socket discovery with temporary files
- Test error handling with forced failures

---

## Related Documentation

### Related Files
| File Path | Relationship | Why Related |
|---|---|---|
| `ui/AIAgentUI/IPC/IPCClient.swift` | Used by | High-level wrapper |
| `ui/AIAgentUI/IPC/StreamingParser.swift` | Uses | Message parsing |
| `ui/AIAgentUI/IPC/MessageProtocol.swift` | Uses | Request creation |
| `agent_host/ipc/server.py` | Server | Creates socket |

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-01-18 | AI Assistant | Initial implementation | Created socket manager | New file |
