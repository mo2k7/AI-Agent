//
//  InputContextBar.swift
//  AIAgentUI
//

import SwiftUI

struct InputContextBar: View {
    let executionMode: ExecutionMode
    let status: AgentStatus
    let browseProfile: BrowseRestrictionProfile
    let accentColor: Color

    var body: some View {
        HStack(spacing: ThemeConstants.spacingS) {
            capsule(
                icon: executionModeIcon,
                label: executionMode.displayName,
                tint: accentColor
            )

            capsule(
                icon: statusIcon,
                label: statusLabel,
                tint: statusTint
            )

            capsule(
                icon: "globe",
                label: browseProfile.displayName,
                tint: browseTint
            )

            Spacer(minLength: 0)
        }
        .padding(.horizontal, ThemeConstants.spacingXS)
        .padding(.vertical, 2)
    }

    private func capsule(icon: String, label: String, tint: Color) -> some View {
        HStack(spacing: 5) {
            Image(systemName: icon)
                .font(.system(size: 10, weight: .semibold))
            Text(label)
                .font(.system(size: 11, weight: .semibold, design: .rounded))
                .lineLimit(1)
        }
        .foregroundColor(tint)
        .padding(.horizontal, 9)
        .padding(.vertical, 5)
        .background(
            Capsule()
                .fill(tint.opacity(0.12))
        )
        .overlay(
            Capsule()
                .stroke(tint.opacity(0.22), lineWidth: 0.8)
        )
    }

    private var executionModeIcon: String {
        executionMode.config.iconName
    }

    private var statusIcon: String {
        switch status {
        case .thinking, .planning:
            return "sparkles"
        case .callingTool:
            return "hammer"
        case .streaming:
            return "waveform"
        case .awaitingApproval:
            return "hand.raised.fill"
        case .executingPlan:
            return "point.topleft.down.curvedto.point.bottomright.up.fill"
        case .capturingScreen:
            return "viewfinder"
        case .complete:
            return "checkmark.circle.fill"
        case .error:
            return "exclamationmark.triangle.fill"
        case .connecting:
            return "dot.radiowaves.left.and.right"
        case .idle, .planReady:
            return "circle.fill"
        }
    }

    private var statusLabel: String {
        switch status {
        case .idle:
            return "Ready"
        case .complete:
            return "Complete"
        case .error:
            return "Attention"
        default:
            return status.shortText.replacingOccurrences(of: "...", with: "")
        }
    }

    private var statusTint: Color {
        switch status {
        case .error:
            return .statusError
        case .complete:
            return .statusComplete
        case .streaming:
            return .statusStreaming
        case .callingTool, .awaitingApproval, .executingPlan, .capturingScreen:
            return .statusToolCall
        case .thinking, .planning:
            return .statusThinking
        case .connecting:
            return .statusConnecting
        case .idle, .planReady:
            return .textSecondary
        }
    }

    private var browseTint: Color {
        switch browseProfile {
        case .strict:
            return .textSecondary
        case .standard:
            return .secondaryBlue
        case .flexible:
            return .warning
        }
    }
}
