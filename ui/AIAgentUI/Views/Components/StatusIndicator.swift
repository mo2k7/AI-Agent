//
//  StatusIndicator.swift
//  AIAgentUI
//
//  Created for Personal macOS AI Agent
//  Status: Active - Status display component
//

import SwiftUI

/// Displays the current agent status with animated indicators
struct StatusIndicator: View {
    
    // MARK: - Properties
    
    /// The current agent status
    let status: AgentStatus
    
    /// Size of the indicator
    var size: IndicatorSize = .medium
    
    // MARK: - Body
    
    var body: some View {
        if status.showsIndicator {
            HStack(spacing: ThemeConstants.spacingS) {
                statusIcon
                
                if !status.displayText.isEmpty {
                    Text(status.displayText)
                        .font(size.font)
                        .foregroundColor(statusColor)
                }
            }
            .padding(.horizontal, ThemeConstants.spacingM)
            .padding(.vertical, ThemeConstants.spacingS)
            .glassCard(cornerRadius: ThemeConstants.cornerRadiusSmall, padding: 0)
            .padding(ThemeConstants.spacingS)
        }
    }
    
    // MARK: - Status Icon
    
    @ViewBuilder
    private var statusIcon: some View {
        switch status {
        case .connecting:
            ConnectingIndicator(size: size)
            
        case .thinking:
            ThinkingIndicator(size: size)

        case .planning:
            PlanningIndicator(size: size)

        case .planReady:
            PlanReadyIndicator(size: size)

        case .awaitingApproval:
            AwaitingApprovalIndicator(size: size)

        case .executingPlan:
            ExecutingPlanIndicator(size: size)
            
        case .callingTool(let toolName):
            ToolCallIndicator(toolName: toolName, size: size)

        case .capturingScreen:
            ThinkingIndicator(size: size)

        case .streaming:
            StreamingIndicator(size: size)
            
        case .error:
            ErrorIndicator(size: size)
            
        case .complete:
            CompleteIndicator(size: size)
            
        default:
            EmptyView()
        }
    }
    
    // MARK: - Status Color
    
    private var statusColor: Color {
        switch status {
        case .idle: return .statusIdle
        case .connecting: return .statusConnecting
        case .thinking: return .statusThinking
        case .planning: return .statusThinking
        case .planReady: return .statusComplete
        case .awaitingApproval: return .statusToolCall
        case .executingPlan: return .statusToolCall
        case .callingTool: return .statusToolCall
        case .capturingScreen: return .statusToolCall
        case .streaming: return .statusStreaming
        case .error: return .statusError
        case .complete: return .statusComplete
        }
    }
    
    // MARK: - Size
    
    enum IndicatorSize {
        case small
        case medium
        case large
        
        var iconSize: CGFloat {
            switch self {
            case .small: return 12
            case .medium: return 16
            case .large: return 24
            }
        }
        
        var font: Font {
            switch self {
            case .small: return .caption2
            case .medium: return .caption
            case .large: return .body
            }
        }
    }
}

// MARK: - Planning Indicator

struct PlanningIndicator: View {
    var size: StatusIndicator.IndicatorSize = .medium
    @State private var isAnimating = false

    var body: some View {
        Image(systemName: "list.bullet.clipboard")
            .font(.system(size: size.iconSize))
            .foregroundColor(.statusThinking)
            .rotationEffect(.degrees(isAnimating ? 6 : -6))
            .animation(
                AnimationConstants.standard
                    .repeatForever(autoreverses: true),
                value: isAnimating
            )
            .onAppear { isAnimating = true }
            .onDisappear { isAnimating = false }
    }
}

// MARK: - Plan Ready Indicator

struct PlanReadyIndicator: View {
    var size: StatusIndicator.IndicatorSize = .medium

    var body: some View {
        Image(systemName: "list.clipboard.fill")
            .font(.system(size: size.iconSize))
            .foregroundColor(.statusComplete)
    }
}

// MARK: - Awaiting Approval Indicator

struct AwaitingApprovalIndicator: View {
    var size: StatusIndicator.IndicatorSize = .medium
    @State private var isAnimating = false

    var body: some View {
        Image(systemName: "hand.raised.fill")
            .font(.system(size: size.iconSize))
            .foregroundColor(.statusToolCall)
            .opacity(isAnimating ? 1.0 : 0.55)
            .animation(
                AnimationConstants.gentle
                    .repeatForever(autoreverses: true),
                value: isAnimating
            )
            .onAppear { isAnimating = true }
            .onDisappear { isAnimating = false }
    }
}

// MARK: - Executing Plan Indicator

struct ExecutingPlanIndicator: View {
    var size: StatusIndicator.IndicatorSize = .medium
    @State private var isAnimating = false

    var body: some View {
        Image(systemName: "checklist.unchecked")
            .font(.system(size: size.iconSize))
            .foregroundColor(.statusToolCall)
            .rotationEffect(.degrees(isAnimating ? 12 : -12))
            .animation(
                AnimationConstants.standard
                    .repeatForever(autoreverses: true),
                value: isAnimating
            )
            .onAppear { isAnimating = true }
            .onDisappear { isAnimating = false }
    }
}

// MARK: - Thinking Indicator

/// Animated thinking indicator with pulsing brain icon
struct ThinkingIndicator: View {
    
    var size: StatusIndicator.IndicatorSize = .medium
    
    @State private var isAnimating = false
    
    var body: some View {
        Image(systemName: "brain")
            .font(.system(size: size.iconSize))
            .foregroundColor(.statusThinking)
            .scaleEffect(isAnimating ? 1.15 : 1.0)
            .opacity(isAnimating ? 1.0 : 0.7)
            .animation(
                AnimationConstants.gentle
                    .repeatForever(autoreverses: true),
                value: isAnimating
            )
            .onAppear { isAnimating = true }
            .onDisappear { isAnimating = false }
    }
}

// MARK: - Connecting Indicator

/// Animated connecting indicator with spinning network icon
struct ConnectingIndicator: View {
    
    var size: StatusIndicator.IndicatorSize = .medium
    
    @State private var isAnimating = false
    
    var body: some View {
        Image(systemName: "network")
            .font(.system(size: size.iconSize))
            .foregroundColor(.statusConnecting)
            .rotationEffect(.degrees(isAnimating ? 360 : 0))
            .animation(
                .linear(duration: 2.0)
                .repeatForever(autoreverses: false),
                value: isAnimating
            )
            .onAppear { isAnimating = true }
            .onDisappear { isAnimating = false }
    }
}

// MARK: - Tool Call Indicator

/// Animated tool call indicator
struct ToolCallIndicator: View {
    
    var toolName: String
    var size: StatusIndicator.IndicatorSize = .medium
    
    @State private var isAnimating = false
    
    var body: some View {
        HStack(spacing: ThemeConstants.spacingXS) {
            Image(systemName: "wrench.and.screwdriver")
                .font(.system(size: size.iconSize))
                .foregroundColor(.statusToolCall)
                .rotationEffect(.degrees(isAnimating ? 15 : -15))
                .animation(
                    AnimationConstants.standard
                        .repeatForever(autoreverses: true),
                    value: isAnimating
                )
            
            Text(toolName)
                .font(size.font)
                .foregroundColor(.statusToolCall)
        }
        .onAppear { isAnimating = true }
        .onDisappear { isAnimating = false }
    }
}

// MARK: - Streaming Indicator

/// Animated streaming indicator with typing dots
struct StreamingIndicator: View {
    
    var size: StatusIndicator.IndicatorSize = .medium
    
    @State private var currentDot = 0
    
    private let timer = Timer.publish(every: 0.3, on: .main, in: .common).autoconnect()
    
    var body: some View {
        HStack(spacing: 2) {
            ForEach(0..<3, id: \.self) { index in
                Circle()
                    .fill(Color.statusStreaming)
                    .frame(width: dotSize, height: dotSize)
                    .opacity(currentDot == index ? 1.0 : 0.3)
            }
        }
        .onReceive(timer) { _ in
            currentDot = (currentDot + 1) % 3
        }
    }
    
    private var dotSize: CGFloat {
        switch size {
        case .small: return 4
        case .medium: return 6
        case .large: return 8
        }
    }
}

// MARK: - Error Indicator

/// Error indicator
struct ErrorIndicator: View {
    
    var size: StatusIndicator.IndicatorSize = .medium
    
    @State private var isAnimating = false
    
    var body: some View {
        Image(systemName: "exclamationmark.triangle.fill")
            .font(.system(size: size.iconSize))
            .foregroundColor(.statusError)
            .scaleEffect(isAnimating ? 1.1 : 1.0)
            .animation(
                AnimationConstants.fast
                    .repeatCount(3, autoreverses: true),
                value: isAnimating
            )
            .onAppear {
                isAnimating = true
            }
    }
}

// MARK: - Complete Indicator

/// Completion indicator with checkmark
struct CompleteIndicator: View {
    
    var size: StatusIndicator.IndicatorSize = .medium
    
    @State private var scale: CGFloat = 0.5
    @State private var opacity: CGFloat = 0
    
    var body: some View {
        Image(systemName: "checkmark.circle.fill")
            .font(.system(size: size.iconSize))
            .foregroundColor(.statusComplete)
            .scaleEffect(scale)
            .opacity(opacity)
            .onAppear {
                withAnimation(AnimationConstants.snappy) {
                    scale = 1.0
                    opacity = 1.0
                }
            }
    }
}

// MARK: - Header Status Indicator

/// Compact status indicator for header with live timer
struct HeaderStatusIndicator: View {
    
    let status: AgentStatus
    
    @State private var elapsedTime: TimeInterval = 0
    @State private var startTime: Date = Date()
    
    private let timer = Timer.publish(every: 0.1, on: .main, in: .common).autoconnect()
    
    var body: some View {
        HStack(spacing: 6) {
            // Animated icon based on status — smooth symbol transitions
            statusIcon
                .contentTransition(.symbolEffect(.replace))

            // Timer (only for thinking/processing states)
            if status.isBusy {
                Text(formattedTime)
                    .font(.system(size: 11, weight: .medium, design: .monospaced))
                    .foregroundColor(statusColor.opacity(0.9))
                    .contentTransition(.numericText())
            }
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(
            RoundedRectangle(cornerRadius: 6)
                .fill(statusColor.opacity(0.15))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 6)
                .stroke(statusColor.opacity(0.3), lineWidth: 1)
        )
        .onReceive(timer) { _ in
            if status.isBusy {
                elapsedTime = Date().timeIntervalSince(startTime)
            }
        }
        .onAppear {
            startTime = Date()
            elapsedTime = 0
        }
        .onChange(of: status) { oldValue, newValue in
            // Reset timer when status changes to a new busy state
            if newValue.isBusy && !oldValue.isBusy {
                startTime = Date()
                elapsedTime = 0
            }
        }
    }
    
    private var formattedTime: String {
        let seconds = elapsedTime
        if seconds < 60 {
            return String(format: "%.1fs", seconds)
        } else {
            let mins = Int(seconds) / 60
            let secs = seconds.truncatingRemainder(dividingBy: 60)
            return String(format: "%d:%04.1f", mins, secs)
        }
    }
    
    @ViewBuilder
    private var statusIcon: some View {
        switch status {
        case .thinking:
            ThinkingDots()
        case .planning:
            Image(systemName: "list.bullet.clipboard")
                .font(.system(size: 10))
                .foregroundColor(statusColor)
        case .planReady:
            Image(systemName: "list.clipboard.fill")
                .font(.system(size: 10))
                .foregroundColor(statusColor)
        case .awaitingApproval:
            Image(systemName: "hand.raised.fill")
                .font(.system(size: 10))
                .foregroundColor(statusColor)
        case .executingPlan:
            Image(systemName: "checklist.unchecked")
                .font(.system(size: 10))
                .foregroundColor(statusColor)
        case .connecting:
            Image(systemName: "network")
                .font(.system(size: 10))
                .foregroundColor(statusColor)
        case .callingTool(let toolName):
            HStack(spacing: 3) {
                Image(systemName: "wrench.fill")
                    .font(.system(size: 9))
                Text(toolName)
                    .font(.system(size: 10, weight: .medium))
            }
            .foregroundColor(statusColor)
        case .streaming:
            StreamingDots()
        case .error:
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 10))
                .foregroundColor(statusColor)
        default:
            EmptyView()
        }
    }
    
    private var statusColor: Color {
        switch status {
        case .idle: return .statusIdle
        case .connecting: return .statusConnecting
        case .thinking: return .statusThinking
        case .planning: return .statusThinking
        case .planReady: return .statusComplete
        case .awaitingApproval: return .statusToolCall
        case .executingPlan: return .statusToolCall
        case .callingTool: return .statusToolCall
        case .capturingScreen: return .statusToolCall
        case .streaming: return .statusStreaming
        case .error: return .statusError
        case .complete: return .statusComplete
        }
    }
}

/// Animated thinking dots for header
private struct ThinkingDots: View {
    @State private var phase = 0
    private let timer = Timer.publish(every: 0.4, on: .main, in: .common).autoconnect()
    
    var body: some View {
        HStack(spacing: 2) {
            ForEach(0..<3, id: \.self) { i in
                Circle()
                    .fill(Color.statusThinking)
                    .frame(width: 4, height: 4)
                    .opacity(phase == i ? 1.0 : 0.3)
            }
        }
        .onReceive(timer) { _ in
            phase = (phase + 1) % 3
        }
    }
}

/// Animated streaming dots for header
private struct StreamingDots: View {
    @State private var offset: CGFloat = 0
    
    var body: some View {
        HStack(spacing: 1) {
            ForEach(0..<3, id: \.self) { i in
                Circle()
                    .fill(Color.statusStreaming)
                    .frame(width: 3, height: 3)
                    .offset(y: offset == CGFloat(i) ? -2 : 0)
            }
        }
        .onAppear {
            withAnimation(.easeInOut(duration: 0.3).repeatForever(autoreverses: true)) {
                offset = 2
            }
        }
    }
}

// MARK: - Inline Status View

/// A compact inline status view for use in headers
struct InlineStatusView: View {
    
    let status: AgentStatus
    let isConnected: Bool
    
    var body: some View {
        HStack(spacing: ThemeConstants.spacingXS) {
            // Connection indicator
            Circle()
                .fill(isConnected ? Color.statusComplete : Color.statusError)
                .frame(width: 8, height: 8)
            
            // Status text
            if status.showsIndicator {
                StatusIndicator(status: status, size: .small)
            }
        }
    }
}

// MARK: - Preview

#if DEBUG
struct StatusIndicatorPreview: View {
    var body: some View {
        VStack(spacing: ThemeConstants.spacingL) {
            Group {
                StatusIndicator(status: .connecting)
                StatusIndicator(status: .thinking)
                StatusIndicator(status: .callingTool(toolName: "search_files"))
                StatusIndicator(status: .streaming)
                StatusIndicator(status: .error(message: "Connection lost"))
                StatusIndicator(status: .complete)
            }
            
            Divider()
            
            // Sizes
            HStack(spacing: ThemeConstants.spacingL) {
                VStack {
                    Text("Small").font(.caption2)
                    ThinkingIndicator(size: .small)
                }
                VStack {
                    Text("Medium").font(.caption2)
                    ThinkingIndicator(size: .medium)
                }
                VStack {
                    Text("Large").font(.caption2)
                    ThinkingIndicator(size: .large)
                }
            }
            
            Divider()
            
            // Inline status
            InlineStatusView(status: .thinking, isConnected: true)
            InlineStatusView(status: .idle, isConnected: false)
        }
        .padding()
        .frame(width: 400)
        .background(Color.panelBackground)
    }
}

struct StatusIndicator_Previews: PreviewProvider {
    static var previews: some View {
        StatusIndicatorPreview()
    }
}
#endif
