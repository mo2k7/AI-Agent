# File Doc: `ui/AIAgentUI/Views/Components/InputField.swift`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `ui/AIAgentUI/Views/Components/InputField.swift` |
| Doc Path | `projects/personal-macos-ai-agent/files/ui/AIAgentUI/Views/Components/InputField.swift.md` |
| Language | Swift |
| File Role | UI Input Component |
| Ownership | Core Team |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-01-18 |
| Last Major Edit (YYYY-MM-DD) | 2026-01-18 |
| Modified By | AI Agent (Opus) |
| WHY (Reason for last change) | Fixed yellow banner rendering issue - replaced BorderlessTextView with native SwiftUI TextEditor |
| Lines of Code (LOC) | 380 |
| Cyclomatic Complexity | Medium |
| Test Coverage | 0% |

---

## Purpose & Responsibilities

### What this file does
**Single-sentence summary:**
Provides a multi-line text input field with native AppKit backing, placeholder handling, and submit shortcuts for the floating panel UI.

**Detailed responsibilities:**
- Renders the main `InputField` with submit button and focus styling
- Implements `BorderlessTextView` using `NSViewRepresentable` to remove scroll borders
- Handles Enter and Command+Enter submission via `SubmitTextView`
- Exposes `SimpleInputField` for single-line usage
- Preserves a legacy `CustomTextEditor` reference for SwiftUI-only input

### What this file must NOT do (boundaries)
**Out of scope:**
- IPC/network operations
- Message state management
- Theme definitions (see `BlueTheme.swift`)

### Who/what calls it
| Caller | Purpose | Frequency | Error Handling |
|---|---|---|---|
| `MainPanelView` | Render prompt input | Continuous | Disabled when busy |

### What it calls
| Callee | Purpose | Error Handling | Fallback Strategy |
|---|---|---|---|
| `ThemeConstants` | Spacing and sizing | N/A | N/A |
| `AnimationConstants` | Focus animation | N/A | N/A |
| `NSScrollView` / `NSTextView` | Native text input | N/A | N/A |

---

## Imports / Dependencies

### Framework Dependencies
| Framework | What's Used | Why Needed |
|---|---|---|
| SwiftUI | Views, bindings, FocusState | UI rendering |
| AppKit | NSTextView, NSScrollView, NSEvent | Native input control |

---

## Public Surface (Document EVERYTHING Exposed)

### Exports / Public Symbols
| Symbol | Type (func/class/const/type) | Visibility | Status | Brief Description |
|---|---|---|---|---|
| `InputField` | struct | internal | Stable | Main multi-line input component |
| `BorderlessTextView` | struct | internal | Stable | NSViewRepresentable input wrapper |
| `SubmitTextView` | class | internal | Stable | NSTextView subclass handling submit keys |
| `SimpleInputField` | struct | internal | Stable | Single-line input field |
| `CustomTextEditor` | struct | internal | Deprecated | SwiftUI TextEditor reference |

---

## Types (Classes / Structs / Enums / Interfaces)

### `InputField`
| Metadata | Value |
|---|---|
| Kind | struct |
| Purpose | Multi-line input with submit button |
| Thread-Safe | Yes (SwiftUI) |
| Immutable | Yes |
| Serializable | No |

#### Key Behaviors
- Uses native SwiftUI `TextEditor` with manual placeholder overlay (fixed from broken NSTextView wrapper)
- Uses `@FocusState` for focus tracking and visual feedback
- Submits on Enter via `.onKeyPress(.return)` handler
- Displays placeholder text when empty via ZStack overlay

### `BorderlessTextView`
| Metadata | Value |
|---|---|
| Kind | struct |
| Purpose | AppKit-backed input without NSScrollView borders |
| Thread-Safe | Yes (SwiftUI) |
| Immutable | Yes |
| Serializable | No |

### `SubmitTextView`
| Metadata | Value |
|---|---|
| Kind | class |
| Purpose | Intercepts key presses for submit shortcuts |
| Thread-Safe | Main-thread only |
| Immutable | No |
| Serializable | No |

#### Key Behaviors
- Enter or Command+Enter triggers submit
- Shift+Enter inserts a newline
- Renders placeholder text when empty

### `SimpleInputField`
| Metadata | Value |
|---|---|
| Kind | struct |
| Purpose | Single-line input variant |
| Thread-Safe | Yes (SwiftUI) |
| Immutable | Yes |
| Serializable | No |

---

## Testing Documentation
| Test Type | Coverage | Location | Notes |
|---|---|---|---|
| Unit | 0% | N/A | UI coverage not implemented |

---

## Technical Debt & Known Issues
| Item | Severity | Description | Status |
|---|---|---|---|
| Deprecated code | Low | `BorderlessTextView`, `SubmitTextView`, and `CustomTextEditor` remain in file but are unused; should be cleaned up | Open |
| Focus handling | Low | May need testing with floating panel's `.nonactivatingPanel` style mask | Needs verification |

---

## Related Documentation
| File Path | Relationship | Why Related |
|---|---|---|
| `ui/AIAgentUI/Views/MainPanelView.swift` | Uses | Hosts the input field |
| `ui/AIAgentUI/Views/Styles/BlueTheme.swift` | Uses | Colors and animation constants |
| `ui/AIAgentUI/Views/Styles/LiquidGlassStyle.swift` | Uses | Input styling |

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-01-18 | AI Agent (Claude) | UI bug fixes | Replaced TextEditor with borderless NSTextView to fix border and invisible text | High |
| 2026-01-18 | AI Agent (Codex) | UI shortcut update | Added Cmd+Enter submit and adaptive text color | Medium |
| 2026-01-18 | AI Agent (Opus) | Fix critical rendering bug | Replaced broken BorderlessTextView (NSViewRepresentable) with native SwiftUI TextEditor - BorderlessTextView was rendering as yellow banner with prohibition symbol | Critical |
