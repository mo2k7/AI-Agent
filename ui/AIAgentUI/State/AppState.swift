//
//  AppState.swift
//  AIAgentUI
//
//  Created for Personal macOS AI Agent
//  Status: Active - Singleton state management
//

import SwiftUI
import Combine
import Darwin

enum SessionMemoryMode: String, CaseIterable, Identifiable {
    case on
    case off
    case ephemeral

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .on:
            return "Persistent"
        case .off:
            return "Off"
        case .ephemeral:
            return "Ephemeral"
        }
    }

    var description: String {
        switch self {
        case .on:
            return "Encrypted local memory + cross-session semantic retrieval."
        case .off:
            return "Semantic memory is disabled for new prompts."
        case .ephemeral:
            return "Semantic memory is kept only while the app is running."
        }
    }
}

enum ResponseVerbosity: String, CaseIterable, Identifiable {
    case low
    case medium
    case high
    case extraHigh = "extra_high"

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .low:
            return "Low"
        case .medium:
            return "Medium"
        case .high:
            return "High"
        case .extraHigh:
            return "Extra High"
        }
    }

    var description: String {
        switch self {
        case .low:
            return "Compact replies for faster skim."
        case .medium:
            return "Balanced detail and readability."
        case .high:
            return "Richer explanations with more context."
        case .extraHigh:
            return "Deep-dive responses with alternatives and verification detail."
        }
    }
}

enum ResponsePresentationStyle: String, CaseIterable, Identifiable {
    case readablePro = "readable_pro"
    case glassEditorial = "glass_editorial"
    case denseTechnical = "dense_technical"

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .readablePro:
            return "Readable Pro"
        case .glassEditorial:
            return "Glass Editorial"
        case .denseTechnical:
            return "Dense Technical"
        }
    }

    var description: String {
        switch self {
        case .readablePro:
            return "High-clarity hierarchy with clean spacing and scan-friendly structure."
        case .glassEditorial:
            return "Premium layered cards with richer accents and visual depth."
        case .denseTechnical:
            return "Compact, information-dense presentation optimized for technical reading."
        }
    }
}

enum StreamingAnimationStyle: String, CaseIterable, Identifiable {
    case waveReveal = "wave_reveal"
    case typewriterLuxe = "typewriter_luxe"
    case minimalMotion = "minimal_motion"

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .waveReveal:
            return "Wave Reveal"
        case .typewriterLuxe:
            return "Typewriter Luxe"
        case .minimalMotion:
            return "Minimal Motion"
        }
    }

    var description: String {
        switch self {
        case .waveReveal:
            return "Smooth chunk reveal with a subtle progress accent."
        case .typewriterLuxe:
            return "Decorative staged reveal with soft pulse highlights."
        case .minimalMotion:
            return "Low-distraction updates with restrained transitions."
        }
    }
}

enum ExecutionMode: String, CaseIterable, Identifiable {
    case direct
    case plan
    case teacher

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .direct:
            return "Direct"
        case .plan:
            return "Plan"
        case .teacher:
            return "Teacher"
        }
    }

    var description: String {
        switch self {
        case .direct:
            return "Execute requests directly with confirmations for destructive actions."
        case .plan:
            return "Planning-only mode. Build plans without executing destructive tools."
        case .teacher:
            return "Teaches interactively while autonomously capturing structured study notes and highlights."
        }
    }

    var badgeText: String {
        switch self {
        case .direct:
            return "DIRECT"
        case .plan:
            return "PLAN"
        case .teacher:
            return "TEACHER"
        }
    }
}

struct SessionListItem: Identifiable, Equatable {
    let sessionId: String
    let title: String
    let memoryMode: SessionMemoryMode
    let updatedAt: Double
    let status: String

    var id: String { sessionId }

    var shortLabel: String {
        if title.count > 28 {
            return String(title.prefix(27)) + "…"
        }
        return title
    }

    init(from payload: IPCSessionSummary) {
        self.sessionId = payload.sessionId
        self.title = payload.title
        self.memoryMode = SessionMemoryMode(rawValue: payload.memoryMode) ?? .on
        self.updatedAt = payload.updatedAt
        self.status = payload.status
    }

    init(from payload: IPCCreatedSession) {
        self.sessionId = payload.sessionId
        self.title = payload.title
        self.memoryMode = SessionMemoryMode(rawValue: payload.memoryMode) ?? .on
        self.updatedAt = payload.createdAt
        self.status = "active"
    }

    init(
        sessionId: String,
        title: String,
        memoryMode: SessionMemoryMode,
        updatedAt: Double,
        status: String
    ) {
        self.sessionId = sessionId
        self.title = title
        self.memoryMode = memoryMode
        self.updatedAt = updatedAt
        self.status = status
    }

    func with(memoryMode: SessionMemoryMode) -> SessionListItem {
        SessionListItem(
            sessionId: sessionId,
            title: title,
            memoryMode: memoryMode,
            updatedAt: updatedAt,
            status: status
        )
    }
}

/// Global application state singleton
/// Manages all state that needs to be shared across the application
@MainActor
final class AppState: ObservableObject {
    
    // MARK: - Singleton Instance
    
    /// Shared singleton instance
    static let shared = AppState()
    
    // MARK: - Published State
    
    /// Current startup phase
    @Published var startupPhase: StartupPhase = .initializing
    
    /// Current agent operational status
    @Published var status: AgentStatus = .idle

    /// Human-readable detail for the current status.
    @Published var statusDetail: String = ""
    
    /// All messages in the conversation
    @Published var messages: [Message] = []
    
    /// Current text in the input field
    @Published var currentInput: String = ""

    /// Currently selected Gemini model
    @Published var selectedModel: GeminiModel = .gemini3FlashPreview {
        didSet {
            guard selectedModel != oldValue else { return }
            UserDefaults.standard.set(selectedModel.rawValue, forKey: Self.selectedModelKey)
        }
    }

    /// Current memory mode for prompts in the active session
    @Published var memoryMode: SessionMemoryMode = .on {
        didSet {
            guard memoryMode != oldValue else { return }
            UserDefaults.standard.set(memoryMode.rawValue, forKey: Self.memoryModeKey)
            backendLogs.append("[MEMORY] Mode set to '\(memoryMode.rawValue)'")
            if backendLogs.count > 100 {
                backendLogs.removeFirst()
            }
        }
    }

    /// Current response verbosity for all outgoing prompts
    @Published var responseVerbosity: ResponseVerbosity = .medium {
        didSet {
            guard responseVerbosity != oldValue else { return }
            UserDefaults.standard.set(responseVerbosity.rawValue, forKey: Self.responseVerbosityKey)
            backendLogs.append("[VERBOSITY] Set to '\(responseVerbosity.rawValue)'")
            if backendLogs.count > 100 {
                backendLogs.removeFirst()
            }
        }
    }

    /// Whether deeper reasoning mode is enabled for outgoing prompts.
    @Published var deepThinkEnabled: Bool = false {
        didSet {
            guard deepThinkEnabled != oldValue else { return }
            UserDefaults.standard.set(deepThinkEnabled, forKey: Self.deepThinkKey)
            backendLogs.append("[DEEP_THINK] \(deepThinkEnabled ? "enabled" : "disabled")")
            if backendLogs.count > 100 {
                backendLogs.removeFirst()
            }
        }
    }

    /// Visual presentation style for rendered assistant responses.
    @Published var responsePresentationStyle: ResponsePresentationStyle = .readablePro {
        didSet {
            guard responsePresentationStyle != oldValue else { return }
            UserDefaults.standard.set(
                responsePresentationStyle.rawValue,
                forKey: Self.responsePresentationStyleKey
            )
            backendLogs.append("[PRESENTATION] Style set to '\(responsePresentationStyle.rawValue)'")
            if backendLogs.count > 100 {
                backendLogs.removeFirst()
            }
        }
    }

    /// Additional contrast boost for the Readable Pro presentation style.
    @Published var readableProHighContrastEnabled: Bool = true {
        didSet {
            guard readableProHighContrastEnabled != oldValue else { return }
            UserDefaults.standard.set(
                readableProHighContrastEnabled,
                forKey: Self.readableProHighContrastKey
            )
            let state = readableProHighContrastEnabled ? "enabled" : "disabled"
            backendLogs.append("[PRESENTATION] Readable Pro high contrast \(state)")
            if backendLogs.count > 100 {
                backendLogs.removeFirst()
            }
        }
    }

    /// Streaming animation style for in-progress assistant responses.
    @Published var streamingAnimationStyle: StreamingAnimationStyle = .waveReveal {
        didSet {
            guard streamingAnimationStyle != oldValue else { return }
            UserDefaults.standard.set(
                streamingAnimationStyle.rawValue,
                forKey: Self.streamingAnimationStyleKey
            )
            backendLogs.append("[STREAM_ANIMATION] Style set to '\(streamingAnimationStyle.rawValue)'")
            if backendLogs.count > 100 {
                backendLogs.removeFirst()
            }
        }
    }

    /// Prompt execution mode for new requests.
    @Published var executionMode: ExecutionMode = .direct {
        didSet {
            guard executionMode != oldValue else { return }
            UserDefaults.standard.set(executionMode.rawValue, forKey: Self.executionModeKey)
            backendLogs.append("[EXECUTION_MODE] Set to '\(executionMode.rawValue)'")
            if backendLogs.count > 100 {
                backendLogs.removeFirst()
            }
        }
    }

    /// Session currently bound to new prompts
    @Published var activeSessionId: String = "" {
        didSet {
            guard activeSessionId != oldValue else { return }
            UserDefaults.standard.set(activeSessionId, forKey: Self.activeSessionIdKey)
        }
    }

    /// Human-readable title for the active session
    @Published var activeSessionTitle: String = "New Session"

    /// Available sessions retrieved from backend storage
    @Published var sessions: [SessionListItem] = []

    /// Whether message history is currently loading for the active session
    @Published private(set) var isSessionHistoryLoading: Bool = false

    /// Whether a prompt submission is currently being prepared/sent
    @Published private(set) var isSendingPrompt: Bool = false
    
    /// Current tool call being displayed
    @Published var currentToolCall: ToolCall?

    /// Pending destructive tool call awaiting explicit user confirmation.
    @Published var pendingDestructiveToolCall: ToolCall?
    
    /// Whether the tool call details are expanded
    @Published var isToolCallExpanded: Bool = true
    
    /// Whether the floating panel is visible
    @Published var isPanelVisible: Bool = true
    
    /// Accumulated streaming text for the current response
    @Published var streamingText: String = ""
    
    /// Whether the app is currently connected to the backend
    @Published var isConnected: Bool = false
    
    /// Last error message
    @Published var lastError: String?
    
    /// Backend server logs (for debugging)
    @Published var backendLogs: [String] = []

    /// User-selected file paths dropped into the UI and attached to new prompts.
    @Published var droppedFilePaths: [String] = []

    /// Notes for the active session.
    @Published var notes: [Note] = []

    /// Whether the notes panel is currently visible.
    @Published var isNotesPanelVisible: Bool = false

    /// Whether notes are being loaded from the backend.
    @Published private(set) var isNotesLoading: Bool = false

    /// In-memory cache for note images (image_id → NSImage).
    var noteImageCache: [String: NSImage] = [:]

    // MARK: - Private Properties
    
    /// IPC client for backend communication
    private let ipcClient: IPCClient
    
    /// Backend launcher for process management
    private let backendLauncher: BackendLauncher
    
    /// Cancellables for Combine subscriptions
    private var cancellables = Set<AnyCancellable>()

    private struct PendingSessionModeUpdate {
        let token: UInt64
        let desiredMode: SessionMemoryMode
        var rollbackMode: SessionMemoryMode
    }

    /// ID of the message currently being streamed to
    private var streamingMessageId: UUID?

    /// Cached index of the currently streaming message (fast path for hot update loop).
    private var streamingMessageIndex: Int?

    /// Execution mode used by the currently in-flight prompt, if any.
    private var activePromptExecutionMode: ExecutionMode?
    
    /// Whether the backend was started by this app
    private var backendStartedByApp: Bool = false

    /// UserDefaults key for persisted model selection
    private static let selectedModelKey = "selectedModel"
    private static let memoryModeKey = "memoryMode"
    private static let responseVerbosityKey = "responseVerbosity"
    private static let deepThinkKey = "deepThinkEnabled"
    private static let responsePresentationStyleKey = "responsePresentationStyle"
    private static let readableProHighContrastKey = "readableProHighContrastEnabled"
    private static let streamingAnimationStyleKey = "streamingAnimationStyle"
    private static let executionModeKey = "executionMode"
    private static let activeSessionIdKey = "activeSessionId"
    private static let autoConnectKey = "autoConnect"
    private static let reconnectOnFailureKey = "reconnectOnFailure"
    private static let maxDroppedFilePaths = 100
    private static let autoSessionCreateCooldownSeconds: TimeInterval = 2.0
    private var isBootstrappingSessions = false
    private var isRefreshingSessions = false
    private var pendingSessionRefreshAllowAutoCreate = false
    private var lastAutoCreatedSessionAt: Date?
    private var pendingHistoryLoadToken = UUID()
    private var completeResetTask: Task<Void, Never>?
    private var toolCallCleanupTask: Task<Void, Never>?
    private var reconnectTask: Task<Void, Never>?
    private var reconnectAttemptCount: Int = 0
    private var isManualDisconnect = false
    private var startupInFlight = false
    private var sessionModeUpdateCounter: UInt64 = 0
    private var pendingSessionModeUpdates: [String: PendingSessionModeUpdate] = [:]
    private var lastKnownSessionModes: [String: SessionMemoryMode] = [:]
    private var reconciliationTask: Task<Void, Never>?
    private var pendingRealtimeRefreshTask: Task<Void, Never>?
    private var pendingRealtimeRefreshIncludeNotes = false
    private var lastRealtimeRefreshAt: Date = .distantPast
    private let realtimePollIntervalNanoseconds: UInt64 = 5_000_000_000
    private let realtimeRefreshDebounceNanoseconds: UInt64 = 200_000_000
    
    // MARK: - Initialization
    
    private init() {
        self.ipcClient = IPCClient()
        self.backendLauncher = BackendLauncher()
        self.selectedModel = Self.loadSelectedModel()
        self.memoryMode = Self.loadMemoryMode()
        self.responseVerbosity = Self.loadResponseVerbosity()
        self.deepThinkEnabled = Self.loadDeepThinkEnabled()
        self.responsePresentationStyle = Self.loadResponsePresentationStyle()
        self.readableProHighContrastEnabled = Self.loadReadableProHighContrastEnabled()
        self.streamingAnimationStyle = Self.loadStreamingAnimationStyle()
        self.executionMode = Self.loadExecutionMode()
        self.activeSessionId = Self.loadActiveSessionId()
        setupBindings()
        setupBackendCallbacks()
    }
    
    /// Sets up bindings between IPC client and app state
    private func setupBindings() {
        // Connection status binding
        ipcClient.$isConnected
            .receive(on: DispatchQueue.main)
            .sink { [weak self] isConnected in
                let wasConnected = self?.isConnected ?? false
                self?.isConnected = isConnected
                if isConnected {
                    self?.cancelReconnectLoop()
                    self?.isManualDisconnect = false
                    self?.status = .idle
                    self?.statusDetail = ""
                    self?.lastError = nil
                    self?.startupPhase = .ready
                    self?.startReconciliationLoopIfNeeded()
                    Task { @MainActor [weak self] in
                        await self?.bootstrapSessionsIfNeeded()
                    }
                } else {
                    self?.stopReconciliationLoop()
                    self?.resetDisconnectedUIState()
                    self?.scheduleReconnectIfEligible(wasConnected: wasConnected)
                }
            }
            .store(in: &cancellables)
        
        // Error binding
        ipcClient.$lastError
            .receive(on: DispatchQueue.main)
            .sink { [weak self] error in
                if let error = error {
                    self?.lastError = error
                    self?.status = .error(message: error)
                    self?.statusDetail = error
                }
            }
            .store(in: &cancellables)
        
        // Set up IPC callbacks
        setupIPCCallbacks()
    }
    
    private func setupIPCCallbacks() {
        ipcClient.onStatusChange = { [weak self] status, detail in
            self?.status = status
            self?.statusDetail = self?.effectiveStatusDetail(for: status, detail: detail) ?? ""

            // Auto-trigger screen capture when backend requests it
            if case .capturingScreen = status {
                self?.handleScreenCaptureRequest()
            }
        }
        
        ipcClient.onStreamUpdate = { [weak self] text, isDone in
            self?.streamingText = text
            self?.updateStreamingMessage(with: text)
            if isDone {
                self?.finalizeStreamingMessage()
            }
        }
        
        ipcClient.onToolCall = { [weak self] toolCall in
            self?.handleToolCallUpdate(toolCall)
        }
        
        ipcClient.onComplete = { [weak self] content in
            self?.handleComplete(content: content)
        }
        
        ipcClient.onError = { [weak self] error in
            self?.lastError = error
            self?.status = .error(message: error)
            self?.statusDetail = error
            self?.activePromptExecutionMode = nil
            self?.markCurrentToolCallFailedIfNeeded(message: error)
            self?.finalizeStreamingMessage(removeIfEmpty: true)
            self?.scheduleToolCallCleanup(after: 2.0)
            if self?.isUnknownSessionError(error) == true {
                Task { @MainActor [weak self] in
                    await self?.recoverFromUnknownSessionError()
                }
            }
        }

        ipcClient.onSystemEvent = { [weak self] event in
            Task { @MainActor [weak self] in
                await self?.handleSystemEvent(event)
            }
        }
    }

    private func setupBackendCallbacks() {
        backendLauncher.onStateChange = { [weak self] state in
            Task { @MainActor in
                switch state {
                case .notStarted:
                    break
                case .starting:
                    self?.startupPhase = .startingBackend
                case .running:
                    self?.startupPhase = .connectingToBackend
                case .failed(let message):
                    self?.startupPhase = .failed(message)
                case .terminated:
                    if self?.backendStartedByApp == true {
                        self?.isConnected = false
                        self?.startupPhase = .failed("Backend server stopped unexpectedly")
                    }
                }
            }
        }
        
        backendLauncher.onServerReady = { [weak self] context in
            Task { @MainActor in
                guard let self = self else { return }
                do {
                    try await self.connectToSocket(path: context.socketPath, authToken: context.authToken)
                } catch {
                    self.startupPhase = .failed("Could not connect to backend: \(error.localizedDescription)")
                }
            }
        }
        
        backendLauncher.onLogOutput = { [weak self] log in
            Task { @MainActor in
                self?.backendLogs.append(log)
                // Keep only last 100 logs
                if self?.backendLogs.count ?? 0 > 100 {
                    self?.backendLogs.removeFirst()
                }
            }
        }
        
        backendLauncher.onErrorOutput = { [weak self] error in
            Task { @MainActor in
                self?.backendLogs.append("[ERROR] \(error)")
            }
        }
    }
    
    // MARK: - Startup Methods
    
    /// Starts the application (called on app launch)
    func startup() async {
        guard !startupInFlight else { return }
        startupInFlight = true
        defer { startupInFlight = false }

        isManualDisconnect = false
        cancelReconnectLoop()
        startupPhase = .initializing
        
        // Small delay for UI to render
        try? await Task.sleep(nanoseconds: 300_000_000)  // 300ms

        guard Self.loadBoolSetting(key: Self.autoConnectKey, defaultValue: true) else {
            startupPhase = .ready
            status = .idle
            return
        }
        
        // First, try to connect to an existing backend
        startupPhase = .connectingToBackend

        let envSocketPath = ProcessInfo.processInfo.environment["AI_AGENT_SOCKET_PATH"]?.trimmingCharacters(
            in: .whitespacesAndNewlines
        )
        let envAuthToken = ProcessInfo.processInfo.environment["AI_AGENT_IPC_AUTH_TOKEN"]?
            .trimmingCharacters(in: .whitespacesAndNewlines)
        if let envSocketPath, !envSocketPath.isEmpty {
            do {
                guard let envAuthToken, !envAuthToken.isEmpty else {
                    throw IPCRequestError.authConfigMissing
                }
                try await connectToSocket(path: envSocketPath, authToken: envAuthToken)
                return
            } catch {
                backendLogs.append("[STARTUP] Failed env socket \(envSocketPath): \(error.localizedDescription)")
                if backendLogs.count > 100 {
                    backendLogs.removeFirst()
                }
            }
        }
        
        if shouldAttachToExistingBackend() {
            let existingSocket = findExistingSocket()
            if let socketPath = existingSocket {
                do {
                    let token = ProcessInfo.processInfo.environment["AI_AGENT_IPC_AUTH_TOKEN"]?
                        .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
                    guard !token.isEmpty else {
                        throw IPCRequestError.authConfigMissing
                    }
                    try await connectToSocket(path: socketPath, authToken: token)
                    return  // Successfully connected to existing backend
                } catch {
                    // Fall through to start a new backend
                }
            }
        } else {
            backendLogs.append(
                "[STARTUP] Skipping auto-attach to existing sockets; starting isolated backend."
            )
            if backendLogs.count > 100 {
                backendLogs.removeFirst()
            }
        }
        
        // No existing backend found, start our own
        await startBackend()
    }
    
    /// Starts the Python backend server
    private func startBackend() async {
        startupPhase = .startingBackend
        backendStartedByApp = true
        
        do {
            let envSocketPath = ProcessInfo.processInfo.environment["AI_AGENT_SOCKET_PATH"]?.trimmingCharacters(
                in: .whitespacesAndNewlines
            )
            if let envSocketPath, !envSocketPath.isEmpty {
                try await backendLauncher.start(customSocketPath: envSocketPath)
            } else {
                try await backendLauncher.start()
            }
            // Wait for server ready callback to connect
        } catch {
            startupPhase = .failed(error.localizedDescription)
        }
    }
    
    /// Connects to a specific socket path
    private func connectToSocket(path: String, authToken: String) async throws {
        startupPhase = .connectingToBackend
        ipcClient.configureAuthToken(authToken)
        try await ipcClient.connect(toSocketPath: path)
        
        // Perform health check after connecting
        await performHealthCheck()
    }
    
    /// Performs health check to verify the backend is responsive
    private func performHealthCheck() async {
        startupPhase = .performingHealthCheck

        // Allow backend warmup and retry under transient startup or load pressure.
        let attempts = 5
        var delayNs: UInt64 = 200_000_000 // 200ms
        var pingSucceeded = false
        for _ in 0..<attempts {
            try? await Task.sleep(nanoseconds: delayNs)
            if await ipcClient.ping() {
                pingSucceeded = true
                break
            }
            delayNs = min(delayNs * 2, 1_000_000_000) // cap at 1s
        }

        if pingSucceeded {
            startupPhase = .ready
            return
        }

        ipcClient.disconnect()
        startupPhase = .failed(
            "Backend health check failed after retries. Verify backend startup logs and retry."
        )
        lastError = "Health check failed: backend did not respond to ping after \(attempts) attempts"
    }
    
    /// Finds an existing socket in /tmp
    private func findExistingSocket() -> String? {
        let fileManager = FileManager.default
        let tmpURL = URL(fileURLWithPath: "/tmp", isDirectory: true)
        let keys: [URLResourceKey] = [.contentModificationDateKey]
        let currentUID = Int(getuid())

        guard let entries = try? fileManager.contentsOfDirectory(
            at: tmpURL,
            includingPropertiesForKeys: keys,
            options: [.skipsHiddenFiles]
        ) else {
            return nil
        }

        let candidates = entries
            .filter { url in
                let name = url.lastPathComponent
                return name.hasPrefix("ai-agent-") && name.hasSuffix(".sock")
            }
            .filter { isTrustedSocket(path: $0.path, currentUID: currentUID) }
            .sorted { lhs, rhs in
                let lhsDate = (try? lhs.resourceValues(forKeys: Set(keys)).contentModificationDate) ?? .distantPast
                let rhsDate = (try? rhs.resourceValues(forKeys: Set(keys)).contentModificationDate) ?? .distantPast
                return lhsDate > rhsDate
            }

        return candidates.first?.path
    }

    private func isTrustedSocket(path: String, currentUID: Int) -> Bool {
        let fileManager = FileManager.default
        guard let attrs = try? fileManager.attributesOfItem(atPath: path) else {
            return false
        }

        guard let type = attrs[.type] as? FileAttributeType, type == .typeSocket else {
            return false
        }

        if let owner = attrs[.ownerAccountID] as? NSNumber {
            return owner.intValue == currentUID
        }
        return false
    }

    private func shouldAttachToExistingBackend() -> Bool {
        let env = ProcessInfo.processInfo.environment
        guard let raw = env["AI_AGENT_ATTACH_EXISTING_BACKEND"] else {
            return false
        }
        guard Self.parseEnvironmentBool(raw, defaultValue: false) else {
            return false
        }
        let token = env["AI_AGENT_IPC_AUTH_TOKEN"]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if token.isEmpty {
            backendLogs.append(
                "[STARTUP] AI_AGENT_ATTACH_EXISTING_BACKEND is enabled but AI_AGENT_IPC_AUTH_TOKEN is missing. Falling back to managed backend launch."
            )
            if backendLogs.count > 100 {
                backendLogs.removeFirst()
            }
            return false
        }
        return true
    }

    private static func parseEnvironmentBool(_ raw: String, defaultValue: Bool) -> Bool {
        switch raw.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
        case "1", "true", "yes", "on":
            return true
        case "0", "false", "no", "off":
            return false
        default:
            return defaultValue
        }
    }
    
    /// Retries the startup process
    func retryStartup() async {
        isManualDisconnect = false
        cancelReconnectLoop()
        backendLauncher.terminate()
        backendStartedByApp = false
        await startup()
    }
    
    /// Shuts down the backend if we started it
    func shutdown() {
        isManualDisconnect = true
        cancelReconnectLoop()
        if backendStartedByApp {
            backendLauncher.terminate()
        }
        disconnect()
    }
    
    // MARK: - Public Methods
    
    /// Disconnects from the backend
    func disconnect() {
        isManualDisconnect = true
        cancelReconnectLoop()
        stopReconciliationLoop()
        ipcClient.disconnect()
        resetDisconnectedUIState()
    }
    
    /// Sends the current input as a prompt to the agent
    func sendPrompt() async {
        guard !isSendingPrompt else { return }
        guard !isSessionHistoryLoading else { return }
        guard status.canSubmit else { return }
        let prompt = currentInput
        guard !prompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        guard isConnected else {
            let message = "Not connected to backend"
            lastError = message
            status = .error(message: message)
            return
        }
        isSendingPrompt = true
        defer { isSendingPrompt = false }

        guard await ensureActiveSession() else {
            return
        }

        let modelForRequest = selectedModel
        if deepThinkEnabled {
            let normalizedModel = modelForRequest.rawValue.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            let supportsDeepThink = normalizedModel.contains("gemini-3") || normalizedModel.contains("gemini-2.5")
            if !supportsDeepThink {
                let message = "Deep Think requires Gemini 3 or Gemini 2.5. Change model or disable Deep Think."
                lastError = message
                status = .error(message: message)
                return
            }
        }
        let sessionForRequest = activeSessionId
        let memoryModeForRequest = memoryMode.rawValue
        let executionModeForRequest = executionMode.rawValue
        let inputPathsForRequest = droppedFilePaths
        let verbosityForRequest = responseVerbosity.rawValue
        let deepThinkForRequest = deepThinkEnabled
        let presentationStyleForRequest = responsePresentationStyle.rawValue
        let streamingAnimationForRequest = streamingAnimationStyle.rawValue
        completeResetTask?.cancel()
        completeResetTask = nil
        toolCallCleanupTask?.cancel()
        toolCallCleanupTask = nil
        pendingHistoryLoadToken = UUID()
        currentInput = ""
        
        // Add user message
        let userMessage = Message.user(prompt)
        messages.append(userMessage)
        
        // Create placeholder assistant message for streaming
        let assistantMessage = Message.streamingAssistant()
        streamingMessageId = assistantMessage.id
        messages.append(assistantMessage)
        streamingMessageIndex = messages.index(before: messages.endIndex)
        
        // Reset state
        streamingText = ""
        currentToolCall = nil
        activePromptExecutionMode = ExecutionMode(rawValue: executionModeForRequest) ?? executionMode
        let isPlanRequest = executionModeForRequest == ExecutionMode.plan.rawValue
        let isTeacherRequest = executionModeForRequest == ExecutionMode.teacher.rawValue
        status = isPlanRequest ? .planning : .thinking
        if isPlanRequest {
            statusDetail = "Starting plan workflow..."
        } else if isTeacherRequest {
            statusDetail = "Starting teacher mode and autonomous notes..."
        } else {
            statusDetail = "Starting analysis..."
        }

        // Send the prompt with a stable snapshot of the currently selected model.
        // This avoids any race where UI selection changes during request setup.
        backendLogs.append(
            "[MODEL] Prompt model='\(modelForRequest.rawValue)' session='\(sessionForRequest)' memory='\(memoryModeForRequest)' execution_mode='\(executionModeForRequest)' input_paths='\(inputPathsForRequest.count)' verbosity='\(verbosityForRequest)' deep_think='\(deepThinkForRequest)' presentation='\(presentationStyleForRequest)' stream_animation='\(streamingAnimationForRequest)'"
        )
        if backendLogs.count > 100 {
            backendLogs.removeFirst()
        }
        let correlationId = UUID().uuidString
        let requestId = await ipcClient.send(
            prompt: prompt,
            model: modelForRequest.rawValue,
            sessionId: sessionForRequest,
            memoryMode: memoryModeForRequest,
            executionMode: executionModeForRequest,
            inputPaths: inputPathsForRequest,
            verbosity: verbosityForRequest,
            presentationStyle: presentationStyleForRequest,
            streamingAnimation: streamingAnimationForRequest,
            deepThink: deepThinkForRequest,
            correlationId: correlationId
        )
        if requestId == nil {
            activePromptExecutionMode = nil
            if currentInput.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                currentInput = prompt
            }
            finalizeStreamingMessage(removeIfEmpty: true)
            markCurrentToolCallFailedIfNeeded(message: "Prompt was not sent to backend")
            scheduleToolCallCleanup(after: 2.0)
            if case .thinking = status {
                status = .idle
            } else if case .planning = status {
                status = .idle
            }
            statusDetail = ""
        }
    }

    /// Updates the selected model and persists it immediately.
    func setSelectedModel(_ model: GeminiModel) {
        guard selectedModel != model else { return }
        selectedModel = model
        lastError = nil
        backendLogs.append("[MODEL] Selected model '\(model.rawValue)'")
        if backendLogs.count > 100 {
            backendLogs.removeFirst()
        }
    }

    func setResponseVerbosity(_ verbosity: ResponseVerbosity) {
        guard responseVerbosity != verbosity else { return }
        responseVerbosity = verbosity
        lastError = nil
    }

    func setDeepThinkEnabled(_ enabled: Bool) {
        guard deepThinkEnabled != enabled else { return }
        deepThinkEnabled = enabled
        lastError = nil
    }

    func setResponsePresentationStyle(_ style: ResponsePresentationStyle) {
        guard responsePresentationStyle != style else { return }
        responsePresentationStyle = style
        lastError = nil
    }

    func setReadableProHighContrastEnabled(_ enabled: Bool) {
        guard readableProHighContrastEnabled != enabled else { return }
        readableProHighContrastEnabled = enabled
        lastError = nil
    }

    func setStreamingAnimationStyle(_ style: StreamingAnimationStyle) {
        guard streamingAnimationStyle != style else { return }
        streamingAnimationStyle = style
        lastError = nil
    }

    func setExecutionMode(_ mode: ExecutionMode) {
        guard executionMode != mode else { return }
        executionMode = mode
        lastError = nil
    }

    func submitPlanClarificationResponse(_ response: String) async {
        let trimmed = response.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        let savedInput = currentInput
        currentInput = trimmed
        await sendPrompt()
        // Restore input if sendPrompt didn't consume it (error before send)
        if !currentInput.isEmpty {
            currentInput = savedInput
        }
    }

    func addDroppedFiles(urls: [URL]) {
        guard !urls.isEmpty else { return }
        let normalized = Self.normalizeDroppedFilePaths(urls: urls)
        guard !normalized.isEmpty else { return }

        var merged = droppedFilePaths
        for path in normalized {
            if merged.contains(path) {
                continue
            }
            merged.append(path)
        }
        if merged.count > Self.maxDroppedFilePaths {
            merged = Array(merged.suffix(Self.maxDroppedFilePaths))
        }
        droppedFilePaths = merged
        backendLogs.append("[INPUT_PATHS] Attached \(normalized.count) path(s)")
        if backendLogs.count > 100 {
            backendLogs.removeFirst()
        }
    }

    func removeDroppedFile(path: String) {
        droppedFilePaths.removeAll { $0 == path }
    }

    func clearDroppedFiles() {
        droppedFilePaths.removeAll(keepingCapacity: false)
    }

    func setMemoryMode(_ mode: SessionMemoryMode) {
        guard memoryMode != mode else { return }
        let sessionId = activeSessionId
        let previousMode = memoryMode
        memoryMode = mode
        lastError = nil

        guard !sessionId.isEmpty else {
            memoryMode = previousMode
            lastError = "No active session to update memory mode"
            return
        }

        applyLocalMemoryMode(mode, toSessionId: sessionId)

        guard isConnected else {
            applyLocalMemoryMode(previousMode, toSessionId: sessionId)
            lastError = "Cannot update memory mode while disconnected"
            return
        }

        let rollbackMode = lastKnownSessionModes[sessionId] ?? previousMode
        let token = nextSessionModeUpdateToken()
        pendingSessionModeUpdates[sessionId] = PendingSessionModeUpdate(
            token: token,
            desiredMode: mode,
            rollbackMode: rollbackMode
        )

        Task { @MainActor [weak self] in
            guard let self else { return }
            do {
                let updated = try await self.ipcClient.setSessionMode(
                    sessionId: sessionId,
                    memoryMode: mode.rawValue
                )
                self.handleSessionModePersistSuccess(
                    response: updated,
                    token: token
                )
            } catch {
                self.handleSessionModePersistFailure(
                    sessionId: sessionId,
                    attemptedMode: mode,
                    token: token,
                    error: error
                )
            }
        }
    }

    func createNewSession() async {
        guard isConnected else {
            let message = "Cannot create session while disconnected"
            lastError = message
            status = .error(message: message)
            return
        }
        lastError = nil
        do {
            let created = try await ipcClient.createSession(
                title: nil,
                memoryMode: memoryMode.rawValue
            )
            let item = SessionListItem(from: created)
            let previousSessionId = activeSessionId
            upsertSession(item)
            applyActiveSession(id: item.sessionId, title: item.title, memoryMode: item.memoryMode)
            clearMessages()
            if previousSessionId != item.sessionId {
                notes.removeAll()
                noteImageCache.removeAll()
                if isNotesPanelVisible {
                    loadNotes()
                }
            }
            status = .idle
            backendLogs.append("[SESSION] Created '\(item.title)' (\(item.sessionId.prefix(8)))")
            if backendLogs.count > 100 {
                backendLogs.removeFirst()
            }
        } catch {
            let message = "Failed to create session: \(error.localizedDescription)"
            lastError = message
            status = .error(message: message)
        }
    }

    func switchSession(_ session: SessionListItem) async {
        guard session.sessionId != activeSessionId else { return }
        let targetSessionId = session.sessionId
        await ipcClient.cancel()
        invalidateInFlightResponseState(resetStatus: true)
        applyActiveSession(id: targetSessionId, title: session.title, memoryMode: session.memoryMode)
        messages.removeAll(keepingCapacity: true)
        notes.removeAll()
        lastError = nil
        status = .idle
        await loadSessionMessages(for: targetSessionId)
        guard activeSessionId == targetSessionId else { return }
        currentToolCall = nil
        if isNotesPanelVisible { loadNotes() }
        backendLogs.append("[SESSION] Switched to '\(session.title)' (\(session.sessionId.prefix(8)))")
        if backendLogs.count > 100 {
            backendLogs.removeFirst()
        }
    }

    func refreshSessions() async {
        await refreshSessionsInternal(allowAutoCreate: false)
    }

    func renameActiveSession(to title: String) async {
        guard isConnected else {
            let message = "Cannot rename session while disconnected"
            lastError = message
            status = .error(message: message)
            return
        }
        let trimmed = title.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            let message = "Session name cannot be empty"
            lastError = message
            status = .error(message: message)
            return
        }
        guard !activeSessionId.isEmpty else {
            let message = "No active session to rename"
            lastError = message
            status = .error(message: message)
            return
        }

        do {
            let updated = try await ipcClient.renameSession(sessionId: activeSessionId, title: trimmed)
            let item = SessionListItem(from: updated)
            upsertSession(item)
            applyActiveSession(id: item.sessionId, title: item.title)
            lastError = nil
            status = .idle
            backendLogs.append("[SESSION] Renamed active session to '\(item.title)'")
            if backendLogs.count > 100 {
                backendLogs.removeFirst()
            }
        } catch {
            let message = "Failed to rename session: \(error.localizedDescription)"
            lastError = message
            status = .error(message: message)
        }
    }

    func deleteSession(_ session: SessionListItem) async {
        guard isConnected else {
            let message = "Cannot delete session while disconnected"
            lastError = message
            status = .error(message: message)
            return
        }

        lastError = nil

        let sessionId = session.sessionId
        let wasActiveSession = (sessionId == activeSessionId)

        // Save state for rollback before any mutation
        let savedActiveSessionId = activeSessionId
        let savedActiveSessionTitle = activeSessionTitle
        let savedMessages = messages

        if wasActiveSession {
            await ipcClient.cancel()
            invalidateInFlightResponseState(resetStatus: true)
            clearMessages()
            notes.removeAll()
            noteImageCache.removeAll()
            activeSessionTitle = "Deleting..."
            status = .thinking
            statusDetail = "Deleting session..."
        }

        do {
            try await ipcClient.deleteSession(sessionId: sessionId)

            // Backend confirmed — now safe to clear active session
            if wasActiveSession {
                activeSessionId = ""
                notes.removeAll()
                noteImageCache.removeAll()
            }

            sessions.removeAll { $0.sessionId == sessionId }
            pendingSessionModeUpdates.removeValue(forKey: sessionId)
            lastKnownSessionModes.removeValue(forKey: sessionId)

            if wasActiveSession || sessions.isEmpty {
                await refreshSessionsInternal(allowAutoCreate: false)
            }

            status = .idle
            lastError = nil
            backendLogs.append("[SESSION] Deleted '\(session.title)' (\(session.sessionId.prefix(8)))")
            if backendLogs.count > 100 {
                backendLogs.removeFirst()
            }
        } catch {
            // Restore state on failure
            if wasActiveSession {
                activeSessionId = savedActiveSessionId
                activeSessionTitle = savedActiveSessionTitle
                messages = savedMessages
            }
            let message = "Failed to delete session: \(error.localizedDescription)"
            lastError = message
            status = .error(message: message)
        }
    }

    func deleteSessions(_ sessionsToDelete: [SessionListItem]) async {
        guard !sessionsToDelete.isEmpty else { return }
        guard isConnected else {
            let message = "Cannot delete sessions while disconnected"
            lastError = message
            status = .error(message: message)
            return
        }

        lastError = nil

        // Deduplicate by session id while preserving first-seen order.
        var seen = Set<String>()
        var unique: [SessionListItem] = []
        unique.reserveCapacity(sessionsToDelete.count)
        for session in sessionsToDelete {
            if seen.insert(session.sessionId).inserted {
                unique.append(session)
            }
        }

        let requestedIds = unique.map(\.sessionId)
        let activeIncluded = requestedIds.contains(activeSessionId)

        // Save state for rollback before any mutation
        let savedActiveSessionId = activeSessionId
        let savedActiveSessionTitle = activeSessionTitle
        let savedMessages = messages

        if activeIncluded {
            await ipcClient.cancel()
            invalidateInFlightResponseState(resetStatus: true)
            clearMessages()
            notes.removeAll()
            noteImageCache.removeAll()
            activeSessionTitle = "Deleting..."
            status = .thinking
            statusDetail = "Deleting \(unique.count) sessions..."
        }

        do {
            let result = try await ipcClient.deleteSessions(sessionIds: requestedIds)
            let deletedIdSet = Set(result.deletedSessionIds)

            // Only clear active session if it was actually deleted
            let activeWasDeleted = activeIncluded && deletedIdSet.contains(savedActiveSessionId)
            if activeWasDeleted {
                activeSessionId = ""
                notes.removeAll()
                noteImageCache.removeAll()
            } else if activeIncluded {
                // Active session was requested but failed to delete — restore
                activeSessionId = savedActiveSessionId
                activeSessionTitle = savedActiveSessionTitle
                messages = savedMessages
            }

            sessions.removeAll { deletedIdSet.contains($0.sessionId) }
            for sessionId in deletedIdSet {
                pendingSessionModeUpdates.removeValue(forKey: sessionId)
                lastKnownSessionModes.removeValue(forKey: sessionId)
            }

            await refreshSessionsInternal(allowAutoCreate: false)

            if !result.failed.isEmpty {
                let failedCount = result.failed.count
                let message = "Deleted \(result.deletedSessionIds.count) sessions; \(failedCount) failed."
                lastError = message
                status = .error(message: message)
            } else {
                status = .idle
                lastError = nil
            }

            backendLogs.append(
                "[SESSION] Bulk delete requested=\(requestedIds.count) deleted=\(result.deletedSessionIds.count) failed=\(result.failed.count)"
            )
            if backendLogs.count > 100 {
                backendLogs.removeFirst()
            }
        } catch {
            // Total failure — restore everything
            if activeIncluded {
                activeSessionId = savedActiveSessionId
                activeSessionTitle = savedActiveSessionTitle
                messages = savedMessages
            }
            let message = "Failed to delete selected sessions: \(error.localizedDescription)"
            lastError = message
            status = .error(message: message)
        }
    }
    
    /// Cancels the current operation
    func cancel() async {
        await ipcClient.cancel()
        pendingDestructiveToolCall = nil
        markCurrentToolCallFailedIfNeeded(message: "Cancelled")
        finalizeStreamingMessage(removeIfEmpty: true)
        scheduleToolCallCleanup(after: 1.2)
        activePromptExecutionMode = nil
        status = .idle
    }

    func respondToDestructiveToolConfirmation(approved: Bool) async {
        guard pendingDestructiveToolCall != nil else { return }
        pendingDestructiveToolCall = nil
        do {
            try await ipcClient.confirmCurrentToolExecution(approved: approved)
            if !approved {
                markCurrentToolCallFailedIfNeeded(message: "Operation denied by user")
                scheduleToolCallCleanup(after: 1.2)
                status = .idle
            }
        } catch {
            let message = "Failed to send tool confirmation: \(error.localizedDescription)"
            lastError = message
            status = .error(message: message)
            markCurrentToolCallFailedIfNeeded(message: message)
            scheduleToolCallCleanup(after: 2.0)
        }
    }

    func dismissDestructiveToolConfirmation() {
        pendingDestructiveToolCall = nil
    }

    /// Handles a screen capture request from the backend.
    /// Automatically captures the screen via ScreenCaptureService and sends the result back.
    private func handleScreenCaptureRequest() {
        guard let requestId = ipcClient.currentRequestId else { return }

        Task {
            do {
                let result = try await ScreenCaptureService.shared.captureScreen()
                try await ipcClient.sendScreenCapture(
                    requestId: requestId,
                    imageData: result.imageData,
                    ocrText: result.ocrText,
                    width: result.width,
                    height: result.height
                )
            } catch {
                // Send error response so the backend future doesn't hang
                do {
                    try await ipcClient.sendScreenCaptureError(
                        requestId: requestId,
                        error: error.localizedDescription
                    )
                } catch {
                    let message = "Failed to report screen capture error: \(error.localizedDescription)"
                    lastError = message
                    status = .error(message: message)
                    DebugLogger.log("screen_capture_error_response_failed", fields: [
                        "request_id": requestId,
                        "error": error.localizedDescription,
                    ])
                }
            }
        }
    }
    
    /// Toggles the panel visibility
    func togglePanel() {
        isPanelVisible.toggle()
    }
    
    /// Clears all messages
    func clearMessages() {
        pendingHistoryLoadToken = UUID()
        messages.removeAll()
        isSessionHistoryLoading = false
        streamingText = ""
        currentToolCall = nil
        pendingDestructiveToolCall = nil
        streamingMessageId = nil
        streamingMessageIndex = nil
    }
    
    /// Toggles tool call expansion
    func toggleToolCallExpansion() {
        isToolCallExpanded.toggle()
    }

    // MARK: - Notes

    /// Toggles the notes panel visibility.
    func toggleNotesPanel() {
        if isNotesPanelVisible {
            NotesPanelController.shared.hide()
        } else {
            NotesPanelController.shared.show()
            if notes.isEmpty { loadNotes() }
        }
        isNotesPanelVisible = NotesPanelController.shared.isVisible
    }

    /// Loads notes for the active session from the backend.
    func loadNotes() {
        let sessionId = activeSessionId
        guard !sessionId.isEmpty, isConnected else { return }
        isNotesLoading = true
        Task { @MainActor [weak self] in
            defer { self?.isNotesLoading = false }
            guard let self else { return }
            do {
                let ipcNotes = try await self.ipcClient.listNotes(sessionId: sessionId)
                // Only apply if session hasn't changed during the fetch
                if self.activeSessionId == sessionId {
                    self.notes = ipcNotes.map { $0.toNote() }
                }
            } catch {
                DebugLogger.log("notes_load_error", fields: ["error": error.localizedDescription])
            }
        }
    }

    /// Creates a new note in the active session.
    func createNote(content: String) {
        let sessionId = activeSessionId
        guard !sessionId.isEmpty, !content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        Task { @MainActor [weak self] in
            guard let self else { return }
            do {
                let ipcNote = try await self.ipcClient.createNote(sessionId: sessionId, content: content)
                if self.activeSessionId == sessionId {
                    self.notes.insert(ipcNote.toNote(), at: 0)
                    // Re-sort: pinned first, then by updatedAt descending
                    self.sortNotes()
                }
            } catch {
                let message = "Failed to create note: \(error.localizedDescription)"
                lastError = message
                status = .error(message: message)
                DebugLogger.log("notes_create_error", fields: ["error": error.localizedDescription])
            }
        }
    }

    /// Updates an existing note.
    func updateNote(noteId: String, content: String? = nil, isPinned: Bool? = nil) {
        let sessionId = activeSessionId
        guard !sessionId.isEmpty else { return }
        Task { @MainActor [weak self] in
            guard let self else { return }
            do {
                let ipcNote = try await self.ipcClient.updateNote(
                    sessionId: sessionId, noteId: noteId, content: content, isPinned: isPinned
                )
                if self.activeSessionId == sessionId,
                   let index = self.notes.firstIndex(where: { $0.id == noteId }) {
                    self.notes[index] = ipcNote.toNote()
                    self.sortNotes()
                }
            } catch {
                let message = "Failed to update note: \(error.localizedDescription)"
                lastError = message
                status = .error(message: message)
                DebugLogger.log("notes_update_error", fields: ["error": error.localizedDescription])
            }
        }
    }

    /// Deletes a note.
    func deleteNote(noteId: String) {
        let sessionId = activeSessionId
        guard !sessionId.isEmpty else { return }
        Task { @MainActor [weak self] in
            guard let self else { return }
            do {
                let deleted = try await self.ipcClient.deleteNote(sessionId: sessionId, noteId: noteId)
                if deleted, self.activeSessionId == sessionId {
                    self.notes.removeAll { $0.id == noteId }
                }
            } catch {
                let message = "Failed to delete note: \(error.localizedDescription)"
                lastError = message
                status = .error(message: message)
                DebugLogger.log("notes_delete_error", fields: ["error": error.localizedDescription])
            }
        }
    }

    /// Fetches a note image by ID, returning a cached or freshly-fetched NSImage.
    func fetchNoteImage(imageId: String) async -> NSImage? {
        if let cached = noteImageCache[imageId] { return cached }
        let sessionId = activeSessionId
        guard !sessionId.isEmpty, isConnected else { return nil }
        do {
            let ipcImage = try await ipcClient.getNoteImage(sessionId: sessionId, imageId: imageId)
            guard let data = Data(base64Encoded: ipcImage.imageData),
                  let nsImage = NSImage(data: data) else {
                DebugLogger.log("note_image_decode_error", fields: ["image_id": imageId])
                return nil
            }
            noteImageCache[imageId] = nsImage
            return nsImage
        } catch {
            DebugLogger.log("note_image_fetch_error", fields: [
                "image_id": imageId,
                "error": error.localizedDescription,
            ])
            return nil
        }
    }

    /// Fetches the version history for a note.
    func fetchNoteVersions(noteId: String) async -> [IPCNoteVersion] {
        let sessionId = activeSessionId
        guard !sessionId.isEmpty, isConnected else { return [] }
        do {
            return try await ipcClient.listNoteVersions(sessionId: sessionId, noteId: noteId)
        } catch {
            DebugLogger.log("note_versions_fetch_error", fields: [
                "note_id": noteId,
                "error": error.localizedDescription,
            ])
            return []
        }
    }

    /// Sorts notes: pinned first, then by updatedAt descending.
    private func sortNotes() {
        notes.sort { lhs, rhs in
            if lhs.isPinned != rhs.isPinned { return lhs.isPinned }
            return lhs.updatedAt > rhs.updatedAt
        }
    }

    /// Reconnects to the backend
    func reconnect() async {
        isManualDisconnect = false
        cancelReconnectLoop()
        await ipcClient.reconnect()
    }

    /// Applies side effects for the auto-connect preference at runtime.
    func handleAutoConnectPreferenceChanged(_ enabled: Bool) {
        UserDefaults.standard.set(enabled, forKey: Self.autoConnectKey)
        if !enabled {
            cancelReconnectLoop()
            return
        }
        guard !isConnected else { return }
        guard !isStartupPhaseInProgress else { return }
        Task { @MainActor [weak self] in
            await self?.startup()
        }
    }

    /// Applies side effects for reconnect-on-failure preference changes.
    func handleReconnectOnFailurePreferenceChanged(_ enabled: Bool) {
        UserDefaults.standard.set(enabled, forKey: Self.reconnectOnFailureKey)
        if !enabled {
            cancelReconnectLoop()
        }
    }

    private func startReconciliationLoopIfNeeded() {
        guard reconciliationTask == nil else { return }
        reconciliationTask = Task { @MainActor [weak self] in
            guard let self else { return }
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: self.realtimePollIntervalNanoseconds)
                guard !Task.isCancelled else { return }
                await self.performRealtimeRefresh(
                    includeNotes: self.isNotesPanelVisible || !self.notes.isEmpty,
                    skipIfRecent: true
                )
            }
        }
    }

    private func stopReconciliationLoop() {
        reconciliationTask?.cancel()
        reconciliationTask = nil
        pendingRealtimeRefreshTask?.cancel()
        pendingRealtimeRefreshTask = nil
        pendingRealtimeRefreshIncludeNotes = false
    }

    private func scheduleRealtimeRefresh(includeNotes: Bool) {
        pendingRealtimeRefreshIncludeNotes = pendingRealtimeRefreshIncludeNotes || includeNotes
        guard pendingRealtimeRefreshTask == nil else { return }
        pendingRealtimeRefreshTask = Task { @MainActor [weak self] in
            guard let self else { return }
            try? await Task.sleep(nanoseconds: self.realtimeRefreshDebounceNanoseconds)
            let shouldLoadNotes = self.pendingRealtimeRefreshIncludeNotes
            self.pendingRealtimeRefreshIncludeNotes = false
            self.pendingRealtimeRefreshTask = nil
            await self.performRealtimeRefresh(includeNotes: shouldLoadNotes, skipIfRecent: false)
        }
    }

    private func performRealtimeRefresh(includeNotes: Bool, skipIfRecent: Bool) async {
        guard isConnected else { return }
        if skipIfRecent && Date().timeIntervalSince(lastRealtimeRefreshAt) < 1.0 {
            return
        }
        await refreshSessionsInternal(allowAutoCreate: false)
        if includeNotes, !activeSessionId.isEmpty, (isNotesPanelVisible || !notes.isEmpty) {
            loadNotes()
        }
        lastRealtimeRefreshAt = Date()
    }

    private func handleSystemEvent(_ event: IPCSystemEvent) async {
        switch event.domain {
        case "session":
            let eventSessionId = sessionIdFromSystemPayload(event.payload)
            if event.action == "deleted", eventSessionId == activeSessionId {
                notes.removeAll()
                noteImageCache.removeAll()
                clearMessages()
            }
            scheduleRealtimeRefresh(includeNotes: false)
        case "notes":
            let eventSessionId = sessionIdFromSystemPayload(event.payload)
            let shouldReloadNotes = (eventSessionId == activeSessionId)
            scheduleRealtimeRefresh(includeNotes: shouldReloadNotes)
        case "memory":
            let shouldReloadNotes = sessionIdFromSystemPayload(event.payload) == activeSessionId
            scheduleRealtimeRefresh(includeNotes: shouldReloadNotes)
        default:
            break
        }
    }

    private func sessionIdFromSystemPayload(_ payload: [String: Any]) -> String? {
        if let direct = payload["session_id"] as? String, !direct.isEmpty {
            return direct
        }
        if let session = payload["session"] as? [String: Any],
           let sessionId = session["session_id"] as? String,
           !sessionId.isEmpty {
            return sessionId
        }
        return nil
    }

    private func isUnknownSessionError(_ message: String) -> Bool {
        let lower = message.lowercased()
        return lower.contains("unknown session") || lower.contains("missing session_id")
    }

    private func recoverFromUnknownSessionError() async {
        await refreshSessionsInternal(allowAutoCreate: false)
        if !activeSessionId.isEmpty {
            await loadSessionMessages(for: activeSessionId)
            if isNotesPanelVisible || !notes.isEmpty {
                loadNotes()
            }
        }
        if case .error = status {
            status = .idle
            statusDetail = ""
        }
    }
    
    // MARK: - Private Methods

    private func bootstrapSessionsIfNeeded() async {
        guard isConnected else { return }
        guard !isBootstrappingSessions else { return }
        isBootstrappingSessions = true
        defer { isBootstrappingSessions = false }
        await refreshSessionsInternal(allowAutoCreate: false)
    }

    private func scheduleReconnectIfEligible(wasConnected: Bool) {
        guard wasConnected else { return }
        guard !isManualDisconnect else { return }
        guard Self.loadBoolSetting(key: Self.autoConnectKey, defaultValue: true) else { return }
        guard Self.loadBoolSetting(key: Self.reconnectOnFailureKey, defaultValue: true) else { return }
        guard reconnectTask == nil else { return }

        reconnectAttemptCount = 0
        reconnectTask = Task { @MainActor [weak self] in
            guard let self else { return }
            defer { self.reconnectTask = nil }

            let maxAttempts = 5
            while !Task.isCancelled {
                guard !self.isConnected else { return }
                guard !self.isManualDisconnect else { return }
                guard Self.loadBoolSetting(key: Self.autoConnectKey, defaultValue: true) else { return }
                guard Self.loadBoolSetting(key: Self.reconnectOnFailureKey, defaultValue: true) else { return }

                self.reconnectAttemptCount += 1
                let attempt = self.reconnectAttemptCount
                let delay = Self.reconnectDelayNanoseconds(forAttempt: attempt)
                try? await Task.sleep(nanoseconds: delay)
                guard !Task.isCancelled else { return }
                guard !self.isConnected else { return }
                guard !self.isManualDisconnect else { return }
                await self.ipcClient.reconnect()
                if self.isConnected {
                    self.reconnectAttemptCount = 0
                    return
                }
                if attempt >= maxAttempts {
                    await self.startup()
                    return
                }
            }
        }
    }

    private func cancelReconnectLoop() {
        reconnectTask?.cancel()
        reconnectTask = nil
        reconnectAttemptCount = 0
    }

    private func ensureActiveSession() async -> Bool {
        guard isConnected else { return false }
        if !activeSessionId.isEmpty,
           let current = sessions.first(where: { $0.sessionId == activeSessionId }) {
            synchronizeActiveMemoryModeWithSession(
                sessionId: current.sessionId,
                sessionMode: current.memoryMode
            )
            return true
        }
        await refreshSessionsInternal(allowAutoCreate: true)
        return !activeSessionId.isEmpty &&
            sessions.contains(where: { $0.sessionId == activeSessionId })
    }

    private func refreshSessionsInternal(allowAutoCreate: Bool) async {
        guard isConnected else { return }
        if isRefreshingSessions {
            pendingSessionRefreshAllowAutoCreate =
                pendingSessionRefreshAllowAutoCreate || allowAutoCreate
            return
        }

        isRefreshingSessions = true
        defer { isRefreshingSessions = false }

        var nextAllowAutoCreate = allowAutoCreate
        while isConnected {
            pendingSessionRefreshAllowAutoCreate = false
            await refreshSessionsInternalOnce(allowAutoCreate: nextAllowAutoCreate)
            guard pendingSessionRefreshAllowAutoCreate else { break }
            nextAllowAutoCreate = pendingSessionRefreshAllowAutoCreate
        }
    }

    private func refreshSessionsInternalOnce(allowAutoCreate: Bool) async {
        guard isConnected else { return }
        let previousActiveSessionId = activeSessionId
        do {
            let remote = try await ipcClient.listSessions(limit: 100)
            var merged: [SessionListItem] = []
            merged.reserveCapacity(remote.count)
            for payload in remote {
                var item = SessionListItem(from: payload)
                let backendMode = item.memoryMode
                lastKnownSessionModes[item.sessionId] = backendMode
                if let pending = pendingSessionModeUpdates[item.sessionId] {
                    if pending.desiredMode == backendMode {
                        pendingSessionModeUpdates.removeValue(forKey: item.sessionId)
                    } else {
                        item = item.with(memoryMode: pending.desiredMode)
                    }
                }
                merged.append(item)
            }
            let sorted = merged.sorted(by: { $0.updatedAt > $1.updatedAt })
            if sorted != sessions {
                sessions = sorted
            }

            if let current = sessions.first(where: { $0.sessionId == activeSessionId }) {
                applyActiveSession(
                    id: current.sessionId,
                    title: current.title,
                    memoryMode: current.memoryMode
                )
                if messages.isEmpty {
                    await loadSessionMessages(for: current.sessionId)
                }
                return
            }

            let stored = Self.loadActiveSessionId()
            if !stored.isEmpty,
               let restored = sessions.first(where: { $0.sessionId == stored }) {
                let switchedSession = previousActiveSessionId != restored.sessionId
                applyActiveSession(
                    id: restored.sessionId,
                    title: restored.title,
                    memoryMode: restored.memoryMode
                )
                if switchedSession {
                    notes.removeAll()
                    noteImageCache.removeAll()
                }
                await loadSessionMessages(for: restored.sessionId)
                if switchedSession && isNotesPanelVisible {
                    loadNotes()
                }
                return
            }

            if let first = sessions.first {
                let switchedSession = previousActiveSessionId != first.sessionId
                applyActiveSession(
                    id: first.sessionId,
                    title: first.title,
                    memoryMode: first.memoryMode
                )
                if switchedSession {
                    notes.removeAll()
                    noteImageCache.removeAll()
                }
                await loadSessionMessages(for: first.sessionId)
                if switchedSession && isNotesPanelVisible {
                    loadNotes()
                }
                return
            }

            if sessions.isEmpty {
                pendingSessionModeUpdates.removeAll()
                lastKnownSessionModes.removeAll()
                if !activeSessionId.isEmpty {
                    activeSessionId = ""
                }
                activeSessionTitle = "No Session"
                notes.removeAll()
                noteImageCache.removeAll()
                if !messages.isEmpty {
                    clearMessages()
                }
            }

            guard allowAutoCreate else {
                return
            }

            if let lastAutoCreatedSessionAt,
               Date().timeIntervalSince(lastAutoCreatedSessionAt) < Self.autoSessionCreateCooldownSeconds {
                return
            }

            let created = try await ipcClient.createSession(
                title: nil,
                memoryMode: memoryMode.rawValue
            )
            lastAutoCreatedSessionAt = Date()
            let createdItem = SessionListItem(from: created)
            sessions = [createdItem]
            applyActiveSession(
                id: createdItem.sessionId,
                title: createdItem.title,
                memoryMode: createdItem.memoryMode
            )
            clearMessages()
            notes.removeAll()
            noteImageCache.removeAll()
            if isNotesPanelVisible {
                loadNotes()
            }
        } catch {
            let message = "Failed to load sessions: \(error.localizedDescription)"
            if shouldRecoverByRestartingBackend(after: error) {
                backendLogs.append("[SESSION] Session store/backend mismatch detected. Restarting managed backend.")
                if backendLogs.count > 100 {
                    backendLogs.removeFirst()
                }
                ipcClient.disconnect()
                await restartManagedBackendForRecovery()
                return
            }
            lastError = message
            status = .error(message: message)
        }
    }

    private func loadSessionMessages(for sessionId: String) async {
        guard isConnected else { return }
        let loadToken = UUID()
        pendingHistoryLoadToken = loadToken
        isSessionHistoryLoading = true
        streamingText = ""
        streamingMessageId = nil
        streamingMessageIndex = nil
        currentToolCall = nil
        defer {
            if pendingHistoryLoadToken == loadToken {
                isSessionHistoryLoading = false
            }
        }
        do {
            let history = try await ipcClient.sessionHistory(sessionId: sessionId, limit: 2000)
            guard pendingHistoryLoadToken == loadToken, activeSessionId == sessionId else {
                return
            }
            let mapped: [Message] = history.compactMap { entry in
                let role: MessageRole
                switch entry.role {
                case "user":
                    role = .user
                case "assistant":
                    role = .assistant
                default:
                    role = .system
                }
                return Message(
                    role: role,
                    content: entry.content,
                    timestamp: Date(timeIntervalSince1970: entry.createdAt)
                )
            }
            messages = mapped
            streamingText = ""
            streamingMessageId = nil
            streamingMessageIndex = nil
            lastError = nil
        } catch {
            guard pendingHistoryLoadToken == loadToken, activeSessionId == sessionId else {
                return
            }
            if shouldRecoverByRestartingBackend(after: error) {
                backendLogs.append("[SESSION] History load mismatch detected. Restarting managed backend.")
                if backendLogs.count > 100 {
                    backendLogs.removeFirst()
                }
                ipcClient.disconnect()
                await restartManagedBackendForRecovery()
                return
            }

            let lower = error.localizedDescription.lowercased()
            if lower.contains("unknown session") || lower.contains("missing session_id") {
                await refreshSessionsInternal(allowAutoCreate: false)
                return
            }

            let message = "Failed to load chat history: \(error.localizedDescription)"
            lastError = message
            status = .error(message: message)
        }
    }

    private func nextSessionModeUpdateToken() -> UInt64 {
        sessionModeUpdateCounter &+= 1
        if sessionModeUpdateCounter == 0 {
            sessionModeUpdateCounter = 1
        }
        return sessionModeUpdateCounter
    }

    private func upsertSession(_ item: SessionListItem, rememberMode: Bool = true) {
        if rememberMode {
            lastKnownSessionModes[item.sessionId] = item.memoryMode
        }
        if let index = sessions.firstIndex(where: { $0.sessionId == item.sessionId }) {
            sessions[index] = item
        } else {
            sessions.insert(item, at: 0)
        }
        sessions.sort(by: { $0.updatedAt > $1.updatedAt })
    }

    private func updateSessionMemoryModeIfPresent(
        sessionId: String,
        mode: SessionMemoryMode
    ) {
        guard let index = sessions.firstIndex(where: { $0.sessionId == sessionId }) else {
            return
        }
        guard sessions[index].memoryMode != mode else { return }
        sessions[index] = sessions[index].with(memoryMode: mode)
    }

    private func applyLocalMemoryMode(_ mode: SessionMemoryMode, toSessionId sessionId: String) {
        if activeSessionId == sessionId, memoryMode != mode {
            memoryMode = mode
        }
        updateSessionMemoryModeIfPresent(sessionId: sessionId, mode: mode)
    }

    private func handleSessionModePersistSuccess(
        response: IPCSessionSummary,
        token: UInt64
    ) {
        let updatedItem = SessionListItem(from: response)
        let resolvedSessionId = updatedItem.sessionId
        let backendMode = updatedItem.memoryMode
        lastKnownSessionModes[resolvedSessionId] = backendMode

        if let pending = pendingSessionModeUpdates[resolvedSessionId] {
            if pending.token != token {
                var newerPending = pending
                newerPending.rollbackMode = backendMode
                pendingSessionModeUpdates[resolvedSessionId] = newerPending
                upsertSession(
                    updatedItem.with(memoryMode: newerPending.desiredMode),
                    rememberMode: false
                )
                return
            }
            pendingSessionModeUpdates.removeValue(forKey: resolvedSessionId)
        }

        upsertSession(updatedItem)
        if activeSessionId == resolvedSessionId {
            synchronizeActiveMemoryModeWithSession(
                sessionId: resolvedSessionId,
                sessionMode: backendMode
            )
        }
        lastError = nil
    }

    private func handleSessionModePersistFailure(
        sessionId: String,
        attemptedMode: SessionMemoryMode,
        token: UInt64,
        error: Error
    ) {
        guard let pending = pendingSessionModeUpdates[sessionId],
              pending.token == token else {
            return
        }

        pendingSessionModeUpdates.removeValue(forKey: sessionId)
        let rollbackMode = pending.rollbackMode
        lastKnownSessionModes[sessionId] = rollbackMode
        applyLocalMemoryMode(rollbackMode, toSessionId: sessionId)

        let message = "Failed to update memory mode: \(error.localizedDescription)"
        lastError = message
        backendLogs.append(
            "[MEMORY] Failed to persist mode '\(attemptedMode.rawValue)' for session '\(sessionId)': \(error.localizedDescription)"
        )
        if backendLogs.count > 100 {
            backendLogs.removeFirst()
        }
    }

    nonisolated static func shouldApplyRemoteSessionMemoryMode(
        localMode: SessionMemoryMode,
        remoteMode: SessionMemoryMode,
        pendingDesiredMode: SessionMemoryMode?
    ) -> Bool {
        guard localMode != remoteMode else { return false }
        guard let pendingDesiredMode else { return true }
        return pendingDesiredMode == remoteMode
    }

    private func synchronizeActiveMemoryModeWithSession(
        sessionId: String,
        sessionMode: SessionMemoryMode
    ) {
        let pendingDesiredMode = pendingSessionModeUpdates[sessionId]?.desiredMode
        guard Self.shouldApplyRemoteSessionMemoryMode(
            localMode: memoryMode,
            remoteMode: sessionMode,
            pendingDesiredMode: pendingDesiredMode
        ) else {
            return
        }
        memoryMode = sessionMode
    }

    private func applyActiveSession(
        id: String,
        title: String,
        memoryMode: SessionMemoryMode? = nil
    ) {
        activeSessionId = id
        activeSessionTitle = title
        if let memoryMode {
            lastKnownSessionModes[id] = memoryMode
            synchronizeActiveMemoryModeWithSession(sessionId: id, sessionMode: memoryMode)
        }
    }
    
    /// Updates the streaming message with new text
    private func updateStreamingMessage(with text: String) {
        guard let index = resolveStreamingMessageIndex() else {
            return
        }
        if messages[index].content == text {
            return
        }
        messages[index].content = text
    }
    
    /// Finalizes the streaming message (marks as no longer streaming)
    private func finalizeStreamingMessage(removeIfEmpty: Bool = false) {
        guard let index = resolveStreamingMessageIndex() else {
            return
        }

        if removeIfEmpty,
           messages[index].content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
           messages[index].toolCall == nil {
            messages.remove(at: index)
            streamingMessageId = nil
            streamingMessageIndex = nil
            return
        }
        
        messages[index].isStreaming = false
        
        // Attach tool call if present
        if let toolCall = currentToolCall {
            messages[index].toolCall = toolCall
        }
        
        streamingMessageId = nil
        streamingMessageIndex = nil
    }
    
    /// Handles completion of a response
    private func handleComplete(content: String?) {
        activePromptExecutionMode = nil
        if let content = content, !content.isEmpty {
            updateStreamingMessage(with: ToolResultFormatter.normalizeContent(content))
        }
        finalizeStreamingMessage()
        if let toolCall = currentToolCall, toolCall.status.isComplete {
            scheduleToolCallCleanup(after: 2.0)
        } else if currentToolCall != nil {
            scheduleToolCallCleanup(after: 0.9)
        }
        status = .complete
        statusDetail = "Completed"

        scheduleCompleteReset(after: 2.0)
    }

    private func resetDisconnectedUIState() {
        pendingHistoryLoadToken = UUID()
        completeResetTask?.cancel()
        completeResetTask = nil
        toolCallCleanupTask?.cancel()
        toolCallCleanupTask = nil
        isSessionHistoryLoading = false
        isSendingPrompt = false
        sessions = []
        activeSessionTitle = "Disconnected"
        messages = []
        streamingMessageId = nil
        streamingMessageIndex = nil
        streamingText = ""
        currentToolCall = nil
        pendingDestructiveToolCall = nil
        activePromptExecutionMode = nil
        notes = []
        if isNotesPanelVisible {
            NotesPanelController.shared.hide()
        }
        isNotesPanelVisible = false
        isNotesLoading = false
        status = .idle
        statusDetail = ""
        pendingSessionModeUpdates.removeAll()
        lastKnownSessionModes.removeAll()
        isRefreshingSessions = false
        pendingSessionRefreshAllowAutoCreate = false
        lastAutoCreatedSessionAt = nil
    }

    private func invalidateInFlightResponseState(resetStatus: Bool) {
        pendingHistoryLoadToken = UUID()
        completeResetTask?.cancel()
        completeResetTask = nil
        toolCallCleanupTask?.cancel()
        toolCallCleanupTask = nil
        streamingMessageId = nil
        streamingMessageIndex = nil
        streamingText = ""
        currentToolCall = nil
        pendingDestructiveToolCall = nil
        activePromptExecutionMode = nil
        isSendingPrompt = false
        if resetStatus {
            status = .idle
            statusDetail = ""
        }
    }

    private func handleToolCallUpdate(_ incomingToolCall: ToolCall) {
        if shouldSuppressToolCallCard(incomingToolCall) {
            if currentToolCall?.name == incomingToolCall.name {
                currentToolCall = nil
            }
            return
        }

        toolCallCleanupTask?.cancel()
        toolCallCleanupTask = nil

        var normalizedIncoming = incomingToolCall
        if let result = normalizedIncoming.result, !result.isEmpty {
            normalizedIncoming.result = ToolResultFormatter.normalizeContent(result)
        }

        if let current = currentToolCall {
            currentToolCall = current.merged(with: normalizedIncoming)
        } else {
            currentToolCall = normalizedIncoming
        }

        if let toolCall = currentToolCall,
           toolCall.name == "apply_ops",
           toolCall.status == .pending {
            pendingDestructiveToolCall = toolCall
        } else {
            pendingDestructiveToolCall = nil
        }

        if let toolCall = currentToolCall, toolCall.status.isComplete {
            if let index = resolveStreamingMessageIndex() {
                messages[index].toolCall = toolCall
            }

            // Auto-open notes panel when agent uses note tools successfully
            let noteTools: Set<String> = [
                "take_note",
                "update_note",
                "delete_note",
                "format_note",
                "merge_notes",
                "reorder_notes",
                "generate_image",
                "generate_quiz",
                "summarize_note",
            ]
            if noteTools.contains(toolCall.name), toolCall.status == .success {
                loadNotes()
                let teacherModeActive = (activePromptExecutionMode ?? executionMode) == .teacher
                if teacherModeActive || !isNotesPanelVisible {
                    NotesPanelController.shared.show()
                    isNotesPanelVisible = true
                }
            }

            scheduleToolCallCleanup(after: 2.0)
        }
    }

    private func resolveStreamingMessageIndex() -> Int? {
        guard let messageId = streamingMessageId else {
            streamingMessageIndex = nil
            return nil
        }
        if let cachedIndex = streamingMessageIndex,
           messages.indices.contains(cachedIndex),
           messages[cachedIndex].id == messageId {
            return cachedIndex
        }
        guard let resolvedIndex = messages.firstIndex(where: { $0.id == messageId }) else {
            streamingMessageIndex = nil
            return nil
        }
        streamingMessageIndex = resolvedIndex
        return resolvedIndex
    }

    private func shouldSuppressToolCallCard(_ toolCall: ToolCall) -> Bool {
        let modeForActivePrompt = activePromptExecutionMode ?? executionMode
        guard modeForActivePrompt == .plan else { return false }
        return toolCall.name == "planner"
    }

    private func markCurrentToolCallFailedIfNeeded(message: String) {
        guard var toolCall = currentToolCall else { return }
        guard !toolCall.status.isComplete else { return }
        toolCall.status = .failed
        if toolCall.error == nil || toolCall.error?.isEmpty == true {
            toolCall.error = message
        }
        currentToolCall = toolCall
    }

    private func scheduleToolCallCleanup(after seconds: TimeInterval) {
        toolCallCleanupTask?.cancel()
        guard currentToolCall != nil else { return }
        let nanoseconds = UInt64(max(0, seconds) * 1_000_000_000)
        toolCallCleanupTask = Task { @MainActor [weak self] in
            try? await Task.sleep(nanoseconds: nanoseconds)
            guard let self else { return }
            guard let toolCall = self.currentToolCall, toolCall.status.isComplete else {
                self.toolCallCleanupTask = nil
                return
            }
            self.currentToolCall = nil
            self.toolCallCleanupTask = nil
        }
    }

    private func scheduleCompleteReset(after seconds: TimeInterval) {
        completeResetTask?.cancel()
        let nanoseconds = UInt64(max(0, seconds) * 1_000_000_000)
        completeResetTask = Task { @MainActor [weak self] in
            try? await Task.sleep(nanoseconds: nanoseconds)
            guard let self else { return }
            if case .complete = self.status {
                self.status = .idle
                self.statusDetail = ""
            }
            self.completeResetTask = nil
        }
    }

    private func effectiveStatusDetail(for status: AgentStatus, detail: String?) -> String {
        let trimmed = detail?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let baseDetail: String
        if !trimmed.isEmpty {
            baseDetail = trimmed
        } else {
            switch status {
            case .idle:
                baseDetail = ""
            case .connecting:
                baseDetail = "Connecting to backend..."
            case .thinking:
                baseDetail = "Analyzing your request..."
            case .planning:
                baseDetail = "Building your plan..."
            case .planReady:
                baseDetail = "Plan is ready for review."
            case .awaitingApproval:
                baseDetail = "Waiting for confirmation."
            case .executingPlan:
                baseDetail = "Executing approved steps..."
            case .callingTool(let toolName):
                baseDetail = "Using \(toolName)"
            case .capturingScreen:
                baseDetail = "Reading screen contents..."
            case .streaming:
                baseDetail = "Writing the response..."
            case .error(let message):
                baseDetail = message
            case .complete:
                baseDetail = "Completed"
            }
        }

        let shouldAnnotateDeepThink: Bool
        switch status {
        case .thinking, .planning, .awaitingApproval, .executingPlan, .callingTool, .capturingScreen, .streaming:
            shouldAnnotateDeepThink = deepThinkEnabled
        default:
            shouldAnnotateDeepThink = false
        }

        guard shouldAnnotateDeepThink else {
            return baseDetail
        }
        if baseDetail.lowercased().contains("deep think") {
            return baseDetail
        }
        if baseDetail.isEmpty {
            return "Deep Think active"
        }
        return "Deep Think active | \(baseDetail)"
    }

    private static func loadSelectedModel() -> GeminiModel {
        if let rawValue = UserDefaults.standard.string(forKey: selectedModelKey),
           let model = GeminiModel(rawValue: rawValue) {
            return model
        }
        let fallback = GeminiModel.gemini3FlashPreview
        UserDefaults.standard.set(fallback.rawValue, forKey: selectedModelKey)
        return fallback
    }

    private static func loadMemoryMode() -> SessionMemoryMode {
        if let rawValue = UserDefaults.standard.string(forKey: memoryModeKey),
           let mode = SessionMemoryMode(rawValue: rawValue) {
            return mode
        }
        let fallback: SessionMemoryMode = .on
        UserDefaults.standard.set(fallback.rawValue, forKey: memoryModeKey)
        return fallback
    }

    private static func loadResponseVerbosity() -> ResponseVerbosity {
        if let rawValue = UserDefaults.standard.string(forKey: responseVerbosityKey),
           let verbosity = ResponseVerbosity(rawValue: rawValue) {
            return verbosity
        }
        let fallback: ResponseVerbosity = .medium
        UserDefaults.standard.set(fallback.rawValue, forKey: responseVerbosityKey)
        return fallback
    }

    private static func loadDeepThinkEnabled() -> Bool {
        let defaults = UserDefaults.standard
        if defaults.object(forKey: deepThinkKey) != nil {
            return defaults.bool(forKey: deepThinkKey)
        }
        let fallback = false
        defaults.set(fallback, forKey: deepThinkKey)
        return fallback
    }

    private static func loadResponsePresentationStyle() -> ResponsePresentationStyle {
        if let rawValue = UserDefaults.standard.string(forKey: responsePresentationStyleKey),
           let style = ResponsePresentationStyle(rawValue: rawValue) {
            return style
        }
        let fallback: ResponsePresentationStyle = .readablePro
        UserDefaults.standard.set(fallback.rawValue, forKey: responsePresentationStyleKey)
        return fallback
    }

    private static func loadReadableProHighContrastEnabled() -> Bool {
        let defaults = UserDefaults.standard
        if defaults.object(forKey: readableProHighContrastKey) != nil {
            return defaults.bool(forKey: readableProHighContrastKey)
        }
        let fallback = true
        defaults.set(fallback, forKey: readableProHighContrastKey)
        return fallback
    }

    private static func loadStreamingAnimationStyle() -> StreamingAnimationStyle {
        if let rawValue = UserDefaults.standard.string(forKey: streamingAnimationStyleKey),
           let style = StreamingAnimationStyle(rawValue: rawValue) {
            return style
        }
        let fallback: StreamingAnimationStyle = .waveReveal
        UserDefaults.standard.set(fallback.rawValue, forKey: streamingAnimationStyleKey)
        return fallback
    }

    private static func loadExecutionMode() -> ExecutionMode {
        if let rawValue = UserDefaults.standard.string(forKey: executionModeKey),
           let mode = ExecutionMode(rawValue: rawValue) {
            return mode
        }
        let fallback: ExecutionMode = .direct
        UserDefaults.standard.set(fallback.rawValue, forKey: executionModeKey)
        return fallback
    }

    nonisolated static func normalizeDroppedFilePaths(urls: [URL]) -> [String] {
        var normalized: [String] = []
        var seen = Set<String>()
        for url in urls {
            let resolved: URL
            if url.isFileURL {
                resolved = url.standardizedFileURL
            } else if let converted = URL(string: url.absoluteString), converted.isFileURL {
                resolved = converted.standardizedFileURL
            } else {
                continue
            }

            let path = resolved.path.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !path.isEmpty else { continue }
            guard !seen.contains(path) else { continue }
            seen.insert(path)
            normalized.append(path)
        }
        return normalized
    }

    private static func loadActiveSessionId() -> String {
        UserDefaults.standard.string(forKey: activeSessionIdKey) ?? ""
    }

    private var isStartupPhaseInProgress: Bool {
        switch startupPhase {
        case .initializing, .startingBackend, .connectingToBackend, .performingHealthCheck:
            return true
        case .ready, .failed:
            return false
        }
    }

    private static func reconnectDelayNanoseconds(forAttempt attempt: Int) -> UInt64 {
        let cappedAttempt = max(1, min(attempt, 5))
        let seconds = min(pow(2.0, Double(cappedAttempt - 1)), 8.0)
        return UInt64(seconds * 1_000_000_000)
    }

    private static func loadBoolSetting(key: String, defaultValue: Bool) -> Bool {
        let defaults = UserDefaults.standard
        guard defaults.object(forKey: key) != nil else { return defaultValue }
        return defaults.bool(forKey: key)
    }

    private func shouldRecoverByRestartingBackend(after error: Error) -> Bool {
        let lower = error.localizedDescription.lowercased()
        if lower.contains("method not found: session.list") {
            return true
        }
        if lower.contains("method not found") && lower.contains("session") {
            return true
        }
        if lower.contains("no such table: sessions") {
            return true
        }
        if lower.contains("no such table: semantic_index") {
            return true
        }
        if lower.contains("no such table: messages") {
            return true
        }
        if lower.contains("no such table: summaries") {
            return true
        }
        return false
    }

    private func restartManagedBackendForRecovery() async {
        // Always terminate our managed launcher state before restart.
        backendLauncher.terminate()
        backendStartedByApp = false
        await startBackend()
    }
}

// MARK: - Preview Helpers

#if DEBUG
extension AppState {
    /// Creates mock state for previews
    static var preview: AppState {
        let state = AppState.shared
        state.messages = [
            Message.user("Find all Python files in Documents"),
            Message.assistant("I found 15 Python files in your Documents folder:\n• main.py\n• config.py\n• utils.py")
        ]
        state.status = .idle
        state.isConnected = true
        state.startupPhase = .ready
        return state
    }
    
    /// Creates mock state showing streaming
    static var previewStreaming: AppState {
        let state = AppState.shared
        state.messages = [
            Message.user("Find all Python files"),
            Message(role: .assistant, content: "Searching...", isStreaming: true)
        ]
        state.status = .streaming
        state.isConnected = true
        state.startupPhase = .ready
        return state
    }
    
    /// Creates mock state with tool call
    static var previewWithToolCall: AppState {
        let state = AppState.shared
        state.messages = [
            Message.user("Search for Python files")
        ]
        state.currentToolCall = ToolCall(
            name: "search_files",
            arguments: [
                "query": .string("Python files"),
                "path_filter": .string("Documents")
            ],
            status: .executing
        )
        state.status = .callingTool(toolName: "search_files")
        state.isConnected = true
        state.startupPhase = .ready
        return state
    }
    
    /// Creates mock state showing startup
    static var previewStartup: AppState {
        let state = AppState.shared
        state.startupPhase = .startingBackend
        return state
    }
}
#endif
