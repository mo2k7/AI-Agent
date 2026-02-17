# File Doc: `ui/AIAgentUI/Views/Components/LoadingShimmer.swift`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `ui/AIAgentUI/Views/Components/LoadingShimmer.swift` |
| Doc Path | `projects/personal-macos-ai-agent/files/ui/AIAgentUI/Views/Components/LoadingShimmer.swift.md` |
| Language | Swift |
| File Role | Loading Placeholder UI |
| Ownership | Core Team |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-01-18 |
| Last Major Edit (YYYY-MM-DD) | 2026-01-18 |
| Modified By | AI Agent (Codex) |
| WHY (Reason for last change) | Added shimmer placeholder for streaming responses |
| Lines of Code (LOC) | 64 |
| Cyclomatic Complexity | Low |
| Test Coverage | 0% |

---

## Purpose & Responsibilities

### What this file does
**Single-sentence summary:**
Renders a lightweight shimmer placeholder for message content while streaming text is empty.

**Detailed responsibilities:**
- Draws configurable shimmer lines using gradients and rounded rectangles
- Animates a horizontal shimmer sweep using linear timing
- Hides itself from accessibility to avoid noisy announcements

### What this file must NOT do (boundaries)
**Out of scope:**
- Message content rendering
- State management or IPC

---

## Imports / Dependencies

### Framework Dependencies
| Framework | What's Used | Why Needed |
|---|---|---|
| SwiftUI | Views, animations | UI rendering |

---

## Public Surface (Document EVERYTHING Exposed)

### Exports / Public Symbols
| Symbol | Type (func/class/const/type) | Visibility | Status | Brief Description |
|---|---|---|---|---|
| `LoadingShimmer` | struct | internal | Stable | Shimmer placeholder view |

---

## Testing Documentation
| Test Type | Coverage | Location | Notes |
|---|---|---|---|
| Unit | 0% | N/A | UI coverage not implemented |

---

## Related Documentation
| File Path | Relationship | Why Related |
|---|---|---|
| `ui/AIAgentUI/Views/Components/ResponseBubble.swift` | Uses | Shimmer while streaming |

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-01-18 | AI Agent (Codex) | UI polish | Added shimmer placeholder component | Low |
