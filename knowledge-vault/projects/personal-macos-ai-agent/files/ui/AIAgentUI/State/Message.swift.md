# File Doc: `ui/AIAgentUI/State/Message.swift`

## File Metadata
| Field | Value |
|---|---|
| Project | personal-macos-ai-agent |
| Code File Path | `ui/AIAgentUI/State/Message.swift` |
| Doc Path | `projects/personal-macos-ai-agent/files/ui/AIAgentUI/State/Message.swift.md` |
| Language | Swift 6 |
| File Role | data model |
| Ownership | @individual-developer |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-01-18 |
| Last Major Edit (YYYY-MM-DD) | 2026-01-18 |
| Modified By | AI Agent (Codex) |
| WHY (Reason for last change) | Updated test coverage path reference |
| Lines of Code (LOC) | 299 |
| Cyclomatic Complexity | Low |
| Test Coverage | 0% (Tests/AIAgentUITests/StateTests/) |

---

## Purpose & Responsibilities

### What this file does
**Single-sentence summary:** Defines data models for chat messages, tool calls, and argument values used throughout the UI.

**Detailed responsibilities:**
- Defines `Message` struct for chat conversation entries
- Defines `MessageRole` enum for sender identification (user/assistant/system)
- Defines `ToolCall` struct for representing agent tool invocations
- Defines `ToolCallStatus` enum for tool execution state
- Defines `ArgumentValue` enum for type-safe tool call arguments
- Provides factory methods for common message types
- Implements `Codable` for JSON serialization
- Implements literal expressibility for convenient `ArgumentValue` creation

### What this file must NOT do (boundaries)
**Out of scope:**
- Does NOT handle message display/rendering (see `ResponseBubble.swift`)
- Does NOT manage conversation state (see `AppState.swift`)
- Does NOT parse IPC messages (see `MessageProtocol.swift`)

### Who/what calls it
| Caller | Purpose | Frequency | Error Handling |
|---|---|---|---|
| `AppState.swift` | Stores and manages messages | Every user/assistant message | N/A |
| `MainPanelView.swift` | Displays messages | On every render | N/A |
| `ResponseBubble.swift` | Renders individual messages | Per message | N/A |
| `ToolCallCard.swift` | Displays tool calls | Per tool call | N/A |

---

## Imports / Dependencies

### External Dependencies
| Package | Version | License | What's Used | Why Needed | Security Risk | Alternatives |
|---|---|---|---|---|---|---|
| Foundation | System | Apple | `UUID`, `Date`, `Codable` | Identity, timestamps, serialization | Low | None |

---

## Public Surface (Document EVERYTHING Exposed)

### Exports / Public Symbols
| Symbol | Type | Visibility | Status | Brief Description |
|---|---|---|---|---|
| `Message` | struct | internal | Stable | Chat message model |
| `MessageRole` | enum | internal | Stable | Message sender role |
| `ToolCall` | struct | internal | Stable | Tool invocation model |
| `ToolCallStatus` | enum | internal | Stable | Tool execution state |
| `ArgumentValue` | enum | internal | Stable | Type-safe argument wrapper |

---

## Types (Classes / Structs / Enums / Interfaces)

### `Message`
| Metadata | Value |
|---|---|
| Kind | struct |
| Purpose | Represents a single chat message |
| Thread-Safe | Yes (Sendable, value type) |
| Immutable | Mostly (content, toolCall, isStreaming are mutable for streaming) |
| Serializable | Yes (Identifiable, Equatable) |
| Related Types | `MessageRole`, `ToolCall` |

#### Conformances
- `Identifiable` - For SwiftUI list rendering
- `Equatable` - For change detection
- `Sendable` - **Swift 6 fix**: For safe actor boundary crossing

#### Fields / Properties
| Name | Type | Visibility | Default | Required | Mutable | Purpose |
|---|---|---|---|---|---|---|
| `id` | `UUID` | public | `UUID()` | No | No | Unique identifier |
| `role` | `MessageRole` | public | - | Yes | No | Sender role |
| `content` | `String` | public | - | Yes | Yes | Message text |
| `timestamp` | `Date` | public | `Date()` | No | No | Creation time |
| `toolCall` | `ToolCall?` | public | `nil` | No | Yes | Associated tool call |
| `isStreaming` | `Bool` | public | `false` | No | Yes | Streaming in progress |

#### Factory Methods
| Method | Parameters | Returns | Description |
|---|---|---|---|
| `user(_:)` | `String` | `Message` | Creates user message |
| `assistant(_:isStreaming:)` | `String`, `Bool` | `Message` | Creates assistant message |
| `streamingAssistant()` | None | `Message` | Creates streaming placeholder |
| `error(_:)` | `String` | `Message` | Creates system error message |

### `MessageRole`
| Metadata | Value |
|---|---|
| Kind | enum |
| Purpose | Identifies message sender |
| Thread-Safe | Yes (Sendable) |
| Immutable | Yes |
| Serializable | Yes (Codable) |

#### Cases
| Case | Raw Value | Description |
|---|---|---|
| `.user` | `"user"` | Human user message |
| `.assistant` | `"assistant"` | AI agent response |
| `.system` | `"system"` | System/error message |

### `ToolCall`
| Metadata | Value |
|---|---|
| Kind | struct |
| Purpose | Represents an agent tool invocation |
| Thread-Safe | Yes (Sendable) |
| Immutable | Mostly (status, result, error are mutable) |
| Serializable | Yes (Identifiable, Equatable) |

#### Fields / Properties
| Name | Type | Visibility | Default | Required | Mutable | Purpose |
|---|---|---|---|---|---|---|
| `id` | `UUID` | public | `UUID()` | No | No | Unique identifier |
| `name` | `String` | public | - | Yes | No | Tool name (e.g., "search_files") |
| `arguments` | `[String: ArgumentValue]` | public | - | Yes | No | Tool arguments |
| `status` | `ToolCallStatus` | public | `.pending` | No | Yes | Execution state |
| `result` | `String?` | public | `nil` | No | Yes | Success result |
| `error` | `String?` | public | `nil` | No | Yes | Error message |
| `timestamp` | `Date` | public | `Date()` | No | No | Invocation time |

#### Computed Properties
| Property | Type | Description |
|---|---|---|
| `argumentsSummary` | `String` | Human-readable argument string |

### `ToolCallStatus`
| Metadata | Value |
|---|---|
| Kind | enum |
| Purpose | Tracks tool execution lifecycle |
| Thread-Safe | Yes (Sendable) |
| Immutable | Yes |
| Serializable | Yes (Codable) |

#### Cases
| Case | Display Text | Icon Name | Complete |
|---|---|---|---|
| `.pending` | "Pending" | "clock" | No |
| `.executing` | "Executing..." | "arrow.trianglehead.2.counterclockwise.rotate.90" | No |
| `.success` | "Success" | "checkmark.circle.fill" | Yes |
| `.failed` | "Failed" | "xmark.circle.fill" | Yes |

### `ArgumentValue`
| Metadata | Value |
|---|---|
| Kind | enum (indirect for recursion) |
| Purpose | Type-safe wrapper for JSON-like argument values |
| Thread-Safe | Yes (Sendable) |
| Immutable | Yes |
| Serializable | Yes (Codable) |

#### Cases
| Case | Associated Type | Description |
|---|---|---|
| `.string(_:)` | `String` | String value |
| `.int(_:)` | `Int` | Integer value |
| `.double(_:)` | `Double` | Floating point value |
| `.bool(_:)` | `Bool` | Boolean value |
| `.null` | None | Null/nil value |
| `.array(_:)` | `[ArgumentValue]` | Array of values |
| `.dictionary(_:)` | `[String: ArgumentValue]` | Object/dictionary |

#### Computed Properties
| Property | Type | Description |
|---|---|---|
| `displayValue` | `String` | Human-readable representation |
| `rawValue` | `Any` | Underlying Swift value |

#### Expressible Conformances
- `ExpressibleByStringLiteral`
- `ExpressibleByIntegerLiteral`
- `ExpressibleByFloatLiteral`
- `ExpressibleByBooleanLiteral`
- `ExpressibleByNilLiteral`
- `ExpressibleByArrayLiteral`
- `ExpressibleByDictionaryLiteral`

---

## Concurrency & Threading

### Swift 6 Sendable Conformance
All types in this file conform to `Sendable`:

| Type | Conformance | Notes |
|---|---|---|
| `Message` | `Sendable` | Value type, all fields are Sendable |
| `MessageRole` | `Sendable` | Enum with raw value |
| `ToolCall` | `Sendable` | Value type, all fields are Sendable |
| `ToolCallStatus` | `Sendable` | Enum with raw value |
| `ArgumentValue` | `Sendable` | Enum, recursively Sendable |

This is **critical for Swift 6** because these types are passed across actor boundaries (from IPC/parsing code to `@MainActor` UI code).

---

## Related Documentation

### Related Files
| File Path | Relationship | Why Related |
|---|---|---|
| `ui/AIAgentUI/State/AppState.swift` | Uses | Manages message array |
| `ui/AIAgentUI/IPC/MessageProtocol.swift` | Uses | Parses IPC into Message |
| `ui/AIAgentUI/Views/MainPanelView.swift` | Uses | Displays messages |
| `ui/AIAgentUI/Views/Components/ResponseBubble.swift` | Uses | Renders messages |
| `ui/AIAgentUI/Views/Components/ToolCallCard.swift` | Uses | Displays tool calls |

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-01-18 | AI Agent (Claude) | Initial creation | Created Message, ToolCall, ArgumentValue models | High |
| 2026-01-18 | AI Agent (Claude) | Swift 6 concurrency | Added Sendable to Message, MessageRole, ToolCall, ToolCallStatus, ArgumentValue | Medium |
