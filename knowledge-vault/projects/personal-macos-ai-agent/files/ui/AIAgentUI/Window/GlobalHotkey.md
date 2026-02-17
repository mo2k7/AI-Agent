# File Doc: `ui/AIAgentUI/Window/GlobalHotkey.swift`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `ui/AIAgentUI/Window/GlobalHotkey.swift` |
| Doc Path | `projects/personal-macos-ai-agent/files/ui/AIAgentUI/Window/GlobalHotkey.md` |
| Language | Swift |
| File Role | Global Hotkey Registration (Cmd+K) |
| Ownership | Core Team |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-01-18 |
| Last Major Edit (YYYY-MM-DD) | 2026-01-18 |
| Modified By | AI Assistant |
| WHY (Reason for last change) | Initial implementation for panel toggle hotkey |
| Lines of Code (LOC) | 320 |
| Cyclomatic Complexity | Medium |
| Test Coverage | 0% |

---

## Purpose & Responsibilities

### What this file does
**Single-sentence summary:**
Registers and handles the global Cmd+K hotkey using Carbon Event Manager for toggling the AI Agent panel.

**Detailed responsibilities:**
- Registers global Cmd+K hotkey using Carbon's `RegisterEventHotKey`
- Installs Carbon event handler for hotkey events
- Provides callback mechanism (`onHotkeyPressed`) for hotkey triggers
- Supports custom hotkey registration via `registerHotkey(keyCode:modifiers:)`
- Includes comprehensive `KeyCode` enum for all keyboard keys
- Includes `ModifierMask` for modifier key combinations
- Provides alternative `HotKeyMonitor` using NSEvent monitors

### What this file must NOT do (boundaries)
**Out of scope:**
- Panel visibility management (handled by `FloatingPanelController`)
- Application state management
- UI rendering

### Who/what calls it
| Caller | Purpose | Frequency | Error Handling |
|---|---|---|---|
| `AppDelegate` | Register hotkey, set callback | Once at launch | Log errors |

### What it calls
| Callee | Purpose | Error Handling | Fallback Strategy |
|---|---|---|---|
| Carbon HIToolbox | Hotkey registration | Check OSStatus | N/A |
| `FloatingPanelController` | Toggle panel | N/A | N/A |

---

## Imports / Dependencies

### Framework Dependencies
| Framework | What's Used | Why Needed |
|---|---|---|
| Foundation | Basic types | Core functionality |
| AppKit | NSEvent | Alternative implementation |
| Carbon.HIToolbox | EventHotKeyID, RegisterEventHotKey | Global hotkey |

---

## Public Surface (Document EVERYTHING Exposed)

### Exports / Public Symbols
| Symbol | Type (func/class/const/type) | Visibility | Status | Brief Description |
|---|---|---|---|---|
| `GlobalHotkeyManager` | class | public | Stable | Carbon-based hotkey manager |
| `HotKeyMonitor` | class | public | Stable | NSEvent-based alternative |
| `KeyCode` | enum | public | Stable | Keyboard key codes |
| `ModifierMask` | struct | public | Stable | Modifier key combinations |

---

## Types (Classes / Structs / Enums / Interfaces)

### `GlobalHotkeyManager`
| Metadata | Value |
|---|---|
| Kind | class |
| Purpose | Singleton for Carbon global hotkey management |
| Thread-Safe | No (main thread only) |
| Immutable | No |
| Serializable | No |

#### Fields / Properties
| Name | Type | Visibility | Default | Required | Mutable | Purpose |
|---|---|---|---|---|---|---|
| `shared` | GlobalHotkeyManager | static | Singleton | N/A | No | Global instance |
| `hotkeyRef` | EventHotKeyRef? | private | `nil` | No | Yes | Registered hotkey |
| `eventHandlerRef` | EventHandlerRef? | private | `nil` | No | Yes | Event handler |
| `hotkeyID` | EventHotKeyID | private | Custom | N/A | No | Unique ID |
| `onHotkeyPressed` | `(() -> Void)?` | public | `nil` | No | Yes | Callback |

#### Methods
| Method | Signature | Visibility | Returns | Purpose |
|---|---|---|---|---|
| `registerHotkey` | `() -> Bool` | public | Success | Register Cmd+K |
| `registerHotkey` | `(keyCode: UInt32, modifiers: UInt32) -> Bool` | public | Success | Register custom |
| `unregisterHotkey` | `()` | public | None | Unregister current |
| `installEventHandler` | `() private` | private | None | Install Carbon handler |

#### Hotkey ID
```swift
private let hotkeyID = EventHotKeyID(
    signature: OSType(0x41474E54),  // "AGNT" in ASCII
    id: 1
)
```

---

### `HotKeyMonitor`
| Metadata | Value |
|---|---|
| Kind | class |
| Purpose | Alternative using NSEvent monitors (no Carbon) |
| Thread-Safe | No |
| Immutable | No |
| Serializable | No |

#### When to Use
Use `HotKeyMonitor` instead of `GlobalHotkeyManager` when:
- Carbon APIs are deprecated in future macOS
- App Sandbox restrictions apply
- Accessibility permissions are available

#### Fields / Properties
| Name | Type | Visibility | Default | Required | Mutable | Purpose |
|---|---|---|---|---|---|---|
| `shared` | HotKeyMonitor | static | Singleton | N/A | No | Global instance |
| `globalMonitor` | Any? | private | `nil` | No | Yes | Global key monitor |
| `localMonitor` | Any? | private | `nil` | No | Yes | Local key monitor |
| `onHotkeyPressed` | `(() -> Void)?` | public | `nil` | No | Yes | Callback |

#### Methods
| Method | Signature | Visibility | Purpose |
|---|---|---|---|
| `startMonitoring` | `()` | public | Start listening |
| `stopMonitoring` | `()` | public | Stop listening |
| `handleKeyEvent` | `(_ event: NSEvent) private` | private | Process key event |

---

### `KeyCode`
| Metadata | Value |
|---|---|
| Kind | enum |
| Purpose | Comprehensive keyboard key codes |
| Thread-Safe | Yes (immutable) |
| Immutable | Yes |
| Serializable | No |

#### Inheritance & Implementation
- **Extends:** `UInt32`
- **Implements:** N/A

#### Selected Cases
| Case | Raw Value | Purpose |
|---|---|---|
| `a` | `0x00` | Letter A |
| `k` | `0x28` | Letter K (default hotkey) |
| `space` | `0x31` | Space bar |
| `returnKey` | `0x24` | Return/Enter |
| `escape` | `0x35` | Escape key |
| `f1`-`f15` | Various | Function keys |

#### Full Key Mapping
```swift
enum KeyCode: UInt32 {
    case a = 0x00, s = 0x01, d = 0x02, f = 0x03
    case h = 0x04, g = 0x05, z = 0x06, x = 0x07
    case c = 0x08, v = 0x09, b = 0x0B
    case q = 0x0C, w = 0x0D, e = 0x0E, r = 0x0F
    case y = 0x10, t = 0x11
    case one = 0x12, two = 0x13, three = 0x14
    case four = 0x15, six = 0x16, five = 0x17
    case equals = 0x18, nine = 0x19, seven = 0x1A
    case minus = 0x1B, eight = 0x1C, zero = 0x1D
    case rightBracket = 0x1E, o = 0x1F
    case u = 0x20, leftBracket = 0x21, i = 0x22
    case p = 0x23, returnKey = 0x24, l = 0x25
    case j = 0x26, apostrophe = 0x27, k = 0x28
    case semicolon = 0x29, backslash = 0x2A
    case comma = 0x2B, slash = 0x2C, n = 0x2D
    case m = 0x2E, period = 0x2F, tab = 0x30
    case space = 0x31, grave = 0x32, delete = 0x33
    case escape = 0x35
    case f5 = 0x60, f6 = 0x61, f7 = 0x62
    case f3 = 0x63, f8 = 0x64, f9 = 0x65
    case f11 = 0x67, f13 = 0x69, f14 = 0x6B
    case f10 = 0x6D, f12 = 0x6F, f15 = 0x71
    case f4 = 0x76, f2 = 0x78, f1 = 0x7A
}
```

---

### `ModifierMask`
| Metadata | Value |
|---|---|
| Kind | struct |
| Purpose | Modifier key combinations for Carbon |
| Thread-Safe | Yes (value type) |
| Immutable | Yes |
| Serializable | No |

#### Inheritance & Implementation
- **Extends:** N/A
- **Implements:** `OptionSet`

#### Static Members
| Member | Carbon Value | Purpose |
|---|---|---|
| `command` | `cmdKey` | Command (⌘) |
| `option` | `optionKey` | Option (⌥) |
| `control` | `controlKey` | Control (⌃) |
| `shift` | `shiftKey` | Shift (⇧) |

#### Computed Properties
| Property | Type | Purpose |
|---|---|---|
| `carbonModifiers` | UInt32 | Convert to Carbon format |

---

## Carbon Hotkey Implementation

### Registration
```swift
@discardableResult
func registerHotkey() -> Bool {
    unregisterHotkey()
    
    // Cmd+K: keyCode 0x28, modifiers cmdKey
    let keyCode: UInt32 = 0x28
    let modifiers: UInt32 = UInt32(cmdKey)
    
    var hotKeyID = hotkeyID
    let status = RegisterEventHotKey(
        keyCode,
        modifiers,
        hotKeyID,
        GetApplicationEventTarget(),
        0,
        &hotkeyRef
    )
    
    guard status == noErr else {
        print("Failed to register hotkey: \(status)")
        return false
    }
    
    installEventHandler()
    return true
}
```

### Event Handler
```swift
private func installEventHandler() {
    var eventType = EventTypeSpec(
        eventClass: OSType(kEventClassKeyboard),
        eventKind: UInt32(kEventHotKeyPressed)
    )
    
    let selfPtr = Unmanaged.passUnretained(self).toOpaque()
    
    InstallEventHandler(
        GetApplicationEventTarget(),
        { (_, event, userData) -> OSStatus in
            guard let userData = userData else {
                return OSStatus(eventNotHandledErr)
            }
            
            let manager = Unmanaged<GlobalHotkeyManager>
                .fromOpaque(userData)
                .takeUnretainedValue()
            
            // Verify hotkey ID
            var hotKeyID = EventHotKeyID()
            GetEventParameter(
                event,
                EventParamName(kEventParamDirectObject),
                EventParamType(typeEventHotKeyID),
                nil,
                MemoryLayout<EventHotKeyID>.size,
                nil,
                &hotKeyID
            )
            
            if hotKeyID.id == manager.hotkeyID.id {
                DispatchQueue.main.async {
                    manager.onHotkeyPressed?()
                }
            }
            
            return noErr
        },
        1,
        &eventType,
        selfPtr,
        &eventHandlerRef
    )
}
```

---

## NSEvent Alternative Implementation

### Global + Local Monitors
```swift
func startMonitoring() {
    // Global monitor (app not focused)
    globalMonitor = NSEvent.addGlobalMonitorForEvents(matching: .keyDown) { [weak self] event in
        self?.handleKeyEvent(event)
    }
    
    // Local monitor (app focused)
    localMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] event in
        self?.handleKeyEvent(event)
        return event
    }
}

private func handleKeyEvent(_ event: NSEvent) {
    // Check for Cmd+K
    if event.modifierFlags.contains(.command) &&
       event.keyCode == KeyCode.k.rawValue {
        DispatchQueue.main.async { [weak self] in
            self?.onHotkeyPressed?()
        }
    }
}
```

### Comparison
| Feature | GlobalHotkeyManager | HotKeyMonitor |
|---|---|---|
| API | Carbon | NSEvent |
| Global capture | Yes | Yes (needs accessibility) |
| Sandbox compatible | Yes | Limited |
| Future support | Deprecated soon? | Preferred |
| Setup complexity | Higher | Lower |

---

## Example Usage

### Basic Setup (Carbon)
```swift
// In AppDelegate
func applicationDidFinishLaunching(_ notification: Notification) {
    // Set callback
    GlobalHotkeyManager.shared.onHotkeyPressed = {
        FloatingPanelController.shared.toggle()
    }
    
    // Register Cmd+K
    GlobalHotkeyManager.shared.registerHotkey()
}

func applicationWillTerminate(_ notification: Notification) {
    GlobalHotkeyManager.shared.unregisterHotkey()
}
```

### Custom Hotkey
```swift
// Register Cmd+Shift+Space
GlobalHotkeyManager.shared.registerHotkey(
    keyCode: KeyCode.space.rawValue,
    modifiers: UInt32(cmdKey | shiftKey)
)
```

### Alternative (NSEvent)
```swift
func applicationDidFinishLaunching(_ notification: Notification) {
    HotKeyMonitor.shared.onHotkeyPressed = {
        FloatingPanelController.shared.toggle()
    }
    
    HotKeyMonitor.shared.startMonitoring()
}

func applicationWillTerminate(_ notification: Notification) {
    HotKeyMonitor.shared.stopMonitoring()
}
```

---

## Error Handling

### OSStatus Codes
| Code | Meaning | Resolution |
|---|---|---|
| `noErr` (0) | Success | N/A |
| `-9878` | Hotkey already registered | Unregister first |
| `-50` | Invalid parameter | Check key code |

### Logging
```swift
guard status == noErr else {
    print("Failed to register hotkey: \(status)")
    return false
}
```

---

## Related Documentation

### Related Files
| File Path | Relationship | Why Related |
|---|---|---|
| `ui/AIAgentUI/Window/FloatingPanelController.swift` | Called by | Toggle callback |
| `ui/AIAgentUI/App/AppDelegate.swift` | Used by | Registration |

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-01-18 | AI Assistant | Initial implementation | Created hotkey manager | New file |
