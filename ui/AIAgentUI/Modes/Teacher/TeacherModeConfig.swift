//
//  TeacherModeConfig.swift
//  AIAgentUI
//
//  Created for Personal macOS AI Agent
//

import SwiftUI

struct TeacherModeConfig: ModeConfig {
    let id = "teacher"
    let displayName = "Teacher"
    let description = "Teaches interactively while autonomously capturing structured study notes and highlights."
    let badgeText = "TEACHER"
    
    let themeColor: Color = .success
    let iconName = "graduationcap"
    let placeholderText = "What would you like to learn?"
    
    let welcomeHeadline = "Teacher Mode"
    let welcomeDescription = "Ask questions and I'll explain concepts, create study notes, and quiz you."
    let welcomeSuggestions = [
        (text: "Explain quantum computing", icon: "atom"),
        (text: "Quiz me on Python", icon: "questionmark.circle"),
        (text: "Teach me about Swift concurrency", icon: "swift"),
        (text: "Create study notes on ML", icon: "note.text")
    ]
}
