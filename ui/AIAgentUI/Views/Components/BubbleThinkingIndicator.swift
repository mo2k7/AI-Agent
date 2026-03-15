//
//  BubbleThinkingIndicator.swift
//  AIAgentUI
//

import SwiftUI

/// Compact thinking indicator with timer for message bubbles
struct BubbleThinkingIndicator: View {

    let status: AgentStatus
    let statusDetail: String
    let activeToolCall: ToolCall?
    let browseNotice: BrowsePolicyNotice?
    let guarded: Bool
    let canCancel: Bool
    let isCancelling: Bool
    let onCancel: (() -> Void)?

    @State private var elapsedTime: TimeInterval = 0
    @State private var startTime: Date = Date()
    @State private var dotPhase = 0
    @State private var isExpanded = false

    private let timer = Timer.publish(every: 0.25, on: .main, in: .common).autoconnect()
    private let dotTimer = Timer.publish(every: 0.8, on: .main, in: .common).autoconnect()

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 8) {
                Button(action: { withAnimation(.easeInOut(duration: 0.2)) { isExpanded.toggle() } }) {
                    HStack(spacing: 6) {
                        Text(activityTitle)
                            .font(.system(size: 11, weight: .medium))
                            .foregroundColor(activityColor)

                        if let activeToolCall {
                            CompactToolCallBadge(toolCall: activeToolCall)
                        }

                        if let browseNotice {
                            CompactBrowseNoticeBadge(notice: browseNotice)
                        }

                        HStack(spacing: 2) {
                            ForEach(0..<3, id: \.self) { i in
                                Circle()
                                    .fill(activityColor)
                                    .frame(width: 4, height: 4)
                                    .opacity(guarded || isCancelling ? (i == 1 ? 0.9 : 0.35) : (dotPhase == i ? 1.0 : 0.4))
                            }
                        }

                        Text(formattedTime)
                            .font(.system(size: 11, weight: .medium, design: .monospaced))
                            .foregroundColor(activityColor)

                        Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                            .font(.system(size: 8, weight: .semibold))
                            .foregroundColor(activityColor.opacity(0.7))
                    }
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(
                        Capsule()
                            .fill(activityColor.opacity(0.15))
                    )
                }
                .buttonStyle(.plain)

                if canCancel, let onCancel {
                    Button(action: onCancel) {
                        HStack(spacing: 5) {
                            Image(systemName: isCancelling ? "hourglass" : "stop.fill")
                                .font(.system(size: 9, weight: .bold))
                            Text(isCancelling ? "Stopping" : "Stop")
                                .font(.system(size: 11, weight: .semibold))
                        }
                        .foregroundColor(isCancelling ? .textSecondary : .white)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(
                            Capsule()
                                .fill(isCancelling ? Color.warning.opacity(0.18) : Color.statusError.opacity(0.88))
                        )
                    }
                    .buttonStyle(.plain)
                    .disabled(isCancelling)
                }
            }

            if isExpanded {
                VStack(alignment: .leading, spacing: 6) {
                    Text(activityDetail)
                        .font(.caption)
                        .foregroundColor(.textSecondary)
                        .lineLimit(nil)
                        .fixedSize(horizontal: false, vertical: true)

                    HStack(spacing: 8) {
                        Label(activityLabel, systemImage: activitySymbol)
                        Spacer()
                        Text(formattedTime)
                            .font(.system(size: 11, design: .monospaced))
                    }
                    .font(.caption2)
                    .foregroundColor(.textTertiary)

                    if let activeToolCall {
                        HStack(spacing: 8) {
                            Label(toolLine(activeToolCall), systemImage: "hammer")
                                .lineLimit(1)
                            Spacer()
                            Text(activeToolCall.status.badgeText)
                                .font(.caption2.weight(.semibold))
                                .foregroundColor(activityColor)
                        }
                        .font(.caption2)
                        .foregroundColor(.textTertiary)
                    }

                    if let browseNotice {
                        HStack(spacing: 8) {
                            Label(browseNotice.badgeText, systemImage: browseNotice.hasWarnings ? "exclamationmark.triangle.fill" : "globe")
                                .lineLimit(1)
                            Spacer()
                            Text(browseNotice.profile.displayName)
                                .font(.caption2.weight(.semibold))
                                .foregroundColor(browseNoticeColor(for: browseNotice))
                        }
                        .font(.caption2)
                        .foregroundColor(.textTertiary)

                        Text(browseNotice.message)
                            .font(.caption2)
                            .foregroundColor(.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                .padding(10)
                .background(
                    RoundedRectangle(cornerRadius: 8)
                        .fill(Color.cardBackground.opacity(0.8))
                )
                .transition(.opacity.combined(with: .move(edge: .top)))
            }
        }
        .onReceive(timer) { _ in
            guard !guarded, !isCancelling else { return }
            elapsedTime = Date().timeIntervalSince(startTime)
        }
        .onReceive(dotTimer) { _ in
            guard !guarded, !isCancelling else { return }
            dotPhase = (dotPhase + 1) % 3
        }
        .onAppear {
            startTime = Date()
            elapsedTime = guarded ? 0 : 0
        }
        .onChange(of: phaseKey) { _, _ in
            startTime = Date()
            elapsedTime = 0
        }
    }

    private var formattedTime: String {
        if isCancelling {
            return "stopping"
        }
        if guarded {
            return "stable"
        }
        let seconds = elapsedTime
        if seconds < 60 {
            return String(format: "%.1fs", seconds)
        } else {
            let mins = Int(seconds) / 60
            let secs = seconds.truncatingRemainder(dividingBy: 60)
            return String(format: "%d:%04.1f", mins, secs)
        }
    }

    private var activityColor: Color {
        if isCancelling { return .warning }
        switch status {
        case .error: return .statusError
        case .complete: return .statusComplete
        case .streaming: return .statusStreaming
        default: return .statusThinking
        }
    }

    private var activityTitle: String {
        if isCancelling { return "Cancelling" }
        switch status {
        case .planning, .thinking, .executingPlan:
            let trimmed = statusDetail.trimmingCharacters(in: .whitespacesAndNewlines)
            if !trimmed.isEmpty {
                return trimmed.count > 36 ? String(trimmed.prefix(33)) + "..." : trimmed
            }
            if case .planning = status { return "Planning" }
            if case .executingPlan = status { return "Executing" }
            return "Thinking"
        case .callingTool: return "Tooling"
        case .capturingScreen: return "Reading Screen"
        case .streaming: return "Responding"
        case .awaitingApproval: return "Approval"
        case .complete: return "Done"
        case .error: return "Issue"
        default: return "Thinking"
        }
    }

    private var activitySymbol: String {
        switch status {
        case .planning: return "list.bullet.clipboard"
        case .callingTool: return "hammer"
        case .capturingScreen: return "eye"
        case .streaming: return "text.bubble"
        case .awaitingApproval: return "hand.raised"
        case .complete: return "checkmark.circle"
        case .error: return "exclamationmark.triangle"
        default: return "brain"
        }
    }

    private var activityLabel: String {
        if isCancelling { return "Stopping response" }
        switch status {
        case .planning: return "Plan mode active"
        case .callingTool: return "Running a tool"
        case .capturingScreen: return "Reading screen contents"
        case .streaming: return "Sending answer"
        case .awaitingApproval: return "Waiting for approval"
        case .complete: return "Finished"
        case .error: return "Needs attention"
        default: return "Analyzing request"
        }
    }

    private var activityDetail: String {
        if isCancelling {
            return "Cancellation was sent to the backend. Late chunks are suppressed while the active request is stopping."
        }
        let trimmed = statusDetail.trimmingCharacters(in: .whitespacesAndNewlines)
        return !trimmed.isEmpty ? trimmed : activityLabel
    }

    private var phaseKey: String {
        let detailSuffix = statusDetail.trimmingCharacters(in: .whitespacesAndNewlines)
        let base: String
        switch status {
        case .idle: base = "idle"
        case .connecting: base = "connecting"
        case .thinking: base = "thinking"
        case .planning: base = "planning"
        case .planReady: base = "plan_ready"
        case .awaitingApproval: base = "awaiting_approval"
        case .executingPlan: base = "executing_plan"
        case .callingTool(let toolName): base = "calling_tool:\(toolName)"
        case .capturingScreen: base = "capturing_screen"
        case .streaming: base = "streaming"
        case .error(let message): base = "error:\(message)"
        case .complete: base = "complete"
        }
        return detailSuffix.isEmpty ? base : "\(base)|\(detailSuffix)"
    }

    private func toolLine(_ toolCall: ToolCall) -> String {
        switch toolCall.status {
        case .pending: return "Queued: \(toolCall.name)"
        case .executing: return "Running: \(toolCall.name)"
        case .success: return "Finished: \(toolCall.name)"
        case .failed: return "Failed: \(toolCall.name)"
        }
    }

    private func browseNoticeColor(for notice: BrowsePolicyNotice) -> Color {
        notice.hasWarnings ? .warning : .secondaryBlue
    }
}
