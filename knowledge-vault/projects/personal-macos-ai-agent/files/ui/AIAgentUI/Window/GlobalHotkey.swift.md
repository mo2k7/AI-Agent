# File Doc: `ui/AIAgentUI/Window/GlobalHotkey.swift`

## File Metadata
| Field | Value |
|---|---|
| Project | personal-macos-ai-agent |
| Code File Path | `ui/AIAgentUI/Window/GlobalHotkey.swift` |
| Doc Path | `projects/personal-macos-ai-agent/files/ui/AIAgentUI/Window/GlobalHotkey.swift.md` |
| Language | Swift 6 |
| File Role | UI |
| Ownership | @individual-developer |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-01-18 |
| Last Major Edit (YYYY-MM-DD) | 2026-01-18 |
| Modified By | AI Agent (Claude) |
| WHY (Reason for last change) | Swift 6 concurrency: Removed unnecessary var copies for RegisterEventHotKey |
| Lines of Code (LOC) | 320 |
| Cyclomatic Complexity | Medium |
| Test Coverage | 0% (System integration) |

---

## Purpose & Responsibilities

### What this file does
**Single-sentence summary:** Registers and manages global Cmd+K hotkey using Carbon Event Manager to toggle the AI agent panel from anywhere in macOS.

**Detailed responsibilities:**
- Registers global Cmd+K hotkey via Carbon API (`RegisterEventHotKey`)
- Installs Carbon event handler for hotkey events
- Provides callback mechanism for hotkey activation
- Includes fallback implementation using NSEvent monitors
- Defines common key codes and modifier masks

### What this file must NOT do (boundaries)
**Out of scope:**
- Does NOT manage the panel itself (see `FloatingPanelController.swift`)
- Does NOT handle other keyboard shortcuts (local to panel)

### Who/what calls it
| Caller | Purpose | Frequency | Error Handling |
|---|---|---|---|
| `AppDelegate.swift` | Registers hotkey on launch | Once at startup | Falls back to NSEvent monitor |

---

## Imports / Dependencies

### External Dependencies
| Package | Version | License | What's Used | Why Needed | Security Risk | Alternatives |
|---|---|---|---|---|---|---|
| Foundation | System | Apple | Basic types | Required | Low | None |
| AppKit | System | Apple | NSEvent | Fallback monitoring | Low | None |
| Carbon.HIToolbox | System | Apple | RegisterEventHotKey, EventHotKeyID | Global hotkey registration | Low | NSEvent (less reliable globally) |

---

## Public Surface (Document EVERYTHING Exposed)

### Exports / Public Symbols
| Symbol | Type | Visibility | Status | Brief Description |
|---|---|---|---|---|
| `GlobalHotkeyManager` | class | internal | Stable | Carbon-based global hotkey manager |
| `KeyCode` | enum | internal | Stable | Key code constants |
| `ModifierMask` | struct | internal | Stable | Modifier key masks |
| `HotKeyMonitor` | class | internal | Stable | NSEvent-based fallback |

---

## Types (Classes / Structs / Enums / Interfaces)

### `GlobalHotkeyManager`
| Metadata | Value |
|---|---|
| Kind | class |
| Purpose | Registers global hotkeys using Carbon Event Manager |
| Thread-Safe | Yes (@MainActor singleton) |
| Immutable | No |
| Serializable | No |
| Related Types | `EventHotKeyID`, `EventHotKeyRef` |

#### Singleton Pattern
```swift
@MainActor
static let shared = GlobalHotkeyManager()
```

#### Fields / Properties
| Name | Type | Visibility | Default | Required | Mutable | Purpose |
|---|---|---|---|---|---|---|
| `hotkeyRef` | `EventHotKeyRef?` | private | `nil` | No | Yes | Carbon hotkey reference |
| `eventHandlerRef` | `EventHandlerRef?` | private | `nil` | No | Yes | Carbon event handler |
| `hotkeyID` | `EventHotKeyID` | private | signature=0x41474E54 ("AGNT"), id=1 | Yes | No | Unique hotkey identifier |
| `onHotkeyPressed` | `(() -> Void)?` | internal | `nil` | No | Yes | Callback handler |

#### Methods
| Method | Visibility | Parameters | Returns | Side Effects | Notes |
|---|---|---|---|---|---|
| `registerHotkey()` | internal | None | `Bool` | Registers Cmd+K | Returns success status |
| `registerHotkey(keyCode:modifiers:)` | internal | `UInt32`, `UInt32` | `Bool` | Custom hotkey | For customization |
| `unregisterHotkey()` | internal | None | Void | Removes hotkey | Cleanup |

### `KeyCode`
| Metadata | Value |
|---|---|
| Kind | enum |
| Purpose | Key code constants for hotkey registration |
| Thread-Safe | Yes (immutable) |
| Raw Type | `UInt32` |

#### Selected Cases
| Case | Raw Value | Description |
|---|---|---|
| `.k` | `0x28` | The 'K' key (default hotkey) |
| `.returnKey` | `0x24` | Return/Enter key |
| `.escape` | `0x35` | Escape key |
| `.space` | `0x31` | Space bar |
| `.tab` | `0x30` | Tab key |

### `ModifierMask`
| Metadata | Value |
|---|---|
| Kind | struct (OptionSet) |
| Purpose | Modifier key masks for Carbon |
| Thread-Safe | Yes (value type) |

#### Options
| Option | Carbon Value | Description |
|---|---|---|
| `.command` | `cmdKey` | Command (⌘) key |
| `.option` | `optionKey` | Option (⌥) key |
| `.control` | `controlKey` | Control (⌃) key |
| `.shift` | `shiftKey` | Shift (⇧) key |

### `HotKeyMonitor`
| Metadata | Value |
|---|---|
| Kind | class |
| Purpose | Fallback hotkey implementation using NSEvent monitors |
| Thread-Safe | Yes (@MainActor singleton) |
| Immutable | No |

#### Usage
Used when Carbon registration fails (e.g., accessibility permissions not granted).

#### Methods
| Method | Visibility | Parameters | Returns | Side Effects |
|---|---|---|---|---|
| `startMonitoring()` | internal | None | Void | Adds NSEvent monitors |
| `stopMonitoring()` | internal | None | Void | Removes monitors |

---

## Concurrency & Threading

### Swift 6 Concurrency Fix Applied
The `registerHotkey()` method had an unnecessary variable copy that Swift 6 flagged:

| Before | After | Reason |
|---|---|---|
| `var localHotkeyID = hotkeyID` then pass `&localHotkeyID` | Pass `hotkeyID` directly | `hotkeyID` is already `let`, no need for mutable copy |

```swift
// Swift 6 compliant version - pass hotkeyID directly
let status = RegisterEventHotKey(
    keyCode,
    modifiers,
    hotkeyID,  // Direct use, no copy needed
    GetApplicationEventTarget(),
    0,
    &hotkeyRef
)
```

### Why Carbon API Still Works
- Carbon Event Manager is still supported on macOS for global hotkeys
- No pure Swift/Cocoa alternative provides reliable global hotkey capture
- NSEvent monitors require accessibility permissions and can miss events

---

## Security Considerations

### Accessibility Permissions
| Concern | Details | Mitigation |
|---|---|---|
| Accessibility Access | Global hotkey requires accessibility permissions | Fallback to NSEvent if Carbon fails |
| Privacy | Can detect keystrokes app-wide | Only registers specific hotkey, not keylogger |

---

## Related Documentation

### Related Files
| File Path | Relationship | Why Related |
|---|---|---|
| `ui/AIAgentUI/App/AppDelegate.swift` | Uses | Registers hotkey and sets callback |
| `ui/AIAgentUI/Window/FloatingPanelController.swift` | Triggers | Called via toggle() on hotkey |

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-01-18 | AI Agent (Claude) | Initial creation | Created GlobalHotkeyManager for Cmd+K hotkey | High |
| 2026-01-18 | AI Agent (Claude) | Swift 6 concurrency | Removed unnecessary var copies for hotkeyID | Low |
