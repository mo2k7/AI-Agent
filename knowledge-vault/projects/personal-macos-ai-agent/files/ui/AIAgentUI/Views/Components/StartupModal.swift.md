# File Doc: `ui/AIAgentUI/Views/Components/StartupModal.swift`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `ui/AIAgentUI/Views/Components/StartupModal.swift` |
| Doc Path | `projects/personal-macos-ai-agent/files/ui/AIAgentUI/Views/Components/StartupModal.swift.md` |
| Language | Swift |
| File Role | Startup/Initialization Overlay |
| Ownership | Core Team |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-01-18 |
| Last Major Edit (YYYY-MM-DD) | 2026-01-18 |
| Modified By | AI Agent (Codex) |
| WHY (Reason for last change) | Standardized startup animations with AnimationConstants |
| Lines of Code (LOC) | 289 |
| Cyclomatic Complexity | Medium |
| Test Coverage | 0% |

---

## Purpose & Responsibilities

### What this file does
**Single-sentence summary:**
Shows a modal overlay during backend startup with animated status icon, retry/quit actions, and phase-specific messaging.

**Detailed responsibilities:**
- Defines `StartupPhase` enum with title, subtitle, symbol, and color
- Renders `StartupModal` with glass styling and animated icon
- Provides `StartupOverlay` that gates the main UI during startup
- Uses shared animation constants for phase transitions and pulses

### What this file must NOT do (boundaries)
**Out of scope:**
- Starting/stopping the backend process
- IPC connection logic

---

## Imports / Dependencies

### Framework Dependencies
| Framework | What's Used | Why Needed |
|---|---|---|
| SwiftUI | Views, animations | UI rendering |

### Internal Dependencies
| Import Path | What's Used | Why Needed | Coupling Level |
|---|---|---|---|
| Same module | `AppState` | Startup phase binding | Medium |
| Same module | `AnimationConstants` | Motion presets | Low |

---

## Public Surface (Document EVERYTHING Exposed)

### Exports / Public Symbols
| Symbol | Type (func/class/const/type) | Visibility | Status | Brief Description |
|---|---|---|---|---|
| `StartupPhase` | enum | internal | Stable | Startup phase states |
| `StartupModal` | struct | internal | Stable | Modal view |
| `StartupOverlay` | struct | internal | Stable | Overlay controller |

---

## Testing Documentation
| Test Type | Coverage | Location | Notes |
|---|---|---|---|
| Unit | 0% | N/A | UI coverage not implemented |

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-01-18 | AI Agent (Claude) | Health check feature | Added performingHealthCheck phase | Low |
| 2026-01-18 | AI Agent (Codex) | UI consistency | Updated modal animations to AnimationConstants | Low |
