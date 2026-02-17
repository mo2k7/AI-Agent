# File Doc: `ui/AIAgentUI/App/AIAgentUIApp.swift`

## File Metadata
| Field | Value |
|---|---|
| Project | personal-macos-ai-agent |
| Code File Path | `ui/AIAgentUI/App/AIAgentUIApp.swift` |
| Doc Path | `projects/personal-macos-ai-agent/files/ui/AIAgentUI/App/AIAgentUIApp.swift.md` |
| Language | Swift 6 |
| File Role | Application Entry Point |
| Ownership | @individual-developer |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-01-18 |
| Last Major Edit (YYYY-MM-DD) | 2026-01-18 |
| Modified By | AI Agent (Codex) |
| WHY (Reason for last change) | Bind model picker to AppState-selected model for live switching |
| Lines of Code (LOC) | ~250 |
| Cyclomatic Complexity | Low |
| Test Coverage | 0% (UI Entry Point) |

---

## Purpose & Responsibilities

### What this file does
**Single-sentence summary:** Entry point for the Personal macOS AI Agent SwiftUI application that configures app-level scenes, integrates AppDelegate for AppKit lifecycle management, and provides system menu bar integration.

**Detailed responsibilities:**
- Mark app entry point with `@main` attribute
- Bridge SwiftUI lifecycle with AppKit's `AppDelegate` for hotkey and panel management
- Provide `Settings` window scene with tabbed configuration interface
- Provide `MenuBarExtra` scene for system tray icon and dropdown menu
- Manage global `AppState` singleton via `@StateObject`
- Configure app-level UI scenes and navigation

### What this file must NOT do (boundaries)
**Out of scope:**
- Does NOT manage floating panel directly (handled by `FloatingPanelController`)
- Does NOT implement backend communication (handled by `IPCClient`)
- Does NOT handle hotkey registration (handled by `AppDelegate`)
- Does NOT manage application state (handled by `AppState`)

### Who/what calls it
| Caller | Purpose | Frequency | Error Handling |
|---|---|---|---|
| SwiftUI Runtime | App entry point via `@main` | Once per launch | Framework-handled |
| System | Settings menu access | User-driven | N/A |
| System | Menu bar icon interaction | User-driven | N/A |

### What it calls
| Callee | Purpose | Error Handling | Fallback Strategy |
|---|---|---|---|
| `AppDelegate` | AppKit lifecycle, hotkeys | Via `@NSApplicationDelegateAdaptor` | Framework-handled |
| `AppState` | Global state management | Via `@StateObject` | N/A |
| `FloatingPanelController` | Panel toggle | Via AppDelegate | N/A |

---

## Imports / Dependencies

### Internal Dependencies
| Import Path | What's Used | Why Needed | Coupling Level | Risk/Notes |
|---|---|---|---|---|
| SwiftUI | App, Scene, View, etc. | UI framework | High | System framework |

### External Dependencies
| Package | Version | License | What's Used | Why Needed | Security Risk | Alternatives |
|---|---|---|---|---|---|---|
| SwiftUI | System | Apple | All components | macOS app UI | Low | AppKit (legacy) |

---

## Public Surface (Document EVERYTHING Exposed)

### Exports / Public Symbols
| Symbol | Type (func/class/const/type) | Visibility | Status | Brief Description |
|---|---|---|---|---|
| `AIAgentUIApp` | struct | internal | Stable | Main app entry point with @main |
| `SettingsView` | struct | internal | Stable | Settings window content |
| `GeneralSettingsView` | struct | internal | Stable | General tab in settings |
| `ConnectionSettingsView` | struct | internal | Stable | Connection tab in settings |
| `AppearanceSettingsView` | struct | internal | Stable | Appearance tab in settings |
| `MenuBarView` | struct | internal | Stable | Menu bar dropdown content |
| `GeminiModel` | enum | internal | Stable | Available AI model options (Session 3) |

---

## Types (Classes / Structs / Enums / Interfaces)

### `AIAgentUIApp`
| Metadata | Value |
|---|---|
| Kind | struct |
| Purpose | SwiftUI app entry point marked with @main |
| Thread-Safe | Yes (@MainActor via SwiftUI) |
| Immutable | No (mutable state via @StateObject) |
| Serializable | No |
| Related Types | AppDelegate, AppState |

#### Inheritance & Implementation
- **Extends:** None
- **Implements:** `App` protocol (SwiftUI)
- **Used By:** SwiftUI runtime
- **Polymorphic Behavior:** None

#### Fields / Properties
| Name | Type | Visibility | Default | Required | Mutable | Purpose | Validation | Notes |
|---|---|---|---|---|---|---|---|---|
| `appDelegate` | `AppDelegate` | internal | Injected | Yes | No | AppKit lifecycle integration | Framework | `@NSApplicationDelegateAdaptor` |
| `appState` | `AppState` | private | `AppState.shared` | Yes | No | Global state singleton | N/A | `@StateObject` wrapper |

#### Body (Scenes)
The app defines two scenes:
1. **Settings**: `Settings { SettingsView() }` - Configuration window
2. **MenuBarExtra**: System tray icon with dropdown menu

### `SettingsView`
| Metadata | Value |
|---|---|
| Kind | struct |
| Purpose | Tabbed settings interface |
| Thread-Safe | Yes (@MainActor via SwiftUI) |
| Immutable | View struct (immutable) |
| Serializable | No |
| Related Types | GeneralSettingsView, ConnectionSettingsView, AppearanceSettingsView |

#### Fields / Properties
| Name | Type | Visibility | Default | Required | Mutable | Purpose | Validation | Notes |
|---|---|---|---|---|---|---|---|---|
| `appState` | `AppState` | N/A | From environment | Yes | No | Injected via `@EnvironmentObject` | N/A | Shared state |
| `selectedTab` | `String` | private | `"general"` | Yes | Yes | Current tab selection | N/A | `@State` |

#### Body (UI Structure)
```
TabView
├── GeneralSettingsView (tag: "general")
├── ConnectionSettingsView (tag: "connection")
└── AppearanceSettingsView (tag: "appearance")
```

### `GeneralSettingsView`
| Metadata | Value |
|---|---|
| Kind | struct |
| Purpose | General settings tab (launch, window behavior) |
| Thread-Safe | Yes |
| Immutable | View struct |
| Serializable | No |
| Related Types | PanelPositionManager |

#### Fields / Properties (AppStorage)
| Name | Type | Visibility | Default | Required | Mutable | Purpose | Validation | Notes |
|---|---|---|---|---|---|---|---|---|
| `launchAtLogin` | `Bool` | private | `false` | Yes | Yes | Auto-start on boot | N/A | `@AppStorage` persisted |
| `showInDock` | `Bool` | private | `false` | Yes | Yes | Dock icon visibility | N/A | `@AppStorage` persisted |
| `enableSnapping` | `Bool` | private | `true` | Yes | Yes | Window edge snapping | N/A | `@AppStorage` persisted |

#### UI Elements
- **Startup Section**: `launchAtLogin`, `showInDock` toggles
- **Window Behavior Section**: `enableSnapping` toggle (syncs to `PanelPositionManager`)
- **Hotkey Section**: Static display of Cmd+K shortcut

### `ConnectionSettingsView`
| Metadata | Value |
|---|---|
| Kind | struct |
| Purpose | Backend connection settings tab |
| Thread-Safe | Yes |
| Immutable | View struct |
| Serializable | No |
| Related Types | AppState |

#### Fields / Properties
| Name | Type | Visibility | Default | Required | Mutable | Purpose | Validation | Notes |
|---|---|---|---|---|---|---|---|---|
| `appState` | `AppState` | N/A | From environment | Yes | No | `@EnvironmentObject` | N/A | Connection status |
| `autoConnect` | `Bool` | private | `true` | Yes | Yes | Auto-connect on launch | N/A | `@AppStorage` |
| `reconnectOnFailure` | `Bool` | private | `true` | Yes | Yes | Auto-retry logic | N/A | `@AppStorage` |

#### UI Elements
- **Connection Section**: 
  - Status indicator (green/red circle)
  - `autoConnect` toggle
  - `reconnectOnFailure` toggle
- **AI Model Section**:
  - Picker bound to `AppState.selectedModel`
  - Preview badge for experimental models
- **Action Button**: "Reconnect Now" (disabled when connected)

### `AppearanceSettingsView`
| Metadata | Value |
|---|---|
| Kind | struct |
| Purpose | UI appearance settings tab |
| Thread-Safe | Yes |
| Immutable | View struct |
| Serializable | No |
| Related Types | None |

#### Fields / Properties
| Name | Type | Visibility | Default | Required | Mutable | Purpose | Validation | Notes |
|---|---|---|---|---|---|---|---|---|
| `panelOpacity` | `Double` | private | `0.95` | Yes | Yes | Glass effect opacity | 0.5-1.0 range | `@AppStorage` |
| `animationsEnabled` | `Bool` | private | `true` | Yes | Yes | UI animation toggle | N/A | `@AppStorage` |

#### UI Elements
- **Panel Section**: Opacity slider (50%-100%)
- **Animations Section**: `animationsEnabled` toggle

### `MenuBarView`
| Metadata | Value |
|---|---|
| Kind | struct |
| Purpose | Menu bar dropdown menu content |
| Thread-Safe | Yes |
| Immutable | View struct |
| Serializable | No |
| Related Types | AppState, FloatingPanelController |

#### Fields / Properties
| Name | Type | Visibility | Default | Required | Mutable | Purpose | Validation | Notes |
|---|---|---|---|---|---|---|---|---|
| `appState` | `AppState` | N/A | From environment | Yes | No | `@EnvironmentObject` | N/A | Connection status |

#### UI Elements (VStack)
1. **Status Row**: Connection indicator + text
2. **Divider**
3. **Show/Hide Panel**: Calls `FloatingPanelController.shared.toggle()` (Cmd+K shortcut)
4. **Reconnect**: Calls `AppState.reconnect()` (disabled when connected)
5. **Divider**
6. **Quit**: Calls `NSApplication.shared.terminate(nil)` (Cmd+Q shortcut)

---

## Architecture & Design

### Why No WindowGroup?
The main UI is a **floating panel** managed by `FloatingPanelController`, not a standard SwiftUI `WindowGroup`. This design allows:
- Always-on-top behavior via `NSPanel`
- Custom window chrome (borderless, non-activating)
- Edge snapping functionality
- Global hotkey toggling (Cmd+K)
- Non-intrusive always-available UI

### SwiftUI + AppKit Integration
```
SwiftUI Lifecycle
    ↓
AIAgentUIApp (@main)
    ↓
@NSApplicationDelegateAdaptor
    ↓
AppDelegate (AppKit)
    ├── applicationDidFinishLaunching() → FloatingPanelController.setup()
    ├── Global hotkey registration (Carbon API)
    └── Panel lifecycle management
```

**Why AppDelegate?**
SwiftUI's pure declarative model lacks:
1. Global hotkey registration (requires Carbon/AppKit)
2. NSPanel management (floating windows need AppKit)
3. App lifecycle hooks (`applicationDidFinishLaunching`, etc.)

`@NSApplicationDelegateAdaptor` bridges these gaps while keeping SwiftUI as the UI layer.

---

## State Management

### State Flow
```
User Action (Settings or Menu Bar)
    ↓
@EnvironmentObject AppState
    ↓
Backend Actions (IPCClient, BackendLauncher)
    ↓
@Published properties update
    ↓
SwiftUI re-renders
```

### Persistence
All settings use `@AppStorage` which persists to `UserDefaults`:
- `launchAtLogin`
- `showInDock`
- `enableSnapping`
- `autoConnect`
- `reconnectOnFailure`
- `panelOpacity`
- `animationsEnabled`

---

## Concurrency & Threading

### Swift 6 Concurrency
| Component | Isolation | Pattern |
|---|---|---|
| `AIAgentUIApp` | `@MainActor` (implicit via SwiftUI) | All UI updates on main thread |
| `AppState` | `@MainActor` (explicit) | Published properties safe for UI binding |
| `AppDelegate` | `@MainActor` (explicit) | AppKit lifecycle on main thread |
| Settings callbacks | `Task { @MainActor }` | Async actions wrapped for main thread |

### Thread Safety
- **UI Binding**: All `@Published` properties from `AppState` are `@MainActor` isolated
- **No Data Races**: `@StateObject` ensures single ownership
- **Async Actions**: Button actions use `Task { await ... }` for async calls

---

## Related Documentation

### Related Files
| File Path | Relationship | Why Related |
|---|---|---|
| `ui/AIAgentUI/App/AppDelegate.swift` | Used | AppKit lifecycle, hotkeys, panel management |
| `ui/AIAgentUI/State/AppState.swift` | Used | Global application state |
| `ui/AIAgentUI/Window/FloatingPanelController.swift` | Used | Floating panel management |
| `ui/AIAgentUI/Window/EdgeSnapping.swift` | Used | Window positioning logic |
| `ui/AIAgentUI/Views/MainPanelView.swift` | Related | Main panel UI content |

---

## Technical Decisions

### Decision: MenuBarExtra vs Dock Icon
**Rationale:**
- Menu bar provides quick access without cluttering Dock
- Consistent with native macOS utilities (Spotlight, Notification Center)
- User can optionally enable Dock icon via Settings

### Decision: Settings Window vs In-Panel Settings
**Rationale:**
- Separate Settings window follows macOS conventions
- Keeps main panel UI clean and focused on chat
- Standard Cmd+, shortcut for settings access
- TabView provides organized multi-section configuration

### Decision: @NSApplicationDelegateAdaptor
**Rationale:**
- SwiftUI lacks APIs for global hotkeys (requires Carbon)
- NSPanel management needs AppKit
- App lifecycle hooks not available in pure SwiftUI
- Hybrid approach keeps UI declarative while enabling platform features

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2025-12 | AI Agent | Initial implementation | Created SwiftUI app entry point with Settings and MenuBar scenes | High - New app structure |
| 2026-01-18 | AI Agent (Claude) | Documentation | Created comprehensive documentation with proper format | None - Docs only |
| 2026-01-18 | AI Agent (Claude) | Model selection feature | Added GeminiModel enum with 4 model options; added model selection Picker to ConnectionSettingsView with @AppStorage persistence | Medium |
| 2026-01-18 | AI Agent (Codex) | Model switching fix | Bound ConnectionSettingsView picker to AppState.selectedModel to keep UI and prompt selection in sync | High |
