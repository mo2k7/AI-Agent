//
//  WelcomeView.swift
//  AIAgentUI
//
//  Created for Personal macOS AI Agent
//  Status: Active - Mode-aware welcome screen for empty conversation state
//

import SwiftUI

// MARK: - Welcome View

/// Mode-aware welcome screen shown when the conversation is empty.
/// Displays a time-based greeting, animated illustration, and suggestion chips.
struct WelcomeView: View {

    let executionMode: ExecutionMode
    var onSuggestionTapped: (String) -> Void

    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        VStack(spacing: 20) {
            Spacer()

            // Animated illustration
            WelcomeIllustration(mode: executionMode, reduceMotion: reduceMotion)
                .frame(width: 80, height: 80)
                .padding(16)
                .background(
                    Circle()
                        .fill(
                            RadialGradient(
                                colors: [
                                    modeTint.opacity(0.18),
                                    modeTint.opacity(0.04),
                                    .clear,
                                ],
                                center: .center,
                                startRadius: 2,
                                endRadius: 68
                            )
                        )
                )

            // Time-aware greeting
            VStack(spacing: 6) {
                Text(greeting)
                    .font(.title3.weight(.medium))
                    .foregroundColor(.textPrimary)

                Text(modeHeadline)
                    .font(.caption.weight(.semibold))
                    .foregroundColor(modeTint)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 4)
                    .background(
                        Capsule()
                            .fill(modeTint.opacity(0.12))
                    )
            }

            // Mode description
            Text(modeDescription)
                .font(.subheadline)
                .foregroundColor(.textSecondary)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 300)

            // Suggestion chips
            WelcomeSuggestionGrid(
                suggestions: suggestions,
                onTap: onSuggestionTapped
            )
            .padding(.top, 4)

            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }

    // MARK: - Computed Properties

    private var greeting: String {
        let hour = Calendar.current.component(.hour, from: Date())
        switch hour {
        case 5..<12:
            return "Good morning"
        case 12..<17:
            return "Good afternoon"
        case 17..<22:
            return "Good evening"
        default:
            return "Hello"
        }
    }

    private var modeDescription: String {
        executionMode.config.welcomeDescription
    }

    private var modeHeadline: String {
        executionMode.config.welcomeHeadline
    }

    private var modeTint: Color {
        executionMode.config.themeColor
    }

    private var suggestions: [WelcomeSuggestion] {
        executionMode.config.welcomeSuggestions.map {
            WelcomeSuggestion(text: $0.text, icon: $0.icon)
        }
    }
}

// MARK: - Suggestion Model

struct WelcomeSuggestion: Identifiable {
    let id = UUID()
    let text: String
    let icon: String
}

// MARK: - Suggestion Grid

struct WelcomeSuggestionGrid: View {
    let suggestions: [WelcomeSuggestion]
    let onTap: (String) -> Void

    var body: some View {
        LazyVGrid(
            columns: [GridItem(.flexible()), GridItem(.flexible())],
            spacing: 8
        ) {
            ForEach(suggestions) { suggestion in
                SuggestionChip(suggestion: suggestion, onTap: onTap)
            }
        }
        .frame(maxWidth: 340)
    }
}

// MARK: - Suggestion Chip

struct SuggestionChip: View {
    let suggestion: WelcomeSuggestion
    let onTap: (String) -> Void
    @State private var isHovered = false

    var body: some View {
        Button(action: { onTap(suggestion.text) }) {
            HStack(spacing: 6) {
                Image(systemName: suggestion.icon)
                    .font(.system(size: 11))
                    .foregroundColor(.primaryBlue)

                Text(suggestion.text)
                    .font(.caption)
                    .foregroundColor(.textPrimary)
                    .lineLimit(1)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 7)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(Color.primaryBlue.opacity(isHovered ? 0.12 : 0.06))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(Color.primaryBlue.opacity(isHovered ? 0.25 : 0.1), lineWidth: 0.5)
            )
        }
        .buttonStyle(.plain)
        .onHover { hovering in isHovered = hovering }
        .accessibilityLabel(suggestion.text)
        .glassFloating(cornerRadius: 8)
    }
}

// MARK: - Welcome Illustration

/// Animated illustration that adapts to the active execution mode.
struct WelcomeIllustration: View {
    let mode: ExecutionMode
    let reduceMotion: Bool

    @State private var phase: CGFloat = 0

    var body: some View {
        TimelineView(.animation(minimumInterval: reduceMotion ? nil : 1.0 / 30.0)) { timeline in
            Canvas { context, size in
                let center = CGPoint(x: size.width / 2, y: size.height / 2)
                let time = reduceMotion ? 0 : timeline.date.timeIntervalSinceReferenceDate

                // Draw radiating circles
                drawRadiatingCircles(context: context, center: center, time: time, size: size)

                // Draw central icon
                drawCentralIcon(context: context, center: center, size: size)
            }
        }
    }

    private func drawRadiatingCircles(context: GraphicsContext, center: CGPoint, time: Double, size: CGSize) {
        let circleCount = 3
        let maxRadius = min(size.width, size.height) / 2
        let baseColor: Color = modeColor

        for i in 0..<circleCount {
            let phaseOffset = Double(i) / Double(circleCount)
            let progress = (sin(time * 0.8 + phaseOffset * .pi * 2) + 1) / 2  // 0...1
            let radius = maxRadius * (0.4 + progress * 0.5)
            let opacity = 0.15 * (1 - progress)

            var circle = Path()
            circle.addEllipse(in: CGRect(
                x: center.x - radius,
                y: center.y - radius,
                width: radius * 2,
                height: radius * 2
            ))

            context.stroke(circle, with: .color(baseColor.opacity(opacity)), lineWidth: 1.5)
        }
    }

    private func drawCentralIcon(context: GraphicsContext, center: CGPoint, size: CGSize) {
        let iconSize: CGFloat = 28
        let iconRect = CGRect(
            x: center.x - iconSize / 2,
            y: center.y - iconSize / 2,
            width: iconSize,
            height: iconSize
        )

        let symbol = context.resolve(Image(systemName: modeIcon))
        context.draw(symbol, in: iconRect)
    }

    private var modeColor: Color {
        mode.config.themeColor
    }

    private var modeIcon: String {
        mode.config.iconName
    }
}

// MARK: - Preview

#if DEBUG
struct WelcomeView_Previews: PreviewProvider {
    static var previews: some View {
        VStack {
            WelcomeView(executionMode: .direct, onSuggestionTapped: { _ in })
        }
        .frame(width: 400, height: 500)
        .background(Color.panelBackground)
    }
}
#endif
