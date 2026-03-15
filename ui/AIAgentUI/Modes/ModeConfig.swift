//
//  ModeConfig.swift
//  AIAgentUI
//
//  Created for Personal macOS AI Agent
//

import SwiftUI

/// A protocol encapsulating the visual, behavioral, and textual properties of an execution mode.
protocol ModeConfig {
    var id: String { get }
    var displayName: String { get }
    var description: String { get }
    var badgeText: String { get }
    
    var themeColor: Color { get }
    var iconName: String { get }
    var placeholderText: String { get }
    
    var welcomeHeadline: String { get }
    var welcomeDescription: String { get }
    var welcomeSuggestions: [(text: String, icon: String)] { get }
}
