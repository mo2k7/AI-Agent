# File Doc: `ui/AIAgentUI/Window/FloatingPanelController.swift`

## File Metadata
| Field | Value |
|---|---|
| Project | personal-macos-ai-agent |
| Code File Path | `ui/AIAgentUI/Window/FloatingPanelController.swift` |
| Doc Path | `projects/personal-macos-ai-agent/files/ui/AIAgentUI/Window/FloatingPanelController.swift.md` |
| Language | Swift 6 |
| File Role | UI |
| Ownership | @individual-developer |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-01-18 |
| Last Major Edit (YYYY-MM-DD) | 2026-01-18 |
| Modified By | AI Agent (Codex) |
| WHY (Reason for last change) | Added drag-end scheduling, improved show/hide animation, and persisted window position restore |
| Lines of Code (LOC) | 333 |
| Cyclomatic Complexity | Low |
| Test Coverage | 0% (UI component) |

---

## Purpose & Responsibilities

### What this file does
**Single-sentence summary:** Manages the floating panel window (NSPanel) that displays the AI agent chat interface, including show/hide animations and edge snapping.

**Detailed responsibilities:**
- Creates and configures the floating panel (NSPanel)
- Hosts the SwiftUI `MainPanelView` inside AppKit window
- Manages panel visibility with scale + fade animations
- Restores persisted panel position at startup
- Integrates with `PanelPositionManager` for edge snapping and drag-end handling
- Handles Escape key to close panel
- Implements singleton pattern for global access

### What this file must NOT do (boundaries)
**Out of scope:**
- Does NOT manage chat content (see `MainPanelView.swift`)
- Does NOT handle global hotkeys (see `GlobalHotkey.swift`)
- Does NOT manage IPC connection (see `IPCClient.swift`)

### Who/what calls it
| Caller | Purpose | Frequency | Error Handling |
|---|---|---|---|
| `AppDelegate.swift` | Setup and show/hide/toggle | On app lifecycle | N/A |
| `GlobalHotkeyManager` | Toggle visibility via Cmd+K | On hotkey press | N/A |
| `FloatingPanel.close()` | Intercepts close to call hide | On user close action | N/A |

---

## Imports / Dependencies

### External Dependencies
| Package | Version | License | What's Used | Why Needed | Security Risk | Alternatives |
|---|---|---|---|---|---|---|
| Foundation | System | Apple | NSObject | Base class | Low | None |
| AppKit | System | Apple | NSPanel, NSHostingView, NSAnimationContext | Window management | Low | None |
| SwiftUI | System | Apple | AnyView, NSHostingView | Host SwiftUI views | Low | None |

---

## Public Surface (Document EVERYTHING Exposed)

### Exports / Public Symbols
| Symbol | Type | Visibility | Status | Brief Description |
|---|---|---|---|---|
| `FloatingPanelController` | class | internal | Stable | Panel window management |
| `FloatingPanel` | class | internal | Stable | Custom NSPanel subclass |
| `WindowAccessor` | struct | internal | Stable | SwiftUI window accessor |
| `FloatingPanelPresenter` | struct | internal | Stable | SwiftUI wrapper view |

---

## Types (Classes / Structs / Enums / Interfaces)

### `FloatingPanelController`
| Metadata | Value |
|---|---|
| Kind | class |
| Purpose | Manages the floating panel lifecycle |
| Thread-Safe | Yes (@MainActor singleton) |
| Immutable | No |
| Serializable | No |
| Related Types | `FloatingPanel`, `PanelPositionManager`, `AppState` |

#### Singleton Pattern
```swift
@MainActor
static let shared = FloatingPanelController()
```

#### Fields / Properties
| Name | Type | Visibility | Default | Required | Mutable | Purpose |
|---|---|---|---|---|---|---|
| `panel` | `FloatingPanel?` | private | `nil` | No | Yes | The panel window |
| `hostingView` | `NSHostingView<AnyView>?` | private | `nil` | No | Yes | SwiftUI host |
| `isVisible` | `Bool` | private(set) | `false` | Yes | Yes | Visibility state |
| `positionManager` | `PanelPositionManager` | private | `.shared` | Yes | No | Edge snapping |
| `dragEndWorkItem` | `DispatchWorkItem?` | private | `nil` | No | Yes | Debounced drag-end handler |
| `dragEndDelay` | `TimeInterval` | private | `0.12` | Yes | No | Drag end detection delay |

#### Methods
| Method | Visibility | Parameters | Returns | Side Effects | Notes |
|---|---|---|---|---|---|
| `setup(appState:)` | internal | `AppState` | Void | Creates panel, sets content | Called once at startup |
| `show()` | internal | None | Void | Shows panel with animation | Scale + fade in 0.25s |
| `hide()` | internal | None | Void | Hides panel with animation | Scale + fade out 0.2s |
| `toggle()` | internal | None | Void | Toggles visibility | Updates AppState |
| `snapTo(edge:)` | internal | `EdgeSnapping.Edge` | Void | Moves panel | Edge snapping |
| `center()` | internal | None | Void | Centers panel | Uses position manager |

#### Drag-End Scheduling
```swift
func windowDidMove(_ notification: Notification) {
    guard let panel = panel else { return }
    positionManager.panelDidMove(panel)
    scheduleDragEnd()
}
```

The controller debounces drag end detection and only triggers snapping logic once the mouse is released.

### `FloatingPanel`
| Metadata | Value |
|---|---|
| Kind | class |
| Purpose | Custom NSPanel with floating behavior |
| Thread-Safe | Yes (AppKit main thread) |
| Immutable | No |
| Serializable | No |

#### Overrides
| Override | Purpose |
|---|---|
| `canBecomeKey` | Returns `true` for keyboard input |
| `canBecomeMain` | Returns `false` to stay floating |
| `resignMain()` | Prevents hiding on deactivation |
| `close()` | Calls hide instead of close |
| `keyDown(with:)` | Handles Escape to close |

---

## Concurrency & Threading

### Swift 6 Concurrency Fix Applied
The `hide()` method's completion handler needed to be fixed for Swift 6:

| Before | After | Reason |
|---|---|---|
| `panel.orderOut(nil)` directly in completion | `Task { @MainActor in panel.orderOut(nil) }` | Completion handlers are `@Sendable`, `orderOut` requires `@MainActor` |

```swift
// Swift 6 compliant version
NSAnimationContext.runAnimationGroup({ context in
    context.duration = 0.15
    panel.animator().alphaValue = 0
}, completionHandler: { [panel] in
    Task { @MainActor in
        panel.orderOut(nil)  // Now properly isolated
    }
})
```

### Why This Fix Was Needed
- `NSAnimationContext.runAnimationGroup` completion handler is `@Sendable`
- `NSWindow.orderOut(_:)` is a `@MainActor`-isolated method
- In Swift 6, calling `@MainActor` methods from `@Sendable` closures requires explicit actor hop
- Solution: Wrap in `Task { @MainActor in ... }` to properly hop to main actor

---

## Related Documentation

### Related Files
| File Path | Relationship | Why Related |
|---|---|---|
| `ui/AIAgentUI/App/AppDelegate.swift` | Uses | Sets up and controls panel |
| `ui/AIAgentUI/Window/GlobalHotkey.swift` | Uses | Triggers toggle via Cmd+K |
| `ui/AIAgentUI/Window/EdgeSnapping.swift` | Uses | Position management |
| `ui/AIAgentUI/Views/MainPanelView.swift` | Contains | SwiftUI content |
| `ui/AIAgentUI/State/AppState.swift` | Uses | Tracks isPanelVisible |

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-01-18 | AI Agent (Claude) | Initial creation | Created FloatingPanelController for window management | High |
| 2026-01-18 | AI Agent (Claude) | Swift 6 concurrency | Fixed completion handler with Task { @MainActor in } | Medium |
| 2026-01-18 | AI Agent (Codex) | UI smoothness | Added drag-end scheduling, smoother show/hide animation, and position restore | High |
