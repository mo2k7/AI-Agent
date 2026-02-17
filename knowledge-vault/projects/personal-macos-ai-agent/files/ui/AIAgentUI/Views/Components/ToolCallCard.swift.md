# File Doc: `ui/AIAgentUI/Views/Components/ToolCallCard.swift`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `ui/AIAgentUI/Views/Components/ToolCallCard.swift` |
| Doc Path | `projects/personal-macos-ai-agent/files/ui/AIAgentUI/Views/Components/ToolCallCard.swift.md` |
| Language | Swift |
| File Role | Tool Call Display Components |
| Ownership | Core Team |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-01-18 |
| Last Major Edit (YYYY-MM-DD) | 2026-01-18 |
| Modified By | AI Agent (Codex) |
| WHY (Reason for last change) | Standardized expand/collapse animations |
| Lines of Code (LOC) | 296 |
| Cyclomatic Complexity | Low |
| Test Coverage | 0% |

---

## Purpose & Responsibilities

### What this file does
**Single-sentence summary:**
Renders tool call cards, active tool call status, and argument lists with collapsible UI.

**Detailed responsibilities:**
- Displays tool name, status badge, and arguments in `ToolCallCard`
- Renders `ActiveToolCallView` for in-flight tool calls
- Provides `ToolCallHistory` for completed tool call lists
- Uses standardized animations for expand/collapse transitions

### What this file must NOT do (boundaries)
**Out of scope:**
- Tool execution logic
- IPC parsing
- App state management

### Who/what calls it
| Caller | Purpose | Frequency | Error Handling |
|---|---|---|---|
| `ResponseBubble` | Show tool call details | Per message | N/A |
| `MainPanelView` | Active tool call display | When tool runs | N/A |

### What it calls
| Callee | Purpose | Error Handling | Fallback Strategy |
|---|---|---|---|
| `ToggleArrow` | Expand/collapse affordance | N/A | N/A |
| `AnimationConstants` | Expand/collapse motion | N/A | N/A |

---

## Imports / Dependencies

### Framework Dependencies
| Framework | What's Used | Why Needed |
|---|---|---|
| SwiftUI | Views, animations | UI rendering |

### Internal Dependencies
| Import Path | What's Used | Why Needed | Coupling Level |
|---|---|---|---|
| Same module | `ToolCall`, `ToolCallStatus` | Tool call data | Medium |
| Same module | `ToggleArrow` | Expand/collapse indicator | Low |

---

## Public Surface (Document EVERYTHING Exposed)

### Exports / Public Symbols
| Symbol | Type (func/class/const/type) | Visibility | Status | Brief Description |
|---|---|---|---|---|
| `ToolCallCard` | struct | internal | Stable | Collapsible tool call card |
| `ArgumentRow` | struct | internal | Stable | Argument key/value row |
| `ActiveToolCallView` | struct | internal | Stable | Active tool call display |
| `ToolCallHistory` | struct | internal | Stable | List of tool call cards |

---

## Types (Classes / Structs / Enums / Interfaces)

### `ToolCallCard`
| Metadata | Value |
|---|---|
| Kind | struct |
| Purpose | Display tool call details with optional result/error |
| Thread-Safe | Yes (SwiftUI) |
| Immutable | Yes |
| Serializable | No |

#### Key Behaviors
- Expands arguments with `AnimationConstants.snappy`
- Shows result or error sections when present

### `ActiveToolCallView`
| Metadata | Value |
|---|---|
| Kind | struct |
| Purpose | Highlight in-flight tool call with rotating icon |
| Thread-Safe | Yes (SwiftUI) |
| Immutable | Yes |
| Serializable | No |

---

## Testing Documentation
| Test Type | Coverage | Location | Notes |
|---|---|---|---|
| Unit | 0% | N/A | UI coverage not implemented |

---

## Related Documentation
| File Path | Relationship | Why Related |
|---|---|---|
| `ui/AIAgentUI/Views/Components/ToggleArrow.swift` | Uses | Expand/collapse arrow |
| `ui/AIAgentUI/Views/Styles/BlueTheme.swift` | Uses | Colors and animations |

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-01-18 | AI Agent (Claude) | Initial implementation | Added tool call card UI | Medium |
| 2026-01-18 | AI Agent (Codex) | UI consistency | Standardized expand/collapse animation timing | Low |
