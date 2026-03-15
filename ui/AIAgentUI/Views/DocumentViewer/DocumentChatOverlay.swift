//
//  DocumentChatOverlay.swift
//  AIAgentUI
//
//  Created for Personal macOS AI Agent
//  Status: Active - Floating contextual chat history over Document Viewer
//

import SwiftUI

/// A floating, bottom-anchored chat view overlaid onto the document.
/// Reuses the global `ChatState` via `appState` within the existing session.
///
/// Performance notes:
/// - Thought bubble visibility uses explicit animation values, not implicit
/// - History restoration runs once on appear and scans in reverse for O(recent) speed
/// - InputField is isolated so streaming text changes don't re-measure it
struct DocumentChatOverlay: View {
    @ObservedObject var appState: AppState
    @ObservedObject var chatState: ChatState = .shared
    let documentURL: URL
    
    @State private var inputText: String = ""
    @State private var localThoughtBubbleText: String? = nil
    @State private var isDocumentInteractionActive: Bool = false
    @Environment(\.colorScheme) private var colorScheme
    
    /// Whether the thought bubble should be visible
    private var showBubble: Bool {
        chatState.status.isBusy || (localThoughtBubbleText != nil && !localThoughtBubbleText!.isEmpty)
    }
    
    var body: some View {
        VStack(spacing: 0) {
            Spacer(minLength: 0)
            
            // Thought Bubble — shown/hidden with smooth animation
            if showBubble {
                ThoughtBubbleView(
                    streamingText: chatState.streamingText,
                    finalText: localThoughtBubbleText,
                    isBusy: chatState.status.isBusy,
                    statusDetail: chatState.statusDetail
                )
                .padding(.bottom, ThemeConstants.spacingS)
                .transition(.asymmetric(
                    insertion: .opacity.combined(with: .move(edge: .bottom)),
                    removal: .opacity
                ))
            }
            
            // Pill-shaped Input Area
            inputArea
                .padding(.horizontal, ThemeConstants.spacingM)
                .padding(.bottom, ThemeConstants.spacingL)
                .padding(.top, ThemeConstants.spacingXS)
        }
        .animation(.spring(response: 0.35, dampingFraction: 0.82), value: showBubble)
        .onChange(of: chatState.status) { newStatus in
            if newStatus == .idle && isDocumentInteractionActive {
                // Capture the final assistant response for this interaction
                if let lastMsg = chatState.messageRows.last, lastMsg.role == .assistant {
                    localThoughtBubbleText = lastMsg.content
                }
                isDocumentInteractionActive = false
            }
        }
        .onAppear {
            restoreDocumentContext()
        }
    }
    
    /// Scans session history in reverse for O(recent) performance
    private func restoreDocumentContext() {
        let rows = chatState.messageRows
        let docName = documentURL.lastPathComponent
        
        // Walk backwards — most recent interaction is what we want
        for i in stride(from: rows.count - 1, through: 0, by: -1) {
            let row = rows[i]
            if row.role == .user && row.content.contains(docName) {
                if i + 1 < rows.count {
                    let nextRow = rows[i + 1]
                    if nextRow.role == .assistant && !nextRow.content.isEmpty {
                        localThoughtBubbleText = nextRow.content
                        return
                    }
                }
            }
        }
    }
    
    /// The glassmorphic chat input bar with a pill / capsule shape
    private let chatBarRadius: CGFloat = 28
    
    private var inputArea: some View {
        InputField(
            text: $inputText,
            placeholder: "Ask about this document...",
            isDisabled: chatState.status.isBusy,
            isBusy: chatState.status.isBusy,
            onSubmit: submitMessage
        )
        .clipShape(RoundedRectangle(cornerRadius: chatBarRadius, style: .continuous))
        .background(
            // Animated Siri glow tightly hugging the pill shape
            SiriMeshAnimationView(
                cornerRadius: chatBarRadius,
                lineWidth: 2.5
            )
            .clipShape(RoundedRectangle(cornerRadius: chatBarRadius + 2, style: .continuous))
            .padding(-2)
        )
        .shadow(color: Color.black.opacity(0.15), radius: 10, x: 0, y: 5)
        .frame(maxWidth: 800)
    }
    
    private func submitMessage() {
        let text = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !chatState.status.isBusy else { return }
        inputText = ""
        chatState.currentInput = text
        localThoughtBubbleText = nil
        isDocumentInteractionActive = true
        Task {
            await appState.sendPrompt()
        }
    }
}
