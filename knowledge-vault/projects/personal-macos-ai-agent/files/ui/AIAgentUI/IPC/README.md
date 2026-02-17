# IPC Module Documentation

This document provides comprehensive documentation for all IPC (Inter-Process Communication) files in the `ui/AIAgentUI/IPC/` directory.

---

## Module Overview

| File | Purpose | Lines |
|---|---|---|
| `IPCClient.swift` | High-level async interface | 272 |
| `SocketManager.swift` | Unix socket management | 316 |
| `MessageProtocol.swift` | Message type definitions | 306 |
| `StreamingParser.swift` | Message parsing utilities | 232 |

---

# MessageProtocol.swift

## File Metadata
| Field | Value |
|---|---|
| Lines of Code | ~320 |
| Last Edited | 2026-01-18 |
| Last Major Edit | 2026-01-18 |
| Modified By | AI Agent (Claude) |
| WHY | Fixed IPC-001 (prompt parameter); added PingRequest for health checks |

## Purpose
Defines message types for IPC communication, mirroring Python `protocol.py`.

## Session 3 Changes

### Bug IPC-001: "Missing 'prompt' parameter" Error
**Problem:** All prompt requests to Python backend failed with "Invalid params: Missing 'prompt' parameter".

**Root Cause:** Swift `PromptParams` struct used property name `text`, but Python backend expected `prompt`.

**Fix:**
```swift
// BEFORE (buggy)
struct PromptParams: Encodable {
    let text: String  // ❌ Wrong property name
    let stream: Bool
}

// AFTER (fixed)
struct PromptParams: Encodable {
    let prompt: String  // ✅ Matches Python backend expectation
    let stream: Bool
}
```

### Feature: PingRequest for Health Checks
Added new request type for startup health checks:
```swift
struct PingRequest: Encodable {
    let jsonrpc: String = kJSONRPCVersion
    let id: String
    let method: String = "ping"
}
```

## Types

### Request Types

#### `IPCRequest`
Base request structure.
```swift
struct IPCRequest: Encodable {
    let jsonrpc: String = "2.0"
    let id: String
    let method: String
    let params: [String: AnyCodable]?
}
```

#### `PromptRequest`
User prompt request.
```swift
// Session 3 fix: Changed "text" to "prompt" to match Python backend
static func prompt(id: String, text: String) -> IPCRequest {
    IPCRequest(
        id: id,
        method: "prompt",
        params: ["prompt": AnyCodable(text)]  // KEY: Must be "prompt", not "text"
    )
}
```

#### `PingRequest` (Session 3)
Health check request for startup validation.
```swift
struct PingRequest: Encodable {
    let jsonrpc: String = kJSONRPCVersion
    let id: String
    let method: String = "ping"
}
```

#### `CancelRequest`
Cancel current operation.
```swift
static func cancel(id: String) -> IPCRequest {
    IPCRequest(
        id: id,
        method: "cancel",
        params: nil
    )
}
```

### Response Types

#### `StatusResponse`
```swift
struct StatusResponse: Decodable {
    let type: String  // "status"
    let status: String
    let detail: String?
}
```

#### `StreamResponse`
```swift
struct StreamResponse: Decodable {
    let type: String  // "stream"
    let delta: String
    let done: Bool
}
```

#### `ToolCallResponse`
```swift
struct ToolCallResponse: Decodable {
    let type: String  // "tool_call"
    let tool: ToolCallData
    
    struct ToolCallData: Decodable {
        let name: String
        let arguments: [String: AnyCodable]
        let status: String
        let result: String?
        let error: String?
    }
}
```

#### `ResultResponse`
```swift
struct ResultResponse: Decodable {
    let type: String  // "result"
    let result: ResultData
    
    struct ResultData: Decodable {
        let content: String
        let tool_calls: [ToolCallData]?
    }
}
```

### Utility Types

#### `IPCMessageParser`
Routes incoming JSON to appropriate type.
```swift
enum IPCMessageParser {
    static func parse(_ data: Data) -> ParsedMessage? {
        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let type = json["type"] as? String else {
            return nil
        }
        
        switch type {
        case "status": return .status(try? decode(StatusResponse.self, from: data))
        case "stream": return .stream(try? decode(StreamResponse.self, from: data))
        case "tool_call": return .toolCall(try? decode(ToolCallResponse.self, from: data))
        case "result": return .result(try? decode(ResultResponse.self, from: data))
        case "error": return .error(try? decode(ErrorResponse.self, from: data))
        default: return nil
        }
    }
}
```

#### `AnyCodable`
Type-erased JSON value wrapper.
```swift
struct AnyCodable: Codable {
    let value: Any
    
    init(_ value: Any) { self.value = value }
    
    // Supports: String, Int, Double, Bool, Array, Dictionary, nil
}
```

---

# StreamingParser.swift

## File Metadata
| Field | Value |
|---|---|
| Lines of Code | 232 |
| Last Edited | 2026-01-18 |

## Purpose
Utilities for parsing newline-delimited JSON and accumulating streamed text.

## Types

### `StreamingParser`
Buffers incoming data and emits complete JSON messages.

#### Properties
| Name | Type | Purpose |
|---|---|---|
| `buffer` | Data | Incomplete message buffer |
| `delimiter` | UInt8 | Newline character (0x0A) |

#### Methods
| Method | Returns | Purpose |
|---|---|---|
| `append(_ data: Data)` | `[Data]` | Add data, return complete messages |
| `reset()` | None | Clear buffer |

#### Implementation
```swift
class StreamingParser {
    private var buffer = Data()
    private let delimiter: UInt8 = 0x0A  // \n
    
    func append(_ data: Data) -> [Data] {
        buffer.append(data)
        
        var messages: [Data] = []
        
        while let newlineIndex = buffer.firstIndex(of: delimiter) {
            let messageData = buffer.prefix(upTo: newlineIndex)
            messages.append(Data(messageData))
            buffer.removeSubrange(...newlineIndex)
        }
        
        return messages
    }
}
```

### `StreamAccumulator`
Accumulates streaming text chunks.

#### Properties
| Name | Type | Purpose |
|---|---|---|
| `text` | String | Accumulated text |
| `isComplete` | Bool | Done flag received |
| `requestId` | String | Request correlation |

#### Methods
| Method | Purpose |
|---|---|
| `append(_ delta: String)` | Add text chunk |
| `markComplete()` | Set done flag |
| `reset()` | Clear for reuse |

### `MessageDispatcher`
Routes parsed messages to handlers.

#### Callback Properties
| Property | Signature | Purpose |
|---|---|---|
| `onStatus` | `(StatusResponse) -> Void` | Status updates |
| `onStream` | `(StreamResponse) -> Void` | Stream chunks |
| `onToolCall` | `(ToolCallResponse) -> Void` | Tool calls |
| `onResult` | `(ResultResponse) -> Void` | Final results |
| `onError` | `(ErrorResponse) -> Void` | Errors |

---

## Protocol Alignment

### Python → Swift Type Mapping

| Python (protocol.py) | Swift (MessageProtocol.swift) |
|---|---|
| `StatusUpdate` | `StatusResponse` |
| `StreamChunk` | `StreamResponse` |
| `ToolCallNotification` | `ToolCallResponse` |
| `ResultMessage` | `ResultResponse` |
| `ErrorMessage` | `ErrorResponse` |
| `IncomingRequest` | `IPCRequest` |

### Message Format
```json
{"jsonrpc": "2.0", "id": "uuid", "type": "status", "status": "thinking", "detail": null}\n
```

### Field Mapping

#### StatusUpdate/StatusResponse
| Python Field | Swift Field |
|---|---|
| `type` | `type` |
| `status` | `status` |
| `detail` | `detail` |

#### StreamChunk/StreamResponse
| Python Field | Swift Field |
|---|---|
| `type` | `type` |
| `delta` | `delta` |
| `done` | `done` |

#### ToolCallNotification/ToolCallResponse
| Python Field | Swift Field |
|---|---|
| `type` | `type` |
| `tool.name` | `tool.name` |
| `tool.arguments` | `tool.arguments` |
| `tool.status` | `tool.status` |
| `tool.result` | `tool.result` |
| `tool.error` | `tool.error` |

---

## Usage Example

### Complete Message Flow
```swift
// 1. Create socket manager
let socketManager = SocketManager()

// 2. Create streaming parser
let parser = StreamingParser()
let accumulator = StreamAccumulator(requestId: "req-123")

// 3. Handle incoming data
socketManager.onData = { data in
    let messages = parser.append(data)
    
    for messageData in messages {
        if let parsed = IPCMessageParser.parse(messageData) {
            switch parsed {
            case .status(let response):
                print("Status: \(response?.status ?? "unknown")")
                
            case .stream(let response):
                if let resp = response {
                    accumulator.append(resp.delta)
                    if resp.done {
                        accumulator.markComplete()
                    }
                }
                
            case .toolCall(let response):
                if let resp = response {
                    let toolCall = ToolCall(
                        name: resp.tool.name,
                        arguments: convertArguments(resp.tool.arguments),
                        status: ToolCallStatus.from(rawValue: resp.tool.status)
                    )
                    // Handle tool call
                }
                
            case .result(let response):
                print("Final result: \(response?.result.content ?? "")")
                
            case .error(let response):
                print("Error: \(response?.error.message ?? "unknown")")
            }
        }
    }
}

// 4. Send request
let request = IPCRequest.prompt(id: "req-123", text: "Hello!")
let data = try JSONEncoder().encode(request)
socketManager.send(data: data)
```

---

## Error Handling

### Parse Errors
```swift
if let parsed = IPCMessageParser.parse(data) {
    // Handle message
} else {
    print("Failed to parse message")
}
```

### Decoding Errors
```swift
do {
    let response = try JSONDecoder().decode(StatusResponse.self, from: data)
} catch {
    print("Decoding error: \(error)")
}
```

---

## Related Documentation

| File Path | Relationship |
|---|---|
| `agent_host/ipc/protocol.py` | Python mirror |
| `ui/AIAgentUI/IPC/IPCClient.swift` | Uses |
| `ui/AIAgentUI/IPC/SocketManager.swift` | Uses |

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-01-18 | AI Assistant | Initial implementation | Created IPC types | New files |
| 2026-01-18 | AI Agent (Claude) | Bug fix IPC-001 | MessageProtocol: Changed PromptParams.text to .prompt to match Python backend | High |
| 2026-01-18 | AI Agent (Claude) | Health check feature | MessageProtocol: Added PingRequest struct; SocketManager: Added sendPing(); IPCClient: Added ping() | Low |
