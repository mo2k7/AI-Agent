//
//  PlanModeConfig.swift
//  AIAgentUI
//
//  Created for Personal macOS AI Agent
//

import SwiftUI

struct PlanModeConfig: ModeConfig {
    let id = "plan"
    let displayName = "Plan"
    let description = "Planning-only mode. Build plans without executing destructive tools."
    let badgeText = "PLAN"
    
    let themeColor: Color = .warning
    let iconName = "list.bullet.clipboard"
    let placeholderText = "What should we plan?"
    
    let welcomeHeadline = "Planning Mode"
    let welcomeDescription = "Describe a goal and I'll create a step-by-step plan before taking action."
    let welcomeSuggestions = [
        (text: "Plan a project migration", icon: "arrow.triangle.branch"),
        (text: "Design a backup strategy", icon: "externaldrive"),
        (text: "Organize my downloads", icon: "folder"),
        (text: "Help me build a workflow", icon: "gearshape.2")
    ]
}
