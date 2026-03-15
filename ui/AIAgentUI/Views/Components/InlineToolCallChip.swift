//
//  InlineToolCallChip.swift
//  AIAgentUI
//
//  Created for Personal macOS AI Agent
//  Status: Active - Compact inline tool call indicator for conversation flow
//

import SwiftUI

/// Compact capsule that shows a tool call inline within an assistant message.
/// Expandable on click to show arguments and results.
struct InlineToolCallChip: View {

    let toolCall: ToolCall
    @State private var isExpanded = false

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Compact chip
            Button(action: { withAnimation(AnimationConstants.snappy) { isExpanded.toggle() } }) {
                HStack(spacing: 5) {
                    ToolCallLifecycleIcon(status: toolCall.status, size: 10)

                    Text(toolCall.name)
                        .font(.caption2.weight(.medium))
                        .foregroundColor(chipTextColor)
                        .lineLimit(1)

                    if toolCall.status == .success {
                        Image(systemName: "checkmark")
                            .font(.system(size: 8, weight: .bold))
                            .foregroundColor(.statusComplete)
                    } else if toolCall.status == .failed {
                        Image(systemName: "xmark")
                            .font(.system(size: 8, weight: .bold))
                            .foregroundColor(.statusError)
                    }

                    Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                        .font(.system(size: 7, weight: .semibold))
                        .foregroundColor(.textTertiary)
                }
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(
                    Capsule()
                        .fill(chipBackgroundColor)
                )
                .overlay(
                    Capsule()
                        .stroke(chipBorderColor, lineWidth: 0.5)
                )
            }
            .buttonStyle(.plain)

            // Expanded details
            if isExpanded {
                VStack(alignment: .leading, spacing: ThemeConstants.spacingXS) {
                    if !toolCall.arguments.isEmpty {
                        Text("Arguments")
                            .font(.caption2.weight(.medium))
                            .foregroundColor(.textSecondary)
                            .padding(.top, ThemeConstants.spacingXS)

                        ForEach(Array(toolCall.arguments.keys.sorted()), id: \.self) { key in
                            if let value = toolCall.arguments[key] {
                                ArgumentRow(key: key, value: value)
                            }
                        }
                    }

                    if let result = toolCall.result, toolCall.status == .success {
                        Text("Result")
                            .font(.caption2.weight(.medium))
                            .foregroundColor(.statusComplete)
                            .padding(.top, 2)
                        Text(result)
                            .font(.caption2)
                            .foregroundColor(.textPrimary)
                            .textSelection(.enabled)
                            .lineLimit(6)
                    }

                    if let error = toolCall.error, toolCall.status == .failed {
                        Text("Error")
                            .font(.caption2.weight(.medium))
                            .foregroundColor(.statusError)
                            .padding(.top, 2)
                        Text(error)
                            .font(.caption2)
                            .foregroundColor(.statusError)
                            .textSelection(.enabled)
                            .lineLimit(4)
                    }
                }
                .padding(.horizontal, ThemeConstants.spacingS)
                .padding(.vertical, ThemeConstants.spacingXS)
                .glassCard(cornerRadius: ThemeConstants.cornerRadiusSmall, padding: ThemeConstants.spacingXS)
                .transition(.asymmetric(
                    insertion: .opacity.combined(with: .move(edge: .top)),
                    removal: .opacity
                ))
            }
        }
    }

    // MARK: - Styling

    private var chipTextColor: Color {
        switch toolCall.status {
        case .pending: return .textSecondary
        case .executing: return .statusToolCall
        case .success: return .textPrimary
        case .failed: return .statusError
        }
    }

    private var chipBackgroundColor: Color {
        switch toolCall.status {
        case .pending: return Color.statusIdle.opacity(0.08)
        case .executing: return Color.statusToolCall.opacity(0.1)
        case .success: return Color.statusComplete.opacity(0.08)
        case .failed: return Color.statusError.opacity(0.08)
        }
    }

    private var chipBorderColor: Color {
        switch toolCall.status {
        case .pending: return Color.statusIdle.opacity(0.2)
        case .executing: return Color.statusToolCall.opacity(0.3)
        case .success: return Color.statusComplete.opacity(0.2)
        case .failed: return Color.statusError.opacity(0.3)
        }
    }
}

// MARK: - Preview

#if DEBUG
struct InlineToolCallChip_Previews: PreviewProvider {
    static var previews: some View {
        VStack(spacing: 12) {
            InlineToolCallChip(toolCall: ToolCall(
                name: "search_files",
                arguments: ["query": .string("*.py")],
                status: .executing
            ))
            InlineToolCallChip(toolCall: ToolCall(
                name: "read_text",
                arguments: ["path": .string("/Users/test/file.py")],
                status: .success,
                result: "File read successfully"
            ))
            InlineToolCallChip(toolCall: ToolCall(
                name: "open_item",
                arguments: ["path": .string("/bad/path")],
                status: .failed,
                error: "File not found"
            ))
        }
        .padding()
        .background(Color.panelBackground)
    }
}
#endif
