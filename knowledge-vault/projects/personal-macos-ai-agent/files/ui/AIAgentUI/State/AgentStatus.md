# File Doc: `ui/AIAgentUI/State/AgentStatus.swift`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `ui/AIAgentUI/State/AgentStatus.swift` |
| Doc Path | `projects/personal-macos-ai-agent/files/ui/AIAgentUI/State/AgentStatus.md` |
| Language | Swift |
| File Role | Agent Status Enumeration |
| Ownership | Core Team |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-01-18 |
| Last Major Edit (YYYY-MM-DD) | 2026-01-18 |
| Modified By | AI Agent (Codex) |
| WHY (Reason for last change) | Updated test path references to Tests/ layout |
| Lines of Code (LOC) | 190 |
| Cyclomatic Complexity | Low |
| Test Coverage | 0% |

---

## Purpose & Responsibilities

### What this file does
**Single-sentence summary:**
Defines the `AgentStatus` enum that represents all possible states of the AI agent with computed properties for UI display.

**Detailed responsibilities:**
- Defines status cases: `idle`, `connecting`, `thinking`, `callingTool`, `streaming`, `error`, `complete`
- Provides associated values for context (tool name, error message)
- Computes display text for each status
- Provides animation and busy state flags
- Determines whether user can submit new prompts
- Supports Codable for JSON serialization
- Provides factory method for parsing from backend status strings

### What this file must NOT do (boundaries)
**Out of scope:**
- Status persistence
- Network communication
- UI rendering (provides data for views)

---

## Public Surface (Document EVERYTHING Exposed)

### Exports / Public Symbols
| Symbol | Type (func/class/const/type) | Visibility | Status | Brief Description |
|---|---|---|---|---|
| `AgentStatus` | enum | public | Stable | Agent operational status |

---

## Types (Classes / Structs / Enums / Interfaces)

### `AgentStatus`
| Metadata | Value |
|---|---|
| Kind | enum |
| Purpose | Represents all possible agent states with display properties |
| Thread-Safe | Yes (immutable) |
| Immutable | Yes |
| Serializable | Yes (Codable) |
| Related Types | `AppState`, `StatusIndicator` |

#### Inheritance & Implementation
- **Extends:** N/A
- **Implements:** `Equatable`, `Codable`
- **Used By:** `AppState`, `StatusIndicator`, `InputField`
- **Polymorphic Behavior:** Associated values for `callingTool` and `error`

#### Cases
| Case | Associated Values | Purpose | Display Text |
|---|---|---|---|
| `idle` | None | Ready and waiting | "Ready" |
| `connecting` | None | Establishing IPC connection | "Connecting..." |
| `thinking` | None | Processing user prompt | "Thinking..." |
| `callingTool(toolName: String)` | Tool name | Executing a tool | "Calling {toolName}..." |
| `streaming` | None | Streaming response | "Responding..." |
| `error(message: String)` | Error message | Error occurred | "Error: {message}" |
| `complete` | None | Request completed | "Done" |

#### Computed Properties
| Property | Type | Purpose | Implementation Notes |
|---|---|---|---|
| `displayText` | String | Human-readable status | Full description with context |
| `shortText` | String | Abbreviated status | Single word/short phrase |
| `isBusy` | Bool | Whether agent is processing | True for thinking, callingTool, streaming |
| `shouldAnimate` | Bool | Whether to animate indicator | True for connecting, thinking, callingTool, streaming |
| `canSubmit` | Bool | Whether user can submit prompt | True only for idle, complete, error |
| `showsIndicator` | Bool | Whether to show status indicator | True for all except idle |
| `isError` | Bool | Whether this is an error state | True only for error case |

#### Static Methods
| Method | Signature | Visibility | Parameters | Returns | Purpose |
|---|---|---|---|---|---|
| `from` | `(rawStatus: String, detail: String?) -> AgentStatus` | static | Raw status string, optional detail | AgentStatus | Parse from backend JSON |

#### Codable Implementation
```swift
// Encoding
func encode(to encoder: Encoder) throws {
    var container = encoder.singleValueContainer()
    switch self {
    case .idle: try container.encode("idle")
    case .connecting: try container.encode("connecting")
    case .thinking: try container.encode("thinking")
    case .callingTool(let name): try container.encode("calling_tool:\(name)")
    case .streaming: try container.encode("streaming")
    case .error(let msg): try container.encode("error:\(msg)")
    case .complete: try container.encode("complete")
    }
}

// Decoding
init(from decoder: Decoder) throws {
    let container = try decoder.singleValueContainer()
    let value = try container.decode(String.self)
    self = AgentStatus.from(rawStatus: value)
}
```

---

## Status State Machine

### Valid Transitions
```
[idle] --prompt--> [thinking] --tool--> [callingTool] --done--> [streaming]
                       |                      |                      |
                       +-------+-------+------+------+-------+-------+
                               |                     |
                           [error]               [complete] --new prompt--> [thinking]
                               |
                           [idle] (after clear)
```

### Transition Rules
| From | To | Trigger |
|---|---|---|
| `idle` | `thinking` | User submits prompt |
| `thinking` | `callingTool` | Backend executes tool |
| `thinking` | `streaming` | Backend starts response |
| `callingTool` | `streaming` | Tool execution complete |
| `callingTool` | `error` | Tool execution failed |
| `streaming` | `complete` | Response finished |
| `complete` | `idle` | Auto-transition after delay |
| `*` | `error` | Any error occurs |
| `error` | `idle` | User clears error |

---

## Example Usage

### Display Status in UI
```swift
struct StatusView: View {
    let status: AgentStatus
    
    var body: some View {
        HStack {
            if status.shouldAnimate {
                ProgressView()
                    .progressViewStyle(.circular)
            }
            
            Text(status.displayText)
                .foregroundColor(status.isError ? .red : .primary)
        }
    }
}
```

### Check Submission Ability
```swift
Button("Send") {
    // Send prompt
}
.disabled(!status.canSubmit)
```

### Parse from Backend
```swift
// From JSON response
let rawStatus = "calling_tool"
let detail = "search_files"
let status = AgentStatus.from(rawStatus: rawStatus, detail: detail)
// Result: .callingTool(toolName: "search_files")

// Error case
let errorStatus = AgentStatus.from(rawStatus: "error", detail: "Connection refused")
// Result: .error(message: "Connection refused")
```

---

## Property Details

### `displayText`
| Case | Output |
|---|---|
| `.idle` | "Ready" |
| `.connecting` | "Connecting..." |
| `.thinking` | "Thinking..." |
| `.callingTool("search")` | "Calling search..." |
| `.streaming` | "Responding..." |
| `.error("Timeout")` | "Error: Timeout" |
| `.complete` | "Done" |

### `shortText`
| Case | Output |
|---|---|
| `.idle` | "Ready" |
| `.connecting` | "Connecting" |
| `.thinking` | "Thinking" |
| `.callingTool("search")` | "search" |
| `.streaming` | "Streaming" |
| `.error("Timeout")` | "Error" |
| `.complete` | "Done" |

### `isBusy`
| Case | Value |
|---|---|
| `.idle` | `false` |
| `.connecting` | `true` |
| `.thinking` | `true` |
| `.callingTool` | `true` |
| `.streaming` | `true` |
| `.error` | `false` |
| `.complete` | `false` |

### `shouldAnimate`
| Case | Value |
|---|---|
| `.idle` | `false` |
| `.connecting` | `true` |
| `.thinking` | `true` |
| `.callingTool` | `true` |
| `.streaming` | `true` |
| `.error` | `false` |
| `.complete` | `false` |

### `canSubmit`
| Case | Value | Reason |
|---|---|---|
| `.idle` | `true` | Ready for input |
| `.connecting` | `false` | Not yet connected |
| `.thinking` | `false` | Already processing |
| `.callingTool` | `false` | Already processing |
| `.streaming` | `false` | Already processing |
| `.error` | `true` | Can retry |
| `.complete` | `true` | Ready for new input |

### `showsIndicator`
| Case | Value | Reason |
|---|---|---|
| `.idle` | `false` | No activity to show |
| `.connecting` | `true` | Show connecting animation |
| `.thinking` | `true` | Show thinking animation |
| `.callingTool` | `true` | Show tool execution |
| `.streaming` | `true` | Show streaming indicator |
| `.error` | `true` | Show error state |
| `.complete` | `true` | Show completion briefly |

---

## Testing Documentation

### Unit Test Coverage
| Function/Class | Coverage | Test Location | Edge Cases Covered |
|---|---|---|---|
| All | 0% | `Tests/AIAgentUITests/StateTests/` | None yet |

### Test Cases to Cover
- [ ] All computed properties for each case
- [ ] `from(rawStatus:detail:)` with all valid inputs
- [ ] `from(rawStatus:detail:)` with unknown status
- [ ] Codable encoding/decoding roundtrip
- [ ] Equatable comparison

---

## Related Documentation

### Related Files
| File Path | Relationship | Why Related |
|---|---|---|
| `ui/AIAgentUI/State/AppState.swift` | Uses | Primary consumer |
| `ui/AIAgentUI/Views/Components/StatusIndicator.swift` | Uses | Displays status |
| `ui/AIAgentUI/Views/Components/InputField.swift` | Uses | Checks canSubmit |
| `agent_host/ipc/protocol.py` | Mirror | Python AgentStatus enum |

### Python Equivalent
```python
# From protocol.py
class AgentStatus(str, Enum):
    IDLE = "idle"
    CONNECTING = "connecting"
    THINKING = "thinking"
    CALLING_TOOL = "calling_tool"
    STREAMING = "streaming"
    ERROR = "error"
    COMPLETE = "complete"
```

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-01-18 | AI Assistant | Initial implementation | Created status enum | New file |
| 2026-01-18 | AI Assistant | Build fix | Added showsIndicator property | API addition |
