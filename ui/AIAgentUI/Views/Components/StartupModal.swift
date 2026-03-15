//
//  StartupModal.swift
//  AIAgentUI
//
//  Created for Personal macOS AI Agent
//  Status: Active - Modern startup/initialization modal
//

import SwiftUI

/// Startup phase for UI display
enum StartupPhase: Equatable {
    case initializing
    case startingBackend
    case connectingToBackend
    case performingHealthCheck
    case loadingDiagnostics
    case loadingModels
    case loadingSessions
    case ready
    case failed(String)
    
    var title: String {
        switch self {
        case .initializing:
            return "Initializing"
        case .startingBackend:
            return "Starting AI Engine"
        case .connectingToBackend:
            return "Connecting"
        case .performingHealthCheck:
            return "Verifying"
        case .loadingDiagnostics:
            return "System Check"
        case .loadingModels:
            return "AI Models"
        case .loadingSessions:
            return "Restoring Sync"
        case .ready:
            return "Ready"
        case .failed:
            return "Error"
        }
    }
    
    var subtitle: String {
        switch self {
        case .initializing:
            return "Preparing components..."
        case .startingBackend:
            return "Launching Python backend..."
        case .connectingToBackend:
            return "Establishing connection..."
        case .performingHealthCheck:
            return "Running health checks..."
        case .loadingDiagnostics:
            return "Validating end-to-end setup..."
        case .loadingModels:
            return "Fetching available AI models..."
        case .loadingSessions:
            return "Synchronizing local data..."
        case .ready:
            return "AI Agent is ready!"
        case .failed(let message):
            return message
        }
    }
    
    var symbolName: String {
        switch self {
        case .initializing:
            return "gearshape.2"
        case .startingBackend:
            return "brain"
        case .connectingToBackend:
            return "network"
        case .performingHealthCheck:
            return "stethoscope"
        case .loadingDiagnostics:
            return "cpu"
        case .loadingModels:
            return "sparkles"
        case .loadingSessions:
            return "arrow.triangle.2.circlepath"
        case .ready:
            return "checkmark.circle"
        case .failed:
            return "exclamationmark.triangle"
        }
    }
    
    var color: Color {
        switch self {
        case .initializing, .startingBackend, .connectingToBackend, .performingHealthCheck,
             .loadingDiagnostics, .loadingModels, .loadingSessions:
            return .primaryBlue
        case .ready:
            return .green
        case .failed:
            return .red
        }
    }
    
    var isLoading: Bool {
        switch self {
        case .initializing, .startingBackend, .connectingToBackend, .performingHealthCheck,
             .loadingDiagnostics, .loadingModels, .loadingSessions:
            return true
        case .ready, .failed:
            return false
        }
    }
}

/// Modern startup modal with Liquid Glass styling
struct StartupModal: View {
    let phase: StartupPhase
    var onRetry: (() -> Void)?
    var onQuit: (() -> Void)?
    
    @State private var rotation: Double = 0
    @State private var scale: CGFloat = 1.0
    @State private var opacity: Double = 1.0
    
    var body: some View {
        ZStack {
            // Blurred background
            Color.black.opacity(0.3)
                .ignoresSafeArea()
            
            // Modal card
            VStack(spacing: 24) {
                // Animated icon
                iconView
                
                // Status text
                VStack(spacing: 8) {
                    Text(phase.title)
                        .font(.system(size: 18, weight: .semibold, design: .rounded))
                        .foregroundColor(.primary)
                    
                    Text(phase.subtitle)
                        .font(.system(size: 13, weight: .regular, design: .rounded))
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                        .lineLimit(3)
                }
                
                // Progress indicator (for loading states)
                if phase.isLoading {
                    ProgressView()
                        .progressViewStyle(CircularProgressViewStyle())
                        .scaleEffect(0.8)
                }
                
                // Error actions
                if case .failed = phase {
                    HStack(spacing: 12) {
                        Button(action: { onRetry?() }) {
                            Label("Retry", systemImage: "arrow.clockwise")
                                .font(.system(size: 13, weight: .medium))
                                .foregroundColor(.white)
                                .padding(.horizontal, 16)
                                .padding(.vertical, 8)
                                .background(Color.primaryBlue)
                                .cornerRadius(8)
                        }
                        .buttonStyle(.plain)
                        
                        Button(action: { onQuit?() }) {
                            Text("Quit")
                                .font(.system(size: 13, weight: .medium))
                                .foregroundColor(.secondary)
                                .padding(.horizontal, 16)
                                .padding(.vertical, 8)
                                .background(Color.secondary.opacity(0.2))
                                .cornerRadius(8)
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            .padding(32)
            .frame(width: 280)
            .background(
                RoundedRectangle(cornerRadius: 20)
                    .fill(.ultraThinMaterial)
                    .shadow(color: .black.opacity(0.2), radius: 20, x: 0, y: 10)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 20)
                    .stroke(Color.white.opacity(0.2), lineWidth: 1)
            )
        }
        .animation(AnimationConstants.standard, value: phase)
    }
    
    @ViewBuilder
    private var iconView: some View {
        ZStack {
            // Glow effect
            Circle()
                .fill(phase.color.opacity(0.2))
                .frame(width: 80, height: 80)
                .blur(radius: 10)
            
            // Icon circle
            Circle()
                .fill(
                    LinearGradient(
                        gradient: Gradient(colors: [
                            phase.color.opacity(0.8),
                            phase.color
                        ]),
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
                .frame(width: 60, height: 60)
                .shadow(color: phase.color.opacity(0.5), radius: 10, x: 0, y: 5)
            
            // Icon
            Image(systemName: phase.symbolName)
                .font(.system(size: 24, weight: .medium))
                .foregroundColor(.white)
                .rotationEffect(phase.isLoading ? .degrees(rotation) : .zero)
                .scaleEffect(scale)
        }
        .onAppear {
            if phase.isLoading {
                withAnimation(.linear(duration: 2).repeatForever(autoreverses: false)) {
                    rotation = 360
                }
                withAnimation(AnimationConstants.gentle.repeatForever(autoreverses: true)) {
                    scale = 1.1
                }
            }
        }
        .onChange(of: phase) { _, newPhase in
            if newPhase.isLoading {
                withAnimation(.linear(duration: 2).repeatForever(autoreverses: false)) {
                    rotation = 360
                }
                withAnimation(AnimationConstants.gentle.repeatForever(autoreverses: true)) {
                    scale = 1.1
                }
            } else {
                rotation = 0
                scale = 1.0
            }
        }
    }
}

/// Startup overlay that can be shown over the main content
struct StartupOverlay: View {
    @ObservedObject var appState: AppState
    @ObservedObject var connectionState: ConnectionState = .shared
    
    var body: some View {
        Group {
            switch connectionState.startupPhase {
            case .ready:
                EmptyView()
            default:
                StartupModal(
                    phase: connectionState.startupPhase,
                    onRetry: {
                        Task {
                            await appState.retryStartup()
                        }
                    },
                    onQuit: {
                        PlatformAppActions.terminate()
                    }
                )
                .transition(.opacity.combined(with: .scale(scale: 0.95)))
            }
        }
        .animation(AnimationConstants.standard, value: connectionState.startupPhase)
    }
}

// MARK: - Previews

#if DEBUG
struct StartupModal_Previews: PreviewProvider {
    static var previews: some View {
        Group {
            StartupModal(phase: .initializing)
                .previewDisplayName("Initializing")
            
            StartupModal(phase: .startingBackend)
                .previewDisplayName("Starting Backend")
            
            StartupModal(phase: .connectingToBackend)
                .previewDisplayName("Connecting")
            
            StartupModal(phase: .ready)
                .previewDisplayName("Ready")
            
            StartupModal(
                phase: .failed("Could not find Python environment"),
                onRetry: {},
                onQuit: {}
            )
            .previewDisplayName("Failed")
        }
        .frame(width: 400, height: 400)
        .background(Color.gray)
    }
}
#endif
