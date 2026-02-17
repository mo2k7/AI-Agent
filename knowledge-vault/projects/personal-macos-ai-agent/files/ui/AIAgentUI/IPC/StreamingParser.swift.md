# File Doc: `ui/AIAgentUI/IPC/StreamingParser.swift`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `ui/AIAgentUI/IPC/StreamingParser.swift` |
| Doc Path | `projects/personal-macos-ai-agent/files/ui/AIAgentUI/IPC/StreamingParser.swift.md` |
| Language | Swift |
| File Role | IPC Streaming Parser + Dispatcher |
| Ownership | Core Team |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-01-18 |
| Last Major Edit (YYYY-MM-DD) | 2026-01-18 |
| Modified By | AI Agent (Codex) |
| WHY (Reason for last change) | Buffer IPC data as bytes to preserve UTF-8 and dispatch complete lines |
| Lines of Code (LOC) | 235 |
| Cyclomatic Complexity | Low |
| Test Coverage | 0% |

---

## Purpose & Responsibilities

### What this file does
**Single-sentence summary:**
Parses newline-delimited IPC JSON messages, accumulates streaming chunks, and dispatches typed events to the IPC client layer.

**Detailed responsibilities:**
- Buffer incoming socket data and split on newline delimiters
- Decode complete JSON lines and convert them into typed IPC messages
- Surface parse/encoding errors via callbacks
- Accumulate streaming deltas into full text responses
- Dispatch status, streaming, tool call, result, and error events

### What this file must NOT do (boundaries)
**Out of scope:**
- Manage socket connections (handled by `SocketManager`)
- Maintain app UI state (handled by `AppState`)
- Execute tool calls or business logic

### Who/what calls it
| Caller | Purpose | Frequency | Error Handling |
|---|---|---|---|
| `SocketManager` | Parse incoming socket data | Per incoming chunk | Emits parsing errors |

### What it calls
| Callee | Purpose | Error Handling | Fallback Strategy |
|---|---|---|---|
| `IPCMessageParser` | Decode JSON into message types | Returns nil on parse failures | Emits `invalidJSON` error |

---

## Imports / Dependencies

### Framework Dependencies
| Framework | What's Used | Why Needed |
|---|---|---|
| Foundation | `Data`, `String`, callbacks | Core parsing + buffering |

### Internal Dependencies
| Import Path | What's Used | Why Needed | Coupling Level |
|---|---|---|---|
| Same module | `IPCMessageParser`, `IPCParsedMessage` | JSON decoding | Medium |
| Same module | `ToolCall`, `AgentStatus` | Message conversion | Medium |

---

## Public Surface (Document EVERYTHING Exposed)

### Exports / Public Symbols
| Symbol | Type (func/class/const/type) | Visibility | Status | Brief Description |
|---|---|---|---|---|
| `StreamingParser` | class | internal | Stable | Buffers and parses IPC messages |
| `StreamingParserError` | enum | internal | Stable | Parse/encoding error types |
| `StreamAccumulator` | class | internal | Stable | Accumulates streaming deltas |
| `MessageDispatcher` | class | internal | Stable | Routes parsed messages to callbacks |

---

## Types (Classes / Structs / Enums / Interfaces)

### `StreamingParser`
| Metadata | Value |
|---|---|
| Kind | class |
| Purpose | Incremental newline-delimited JSON parser |
| Thread-Safe | No (single queue use) |
| Immutable | No |
| Serializable | No |
| Related Types | `MessageDispatcher` |

#### Key Behaviors
- Buffers raw bytes to avoid UTF-8 split errors
- Splits on newline (`0x0A`) and decodes each line
- Emits `StreamingParserError` on invalid UTF-8 or JSON

### `StreamingParserError`
| Metadata | Value |
|---|---|
| Kind | enum |
| Purpose | Describe parsing/encoding failures |
| Thread-Safe | Yes |
| Immutable | Yes |
| Serializable | No |
| Related Types | `StreamingParser` |

### `StreamAccumulator`
| Metadata | Value |
|---|---|
| Kind | class |
| Purpose | Aggregate streaming text chunks |
| Thread-Safe | No (single queue use) |
| Immutable | No |
| Serializable | No |
| Related Types | `MessageDispatcher` |

### `MessageDispatcher`
| Metadata | Value |
|---|---|
| Kind | class |
| Purpose | Route parsed messages to per-type callbacks |
| Thread-Safe | No (single queue use) |
| Immutable | No |
| Serializable | No |
| Related Types | `StreamAccumulator` |

---

## Error Handling Strategy

### Error Categories
| Category | Examples | Default Behavior | User Action |
|---|---|---|---|
| Encoding errors | Invalid UTF-8 in socket stream | Emit `invalidEncoding` | None |
| JSON errors | Malformed JSON line | Emit `invalidJSON` | None |

---

## Concurrency & Threading

### Concurrency Model
- **Thread Safety:** Not thread-safe; expected to run on the socket queue.
- **Async Patterns:** Callback-based.
- **Synchronization Primitives:** None.

---

## Testing Documentation

### Test Coverage
| Test Type | Coverage | Location | Notes |
|---|---|---|---|
| Unit | 0% | N/A | No Swift IPC parser tests yet |

---

## Technical Debt & Known Issues

### Known Bugs
| Bug ID | Description | Severity | Confidence | Repro Steps | Workaround | Status |
|---|---|---|---|---|---|---|
| None | N/A | S3 | Confirmed | N/A | N/A | N/A |

---

## Related Documentation
| File Path | Relationship | Why Related |
|---|---|---|
| `ui/AIAgentUI/IPC/SocketManager.swift` | Uses | Feeds raw data into parser |
| `ui/AIAgentUI/IPC/MessageProtocol.swift` | Uses | Defines message parsing types |
| `ui/AIAgentUI/IPC/IPCClient.swift` | Uses | Consumes dispatcher callbacks |

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-01-18 | AI Agent (Codex) | UTF-8 safety | Buffer socket bytes and decode complete lines before parsing | Medium |
