//
//  AmbientAppIcon.swift
//  AIAgentUI
//
//  Created for Personal macOS AI Agent
//  Status: Active - Status-reactive app icon with animated glow ring
//

import SwiftUI

/// A 24x24 brain icon with an animated glow ring that reacts to agent status.
/// Replaces the static header brain icon with ambient intelligence feedback.
struct AmbientAppIcon: View {

    let status: AgentStatus
    let isConnected: Bool

    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private let iconSize: CGFloat = 18
    private let ringSize: CGFloat = 28
    @State private var animateBusyRing = false

    var body: some View {
        ZStack {
            // Glow ring
            glowRing

            // Brain icon
            Image(systemName: "brain")
                .font(.system(size: iconSize, weight: .medium))
                .foregroundColor(.primaryBlue)

            // Connection dot
            Circle()
                .fill(isConnected ? Color.statusComplete : Color.statusError)
                .frame(width: 6, height: 6)
                .overlay(
                    Circle()
                        .stroke(Color.panelBackground, lineWidth: 1.5)
                )
                .offset(x: 9, y: 9)
        }
        .frame(width: ringSize + 4, height: ringSize + 4)
        .onAppear {
            animateBusyRing = status.isBusy
        }
        .onChange(of: status.isBusy) { _, busy in
            animateBusyRing = busy
        }
        .animation(
            reduceMotion ? nil : .linear(duration: 1.6).repeatForever(autoreverses: false),
            value: animateBusyRing
        )
    }

    // MARK: - Glow Ring

    @ViewBuilder
    private var glowRing: some View {
        if status.isBusy {
            if case .streaming = status {
                Circle()
                    .trim(from: 0.12, to: 0.88)
                    .stroke(
                        AngularGradient(
                            colors: [
                                Color.statusStreaming.opacity(0.1),
                                Color.statusStreaming,
                                Color.secondaryBlue,
                                Color.statusStreaming.opacity(0.1),
                            ],
                            center: .center
                        ),
                        style: StrokeStyle(lineWidth: 2.4, lineCap: .round)
                    )
                    .frame(width: ringSize, height: ringSize)
                    .rotationEffect(.degrees(reduceMotion ? 0 : (animateBusyRing ? 360 : 0)))
                    .shadow(color: Color.statusStreaming.opacity(0.35), radius: 8)
            } else {
                Circle()
                    .stroke(
                        ringColor.opacity(reduceMotion ? 0.34 : ringOpacity),
                        lineWidth: toolFocusedRing ? 2.4 : 2
                    )
                    .frame(width: ringSize, height: ringSize)
                    .modifier(GlowPulseModifier(
                        isActive: status.isBusy && !reduceMotion,
                        color: ringColor
                    ))
            }
        } else {
            Circle()
                .stroke(Color.primaryBlue.opacity(0.15), lineWidth: 1.5)
                .frame(width: ringSize, height: ringSize)
        }
    }

    private var ringColor: Color {
        switch status {
        case .thinking, .planning, .planReady:
            return .statusThinking
        case .callingTool, .awaitingApproval, .executingPlan, .capturingScreen:
            return .statusToolCall
        case .streaming:
            return .statusStreaming
        case .connecting:
            return .statusConnecting
        case .error:
            return .statusError
        default:
            return .primaryBlue
        }
    }

    private var ringOpacity: CGFloat {
        status.isBusy ? 0.5 : 0.15
    }

    private var toolFocusedRing: Bool {
        switch status {
        case .callingTool, .awaitingApproval, .executingPlan, .capturingScreen:
            return true
        default:
            return false
        }
    }

    init(status: AgentStatus, isConnected: Bool) {
        self.status = status
        self.isConnected = isConnected
    }
}

// MARK: - Glow Pulse Modifier

/// Adds a pulsing glow effect around the ring when active
private struct GlowPulseModifier: ViewModifier {
    let isActive: Bool
    let color: Color

    @State private var isPulsing = false

    func body(content: Content) -> some View {
        content
            .shadow(
                color: isActive ? color.opacity(isPulsing ? 0.4 : 0.1) : .clear,
                radius: isPulsing ? 6 : 2
            )
            .scaleEffect(isPulsing ? 1.08 : 1.0)
            .animation(
                isActive
                    ? Animation.easeInOut(duration: 1.2).repeatForever(autoreverses: true)
                    : .default,
                value: isPulsing
            )
            .onChange(of: isActive) { _, active in
                isPulsing = active
            }
            .onAppear {
                if isActive { isPulsing = true }
            }
    }
}

// MARK: - Preview

#if DEBUG
struct AmbientAppIcon_Previews: PreviewProvider {
    static var previews: some View {
        VStack(spacing: 20) {
            AmbientAppIcon(status: .idle, isConnected: true)
            AmbientAppIcon(status: .thinking, isConnected: true)
            AmbientAppIcon(status: .callingTool(toolName: "search"), isConnected: true)
            AmbientAppIcon(status: .streaming, isConnected: true)
            AmbientAppIcon(status: .error(message: "fail"), isConnected: false)
        }
        .padding()
        .background(Color.panelBackground)
    }
}
#endif
