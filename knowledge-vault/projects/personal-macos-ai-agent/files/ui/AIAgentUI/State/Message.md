# File Doc: `ui/AIAgentUI/State/Message.swift`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `ui/AIAgentUI/State/Message.swift` |
| Doc Path | `projects/personal-macos-ai-agent/files/ui/AIAgentUI/State/Message.md` |
| Language | Swift |
| File Role | Message and Tool Call Data Models |
| Ownership | Core Team |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-01-18 |
| Last Major Edit (YYYY-MM-DD) | 2026-01-18 |
| Modified By | AI Agent (Codex) |
| WHY (Reason for last change) | Updated test path references to Tests/ layout |
| Lines of Code (LOC) | 299 |
| Cyclomatic Complexity | Low |
| Test Coverage | 0% |

---

## Purpose & Responsibilities

### What this file does
**Single-sentence summary:**
Defines data models for chat messages, tool calls, and their associated types for the conversation UI.

**Detailed responsibilities:**
- Defines `Message` struct for conversation messages (user, assistant, system)
- Defines `MessageRole` enum for message sender identification
- Defines `ToolCall` struct for tool execution details
- Defines `ToolCallStatus` enum for tool execution states
- Defines `ArgumentValue` enum for type-safe JSON argument representation
- Provides Codable conformance for JSON serialization
- Provides ExpressibleByLiteral conformances for convenient initialization
- Supports streaming message state

### What this file must NOT do (boundaries)
**Out of scope:**
- Message persistence/storage
- Network serialization (handled by IPC layer)
- UI rendering

---

## Public Surface (Document EVERYTHING Exposed)

### Exports / Public Symbols
| Symbol | Type (func/class/const/type) | Visibility | Status | Brief Description |
|---|---|---|---|---|
| `Message` | struct | public | Stable | Chat message model |
| `MessageRole` | enum | public | Stable | Message sender role |
| `ToolCall` | struct | public | Stable | Tool execution details |
| `ToolCallStatus` | enum | public | Stable | Tool execution state |
| `ArgumentValue` | enum | public | Stable | Type-safe JSON value |

---

## Types (Classes / Structs / Enums / Interfaces)

### `Message`
| Metadata | Value |
|---|---|
| Kind | struct |
| Purpose | Represents a single message in the conversation |
| Thread-Safe | Yes (value type) |
| Immutable | Mostly (isStreaming mutable) |
| Serializable | Yes (Codable) |
| Related Types | `MessageRole`, `ToolCall` |

#### Inheritance & Implementation
- **Extends:** N/A
- **Implements:** `Identifiable`, `Equatable`, `Codable`
- **Used By:** `AppState`, `ResponseBubble`, `MessageListView`

#### Fields / Properties
| Name | Type | Visibility | Default | Required | Mutable | Purpose | Validation | Notes |
|---|---|---|---|---|---|---|---|---|
| `id` | UUID | public | `UUID()` | No | No | Unique identifier | N/A | For Identifiable |
| `role` | MessageRole | public | Required | Yes | No | Sender role | N/A | |
| `content` | String | public | Required | Yes | No | Message text | N/A | May be empty for tool-only |
| `timestamp` | Date | public | `Date()` | No | No | Creation time | N/A | |
| `toolCall` | ToolCall? | public | `nil` | No | No | Associated tool call | N/A | |
| `isStreaming` | Bool | public | `false` | No | Yes | Currently streaming | N/A | var for updates |

#### Computed Properties
| Property | Type | Purpose |
|---|---|---|
| `isUser` | Bool | True if role is .user |
| `isAssistant` | Bool | True if role is .assistant |
| `isSystem` | Bool | True if role is .system |
| `hasToolCall` | Bool | True if toolCall is not nil |
| `displayContent` | String | Content with streaming indicator |

#### Example Usage
```swift
// User message
let userMsg = Message(role: .user, content: "Search for Python files")

// Assistant message with tool call
let toolCall = ToolCall(
    name: "search_files",
    arguments: ["query": "*.py", "path": "/Documents"],
    status: .success,
    result: "Found 15 files"
)
let assistantMsg = Message(
    role: .assistant,
    content: "I found the files you requested.",
    toolCall: toolCall
)

// Streaming message
var streamingMsg = Message(role: .assistant, content: "", isStreaming: true)
streamingMsg.content += "Hello"  // Append streamed text
streamingMsg.isStreaming = false  // Mark complete
```

---

### `MessageRole`
| Metadata | Value |
|---|---|
| Kind | enum |
| Purpose | Identifies the sender of a message |
| Thread-Safe | Yes (immutable) |
| Immutable | Yes |
| Serializable | Yes (String rawValue) |

#### Cases
| Case | Raw Value | Purpose | UI Treatment |
|---|---|---|---|
| `user` | "user" | User's input | Right-aligned, user color |
| `assistant` | "assistant" | AI response | Left-aligned, assistant color |
| `system` | "system" | System message | Centered, muted color |

#### Computed Properties
| Property | Type | Purpose |
|---|---|---|
| `displayName` | String | Human-readable name |
| `iconName` | String | SF Symbol name |

---

### `ToolCall`
| Metadata | Value |
|---|---|
| Kind | struct |
| Purpose | Details of a tool execution |
| Thread-Safe | Yes (value type) |
| Immutable | Mostly (status, result, error mutable) |
| Serializable | Yes (Codable) |
| Related Types | `ToolCallStatus`, `ArgumentValue` |

#### Inheritance & Implementation
- **Extends:** N/A
- **Implements:** `Identifiable`, `Equatable`, `Codable`
- **Used By:** `Message`, `ToolCallCard`, `ActiveToolCallView`

#### Fields / Properties
| Name | Type | Visibility | Default | Required | Mutable | Purpose | Validation | Notes |
|---|---|---|---|---|---|---|---|---|
| `id` | UUID | public | `UUID()` | No | No | Unique identifier | N/A | |
| `name` | String | public | Required | Yes | No | Tool name | N/A | e.g., "search_files" |
| `arguments` | [String: ArgumentValue] | public | Required | Yes | No | Tool arguments | N/A | Key-value pairs |
| `status` | ToolCallStatus | public | `.pending` | No | Yes | Execution status | N/A | var |
| `result` | String? | public | `nil` | No | Yes | Success result | N/A | var |
| `error` | String? | public | `nil` | No | Yes | Error message | N/A | var |

#### Computed Properties
| Property | Type | Purpose |
|---|---|---|
| `isComplete` | Bool | True if status is success or failed |
| `hasResult` | Bool | True if result is not nil |
| `hasError` | Bool | True if error is not nil |

#### Example Usage
```swift
// Create pending tool call
var toolCall = ToolCall(
    name: "search_files",
    arguments: [
        "query": .string("*.swift"),
        "path": .string("/Users/dev"),
        "recursive": .bool(true)
    ]
)

// Update status
toolCall.status = .executing

// Mark success
toolCall.status = .success
toolCall.result = "Found 42 files"

// Or mark failed
toolCall.status = .failed
toolCall.error = "Permission denied"
```

---

### `ToolCallStatus`
| Metadata | Value |
|---|---|
| Kind | enum |
| Purpose | Represents the execution state of a tool call |
| Thread-Safe | Yes (immutable) |
| Immutable | Yes |
| Serializable | Yes (String rawValue) |

#### Cases
| Case | Raw Value | Purpose | Icon |
|---|---|---|---|
| `pending` | "pending" | Queued for execution | `clock` |
| `executing` | "executing" | Currently running | `gearshape` |
| `success` | "success" | Completed successfully | `checkmark.circle.fill` |
| `failed` | "failed" | Execution failed | `xmark.circle.fill` |

#### Computed Properties
| Property | Type | Purpose |
|---|---|---|
| `displayText` | String | Human-readable status |
| `iconName` | String | SF Symbol for status |
| `isComplete` | Bool | True if success or failed |
| `color` | Color | Status indicator color |

#### Static Method
| Method | Signature | Purpose |
|---|---|---|
| `from` | `(rawValue: String) -> ToolCallStatus` | Parse from string with default |

---

### `ArgumentValue`
| Metadata | Value |
|---|---|
| Kind | enum |
| Purpose | Type-safe representation of JSON argument values |
| Thread-Safe | Yes (value type) |
| Immutable | Yes |
| Serializable | Yes (Codable) |

#### Inheritance & Implementation
- **Extends:** N/A
- **Implements:** `Equatable`, `Codable`, `CustomStringConvertible`, `ExpressibleByStringLiteral`, `ExpressibleByIntegerLiteral`, `ExpressibleByBooleanLiteral`, `ExpressibleByArrayLiteral`, `ExpressibleByDictionaryLiteral`

#### Cases
| Case | Associated Type | Purpose | Example |
|---|---|---|---|
| `string(String)` | String | Text value | `"*.py"` |
| `int(Int)` | Int | Integer value | `42` |
| `double(Double)` | Double | Floating point | `3.14` |
| `bool(Bool)` | Bool | Boolean value | `true` |
| `array([ArgumentValue])` | Array | List of values | `["a", "b"]` |
| `dictionary([String: ArgumentValue])` | Dictionary | Nested object | `{"key": "value"}` |
| `null` | N/A | Null/nil value | `null` |

#### Accessor Methods
| Method | Signature | Returns | Purpose |
|---|---|---|---|
| `stringValue` | `() -> String?` | Optional String | Extract string or nil |
| `intValue` | `() -> Int?` | Optional Int | Extract int or nil |
| `doubleValue` | `() -> Double?` | Optional Double | Extract double or nil |
| `boolValue` | `() -> Bool?` | Optional Bool | Extract bool or nil |
| `arrayValue` | `() -> [ArgumentValue]?` | Optional Array | Extract array or nil |
| `dictionaryValue` | `() -> [String: ArgumentValue]?` | Optional Dict | Extract dict or nil |

#### CustomStringConvertible
```swift
var description: String {
    switch self {
    case .string(let s): return "\"\(s)\""
    case .int(let i): return String(i)
    case .double(let d): return String(d)
    case .bool(let b): return String(b)
    case .array(let a): return "[\(a.map { $0.description }.joined(separator: ", "))]"
    case .dictionary(let d): return "{\(d.map { "\"\($0)\": \($1.description)" }.joined(separator: ", "))}"
    case .null: return "null"
    }
}
```

#### Literal Conformances
```swift
// String literal
let arg: ArgumentValue = "hello"  // .string("hello")

// Integer literal
let arg: ArgumentValue = 42  // .int(42)

// Boolean literal
let arg: ArgumentValue = true  // .bool(true)

// Array literal
let arg: ArgumentValue = ["a", "b"]  // .array([.string("a"), .string("b")])

// Dictionary literal
let arg: ArgumentValue = ["key": "value"]  // .dictionary(["key": .string("value")])
```

#### Codable Implementation
```swift
init(from decoder: Decoder) throws {
    let container = try decoder.singleValueContainer()
    
    if container.decodeNil() {
        self = .null
    } else if let string = try? container.decode(String.self) {
        self = .string(string)
    } else if let int = try? container.decode(Int.self) {
        self = .int(int)
    } else if let double = try? container.decode(Double.self) {
        self = .double(double)
    } else if let bool = try? container.decode(Bool.self) {
        self = .bool(bool)
    } else if let array = try? container.decode([ArgumentValue].self) {
        self = .array(array)
    } else if let dict = try? container.decode([String: ArgumentValue].self) {
        self = .dictionary(dict)
    } else {
        throw DecodingError.dataCorruptedError(in: container, debugDescription: "Unknown type")
    }
}
```

---

## Example Usage

### Complete Conversation Flow
```swift
// Start with user message
var messages: [Message] = []

messages.append(Message(role: .user, content: "Find all Swift files"))

// Add streaming assistant message
var response = Message(role: .assistant, content: "", isStreaming: true)
messages.append(response)

// Stream content
response.content += "Let me search "
response.content += "for Swift files..."

// Add tool call
let toolCall = ToolCall(
    name: "search_files",
    arguments: ["query": "*.swift", "recursive": true],
    status: .executing
)
response.toolCall = toolCall

// Complete tool call
response.toolCall?.status = .success
response.toolCall?.result = "Found 25 files"

// Complete streaming
response.content += "\n\nI found 25 Swift files in your project."
response.isStreaming = false
```

---

## Testing Documentation

### Unit Test Coverage
| Function/Class | Coverage | Test Location | Edge Cases Covered |
|---|---|---|---|
| All | 0% | `Tests/AIAgentUITests/StateTests/` | None yet |

### Test Cases to Cover
- [ ] Message creation and computed properties
- [ ] ToolCall status transitions
- [ ] ArgumentValue Codable roundtrip
- [ ] ArgumentValue literal initialization
- [ ] ArgumentValue accessor methods

---

## Related Documentation

### Related Files
| File Path | Relationship | Why Related |
|---|---|---|
| `ui/AIAgentUI/State/AppState.swift` | Uses | Stores messages |
| `ui/AIAgentUI/Views/Components/ResponseBubble.swift` | Uses | Displays messages |
| `ui/AIAgentUI/Views/Components/ToolCallCard.swift` | Uses | Displays tool calls |
| `ui/AIAgentUI/IPC/MessageProtocol.swift` | Uses | Parses from JSON |

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-01-18 | AI Assistant | Initial implementation | Created message models | New file |
| 2026-01-18 | AI Assistant | Build fix | Added iconName to ToolCallStatus | API addition |
