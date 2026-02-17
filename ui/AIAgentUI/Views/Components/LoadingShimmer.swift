//
//  LoadingShimmer.swift
//  AIAgentUI
//
//  Created for Personal macOS AI Agent
//  Status: Active - Loading shimmer placeholder
//

import SwiftUI

/// Animated shimmer placeholder for loading text blocks
struct LoadingShimmer: View {
    
    var lineCount: Int = 2
    var lineHeight: CGFloat = 10
    var cornerRadius: CGFloat = 4
    
    @State private var shimmerOffset: CGFloat = -1
    
    var body: some View {
        VStack(alignment: .leading, spacing: ThemeConstants.spacingS) {
            ForEach(0..<lineCount, id: \.self) { index in
                RoundedRectangle(cornerRadius: cornerRadius)
                    .fill(Color.textTertiary.opacity(0.2))
                    .overlay(
                        GeometryReader { geometry in
                            LinearGradient(
                                colors: [
                                    Color.clear,
                                    Color.white.opacity(0.4),
                                    Color.clear
                                ],
                                startPoint: .leading,
                                endPoint: .trailing
                            )
                            .frame(width: geometry.size.width * 0.6)
                            .offset(x: shimmerOffset * geometry.size.width)
                        }
                        .clipShape(RoundedRectangle(cornerRadius: cornerRadius))
                    )
                    .frame(height: lineHeight)
                    .frame(maxWidth: index == lineCount - 1 ? 180 : .infinity, alignment: .leading)
            }
        }
        .accessibilityHidden(true)
        .onAppear {
            shimmerOffset = -1
            withAnimation(.linear(duration: 1.4).repeatForever(autoreverses: false)) {
                shimmerOffset = 1
            }
        }
    }
}

#if DEBUG
struct LoadingShimmer_Previews: PreviewProvider {
    static var previews: some View {
        LoadingShimmer()
            .padding()
            .background(Color.panelBackground)
            .frame(width: 300)
    }
}
#endif
