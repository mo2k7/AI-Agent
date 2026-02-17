//
//  PreviewData.swift
//  AIAgentUI
//
//  Created for Personal macOS AI Agent
//  Status: Active - Preview helpers for SwiftUI Canvas
//

import SwiftUI

#if DEBUG

// MARK: - Preview Providers

/// Provides sample messages for previews
enum PreviewMessages {
    
    /// Sample user message
    static let userMessage = Message.user("Find all Python files in my Documents folder")
    
    /// Sample assistant response
    static let assistantMessage = Message.assistant(
        """
        I found 15 Python files in your Documents folder:
        
        • main.py
        • config.py
        • utils.py
        • test_api.py
        • data_processor.py
        
        Would you like me to open any of these files?
        """
    )
    
    /// Sample streaming message
    static let streamingMessage = Message(
        role: .assistant,
        content: "Searching your files...",
        isStreaming: true
    )
    
    /// Sample conversation
    static let conversation: [Message] = [
        userMessage,
        assistantMessage,
        Message.user("Yes, open main.py"),
        Message(
            role: .assistant,
            content: "I've opened main.py in your default editor.",
            toolCall: sampleToolCall
        )
    ]
    
    /// Long conversation for scroll testing
    static let longConversation: [Message] = [
        Message.user("What time is it?"),
        Message.assistant("The current time is 3:42 PM."),
        Message.user("Search for all images in Downloads"),
        Message(
            role: .assistant,
            content: "Found 47 images in Downloads.",
            toolCall: ToolCall(
                name: "search_files",
                arguments: [
                    "query": .string("*.{jpg,png,gif,jpeg}"),
                    "path_filter": .string("~/Downloads")
                ],
                status: .success,
                result: "47 files found"
            )
        ),
        Message.user("How many are PNG files?"),
        Message.assistant("There are 23 PNG files out of the 47 total images."),
        userMessage,
        assistantMessage
    ]
}

// MARK: - Sample Tool Calls

extension PreviewMessages {
    
    /// Sample completed tool call
    static let sampleToolCall = ToolCall(
        name: "open_item",
        arguments: [
            "path": .string("/Users/test/Documents/main.py")
        ],
        status: .success,
        result: "File opened successfully"
    )
    
    /// Sample pending tool call
    static let pendingToolCall = ToolCall(
        name: "search_files",
        arguments: [
            "query": .string("*.py"),
            "path_filter": .string("Documents")
        ],
        status: .pending
    )
    
    /// Sample executing tool call
    static let executingToolCall = ToolCall(
        name: "get_metadata",
        arguments: [
            "path": .string("/Users/test/file.txt"),
            "include_hash": .bool(true)
        ],
        status: .executing
    )
    
    /// Sample failed tool call
    static let failedToolCall = ToolCall(
        name: "read_text",
        arguments: [
            "path": .string("/nonexistent/file.txt")
        ],
        status: .failed,
        error: "File not found: /nonexistent/file.txt"
    )
}

// MARK: - Preview Container

/// A container view for previewing components with consistent styling
struct PreviewContainer<Content: View>: View {
    
    let title: String
    var width: CGFloat = 400
    var height: CGFloat? = nil
    @ViewBuilder var content: () -> Content
    
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Title bar
            HStack {
                Text(title)
                    .font(.caption.weight(.medium))
                    .foregroundColor(.textSecondary)
                Spacer()
            }
            .padding(.horizontal, ThemeConstants.spacingM)
            .padding(.vertical, ThemeConstants.spacingS)
            .background(Color.black.opacity(0.05))
            
            // Content
            content()
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .frame(width: width)
        .frame(height: height)
        .background(Color.panelBackground)
        .clipShape(RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusSmall))
        .shadow(color: .black.opacity(0.1), radius: 5)
    }
}

// MARK: - Gradient Background for Previews

/// A gradient background to showcase glass effects in previews
struct PreviewBackground<Content: View>: View {
    
    @ViewBuilder var content: () -> Content
    
    var body: some View {
        ZStack {
            LinearGradient(
                colors: [
                    Color.blue.opacity(0.3),
                    Color.purple.opacity(0.2),
                    Color.pink.opacity(0.1)
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            
            content()
        }
    }
}

// MARK: - State Preview Wrappers

/// Preview wrapper that provides a mock AppState
struct StatefulPreview<Value, Content: View>: View {
    
    @State private var value: Value
    let content: (Binding<Value>) -> Content
    
    init(_ initialValue: Value, @ViewBuilder content: @escaping (Binding<Value>) -> Content) {
        _value = State(initialValue: initialValue)
        self.content = content
    }
    
    var body: some View {
        content($value)
    }
}

// MARK: - Preview Helpers

extension View {
    
    /// Wraps the view in a preview container
    func previewContainer(_ title: String, width: CGFloat = 400, height: CGFloat? = nil) -> some View {
        PreviewContainer(title: title, width: width, height: height) {
            self
        }
    }
    
    /// Wraps the view in a gradient background
    func previewBackground() -> some View {
        PreviewBackground {
            self
        }
    }
}

// MARK: - Sample Data Generators

/// Generates sample data for testing
enum SampleData {
    
    /// Generates random messages
    static func randomMessages(count: Int) -> [Message] {
        var messages: [Message] = []
        let prompts = [
            "What's the weather like?",
            "Find all images in Downloads",
            "Open Safari",
            "Search for Python files",
            "Get info about this file"
        ]
        
        let responses = [
            "Here's what I found...",
            "Done! I've completed the task.",
            "I found several matches.",
            "The operation completed successfully.",
            "Here are the results:"
        ]
        
        for i in 0..<count {
            let isUser = i % 2 == 0
            if isUser {
                messages.append(Message.user(prompts.randomElement()!))
            } else {
                messages.append(Message.assistant(responses.randomElement()!))
            }
        }
        
        return messages
    }
    
    /// Random tool call
    static func randomToolCall() -> ToolCall {
        let tools = ["search_files", "get_metadata", "read_text", "open_item", "run_automation"]
        let statuses: [ToolCallStatus] = [.pending, .executing, .success, .failed]
        
        return ToolCall(
            name: tools.randomElement()!,
            arguments: ["sample": .string("value")],
            status: statuses.randomElement()!
        )
    }
}

#endif
