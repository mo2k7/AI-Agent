//
//  AgentStatus.swift
//  AIAgentUI
//
//  Created for Personal macOS AI Agent
//  Status: Active - Agent operational status enum
//

import Foundation

/// Represents the current operational status of the AI agent.
///
/// This enum maps directly to the Python backend's `AgentStatus` enum
/// to ensure consistent status representation across the IPC boundary.
enum AgentStatus: Equatable {
    /// Agent is ready and waiting for input
    case idle
    
    /// Establishing connection to backend
    case connecting
    
    /// Processing the user's prompt (waiting for LLM response)
    case thinking

    /// Building a plan before execution
    case planning

    /// A plan is ready for review/approval
    case planReady(detail: String)

    /// Waiting for user approval for a destructive action
    case awaitingApproval(detail: String)

    /// Executing an approved plan
    case executingPlan(detail: String)
    
    /// Executing a tool call
    case callingTool(toolName: String)

    /// Capturing screen contents (read-only visual capture)
    case capturingScreen

    /// Streaming response text from the LLM
    case streaming
    
    /// An error occurred
    case error(message: String)
    
    /// Request completed successfully
    case complete
    
    // MARK: - Display Properties
    
    /// Human-readable status text for display
    var displayText: String {
        switch self {
        case .idle:
            return "Ready"
        case .connecting:
            return "Connecting..."
        case .thinking:
            return "Thinking..."
        case .planning:
            return "Planning..."
        case .planReady(let detail):
            return detail.isEmpty ? "Plan Ready" : "Plan Ready: \(detail)"
        case .awaitingApproval(let detail):
            return detail.isEmpty ? "Awaiting Approval..." : detail
        case .executingPlan(let detail):
            return detail.isEmpty ? "Executing Plan..." : detail
        case .callingTool(let toolName):
            return "Calling \(toolName)..."
        case .capturingScreen:
            return "Reading screen..."
        case .streaming:
            return "Responding..."
        case .error(let message):
            return "Error: \(message)"
        case .complete:
            return "Done"
        }
    }
    
    /// Short status text (without details)
    var shortText: String {
        switch self {
        case .idle: return "Ready"
        case .connecting: return "Connecting..."
        case .thinking: return "Thinking..."
        case .planning: return "Planning..."
        case .planReady: return "Plan Ready"
        case .awaitingApproval: return "Awaiting Approval"
        case .executingPlan: return "Executing Plan..."
        case .callingTool: return "Calling Tool..."
        case .capturingScreen: return "Reading Screen..."
        case .streaming: return "Responding..."
        case .error: return "Error"
        case .complete: return "Done"
        }
    }
    
    /// Whether this status indicates the agent is busy
    var isBusy: Bool {
        switch self {
        case .connecting, .thinking, .planning, .awaitingApproval, .executingPlan, .callingTool, .capturingScreen, .streaming:
            return true
        case .idle, .planReady, .error, .complete:
            return false
        }
    }

    /// Whether this status should show an animated indicator
    var shouldAnimate: Bool {
        switch self {
        case .thinking, .planning, .awaitingApproval, .executingPlan, .callingTool, .capturingScreen, .streaming:
            return true
        case .idle, .planReady, .connecting, .error, .complete:
            return false
        }
    }
    
    /// Whether the user can submit a new prompt
    var canSubmit: Bool {
        switch self {
        case .idle, .planReady, .error, .complete:
            return true
        case .connecting, .thinking, .planning, .awaitingApproval, .executingPlan, .callingTool, .capturingScreen, .streaming:
            return false
        }
    }
    
    /// Whether to show the status indicator
    var showsIndicator: Bool {
        switch self {
        case .idle, .complete:
            return false
        case .connecting, .thinking, .planning, .planReady, .awaitingApproval, .executingPlan, .callingTool, .capturingScreen, .streaming, .error:
            return true
        }
    }
    
    /// Whether this status represents an error state
    var isError: Bool {
        if case .error = self { return true }
        return false
    }
    
    /// Extract tool name if calling a tool
    var toolName: String? {
        if case .callingTool(let name) = self { return name }
        return nil
    }
    
    /// Extract error message if in error state
    var errorMessage: String? {
        if case .error(let message) = self { return message }
        return nil
    }
    
    // MARK: - Factory Methods
    
    /// Creates an AgentStatus from raw backend status string
    /// - Parameters:
    ///   - rawStatus: The status string from the backend
    ///   - detail: Optional detail string (e.g., tool name for calling_tool, error message for error)
    /// - Returns: The corresponding AgentStatus
    static func from(rawStatus: String, detail: String?) -> AgentStatus {
        switch rawStatus {
        case "idle": return .idle
        case "connecting": return .connecting
        case "thinking": return .thinking
        case "planning": return .planning
        case "plan_ready": return .planReady(detail: detail ?? "")
        case "awaiting_approval": return .awaitingApproval(detail: detail ?? "")
        case "executing_plan": return .executingPlan(detail: detail ?? "")
        case "calling_tool": return .callingTool(toolName: detail ?? "unknown")
        case "capturing_screen": return .capturingScreen
        case "streaming": return .streaming
        case "error": return .error(message: detail ?? "Unknown error")
        case "complete": return .complete
        default: return .idle
        }
    }

    var signatureKey: String {
        switch self {
        case .idle:
            return "idle"
        case .connecting:
            return "connecting"
        case .thinking:
            return "thinking"
        case .planning:
            return "planning"
        case .planReady(let detail):
            return "plan_ready:\(detail)"
        case .awaitingApproval(let detail):
            return "awaiting_approval:\(detail)"
        case .executingPlan(let detail):
            return "executing_plan:\(detail)"
        case .callingTool(let toolName):
            return "calling_tool:\(toolName)"
        case .capturingScreen:
            return "capturing_screen"
        case .streaming:
            return "streaming"
        case .error(let message):
            return "error:\(message)"
        case .complete:
            return "complete"
        }
    }
}

// MARK: - Codable Support

extension AgentStatus: Codable {
    
    private enum CodingKeys: String, CodingKey {
        case type
        case detail
    }
    
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let type = try container.decode(String.self, forKey: .type)
        let detail = try container.decodeIfPresent(String.self, forKey: .detail)
        
        self = AgentStatus.from(rawStatus: type, detail: detail)
    }
    
    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        
        switch self {
        case .idle:
            try container.encode("idle", forKey: .type)
        case .connecting:
            try container.encode("connecting", forKey: .type)
        case .thinking:
            try container.encode("thinking", forKey: .type)
        case .planning:
            try container.encode("planning", forKey: .type)
        case .planReady(let detail):
            try container.encode("plan_ready", forKey: .type)
            try container.encode(detail, forKey: .detail)
        case .awaitingApproval(let detail):
            try container.encode("awaiting_approval", forKey: .type)
            try container.encode(detail, forKey: .detail)
        case .executingPlan(let detail):
            try container.encode("executing_plan", forKey: .type)
            try container.encode(detail, forKey: .detail)
        case .callingTool(let toolName):
            try container.encode("calling_tool", forKey: .type)
            try container.encode(toolName, forKey: .detail)
        case .capturingScreen:
            try container.encode("capturing_screen", forKey: .type)
        case .streaming:
            try container.encode("streaming", forKey: .type)
        case .error(let message):
            try container.encode("error", forKey: .type)
            try container.encode(message, forKey: .detail)
        case .complete:
            try container.encode("complete", forKey: .type)
        }
    }
}
