//
//  HeaderContextTray.swift
//  AIAgentUI
//
//  Created for Personal macOS AI Agent
//  Status: Active - Hover-reveal tray for header badges
//

import SwiftUI

/// A hover-reveal tray that slides down from the header to show
/// execution mode, deep think, and browse profile badges.
struct HeaderContextTray: View {

    @ObservedObject var appState: AppState
    let isVisible: Bool

    var body: some View {
        VStack(spacing: 0) {
            if isVisible {
                AdaptiveBadgeFlow(spacing: 6, rowSpacing: 6) {
                    executionModeBadge
                    deepThinkBadge
                    browseProfileBadge
                }
                .padding(.horizontal, ThemeConstants.spacingM)
                .padding(.top, 2)
                .padding(.bottom, 8)
                .background(
                    LinearGradient(
                        colors: [
                            Color.white.opacity(0.02),
                            Color.clear,
                        ],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                )
                .transition(.asymmetric(
                    insertion: .opacity.combined(with: .move(edge: .top)),
                    removal: .opacity
                ))
            }
        }
        .clipped()
        .animation(AnimationConstants.snappy, value: isVisible)
    }

    // MARK: - Badges

    private var executionModeBadge: some View {
        Text(appState.executionMode.badgeText)
            .font(.caption2.monospaced())
            .fontWeight(.semibold)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(
                RoundedRectangle(cornerRadius: 5)
                    .fill(executionModeBadgeBackground)
            )
            .foregroundColor(executionModeBadgeForeground)
    }

    private var executionModeBadgeForeground: Color {
        appState.executionMode.config.themeColor
    }

    private var executionModeBadgeBackground: Color {
        appState.executionMode.config.themeColor.opacity(0.2)
    }

    private var deepThinkBadge: some View {
        HStack(spacing: 4) {
            Image(systemName: "brain")
                .font(.system(size: 10, weight: .semibold))
            Text(appState.deepThinkEnabled ? "DEEP THINK ON" : "DEEP THINK OFF")
                .font(.caption2.monospaced())
                .fontWeight(.semibold)
        }
        .padding(.horizontal, 6)
        .padding(.vertical, 2)
        .background(
            RoundedRectangle(cornerRadius: 5)
                .fill(deepThinkBadgeBackground)
        )
        .foregroundColor(deepThinkBadgeForeground)
    }

    private var deepThinkBadgeForeground: Color {
        appState.deepThinkEnabled ? .statusThinking : .textTertiary
    }

    private var deepThinkBadgeBackground: Color {
        appState.deepThinkEnabled ? Color.statusThinking.opacity(0.15) : Color.cardBackground.opacity(0.55)
    }

    private var browseProfileBadge: some View {
        HStack(spacing: 4) {
            Image(systemName: "globe")
                .font(.system(size: 10, weight: .semibold))
            Text("WEB \(appState.browseRestrictionProfile.displayName.uppercased())")
                .font(.caption2.monospaced())
                .fontWeight(.semibold)
        }
        .padding(.horizontal, 6)
        .padding(.vertical, 2)
        .background(
            RoundedRectangle(cornerRadius: 5)
                .fill(browseProfileBadgeBackground)
        )
        .foregroundColor(browseProfileBadgeForeground)
    }

    private var browseProfileBadgeForeground: Color {
        switch appState.browseRestrictionProfile {
        case .strict: return .textSecondary
        case .standard: return .secondaryBlue
        case .flexible: return .warning
        }
    }

    private var browseProfileBadgeBackground: Color {
        switch appState.browseRestrictionProfile {
        case .strict: return Color.cardBackground.opacity(0.55)
        case .standard: return Color.secondaryBlue.opacity(0.16)
        case .flexible: return Color.warning.opacity(0.16)
        }
    }
}

private struct AdaptiveBadgeFlow: Layout {
    var spacing: CGFloat = 6
    var rowSpacing: CGFloat = 6

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let maxWidth = proposal.width ?? .greatestFiniteMagnitude
        var currentRowWidth: CGFloat = 0
        var currentRowHeight: CGFloat = 0
        var totalHeight: CGFloat = 0
        var maxRowWidth: CGFloat = 0

        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            let proposedRowWidth = currentRowWidth == 0 ? size.width : currentRowWidth + spacing + size.width
            if proposedRowWidth > maxWidth && currentRowWidth > 0 {
                totalHeight += currentRowHeight + rowSpacing
                maxRowWidth = max(maxRowWidth, currentRowWidth)
                currentRowWidth = size.width
                currentRowHeight = size.height
            } else {
                currentRowWidth = proposedRowWidth
                currentRowHeight = max(currentRowHeight, size.height)
            }
        }

        totalHeight += currentRowHeight
        maxRowWidth = max(maxRowWidth, currentRowWidth)
        return CGSize(width: min(maxWidth, maxRowWidth), height: totalHeight)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var x = bounds.minX
        var y = bounds.minY
        var rowHeight: CGFloat = 0

        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            let nextX = x == bounds.minX ? x + size.width : x + spacing + size.width
            if nextX > bounds.maxX && x > bounds.minX {
                x = bounds.minX
                y += rowHeight + rowSpacing
                rowHeight = 0
            }

            if x > bounds.minX {
                x += spacing
            }

            subview.place(
                at: CGPoint(x: x, y: y),
                anchor: .topLeading,
                proposal: ProposedViewSize(size)
            )

            x += size.width
            rowHeight = max(rowHeight, size.height)
        }
    }
}

// MARK: - Preview

#if DEBUG
struct HeaderContextTray_Previews: PreviewProvider {
    static var previews: some View {
        VStack {
            HeaderContextTray(appState: AppState.shared, isVisible: true)
        }
        .frame(width: 400)
        .background(Color.panelBackground)
    }
}
#endif
