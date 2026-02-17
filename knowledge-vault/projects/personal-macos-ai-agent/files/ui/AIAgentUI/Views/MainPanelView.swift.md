# File Doc: `ui/AIAgentUI/Views/MainPanelView.swift`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `ui/AIAgentUI/Views/MainPanelView.swift` |
| Doc Path | `projects/personal-macos-ai-agent/files/ui/AIAgentUI/Views/MainPanelView.swift.md` |
| Language | Swift |
| File Role | Main Panel SwiftUI View |
| Ownership | Core Team |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-01-18 |
| Last Major Edit (YYYY-MM-DD) | 2026-01-18 |
| Modified By | AI Agent (Codex) |
| WHY (Reason for last change) | Added drawingGroup for panel rendering performance |
| Lines of Code (LOC) | 371 |
| Cyclomatic Complexity | Medium |
| Test Coverage | 0% |

---

## Purpose & Responsibilities

### What this file does
**Single-sentence summary:**
Root SwiftUI view for the AI Agent floating panel containing header, message list, status indicator, and input field.

**Detailed responsibilities:**
- Provides main container view `MainPanelView` with full panel layout
- Includes header with title, connection indicator, and menu button
- Displays message list with `MessageListView`
- Shows status indicator for active operations
- Contains input field with submit functionality
- Displays error banner when `lastError` is set
- Provides `CompactPanelView` for minimal mode
- Applies Liquid Glass styling throughout
- Flattens panel rendering via `drawingGroup` for smoother effects
- Provides a header model menu that updates `AppState.selectedModel`

### What this file must NOT do (boundaries)
**Out of scope:**
- Window management (handled by `FloatingPanelController`)
- State management logic (handled by `AppState`)
- IPC communication (handled by `IPCClient`)
- Individual component styling (handled by respective component files)

### Who/what calls it
| Caller | Purpose | Frequency | Error Handling |
|---|---|---|---|
| `FloatingPanelController` | Panel content | Once per setup | N/A |

### What it calls
| Callee | Purpose | Error Handling | Fallback Strategy |
|---|---|---|---|
| `StatusIndicator` | Show status | N/A | N/A |
| `InputField` | User input | N/A | N/A |
| `ResponseBubble` | Messages | N/A | N/A |
| `ToolCallCard` | Tool calls | N/A | N/A |
| `AppState` | Read state | N/A | N/A |

---

## Imports / Dependencies

### Framework Dependencies
| Framework | What's Used | Why Needed |
|---|---|---|
| SwiftUI | View, VStack, etc. | UI framework |

### Internal Dependencies
| Import Path | What's Used | Why Needed | Coupling Level |
|---|---|---|---|
| Same module | All components | UI composition | High |

---

## Public Surface (Document EVERYTHING Exposed)

### Exports / Public Symbols
| Symbol | Type (func/class/const/type) | Visibility | Status | Brief Description |
|---|---|---|---|---|
| `MainPanelView` | struct | public | Stable | Main panel view |
| `CompactPanelView` | struct | public | Stable | Minimal panel variant |

---

## Types (Classes / Structs / Enums / Interfaces)

### `MainPanelView`
| Metadata | Value |
|---|---|
| Kind | struct |
| Purpose | Root view for the AI Agent panel |
| Thread-Safe | Yes (SwiftUI) |
| Immutable | Yes |
| Serializable | No |
| Related Types | `AppState` |

#### Inheritance & Implementation
- **Extends:** N/A
- **Implements:** `View`
- **Used By:** `FloatingPanelController`

#### Fields / Properties
| Name | Type | Visibility | Default | Required | Mutable | Purpose |
|---|---|---|---|---|---|---|
| `appState` | AppState | public | Required | Yes | No | State binding |

#### Body Structure
```swift
var body: some View {
    VStack(spacing: 0) {
        // Header
        PanelHeader()
        
        // Error Banner (if error)
        if let error = appState.lastError {
            ErrorBanner(message: error)
        }
        
        // Message List
        MessageListView(messages: appState.messages)
        
        // Status Indicator (if active)
        if appState.status.showsIndicator {
            StatusIndicator(status: appState.status)
        }
        
        // Input Field
        InputField(
            text: $appState.currentInput,
            isDisabled: !appState.status.canSubmit,
            onSubmit: {
                Task { await appState.sendPrompt() }
            }
        )
    }
    .frame(
        width: ThemeConstants.panelWidth,
        height: ThemeConstants.panelHeight
    )
    .liquidGlass()
}
```

---

### View Components

#### Session 3 Changes

##### Bug UI-003: Settings Button Not Working
**Problem:** Clicking "Settings" in the menu did nothing.

**Root Cause:** In menu bar agent apps, `NSApp.sendAction(Selector(("showPreferencesWindow:")), ...)` fails silently because the app doesn't have keyboard focus.

**Solution:** Add `NSApp.activate(ignoringOtherApps: true)` before attempting to show Settings, plus fallback chain:
```swift
private func openSettings() {
    NSApp.activate(ignoringOtherApps: true)  // Required for agent apps
    
    // Try macOS 13+ selector first
    if !NSApp.sendAction(Selector(("showPreferencesWindow:")), to: nil, from: nil) {
        // Fallback to older selector
        if !NSApp.sendAction(Selector(("showSettingsWindow:")), to: nil, from: nil) {
            // Fallback to AppDelegate method
            if let appDelegate = NSApp.delegate as? AppDelegate {
                appDelegate.showPreferences()
            }
        }
    }
}
```

##### Feature: Model Selection Submenu
Added `@AppStorage("selectedModel")` for persistence and model submenu:
```swift
@AppStorage("selectedModel") private var selectedModel = GeminiModel.flash.rawValue

// In menu:
Menu("Model") {
    ForEach(GeminiModel.allCases) { model in
        Button {
            selectedModel = model.rawValue
        } label: {
            HStack {
                Text(model.displayName)
                if selectedModel == model.rawValue {
                    Image(systemName: "checkmark")
                }
            }
        }
    }
}
```

---

#### `PanelHeader`
```swift
private var PanelHeader: some View {
    HStack {
        // Connection indicator
        Circle()
            .fill(appState.isConnected ? Color.statusComplete : Color.statusError)
            .frame(width: 8, height: 8)
        
        Text("AI Agent")
            .font(.headline)
            .foregroundColor(.textPrimary)
        
        Spacer()
        
        // Menu button
        Menu {
            Button("Clear Messages") {
                appState.clearMessages()
            }
            Button("Reconnect") {
                Task { await appState.connect() }
            }
            
            Divider()
            
            // Model selection submenu (Session 3)
            Menu("Model") {
                ForEach(GeminiModel.allCases) { model in
                    Button {
                        selectedModel = model.rawValue
                    } label: {
                        HStack {
                            Text(model.displayName)
                            if selectedModel == model.rawValue {
                                Image(systemName: "checkmark")
                            }
                        }
                    }
                }
            }
            
            Divider()
            
            Button("Settings...") {
                openSettings()  // Uses fixed implementation
            }
            
            Divider()
            
            Button("Hide Panel") {
                FloatingPanelController.shared.hide()
            }
        } label: {
            Image(systemName: "ellipsis.circle")
                .foregroundColor(.textSecondary)
        }
        .menuStyle(.borderlessButton)
    }
    .padding(.horizontal, ThemeConstants.padding)
    .padding(.vertical, ThemeConstants.paddingSmall)
    .background(Color.glassBg.opacity(0.5))
}
```

#### `ErrorBanner`
```swift
private struct ErrorBanner: View {
    let message: String
    
    var body: some View {
        HStack {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundColor(.statusError)
            
            Text(message)
                .font(.caption)
                .foregroundColor(.textPrimary)
                .lineLimit(2)
            
            Spacer()
            
            Button {
                AppState.shared.clearError()
            } label: {
                Image(systemName: "xmark.circle.fill")
                    .foregroundColor(.textSecondary)
            }
            .buttonStyle(.plain)
        }
        .padding(ThemeConstants.paddingSmall)
        .background(Color.statusError.opacity(0.1))
    }
}
```

#### `ContentArea`
```swift
private var ContentArea: some View {
    VStack(spacing: ThemeConstants.spacing) {
        // Messages
        if appState.messages.isEmpty {
            EmptyStateView()
        } else {
            MessageListView(messages: appState.messages)
        }
        
        // Current tool call
        if let toolCall = appState.currentToolCall {
            ActiveToolCallView(toolCall: toolCall)
        }
    }
}
```

---

### `CompactPanelView`
| Metadata | Value |
|---|---|
| Kind | struct |
| Purpose | Minimal panel variant for limited space |
| Thread-Safe | Yes |
| Immutable | Yes |

#### Body Structure
```swift
var body: some View {
    VStack(spacing: ThemeConstants.paddingSmall) {
        // Inline status
        InlineStatusView(status: appState.status)
        
        // Simple input
        SimpleInputField(
            text: $appState.currentInput,
            onSubmit: {
                Task { await appState.sendPrompt() }
            }
        )
    }
    .padding(ThemeConstants.paddingSmall)
    .frame(width: 300, height: 80)
    .liquidGlass(cornerRadius: ThemeConstants.cornerRadiusSmall)
}
```

---

## Layout Structure

### Full Panel Layout
```
+----------------------------------+
|  [●] AI Agent           [⋯ Menu] |  <- Header (40pt)
+----------------------------------+
|  ⚠️ Error message         [×]    |  <- Error Banner (optional)
+----------------------------------+
|                                  |
|  User: Search for files          |  <- MessageListView (flex)
|                                  |
|  Assistant: I'll search...       |
|    [📦 search_files ▾]           |  <- ToolCallCard
|                                  |
+----------------------------------+
|  🔄 Searching files...           |  <- StatusIndicator (40pt)
+----------------------------------+
|  [Enter your message...]   [→]   |  <- InputField (50pt)
+----------------------------------+
```

### Compact Panel Layout
```
+------------------------+
|  🟢 Ready              |  <- InlineStatusView
|  [Enter message...] [→]|  <- SimpleInputField
+------------------------+
```

---

## Styling

### Theme Application
```swift
// Full panel
.frame(
    width: ThemeConstants.panelWidth,    // 400
    height: ThemeConstants.panelHeight   // 600
)
.liquidGlass()  // Glass effect

// Compact panel
.frame(width: 300, height: 80)
.liquidGlass(cornerRadius: ThemeConstants.cornerRadiusSmall)
```

### Colors Used
| Element | Color |
|---|---|
| Connection dot (connected) | `Color.statusComplete` |
| Connection dot (disconnected) | `Color.statusError` |
| Title text | `Color.textPrimary` |
| Menu icon | `Color.textSecondary` |
| Error banner background | `Color.statusError.opacity(0.1)` |

---

## State Bindings

### Read Properties
| Property | Usage |
|---|---|
| `appState.messages` | Display in list |
| `appState.status` | Show indicator, disable input |
| `appState.isConnected` | Connection indicator |
| `appState.lastError` | Error banner |
| `appState.currentToolCall` | Active tool display |

### Write Bindings
| Binding | Usage |
|---|---|
| `$appState.currentInput` | Input field text |

### Actions
| Action | Trigger |
|---|---|
| `appState.sendPrompt()` | Input submit |
| `appState.clearMessages()` | Menu action |
| `appState.connect()` | Menu action |
| `appState.clearError()` | Error dismiss |

---

## Preview Provider

```swift
struct MainPanelView_Previews: PreviewProvider {
    static var previews: some View {
        Group {
            MainPanelView(appState: PreviewData.appState)
                .previewDisplayName("Default")
            
            MainPanelView(appState: PreviewData.appStateWithMessages)
                .previewDisplayName("With Messages")
            
            MainPanelView(appState: PreviewData.appStateWithError)
                .previewDisplayName("With Error")
            
            CompactPanelView(appState: PreviewData.appState)
                .previewDisplayName("Compact")
        }
    }
}
```

---

## Related Documentation

### Related Files
| File Path | Relationship | Why Related |
|---|---|---|
| `ui/AIAgentUI/Views/Components/InputField.swift` | Uses | Input component |
| `ui/AIAgentUI/Views/Components/StatusIndicator.swift` | Uses | Status display |
| `ui/AIAgentUI/Views/Components/ResponseBubble.swift` | Uses | Messages |
| `ui/AIAgentUI/Views/Components/ToolCallCard.swift` | Uses | Tool calls |
| `ui/AIAgentUI/Views/Styles/LiquidGlassStyle.swift` | Uses | Styling |
| `ui/AIAgentUI/Views/Styles/BlueTheme.swift` | Uses | Colors, constants |
| `ui/AIAgentUI/State/AppState.swift` | Uses | State management |
| `ui/AIAgentUI/Window/FloatingPanelController.swift` | Used by | Panel host |

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-01-18 | AI Assistant | Initial implementation | Created main panel view | New file |
| 2026-01-18 | AI Agent (Codex) | UI smoothness | Added drawingGroup to flatten panel rendering | Low |
| 2026-01-18 | AI Agent (Claude) | Bug fix UI-003 | Fixed Settings button with NSApp.activate + fallback chain | High |
| 2026-01-18 | AI Agent (Claude) | Model selection feature | Added @AppStorage for model persistence, model submenu in header menu | Medium |
| 2026-01-18 | AI Agent (Codex) | Model switching fix | Updated header model menu to use AppState.selectedModel | Medium |
