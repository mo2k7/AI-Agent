# File Doc: `ui/AIAgentUI/App/AppDelegate.swift`

## File Metadata
| Field | Value |
|---|---|
| Project | personal-macos-ai-agent |
| Code File Path | `ui/AIAgentUI/App/AppDelegate.swift` |
| Doc Path | `projects/personal-macos-ai-agent/files/ui/AIAgentUI/App/AppDelegate.swift.md` |
| Language | Swift 6 |
| File Role | UI |
| Ownership | @individual-developer |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-01-18 |
| Last Major Edit (YYYY-MM-DD) | 2026-01-18 |
| Modified By | AI Agent (Claude) |
| WHY (Reason for last change) | Improved showPreferences() with NSApp.activate + async dispatch for Settings button |
| Lines of Code (LOC) | ~320 |
| Cyclomatic Complexity | Low |
| Test Coverage | 0% (UI component) |

---

## Purpose & Responsibilities

### What this file does
**Single-sentence summary:** Application delegate handling lifecycle events, global hotkey registration, menu creation, and status bar integration.

**Detailed responsibilities:**
- Handles app launch (`applicationDidFinishLaunching`)
- Configures app behavior (dock visibility, agent mode)
- Sets up floating panel via `FloatingPanelController`
- Registers global Cmd+K hotkey via `GlobalHotkeyManager`
- Triggers backend startup and connection via `AppState`
- Creates application menus and status bar items
- Handles app termination cleanup

### What this file must NOT do (boundaries)
**Out of scope:**
- Does NOT manage the floating panel content (see `MainPanelView.swift`)
- Does NOT handle IPC communication (see `IPCClient.swift`)
- Does NOT implement hotkey capture logic (see `GlobalHotkey.swift`)

### Who/what calls it
| Caller | Purpose | Frequency | Error Handling |
|---|---|---|---|
| AppKit | Lifecycle callbacks | On app lifecycle events | N/A |
| Menu items | Action handlers | User-triggered | Shows error dialogs |

---

## Imports / Dependencies

### External Dependencies
| Package | Version | License | What's Used | Why Needed | Security Risk | Alternatives |
|---|---|---|---|---|---|---|
| Foundation | System | Apple | NSObject | Base class | Low | None |
| AppKit | System | Apple | NSApplication, NSApplicationDelegate, NSMenu, NSStatusItem | macOS app lifecycle | Low | None |
| SwiftUI | System | Apple | None directly | Type compatibility | Low | None |

---

## Public Surface (Document EVERYTHING Exposed)

### Exports / Public Symbols
| Symbol | Type | Visibility | Status | Brief Description |
|---|---|---|---|---|
| `AppDelegate` | class | internal | Stable | Main application delegate |

---

## Types (Classes / Structs / Enums / Interfaces)

### `AppDelegate`
| Metadata | Value |
|---|---|
| Kind | class |
| Purpose | Handles macOS app lifecycle and system integration |
| Thread-Safe | Yes (@MainActor isolated) |
| Immutable | No |
| Serializable | No |
| Related Types | `FloatingPanelController`, `GlobalHotkeyManager`, `AppState` |

#### Inheritance & Implementation
- **Extends:** `NSObject`
- **Implements:** `NSApplicationDelegate`
- **Used By:** App entry point via `@NSApplicationDelegateAdaptor`
- **Polymorphic Behavior:** NSApplicationDelegate protocol methods

#### Fields / Properties
| Name | Type | Visibility | Default | Required | Mutable | Purpose |
|---|---|---|---|---|---|---|
| `panelController` | `FloatingPanelController` | private | `.shared` | Yes | No | Window management |
| `hotkeyManager` | `GlobalHotkeyManager` | private | `.shared` | Yes | No | Global hotkey handling |
| `appState` | `AppState` | private (computed) | `.shared` | Yes | No | App state management |

#### Methods
| Method | Visibility | Parameters | Returns | Side Effects | Notes |
|---|---|---|---|---|---|
| `applicationDidFinishLaunching(_:)` | public | `Notification` | Void | Setup, show panel | Main entry point |
| `applicationWillTerminate(_:)` | public | `Notification` | Void | Cleanup | Shutdown hook |
| `applicationShouldHandleReopen(_:hasVisibleWindows:)` | public | `NSApplication`, `Bool` | Bool | Shows panel | Dock click handler |
| `togglePanel()` | @objc | None | Void | Panel visibility | Menu action |
| `showPanel()` | @objc | None | Void | Shows panel | Menu action |
| `hidePanel()` | @objc | None | Void | Hides panel | Menu action |
| `reconnect()` | @objc | None | Void | Reconnects IPC | Menu action |
| `clearMessages()` | @objc | None | Void | Clears chat | Menu action |
| `quitApp()` | @objc | None | Void | Quits app | Menu action |
| `showPreferences()` | @objc | None | Void | Opens Settings window | Menu action (Session 3 fix) |
| `createApplicationMenu()` | internal | None | `NSMenu` | None | Creates app menu |
| `setupStatusBarItem()` | internal | None | `NSStatusItem` | Creates status item | Menu bar icon |

---

## Concurrency & Threading

### Concurrency Model
- **Thread Safety:** `@MainActor` isolated for all UI operations
- **Async Patterns:** `Task { await ... }` for async operations like `appState.startup()`

### Swift 6 Concurrency Fix Applied
| Before | After | Reason |
|---|---|---|
| `class AppDelegate: NSObject, NSApplicationDelegate` | `@MainActor final class AppDelegate: NSObject, NSApplicationDelegate` | All singleton access (`FloatingPanelController.shared`, etc.) requires @MainActor |

---

## Related Documentation

### Related Files
| File Path | Relationship | Why Related |
|---|---|---|
| `ui/AIAgentUI/Window/FloatingPanelController.swift` | Uses | Panel management |
| `ui/AIAgentUI/Window/GlobalHotkey.swift` | Uses | Hotkey registration |
| `ui/AIAgentUI/State/AppState.swift` | Uses | State management |
| `ui/AIAgentUI/App/AIAgentUIApp.swift` | Used by | Registered via @NSApplicationDelegateAdaptor |

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-01-18 | AI Agent (Claude) | Initial creation | Created AppDelegate for app lifecycle | High |
| 2026-01-18 | AI Agent (Claude) | Swift 6 concurrency | Added @MainActor to fix nonisolated access errors | Medium |
| 2026-01-18 | AI Agent (Claude) | Settings window fix | Improved showPreferences() with NSApp.activate(ignoringOtherApps: true) and async dispatch to fix Settings button in agent apps | Medium |
