# File Doc: `ui/AIAgentUI/Views/Components/StatusIndicator.swift`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `ui/AIAgentUI/Views/Components/StatusIndicator.swift` |
| Doc Path | `projects/personal-macos-ai-agent/files/ui/AIAgentUI/Views/Components/StatusIndicator.swift.md` |
| Language | Swift |
| File Role | Status Indicator UI |
| Ownership | Core Team |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-01-18 |
| Last Major Edit (YYYY-MM-DD) | 2026-01-18 |
| Modified By | AI Agent (Codex) |
| WHY (Reason for last change) | Standardized status animations with AnimationConstants |
| Lines of Code (LOC) | 346 |
| Cyclomatic Complexity | Medium |
| Test Coverage | 0% |

---

## Purpose & Responsibilities

### What this file does
**Single-sentence summary:**
Displays animated status indicators for the agent state, including thinking, connecting, streaming, and error feedback.

**Detailed responsibilities:**
- Renders `StatusIndicator` for active agent states
- Provides specialized sub-indicators (thinking, connecting, tool call, streaming, error, complete)
- Uses shared animation presets for consistent motion
- Includes `InlineStatusView` for compact header display

### What this file must NOT do (boundaries)
**Out of scope:**
- State management or IPC
- Message rendering

### Who/what calls it
| Caller | Purpose | Frequency | Error Handling |
|---|---|---|---|
| `MainPanelView` | Display status at bottom | State changes | N/A |
| `InlineStatusView` | Header status indicator | State changes | N/A |

---

## Imports / Dependencies

### Framework Dependencies
| Framework | What's Used | Why Needed |
|---|---|---|
| SwiftUI | Views, animations | UI rendering |

### Internal Dependencies
| Import Path | What's Used | Why Needed | Coupling Level |
|---|---|---|---|
| Same module | `AgentStatus` | Status display | Medium |
| Same module | `AnimationConstants` | Motion presets | Low |

---

## Public Surface (Document EVERYTHING Exposed)

### Exports / Public Symbols
| Symbol | Type (func/class/const/type) | Visibility | Status | Brief Description |
|---|---|---|---|---|
| `StatusIndicator` | struct | internal | Stable | Main status display |
| `InlineStatusView` | struct | internal | Stable | Compact status display |

---

## Types (Classes / Structs / Enums / Interfaces)

### `StatusIndicator`
| Metadata | Value |
|---|---|
| Kind | struct |
| Purpose | Switches between status visuals based on `AgentStatus` |
| Thread-Safe | Yes (SwiftUI) |
| Immutable | Yes |
| Serializable | No |

#### Key Behaviors
- Uses `AnimationConstants.gentle/standard/snappy` for pulses and transitions
- Displays status text alongside icon when needed

---

## Testing Documentation
| Test Type | Coverage | Location | Notes |
|---|---|---|---|
| Unit | 0% | N/A | UI coverage not implemented |

---

## Related Documentation
| File Path | Relationship | Why Related |
|---|---|---|
| `ui/AIAgentUI/State/AgentStatus.swift` | Uses | Status values and display text |
| `ui/AIAgentUI/Views/Styles/BlueTheme.swift` | Uses | Status colors and animations |

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-01-18 | AI Agent (Claude) | Initial implementation | Added animated status indicators | Medium |
| 2026-01-18 | AI Agent (Codex) | UI consistency | Updated animations to use AnimationConstants | Low |
