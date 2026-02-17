# File Doc: `ui/AIAgentUI/Window/FloatingPanelController.swift`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `ui/AIAgentUI/Window/FloatingPanelController.swift` |
| Doc Path | `projects/personal-macos-ai-agent/files/ui/AIAgentUI/Window/FloatingPanelController.md` |
| Language | Swift |
| File Role | Floating Panel Window Management |
| Ownership | Core Team |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-01-18 |
| Last Major Edit (YYYY-MM-DD) | 2026-01-18 |
| Modified By | AI Assistant |
| WHY (Reason for last change) | Fixed actor isolation for AppState access |
| Lines of Code (LOC) | 281 |
| Cyclomatic Complexity | Low |
| Test Coverage | 0% |

---

## Purpose & Responsibilities

### What this file does
**Single-sentence summary:**
Singleton controller that manages the floating NSPanel window for the AI Agent UI with non-activating behavior.

**Detailed responsibilities:**
- Creates and configures the floating `NSPanel` with non-activating behavior
- Manages panel visibility (show/hide/toggle) with animations
- Integrates with `PanelPositionManager` for edge snapping
- Provides `setup(appState:)` for SwiftUI content hosting
- Handles panel close behavior (hide instead of destroy)
- Implements `NSWindowDelegate` for position tracking
- Provides `WindowAccessor` for SwiftUI window access
- Provides `FloatingPanelPresenter` for SwiftUI wrapping

### What this file must NOT do (boundaries)
**Out of scope:**
- Edge snapping logic (delegated to `EdgeSnapping.swift`)
- Global hotkey handling (delegated to `GlobalHotkey.swift`)
- SwiftUI view content (delegated to `MainPanelView`)
- State management (delegated to `AppState`)

### Who/what calls it
| Caller | Purpose | Frequency | Error Handling |
|---|---|---|---|
| `AppDelegate` | Setup and toggle | On app launch, hotkey | N/A |
| `GlobalHotkeyManager` | Toggle visibility | On Cmd+K | N/A |

### What it calls
| Callee | Purpose | Error Handling | Fallback Strategy |
|---|---|---|---|
| `PanelPositionManager` | Edge snapping | N/A | N/A |
| `MainPanelView` | UI content | N/A | N/A |
| `AppState` | State updates | N/A | N/A |
| `ThemeConstants` | Panel dimensions | N/A | N/A |

---

## Imports / Dependencies

### Framework Dependencies
| Framework | What's Used | Why Needed |
|---|---|---|
| Foundation | Basic types | Core functionality |
| AppKit | NSPanel, NSWindow | Window management |
| SwiftUI | NSHostingView, View | UI hosting |

### Internal Dependencies
| Import Path | What's Used | Why Needed | Coupling Level |
|---|---|---|---|
| Same module | `PanelPositionManager`, `ThemeConstants`, `MainPanelView`, `AppState` | Window behavior | High |

---

## Public Surface (Document EVERYTHING Exposed)

### Exports / Public Symbols
| Symbol | Type (func/class/const/type) | Visibility | Status | Brief Description |
|---|---|---|---|---|
| `FloatingPanelController` | class | public | Stable | Panel management singleton |
| `FloatingPanel` | class | internal | Stable | Custom NSPanel subclass |
| `WindowAccessor` | struct | public | Stable | SwiftUI window access |
| `FloatingPanelPresenter` | struct | public | Stable | SwiftUI wrapper |

---

## Types (Classes / Structs / Enums / Interfaces)

### `FloatingPanelController`
| Metadata | Value |
|---|---|
| Kind | class |
| Purpose | Singleton managing the floating panel window |
| Thread-Safe | No (use from main thread) |
| Immutable | No |
| Serializable | No |
| Related Types | `FloatingPanel`, `AppState` |

#### Inheritance & Implementation
- **Extends:** `NSObject`
- **Implements:** `NSWindowDelegate`
- **Used By:** `AppDelegate`, `GlobalHotkeyManager`
- **Polymorphic Behavior:** N/A

#### Fields / Properties
| Name | Type | Visibility | Default | Required | Mutable | Purpose | Validation | Notes |
|---|---|---|---|---|---|---|---|---|
| `shared` | FloatingPanelController | static | Singleton | N/A | No | Global instance | N/A | |
| `panel` | FloatingPanel? | private | `nil` | No | Yes | Panel window | N/A | Created lazily |
| `hostingView` | NSHostingView<AnyView>? | private | `nil` | No | Yes | SwiftUI host | N/A | |
| `isVisible` | Bool | public | `false` | N/A | Yes | Visibility state | N/A | Read-only externally |
| `positionManager` | PanelPositionManager | private | `.shared` | N/A | No | Edge snapping | N/A | |

#### Methods
| Method | Signature | Visibility | Parameters | Returns | Throws/Errors | Side Effects | Thread-Safe | Complexity | Notes |
|---|---|---|---|---|---|---|---|---|---|
| `setup` | `(appState: AppState)` | public | App state | None | Never | Creates panel | No | O(1) | Must call before show |
| `show` | `()` | public | None | None | Never | Shows panel | No | O(1) | With animation |
| `hide` | `()` | public | None | None | Never | Hides panel | No | O(1) | With animation |
| `toggle` | `()` | public | None | None | Never | Toggles visibility | No | O(1) | Updates AppState |
| `snapTo` | `(edge: EdgeSnapping.Edge)` | public | Target edge | None | Never | Snaps panel | No | O(1) | |
| `center` | `()` | public | None | None | Never | Centers panel | No | O(1) | |
| `createPanel` | `() private` | private | None | None | Never | Creates NSPanel | No | O(1) | |
| `positionPanel` | `() private` | private | None | None | Never | Sets position | No | O(1) | |

#### Static Members
| Member | Type | Purpose | Mutability | Thread-Safe |
|---|---|---|---|---|
| `shared` | FloatingPanelController | Singleton instance | Immutable ref | No |

---

### `FloatingPanel`
| Metadata | Value |
|---|---|
| Kind | class |
| Purpose | Custom NSPanel with floating behavior |
| Thread-Safe | No |
| Immutable | No |
| Serializable | No |

#### Inheritance & Implementation
- **Extends:** `NSPanel`
- **Implements:** N/A
- **Used By:** `FloatingPanelController`

#### Overridden Properties/Methods
| Override | Purpose | Behavior |
|---|---|---|
| `canBecomeKey` | Allow key window | Returns `true` |
| `canBecomeMain` | Prevent main window | Returns `false` |
| `resignMain()` | Handle deactivation | Keep visible |
| `close()` | Custom close | Hide instead of close |
| `keyDown(with:)` | Handle Escape | Hide on Escape |

#### Panel Configuration
```swift
// Style mask
styleMask: [.nonactivatingPanel, .titled, .closable, .resizable, .fullSizeContentView]

// Panel properties
panel.title = "AI Agent"
panel.titleVisibility = .hidden
panel.titlebarAppearsTransparent = true
panel.isMovableByWindowBackground = true
panel.level = .floating
panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
panel.isOpaque = false
panel.backgroundColor = .clear
panel.hasShadow = true

// Size constraints
panel.minSize = NSSize(width: 300, height: 400)
panel.maxSize = NSSize(width: 600, height: 900)
```

---

### `WindowAccessor`
| Metadata | Value |
|---|---|
| Kind | struct |
| Purpose | SwiftUI bridge to access NSWindow |
| Thread-Safe | No |
| Immutable | No |
| Serializable | No |

#### Inheritance & Implementation
- **Extends:** N/A
- **Implements:** `NSViewRepresentable`
- **Used By:** `FloatingPanelPresenter`

#### Fields / Properties
| Name | Type | Visibility | Default | Required | Mutable | Purpose |
|---|---|---|---|---|---|---|
| `window` | `Binding<NSWindow?>` | public | Required | Yes | Yes (binding) | Window reference |

#### Methods
| Method | Purpose |
|---|---|
| `makeNSView(context:)` | Create NSView and capture window |
| `updateNSView(_:context:)` | Update window reference |

---

### `FloatingPanelPresenter`
| Metadata | Value |
|---|---|
| Kind | struct |
| Purpose | SwiftUI wrapper for panel content |
| Thread-Safe | No |
| Immutable | Yes |
| Serializable | No |

#### Inheritance & Implementation
- **Extends:** N/A
- **Implements:** `View`
- **Used By:** SwiftUI views needing window access

#### Generic Parameters
| Parameter | Constraint | Purpose |
|---|---|---|
| `Content` | `View` | Panel content |

#### Fields / Properties
| Name | Type | Visibility | Default | Required | Mutable | Purpose |
|---|---|---|---|---|---|---|
| `content` | Content | public | Required | Yes | No | Wrapped view |
| `window` | `State<NSWindow?>` | private | `nil` | No | Yes | Window state |

---

## NSPanel Behavior

### Non-Activating Panel
The `.nonactivatingPanel` style mask ensures:
- Panel doesn't steal focus from other apps
- User can interact with panel while using other apps
- Panel stays visible when app is not active

### Window Level
`.floating` level keeps the panel above normal windows but below modal dialogs.

### Collection Behavior
| Behavior | Effect |
|---|---|
| `.canJoinAllSpaces` | Panel appears on all virtual desktops |
| `.fullScreenAuxiliary` | Panel can appear alongside full-screen apps |

---

## Animation Details

### Show Animation
```swift
func show() {
    guard let panel = panel else { return }
    
    if !isVisible {
        panel.alphaValue = 0
        panel.makeKeyAndOrderFront(nil)
        
        NSAnimationContext.runAnimationGroup { context in
            context.duration = 0.2
            context.timingFunction = CAMediaTimingFunction(name: .easeOut)
            panel.animator().alphaValue = 1
        }
    }
    
    isVisible = true
}
```

### Hide Animation
```swift
func hide() {
    guard let panel = panel, isVisible else { return }
    
    NSAnimationContext.runAnimationGroup({ context in
        context.duration = 0.15
        context.timingFunction = CAMediaTimingFunction(name: .easeIn)
        panel.animator().alphaValue = 0
    }, completionHandler: {
        panel.orderOut(nil)
    })
    
    isVisible = false
}
```

---

## Actor Isolation

### MainActor Access Pattern
When accessing `AppState.shared` from non-MainActor contexts:

```swift
func toggle() {
    if isVisible {
        hide()
    } else {
        show()
    }
    
    // Update app state on main actor
    Task { @MainActor in
        AppState.shared.isPanelVisible = isVisible
    }
}
```

This pattern is used in:
- `toggle()`
- `windowWillClose(_:)`

---

## NSWindowDelegate Implementation

### Delegate Methods
| Method | Purpose | Implementation |
|---|---|---|
| `windowDidMove(_:)` | Track position | Call `positionManager.panelDidMove` |
| `windowDidEndLiveResize(_:)` | End drag | Call `positionManager.panelDragEnded` |
| `windowWillClose(_:)` | Handle close | Update `isVisible` and `AppState` |

---

## Example Usage

### Basic Setup
```swift
// In AppDelegate
func applicationDidFinishLaunching(_ notification: Notification) {
    FloatingPanelController.shared.setup(appState: AppState.shared)
}

// Toggle on hotkey
GlobalHotkeyManager.shared.onHotkeyPressed = {
    FloatingPanelController.shared.toggle()
}
```

### Programmatic Control
```swift
// Show panel
FloatingPanelController.shared.show()

// Hide panel
FloatingPanelController.shared.hide()

// Snap to right edge
FloatingPanelController.shared.snapTo(edge: .right)

// Center panel
FloatingPanelController.shared.center()
```

---

## Related Documentation

### Related Files
| File Path | Relationship | Why Related |
|---|---|---|
| `ui/AIAgentUI/Window/EdgeSnapping.swift` | Uses | Position management |
| `ui/AIAgentUI/Window/GlobalHotkey.swift` | Used by | Toggle trigger |
| `ui/AIAgentUI/App/AppDelegate.swift` | Used by | Setup and lifecycle |
| `ui/AIAgentUI/Views/MainPanelView.swift` | Uses | Panel content |
| `ui/AIAgentUI/Views/Styles/BlueTheme.swift` | Uses | ThemeConstants |

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-01-18 | AI Assistant | Initial implementation | Created panel controller | New file |
| 2026-01-18 | AI Assistant | Actor isolation fix | Wrapped AppState access in Task | Concurrency safety |
