# File Doc: `ui/AIAgentUI/App/AppDelegate.swift`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `ui/AIAgentUI/App/AppDelegate.swift` |
| Doc Path | `projects/personal-macos-ai-agent/files/ui/AIAgentUI/App/AppDelegate.md` |
| Language | Swift |
| File Role | Application Delegate |
| Ownership | Core Team |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-01-18 |
| Last Major Edit (YYYY-MM-DD) | 2026-01-18 |
| Modified By | AI Assistant |
| WHY (Reason for last change) | Fixed actor isolation for AppState access |
| Lines of Code (LOC) | 301 |
| Cyclomatic Complexity | Low |
| Test Coverage | 0% |

---

## Purpose & Responsibilities

### What this file does
**Single-sentence summary:**
Application delegate that handles macOS app lifecycle, sets up the floating panel, registers global hotkey, and manages menu items.

**Detailed responsibilities:**
- Implements `NSApplicationDelegate` for app lifecycle
- Sets up `FloatingPanelController` with `AppState`
- Registers global Cmd+K hotkey via `GlobalHotkeyManager`
- Creates status bar menu item with brain icon
- Provides menu actions: toggle, show, hide, reconnect, clear, quit
- Handles app termination cleanup
- Auto-connects to IPC server on launch

### What this file must NOT do (boundaries)
**Out of scope:**
- UI rendering (handled by SwiftUI views)
- State management logic (handled by `AppState`)
- Window positioning (handled by `FloatingPanelController`)
- IPC communication (handled by `IPCClient`)

### Who/what calls it
| Caller | Purpose | Frequency | Error Handling |
|---|---|---|---|
| macOS System | App lifecycle | On launch/terminate | N/A |

### What it calls
| Callee | Purpose | Error Handling | Fallback Strategy |
|---|---|---|---|
| `FloatingPanelController` | Setup panel | N/A | N/A |
| `GlobalHotkeyManager` | Register hotkey | Logs failures | N/A |
| `AppState` | State access | N/A | N/A |

---

## Imports / Dependencies

### Framework Dependencies
| Framework | What's Used | Why Needed |
|---|---|---|
| AppKit | NSApplicationDelegate | App lifecycle |
| SwiftUI | N/A | State interop |

### Internal Dependencies
| Import Path | What's Used | Why Needed | Coupling Level |
|---|---|---|---|
| Same module | `FloatingPanelController`, `GlobalHotkeyManager`, `AppState` | Setup | High |

---

## Public Surface (Document EVERYTHING Exposed)

### Exports / Public Symbols
| Symbol | Type (func/class/const/type) | Visibility | Status | Brief Description |
|---|---|---|---|---|
| `AppDelegate` | class | public | Stable | NSApplicationDelegate |

---

## Types (Classes / Structs / Enums / Interfaces)

### `AppDelegate`
| Metadata | Value |
|---|---|
| Kind | class |
| Purpose | macOS application delegate |
| Thread-Safe | No (main thread only) |
| Immutable | No |
| Serializable | No |

#### Inheritance & Implementation
- **Extends:** `NSObject`
- **Implements:** `NSApplicationDelegate`
- **Used By:** `AIAgentUIApp` (via `@NSApplicationDelegateAdaptor`)

#### Fields / Properties
| Name | Type | Visibility | Default | Required | Mutable | Purpose |
|---|---|---|---|---|---|---|
| `statusItem` | NSStatusItem? | private | `nil` | No | Yes | Menu bar item |

---

## Lifecycle Methods

### `applicationDidFinishLaunching(_:)`
```swift
func applicationDidFinishLaunching(_ notification: Notification) {
    // 1. Setup floating panel
    Task { @MainActor in
        FloatingPanelController.shared.setup(appState: AppState.shared)
    }
    
    // 2. Register global hotkey
    GlobalHotkeyManager.shared.onHotkeyPressed = {
        FloatingPanelController.shared.toggle()
    }
    GlobalHotkeyManager.shared.registerHotkey()
    
    // 3. Create status bar item
    setupStatusBarItem()
    
    // 4. Auto-connect to backend
    Task { @MainActor in
        await AppState.shared.connect()
    }
}
```

### `applicationWillTerminate(_:)`
```swift
func applicationWillTerminate(_ notification: Notification) {
    // 1. Unregister hotkey
    GlobalHotkeyManager.shared.unregisterHotkey()
    
    // 2. Disconnect IPC
    Task { @MainActor in
        await AppState.shared.disconnect()
    }
}
```

### `applicationShouldHandleReopen(_:hasVisibleWindows:)`
```swift
func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
    // Show panel when clicking dock icon
    if !flag {
        FloatingPanelController.shared.show()
    }
    return true
}
```

---

## Status Bar Item

### Setup
```swift
private func setupStatusBarItem() {
    statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
    
    if let button = statusItem?.button {
        button.image = NSImage(systemSymbolName: "brain", accessibilityDescription: "AI Agent")
        button.action = #selector(statusBarButtonClicked)
        button.target = self
    }
    
    // Create menu
    let menu = NSMenu()
    menu.addItem(withTitle: "Toggle Panel", action: #selector(togglePanel), keyEquivalent: "k")
    menu.addItem(withTitle: "Show Panel", action: #selector(showPanel), keyEquivalent: "")
    menu.addItem(withTitle: "Hide Panel", action: #selector(hidePanel), keyEquivalent: "")
    menu.addItem(NSMenuItem.separator())
    menu.addItem(withTitle: "Reconnect", action: #selector(reconnect), keyEquivalent: "r")
    menu.addItem(withTitle: "Clear Messages", action: #selector(clearMessages), keyEquivalent: "")
    menu.addItem(NSMenuItem.separator())
    menu.addItem(withTitle: "Quit", action: #selector(quit), keyEquivalent: "q")
    
    statusItem?.menu = menu
}
```

### Menu Icon
- **Symbol:** `brain` (SF Symbol)
- **Accessibility:** "AI Agent"

---

## Menu Actions

### `togglePanel`
```swift
@objc func togglePanel() {
    FloatingPanelController.shared.toggle()
}
```

### `showPanel`
```swift
@objc func showPanel() {
    FloatingPanelController.shared.show()
}
```

### `hidePanel`
```swift
@objc func hidePanel() {
    FloatingPanelController.shared.hide()
}
```

### `reconnect`
```swift
@objc func reconnect() {
    Task { @MainActor in
        await AppState.shared.disconnect()
        await AppState.shared.connect()
    }
}
```

### `clearMessages`
```swift
@objc func clearMessages() {
    Task { @MainActor in
        AppState.shared.clearMessages()
    }
}
```

### `quit`
```swift
@objc func quit() {
    NSApplication.shared.terminate(nil)
}
```

---

## Actor Isolation

### MainActor Pattern
Since `AppState` is `@MainActor` isolated, all access from `AppDelegate` must be wrapped:

```swift
// Correct pattern
Task { @MainActor in
    FloatingPanelController.shared.setup(appState: AppState.shared)
    await AppState.shared.connect()
}

// For synchronous properties
Task { @MainActor in
    AppState.shared.clearMessages()
}
```

---

## Menu Structure

```
[🧠] AI Agent (Status Bar)
├── Toggle Panel     ⌘K
├── Show Panel
├── Hide Panel
├── ─────────────────
├── Reconnect        ⌘R
├── Clear Messages
├── ─────────────────
└── Quit             ⌘Q
```

---

## Related Documentation

### Related Files
| File Path | Relationship | Why Related |
|---|---|---|
| `ui/AIAgentUI/App/AIAgentUIApp.swift` | Uses | App entry point |
| `ui/AIAgentUI/Window/FloatingPanelController.swift` | Uses | Panel management |
| `ui/AIAgentUI/Window/GlobalHotkey.swift` | Uses | Hotkey registration |
| `ui/AIAgentUI/State/AppState.swift` | Uses | State access |

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-01-18 | AI Assistant | Initial implementation | Created app delegate | New file |
| 2026-01-18 | AI Assistant | Actor isolation fix | Wrapped AppState access in Tasks | Concurrency safety |
