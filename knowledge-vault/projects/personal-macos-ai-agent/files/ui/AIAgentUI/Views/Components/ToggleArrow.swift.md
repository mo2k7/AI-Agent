# File Doc: `ui/AIAgentUI/Views/Components/ToggleArrow.swift`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `ui/AIAgentUI/Views/Components/ToggleArrow.swift` |
| Doc Path | `projects/personal-macos-ai-agent/files/ui/AIAgentUI/Views/Components/ToggleArrow.swift.md` |
| Language | Swift |
| File Role | Expand/Collapse UI Controls |
| Ownership | Core Team |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-01-18 |
| Last Major Edit (YYYY-MM-DD) | 2026-01-18 |
| Modified By | AI Agent (Codex) |
| WHY (Reason for last change) | Standardized toggle animations |
| Lines of Code (LOC) | 238 |
| Cyclomatic Complexity | Low |
| Test Coverage | 0% |

---

## Purpose & Responsibilities

### What this file does
**Single-sentence summary:**
Provides toggle arrow components and collapsible section helpers with consistent animation timing.

**Detailed responsibilities:**
- Renders `ToggleArrow` with rotation animation
- Provides `CollapsibleSectionHeader` and `CollapsibleSection` helpers
- Supplies `ToolCallHeader` for tool call cards

### What this file must NOT do (boundaries)
**Out of scope:**
- Tool call rendering logic
- Data fetching or state storage

---

## Imports / Dependencies

### Framework Dependencies
| Framework | What's Used | Why Needed |
|---|---|---|
| SwiftUI | Views, animations | UI rendering |

### Internal Dependencies
| Import Path | What's Used | Why Needed | Coupling Level |
|---|---|---|---|
| Same module | `AnimationConstants` | Toggle motion | Low |
| Same module | `ToolCallStatus` | Tool call header badge | Low |

---

## Public Surface (Document EVERYTHING Exposed)

### Exports / Public Symbols
| Symbol | Type (func/class/const/type) | Visibility | Status | Brief Description |
|---|---|---|---|---|
| `ToggleArrow` | struct | internal | Stable | Chevron rotation indicator |
| `CollapsibleSectionHeader` | struct | internal | Stable | Header with arrow |
| `CollapsibleSection` | struct | internal | Stable | Collapsible container |
| `ToolCallHeader` | struct | internal | Stable | Tool call header row |

---

## Testing Documentation
| Test Type | Coverage | Location | Notes |
|---|---|---|---|
| Unit | 0% | N/A | UI coverage not implemented |

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-01-18 | AI Agent (Claude) | Initial implementation | Added toggle arrow and collapsible sections | Low |
| 2026-01-18 | AI Agent (Codex) | UI consistency | Updated toggle animations to AnimationConstants.snappy | Low |
