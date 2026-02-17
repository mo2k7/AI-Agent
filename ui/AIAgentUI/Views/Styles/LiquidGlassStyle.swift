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
    
    /// Applies a hover effect for interactive elements
    func hoverEffect() -> some View {
        self.contentShape(Rectangle())
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
