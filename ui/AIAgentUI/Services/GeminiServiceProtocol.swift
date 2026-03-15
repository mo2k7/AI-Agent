//
//  GeminiServiceProtocol.swift
//  AIAgentUI
//
//  Shared protocol abstracting AI prompt streaming.
//  macOS uses MacOSGeminiService (wraps IPCClient/Python backend).
//  iOS uses IOSGeminiService (direct Gemini REST API via URLSession).
//

import Foundation

// MARK: - Protocol

/// Abstraction over the AI model prompt path.
///
/// Implementations handle prompt delivery, streaming response events,
/// tool-call loops, and cancellation. Data operations (sessions, notes,
/// memory) are NOT part of this protocol.
@MainActor
protocol GeminiServiceProtocol: AnyObject {

    /// Send a prompt and receive streamed events.
    ///
    /// The returned stream emits `.text`, `.toolCall`, `.statusUpdate`,
    /// `.complete`, `.error`, and `.cancelled` events.  Callers iterate
    /// the stream in a `for try await` loop.
    func sendPrompt(_ config: PromptConfiguration) -> AsyncThrowingStream<StreamEvent, Error>

    /// Submit a tool execution result so the model can continue generating.
    ///
    /// On macOS this maps to `tool.confirm`.  On iOS it feeds a
    /// `functionResponse` back into the Gemini REST continuation call.
    func submitToolResult(requestId: String, name: String, result: [String: Any]) async throws

    /// Cancel the in-flight request.
    func cancelCurrentRequest() async

    /// Whether the service is ready to accept a new prompt.
    var isReady: Bool { get }
}

// MARK: - Prompt Configuration

/// All parameters needed to send a single prompt to the AI model.
struct PromptConfiguration: Sendable {
    let text: String
    let model: String
    let sessionId: String?
    let memoryMode: String?
    let executionMode: String
    let history: [ChatMessage]
    let systemInstruction: String?
    let tools: [ToolDeclaration]

    // Presentation / behaviour knobs
    let inputPaths: [String]
    let verbosity: String
    let presentationStyle: String
    let streamingAnimation: String
    let browseProfile: String
    let deepThink: Bool
    let correlationId: String

    init(
        text: String,
        model: String,
        sessionId: String? = nil,
        memoryMode: String? = nil,
        executionMode: String = "direct",
        history: [ChatMessage] = [],
        systemInstruction: String? = nil,
        tools: [ToolDeclaration] = [],
        inputPaths: [String] = [],
        verbosity: String = "medium",
        presentationStyle: String = "readable_pro",
        streamingAnimation: String = "wave_reveal",
        browseProfile: String = "strict",
        deepThink: Bool = false,
        correlationId: String = UUID().uuidString
    ) {
        self.text = text
        self.model = model
        self.sessionId = sessionId
        self.memoryMode = memoryMode
        self.executionMode = executionMode
        self.history = history
        self.systemInstruction = systemInstruction
        self.tools = tools
        self.inputPaths = inputPaths
        self.verbosity = verbosity
        self.presentationStyle = presentationStyle
        self.streamingAnimation = streamingAnimation
        self.browseProfile = browseProfile
        self.deepThink = deepThink
        self.correlationId = correlationId
    }
}

// MARK: - Stream Events

/// Events emitted by the AI model during response generation.
enum StreamEvent: Sendable {
    /// Incremental text delta from the model.
    case text(String)

    /// The model wants to call a tool.
    /// On macOS the Python backend executes it; this is just a UI notification.
    /// On iOS the app must execute the tool and call `submitToolResult`.
    case toolCall(ToolCallEvent)

    /// Notification that a tool result was processed.
    case toolResult(name: String, content: String)

    /// Agent status change (e.g. "thinking", "searching").
    case statusUpdate(status: String, detail: String?)

    /// Response generation finished.
    case complete(content: String?)

    /// An error occurred.
    case error(String)

    /// Cancellation was confirmed by the backend/API.
    case cancelled
}

/// Details of a tool call requested by the model.
struct ToolCallEvent: Sendable {
    let name: String
    let id: String
    let arguments: [String: AnySendable]
    /// Status description (e.g. "executing", "pending_approval").
    let status: String?
    /// Pre-formatted result content (macOS only — Python already ran the tool).
    let result: String?
    /// Error message from execution (macOS only).
    let error: String?
}

// MARK: - Chat Message

/// A single turn in the conversation history.
struct ChatMessage: Sendable, Identifiable {
    let id: String
    let role: ChatRole
    let content: String
    let timestamp: Date

    init(
        id: String = UUID().uuidString,
        role: ChatRole,
        content: String,
        timestamp: Date = Date()
    ) {
        self.id = id
        self.role = role
        self.content = content
        self.timestamp = timestamp
    }
}

enum ChatRole: String, Sendable, Codable {
    case user
    case model
    case system
}

// MARK: - Tool Declaration

/// Schema for a tool that the model can invoke via function calling.
struct ToolDeclaration: Sendable {
    let name: String
    let description: String
    let parameters: ToolParameters
}

/// JSON-Schema-style parameter definition for a tool.
struct ToolParameters: Sendable {
    let type: String  // "object"
    let properties: [String: ToolProperty]
    let required: [String]

    init(
        properties: [String: ToolProperty] = [:],
        required: [String] = []
    ) {
        self.type = "object"
        self.properties = properties
        self.required = required
    }
}

/// A single property within tool parameters.
struct ToolProperty: Sendable {
    let type: String  // "string", "integer", "boolean", "array", "object"
    let description: String
    let enumValues: [String]?
    let items: ToolPropertyItems?

    init(
        type: String,
        description: String,
        enumValues: [String]? = nil,
        items: ToolPropertyItems? = nil
    ) {
        self.type = type
        self.description = description
        self.enumValues = enumValues
        self.items = items
    }
}

/// Array item definition for array-typed tool properties.
struct ToolPropertyItems: Sendable {
    let type: String
}

// MARK: - AnySendable Wrapper

/// A `Sendable`-conforming wrapper for arbitrary JSON-compatible values.
///
/// Used in `ToolCallEvent.arguments` to bridge the untyped argument
/// dictionaries from both IPCClient (macOS) and Gemini REST API (iOS).
struct AnySendable: @unchecked Sendable {
    let value: Any

    init(_ value: Any) {
        self.value = value
    }

    var stringValue: String? { value as? String }
    var intValue: Int? { value as? Int }
    var boolValue: Bool? { value as? Bool }
    var doubleValue: Double? { value as? Double }
    var arrayValue: [Any]? { value as? [Any] }
    var dictValue: [String: Any]? { value as? [String: Any] }
}

// MARK: - Service Errors

enum GeminiServiceError: LocalizedError {
    case notReady
    case apiKeyMissing
    case invalidResponse(String)
    case httpError(statusCode: Int, message: String)
    case streamingError(String)
    case cancelled
    case toolExecutionFailed(name: String, error: String)

    var errorDescription: String? {
        switch self {
        case .notReady:
            return "Gemini service is not ready."
        case .apiKeyMissing:
            return "Gemini API key is missing. Add it in Settings."
        case .invalidResponse(let detail):
            return "Invalid response from Gemini API: \(detail)"
        case .httpError(let code, let message):
            return "HTTP \(code): \(message)"
        case .streamingError(let detail):
            return "Streaming error: \(detail)"
        case .cancelled:
            return "Request was cancelled."
        case .toolExecutionFailed(let name, let error):
            return "Tool '\(name)' failed: \(error)"
        }
    }
}
