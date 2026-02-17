# UI Components Documentation

This document provides comprehensive documentation for all SwiftUI components in the `ui/AIAgentUI/Views/Components/` directory.

---

## Component Overview

| Component | File | Purpose | Lines |
|---|---|---|---|
| `InputField` | `InputField.swift` | User text input | ~210 |
| `ResponseBubble` | `ResponseBubble.swift` | Message display | 333 |
| `StatusIndicator` | `StatusIndicator.swift` | Status animations | 346 |
| `ToggleArrow` | `ToggleArrow.swift` | Collapsible indicator | 238 |
| `ToolCallCard` | `ToolCallCard.swift` | Tool execution display | 296 |
| `StartupModal` | `StartupModal.swift` | Backend startup progress | ~85 |

---

# InputField.swift

## File Metadata
| Field | Value |
|---|---|
| Lines of Code | ~210 |
| Last Edited | 2026-01-18 |
| Last Major Edit | 2026-01-18 |
| Modified By | AI Agent (Claude) |
| WHY | Fixed vertical black line bug and invisible text issue |

## Purpose
Multi-line text input field with placeholder, submit functionality, and glass styling.

## Session 3 Bug Fixes (2026-01-18)

### Bug UI-001: Vertical Black Line
**Problem:** SwiftUI `TextEditor` on macOS wraps an `NSScrollView` that always shows a border, appearing as a vertical black line on the left edge.

**Root Cause:** `NSScrollView.borderType` defaults to a visible border on macOS, and SwiftUI provides no way to remove it.

**Solution:** Replaced `TextEditor` with custom `BorderlessTextView` using `NSViewRepresentable`:
```swift
scrollView.borderType = .noBorder  // Key fix
scrollView.drawsBackground = false
```

### Bug UI-002: Invisible Text
**Problem:** Text typed in the input field was invisible (white on white background).

**Root Cause:** `NSColor.labelColor` adapts to system theme; when system is in dark mode but the app uses a light background, label color could be white.

**Solution:** Set explicit black text color:
```swift
textView.textColor = NSColor.black  // Explicit, not .labelColor
```

## Types

### `InputField`
Main input component with submit callback.

#### Properties
| Name | Type | Purpose |
|---|---|---|
| `text` | `Binding<String>` | Two-way text binding |
| `placeholder` | String | Placeholder text |
| `isDisabled` | Bool | Disabled state |
| `onSubmit` | `() -> Void` | Submit callback |

#### Body Structure
```swift
var body: some View {
    HStack(spacing: ThemeConstants.spacingSmall) {
        // BorderlessTextView (NSViewRepresentable)
        BorderlessTextView(text: $text, placeholder: placeholder)
            .frame(minHeight: 36, maxHeight: 100)
        
        // Submit button
        Button(action: onSubmit) {
            Image(systemName: "arrow.up.circle.fill")
                .font(.system(size: ThemeConstants.iconSizeLarge))
                .foregroundColor(canSubmit ? .primaryBlue : .textTertiary)
        }
        .buttonStyle(.plain)
        .disabled(!canSubmit)
    }
    .padding(ThemeConstants.paddingSmall)
    .glassInput(isFocused: isFocused)
}
```

### `BorderlessTextView` (NSViewRepresentable)
Custom AppKit text view bridged to SwiftUI for borderless input.

#### Key Implementation
```swift
struct BorderlessTextView: NSViewRepresentable {
    @Binding var text: String
    var placeholder: String
    
    func makeNSView(context: Context) -> NSScrollView {
        let scrollView = NSScrollView()
        scrollView.borderType = .noBorder  // FIX: Removes black line
        scrollView.drawsBackground = false
        scrollView.hasVerticalScroller = false
        
        let textView = NSTextView()
        textView.backgroundColor = .clear
        textView.textColor = NSColor.black  // FIX: Explicit color
        textView.font = NSFont.systemFont(ofSize: 14)
        textView.drawsBackground = false
        textView.isEditable = true
        textView.isRichText = false
        
        scrollView.documentView = textView
        return scrollView
    }
}
```

### `SimpleInputField`
Single-line variant for compact mode.

## Technical Notes

### Why NSViewRepresentable?
SwiftUI's `TextEditor` on macOS:
1. Cannot have its border removed (no `.border(.clear)` equivalent for underlying NSScrollView)
2. Has limited styling control over the wrapped NSTextView
3. Text color follows system theme inappropriately

### Dark Mode Consideration
Current implementation uses `NSColor.black` explicitly. For full dark mode support, consider:
```swift
textView.textColor = NSColor.textColor  // Adapts to dark mode
```
However, this requires ensuring the background also adapts correctly.

---

# ResponseBubble.swift

## File Metadata
| Field | Value |
|---|---|
| Lines of Code | 333 |
| Last Edited | 2026-01-18 |

## Purpose
Message bubble display with role icon, content, timestamp, and optional tool call.

## Types

### `ResponseBubble`
Individual message display.

#### Properties
| Name | Type | Purpose |
|---|---|---|
| `message` | Message | Message to display |

#### Layout
```
+------------------------------------------+
|  [👤/🤖] Role Name              12:30 PM |
|                                          |
|  Message content with optional           |
|  typewriter animation for streaming...   |
|                                          |
|  [📦 tool_name              ▾ Success ]  |  <- Optional ToolCallCard
+------------------------------------------+
```

#### Role Styling
| Role | Icon | Background | Alignment |
|---|---|---|---|
| User | `person.circle` | `userMessageBg` | Right |
| Assistant | `brain` | `assistantMessageBg` | Left |
| System | `gear` | `systemMessageBg` | Center |

### `TypewriterText`
Animated text display for streaming responses.

#### Properties
| Name | Type | Purpose |
|---|---|---|
| `text` | String | Text to animate |
| `isAnimating` | Bool | Enable animation |
| `charDelay` | TimeInterval | Delay per character |

#### Animation
```swift
.onAppear {
    if isAnimating {
        for (index, char) in text.enumerated() {
            DispatchQueue.main.asyncAfter(deadline: .now() + charDelay * Double(index)) {
                displayedText.append(char)
            }
        }
    } else {
        displayedText = text
    }
}
```

### `MessageListView`
Scrollable list of messages with auto-scroll.

### `EmptyMessageView`
Empty state when no messages.

---

# StatusIndicator.swift

## File Metadata
| Field | Value |
|---|---|
| Lines of Code | 346 |
| Last Edited | 2026-01-18 |

## Purpose
Animated status indicators for different agent states.

## Types

### `StatusIndicator`
Main status display that switches based on status.

#### Properties
| Name | Type | Purpose |
|---|---|---|
| `status` | AgentStatus | Current status |

#### Status → Indicator Mapping
| Status | Indicator | Animation |
|---|---|---|
| `idle` | None | N/A |
| `connecting` | `ConnectingIndicator` | Spinning |
| `thinking` | `ThinkingIndicator` | Pulsing |
| `callingTool` | `ToolCallIndicator` | Rotating |
| `streaming` | `StreamingIndicator` | Typing dots |
| `error` | `ErrorIndicator` | Static |
| `complete` | `CompleteIndicator` | Checkmark |

### `ThinkingIndicator`
Pulsing brain animation.

```swift
var body: some View {
    HStack(spacing: ThemeConstants.spacingSmall) {
        Image(systemName: "brain")
            .foregroundColor(.statusThinking)
            .scaleEffect(isPulsing ? 1.2 : 1.0)
            .animation(.easeInOut(duration: 0.6).repeatForever(autoreverses: true), value: isPulsing)
        
        Text("Thinking...")
            .foregroundColor(.textSecondary)
    }
    .onAppear { isPulsing = true }
}
```

### `ConnectingIndicator`
Spinning network icon.

### `ToolCallIndicator`
Rotating wrench with tool name.

### `StreamingIndicator`
Three bouncing dots.

```swift
var body: some View {
    HStack(spacing: 4) {
        ForEach(0..<3) { index in
            Circle()
                .fill(Color.statusStreaming)
                .frame(width: 6, height: 6)
                .offset(y: animating ? -4 : 0)
                .animation(
                    .easeInOut(duration: 0.4)
                    .repeatForever(autoreverses: true)
                    .delay(0.1 * Double(index)),
                    value: animating
                )
        }
    }
}
```

### `ErrorIndicator`
Red exclamation with error message.

### `CompleteIndicator`
Green checkmark.

### `InlineStatusView`
Compact status for header display.

---

# ToggleArrow.swift

## File Metadata
| Field | Value |
|---|---|
| Lines of Code | 238 |
| Last Edited | 2026-01-18 |

## Purpose
Animated chevron arrow for collapsible sections.

## Types

### `ToggleArrow`
Rotating chevron indicator.

#### Properties
| Name | Type | Purpose |
|---|---|---|
| `isExpanded` | Bool | Expansion state |
| `size` | CGFloat | Icon size |
| `color` | Color | Icon color |

#### Animation
```swift
var body: some View {
    Image(systemName: "chevron.right")
        .font(.system(size: size, weight: .semibold))
        .foregroundColor(color)
        .rotationEffect(.degrees(isExpanded ? 90 : 0))
        .animation(.easeOut(duration: ThemeConstants.animationFast), value: isExpanded)
}
```

### `CollapsibleSection<Header, Content>`
Generic collapsible container.

#### Properties
| Name | Type | Purpose |
|---|---|---|
| `isExpanded` | `Binding<Bool>` | Expansion binding |
| `header` | `() -> Header` | Header view builder |
| `content` | `() -> Content` | Content view builder |

#### Usage
```swift
CollapsibleSection(isExpanded: $isExpanded) {
    HStack {
        Text("Section Title")
        Spacer()
        ToggleArrow(isExpanded: isExpanded)
    }
} content: {
    Text("Section content here")
}
```

### `ToolCallHeader`
Specialized header for tool calls with status badge.

---

# ToolCallCard.swift

## File Metadata
| Field | Value |
|---|---|
| Lines of Code | 296 |
| Last Edited | 2026-01-18 |

## Purpose
Display tool call details with collapsible arguments.

## Types

### `ToolCallCard`
Main tool call display.

#### Properties
| Name | Type | Purpose |
|---|---|---|
| `toolCall` | ToolCall | Tool call data |
| `isExpanded` | Bool | Show arguments |

#### Layout
```
+------------------------------------------+
|  [🔧] search_files     ▾    ✓ Success    |
+------------------------------------------+
|  Arguments:                              |  <- Shown when expanded
|    query: "*.swift"                      |
|    path: "/Documents"                    |
|    recursive: true                       |
|                                          |
|  Result:                                 |
|    Found 25 files                        |
+------------------------------------------+
```

#### Status Badge Colors
| Status | Color | Icon |
|---|---|---|
| `pending` | `statusIdle` | `clock` |
| `executing` | `statusToolCall` | `gearshape` |
| `success` | `statusComplete` | `checkmark.circle.fill` |
| `failed` | `statusError` | `xmark.circle.fill` |

### `ArgumentRow`
Single argument key-value display.

```swift
struct ArgumentRow: View {
    let key: String
    let value: ArgumentValue
    
    var body: some View {
        HStack(alignment: .top) {
            Text(key + ":")
                .foregroundColor(.textSecondary)
            
            Text(value.description)
                .foregroundColor(.textPrimary)
        }
        .font(.caption)
    }
}
```

### `ActiveToolCallView`
Animated view for currently executing tool.

### `ToolCallHistory`
List of completed tool calls.

---

# StartupModal.swift

## File Metadata
| Field | Value |
|---|---|
| Lines of Code | ~85 |
| Last Edited | 2026-01-18 |
| Last Major Edit | 2026-01-18 |
| Modified By | AI Agent (Claude) |
| WHY | Added .performingHealthCheck phase for startup health checks |

## Purpose
Modal overlay showing backend startup progress with animated phases.

## Session 3 Changes (2026-01-18)

### Feature: Health Check Phase
Added new `.performingHealthCheck` phase to the startup sequence.

```swift
enum StartupPhase: CaseIterable, Identifiable {
    case launchingBackend
    case waitingForSocket
    case connectingToBackend
    case performingHealthCheck  // NEW: Added in Session 3
    case ready
}
```

## Types

### `StartupPhase`
Enum representing backend startup states.

#### Cases
| Case | Title | Subtitle | Symbol |
|---|---|---|---|
| `launchingBackend` | "Starting Backend" | "Launching Python process..." | `terminal` |
| `waitingForSocket` | "Waiting" | "Socket initialization..." | `network` |
| `connectingToBackend` | "Connecting" | "Establishing IPC connection..." | `link` |
| `performingHealthCheck` | "Verifying" | "Running health checks..." | `stethoscope` |
| `ready` | "Ready" | "Backend connected successfully" | `checkmark.circle` |

#### Computed Properties
| Property | Type | Purpose |
|---|---|---|
| `title` | String | Phase title for display |
| `subtitle` | String | Descriptive subtitle |
| `symbolName` | String | SF Symbol icon name |

### `StartupModal`
Modal view displaying current startup phase.

#### Properties
| Name | Type | Purpose |
|---|---|---|
| `phase` | StartupPhase | Current startup phase |
| `isVisible` | Bool | Show/hide modal |

#### Body Structure
```swift
var body: some View {
    if isVisible {
        ZStack {
            // Blur background
            Color.black.opacity(0.3)
                .ignoresSafeArea()
            
            // Modal content
            VStack(spacing: 16) {
                // Animated symbol
                Image(systemName: phase.symbolName)
                    .font(.system(size: 40))
                    .foregroundColor(.primaryBlue)
                    .rotationEffect(.degrees(isAnimating ? 360 : 0))
                
                Text(phase.title)
                    .font(.headline)
                
                Text(phase.subtitle)
                    .font(.subheadline)
                    .foregroundColor(.textSecondary)
                
                ProgressView()
            }
            .padding(32)
            .glassCard()
        }
    }
}
```

## Related Components
| Component | Relationship |
|---|---|
| `AppState` | Provides `startupPhase` binding |
| `MainPanelView` | Hosts StartupModal as overlay |

---

## Common Patterns

### Focus State
```swift
@FocusState private var isFocused: Bool

TextField("...", text: $text)
    .focused($isFocused)
    .glassInput(isFocused: isFocused)
```

### Animation on Appear
```swift
@State private var isAnimating = false

.onAppear {
    isAnimating = true
}
```

### Binding for Expansion
```swift
@State private var isExpanded = false

CollapsibleSection(isExpanded: $isExpanded) { ... }
```

---

## Styling Guidelines

### All Components Use
- `Color.*` from `BlueTheme.swift`
- `ThemeConstants.*` for spacing/sizing
- `.glassCard()` or `.glassInput()` modifiers

### Animation Durations
| Type | Duration |
|---|---|
| Fast (toggles) | `ThemeConstants.animationFast` (0.15s) |
| Normal (expand) | `ThemeConstants.animationNormal` (0.25s) |
| Pulse/repeat | Custom with `.repeatForever()` |

---

## Preview Providers

All components include preview providers using `PreviewData`:

```swift
struct InputField_Previews: PreviewProvider {
    static var previews: some View {
        Group {
            InputField(text: .constant(""), onSubmit: {})
                .previewDisplayName("Empty")
            
            InputField(text: .constant("Hello"), onSubmit: {})
                .previewDisplayName("With Text")
            
            InputField(text: .constant(""), isDisabled: true, onSubmit: {})
                .previewDisplayName("Disabled")
        }
        .padding()
    }
}
```

---

## Related Documentation

| File Path | Relationship |
|---|---|
| `ui/AIAgentUI/Views/Styles/BlueTheme.swift` | Colors, constants |
| `ui/AIAgentUI/Views/Styles/LiquidGlassStyle.swift` | Glass effects |
| `ui/AIAgentUI/State/Message.swift` | Message, ToolCall types |
| `ui/AIAgentUI/State/AgentStatus.swift` | Status enum |

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-01-18 | AI Assistant | Initial implementation | Created all components | New files |
| 2026-01-18 | AI Agent (Claude) | Bug fixes UI-001, UI-002 | InputField: Replaced TextEditor with NSViewRepresentable BorderlessTextView; fixed vertical black line and invisible text | High |
| 2026-01-18 | AI Agent (Claude) | Health check feature | StartupModal: Added .performingHealthCheck phase | Low |
