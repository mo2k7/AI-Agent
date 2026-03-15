//
//  StreamingAnimationEffects.swift
//  AIAgentUI
//

import SwiftUI

// MARK: - Wave Reveal Phase

/// Describes the lifecycle of the aurora rim animation.
enum WaveRevealPhase {
    case idle       // no streaming
    case thinking   // streaming started, no text yet
    case streaming  // text arriving
    case done       // streaming complete, fading out
}

// MARK: - Text Height Preference Key

struct TextHeightPreferenceKey: PreferenceKey {
    static let defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) {
        value = max(value, nextValue())
    }
}

// MARK: - Wave Reveal Mask Modifier

/// A feathered top-to-bottom reveal mask applied to the text content.
struct WaveRevealMaskModifier: ViewModifier {
    let isActive: Bool
    let maskHeight: CGFloat
    let featherSize: CGFloat

    func body(content: Content) -> some View {
        if isActive {
            content.mask(
                VStack(spacing: 0) {
                    Rectangle()
                        .frame(height: max(0, maskHeight - featherSize))
                    LinearGradient(
                        colors: [.white, .clear],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                    .frame(height: featherSize)
                    Spacer(minLength: 0)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
            )
        } else {
            content
        }
    }
}

// MARK: - Aurora Rim Overlay

struct AuroraRimOverlay: View {

    let velocity: CGFloat
    let phase: WaveRevealPhase
    let doneOpacity: CGFloat
    let reduceMotion: Bool
    let cornerRadius: CGFloat

    private static let auroraColors: [Color] = [
        Color.secondaryBlue.opacity(0.8),
        Color.statusStreaming.opacity(0.7),
        Color.primaryBlue.opacity(0.6),
        Color.secondaryBlue.opacity(0.5),
        Color.statusStreaming.opacity(0.7),
        Color.primaryBlue.opacity(0.8),
        Color.secondaryBlue.opacity(0.8),
    ]

    var body: some View {
        if reduceMotion {
            RoundedRectangle(cornerRadius: cornerRadius)
                .stroke(Color.secondaryBlue.opacity(Double(rimOpacity)), lineWidth: Double(rimLineWidth))
                .opacity(Double(doneOpacity))
        } else {
            TimelineView(.animation) { context in
                let t = context.date.timeIntervalSinceReferenceDate
                let v = effectiveVelocity
                let period = 12.0 - 5.0 * Double(v)
                let angle = Angle.degrees(t.truncatingRemainder(dividingBy: period) / period * 360)

                RoundedRectangle(cornerRadius: cornerRadius)
                    .stroke(
                        AngularGradient(
                            colors: Self.auroraColors,
                            center: .center,
                            angle: angle
                        ),
                        lineWidth: Double(rimLineWidth)
                    )
                    .blur(radius: Double(rimBlur))
                    .opacity(Double(rimOpacity) * Double(doneOpacity))
            }
        }
    }

    private var effectiveVelocity: CGFloat {
        switch phase {
        case .idle: return 0
        case .thinking: return 0.05
        case .streaming: return velocity
        case .done: return 0.05
        }
    }

    private var rimOpacity: CGFloat { 0.18 + 0.55 * effectiveVelocity }
    private var rimBlur: CGFloat { 1.0 + 4.0 * effectiveVelocity }
    private var rimLineWidth: CGFloat { 1.2 + 1.0 * effectiveVelocity }
}

struct LuxeStreamingIndicator: View {
    let eventToken: Int
    let title: String
    let detail: String
    @State private var phase = false

    var body: some View {
        HStack(spacing: 10) {
            HStack(spacing: 5) { indicatorDots }
            VStack(alignment: .leading, spacing: 1) {
                Text(title)
                    .font(.caption.weight(.semibold))
                    .foregroundColor(.textPrimary)
                Text(detail)
                    .font(.caption2)
                    .foregroundColor(.textSecondary)
                    .lineLimit(1)
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 6)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(Color.secondaryBlue.opacity(0.12))
        )
        .onAppear { phase.toggle() }
        .onChange(of: eventToken) { _, _ in phase.toggle() }
    }

    private var indicatorDots: some View {
        ForEach(0..<3, id: \.self) { idx in
            Circle()
                .fill(
                    LinearGradient(
                        colors: [Color.secondaryBlue, Color.primaryBlue],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
                .frame(width: 6, height: 6)
                .scaleEffect(phase ? (idx == 1 ? 1.45 : 1.2) : 0.82)
                .opacity(phase ? 1.0 : 0.6)
                .animation(
                    .easeInOut(duration: 0.42).delay(Double(idx) * 0.06),
                    value: phase
                )
        }
    }
}

struct MinimalStreamingIndicator: View {
    var body: some View {
        HStack(spacing: ThemeConstants.spacingS) {
            Circle()
                .fill(Color.statusStreaming.opacity(0.65))
                .frame(width: 6, height: 6)
            Text("Updating")
                .font(.caption2)
                .foregroundColor(.textSecondary)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(
            Capsule()
                .fill(Color.statusStreaming.opacity(0.1))
        )
    }
}

struct StreamingPlaceholderCard: View {
    let title: String
    let detail: String
    let activeToolCall: ToolCall?
    let guarded: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: ThemeConstants.spacingS) {
            HStack(alignment: .center, spacing: ThemeConstants.spacingS) {
                placeholderGlyph
                VStack(alignment: .leading, spacing: 3) {
                    Text(title)
                        .font(.system(.body, design: .rounded).weight(.semibold))
                        .foregroundColor(.textPrimary)
                    Text(detail)
                        .font(.caption)
                        .foregroundColor(.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 0)
                if guarded {
                    Text("Stable")
                        .font(.caption2.weight(.semibold))
                        .foregroundColor(.secondaryBlue)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(Capsule().fill(Color.secondaryBlue.opacity(0.12)))
                }
            }

            if let activeToolCall {
                HStack(spacing: ThemeConstants.spacingXS) {
                    Image(systemName: activeToolCall.status.iconName)
                        .font(.caption2)
                        .foregroundColor(.secondaryBlue)
                    Text("\(activeToolCall.status.badgeText): \(activeToolCall.name)")
                        .font(.caption)
                        .foregroundColor(.textSecondary)
                        .lineLimit(1)
                }
            }

            RoundedRectangle(cornerRadius: 999)
                .fill(Color.secondaryBlue.opacity(0.14))
                .frame(height: 6)
                .overlay(alignment: .leading) {
                    Capsule()
                        .fill(
                            LinearGradient(
                                colors: [Color.secondaryBlue.opacity(0.92), Color.primaryBlue.opacity(0.78)],
                                startPoint: .leading,
                                endPoint: .trailing
                            )
                        )
                        .frame(width: guarded ? 90 : 132, height: 6)
                }
        }
        .padding(ThemeConstants.spacingM)
        .background(
            RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusMedium)
                .fill(Color.cardBackground.opacity(0.72))
        )
        .overlay(
            RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusMedium)
                .stroke(Color.glassStroke.opacity(0.42), lineWidth: 0.8)
        )
    }

    private var placeholderGlyph: some View {
        ZStack {
            Circle()
                .fill(
                    LinearGradient(
                        colors: [Color.secondaryBlue.opacity(0.18), Color.primaryBlue.opacity(0.12)],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
                .frame(width: 34, height: 34)
            Image(systemName: guarded ? "waveform.path.ecg" : "sparkles")
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(.secondaryBlue)
        }
    }
}

struct StreamingStatusFooter: View {
    let title: String
    let detail: String
    let guarded: Bool
    let velocity: CGFloat

    var body: some View {
        HStack(spacing: ThemeConstants.spacingS) {
            HStack(spacing: 4) {
                Circle()
                    .fill(accentColor.opacity(0.92))
                    .frame(width: 6, height: 6)
                Capsule()
                    .fill(accentColor.opacity(0.28))
                    .frame(width: progressWidth, height: 6)
            }
            VStack(alignment: .leading, spacing: 1) {
                Text(title)
                    .font(.caption.weight(.semibold))
                    .foregroundColor(.textPrimary)
                Text(detail)
                    .font(.caption2)
                    .foregroundColor(.textSecondary)
                    .lineLimit(1)
            }
            Spacer(minLength: 0)
            if guarded {
                Text("Stable")
                    .font(.caption2.weight(.semibold))
                    .foregroundColor(.secondaryBlue)
            }
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 6)
        .background(
            RoundedRectangle(cornerRadius: 10)
                .fill(accentColor.opacity(0.08))
        )
    }

    private var accentColor: Color { guarded ? .secondaryBlue : .statusStreaming }
    private var progressWidth: CGFloat {
        let normalizedVelocity = min(max(velocity, 0), 1)
        return guarded ? 16 : 16 + (normalizedVelocity * 28)
    }
}

struct CompactToolCallBadge: View {
    let toolCall: ToolCall

    var body: some View {
        HStack(spacing: 5) {
            Image(systemName: toolCall.status.iconName)
                .font(.system(size: 9, weight: .semibold))
            Text(labelText)
                .font(.system(size: 10, weight: .semibold))
                .lineLimit(1)
        }
        .foregroundColor(statusColor)
        .padding(.horizontal, 7)
        .padding(.vertical, 3)
        .background(Capsule().fill(statusColor.opacity(0.16)))
    }

    private var labelText: String {
        switch toolCall.status {
        case .pending: return "Queued \(toolCall.name)"
        case .executing: return "Running \(toolCall.name)"
        case .success: return "Success \(toolCall.name)"
        case .failed: return "Failed \(toolCall.name)"
        }
    }

    private var statusColor: Color {
        switch toolCall.status {
        case .pending: return .statusIdle
        case .executing: return .statusToolCall
        case .success: return .statusComplete
        case .failed: return .statusError
        }
    }
}

struct CompactBrowseNoticeBadge: View {
    let notice: BrowsePolicyNotice

    var body: some View {
        HStack(spacing: 5) {
            Image(systemName: notice.hasWarnings ? "exclamationmark.triangle.fill" : "globe")
                .font(.system(size: 9, weight: .semibold))
            Text(labelText)
                .font(.system(size: 10, weight: .semibold))
                .lineLimit(1)
        }
        .foregroundColor(statusColor)
        .padding(.horizontal, 7)
        .padding(.vertical, 3)
        .background(Capsule().fill(statusColor.opacity(0.16)))
    }

    private var labelText: String { notice.hasWarnings ? "Web warning" : "Web \(notice.profile.displayName)" }
    private var statusColor: Color { notice.hasWarnings ? .warning : .secondaryBlue }
}
