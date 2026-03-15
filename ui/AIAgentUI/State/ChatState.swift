//
//  ChatState.swift
//  AIAgentUI
//

import SwiftUI
import Combine

/// Manages high-frequency conversation state like text streaming, input, and message lists
/// to isolate MainPanelView layout re-evaluations.
@MainActor
final class ChatState: ObservableObject {
    static let shared = ChatState()

    /// Current text in the input field
    @Published var currentInput: String = ""

    /// Live row models for the current conversation window.
    @Published var messageRows: [MessageRowModel] = []
    
    /// Accumulated streaming text for the current response
    @Published var streamingText: String = ""

    /// Current agent operational status
    @Published var status: AgentStatus = .idle

    /// Human-readable detail for the current status.
    @Published var statusDetail: String = ""

    /// Current tool call being displayed
    @Published var currentToolCall: ToolCall?

    /// Active browse policy notice for the current response lifecycle.
    @Published var activeBrowsePolicyNotice: BrowsePolicyNotice?

    /// Whether the tool call details are expanded
    @Published var isToolCallExpanded: Bool = true
    
    /// Pending destructive tool call awaiting explicit user confirmation.
    @Published var pendingDestructiveToolCall: ToolCall?

    /// Whether a live cancel request is waiting for backend acknowledgement.
    @Published var isCancellationInFlight: Bool = false

    /// Whether older persisted messages exist above the loaded window.
    @Published var hasOlderMessages: Bool = false

    /// Whether newer persisted messages exist below the loaded window.
    @Published var hasNewerMessages: Bool = false

    /// Whether an older history page is currently being fetched.
    @Published var isLoadingOlderMessages: Bool = false

    private init() {}
}
