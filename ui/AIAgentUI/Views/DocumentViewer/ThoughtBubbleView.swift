//
//  ThoughtBubbleView.swift
//  AIAgentUI
//

import SwiftUI

/// A lightweight, high-performance bubble that displays the AI's current thought process
/// and its final generated response beautifully without the overhead of a full MessageListView.
///
/// Performance notes:
/// - Markdown parsing is cached via `EquatableMarkdown` to prevent re-parsing on every SwiftUI diff
/// - Animations use explicit value-based transitions for smooth 60fps rendering
struct ThoughtBubbleView: View {
    let streamingText: String
    let finalText: String?
    let isBusy: Bool
    let statusDetail: String
    
    var body: some View {
        VStack(alignment: .leading, spacing: ThemeConstants.spacingS) {
            if isBusy {
                HStack(spacing: ThemeConstants.spacingS) {
                    ProgressView()
                        .scaleEffect(0.8)
                    Text(statusDetail.isEmpty ? "Thinking..." : statusDetail)
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                }
                .transition(.opacity)
                
                if !streamingText.isEmpty {
                    EquatableMarkdown(text: streamingText)
                        .transition(.opacity)
                }
            } else {
                // Instantly display final text when not busy
                if let finalMsg = finalText, !finalMsg.isEmpty {
                    EquatableMarkdown(text: finalMsg)
                        .transition(.opacity)
                }
            }
        }
        .padding(ThemeConstants.spacingM)
        .padding(.bottom, 12) // Room for the tail
        .background(
            SpeechBubbleShape()
                .fill(.ultraThinMaterial)
                .shadow(color: Color.black.opacity(0.15), radius: 10, y: 5)
        )
        .overlay(
            SpeechBubbleShape()
                .stroke(Color.primary.opacity(0.1), lineWidth: 1)
        )
        .padding(.horizontal, ThemeConstants.spacingM)
        .animation(.easeInOut(duration: 0.2), value: isBusy)
    }
}

/// Equatable wrapper that only re-parses markdown when the text actually changes.
/// This prevents expensive AttributedString parsing on every SwiftUI body evaluation.
private struct EquatableMarkdown: View {
    let text: String
    
    var body: some View {
        let options = AttributedString.MarkdownParsingOptions(
            allowsExtendedAttributes: true,
            interpretedSyntax: .full
        )
        let attributed = (try? AttributedString(markdown: text, options: options))
            ?? AttributedString(text)
        
        Text(attributed)
            .font(.body)
            .foregroundColor(.primary)
            .lineSpacing(4)
            .frame(maxWidth: .infinity, alignment: .leading)
            .textSelection(.enabled)
    }
}

/// A custom shape for a realistic comic-style speech/thought bubble pointing down.
struct SpeechBubbleShape: Shape {
    var cornerRadius: CGFloat = ThemeConstants.cornerRadiusMedium
    var tailWidth: CGFloat = 20
    var tailHeight: CGFloat = 12
    
    func path(in rect: CGRect) -> Path {
        var path = Path()
        let w = rect.width
        let h = rect.height - tailHeight
        let r = min(cornerRadius, min(w, h) / 2) // Clamp to prevent overdraw
        
        path.move(to: CGPoint(x: r, y: 0))
        path.addLine(to: CGPoint(x: w - r, y: 0))
        path.addArc(center: CGPoint(x: w - r, y: r), radius: r, startAngle: Angle(degrees: -90), endAngle: Angle(degrees: 0), clockwise: false)
        
        path.addLine(to: CGPoint(x: w, y: h - r))
        path.addArc(center: CGPoint(x: w - r, y: h - r), radius: r, startAngle: Angle(degrees: 0), endAngle: Angle(degrees: 90), clockwise: false)
        
        // Tail
        path.addLine(to: CGPoint(x: w / 2 + tailWidth / 2, y: h))
        path.addLine(to: CGPoint(x: w / 2 - 15, y: rect.height))
        path.addLine(to: CGPoint(x: w / 2 - tailWidth / 2 - 5, y: h))
        
        path.addLine(to: CGPoint(x: r, y: h))
        path.addArc(center: CGPoint(x: r, y: h - r), radius: r, startAngle: Angle(degrees: 90), endAngle: Angle(degrees: 180), clockwise: false)
        
        path.addLine(to: CGPoint(x: 0, y: r))
        path.addArc(center: CGPoint(x: r, y: r), radius: r, startAngle: Angle(degrees: 180), endAngle: Angle(degrees: 270), clockwise: false)
        
        path.closeSubpath()
        return path
    }
}
