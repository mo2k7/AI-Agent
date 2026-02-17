# File Doc: `ui/AIAgentUI/Views/Styles/BlueTheme.swift`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `ui/AIAgentUI/Views/Styles/BlueTheme.swift` |
| Doc Path | `projects/personal-macos-ai-agent/files/ui/AIAgentUI/Views/Styles/BlueTheme.swift.md` |
| Language | Swift |
| File Role | Color Theme and Constants |
| Ownership | Core Team |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-01-18 |
| Last Major Edit (YYYY-MM-DD) | 2026-01-18 |
| Modified By | AI Agent (Codex) |
| WHY (Reason for last change) | Removed main-actor appearance checks in favor of dynamic NSColor values |
| Lines of Code (LOC) | 282 |
| Cyclomatic Complexity | None |
| Test Coverage | N/A |

---

## Purpose & Responsibilities

### What this file does
**Single-sentence summary:**
Defines the blue-themed color palette, semantic colors, and design constants for the AI Agent UI.

**Detailed responsibilities:**
- Provides primary blue color (#007AFF) and variations
- Defines glass/blur effect colors for Liquid Glass style
- Provides semantic text colors (primary, secondary, tertiary)
- Defines status indicator colors (idle, thinking, streaming, error, complete)
- Provides `ThemeConstants` with spacing, radii, and panel dimensions
- Provides `AnimationConstants` for consistent UI motion
- Extends SwiftUI `Color` with convenient static properties
- Supports dark mode with adaptive colors

### What this file must NOT do (boundaries)
**Out of scope:**
- View implementation
- Style modifiers (see `LiquidGlassStyle.swift`)

### Who/what calls it
| Caller | Purpose | Frequency | Error Handling |
|---|---|---|---|
| All UI components | Color and constant access | Throughout app | N/A |

---

## Imports / Dependencies

### Framework Dependencies
| Framework | What's Used | Why Needed |
|---|---|---|
| SwiftUI | Color | Color definitions |
| AppKit | NSColor | Adaptive system colors |

---

## Public Surface (Document EVERYTHING Exposed)

### Exports / Public Symbols
| Symbol | Type (func/class/const/type) | Visibility | Status | Brief Description |
|---|---|---|---|---|
| `Color` extension | extension | public | Stable | Color properties |
| `ThemeConstants` | struct | public | Stable | Design constants |
| `AnimationConstants` | enum | public | Stable | Shared motion presets |

---

## Color Definitions

### Primary Blue Palette
| Color | Hex Value | Usage |
|---|---|---|
| `primaryBlue` | `#007AFF` | Primary accent, buttons |
| `secondaryBlue` | `#5AC8FA` | Lighter accent |
| `darkBlue` | `#0A84FF` | Active/pressed states |
| `lightBlue` | `#E1F0FF` | Subtle backgrounds |

### Code Definition
```swift
extension Color {
    // Primary Blues
    static let primaryBlue = Color(hex: "007AFF")
    static let secondaryBlue = Color(hex: "5AC8FA")
    static let darkBlue = Color(hex: "0A84FF")
    static let lightBlue = Color(hex: "E1F0FF")
}
```

### Glass Effect Colors
| Color | Usage | Opacity |
|---|---|---|
| `glassBg` | Panel background | `windowBackgroundColor` with opacity |
| `glassStroke` | Border strokes | `separatorColor` with opacity |
| `glassHighlight` | Top edge highlight | White with subtle opacity |
| `glassShadow` | Drop shadow | Black with subtle opacity |

```swift
extension Color {
    // Glass Effect
    static var glassBg: Color {
        Color(NSColor.windowBackgroundColor).opacity(0.75)
    }
    static var glassStroke: Color {
        Color(NSColor.separatorColor).opacity(0.35)
    }
    static var glassHighlight: Color {
        Color.white.opacity(0.2)
    }
    static var glassShadow: Color {
        Color.black.opacity(0.2)
    }
}
```

### Text Colors
| Color | Usage | Light Mode | Dark Mode |
|---|---|---|---|
| `textPrimary` | Main text | `labelColor` | `labelColor` |
| `textSecondary` | Secondary text | `secondaryLabelColor` | `secondaryLabelColor` |
| `textTertiary` | Muted text | `tertiaryLabelColor` | `tertiaryLabelColor` |
| `textInverted` | Text on dark surfaces | `textBackgroundColor` | `textBackgroundColor` |

```swift
extension Color {
    // Text
    static var textPrimary: Color { Color(NSColor.labelColor) }
    static var textSecondary: Color { Color(NSColor.secondaryLabelColor) }
    static var textTertiary: Color { Color(NSColor.tertiaryLabelColor) }
    static var textInverted: Color { Color(NSColor.textBackgroundColor) }
}
```

### Status Colors
| Color | Status | Hex Value | Usage |
|---|---|---|---|
| `statusIdle` | Idle | `#34C759` | Ready indicator |
| `statusThinking` | Thinking | `#007AFF` | Processing indicator |
| `statusToolCall` | Calling Tool | `#FF9500` | Tool execution |
| `statusStreaming` | Streaming | `#5856D6` | Response streaming |
| `statusError` | Error | `#FF3B30` | Error states |
| `statusComplete` | Complete | `#34C759` | Success |

```swift
extension Color {
    // Status
    static let statusIdle = Color(red: 52/255, green: 199/255, blue: 89/255)  // #34C759 (green)
    static let statusThinking = Color.primaryBlue  // #007AFF
    static let statusToolCall = Color(red: 255/255, green: 149/255, blue: 0/255)  // #FF9500 (orange)
    static let statusStreaming = Color(red: 88/255, green: 86/255, blue: 214/255)  // #5856D6 (purple)
    static let statusError = Color(red: 255/255, green: 59/255, blue: 48/255)  // #FF3B30 (red)
    static let statusComplete = Color(red: 52/255, green: 199/255, blue: 89/255)  // #34C759 (green)
}
```

### Message Role Colors
| Color | Role | Usage |
|---|---|---|
| `userMessageBg` | User | User message bubble |
| `assistantMessageBg` | Assistant | Assistant message bubble |
| `systemMessageBg` | System | System message bubble |

```swift
extension Color {
    // Message Bubbles
    static let userMessageBg = Color.primaryBlue.opacity(0.15)
    static let assistantMessageBg = Color.gray.opacity(0.1)
    static let systemMessageBg = Color.orange.opacity(0.1)
}
```

---

## Theme Constants

### `ThemeConstants`
| Metadata | Value |
|---|---|
| Kind | enum |
| Purpose | Centralized design constants |
| Thread-Safe | Yes (all static) |
| Immutable | Yes |

#### Corner Radii
| Constant | Value | Usage |
|---|---|---|
| `cornerRadiusLarge` | 20 | Panel corners |
| `cornerRadiusMedium` | 12 | Cards, buttons |
| `cornerRadiusSmall` | 8 | Inputs, tags |

#### Spacing Constants
| Constant | Value | Usage |
|---|---|---|
| `spacingXL` | 24 | Section separation |
| `spacingL` | 16 | Standard padding |
| `spacingM` | 12 | Inter-element gap |
| `spacingS` | 8 | Compact spacing |
| `spacingXS` | 4 | Tight spacing |

#### Panel Dimensions
| Constant | Value | Usage |
|---|---|---|
| `panelWidth` | 400 | Default width |
| `panelHeight` | 600 | Default height |
| `panelMinWidth` | 300 | Minimum width |
| `panelMinHeight` | 400 | Minimum height |
| `panelMaxWidth` | 600 | Maximum width |
| `panelMaxHeight` | 800 | Maximum height |

#### Animation Durations
| Constant | Value | Usage |
|---|---|---|
| `animationDuration` | 0.3 | Standard timing |
| `animationDurationFast` | 0.15 | Quick timing |
| `animationDurationSlow` | 0.5 | Gentle timing |

#### Shadows
| Constant | Value | Usage |
|---|---|---|
| `shadowRadius` | 10 | Drop shadow radius |
| `shadowY` | 5 | Drop shadow offset |

### Code Definition
```swift
enum ThemeConstants {
    static let cornerRadiusLarge: CGFloat = 20
    static let cornerRadiusMedium: CGFloat = 12
    static let cornerRadiusSmall: CGFloat = 8

    static let spacingXL: CGFloat = 24
    static let spacingL: CGFloat = 16
    static let spacingM: CGFloat = 12
    static let spacingS: CGFloat = 8
    static let spacingXS: CGFloat = 4

    static let panelWidth: CGFloat = 400
    static let panelHeight: CGFloat = 600
    static let panelMinWidth: CGFloat = 300
    static let panelMinHeight: CGFloat = 400
    static let panelMaxWidth: CGFloat = 600
    static let panelMaxHeight: CGFloat = 800

    static let animationDuration: CGFloat = 0.3
    static let animationDurationFast: CGFloat = 0.15
    static let animationDurationSlow: CGFloat = 0.5

    static let shadowRadius: CGFloat = 10
    static let shadowY: CGFloat = 5
}
```

---

## Animation Constants

### `AnimationConstants`
| Constant | Value | Usage |
|---|---|---|
| `standard` | `Animation.smooth(0.3)` | Default motion |
| `fast` | `Animation.smooth(0.15)` | Quick feedback |
| `snappy` | `Animation.snappy(0.25)` | Direct manipulation |
| `gentle` | `Animation.smooth(0.5, extraBounce: 0.1)` | Large transitions |
| `blink` | `Animation.easeInOut(0.5)` | Cursor blink |
| `appKitTimingFunction()` | `.easeInEaseOut` | NSAnimationContext |

---

## Example Usage

### Using Colors
```swift
// Primary button
Button("Send") { }
    .foregroundColor(.textInverted)
    .background(Color.primaryBlue)

// Status indicator
Circle()
    .fill(status.isError ? Color.statusError : Color.statusIdle)

// Glass background
Rectangle()
    .fill(Color.glassBg)
    .overlay(
        Rectangle()
            .stroke(Color.glassStroke, lineWidth: 1)
    )
```

### Using Constants
```swift
// Padding
.padding(ThemeConstants.spacingL)
.padding(.horizontal, ThemeConstants.spacingXL)

// Corner radius
.cornerRadius(ThemeConstants.cornerRadiusMedium)
.clipShape(RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusLarge))

// Panel size
.frame(
    width: ThemeConstants.panelWidth,
    height: ThemeConstants.panelHeight
)

// Animation
.animation(AnimationConstants.standard, value: isVisible)
```

---

## Dark Mode Support

### Adaptive Colors
Adaptive colors are derived from AppKit system colors:
- `textPrimary` / `textSecondary` / `textTertiary` use `NSColor.*LabelColor`
- Backgrounds use `NSColor.windowBackgroundColor` and `NSColor.controlBackgroundColor`
- Glass colors derive from dynamic `NSColor` values with fixed opacities

### Manual Adaptation
If a custom view needs explicit overrides, keep adjustments localized and reuse
`AnimationConstants`/`ThemeConstants` to avoid drift from the system palette.

---

## Design System Reference

### Color Hierarchy
1. **Primary Blue** - Main actions, active states
2. **Status Colors** - Contextual feedback
3. **Text Colors** - Content hierarchy
4. **Glass Colors** - Background and overlays

### Spacing Hierarchy
1. **Small (8pt)** - Compact elements, inline spacing
2. **Normal (16pt)** - Standard padding
3. **Large (24pt)** - Section separation

### Radius Hierarchy
1. **Small (8pt)** - Buttons, tags
2. **Medium (12pt)** - Cards, inputs
3. **Large (20pt)** - Panels, modals

---

## Related Documentation

### Related Files
| File Path | Relationship | Why Related |
|---|---|---|
| `ui/AIAgentUI/Views/Styles/LiquidGlassStyle.swift` | Uses | Glass effect styling |
| `ui/AIAgentUI/Views/MainPanelView.swift` | Uses | Panel dimensions |
| `ui/AIAgentUI/Views/Components/*.swift` | Uses | All components |

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-01-18 | AI Assistant | Initial implementation | Created theme system | New file |
| 2026-01-18 | AI Agent (Codex) | UI consistency | Added adaptive colors and AnimationConstants; refreshed ThemeConstants docs | High |
| 2026-01-18 | AI Agent (Codex) | Concurrency warnings | Removed NSApplication appearance checks from color helpers | Medium |
