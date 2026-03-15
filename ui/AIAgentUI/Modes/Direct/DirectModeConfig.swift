//
//  DirectModeConfig.swift
//  AIAgentUI
//
//  Created for Personal macOS AI Agent
//

import SwiftUI

struct DirectModeConfig: ModeConfig {
    let id = "direct"
    let displayName = "Direct"
    let description = "Execute requests directly with confirmations for destructive actions."
    let badgeText = "DIRECT"
    
    let themeColor: Color = .primaryBlue
    let iconName = "brain"
    let placeholderText = "How can I help you?"
    
    let welcomeHeadline = "Direct Mode"
    let welcomeDescription = "Ask me to search, open apps, summarize files, or automate tasks on your Mac."
    let welcomeSuggestions = [
        (text: "Search my documents", icon: "magnifyingglass"),
        (text: "Open an app", icon: "macwindow"),
        (text: "Summarize a file", icon: "doc.text"),
        (text: "What can you do?", icon: "sparkles")
    ]
}
