//
//  ToolCallCard.swift
//  AIAgentUI
//
//  Created for Personal macOS AI Agent
//  Status: Active - Tool call display component
//

import SwiftUI

/// Displays a tool call with collapsible arguments
struct ToolCallCard: View {
    
    // MARK: - Properties
    
    /// The tool call to display
    let toolCall: ToolCall
    
    /// Whether the arguments are expanded
    @State private var isExpanded: Bool = false
    
    // MARK: - Body
    
    var body: some View {
        VStack(alignment: .leading, spacing: ThemeConstants.spacingS) {
            // Header
            ToolCallHeader(
                toolName: toolCall.name,
                status: toolCall.status,
                isExpanded: $isExpanded
            )
            
            // Arguments (collapsible)
            if isExpanded {
                argumentsView
                    .transition(.asymmetric(
                        insertion: .opacity.combined(with: .move(edge: .top)),
                        removal: .opacity
                    ))
            }
            
            // Result or error
            if let result = toolCall.result {
                resultView(result)
            } else if let error = toolCall.error {
                errorView(error)
            }
        }
        .padding(ThemeConstants.spacingM)
        .background(Color.cardBackground.opacity(0.6))
        .clipShape(RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusSmall))
        .overlay(
            RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusSmall)
                .stroke(statusColor.opacity(0.5), lineWidth: 1)
        )
    }
    
    // MARK: - Subviews
    
    private var argumentsView: some View {
        VStack(alignment: .leading, spacing: ThemeConstants.spacingXS) {
            Text("Arguments")
                .font(.caption.weight(.medium))
                .foregroundColor(.textSecondary)
            
            ForEach(Array(toolCall.arguments.keys.sorted()), id: \.self) { key in
                if let value = toolCall.arguments[key] {
                    ArgumentRow(key: key, value: value)
                }
            }
        }
        .padding(.leading, ThemeConstants.spacingL)
        .padding(.top, ThemeConstants.spacingXS)
    }
    
    private func resultView(_ result: String) -> some View {
        VStack(alignment: .leading, spacing: ThemeConstants.spacingXS) {
            Text("Result")
                .font(.caption.weight(.medium))
                .foregroundColor(.statusComplete)
            
            Text(result)
                .font(.caption)
                .foregroundColor(.textPrimary)
                .textSelection(.enabled)
        }
        .padding(.top, ThemeConstants.spacingS)
    }
    
    private func errorView(_ error: String) -> some View {
        VStack(alignment: .leading, spacing: ThemeConstants.spacingXS) {
            Text("Error")
                .font(.caption.weight(.medium))
                .foregroundColor(.statusError)
            
            Text(error)
                .font(.caption)
                .foregroundColor(.statusError)
                .textSelection(.enabled)
        }
        .padding(.top, ThemeConstants.spacingS)
    }
    
    // MARK: - Computed Properties
    
    private var statusColor: Color {
        switch toolCall.status {
        case .pending: return .statusIdle
        case .executing: return .statusToolCall
        case .success: return .statusComplete
        case .failed: return .statusError
        }
    }
}

// MARK: - Argument Row

/// Displays a single argument key-value pair
struct ArgumentRow: View {
    
    let key: String
    let value: ArgumentValue
    
    var body: some View {
        HStack(alignment: .top, spacing: ThemeConstants.spacingS) {
            Text("\(key):")
                .font(.system(.caption, design: .monospaced))
                .foregroundColor(.textSecondary)
            
            Text(value.displayValue)
                .font(.system(.caption, design: .monospaced))
                .foregroundColor(.textPrimary)
                .textSelection(.enabled)
        }
    }
}

// MARK: - Tool Call Lifecycle Icon

struct ToolCallLifecycleIcon: View {
    let status: ToolCallStatus
    var size: CGFloat = 16

    @State private var isSpinning = false
    @State private var isPulsing = false
    @State private var isSuccessScaled = false
    @State private var failureOffset: CGFloat = 0

    var body: some View {
        ZStack {
            switch status {
            case .pending:
                Circle()
                    .stroke(Color.statusIdle.opacity(0.35), lineWidth: 1.5)
                    .frame(width: size + 8, height: size + 8)
                    .scaleEffect(isPulsing ? 1.15 : 0.82)
                    .opacity(isPulsing ? 0.2 : 0.6)

                Image(systemName: "clock.fill")
                    .font(.system(size: size, weight: .semibold))
                    .foregroundColor(.statusIdle)

            case .executing:
                Image(systemName: "gearshape.2.fill")
                    .font(.system(size: size, weight: .semibold))
                    .foregroundColor(.statusToolCall)
                    .rotationEffect(.degrees(isSpinning ? 360 : 0))

            case .success:
                Image(systemName: "checkmark.circle.fill")
                    .font(.system(size: size + 1, weight: .bold))
                    .foregroundColor(.statusComplete)
                    .scaleEffect(isSuccessScaled ? 1.0 : 0.7)
                    .opacity(isSuccessScaled ? 1 : 0.7)

            case .failed:
                Image(systemName: "xmark.octagon.fill")
                    .font(.system(size: size + 1, weight: .semibold))
                    .foregroundColor(.statusError)
                    .offset(x: failureOffset)
            }
        }
        .frame(width: size + 12, height: size + 12)
        .onAppear {
            applyAnimation(for: status)
        }
        .onChange(of: status) { _, newStatus in
            applyAnimation(for: newStatus)
        }
    }

    private func applyAnimation(for status: ToolCallStatus) {
        switch status {
        case .pending:
            isPulsing = false
            withAnimation(.easeInOut(duration: 0.9).repeatForever(autoreverses: true)) {
                isPulsing = true
            }
            isSpinning = false
            isSuccessScaled = false
            failureOffset = 0
        case .executing:
            isSpinning = false
            withAnimation(.linear(duration: 1.1).repeatForever(autoreverses: false)) {
                isSpinning = true
            }
            isPulsing = false
            isSuccessScaled = false
            failureOffset = 0
        case .success:
            isSuccessScaled = false
            withAnimation(.spring(duration: 0.36, bounce: 0.28)) {
                isSuccessScaled = true
            }
            isSpinning = false
            isPulsing = false
            failureOffset = 0
        case .failed:
            failureOffset = -3
            withAnimation(.easeInOut(duration: 0.07).repeatCount(5, autoreverses: true)) {
                failureOffset = 3
            }
            isSpinning = false
            isPulsing = false
            isSuccessScaled = false
        }
    }
}

// MARK: - Active Tool Call View

/// A larger view for the currently active tool call
struct ActiveToolCallView: View {
    
    let toolCall: ToolCall
    @Binding var isExpanded: Bool
    
    var body: some View {
        VStack(alignment: .leading, spacing: ThemeConstants.spacingS) {
            // Header with animation
            HStack(spacing: ThemeConstants.spacingS) {
                ToolCallLifecycleIcon(status: toolCall.status, size: 14)

                VStack(alignment: .leading, spacing: 2) {
                    Text("\(statusPrefix): \(toolCall.name)")
                        .font(.subheadline.weight(.medium))
                        .foregroundColor(.textPrimary)

                    Text(toolCall.status.badgeText)
                        .font(.caption2.weight(.medium))
                        .foregroundColor(statusColor)
                }
                
                Spacer()
                
                ToggleArrow(isExpanded: $isExpanded, color: statusColor)
            }
            
            // Arguments (collapsible)
            if isExpanded {
                VStack(alignment: .leading, spacing: ThemeConstants.spacingXS) {
                    ForEach(Array(toolCall.arguments.keys.sorted()), id: \.self) { key in
                        if let value = toolCall.arguments[key] {
                            ArgumentRow(key: key, value: value)
                        }
                    }

                    if let result = toolCall.result, toolCall.status == .success {
                        Divider()
                            .padding(.vertical, ThemeConstants.spacingXS)
                        Text(result)
                            .font(.caption)
                            .foregroundColor(.textPrimary)
                            .textSelection(.enabled)
                    }

                    if let error = toolCall.error, toolCall.status == .failed {
                        Divider()
                            .padding(.vertical, ThemeConstants.spacingXS)
                        Text(error)
                            .font(.caption)
                            .foregroundColor(.statusError)
                            .textSelection(.enabled)
                    }
                }
                .padding(.leading, ThemeConstants.spacingL)
                .transition(.asymmetric(
                    insertion: .opacity.combined(with: .move(edge: .top)),
                    removal: .opacity
                ))
            }
        }
        .padding(ThemeConstants.spacingM)
        .glassCard(cornerRadius: ThemeConstants.cornerRadiusSmall)
        .overlay(
            RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusSmall)
                .stroke(statusColor.opacity(0.55), lineWidth: 2)
        )
    }

    private var statusPrefix: String {
        switch toolCall.status {
        case .pending:
            return "Queued"
        case .executing:
            return "Running"
        case .success:
            return "Succeeded"
        case .failed:
            return "Failed"
        }
    }

    private var statusColor: Color {
        switch toolCall.status {
        case .pending:
            return .statusIdle
        case .executing:
            return .statusToolCall
        case .success:
            return .statusComplete
        case .failed:
            return .statusError
        }
    }
}

// MARK: - Tool Call History

/// Displays a list of completed tool calls
struct ToolCallHistory: View {
    
    let toolCalls: [ToolCall]
    
    var body: some View {
        VStack(alignment: .leading, spacing: ThemeConstants.spacingS) {
            Text("Tool Calls")
                .font(.caption.weight(.medium))
                .foregroundColor(.textSecondary)
            
            ForEach(toolCalls) { toolCall in
                ToolCallCard(toolCall: toolCall)
            }
        }
    }
}

// MARK: - Preview

#if DEBUG
struct ToolCallCardPreview: View {
    @State private var isExpanded = true
    
    var body: some View {
        VStack(spacing: ThemeConstants.spacingL) {
            // Pending tool call
            ToolCallCard(toolCall: ToolCall(
                name: "search_files",
                arguments: [
                    "query": .string("Python files"),
                    "path_filter": .string("Documents")
                ],
                status: .pending
            ))
            
            // Executing tool call
            ToolCallCard(toolCall: ToolCall(
                name: "get_metadata",
                arguments: [
                    "path": .string("/Users/test/file.py"),
                    "include_hash": .bool(true)
                ],
                status: .executing
            ))
            
            // Successful tool call
            ToolCallCard(toolCall: ToolCall(
                name: "read_text",
                arguments: [
                    "path": .string("/Users/test/config.json"),
                    "max_bytes": .int(1024)
                ],
                status: .success,
                result: "File contents read successfully"
            ))
            
            // Failed tool call
            ToolCallCard(toolCall: ToolCall(
                name: "open_item",
                arguments: [
                    "path": .string("/nonexistent/file.txt")
                ],
                status: .failed,
                error: "File not found"
            ))
            
            Divider()
            
            // Active tool call view
            ActiveToolCallView(
                toolCall: ToolCall(
                    name: "search_files",
                    arguments: [
                        "query": .string("*.py"),
                        "scope": .string("user_documents")
                    ],
                    status: .executing
                ),
                isExpanded: $isExpanded
            )
        }
        .padding()
        .background(Color.panelBackground)
        .frame(width: 380)
    }
}

struct ToolCallCard_Previews: PreviewProvider {
    static var previews: some View {
        ToolCallCardPreview()
    }
}
#endif
