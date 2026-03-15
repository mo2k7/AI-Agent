//
//  ToggleArrow.swift
//  AIAgentUI
//
//  Created for Personal macOS AI Agent
//  Status: Active - Collapsible section toggle arrow
//

import SwiftUI

/// An animated toggle arrow for collapsible sections
struct ToggleArrow: View {
    
    // MARK: - Properties
    
    /// Whether the section is expanded
    @Binding var isExpanded: Bool
    
    /// Size of the arrow
    var size: CGFloat = 12
    
    /// Color of the arrow
    var color: Color = .textSecondary
    
    // MARK: - Body
    
    var body: some View {
        Image(systemName: "chevron.right")
            .font(.system(size: size, weight: .semibold))
            .foregroundColor(color)
            .rotationEffect(.degrees(isExpanded ? 90 : 0))
            .animation(AnimationConstants.snappy, value: isExpanded)
            .contentShape(Rectangle())
            .onTapGesture {
                isExpanded.toggle()
            }
    }
}

// MARK: - Collapsible Section Header

/// A header for collapsible sections with toggle arrow
struct CollapsibleSectionHeader: View {
    
    // MARK: - Properties
    
    let title: String
    @Binding var isExpanded: Bool
    
    var icon: String? = nil
    var iconColor: Color = .primaryBlue
    
    // MARK: - Body
    
    var body: some View {
        Button(action: { isExpanded.toggle() }) {
            HStack(spacing: ThemeConstants.spacingS) {
                ToggleArrow(isExpanded: $isExpanded)
                
                if let icon = icon {
                    Image(systemName: icon)
                        .font(.system(size: 14))
                        .foregroundColor(iconColor)
                }
                
                Text(title)
                    .font(.subheadline.weight(.medium))
                    .foregroundColor(.textPrimary)
                
                Spacer()
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Collapsible Section

/// A complete collapsible section with header and content
struct CollapsibleSection<Content: View>: View {
    
    // MARK: - Properties
    
    let title: String
    @Binding var isExpanded: Bool
    
    var icon: String? = nil
    var iconColor: Color = .primaryBlue
    
    @ViewBuilder var content: () -> Content
    
    // MARK: - Body
    
    var body: some View {
        VStack(alignment: .leading, spacing: ThemeConstants.spacingS) {
            CollapsibleSectionHeader(
                title: title,
                isExpanded: $isExpanded,
                icon: icon,
                iconColor: iconColor
            )
            
            if isExpanded {
                content()
                    .transition(.asymmetric(
                        insertion: .opacity.combined(with: .move(edge: .top)),
                        removal: .opacity
                    ))
            }
        }
        .animation(AnimationConstants.snappy, value: isExpanded)
    }
}

// MARK: - Tool Call Arrow Header

/// A specialized header for tool call sections
struct ToolCallHeader: View {
    
    let toolName: String
    let status: ToolCallStatus
    @Binding var isExpanded: Bool
    
    var body: some View {
        Button(action: { withAnimation(AnimationConstants.snappy) { isExpanded.toggle() } }) {
            HStack(spacing: ThemeConstants.spacingS) {
                ToggleArrow(isExpanded: $isExpanded, color: statusColor)
                
                Label {
                    Text("Tool Call: \(toolName)")
                        .font(.subheadline.weight(.medium))
                        .foregroundColor(.textPrimary)
                } icon: {
                    ToolCallLifecycleIcon(status: status, size: 10)
                }
                
                Spacer()
                
                // Status badge
                Text(status.badgeText)
                    .font(.caption2)
                    .foregroundColor(.white)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(statusColor)
                    .clipShape(Capsule())
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
    
    private var statusColor: Color {
        switch status {
        case .pending: return .statusIdle
        case .executing: return .statusToolCall
        case .success: return .statusComplete
        case .failed: return .statusError
        }
    }
}

// MARK: - Preview

#if DEBUG
struct ToggleArrowPreview: View {
    @State private var isExpanded1 = false
    @State private var isExpanded2 = true
    @State private var isExpanded3 = false
    @State private var isExpanded4 = true
    
    var body: some View {
        VStack(alignment: .leading, spacing: ThemeConstants.spacingL) {
            // Simple toggle arrow
            HStack {
                Text("Toggle Arrow:")
                ToggleArrow(isExpanded: $isExpanded1)
                Text(isExpanded1 ? "Expanded" : "Collapsed")
                    .foregroundColor(.textSecondary)
            }
            
            Divider()
            
            // Collapsible section
            CollapsibleSection(
                title: "Advanced Settings",
                isExpanded: $isExpanded2,
                icon: "gearshape",
                iconColor: .primaryBlue
            ) {
                VStack(alignment: .leading, spacing: ThemeConstants.spacingS) {
                    Text("Setting 1")
                    Text("Setting 2")
                    Text("Setting 3")
                }
                .padding(.leading, ThemeConstants.spacingL)
                .foregroundColor(.textSecondary)
            }
            
            Divider()
            
            // Tool call headers
            VStack(alignment: .leading, spacing: ThemeConstants.spacingS) {
                ToolCallHeader(
                    toolName: "search_files",
                    status: .pending,
                    isExpanded: $isExpanded3
                )
                
                ToolCallHeader(
                    toolName: "get_metadata",
                    status: .executing,
                    isExpanded: $isExpanded4
                )
                
                if isExpanded4 {
                    Text("path: /Users/test/file.txt")
                        .font(.caption)
                        .foregroundColor(.textSecondary)
                        .padding(.leading, ThemeConstants.spacingL)
                }
            }
        }
        .padding()
        .frame(width: 350)
        .background(Color.panelBackground)
    }
}

struct ToggleArrow_Previews: PreviewProvider {
    static var previews: some View {
        ToggleArrowPreview()
    }
}
#endif
