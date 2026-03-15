//
//  BlueTheme.swift
//  AIAgentUI
//
//  Created for Personal macOS AI Agent
//  Status: Active - Color definitions
//

import SwiftUI
#if os(macOS)
import AppKit
#elseif canImport(UIKit)
import UIKit
#endif

/// Blue theme color definitions for the AI Agent UI
/// Based on Apple's Human Interface Guidelines with custom accents
extension Color {
    
    // MARK: - Primary Colors
    
    /// Primary blue accent color (#007AFF)
    static let primaryBlue = Color(hex: "007AFF")
    
    /// Secondary blue for highlights and links (#5AC8FA)
    static let secondaryBlue = Color(hex: "5AC8FA")
    
    /// Dark blue for active/pressed states (#0A84FF)
    static let darkBlue = Color(hex: "0A84FF")
    
    /// Light blue for subtle backgrounds
    static let lightBlue = Color(hex: "E1F0FF")
    
    // MARK: - Ambient Glow Colors

    /// Ambient glow for the app icon ring (idle state)
    static let ambientGlow = Color(hex: "007AFF").opacity(0.25)

    /// Active ambient glow for busy states
    static let ambientGlowActive = Color(hex: "5AC8FA").opacity(0.4)

    // MARK: - Glass Effect Colors
    
    /// Glass background color (adapts to appearance)
    static var glassBg: Color {
        #if os(macOS)
        return Color(PlatformColor.windowBackgroundColor).opacity(0.75)
        #else
        return Color(PlatformColor.systemBackground).opacity(0.75)
        #endif
    }
    
    /// Glass stroke/border color (adapts to appearance)
    static var glassStroke: Color {
        #if os(macOS)
        return Color(PlatformColor.separatorColor).opacity(0.35)
        #else
        return Color(PlatformColor.separator).opacity(0.35)
        #endif
    }
    
    /// Glass inner highlight
    static var glassHighlight: Color {
        Color.white.opacity(0.2)
    }
    
    /// Glass shadow color
    static var glassShadow: Color {
        Color.black.opacity(0.2)
    }
    
    // MARK: - Text Colors
    
    /// Primary text color (adapts to appearance)
    static var textPrimary: Color {
        #if os(macOS)
        return Color(PlatformColor.labelColor)
        #else
        return Color(PlatformColor.label)
        #endif
    }
    
    /// Secondary text color (adapts to appearance)
    static var textSecondary: Color {
        #if os(macOS)
        return Color(PlatformColor.secondaryLabelColor)
        #else
        return Color(PlatformColor.secondaryLabel)
        #endif
    }
    
    /// Tertiary text color for hints (adapts to appearance)
    static var textTertiary: Color {
        #if os(macOS)
        return Color(PlatformColor.tertiaryLabelColor)
        #else
        return Color(PlatformColor.tertiaryLabel)
        #endif
    }
    
    /// Inverted text color for dark backgrounds
    static var textInverted: Color {
        #if os(macOS)
        return Color(PlatformColor.textBackgroundColor)
        #else
        return Color(PlatformColor.systemBackground)
        #endif
    }
    
    // MARK: - Semantic Colors
    
    /// Success color for completed operations
    static let success = Color(hex: "34C759")
    
    /// Warning color for caution states
    static let warning = Color(hex: "FF9500")
    
    /// Error/danger color
    static let danger = Color(hex: "FF3B30")
    
    /// Info color for informational messages
    static let info = Color(hex: "5856D6")
    
    // MARK: - Background Colors
    
    /// Panel background (for the floating panel)
    static var panelBackground: Color {
        #if os(macOS)
        return Color(PlatformColor.windowBackgroundColor)
        #else
        return Color(PlatformColor.systemBackground)
        #endif
    }
    
    /// Card background (for message bubbles, tool cards)
    static var cardBackground: Color {
        #if os(macOS)
        return Color(PlatformColor.controlBackgroundColor)
        #else
        return Color(PlatformColor.secondarySystemBackground)
        #endif
    }
    
    /// Input field background
    static var inputBackground: Color {
        #if os(macOS)
        return Color(PlatformColor.textBackgroundColor)
        #else
        return Color(PlatformColor.secondarySystemBackground)
        #endif
    }
    
    /// Hover state background
    static var hoverBackground: Color {
        #if os(macOS)
        return Color(PlatformColor.selectedContentBackgroundColor).opacity(0.2)
        #else
        return Color(PlatformColor.systemFill).opacity(0.2)
        #endif
    }
    
    // MARK: - Status Colors
    
    /// Color for idle/ready state
    static let statusIdle = Color(hex: "8E8E93")
    
    /// Color for connecting state
    static let statusConnecting = Color(hex: "5AC8FA")
    
    /// Color for thinking/processing state
    static let statusThinking = Color(hex: "007AFF")
    
    /// Color for tool call in progress
    static let statusToolCall = Color(hex: "AF52DE")
    
    /// Color for streaming response
    static let statusStreaming = Color(hex: "34C759")
    
    /// Color for error state
    static let statusError = Color(hex: "FF3B30")
    
    /// Color for completion
    static let statusComplete = Color(hex: "34C759")
}

// MARK: - Hex Color Initializer

extension Color {
    /// Creates a Color from a hex string
    /// - Parameter hex: Hex color string (with or without #)
    init(hex: String) {
        let hex = hex.trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
        var int: UInt64 = 0
        Scanner(string: hex).scanHexInt64(&int)
        let a, r, g, b: UInt64
        switch hex.count {
        case 3: // RGB (12-bit)
            (a, r, g, b) = (255, (int >> 8) * 17, (int >> 4 & 0xF) * 17, (int & 0xF) * 17)
        case 6: // RGB (24-bit)
            (a, r, g, b) = (255, int >> 16, int >> 8 & 0xFF, int & 0xFF)
        case 8: // ARGB (32-bit)
            (a, r, g, b) = (int >> 24, int >> 16 & 0xFF, int >> 8 & 0xFF, int & 0xFF)
        default:
            (a, r, g, b) = (1, 1, 1, 0)
        }
        
        self.init(
            .sRGB,
            red: Double(r) / 255,
            green: Double(g) / 255,
            blue: Double(b) / 255,
            opacity: Double(a) / 255
        )
    }
}

// MARK: - Theme Gradients

extension LinearGradient {
    
    /// Glass effect gradient for backgrounds
    static let glassGradient = LinearGradient(
        colors: [
            Color.glassHighlight,
            Color.glassBg.opacity(0.2)
        ],
        startPoint: .topLeading,
        endPoint: .bottomTrailing
    )
    
    /// Primary button gradient
    static let primaryButtonGradient = LinearGradient(
        colors: [
            Color.primaryBlue,
            Color.darkBlue
        ],
        startPoint: .top,
        endPoint: .bottom
    )
    
    /// Status indicator gradient
    static let statusGradient = LinearGradient(
        colors: [
            Color.primaryBlue.opacity(0.8),
            Color.secondaryBlue.opacity(0.6)
        ],
        startPoint: .leading,
        endPoint: .trailing
    )
}

// MARK: - Theme Constants

/// UI dimension constants for consistent styling
enum ThemeConstants {
    
    // MARK: - Corner Radius
    
    /// Large corner radius (panel)
    static let cornerRadiusLarge: CGFloat = 20
    
    /// Medium corner radius (cards, buttons)
    static let cornerRadiusMedium: CGFloat = 12
    
    /// Small corner radius (input fields, tags)
    static let cornerRadiusSmall: CGFloat = 8
    
    // MARK: - Spacing
    
    /// Extra large spacing
    static let spacingXL: CGFloat = 24
    
    /// Large spacing
    static let spacingL: CGFloat = 16
    
    /// Medium spacing
    static let spacingM: CGFloat = 12
    
    /// Small spacing
    static let spacingS: CGFloat = 8
    
    /// Extra small spacing
    static let spacingXS: CGFloat = 4
    
    // MARK: - Panel Dimensions
    
    /// Default panel width
    static let panelWidth: CGFloat = 400
    
    /// Default panel height
    static let panelHeight: CGFloat = 600
    
    /// Minimum panel width
    static let panelMinWidth: CGFloat = 300
    
    /// Minimum panel height
    static let panelMinHeight: CGFloat = 400
    
    /// Maximum panel width (uncapped — follows macOS native resize behavior)
    static let panelMaxWidth: CGFloat = .infinity

    /// Maximum panel height (uncapped — follows macOS native resize behavior)
    static let panelMaxHeight: CGFloat = .infinity
    
    // MARK: - Animation
    
    /// Standard animation duration
    static let animationDuration: CGFloat = 0.3
    
    /// Fast animation duration
    static let animationDurationFast: CGFloat = 0.15
    
    /// Slow animation duration
    static let animationDurationSlow: CGFloat = 0.5
    
    // MARK: - Shadows
    
    /// Standard shadow radius
    static let shadowRadius: CGFloat = 10
    
    /// Standard shadow Y offset
    static let shadowY: CGFloat = 5
}

// MARK: - Depth Level Constants

/// Visual depth levels for the glass system
enum DepthLevel {
    case base       // Panel background (deepest)
    case surface    // Message bubbles, content cards (middle)
    case floating   // Interactive elements, chips, popovers (top)

    var shadowRadius: CGFloat {
        switch self {
        case .base: return 22
        case .surface: return 10
        case .floating: return 18
        }
    }

    var strokeOpacity: CGFloat {
        switch self {
        case .base: return 0.10
        case .surface: return 0.18
        case .floating: return 0.28
        }
    }

    var shadowOpacity: CGFloat {
        switch self {
        case .base: return 0.26
        case .surface: return 0.16
        case .floating: return 0.32
        }
    }

    var shadowColor: Color {
        Color.black.opacity(shadowOpacity)
    }

    var shadowY: CGFloat {
        switch self {
        case .base: return 12
        case .surface: return 5
        case .floating: return 9
        }
    }
}

// MARK: - Animation Constants

/// Standardized animations for UI consistency
enum AnimationConstants {
    /// Standard spring animation for most interactions
    static let standard = Animation.smooth(duration: 0.3)
    
    /// Quick spring for small UI changes
    static let fast = Animation.smooth(duration: 0.15)
    
    /// Snappy spring for direct manipulation feedback
    static let snappy = Animation.snappy(duration: 0.25)
    
    /// Gentle spring for large transitions
    static let gentle = Animation.smooth(duration: 0.5, extraBounce: 0.1)

    /// Cursor blink animation (non-spring for legibility)
    static let blink = Animation.easeInOut(duration: 0.5)
    
    /// AppKit timing function for NSAnimationContext
    #if os(macOS)
    static func appKitTimingFunction() -> CAMediaTimingFunction {
        CAMediaTimingFunction(name: .easeInEaseOut)
    }
    #endif
}
