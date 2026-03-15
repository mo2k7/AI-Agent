//
//  LiquidGlassStyle.swift
//  AIAgentUI
//
//  Created for Personal macOS AI Agent
//  Status: Active - Glass effect modifiers
//

import SwiftUI

// MARK: - Liquid Glass View Modifier

/// Applies the liquid glass effect to a view
struct LiquidGlassModifier: ViewModifier {
    
    /// Corner radius for the glass effect
    var cornerRadius: CGFloat
    
    /// Whether to show the border stroke
    var showBorder: Bool
    
    /// Whether to show the shadow
    var showShadow: Bool
    
    /// Material style to use
    var material: Material
    
    init(
        cornerRadius: CGFloat = ThemeConstants.cornerRadiusLarge,
        showBorder: Bool = true,
        showShadow: Bool = true,
        material: Material = .ultraThinMaterial
    ) {
        self.cornerRadius = cornerRadius
        self.showBorder = showBorder
        self.showShadow = showShadow
        self.material = material
    }
    
    func body(content: Content) -> some View {
        content
            .background(material)
            .background(
                LinearGradient.glassGradient
            )
            .clipShape(RoundedRectangle(cornerRadius: cornerRadius))
            .overlay(
                RoundedRectangle(cornerRadius: cornerRadius)
                    .stroke(Color.glassStroke, lineWidth: showBorder ? 1 : 0)
            )
            .shadow(
                color: showShadow ? Color.glassShadow : .clear,
                radius: ThemeConstants.shadowRadius,
                x: 0,
                y: ThemeConstants.shadowY
            )
    }
}

// MARK: - Section Fade Modifier

/// Adds a gradient fade at a specified edge to blend sections seamlessly
struct SectionFadeModifier: ViewModifier {
    var edge: Edge
    var height: CGFloat
    var color: Color

    func body(content: Content) -> some View {
        content.overlay(alignment: edgeAlignment) {
            LinearGradient(
                colors: gradientColors,
                startPoint: startPoint,
                endPoint: endPoint
            )
            .frame(height: height)
            .allowsHitTesting(false)
        }
    }

    private var edgeAlignment: Alignment {
        edge == .top ? .top : .bottom
    }

    private var gradientColors: [Color] {
        switch edge {
        case .top:
            return [color, .clear]
        case .bottom:
            return [.clear, color]
        default:
            return [.clear, color]
        }
    }

    private var startPoint: UnitPoint {
        edge == .top ? .top : .top
    }

    private var endPoint: UnitPoint {
        edge == .top ? .bottom : .bottom
    }
}

// MARK: - Glass Card Modifier

/// Applies a subtle glass card effect for inner components
struct GlassCardModifier: ViewModifier {
    
    var cornerRadius: CGFloat
    var padding: CGFloat
    
    init(
        cornerRadius: CGFloat = ThemeConstants.cornerRadiusMedium,
        padding: CGFloat = ThemeConstants.spacingM
    ) {
        self.cornerRadius = cornerRadius
        self.padding = padding
    }
    
    func body(content: Content) -> some View {
        content
            .padding(padding)
            .background(Color.cardBackground.opacity(0.8))
            .clipShape(RoundedRectangle(cornerRadius: cornerRadius))
            .overlay(
                RoundedRectangle(cornerRadius: cornerRadius)
                    .stroke(Color.glassStroke.opacity(0.5), lineWidth: 0.5)
            )
    }
}

// MARK: - Glass Button Style

/// A button style with glass effect
struct GlassButtonStyle: ButtonStyle {
    
    var isDestructive: Bool = false
    
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .padding(.horizontal, ThemeConstants.spacingM)
            .padding(.vertical, ThemeConstants.spacingS)
            .background(
                Group {
                    if isDestructive {
                        Color.danger.opacity(configuration.isPressed ? 0.8 : 0.6)
                    } else {
                        Color.primaryBlue.opacity(configuration.isPressed ? 0.9 : 0.7)
                    }
                }
            )
            .foregroundColor(.white)
            .clipShape(RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusSmall))
            .overlay(
                RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusSmall)
                    .stroke(Color.white.opacity(0.2), lineWidth: 0.5)
            )
            .scaleEffect(configuration.isPressed ? 0.98 : 1.0)
            .animation(AnimationConstants.fast, value: configuration.isPressed)
    }
}

// MARK: - Glass Input Style

/// A text field style with glass effect
struct GlassInputStyle: TextFieldStyle {
    
    @FocusState private var isFocused: Bool
    
    func _body(configuration: TextField<Self._Label>) -> some View {
        configuration
            .textFieldStyle(.plain)
            .padding(ThemeConstants.spacingM)
            .background(Color.inputBackground.opacity(0.8))
            .clipShape(RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusSmall))
            .overlay(
                RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusSmall)
                    .stroke(
                        Color.primaryBlue.opacity(0.5),
                        lineWidth: 1
                    )
            )
    }
}

// MARK: - View Extensions

extension View {
    /// Deepest glass layer for panel shells and overlay frames.
    /// On macOS this applies rounded corners, border stroke, and drop shadow for the floating panel.
    /// On iOS this applies the material background without clipping or shadow since the root view is full-screen.
    func glassBase(cornerRadius: CGFloat = ThemeConstants.cornerRadiusLarge) -> some View {
        #if os(macOS)
        self
            .background(.ultraThinMaterial)
            .background(LinearGradient.glassGradient.opacity(0.9))
            .clipShape(RoundedRectangle(cornerRadius: cornerRadius))
            .overlay(
                RoundedRectangle(cornerRadius: cornerRadius)
                    .stroke(Color.glassStroke.opacity(DepthLevel.base.strokeOpacity), lineWidth: 1)
            )
            .shadow(
                color: DepthLevel.base.shadowColor,
                radius: DepthLevel.base.shadowRadius,
                x: 0,
                y: DepthLevel.base.shadowY
            )
        #else
        self
            .background(.ultraThinMaterial)
            .background(LinearGradient.glassGradient.opacity(0.9))
        #endif
    }

    /// Full-screen glass background for the iOS root container.
    /// Applies the material + gradient without rounded corners, clipping, or shadow.
    func iosFullScreenBase() -> some View {
        self
            .background(.ultraThinMaterial)
            .background(LinearGradient.glassGradient.opacity(0.9))
    }

    
    /// Applies the liquid glass effect
    /// - Parameters:
    ///   - cornerRadius: Corner radius for the glass shape
    ///   - showBorder: Whether to show the border stroke
    ///   - showShadow: Whether to show the drop shadow
    ///   - material: Material style to use for the blur
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
    
    /// Applies the glass card effect
    /// - Parameters:
    ///   - cornerRadius: Corner radius for the card
    ///   - padding: Inner padding
    func glassCard(
        cornerRadius: CGFloat = ThemeConstants.cornerRadiusMedium,
        padding: CGFloat = ThemeConstants.spacingM
    ) -> some View {
        modifier(GlassCardModifier(
            cornerRadius: cornerRadius,
            padding: padding
        ))
    }
    
    /// Glass surface depth (middle layer — message bubbles, content cards)
    func glassSurface(cornerRadius: CGFloat = ThemeConstants.cornerRadiusMedium) -> some View {
        self
            .background(.thinMaterial)
            .clipShape(RoundedRectangle(cornerRadius: cornerRadius))
            .overlay(
                RoundedRectangle(cornerRadius: cornerRadius)
                    .stroke(Color.glassStroke.opacity(DepthLevel.surface.strokeOpacity), lineWidth: 0.8)
            )
            .shadow(
                color: DepthLevel.surface.shadowColor,
                radius: DepthLevel.surface.shadowRadius,
                x: 0,
                y: DepthLevel.surface.shadowY
            )
    }

    /// Glass floating depth (top layer — interactive elements, chips, popovers)
    func glassFloating(cornerRadius: CGFloat = ThemeConstants.cornerRadiusSmall) -> some View {
        self
            .background(.regularMaterial)
            .clipShape(RoundedRectangle(cornerRadius: cornerRadius))
            .overlay(
                RoundedRectangle(cornerRadius: cornerRadius)
                    .stroke(Color.glassStroke.opacity(DepthLevel.floating.strokeOpacity), lineWidth: 1)
            )
            .shadow(
                color: DepthLevel.floating.shadowColor,
                radius: DepthLevel.floating.shadowRadius,
                x: 0,
                y: DepthLevel.floating.shadowY
            )
    }

    /// Adds a gradient fade at the specified edge to blend sections
    func sectionFade(
        edge: Edge = .bottom,
        height: CGFloat = 6,
        color: Color = Color.glassShadow.opacity(0.06)
    ) -> some View {
        modifier(SectionFadeModifier(edge: edge, height: height, color: color))
    }

    /// Applies a hover effect for interactive elements
    func hoverEffect() -> some View {
        self.contentShape(Rectangle())
    }
}

// MARK: - Overlay Container

/// Reusable overlay container for modal-like content on NSPanel.
/// Uses ZStack pattern instead of .sheet() which is invisible on NSPanel with hidden titlebar.
struct OverlayContainer<Content: View>: View {
    @Binding var isPresented: Bool
    var tapOutsideToDismiss: Bool = true
    @ViewBuilder var content: () -> Content

    var body: some View {
        ZStack {
            Color.black.opacity(0.35)
                .ignoresSafeArea()
                .contentShape(Rectangle())
                .onTapGesture {
                    guard tapOutsideToDismiss else { return }
                    isPresented = false
                }

            VStack(spacing: 0) {
                HStack {
                    Spacer()
                    Button(action: { isPresented = false }) {
                        Image(systemName: "xmark.circle.fill")
                            .font(.system(size: 20))
                            .foregroundColor(.secondary)
                    }
                    .buttonStyle(.plain)
                    .help("Close")
                }
                .padding(.trailing, ThemeConstants.spacingM)
                .padding(.top, ThemeConstants.spacingS)

                content()
            }
            #if os(macOS)
            .glassBase(cornerRadius: ThemeConstants.cornerRadiusLarge)
            #else
            .background(.ultraThinMaterial)
            .background(LinearGradient.glassGradient.opacity(0.9))
            .clipShape(RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusLarge))
            .contentShape(RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusLarge))
            .padding(.horizontal, ThemeConstants.spacingM)
            .padding(.vertical, ThemeConstants.spacingXL)
            #endif
        }
        .transition(.opacity.combined(with: .scale(scale: 0.95)))
    }
}

// MARK: - Preview

#if DEBUG
struct LiquidGlassPreview: View {
    var body: some View {
        ZStack {
            // Background gradient to show glass effect
            LinearGradient(
                colors: [.blue.opacity(0.3), .purple.opacity(0.3)],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            
            VStack(spacing: ThemeConstants.spacingL) {
                // Glass panel
                VStack(spacing: ThemeConstants.spacingM) {
                    Text("Liquid Glass Panel")
                        .font(.headline)
                        .foregroundColor(.textPrimary)
                    
                    Text("This is a demonstration of the glass effect")
                        .font(.body)
                        .foregroundColor(.textSecondary)
                    
                    // Glass card inside
                    HStack {
                        Image(systemName: "brain")
                            .foregroundColor(.primaryBlue)
                        Text("Thinking...")
                            .foregroundColor(.textPrimary)
                    }
                    .glassCard()
                    
                    // Buttons
                    HStack(spacing: ThemeConstants.spacingS) {
                        Button("Primary") {}
                            .buttonStyle(GlassButtonStyle())
                        
                        Button("Cancel") {}
                            .buttonStyle(GlassButtonStyle(isDestructive: true))
                    }
                }
                .padding(ThemeConstants.spacingL)
                .liquidGlass()
                .frame(width: 300)
            }
        }
        .frame(width: 400, height: 400)
    }
}

struct LiquidGlassStyle_Previews: PreviewProvider {
    static var previews: some View {
        LiquidGlassPreview()
    }
}
#endif
