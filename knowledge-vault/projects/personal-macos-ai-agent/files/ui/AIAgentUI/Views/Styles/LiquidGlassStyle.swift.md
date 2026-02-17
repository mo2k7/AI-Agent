# File Doc: `ui/AIAgentUI/Views/Styles/LiquidGlassStyle.swift`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `ui/AIAgentUI/Views/Styles/LiquidGlassStyle.swift` |
| Doc Path | `projects/personal-macos-ai-agent/files/ui/AIAgentUI/Views/Styles/LiquidGlassStyle.swift.md` |
| Language | Swift |
| File Role | Liquid Glass Visual Effect Modifiers |
| Ownership | Core Team |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-01-18 |
| Last Major Edit (YYYY-MM-DD) | 2026-01-18 |
| Modified By | AI Agent (Codex) |
| WHY (Reason for last change) | Added compositingGroup optimization and standardized button press animation |
| Lines of Code (LOC) | 243 |
| Cyclomatic Complexity | Low |
| Test Coverage | 0% |

---

## Purpose & Responsibilities

### What this file does
**Single-sentence summary:**
Provides SwiftUI view modifiers for applying the "Liquid Glass" visual effect with blur, gradients, and subtle borders.

**Detailed responsibilities:**
- Implements `LiquidGlassModifier` for main panel glass effect
- Implements `GlassCardModifier` for inner card elements
- Provides `GlassButtonStyle` for buttons
- Provides `GlassInputStyle` for text inputs
- Offers View extensions for convenient access (`.liquidGlass()`, `.glassCard()`)
- Combines material blur, gradient overlays, stroke borders, and shadows
- Flattens expensive layers via `compositingGroup()` for performance

### What this file must NOT do (boundaries)
**Out of scope:**
- Color definitions (see `BlueTheme.swift`)
- Layout or component structure

### Who/what calls it
| Caller | Purpose | Frequency | Error Handling |
|---|---|---|---|
| `MainPanelView` | Panel styling | Once | N/A |
| All UI components | Element styling | Throughout | N/A |

---

## Imports / Dependencies

### Framework Dependencies
| Framework | What's Used | Why Needed |
|---|---|---|
| SwiftUI | ViewModifier, Material | UI framework |

---

## Public Surface (Document EVERYTHING Exposed)

### Exports / Public Symbols
| Symbol | Type (func/class/const/type) | Visibility | Status | Brief Description |
|---|---|---|---|---|
| `LiquidGlassModifier` | struct | public | Stable | Main glass effect |
| `GlassCardModifier` | struct | public | Stable | Inner card effect |
| `GlassButtonStyle` | struct | public | Stable | Button style |
| `GlassInputStyle` | struct | public | Stable | Input field style |
| `View.liquidGlass()` | extension | public | Stable | Convenience method |
| `View.glassCard()` | extension | public | Stable | Convenience method |
| `View.hoverEffect()` | extension | public | Stable | Pointer affordance helper |

---

## Types (Classes / Structs / Enums / Interfaces)

### `LiquidGlassModifier`
| Metadata | Value |
|---|---|
| Kind | struct |
| Purpose | Main panel glass effect with blur, gradient, and shadow |
| Thread-Safe | Yes (value type) |
| Immutable | Yes |
| Serializable | No |

#### Inheritance & Implementation
- **Extends:** N/A
- **Implements:** `ViewModifier`
- **Used By:** `MainPanelView`, panel containers

#### Fields / Properties
| Name | Type | Visibility | Default | Required | Mutable | Purpose |
|---|---|---|---|---|---|---|
| `cornerRadius` | CGFloat | public | `ThemeConstants.cornerRadiusLarge` | No | No | Corner rounding |
| `showBorder` | Bool | public | `true` | No | No | Toggle border stroke |
| `showShadow` | Bool | public | `true` | No | No | Toggle drop shadow |
| `material` | Material | public | `.ultraThinMaterial` | No | No | Background material |

#### Effect Layers
```swift
func body(content: Content) -> some View {
    content
        // 1. Background blur
        .background(material)
        
        // 2. Gradient overlay
        .background(LinearGradient.glassGradient)
        
        // 3. Flatten layers before effects
        .compositingGroup()
        
        // 4. Corner clipping
        .clipShape(RoundedRectangle(cornerRadius: cornerRadius, style: .continuous))
        
        // 5. Border stroke
        .overlay(
            RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                .stroke(Color.glassStroke, lineWidth: showBorder ? 1 : 0)
        )
        
        // 6. Drop shadow
        .shadow(color: showShadow ? Color.glassShadow : .clear,
                radius: ThemeConstants.shadowRadius,
                x: 0,
                y: ThemeConstants.shadowY)
}
```

---

### `GlassCardModifier`
| Metadata | Value |
|---|---|
| Kind | struct |
| Purpose | Subtle glass effect for inner cards |
| Thread-Safe | Yes |
| Immutable | Yes |

#### Effect Layers
```swift
func body(content: Content) -> some View {
    content
        .padding(padding)
        .background(Color.cardBackground.opacity(0.8))
        .clipShape(RoundedRectangle(cornerRadius: cornerRadius, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                .stroke(Color.glassStroke.opacity(0.5), lineWidth: 0.5)
        )
}
```

---

### `GlassButtonStyle`
| Metadata | Value |
|---|---|
| Kind | struct |
| Purpose | Glass-styled button with hover effects |
| Thread-Safe | Yes |
| Immutable | Yes |

#### Inheritance & Implementation
- **Extends:** N/A
- **Implements:** `ButtonStyle`

#### Configuration Options
| Option | Type | Default | Purpose |
|---|---|---|---|
| `isPrimary` | Bool | `true` | Primary vs secondary styling |

#### Visual States
| State | Background | Border |
|---|---|---|
| Normal | `primaryBlue` or `danger` | `white.opacity(0.2)` |
| Pressed | Higher opacity | `white.opacity(0.2)` |

#### Implementation
```swift
struct GlassButtonStyle: ButtonStyle {
    var isDestructive: Bool = false
    
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .padding(.horizontal, ThemeConstants.spacingM)
            .padding(.vertical, ThemeConstants.spacingS)
            .background(
                isDestructive
                    ? Color.danger.opacity(configuration.isPressed ? 0.8 : 0.6)
                    : Color.primaryBlue.opacity(configuration.isPressed ? 0.9 : 0.7)
            )
            .foregroundColor(.white)
            .clipShape(RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusSmall))
            .overlay(
                RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusSmall)
                    .stroke(Color.white.opacity(0.2), lineWidth: 0.5)
            )
            .scaleEffect(configuration.isPressed ? 0.98 : 1)
            .animation(AnimationConstants.fast, value: configuration.isPressed)
    }
}
```

---

### `GlassInputStyle`
| Metadata | Value |
|---|---|
| Kind | struct |
| Purpose | Glass-styled text input field |
| Thread-Safe | Yes |
| Immutable | Yes |

#### Implementation
```swift
struct GlassInputStyle: TextFieldStyle {
    func _body(configuration: TextField<Self._Label>) -> some View {
        configuration
            .textFieldStyle(.plain)
            .padding(ThemeConstants.spacingM)
            .background(Color.inputBackground.opacity(0.8))
            .clipShape(RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusSmall))
            .overlay(
                RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusSmall)
                    .stroke(Color.primaryBlue.opacity(0.5), lineWidth: 1)
            )
    }
}
```

---

## View Extensions

### `.liquidGlass()`
```swift
extension View {
    func liquidGlass(
        cornerRadius: CGFloat = ThemeConstants.cornerRadiusLarge,
        showBorder: Bool = true,
        showShadow: Bool = true,
        material: Material = .ultraThinMaterial
    ) -> some View {
        modifier(LiquidGlassModifier(
            cornerRadius: cornerRadius,
            showBorder: showBorder,
            showShadow: showShadow,
            material: material
        ))
    }
}
```

### `.glassCard()`
```swift
extension View {
    func glassCard(
        cornerRadius: CGFloat = ThemeConstants.cornerRadiusMedium,
        padding: CGFloat = ThemeConstants.spacingM
    ) -> some View {
        modifier(GlassCardModifier(cornerRadius: cornerRadius, padding: padding))
    }
}
```

---

## Example Usage

### Main Panel
```swift
VStack {
    // Panel content
}
.frame(width: 400, height: 600)
.liquidGlass()
```

### Card Inside Panel
```swift
VStack {
    Text("Tool Call")
    // ...
}
.padding()
.glassCard()
```

### Primary Button
```swift
Button("Send") {
    // action
}
.buttonStyle(GlassButtonStyle())
```

### Destructive Button
```swift
Button("Cancel") {
    // action
}
.buttonStyle(GlassButtonStyle(isDestructive: true))
```

### Input Field
```swift
@State private var text = ""
TextField("Enter message...", text: $text)
    .textFieldStyle(GlassInputStyle())
```

---

## Visual Design Notes

### Liquid Glass Effect Components
1. **Material Blur** (`.ultraThinMaterial`) - Base translucency
2. **Gradient Overlay** - Subtle white gradient for depth
3. **Rounded Corners** - `.continuous` style for smooth curves
4. **Border Gradient** - Top-left highlight to bottom-right
5. **Drop Shadow** - Soft shadow for elevation

### Design Principles
- **Depth**: Layered transparency creates sense of depth
- **Softness**: Rounded corners and blur reduce visual harshness
- **Hierarchy**: Different intensities for panel vs cards
- **Feedback**: Buttons scale on press, inputs highlight on focus

### Material Choices
| Element | Material | Reason |
|---|---|---|
| Main Panel | `.ultraThinMaterial` | Maximum blur, subtle |
| Cards | `white.opacity(0.1)` | Lighter, layered |
| Inputs | `white.opacity(0.1)` | Match cards |

---

## Preview Provider

```swift
struct LiquidGlassStyle_Previews: PreviewProvider {
    static var previews: some View {
        VStack(spacing: 20) {
            // Main panel preview
            VStack {
                Text("Liquid Glass Panel")
            }
            .frame(width: 300, height: 200)
            .liquidGlass()
            
            // Card preview
            VStack {
                Text("Glass Card")
            }
            .padding()
            .glassCard()
            
            // Buttons
            HStack {
                Button("Primary") { }
                    .buttonStyle(GlassButtonStyle(isPrimary: true))
                
                Button("Secondary") { }
                    .buttonStyle(GlassButtonStyle(isPrimary: false))
            }
        }
        .padding()
        .background(Color.gray)
    }
}
```

---

## Related Documentation

### Related Files
| File Path | Relationship | Why Related |
|---|---|---|
| `ui/AIAgentUI/Views/Styles/BlueTheme.swift` | Uses | Colors and constants |
| `ui/AIAgentUI/Views/MainPanelView.swift` | Used by | Panel styling |
| `ui/AIAgentUI/Views/Components/InputField.swift` | Used by | Input styling |
| `ui/AIAgentUI/Views/Components/ToolCallCard.swift` | Used by | Card styling |

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-01-18 | AI Assistant | Initial implementation | Created glass style modifiers | New file |
| 2026-01-18 | AI Agent (Codex) | Performance polish | Added compositingGroup and updated button animation; aligned docs with current API | Medium |
