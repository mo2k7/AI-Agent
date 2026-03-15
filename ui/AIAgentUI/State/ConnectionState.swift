//
//  ConnectionState.swift
//  AIAgentUI
//

import SwiftUI
import Combine

@MainActor
final class ConnectionState: ObservableObject {
    static let shared = ConnectionState()

    /// Current startup phase
    @Published var startupPhase: StartupPhase = .initializing
    
    /// Whether the app is currently connected to the backend
    @Published var isConnected: Bool = false
    
    /// Registered device manifest for capability negotiation.
    @Published var deviceBridgeManifest: DeviceBridgeManifest = .current()
    
    /// Backend-acknowledged capability registration snapshot.
    @Published var registeredDevice: IPCRegisteredDevice?

    private init() {}
}
