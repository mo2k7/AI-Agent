//
//  SiriMeshAnimationView.swift
//  AIAgentUI
//
//  Created for Personal macOS AI Agent
//  Status: Active - GPU-accelerated animated border for Document Viewer
//

import SwiftUI

/// A high-performance animated glowing mesh border similar to iOS 18 Siri.
/// Uses `.drawingGroup()` to offload gradient + blur compositing to Metal for 60fps.
struct SiriMeshAnimationView: View {
    let cornerRadius: CGFloat
    let lineWidth: CGFloat
    
    @State private var rotation: Double = 0
    @State private var pulse: CGFloat = 1.0
    
    // Pre-computed Siri-like colors (static to avoid re-allocation)
    private static let siriColors: [Color] = [
        Color(red: 0.29, green: 0.56, blue: 0.89), // Deep Blue
        Color(red: 0.31, green: 0.89, blue: 0.76), // Teal
        Color(red: 0.72, green: 0.45, blue: 0.96), // Purple
        Color(red: 1.00, green: 0.37, blue: 0.58), // Pink
        Color(red: 1.00, green: 0.68, blue: 0.20), // Orange
        Color(red: 0.29, green: 0.56, blue: 0.89)  // Loop back for seamless spin
    ]
    
    var body: some View {
        ZStack {
            // Inner crisp stroke
            RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                .stroke(
                    AngularGradient(
                        gradient: Gradient(colors: Self.siriColors),
                        center: .center,
                        angle: .degrees(rotation)
                    ),
                    lineWidth: lineWidth
                )
            
            // Outer blurred glow
            RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                .stroke(
                    AngularGradient(
                        gradient: Gradient(colors: Self.siriColors),
                        center: .center,
                        angle: .degrees(rotation + 45)
                    ),
                    lineWidth: lineWidth * 3.0
                )
                .blur(radius: 12)
                .opacity(0.85)
        }
        .scaleEffect(pulse)
        // Metal-accelerated compositing: renders gradient+blur offscreen via GPU
        .drawingGroup(opaque: false)
        .onAppear {
            withAnimation(.linear(duration: 5.5).repeatForever(autoreverses: false)) {
                rotation = 360
            }
            withAnimation(.easeInOut(duration: 2.5).repeatForever(autoreverses: true)) {
                pulse = 1.015
            }
        }
    }
}

struct SiriMeshAnimationView_Previews: PreviewProvider {
    static var previews: some View {
        ZStack {
            Color.black.edgesIgnoringSafeArea(.all)
            SiriMeshAnimationView(cornerRadius: 24, lineWidth: 3)
                .frame(width: 300, height: 200)
        }
    }
}
