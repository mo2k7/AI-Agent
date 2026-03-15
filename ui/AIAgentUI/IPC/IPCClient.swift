//
//  IPCClient.swift
//  AIAgentUI
//
//  Created for Personal macOS AI Agent
//  Status: Active - High-level IPC interface
//

import Foundation
import Combine
struct IPCSystemDiagnostics: Decodable {
    let status: String
    let apiKeyValid: Bool
    let dbConnected: Bool
    let toolsReady: Bool
    let errors: [String]

    enum CodingKeys: String, CodingKey {
        case status
        case apiKeyValid = "api_key_valid"
        case dbConnected = "db_connected"
        case toolsReady = "tools_ready"
        case errors
    }
}

struct IPCSessionSummary: Decodable, Identifiable {
    let sessionId: String
    let title: String
    let memoryMode: String
    let createdAt: Double
    let updatedAt: Double
    let lastActivity: Double
    let status: String
    let storeVersion: Int?

    var id: String { sessionId }

    enum CodingKeys: String, CodingKey {
        case sessionId = "session_id"
        case title
        case memoryMode = "memory_mode"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case lastActivity = "last_activity"
        case status
        case storeVersion = "store_version"
    }
}

struct IPCSessionMessage: Decodable, Identifiable {
    let messageId: String
    let role: String
    let content: String
    let createdAt: Double
    let turnIndex: Int

    var id: String { messageId }

    enum CodingKeys: String, CodingKey {
        case messageId = "message_id"
        case role
        case content
        case createdAt = "created_at"
        case turnIndex = "turn_index"
    }
}

struct IPCSessionHistoryPage: Decodable {
    let messages: [IPCSessionMessage]
    let direction: String
    let oldestTurnIndex: Int?
    let newestTurnIndex: Int?
    let hasOlder: Bool

    enum CodingKeys: String, CodingKey {
        case messages
        case direction
        case oldestTurnIndex = "oldest_turn_index"
        case newestTurnIndex = "newest_turn_index"
        case hasOlder = "has_older"
    }
}

struct IPCModelCatalog: Decodable {
    let defaultModel: String
    let models: [GeminiModelOption]

    enum CodingKeys: String, CodingKey {
        case defaultModel = "default_model"
        case models
    }
}

struct IPCRegisteredDevice: Decodable {
    let deviceId: String
    let platform: String
    let deviceName: String
    let appVersion: String
    let capabilities: [String]

    enum CodingKeys: String, CodingKey {
        case deviceId = "device_id"
        case platform
        case deviceName = "device_name"
        case appVersion = "app_version"
        case capabilities
    }
}

struct IPCCreatedSession: Decodable {
    let sessionId: String
    let title: String
    let memoryMode: String
    let createdAt: Double

    enum CodingKeys: String, CodingKey {
        case sessionId = "session_id"
        case title
        case memoryMode = "memory_mode"
        case createdAt = "created_at"
    }
}

struct IPCMemoryEntry: Decodable, Identifiable {
    let memoryId: String
    let kind: String
    let factKey: String
    let content: String
    let confidence: Double
    let trustFlags: [String]
    let policyFlags: [String]
    let updatedAt: Double

    var id: String { memoryId }

    enum CodingKeys: String, CodingKey {
        case memoryId = "memory_id"
        case kind
        case factKey = "fact_key"
        case content
        case confidence
        case trustFlags = "trust_flags"
        case policyFlags = "policy_flags"
        case updatedAt = "updated_at"
    }
}

private struct IPCDeleteMemoryResult: Decodable {
    let deleted: Bool
    let memoryId: String

    enum CodingKeys: String, CodingKey {
        case deleted
        case memoryId = "memory_id"
    }
}

private struct IPCDeleteSessionsResult: Decodable {
    struct FailedSession: Decodable {
        let sessionId: String
        let error: String

        enum CodingKeys: String, CodingKey {
            case sessionId = "session_id"
            case error
        }
    }

    let requestedCount: Int
    let deletedCount: Int
    let deletedSessionIds: [String]
    let failed: [FailedSession]

    enum CodingKeys: String, CodingKey {
        case requestedCount = "requested_count"
        case deletedCount = "deleted_count"
        case deletedSessionIds = "deleted_session_ids"
        case failed
    }
}

private struct IPCSessionListSinceResponse: Decodable {
    let sessions: [IPCSessionSummary]
    let maxVersion: Int

    enum CodingKeys: String, CodingKey {
        case sessions
        case maxVersion = "max_version"
    }
}

private struct IPCAuthHelloResponse: Decodable {
    let authenticated: Bool
    let protocolVersion: String
    let features: [String]
    let rotationToken: String?

    enum CodingKeys: String, CodingKey {
        case authenticated
        case protocolVersion = "protocol_version"
        case features
        case rotationToken = "rotation_token"
    }
}

struct IPCSystemEvent {
    let domain: String
    let action: String
    let payload: [String: Any]
    let seq: Int?
}

struct IPCRequestTimeoutPayload {
    let requestId: String
    let code: String
    let phase: String
    let operation: String
    let timeoutSeconds: Double?
    let elapsedSeconds: Double?
    let userMessage: String
}

enum IPCRequestError: LocalizedError {
    case notConnected
    case disconnected
    case timeout(method: String)
    case backend(message: String, code: Int?)
    case invalidPayload(String)
    case authConfigMissing
    case protocolMismatch(expected: String, actual: String)
    case missingFeatures([String])

    var errorDescription: String? {
        switch self {
        case .notConnected:
            return "IPC backend is not connected."
        case .disconnected:
            return "IPC connection was closed before the request completed."
        case .timeout(let method):
            return "Timed out waiting for '\(method)' response."
        case .backend(let message, let code):
            if let code {
                return "Backend error (\(code)): \(message)"
            }
            return "Backend error: \(message)"
        case .invalidPayload(let details):
            return "Invalid backend payload: \(details)"
        case .authConfigMissing:
            return "IPC auth token is missing; cannot authenticate to backend."
        case .protocolMismatch(let expected, let actual):
            return "IPC protocol mismatch. Expected \(expected), got \(actual)."
        case .missingFeatures(let features):
            return "IPC backend is missing required features: \(features.joined(separator: ", "))."
        }
    }
}

/// High-level IPC client that provides a clean async interface for communicating
/// with the backend via WebSocket transport.
@MainActor
final class IPCClient: ObservableObject {
    
    // MARK: - Published Properties
    
    /// Current connection status
    @Published private(set) var isConnected: Bool = false
    
    /// Last error that occurred
    @Published private(set) var lastError: String?
    
    /// Current streaming text (for the active request)
    @Published private(set) var streamingText: String = ""
    
    /// Whether currently streaming a response
    @Published private(set) var isStreaming: Bool = false

    /// Whether a live cancellation request is waiting for backend acknowledgement.
    @Published private(set) var isCancellationPending: Bool = false
    
    // MARK: - Private Properties
    
    /// The underlying socket manager
    private let socketManager: SocketManager

    /// Shared token required for backend auth.hello handshake.
    private var authToken: String?

    /// One-time rotation token issued by the backend on auth success.
    /// Survives disconnect so reconnects can use it instead of the static bootstrap token.
    private var rotationToken: String?

    /// Whether transport-level auth/version negotiation has completed.
    private var isAuthenticatedTransport: Bool = false

    /// Negotiated protocol version for the active connection.
    private(set) var negotiatedProtocolVersion: String?

    private let expectedProtocolVersion = "2.0.0"
    private let requiredBackendFeatures: Set<String> = [
        "prompt",
        "cancel",
        "device.register",
        "tool.confirm",
        "screen.capture_response",
        "ping",
        "session.create",
        "session.list",
        "session.history",
        "session.history_page",
        "models.list",
        "session.set_mode",
        "session.rename",
        "session.delete",
        "session.delete_many",
        "memory.list",
        "memory.delete",
        "notes.list",
        "notes.create",
        "notes.update",
        "notes.delete",
        "notes.get_image",
        "notes.list_versions",
        "system.session_events",
        "system.notes_events",
        "system.memory_events",
    ]
    
    /// Current request ID being tracked
    private(set) var currentRequestId: String?

    /// Request ID currently waiting for cancellation acknowledgement from the backend.
    private var cancellationPendingRequestId: String?
    
    /// Cancellables for Combine subscriptions
    private var cancellables = Set<AnyCancellable>()
    
    /// Pending ping request tracking
    private var pendingPingId: String?
    private var pendingPingContinuation: CheckedContinuation<Bool, Never>?
    private var pendingPingTimeoutTask: Task<Void, Never>?
    private var ignoredPingIds = Set<String>()

    /// Pending non-streaming RPC requests (session/memory methods).
    private var pendingRPCContinuations: [String: CheckedContinuation<String, Error>] = [:]
    private var pendingRPCTimeoutTasks: [String: Task<Void, Never>] = [:]
    private let defaultRPCTimeoutNanoseconds: UInt64 = 3_000_000_000
    private let sessionDeleteRPCTimeoutNanoseconds: UInt64 = 45_000_000_000
    private var requestStartTimes: [String: Date] = [:]
    private var lastDeliveredStatusSignature: String?
    private let pingTimeoutNanoseconds: UInt64 = {
        let env = ProcessInfo.processInfo.environment["AI_AGENT_PING_TIMEOUT_MS"]
        let value = UInt64(env ?? "") ?? 3_000
        let clamped = max(UInt64(500), min(value, UInt64(30_000)))
        return clamped * 1_000_000
    }()
    private let requestTimeoutErrorCode = -32014
    
    // MARK: - Callbacks
    
    /// Called when agent status changes
    var onStatusChange: ((AgentStatus, String?) -> Void)?
    
    /// Called when streaming text is updated
    var onStreamUpdate: ((String, String, Bool) -> Void)? // delta, text, isDone
    
    /// Called when a tool call is received
    var onToolCall: ((ToolCall) -> Void)?
    
    /// Called when the response is complete
    var onComplete: ((String?) -> Void)? // final content
    
    /// Called when an error occurs
    var onError: ((String) -> Void)?

    /// Called when the backend confirms the active request was cancelled.
    var onCancelled: (() -> Void)?

    /// Called when backend reports structured request-timeout metadata.
    var onRequestTimeout: ((IPCRequestTimeoutPayload) -> Void)?

    /// Called for backend lifecycle system events (session/notes/memory).
    var onSystemEvent: ((IPCSystemEvent) -> Void)?
    
    // MARK: - Initialization
    
    init() {
        self.socketManager = SocketManager()
        setupCallbacks()
    }
    
    private func setupCallbacks() {
        // State change handling
        socketManager.onStateChange = { [weak self] state in
            Task { @MainActor in
                self?.handleStateChange(state)
            }
        }
        
        // Error handling
        socketManager.onError = { [weak self] error in
            Task { @MainActor in
                self?.handleError(error.localizedDescription)
            }
        }
        
        // Message dispatcher callbacks
        socketManager.dispatcher.onStatusUpdate = { [weak self] status, requestId, detail in
            Task { @MainActor in
                self?.handleStatusUpdate(status, requestId: requestId, detail: detail)
            }
        }
        
        socketManager.dispatcher.onStreamingUpdate = { [weak self] requestId, delta, text, isDone in
            Task { @MainActor in
                self?.handleStreamingUpdate(
                    requestId: requestId,
                    delta: delta,
                    text: text,
                    isDone: isDone
                )
            }
        }
        
        socketManager.dispatcher.onToolCall = { [weak self] toolCall, requestId in
            Task { @MainActor in
                self?.handleToolCall(toolCall, requestId: requestId)
            }
        }
        
        socketManager.dispatcher.onComplete = { [weak self] requestId, content in
            Task { @MainActor in
                self?.handleComplete(requestId: requestId, content: content)
            }
        }
        
        socketManager.dispatcher.onError = { [weak self] requestId, message, code, data in
            Task { @MainActor in
                self?.handleError(message, requestId: requestId, code: code, data: data)
            }
        }

        socketManager.dispatcher.onSystemMessage = { [weak self] response, requestId in
            Task { @MainActor in
                self?.handleSystemMessage(response, requestId: requestId)
            }
        }
    }
    
    // MARK: - Public Methods

    func configureAuthToken(_ token: String?) {
        let trimmed = token?.trimmingCharacters(in: .whitespacesAndNewlines)
        authToken = (trimmed?.isEmpty == false) ? trimmed : nil
    }
    
    /// Connects to the backend using the configured WebSocket endpoint.
    func connect() async {
        do {
            try await socketManager.connect()
            try await authenticateAndNegotiate()
        } catch {
            socketManager.disconnect()
            handleError(error.localizedDescription)
        }
    }
    
    /// Connects to a specific WebSocket endpoint URL.
    /// - Parameter url: Fully qualified `ws://` or `wss://` endpoint.
    func connect(toWebSocketURL url: String) async throws {
        try await socketManager.connect(toURLString: url)
        do {
            try await authenticateAndNegotiate()
        } catch {
            socketManager.disconnect()
            throw error
        }
    }
    
    /// Disconnects from the Python backend
    func disconnect() {
        isAuthenticatedTransport = false
        negotiatedProtocolVersion = nil
        isConnected = false
        isCancellationPending = false
        cancellationPendingRequestId = nil
        if let pendingPingId = pendingPingId {
            ignoredPingIds.insert(pendingPingId)
            completePingIfNeeded(requestId: pendingPingId, success: false)
        }
        failAllPendingRPCs(IPCRequestError.disconnected)
        requestStartTimes.removeAll()
        lastDeliveredStatusSignature = nil
        socketManager.disconnect()
    }
    
    /// Sends a prompt to the agent
    /// - Parameters:
    ///   - prompt: The user's prompt text
    ///   - model: The Gemini model to use for this request
    ///   - sessionId: Session identifier for memory partitioning.
    ///   - memoryMode: Memory behavior (`on`, `off`, `ephemeral`).
    ///   - executionMode: Prompt execution mode (`direct`, `plan`).
    ///   - inputPaths: Optional user-selected file paths for this prompt.
    ///   - verbosity: Response verbosity (`low`, `medium`, `high`, `extra_high`).
    ///   - presentationStyle: Response rendering style (`readable_pro`, `glass_editorial`, `dense_technical`).
    ///   - streamingAnimation: Streaming animation style (`wave_reveal`, `typewriter_luxe`, `minimal_motion`).
    ///   - browseProfile: Browse restriction profile (`strict`, `standard`, `flexible`).
    ///   - deepThink: Enables stronger reasoning mode for this prompt.
    /// - Returns: The request ID for tracking.
    @discardableResult
    func send(
        prompt: String,
        model: String,
        sessionId: String?,
        memoryMode: String?,
        executionMode: String,
        inputPaths: [String],
        verbosity: String,
        presentationStyle: String,
        streamingAnimation: String,
        browseProfile: String,
        deepThink: Bool,
        correlationId: String
    ) async -> String? {
        guard isConnected else {
            handleError("Not connected to backend")
            return nil
        }
        
        // Reset streaming state
        streamingText = ""
        isStreaming = true
        isCancellationPending = false
        cancellationPendingRequestId = nil
        lastDeliveredStatusSignature = nil
        let requestId = UUID().uuidString
        currentRequestId = requestId
        requestStartTimes[requestId] = Date()
        DebugLogger.log(
            "prompt_send",
            fields: [
                "request_id": requestId,
                "correlation_id": correlationId,
                "model": model,
                "session_id": sessionId ?? "none",
                "memory_mode": memoryMode ?? "none",
                "execution_mode": executionMode,
                "input_paths_count": String(inputPaths.count),
                "verbosity": verbosity,
                "presentation_style": presentationStyle,
                "stream_animation": streamingAnimation,
                "browse_profile": browseProfile,
                "deep_think": deepThink ? "true" : "false",
            ]
        )
        
        do {
            let sentRequestId = try await socketManager.sendPrompt(
                prompt,
                model: model,
                sessionId: sessionId,
                memoryMode: memoryMode,
                executionMode: executionMode,
                inputPaths: inputPaths.isEmpty ? nil : inputPaths,
                verbosity: verbosity,
                presentationStyle: presentationStyle,
                streamingAnimation: streamingAnimation,
                browseProfile: browseProfile,
                deepThink: deepThink,
                correlationId: correlationId,
                requestId: requestId
            )
            return sentRequestId
        } catch {
            if currentRequestId == requestId {
                currentRequestId = nil
            }
            if cancellationPendingRequestId == requestId {
                cancellationPendingRequestId = nil
                isCancellationPending = false
            }
            requestStartTimes.removeValue(forKey: requestId)
            handleError(error.localizedDescription)
            isStreaming = false
            return nil
        }
    }

    func createSession(title: String?, memoryMode: String) async throws -> IPCCreatedSession {
        var params: [String: AnyCodable] = ["memory_mode": AnyCodable(memoryMode)]
        if let title, !title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            params["title"] = AnyCodable(title)
        }
        let content = try await sendRPC(method: "session.create", params: params)
        return try decodeJSONPayload(content, as: IPCCreatedSession.self)
    }

    func listSessions(limit: Int = 0) async throws -> [IPCSessionSummary] {
        let resolvedLimit = limit <= 0 ? 0 : min(limit, 5_000)
        let content = try await sendRPC(
            method: "session.list",
            params: ["limit": AnyCodable(resolvedLimit)]
        )
        return try decodeJSONPayload(content, as: [IPCSessionSummary].self)
    }

    func listSessionsSince(sinceVersion: Int, limit: Int = 200) async throws -> (sessions: [IPCSessionSummary], maxVersion: Int) {
        let content = try await sendRPC(
            method: "session.list_since",
            params: [
                "since_version": AnyCodable(sinceVersion),
                "limit": AnyCodable(max(1, min(limit, 500))),
            ]
        )
        let result = try decodeJSONPayload(content, as: IPCSessionListSinceResponse.self)
        return (result.sessions, result.maxVersion)
    }

    func getSystemDiagnostics() async throws -> IPCSystemDiagnostics {
        let content = try await sendRPC(method: "system.diagnostics", params: [:])
        return try decodeJSONPayload(content, as: IPCSystemDiagnostics.self)
    }

    func deleteSession(sessionId: String) async throws {
        _ = try await sendRPC(
            method: "session.delete",
            params: ["session_id": AnyCodable(sessionId)]
        )
    }

    func deleteSessions(sessionIds: [String]) async throws -> (deletedSessionIds: [String], failed: [String: String]) {
        let normalized = Array(
            Set(
                sessionIds
                    .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
                    .filter { !$0.isEmpty }
            )
        ).sorted()
        guard !normalized.isEmpty else { return ([], [:]) }
        let content = try await sendRPC(
            method: "session.delete_many",
            params: ["session_ids": AnyCodable(normalized)]
        )
        let parsed = try decodeJSONPayload(content, as: IPCDeleteSessionsResult.self)
        var failedById: [String: String] = [:]
        for failure in parsed.failed {
            failedById[failure.sessionId] = failure.error
        }
        return (parsed.deletedSessionIds, failedById)
    }

    func sessionHistory(sessionId: String, limit: Int = 500) async throws -> [IPCSessionMessage] {
        let clamped = max(1, min(limit, 2000))
        let content = try await sendRPC(
            method: "session.history",
            params: [
                "session_id": AnyCodable(sessionId),
                "limit": AnyCodable(clamped),
            ]
        )
        return try decodeJSONPayload(content, as: [IPCSessionMessage].self)
    }

    func sessionHistoryPage(
        sessionId: String,
        direction: String,
        anchorTurnIndex: Int? = nil,
        limit: Int = 120
    ) async throws -> IPCSessionHistoryPage {
        var params: [String: AnyCodable] = [
            "session_id": AnyCodable(sessionId),
            "direction": AnyCodable(direction),
            "limit": AnyCodable(max(1, min(limit, 120))),
        ]
        if let anchorTurnIndex {
            params["anchor_turn_index"] = AnyCodable(anchorTurnIndex)
        }
        let content = try await sendRPC(
            method: "session.history_page",
            params: params
        )
        return try decodeJSONPayload(content, as: IPCSessionHistoryPage.self)
    }

    func listModels(forceRefresh: Bool = false) async throws -> IPCModelCatalog {
        let content = try await sendRPC(
            method: "models.list",
            params: ["force_refresh": AnyCodable(forceRefresh)]
        )
        return try decodeJSONPayload(content, as: IPCModelCatalog.self)
    }

    func renameSession(sessionId: String, title: String) async throws -> IPCSessionSummary {
        let trimmed = title.trimmingCharacters(in: .whitespacesAndNewlines)
        let content = try await sendRPC(
            method: "session.rename",
            params: [
                "session_id": AnyCodable(sessionId),
                "title": AnyCodable(trimmed),
            ]
        )
        return try decodeJSONPayload(content, as: IPCSessionSummary.self)
    }

    func setSessionMode(sessionId: String, memoryMode: String) async throws -> IPCSessionSummary {
        let content = try await sendRPC(
            method: "session.set_mode",
            params: [
                "session_id": AnyCodable(sessionId),
                "memory_mode": AnyCodable(memoryMode),
            ]
        )
        return try decodeJSONPayload(content, as: IPCSessionSummary.self)
    }

    func listMemories(sessionId: String, limit: Int = 100) async throws -> [IPCMemoryEntry] {
        let clamped = max(1, min(limit, 500))
        let content = try await sendRPC(
            method: "memory.list",
            params: [
                "session_id": AnyCodable(sessionId),
                "limit": AnyCodable(clamped),
            ]
        )
        return try decodeJSONPayload(content, as: [IPCMemoryEntry].self)
    }

    func deleteMemory(sessionId: String, memoryId: String) async throws -> Bool {
        let content = try await sendRPC(
            method: "memory.delete",
            params: [
                "session_id": AnyCodable(sessionId),
                "memory_id": AnyCodable(memoryId),
            ]
        )
        let parsed = try decodeJSONPayload(content, as: IPCDeleteMemoryResult.self)
        return parsed.deleted
    }

    // MARK: - Notes

    func listNotes(sessionId: String, limit: Int = 200) async throws -> [IPCNote] {
        let clamped = max(1, min(limit, 500))
        let content = try await sendRPC(
            method: "notes.list",
            params: [
                "session_id": AnyCodable(sessionId),
                "limit": AnyCodable(clamped),
            ]
        )
        return try decodeJSONPayload(content, as: [IPCNote].self)
    }

    func createNote(
        sessionId: String,
        content: String,
        source: String = "user",
        title: String? = nil,
        workspaceKind: String? = nil
    ) async throws -> IPCNote {
        var params: [String: AnyCodable] = [
            "session_id": AnyCodable(sessionId),
            "content": AnyCodable(content),
            "source": AnyCodable(source),
        ]
        if let title {
            params["title"] = AnyCodable(title)
        }
        if let workspaceKind {
            params["workspace_kind"] = AnyCodable(workspaceKind)
        }
        let result = try await sendRPC(
            method: "notes.create",
            params: params
        )
        return try decodeJSONPayload(result, as: IPCNote.self)
    }

    func updateNote(
        sessionId: String,
        noteId: String,
        content: String? = nil,
        isPinned: Bool? = nil,
        title: String? = nil
    ) async throws -> IPCNote {
        var params: [String: AnyCodable] = [
            "session_id": AnyCodable(sessionId),
            "note_id": AnyCodable(noteId),
        ]
        if let content { params["content"] = AnyCodable(content) }
        if let isPinned { params["is_pinned"] = AnyCodable(isPinned) }
        if let title { params["title"] = AnyCodable(title) }
        let result = try await sendRPC(method: "notes.update", params: params)
        return try decodeJSONPayload(result, as: IPCNote.self)
    }

    func deleteNote(sessionId: String, noteId: String) async throws -> Bool {
        let content = try await sendRPC(
            method: "notes.delete",
            params: [
                "session_id": AnyCodable(sessionId),
                "note_id": AnyCodable(noteId),
            ]
        )
        let parsed = try decodeJSONPayload(content, as: IPCDeleteNoteResult.self)
        return parsed.deleted
    }

    func getNoteImage(sessionId: String, imageId: String) async throws -> IPCNoteImage {
        let content = try await sendRPC(
            method: "notes.get_image",
            params: [
                "session_id": AnyCodable(sessionId),
                "image_id": AnyCodable(imageId),
            ]
        )
        return try decodeJSONPayload(content, as: IPCNoteImage.self)
    }

    func listNoteVersions(sessionId: String, noteId: String) async throws -> [IPCNoteVersion] {
        let content = try await sendRPC(
            method: "notes.list_versions",
            params: [
                "session_id": AnyCodable(sessionId),
                "note_id": AnyCodable(noteId),
            ]
        )
        return try decodeJSONPayload(content, as: [IPCNoteVersion].self)
    }

    func registerDevice(_ manifest: DeviceBridgeManifest) async throws -> IPCRegisteredDevice {
        let content = try await sendRPC(
            method: "device.register",
            params: [
                "device_id": AnyCodable(manifest.deviceId),
                "platform": AnyCodable(manifest.platform),
                "device_name": AnyCodable(manifest.deviceName),
                "app_version": AnyCodable(manifest.appVersion),
                "capabilities": AnyCodable(manifest.capabilityNames),
                "supported_tools": AnyCodable(manifest.supportedTools),
            ]
        )
        return try decodeJSONPayload(content, as: IPCRegisteredDevice.self)
    }

    func confirmCurrentToolExecution(approved: Bool) async throws {
        guard let requestId = currentRequestId else {
            throw IPCRequestError.invalidPayload("No active request awaiting confirmation.")
        }
        _ = try await sendRPC(
            method: "tool.confirm",
            params: [
                "request_id": AnyCodable(requestId),
                "approved": AnyCodable(approved),
            ]
        )
    }
    
    /// Sends a screen capture response back to the backend.
    func sendScreenCapture(
        requestId: String,
        imageData: Data,
        ocrText: String,
        width: Int,
        height: Int
    ) async throws {
        _ = try await sendRPC(
            method: "screen.capture_response",
            params: [
                "request_id": AnyCodable(requestId),
                "image_data": AnyCodable(imageData.base64EncodedString()),
                "ocr_text": AnyCodable(ocrText),
                "width": AnyCodable(width),
                "height": AnyCodable(height),
            ]
        )
    }

    /// Sends an error response when screen capture fails.
    func sendScreenCaptureError(requestId: String, error: String) async throws {
        _ = try await sendRPC(
            method: "screen.capture_response",
            params: [
                "request_id": AnyCodable(requestId),
                "image_data": AnyCodable(""),
                "ocr_text": AnyCodable(""),
                "width": AnyCodable(0),
                "height": AnyCodable(0),
                "error": AnyCodable(error),
            ]
        )
    }

    /// Sends a proxied tool execution result back to the backend.
    func sendToolExecuteResponse(proxyKey: String, result: [String: Any]) async throws {
        _ = try await sendRPC(
            method: "tool.execute_response",
            params: [
                "proxy_key": AnyCodable(proxyKey),
                "result": AnyCodable(result),
            ]
        )
    }

    /// Cancels the current request
    func cancel() async {
        guard isConnected else { return }
        guard let requestId = currentRequestId else { return }
        guard cancellationPendingRequestId == nil else { return }
        
        do {
            cancellationPendingRequestId = requestId
            isCancellationPending = true
            isStreaming = false
            try await socketManager.sendCancel(targetRequestId: requestId)
        } catch {
            cancellationPendingRequestId = nil
            isCancellationPending = false
            handleError(error.localizedDescription)
        }
    }
    
    /// Sends a ping to verify the backend is responsive
    /// - Returns: True if ping was successful (response received), false otherwise
    func ping() async -> Bool {
        guard isConnected else { return false }
        guard pendingPingId == nil else { return false }
        
        do {
            let requestId = try await socketManager.sendPing()
            return await withCheckedContinuation { continuation in
                pendingPingId = requestId
                pendingPingContinuation = continuation
                pendingPingTimeoutTask?.cancel()
                pendingPingTimeoutTask = Task { @MainActor in
                    try? await Task.sleep(nanoseconds: pingTimeoutNanoseconds)
                    ignoredPingIds.insert(requestId)
                    completePingIfNeeded(requestId: requestId, success: false)
                }
            }
        } catch {
            return false
        }
    }
    
    /// Reconnects to the backend
    func reconnect() async {
        disconnect()
        await connect()
    }

    private func authenticateAndNegotiate() async throws {
        guard let authToken, !authToken.isEmpty else {
            throw IPCRequestError.authConfigMissing
        }

        let requestPid = Int(ProcessInfo.processInfo.processIdentifier)
        var authParams: [String: AnyCodable] = [
            "protocol_version": AnyCodable(expectedProtocolVersion),
            "client_name": AnyCodable("AIAgentUI"),
            "client_pid": AnyCodable(requestPid),
            "auth_token": AnyCodable(authToken),
        ]
        if let rotationToken {
            authParams["rotation_token"] = AnyCodable(rotationToken)
        }
        let content = try await sendRPC(
            method: "auth.hello",
            params: authParams
        )
        let auth = try decodeJSONPayload(content, as: IPCAuthHelloResponse.self)
        guard auth.authenticated else {
            throw IPCRequestError.backend(message: "Backend rejected auth.hello", code: nil)
        }
        guard auth.protocolVersion == expectedProtocolVersion else {
            throw IPCRequestError.protocolMismatch(
                expected: expectedProtocolVersion,
                actual: auth.protocolVersion
            )
        }
        let featureSet = Set(auth.features)
        let missing = requiredBackendFeatures.subtracting(featureSet).sorted()
        if !missing.isEmpty {
            throw IPCRequestError.missingFeatures(missing)
        }

        // Store new rotation token for next reconnect.
        rotationToken = auth.rotationToken

        isAuthenticatedTransport = true
        negotiatedProtocolVersion = auth.protocolVersion
        isConnected = true
        lastError = nil
        emitStatusChange(.idle, nil)
    }
    
    // MARK: - Private Handlers
    
    private func handleStateChange(_ state: SocketManager.ConnectionState) {
        DebugLogger.log("ipc_state_change", fields: ["state": String(describing: state)])
        switch state {
        case .connected:
            if isAuthenticatedTransport {
                isConnected = true
                lastError = nil
                emitStatusChange(.idle, nil)
            } else {
                isConnected = false
                emitStatusChange(.connecting, "Authenticating IPC session...")
            }
            
        case .disconnected:
            isAuthenticatedTransport = false
            negotiatedProtocolVersion = nil
            isConnected = false
            isStreaming = false
            isCancellationPending = false
            cancellationPendingRequestId = nil
            currentRequestId = nil
            if let pendingPingId = pendingPingId {
                ignoredPingIds.insert(pendingPingId)
                completePingIfNeeded(requestId: pendingPingId, success: false)
            }
            failAllPendingRPCs(IPCRequestError.disconnected)
            
        case .connecting:
            emitStatusChange(.connecting, nil)
            
        case .failed(let error):
            isAuthenticatedTransport = false
            negotiatedProtocolVersion = nil
            isConnected = false
            isStreaming = false
            isCancellationPending = false
            cancellationPendingRequestId = nil
            if let pendingPingId = pendingPingId {
                ignoredPingIds.insert(pendingPingId)
                completePingIfNeeded(requestId: pendingPingId, success: false)
            }
            failAllPendingRPCs(IPCRequestError.backend(message: error, code: nil))
            handleError(error)
        }
    }
    
    private func handleStatusUpdate(_ status: AgentStatus, requestId: String, detail: String?) {
        // Only handle updates for our current request
        guard let activeRequestId = currentRequestId, requestId == activeRequestId else { return }
        guard cancellationPendingRequestId != requestId else { return }
        
        emitStatusChange(status, detail)
        
        // Update streaming state based on status
        switch status {
        case .streaming:
            isStreaming = true
        case .complete, .error, .idle, .planReady:
            isStreaming = false
        default:
            break
        }
    }
    
    private func handleStreamingUpdate(requestId: String, delta: String, text: String, isDone: Bool) {
        guard let activeRequestId = currentRequestId, requestId == activeRequestId else { return }
        guard cancellationPendingRequestId != requestId else { return }

        let isTextChanged = streamingText != text
        if isTextChanged {
            streamingText = text
        }
        if isTextChanged || isDone {
            onStreamUpdate?(delta, text, isDone)
        }
        
        if isDone {
            isStreaming = false
        }
    }
    
    private func handleToolCall(_ toolCall: ToolCall, requestId: String) {
        guard let activeRequestId = currentRequestId, requestId == activeRequestId else { return }
        guard cancellationPendingRequestId != requestId else { return }
        
        onToolCall?(toolCall)
        switch toolCall.status {
        case .pending, .executing:
            emitStatusChange(.callingTool(toolName: toolCall.name), "Using \(toolCall.name)")
        case .success, .failed:
            break
        }
    }
    
    private func handleComplete(requestId: String, content: String?) {
        if ignoredPingIds.remove(requestId) != nil {
            logRequestCompletion(requestId: requestId, kind: "ping_ignored", error: nil)
            return
        }
        if let pendingPingId = pendingPingId, pendingPingId == requestId {
            completePingIfNeeded(requestId: requestId, success: true)
            logRequestCompletion(requestId: requestId, kind: "ping", error: nil)
            return
        }
        if let continuation = pendingRPCContinuations.removeValue(forKey: requestId) {
            clearRPCTimeout(for: requestId)
            logRequestCompletion(requestId: requestId, kind: "rpc", error: nil)
            continuation.resume(returning: content ?? "")
            return
        }
        
        // Log completion to cleanup timing tracking regardless of active status
        logRequestCompletion(requestId: requestId, kind: "prompt", error: nil)
        
        guard let activeRequestId = currentRequestId, requestId == activeRequestId else { return }

        if cancellationPendingRequestId == requestId {
            isStreaming = false
            isCancellationPending = false
            cancellationPendingRequestId = nil
            currentRequestId = nil
            onCancelled?()
            emitStatusChange(.idle, nil)
            return
        }
        
        isStreaming = false
        isCancellationPending = false
        cancellationPendingRequestId = nil
        currentRequestId = nil
        onComplete?(content)
        emitStatusChange(.complete, nil)
    }

    private func emitStatusChange(_ status: AgentStatus, _ detail: String?) {
        let normalizedDetail = detail?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let signature = "\(status.signatureKey)|\(normalizedDetail)"
        guard lastDeliveredStatusSignature != signature else { return }
        lastDeliveredStatusSignature = signature
        onStatusChange?(status, normalizedDetail.isEmpty ? nil : normalizedDetail)
    }
    
    private func _asString(_ value: Any?) -> String? {
        guard let value else { return nil }
        if let string = value as? String {
            let trimmed = string.trimmingCharacters(in: .whitespacesAndNewlines)
            return trimmed.isEmpty ? nil : trimmed
        }
        return nil
    }

    private func _asDouble(_ value: Any?) -> Double? {
        if let value = value as? Double {
            return value.isFinite ? value : nil
        }
        if let value = value as? Int {
            return Double(value)
        }
        if let value = value as? String {
            let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
            guard let parsed = Double(trimmed), parsed.isFinite else { return nil }
            return parsed
        }
        return nil
    }

    private func parseRequestTimeoutPayload(
        requestId: String?,
        code: Int?,
        data: [String: Any]?,
        normalizedMessage: String
    ) -> IPCRequestTimeoutPayload? {
        let isTimeoutCode = (code == requestTimeoutErrorCode)
        let dataCode = _asString(data?["code"])
        let dataLooksLikeTimeout = (dataCode?.hasSuffix("_timeout") == true)
        guard isTimeoutCode || dataLooksLikeTimeout else { return nil }

        let resolvedRequestId = _asString(data?["request_id"])
            ?? requestId?.trimmingCharacters(in: .whitespacesAndNewlines)
            ?? "global"
        let resolvedCode = dataCode ?? "request_timeout"
        let phase = _asString(data?["phase"]) ?? "request"
        let operation = _asString(data?["operation"]) ?? "unknown"
        let timeoutSeconds = _asDouble(data?["timeout_seconds"])
        let elapsedSeconds = _asDouble(data?["elapsed_seconds"])
        let userMessage = _asString(data?["user_message"]) ?? normalizedMessage
        return IPCRequestTimeoutPayload(
            requestId: resolvedRequestId,
            code: resolvedCode,
            phase: phase,
            operation: operation,
            timeoutSeconds: timeoutSeconds,
            elapsedSeconds: elapsedSeconds,
            userMessage: userMessage
        )
    }

    private func handleError(
        _ message: String,
        requestId: String? = nil,
        code: Int? = nil,
        data: [String: Any]? = nil
    ) {
        let normalizedMessage: String = {
            let trimmed = message.trimmingCharacters(in: .whitespacesAndNewlines)
            return trimmed.isEmpty ? "Unknown backend error." : trimmed
        }()
        let userVisibleMessage: String = {
            guard let code else { return normalizedMessage }
            let hasCode = normalizedMessage.contains("(\(code))")
                || normalizedMessage.contains("code \(code)")
            if hasCode {
                return normalizedMessage
            }
            return "Backend error (\(code)): \(normalizedMessage)"
        }()
        let timeoutPayload = parseRequestTimeoutPayload(
            requestId: requestId,
            code: code,
            data: data,
            normalizedMessage: normalizedMessage
        )

        if let requestId = requestId,
           let pendingPingId = pendingPingId,
           pendingPingId == requestId {
            completePingIfNeeded(requestId: requestId, success: false)
            logRequestCompletion(requestId: requestId, kind: "ping", error: userVisibleMessage)
            return
        }
        if let requestId = requestId, ignoredPingIds.remove(requestId) != nil {
            logRequestCompletion(requestId: requestId, kind: "ping_ignored", error: userVisibleMessage)
            return
        }
        if let requestId = requestId,
           let continuation = pendingRPCContinuations.removeValue(forKey: requestId) {
            clearRPCTimeout(for: requestId)
            logRequestCompletion(requestId: requestId, kind: "rpc", error: normalizedMessage)
            continuation.resume(throwing: IPCRequestError.backend(message: normalizedMessage, code: code))
            return
        }
        
        // Cleanup timing for prompt requests
        if let requestId = requestId {
             logRequestCompletion(requestId: requestId, kind: "prompt", error: normalizedMessage)
        }

        let isGlobalError = requestId == nil || requestId == "" || requestId == "global"
        // Ignore request-scoped errors unless they target the current request.
        if let requestId = requestId, !isGlobalError {
            guard let activeRequestId = currentRequestId, requestId == activeRequestId else {
                return
            }
        }

        if let timeoutPayload {
            onRequestTimeout?(timeoutPayload)
        }

        let normalizedLower = normalizedMessage.lowercased()
        let isCancellation = code == -32800
            || normalizedLower.contains("request cancelled by user")
            || normalizedLower.contains("request canceled by user")

        if isGlobalError || requestId == currentRequestId {
            currentRequestId = nil
        }
        if requestId == cancellationPendingRequestId || isCancellation {
            cancellationPendingRequestId = nil
            isCancellationPending = false
        }
        if isCancellation {
            lastError = nil
            isStreaming = false
            onCancelled?()
            emitStatusChange(.idle, nil)
            return
        }

        lastError = userVisibleMessage
        isStreaming = false
        onError?(userVisibleMessage)
        emitStatusChange(.error(message: userVisibleMessage), userVisibleMessage)
    }

    private func handleSystemMessage(_ response: SystemResponse, requestId: String) {
        _ = requestId
        guard response.system.event == "lifecycle" else { return }
        guard let domain = response.system.domain?.trimmingCharacters(in: .whitespacesAndNewlines),
              let action = response.system.action?.trimmingCharacters(in: .whitespacesAndNewlines),
              !domain.isEmpty,
              !action.isEmpty else {
            return
        }
        let payload = response.system.payload?.mapValues { $0.value } ?? [:]
        onSystemEvent?(
            IPCSystemEvent(
                domain: domain,
                action: action,
                payload: payload,
                seq: response.system.seq
            )
        )
    }
    
    private func completePingIfNeeded(requestId: String, success: Bool) {
        guard pendingPingId == requestId else { return }
        pendingPingId = nil
        pendingPingTimeoutTask?.cancel()
        pendingPingTimeoutTask = nil
        if let continuation = pendingPingContinuation {
            pendingPingContinuation = nil
            continuation.resume(returning: success)
        }
    }

    private func sendRPC(method: String, params: [String: AnyCodable]) async throws -> String {
        guard socketManager.state == .connected else {
            throw IPCRequestError.notConnected
        }
        let correlationId = UUID().uuidString
        var finalParams = params
        if finalParams["correlation_id"] == nil {
            finalParams["correlation_id"] = AnyCodable(correlationId)
        }
        let request = IPCRequest(method: method, params: finalParams)
        let data = try JSONEncoder().encode(request)
        guard let payload = String(data: data, encoding: .utf8) else {
            throw IPCRequestError.invalidPayload("Could not encode request payload.")
        }
        let requestId = request.id
        requestStartTimes[requestId] = Date()
        DebugLogger.log(
            "rpc_send",
            fields: [
                "method": method,
                "request_id": requestId,
                "correlation_id": correlationId,
            ]
        )
        return try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<String, Error>) in
            pendingRPCContinuations[requestId] = continuation
            scheduleRPCTimeout(requestId: requestId, method: method)
            // Register continuation before write to avoid fast-response races.
            Task { @MainActor in
                do {
                    try await socketManager.send(payload)
                } catch {
                    if let pending = pendingRPCContinuations.removeValue(forKey: requestId) {
                        clearRPCTimeout(for: requestId)
                        requestStartTimes.removeValue(forKey: requestId)
                        pending.resume(throwing: error)
                    }
                }
            }
        }
    }

    private func decodeJSONPayload<T: Decodable>(_ content: String, as type: T.Type) throws -> T {
        guard let data = content.data(using: .utf8) else {
            throw IPCRequestError.invalidPayload("Response is not UTF-8.")
        }
        do {
            return try JSONDecoder().decode(type, from: data)
        } catch {
            throw IPCRequestError.invalidPayload(error.localizedDescription)
        }
    }

    private func scheduleRPCTimeout(requestId: String, method: String) {
        pendingRPCTimeoutTasks[requestId]?.cancel()
        let timeout = rpcTimeoutNanoseconds(for: method)
        pendingRPCTimeoutTasks[requestId] = Task { @MainActor [weak self, timeout] in
            try? await Task.sleep(nanoseconds: timeout)
            guard let self else { return }
            guard let continuation = self.pendingRPCContinuations.removeValue(forKey: requestId) else {
                self.pendingRPCTimeoutTasks.removeValue(forKey: requestId)
                return
            }
            self.pendingRPCTimeoutTasks.removeValue(forKey: requestId)
            self.logRequestCompletion(
                requestId: requestId,
                kind: "rpc",
                error: "timeout waiting for \(method)"
            )
            continuation.resume(throwing: IPCRequestError.timeout(method: method))
        }
    }

    private func rpcTimeoutNanoseconds(for method: String) -> UInt64 {
        switch method {
        case "session.delete", "session.delete_many":
            return sessionDeleteRPCTimeoutNanoseconds
        default:
            return defaultRPCTimeoutNanoseconds
        }
    }

    private func clearRPCTimeout(for requestId: String) {
        pendingRPCTimeoutTasks[requestId]?.cancel()
        pendingRPCTimeoutTasks.removeValue(forKey: requestId)
    }

    private func failAllPendingRPCs(_ error: Error) {
        if pendingRPCContinuations.isEmpty {
            return
        }
        let continuations = pendingRPCContinuations.values
        pendingRPCContinuations.removeAll()
        let timeoutTasks = pendingRPCTimeoutTasks.values
        pendingRPCTimeoutTasks.removeAll()
        for task in timeoutTasks {
            task.cancel()
        }
        for continuation in continuations {
            continuation.resume(throwing: error)
        }
        requestStartTimes.removeAll()
    }

    private func logRequestCompletion(requestId: String, kind: String, error: String?) {
        let started = requestStartTimes.removeValue(forKey: requestId)
        let durationMs: String = {
            guard let started else { return "unknown" }
            return String(format: "%.1f", Date().timeIntervalSince(started) * 1000.0)
        }()
        var fields: [String: String] = [
            "kind": kind,
            "request_id": requestId,
            "duration_ms": durationMs,
        ]
        if let error {
            fields["error"] = error
        }
        DebugLogger.log("request_complete", fields: fields)
    }
}

// MARK: - Mock Client for Previews

#if DEBUG
extension IPCClient {
    /// Creates a mock client for SwiftUI previews
    static var mock: IPCClient {
        let client = IPCClient()
        // Mock is disconnected by default
        return client
    }
    
    /// Creates a mock client that simulates being connected
    static var mockConnected: IPCClient {
        let client = IPCClient()
        // Note: In a real mock, we'd set up fake data
        return client
    }
}
#endif
