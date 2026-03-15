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

enum BrowseRestrictionProfile: String, CaseIterable, Identifiable {
    case strict
    case standard
    case flexible

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .strict:
            return "Strict"
        case .standard:
            return "Standard"
        case .flexible:
            return "Flexible"
        }
    }

    var description: String {
        switch self {
        case .strict:
            return "Current locked-down browsing behavior with full compliance gating."
        case .standard:
            return "Balanced browsing with fewer false blocks from robots availability and country inference."
        case .flexible:
            return "Broader browsing access while keeping SSRF, prompt-injection, and PII protections hard."
        }
    }

    var quickMenuDescription: String {
        switch self {
        case .strict:
            return "Highest restrictions and strict compliance enforcement."
        case .standard:
            return "Recommended balanced browsing with fewer false blocks."
        case .flexible:
            return "Broader access while still blocking SSRF, prompt-injection, and PII."
        }
    }
}

struct BrowsePolicyNotice: Equatable, Sendable {
    let profile: BrowseRestrictionProfile
    let message: String
    let hasWarnings: Bool

    var badgeText: String {
        if hasWarnings {
            return "Web warning"
        }
        return "Web \(profile.displayName)"
    }
}

enum ExecutionMode: String, CaseIterable, Identifiable {
    case direct
    case plan
    case teacher

    var id: String { rawValue }
    
    var config: ModeConfig {
        switch self {
        case .direct: return DirectModeConfig()
        case .plan: return PlanModeConfig()
        case .teacher: return TeacherModeConfig()
        }
    }

    var displayName: String { config.displayName }
    var description: String { config.description }
    var badgeText: String { config.badgeText }
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

private struct PersistedSessionSummary: Codable, Sendable {
    let sessionId: String
    let title: String
    let memoryMode: String
    let updatedAt: Double
    let status: String

    init(from item: SessionListItem) {
        self.sessionId = item.sessionId
        self.title = item.title
        self.memoryMode = item.memoryMode.rawValue
        self.updatedAt = item.updatedAt
        self.status = item.status
    }

    func toSessionListItem() -> SessionListItem {
        SessionListItem(
            sessionId: sessionId,
            title: title,
            memoryMode: SessionMemoryMode(rawValue: memoryMode) ?? .on,
            updatedAt: updatedAt,
            status: status
        )
    }
}

private struct PersistedConversationMessage: Codable, Sendable {
    let id: UUID
    let backendMessageId: String?
    let role: String
    let content: String
    let timestamp: Double
    let turnIndex: Int?

    @MainActor
    init(from row: MessageRowModel) {
        self.id = row.id
        self.backendMessageId = row.backendMessageId
        self.role = row.role.rawValue
        self.content = row.content
        self.timestamp = row.timestamp.timeIntervalSince1970
        self.turnIndex = row.turnIndex
    }

    @MainActor
    func toRowModel() -> MessageRowModel {
        MessageRowModel(
            id: id,
            backendMessageId: backendMessageId,
            role: MessageRole(rawValue: role) ?? .system,
            content: content,
            timestamp: Date(timeIntervalSince1970: timestamp),
            turnIndex: turnIndex,
            toolCall: nil,
            isStreaming: false
        )
    }
}

private struct PersistedConversationWindow: Codable, Sendable {
    let sessionId: String
    let messages: [PersistedConversationMessage]
    let hasOlder: Bool
    let hasNewer: Bool
    let oldestTurnIndex: Int?
    let newestTurnIndex: Int?
    let updatedAt: Double
}

private struct PersistedSessionBootstrapState: Codable, Sendable {
    let sessions: [PersistedSessionSummary]
    let activeSessionId: String
    let activeSessionTitle: String
    let windows: [PersistedConversationWindow]
}

struct RequestTimeoutNotice: Identifiable, Equatable {
    let id: String
    let requestId: String
    let code: String
    let phase: String
    let operation: String
    let timeoutSeconds: Double?
    let elapsedSeconds: Double?
    let userMessage: String
    let timestamp: Date
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
    var startupPhase: StartupPhase {
        get { ConnectionState.shared.startupPhase }
        set { ConnectionState.shared.startupPhase = newValue }
    }
    
    /// Current agent operational status
    var status: AgentStatus {
        get { ChatState.shared.status }
        set { ChatState.shared.status = newValue }
    }

    /// Human-readable detail for the current status.
    var statusDetail: String {
        get { ChatState.shared.statusDetail }
        set { ChatState.shared.statusDetail = newValue }
    }
    
    /// Live row models for the current conversation window.
    var messageRows: [MessageRowModel] {
        get { ChatState.shared.messageRows }
        set { ChatState.shared.messageRows = newValue }
    }

    /// Whether older persisted messages exist above the loaded window.
    var hasOlderMessages: Bool {
        get { ChatState.shared.hasOlderMessages }
        set { ChatState.shared.hasOlderMessages = newValue }
    }

    /// Whether newer persisted messages exist below the loaded window.
    var hasNewerMessages: Bool {
        get { ChatState.shared.hasNewerMessages }
        set { ChatState.shared.hasNewerMessages = newValue }
    }

    /// Whether an older history page is currently being fetched.
    var isLoadingOlderMessages: Bool {
        get { ChatState.shared.isLoadingOlderMessages }
        set { ChatState.shared.isLoadingOlderMessages = newValue }
    }
    
    /// Current text in the input field
    var currentInput: String {
        get { ChatState.shared.currentInput }
        set { ChatState.shared.currentInput = newValue }
    }

    /// Live Gemini text-model catalog loaded from the backend.
    @Published private(set) var availableModels: [GeminiModelOption] = []

    /// Whether the frontend is currently refreshing the live Gemini model catalog.
    @Published private(set) var isLoadingModelCatalog: Bool = false

    /// Last catalog refresh error, if any.
    @Published private(set) var modelCatalogError: String?

    /// Currently selected Gemini model identifier.
    @Published var selectedModelId: String = "" {
        didSet {
            guard selectedModelId != oldValue else { return }
            UserDefaults.standard.set(selectedModelId, forKey: Self.selectedModelKey)
        }
    }

    var selectedModel: GeminiModelOption {
        if let liveMatch = availableModels.first(where: { $0.id == selectedModelId }) {
            return liveMatch
        }
        return GeminiModelOption.placeholder(name: selectedModelId)
    }

    var modelSelectionOptions: [GeminiModelOption] {
        if availableModels.isEmpty {
            return [selectedModel]
        }
        return availableModels
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

    // Presentation styles have been migrated to UIThemeState.swift

    /// Global browse restriction profile applied to web browsing tools.
    @Published var browseRestrictionProfile: BrowseRestrictionProfile = .standard {
        didSet {
            guard browseRestrictionProfile != oldValue else { return }
            UserDefaults.standard.set(
                browseRestrictionProfile.rawValue,
                forKey: Self.browseRestrictionProfileKey
            )
            backendLogs.append("[BROWSE_PROFILE] Set to '\(browseRestrictionProfile.rawValue)'")
            if backendLogs.count > 100 {
                backendLogs.removeFirst()
            }
        }
    }


    /// Registered device manifest for capability negotiation.
    var deviceBridgeManifest: DeviceBridgeManifest {
        get { ConnectionState.shared.deviceBridgeManifest }
        set { ConnectionState.shared.deviceBridgeManifest = newValue }
    }

    /// Backend-acknowledged capability registration snapshot.
    var registeredDevice: IPCRegisteredDevice? {
        get { ConnectionState.shared.registeredDevice }
        set { ConnectionState.shared.registeredDevice = newValue }
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
    var currentToolCall: ToolCall? {
        get { ChatState.shared.currentToolCall }
        set { ChatState.shared.currentToolCall = newValue }
    }

    /// Active browse policy notice for the current response lifecycle.
    var activeBrowsePolicyNotice: BrowsePolicyNotice? {
        get { ChatState.shared.activeBrowsePolicyNotice }
        set { ChatState.shared.activeBrowsePolicyNotice = newValue }
    }

    /// Pending destructive tool call awaiting explicit user confirmation.
    var pendingDestructiveToolCall: ToolCall? {
        get { ChatState.shared.pendingDestructiveToolCall }
        set { ChatState.shared.pendingDestructiveToolCall = newValue }
    }

    /// Whether a live cancel request is waiting for backend acknowledgement.
    var isCancellationInFlight: Bool {
        get { ChatState.shared.isCancellationInFlight }
        set { ChatState.shared.isCancellationInFlight = newValue }
    }
    
    /// Whether the tool call details are expanded
    var isToolCallExpanded: Bool {
        get { ChatState.shared.isToolCallExpanded }
        set { ChatState.shared.isToolCallExpanded = newValue }
    }
    
    /// Whether the floating panel is visible
    @Published var isPanelVisible: Bool = true
    
    /// Accumulated streaming text for the current response
    var streamingText: String {
        get { ChatState.shared.streamingText }
        set { ChatState.shared.streamingText = newValue }
    }
    
    /// Whether the app is currently connected to the backend
    var isConnected: Bool {
        get { ConnectionState.shared.isConnected }
        set { ConnectionState.shared.isConnected = newValue }
    }

    /// How the app is currently connected.
    enum ConnectionMode: Equatable {
        case localBackend          // macOS: connected to local Python backend
        case remoteMac(String)     // iOS: connected to Mac via Tailscale (stores address)
        case standalone            // iOS: using IOSGeminiService with native tools
        case reconnecting(Int)     // iOS: auto-reconnecting (attempt number)
        case disconnected          // not connected

        var displayName: String {
            switch self {
            case .localBackend: return "Local Backend"
            case .remoteMac(let ip): return "Remote Mac (\(ip))"
            case .standalone: return "Standalone (iOS)"
            case .reconnecting(let n): return "Reconnecting (\(n)/3)…"
            case .disconnected: return "Disconnected"
            }
        }

        var systemImage: String {
            switch self {
            case .localBackend: return "desktopcomputer"
            case .remoteMac: return "network"
            case .standalone: return "iphone"
            case .reconnecting: return "arrow.triangle.2.circlepath"
            case .disconnected: return "wifi.slash"
            }
        }

        var isRemote: Bool {
            if case .remoteMac = self { return true }
            return false
        }
    }

    @Published var connectionMode: ConnectionMode = .disconnected

    /// Convenience: whether iOS is connected to a remote Mac backend
    var remoteBackendConnected: Bool { connectionMode.isRemote }
    
    /// Last error message
    @Published var lastError: String?

    /// Structured timeout notice for request-level model/tool/prompt timeouts.
    @Published var requestTimeoutNotice: RequestTimeoutNotice?
    
    /// Backend server logs (for debugging)
    var backendLogs: [String] = []

    /// User-selected file paths dropped into the UI and attached to new prompts.
    @Published var droppedFilePaths: [String] = []

    /// Notes for the active session.
    @Published var notes: [Note] = []

    /// Whether the notes panel is currently visible.
    @Published var isNotesPanelVisible: Bool = false

    /// Whether notes are being loaded from the backend.
    @Published private(set) var isNotesLoading: Bool = false

    /// In-memory cache for note images (image_id → platform image).
    var noteImageCache: [String: PlatformImage] = [:]

    // MARK: - Private Properties
    
    /// IPC client for backend communication
    private let ipcClient: IPCClient

    /// Abstracted AI model service (macOS: IPCClient wrapper, iOS: direct Gemini REST)
    private let geminiService: any GeminiServiceProtocol
    
    /// Backend launcher for process management (internal for Settings pairing UI access)
    let backendLauncher: BackendLauncher
    
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

    /// Last known authenticated backend endpoint context for deterministic reconnect.
    private var lastConnectedEndpointURL: String?
    private var lastConnectedAuthToken: String?

    /// UserDefaults key for persisted model selection
    private static let selectedModelKey = "selectedModel"
    private static let memoryModeKey = "memoryMode"
    private static let responseVerbosityKey = "responseVerbosity"
    private static let deepThinkKey = "deepThinkEnabled"
    private static let responsePresentationStyleKey = "responsePresentationStyle"
    private static let readableProHighContrastKey = "readableProHighContrastEnabled"
    private static let streamingAnimationStyleKey = "streamingAnimationStyle"
    private static let browseRestrictionProfileKey = "browseRestrictionProfile"
    private static let executionModeKey = "executionMode"
    private static let activeSessionIdKey = "activeSessionId"
    private static let documentSessionMapKey = "documentSessionMap"
    private static let persistedSessionBootstrapStateKey = "persistedSessionBootstrapState"
    private static let autoConnectKey = "autoConnect"
    private static let reconnectOnFailureKey = "reconnectOnFailure"
    private static let remoteMacEndpointKey = "remote_mac_endpoint"
    private static let remoteMacAuthTokenKey = "remote_mac_auth_token"
    private static let maxDroppedFilePaths = 100
    private static let maxPersistedConversationWindows = 12
    private static let autoSessionCreateCooldownSeconds: TimeInterval = 2.0
    private var isBootstrappingSessions = false
    private var isRefreshingSessions = false
    private var pendingSessionRefreshAllowAutoCreate = false
    private var lastAutoCreatedSessionAt: Date?
    private var pendingHistoryLoadToken = UUID()
    private var completeResetTask: Task<Void, Never>?
    private var toolCallCleanupTask: Task<Void, Never>?
    private var reconnectTask: Task<Void, Never>?
    private var bootstrapPersistTask: Task<Void, Never>?
    private var bootstrapPersistDirty = false
    private var bootstrapPersistSequence: UInt64 = 0
    private var pendingNotesRefreshAfterPrompt = false
    private var pendingNotesPanelRevealAfterPrompt = false
    private var reconnectAttemptCount: Int = 0
    private var isManualDisconnect = false
    private var startupInFlight = false
    private let initialHistoryPageSize = 50
    private let olderHistoryPageSize = 50
    private let maxRenderedLiveRows = 50
    private let bootstrapPersistDebounceNanoseconds: UInt64 = 350_000_000
    private var loadedOldestTurnIndex: Int?
    private var loadedNewestTurnIndex: Int?
    private let streamingRenderCoordinator = StreamingRenderCoordinator()
    private var sessionModeUpdateCounter: UInt64 = 0
    private var pendingSessionModeUpdates: [String: PendingSessionModeUpdate] = [:]
    private var lastKnownSessionModes: [String: SessionMemoryMode] = [:]
    private var reconciliationTask: Task<Void, Never>?
    private var pendingRealtimeRefreshTask: Task<Void, Never>?
    private var pendingRealtimeRefreshIncludeNotes = false
    private var lastRealtimeRefreshAt: Date = .distantPast
    private var lastLifecycleSeq: Int = 0
    private var lastKnownStoreVersion: Int = 0
    private var cachedConversationWindows: [String: PersistedConversationWindow] = [:]
    private let realtimePollIntervalNanoseconds: UInt64 = 30_000_000_000
    private let realtimeRefreshDebounceNanoseconds: UInt64 = 200_000_000

    var messages: [Message] {
        messageRows.map { $0.snapshot() }
    }
    
    // MARK: - Initialization
    
    private init() {
        self.ipcClient = IPCClient()
        #if os(macOS)
        self.geminiService = MacOSGeminiService(ipcClient: ipcClient)
        #else
        self.geminiService = IOSGeminiService()
        #endif
        self.backendLauncher = BackendLauncher()
        self.selectedModelId = Self.loadSelectedModel()
        self.memoryMode = Self.loadMemoryMode()
        self.responseVerbosity = Self.loadResponseVerbosity()
        self.deepThinkEnabled = Self.loadDeepThinkEnabled()
        // Theme states migrated to UIThemeState
        self.browseRestrictionProfile = Self.loadBrowseRestrictionProfile()
        // Remote backend mode removed — all connections are now platform-native.
        self.deviceBridgeManifest = .current()
        self.executionMode = Self.loadExecutionMode()
        self.activeSessionId = Self.loadActiveSessionId()
        _ = restorePersistedSessionBootstrapState()
        setupBindings()
        setupBackendCallbacks()

        // Forward objectWillChange from child state objects so that views
        // observing AppState re-render when proxied properties change.
        ChatState.shared.objectWillChange
            .sink { [weak self] _ in
                self?.objectWillChange.send()
            }
            .store(in: &cancellables)

        ConnectionState.shared.objectWillChange
            .sink { [weak self] _ in
                self?.objectWillChange.send()
            }
            .store(in: &cancellables)
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
                    self?.requestTimeoutNotice = nil
                    self?.startupPhase = .ready
                    self?.connectionMode = .localBackend
                    self?.startReconciliationLoopIfNeeded()
                    // Sync API key to shared UserDefaults for cross-platform access
                    let googleKey = ProcessInfo.processInfo.environment["GOOGLE_API_KEY"]?
                        .trimmingCharacters(in: .whitespacesAndNewlines)
                    let geminiKey = ProcessInfo.processInfo.environment["GEMINI_API_KEY"]?
                        .trimmingCharacters(in: .whitespacesAndNewlines)
                    if let apiKey = [googleKey, geminiKey].compactMap({ $0 }).first(where: { !$0.isEmpty }) {
                        UserDefaults.standard.set(apiKey, forKey: "gemini_api_key")
                    }
                    Task { @MainActor [weak self] in
                        await self?.refreshModelCatalogIfNeeded()
                        await self?.bootstrapSessionsIfNeeded()
                    }
                } else {
                    self?.registeredDevice = nil
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
                    guard self?.isCancellationMessage(error) != true else { return }
                    self?.lastError = error
                    self?.status = .error(message: error)
                    self?.statusDetail = error
                }
            }
            .store(in: &cancellables)

        ipcClient.$isCancellationPending
            .receive(on: DispatchQueue.main)
            .sink { [weak self] isPending in
                self?.isCancellationInFlight = isPending
            }
            .store(in: &cancellables)
        
        // Set up IPC callbacks
        setupIPCCallbacks()
    }
    
    private func setupIPCCallbacks() {
        ipcClient.onStatusChange = { [weak self] status, detail in
            guard let self else { return }
            let resolvedDetail = self.effectiveStatusDetail(for: status, detail: detail)
            if self.status != status {
                self.status = status
            }
            if self.statusDetail != resolvedDetail {
                self.statusDetail = resolvedDetail
            }
        }
        
        ipcClient.onStreamUpdate = { [weak self] delta, text, isDone in
            Task { @MainActor [weak self] in
                self?.streamingText = text
                await self?.queueStreamingUpdate(delta: delta, fullText: text, isDone: isDone)
            }
        }
        
        ipcClient.onToolCall = { [weak self] toolCall in
            self?.handleToolCallUpdate(toolCall)
        }
        
        ipcClient.onComplete = { [weak self] content in
            self?.isCancellationInFlight = false
            self?.handleComplete(content: content)
        }
        
        ipcClient.onError = { [weak self] error in
            if self?.isCancellationMessage(error) == true {
                self?.handleCancellationCompletion()
                return
            }
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

        ipcClient.onCancelled = { [weak self] in
            self?.handleCancellationCompletion()
        }

        ipcClient.onRequestTimeout = { [weak self] payload in
            self?.requestTimeoutNotice = RequestTimeoutNotice(
                id: "\(payload.requestId)-\(Date().timeIntervalSince1970)",
                requestId: payload.requestId,
                code: payload.code,
                phase: payload.phase,
                operation: payload.operation,
                timeoutSeconds: payload.timeoutSeconds,
                elapsedSeconds: payload.elapsedSeconds,
                userMessage: payload.userMessage,
                timestamp: Date()
            )
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
                    try await self.connectToEndpoint(url: context.endpointURL, authToken: context.authToken)
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
        
        // First, try environment-provided backend config.
        startupPhase = .connectingToBackend

        let envEndpointURL = ProcessInfo.processInfo.environment["AI_AGENT_BACKEND_URL"]?.trimmingCharacters(
            in: .whitespacesAndNewlines
        )
        let envAuthToken = ProcessInfo.processInfo.environment["AI_AGENT_IPC_AUTH_TOKEN"]?
            .trimmingCharacters(in: .whitespacesAndNewlines)
        if let envEndpointURL, !envEndpointURL.isEmpty {
            do {
                guard let envAuthToken, !envAuthToken.isEmpty else {
                    throw IPCRequestError.authConfigMissing
                }
                try await connectToEndpoint(url: envEndpointURL, authToken: envAuthToken)
                return
            } catch {
                backendLogs.append("[STARTUP] Failed backend endpoint \(envEndpointURL): \(error.localizedDescription)")
                if backendLogs.count > 100 {
                    backendLogs.removeFirst()
                }
            }
        }


        #if os(macOS)
        await startBackend()
        #else
        await startIOSGeminiService()
        #endif
    }
    
    /// Starts the Python backend server
    private func startBackend() async {
        startupPhase = .startingBackend
        backendStartedByApp = true
        
        do {
            let envEndpointURL = ProcessInfo.processInfo.environment["AI_AGENT_BACKEND_URL"]?.trimmingCharacters(
                in: .whitespacesAndNewlines
            )
            if let envEndpointURL, !envEndpointURL.isEmpty {
                try await backendLauncher.start(customEndpointURL: envEndpointURL)
            } else {
                try await backendLauncher.start()
            }
            // Wait for server ready callback to connect
        } catch {
            startupPhase = .failed(error.localizedDescription)
        }
    }

    #if os(iOS)
    nonisolated static func normalizedRemoteMacHost(from input: String) -> String? {
        let trimmed = input.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        if trimmed.hasPrefix("ws://") || trimmed.hasPrefix("wss://") {
            guard let url = URL(string: trimmed), let host = url.host else { return nil }
            return host.hasSuffix(".") ? String(host.dropLast()) : host
        }
        return trimmed.hasSuffix(".") ? String(trimmed.dropLast()) : trimmed
    }

    nonisolated static func isDeprecatedRemoteMacAddress(_ input: String) -> Bool {
        guard let host = normalizedRemoteMacHost(from: input) else { return false }
        return TailscaleEndpoint.isTailscaleIP(host)
    }

    /// Initializes the iOS Gemini service with the stored API key.
    /// On iOS there is no Python backend — the app talks directly to Gemini REST API.
    /// If a remote Mac address is saved (via Tailscale), it tries that first with auto-reconnect.
    private func startIOSGeminiService() async {
        startupPhase = .connectingToBackend
        var startupError: String?

        // Try saved remote Mac Tailscale address first.
        let savedAddress = UserDefaults.standard.string(forKey: Self.remoteMacEndpointKey)?
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let savedAuthToken = UserDefaults.standard.string(forKey: Self.remoteMacAuthTokenKey)?
            .trimmingCharacters(in: .whitespacesAndNewlines)

        if let savedAddress, !savedAddress.isEmpty, let savedAuthToken, !savedAuthToken.isEmpty {
            if Self.isDeprecatedRemoteMacAddress(savedAddress) {
                startupError = "Enter your Mac's Full domain (*.ts.net), not the 100.x Tailscale IP."
                backendLogs.append("[STARTUP] Refusing legacy Tailscale IPv4 remote address: \(savedAddress)")
            } else {
                let endpoint = tailscaleEndpointURL(from: savedAddress)
                // Auto-reconnect: try up to 3 times with exponential backoff
                let maxRetries = 3
                for attempt in 1...maxRetries {
                    connectionMode = .reconnecting(attempt)
                    do {
                        try await connectToEndpoint(url: endpoint, authToken: savedAuthToken)
                        connectionMode = .remoteMac(savedAddress)
                        return  // Connected to Mac backend — full tool access!
                    } catch {
                        backendLogs.append("[STARTUP] Remote Mac attempt \(attempt)/\(maxRetries) failed (\(endpoint)): \(error.localizedDescription)")
                        if attempt < maxRetries {
                            let delaySeconds = UInt64(pow(2.0, Double(attempt)))  // 2s, 4s, 8s
                            try? await Task.sleep(nanoseconds: delaySeconds * 1_000_000_000)
                        }
                    }
                }
                connectionMode = .standalone
                backendLogs.append("[STARTUP] All retries exhausted — falling back to standalone mode")
            }
        }

        // Standalone mode: use IOSGeminiService with native tools
        let storedKey = UserDefaults.standard.string(forKey: "gemini_api_key")?
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let envKey = (ProcessInfo.processInfo.environment["GOOGLE_API_KEY"]
            ?? ProcessInfo.processInfo.environment["GEMINI_API_KEY"])?
            .trimmingCharacters(in: .whitespacesAndNewlines)

        let apiKey = [storedKey, envKey].compactMap({ $0 }).first(where: { !$0.isEmpty })

        if let apiKey,
           let iosService = geminiService as? IOSGeminiService {
            iosService.setAPIKey(apiKey)
            UserDefaults.standard.set(apiKey, forKey: "gemini_api_key")
        }

        isConnected = true
        connectionMode = .standalone
        status = .idle
        statusDetail = ""
        lastError = startupError
        startupPhase = .ready
    }

    /// Connects to a remote Mac backend (called from Settings).
    /// Accepts a Tailscale MagicDNS hostname, Tailscale IP, or full ws:// / wss:// URL.
    func connectToRemoteMac() async {
        let address = UserDefaults.standard.string(forKey: Self.remoteMacEndpointKey)?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let authToken = UserDefaults.standard.string(forKey: Self.remoteMacAuthTokenKey)?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""

        guard !address.isEmpty else {
            lastError = "Enter your Mac's Tailscale address"
            return
        }
        guard !authToken.isEmpty else {
            lastError = "Enter your Mac pairing token"
            return
        }
        guard !Self.isDeprecatedRemoteMacAddress(address) else {
            lastError = "Enter your Mac's Full domain (*.ts.net), not the 100.x Tailscale IP."
            return
        }

        let endpoint = tailscaleEndpointURL(from: address)

        connectionMode = .reconnecting(1)
        do {
            try await connectToEndpoint(url: endpoint, authToken: authToken)
            connectionMode = .remoteMac(address)
            lastError = nil
        } catch {
            connectionMode = .standalone
            lastError = "Could not connect to Mac at \(address): \(error.localizedDescription)"
        }
    }

    /// Constructs a WebSocket URL from a Tailscale hostname/IP or raw ws:// / wss:// URL.
    private func tailscaleEndpointURL(from input: String) -> String {
        let trimmed = input.trimmingCharacters(in: .whitespacesAndNewlines)

        // If user already typed a full ws:// URL, use it directly
        if trimmed.hasPrefix("ws://") || trimmed.hasPrefix("wss://") {
            return trimmed
        }

        let normalizedHost = trimmed.hasSuffix(".") ? String(trimmed.dropLast()) : trimmed
        return "wss://\(normalizedHost):8765"
    }

    /// Disconnects from remote Mac and switches to standalone iOS mode.
    func disconnectRemoteAndGoStandalone() async {
        ipcClient.disconnect()
        connectionMode = .disconnected
        await startIOSGeminiService()
    }
    #endif
    
    /// Connects to a specific backend WebSocket endpoint.
    private func connectToEndpoint(url: String, authToken: String?) async throws {
        startupPhase = .connectingToBackend
        ipcClient.configureAuthToken(authToken)
        try await ipcClient.connect(toWebSocketURL: url)
        lastConnectedEndpointURL = url
        lastConnectedAuthToken = authToken
        let registered = try await ipcClient.registerDevice(deviceBridgeManifest)
        registeredDevice = registered
        
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
            startupPhase = .loadingDiagnostics
            do {
                let diagnostics = try await ipcClient.getSystemDiagnostics()
                if diagnostics.status != "ok" {
                    ipcClient.disconnect()
                    let errorDetails = diagnostics.errors.joined(separator: ", ")
                    startupPhase = .failed("System Diagnostics Failed: \(errorDetails)")
                    lastError = "Diagnostics error: \(errorDetails)"
                    return
                }
            } catch {
                ipcClient.disconnect()
                startupPhase = .failed("Failed to run system diagnostics. Is the backend healthy?")
                lastError = "Diagnostics RPC failed: \(error.localizedDescription)"
                return
            }

            startupPhase = .loadingModels
            await refreshModelCatalogIfNeeded()

            startupPhase = .loadingSessions
            await refreshSessionsInternal(allowAutoCreate: activeSessionId.isEmpty)

            if !activeSessionId.isEmpty {
                await loadSessionMessages(for: activeSessionId)
                loadNotes()
            }

            startupPhase = .ready
            return
        }

        ipcClient.disconnect()
        startupPhase = .failed(
            "Backend health check failed after retries. Verify backend startup logs and retry."
        )
        lastError = "Health check failed: backend did not respond to ping after \(attempts) attempts"
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
        requestTimeoutNotice = nil
        isSendingPrompt = true
        defer { isSendingPrompt = false }

        guard await ensureActiveSession() else {
            return
        }

        guard await ensureModelSelectionReady() else {
            return
        }

        let modelForRequest = selectedModelId
        if deepThinkEnabled {
            if !GeminiModelOption.supportsDeepThink(modelID: modelForRequest) {
                let message = "Deep Think requires a Gemini 2.5+ or Gemini 3+ reasoning model. Change model or disable Deep Think."
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
        let presentationStyleForRequest = UIThemeState.shared.responsePresentationStyle.rawValue
        let streamingAnimationForRequest = UIThemeState.shared.streamingAnimationStyle.rawValue
        let browseProfileForRequest = browseRestrictionProfile.rawValue
        completeResetTask?.cancel()
        completeResetTask = nil
        toolCallCleanupTask?.cancel()
        toolCallCleanupTask = nil
        pendingHistoryLoadToken = UUID()
        currentInput = ""
        
        // Add user message
        let userMessage = Message.user(prompt)
        appendRow(MessageRowModel(message: userMessage))
        
        // Create placeholder assistant message for streaming
        let assistantMessage = Message.streamingAssistant()
        streamingMessageId = assistantMessage.id
        appendRow(MessageRowModel(message: assistantMessage))
        streamingMessageIndex = messageRows.index(before: messageRows.endIndex)
        trimLiveConversationTailIfNeeded()
        
        // Reset state
        streamingText = ""
        currentToolCall = nil
        activeBrowsePolicyNotice = nil
        isCancellationInFlight = false
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
            "[MODEL] Prompt model='\(modelForRequest)' session='\(sessionForRequest)' memory='\(memoryModeForRequest)' execution_mode='\(executionModeForRequest)' input_paths='\(inputPathsForRequest.count)' verbosity='\(verbosityForRequest)' deep_think='\(deepThinkForRequest)' presentation='\(presentationStyleForRequest)' stream_animation='\(streamingAnimationForRequest)' browse_profile='\(browseProfileForRequest)'"
        )
        if backendLogs.count > 100 {
            backendLogs.removeFirst()
        }
        let correlationId = UUID().uuidString
        let requestId = await ipcClient.send(
            prompt: prompt,
            model: modelForRequest,
            sessionId: sessionForRequest,
            memoryMode: memoryModeForRequest,
            executionMode: executionModeForRequest,
            inputPaths: inputPathsForRequest,
            verbosity: verbosityForRequest,
            presentationStyle: presentationStyleForRequest,
            streamingAnimation: streamingAnimationForRequest,
            browseProfile: browseProfileForRequest,
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

    /// Updates the selected model identifier and persists it immediately.
    func setSelectedModel(_ modelId: String) {
        let normalized = modelId.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !normalized.isEmpty else { return }
        guard selectedModelId != normalized else { return }
        selectedModelId = normalized
        lastError = nil
        backendLogs.append("[MODEL] Selected model '\(normalized)'")
        if backendLogs.count > 100 {
            backendLogs.removeFirst()
        }
    }

    func refreshModelCatalog(forceRefresh: Bool = false) async {
        guard isConnected else { return }
        if isLoadingModelCatalog { return }
        isLoadingModelCatalog = true
        defer { isLoadingModelCatalog = false }

        do {
            let catalog = try await ipcClient.listModels(forceRefresh: forceRefresh)
            availableModels = catalog.models
            modelCatalogError = nil

            let liveModelIDs = Set(catalog.models.map(\.id))
            if selectedModelId.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
               !catalog.defaultModel.isEmpty {
                selectedModelId = catalog.defaultModel
            } else if !selectedModelId.isEmpty, !liveModelIDs.contains(selectedModelId) {
                selectedModelId = catalog.defaultModel
                backendLogs.append("[MODEL] Stored model unavailable; switched to live default '\(catalog.defaultModel)'")
                if backendLogs.count > 100 {
                    backendLogs.removeFirst()
                }
            }
        } catch {
            modelCatalogError = error.localizedDescription
            backendLogs.append("[MODEL] Live model catalog refresh failed: \(error.localizedDescription)")
            if backendLogs.count > 100 {
                backendLogs.removeFirst()
            }
        }
    }

    private func refreshModelCatalogIfNeeded() async {
        if availableModels.isEmpty || selectedModelId.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            await refreshModelCatalog()
        }
    }

    private func ensureModelSelectionReady() async -> Bool {
        await refreshModelCatalogIfNeeded()
        let selected = selectedModelId.trimmingCharacters(in: .whitespacesAndNewlines)
        if !selected.isEmpty {
            return true
        }
        let message = modelCatalogError.map { "Gemini model catalog unavailable: \($0)" }
            ?? "Gemini model catalog is unavailable. Reconnect and retry."
        lastError = message
        status = .error(message: message)
        return false
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
        UIThemeState.shared.responsePresentationStyle = style
    }

    func setReadableProHighContrastEnabled(_ enabled: Bool) {
        UIThemeState.shared.readableProHighContrastEnabled = enabled
    }

    func setStreamingAnimationStyle(_ style: StreamingAnimationStyle) {
        UIThemeState.shared.streamingAnimationStyle = style
    }

    func setBrowseRestrictionProfile(_ profile: BrowseRestrictionProfile) {
        guard browseRestrictionProfile != profile else { return }
        browseRestrictionProfile = profile
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
        clearConversationRows()
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

    /// Opens or resumes a document-specific chat session permanently linked to the URL.
    /// Returns the activeSessionId *before* the switch so the caller can pop back later.
    func pushDocumentSession(for url: URL) async -> String {
        let urlString = url.absoluteString
        var map = UserDefaults.standard.dictionary(forKey: Self.documentSessionMapKey) as? [String: String] ?? [:]
        
        let previousId = activeSessionId
        let existingId = map[urlString]
        
        // If we already have a session ID for this document, try to switch to it
        if let existingId = existingId, let target = sessions.first(where: { $0.sessionId == existingId }) {
            await switchSession(target)
            return previousId
        }
        
        // Ensure connected before creating
        guard isConnected else {
            let message = "Cannot create document session while disconnected"
            lastError = message
            status = .error(message: message)
            return previousId
        }
        
        // Otherwise, create a new session specifically for this document
        do {
            let title = "Doc: \(url.lastPathComponent)"
            let created = try await ipcClient.createSession(
                title: title,
                memoryMode: SessionMemoryMode.on.rawValue
            )
            
            // Save mapping
            map[urlString] = created.sessionId
            UserDefaults.standard.set(map, forKey: Self.documentSessionMapKey)
            
            let item = SessionListItem(from: created)
            upsertSession(item)
            
            // Switch to it
            await switchSession(item)
            
            backendLogs.append("[DOCUMENT] Created Session for '\(url.lastPathComponent)'")
            if backendLogs.count > 100 {
                backendLogs.removeFirst()
            }
            return previousId
        } catch {
            let message = "Failed to create document session: \(error.localizedDescription)"
            lastError = message
            status = .error(message: message)
            return previousId
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
                rebuildConversationRows(from: savedMessages)
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
                rebuildConversationRows(from: savedMessages)
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
                rebuildConversationRows(from: savedMessages)
            }
            let message = "Failed to delete selected sessions: \(error.localizedDescription)"
            lastError = message
            status = .error(message: message)
        }
    }
    
    /// Cancels the current operation
    func cancel() async {
        guard !isCancellationInFlight else { return }
        guard ipcClient.currentRequestId != nil else { return }
        isCancellationInFlight = true
        pendingDestructiveToolCall = nil
        requestTimeoutNotice = nil
        statusDetail = "Cancelling response..."
        await ipcClient.cancel()
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
    private func handleScreenCaptureRequest(requestId: String) {
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

    /// Handles a proxied tool execution request from the Mac backend.
    /// The backend determined this tool should run natively on the iOS device.
    private func handleProxiedToolExecution(toolName: String, arguments: [String: Any], proxyKey: String) {
        #if os(iOS)
        Task {
            DebugLogger.log("proxied_tool_start", fields: [
                "tool_name": toolName,
                "proxy_key": proxyKey,
            ])

            let result = await IOSToolExecutor.shared.execute(name: toolName, arguments: arguments)

            do {
                try await ipcClient.sendToolExecuteResponse(
                    proxyKey: proxyKey,
                    result: result
                )
                DebugLogger.log("proxied_tool_complete", fields: [
                    "tool_name": toolName,
                    "proxy_key": proxyKey,
                    "status": (result["status"] as? String) ?? "unknown",
                ])
            } catch {
                DebugLogger.log("proxied_tool_send_failed", fields: [
                    "tool_name": toolName,
                    "proxy_key": proxyKey,
                    "error": error.localizedDescription,
                ])
            }
        }
        #endif
    }
    
    /// Toggles the panel visibility
    func togglePanel() {
        isPanelVisible.toggle()
    }
    
    /// Clears all messages
    func clearMessages() {
        pendingHistoryLoadToken = UUID()
        clearConversationRows()
        isSessionHistoryLoading = false
        streamingText = ""
        currentToolCall = nil
        activeBrowsePolicyNotice = nil
        pendingDestructiveToolCall = nil
        isCancellationInFlight = false
        streamingMessageId = nil
        streamingMessageIndex = nil
        requestTimeoutNotice = nil
        Task {
            await streamingRenderCoordinator.cancelAll()
        }
    }

    func dismissRequestTimeoutNotice() {
        requestTimeoutNotice = nil
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
                    self.sortNotes()
                }
            } catch {
                DebugLogger.log("notes_load_error", fields: ["error": error.localizedDescription])
            }
        }
    }

    /// Creates a new secondary tab in the active session.
    func createNote(
        content: String,
        title: String? = nil,
        workspaceKind: String = "tab",
        completion: ((Note) -> Void)? = nil
    ) {
        let sessionId = activeSessionId
        guard !sessionId.isEmpty, !content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        Task { @MainActor [weak self] in
            guard let self else { return }
            do {
                let ipcNote = try await self.ipcClient.createNote(
                    sessionId: sessionId,
                    content: content,
                    title: title,
                    workspaceKind: workspaceKind
                )
                if self.activeSessionId == sessionId {
                    let note = ipcNote.toNote()
                    self.notes.insert(note, at: 0)
                    self.sortNotes()
                    completion?(note)
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
    func updateNote(noteId: String, content: String? = nil, isPinned: Bool? = nil, title: String? = nil) {
        let sessionId = activeSessionId
        guard !sessionId.isEmpty else { return }
        Task { @MainActor [weak self] in
            guard let self else { return }
            do {
                let ipcNote = try await self.ipcClient.updateNote(
                    sessionId: sessionId,
                    noteId: noteId,
                    content: content,
                    isPinned: isPinned,
                    title: title
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

    /// Fetches a note image by ID, returning a cached or freshly-fetched platform image.
    func fetchNoteImage(imageId: String) async -> PlatformImage? {
        if let cached = noteImageCache[imageId] { return cached }
        let sessionId = activeSessionId
        guard !sessionId.isEmpty, isConnected else { return nil }
        do {
            let ipcImage = try await ipcClient.getNoteImage(sessionId: sessionId, imageId: imageId)
            guard let data = Data(base64Encoded: ipcImage.imageData),
                  let image = PlatformImage(data: data) else {
                DebugLogger.log("note_image_decode_error", fields: ["image_id": imageId])
                return nil
            }
            noteImageCache[imageId] = image
            return image
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

    /// Sorts notes: session pad first, then pinned tabs, then tab order / recency.
    private func sortNotes() {
        notes.sort { lhs, rhs in
            if lhs.isDefaultTab != rhs.isDefaultTab { return lhs.isDefaultTab }
            if lhs.isPinned != rhs.isPinned { return lhs.isPinned }
            if lhs.tabOrder != rhs.tabOrder { return lhs.tabOrder < rhs.tabOrder }
            return lhs.updatedAt > rhs.updatedAt
        }
    }

    /// Reconnects to the backend
    func reconnect() async {
        isManualDisconnect = false
        cancelReconnectLoop()
        if await reconnectUsingLastKnownContext() {
            return
        }
        await startup()
    }

    private func reconnectUsingLastKnownContext() async -> Bool {
        guard let endpointURL = lastConnectedEndpointURL, !endpointURL.isEmpty else {
            return false
        }
        do {
            try await connectToEndpoint(url: endpointURL, authToken: lastConnectedAuthToken)
            return true
        } catch {
            backendLogs.append("[RECONNECT] Known endpoint reconnect failed: \(error.localizedDescription)")
            if backendLogs.count > 100 {
                backendLogs.removeFirst()
            }
            return false
        }
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
        if streamingMessageId != nil {
            return
        }
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
        if let seq = event.seq {
            guard seq > lastLifecycleSeq else { return }
            lastLifecycleSeq = seq
        }

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
        case "device":
            if event.action == "screen_capture_requested",
               let requestId = event.payload["request_id"] as? String,
               !requestId.isEmpty {
                handleScreenCaptureRequest(requestId: requestId)
            } else if event.action == "tool_execute_request",
               let toolName = event.payload["tool_name"] as? String,
               let proxyKey = event.payload["proxy_key"] as? String,
               !toolName.isEmpty, !proxyKey.isEmpty {
                let arguments = event.payload["arguments"] as? [String: Any] ?? [:]
                handleProxiedToolExecution(toolName: toolName, arguments: arguments, proxyKey: proxyKey)
            }
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
                let connected = await self.reconnectUsingLastKnownContext()
                if connected || self.isConnected {
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
            // Incremental path: if we have a known cursor, fetch only changes.
            if lastKnownStoreVersion > 0 {
                let (delta, maxVer) = try await ipcClient.listSessionsSince(sinceVersion: lastKnownStoreVersion)
                if !delta.isEmpty {
                    mergeSessionsDelta(delta)
                    lastKnownStoreVersion = maxVer
                }
                return
            }

            let remote = try await ipcClient.listSessions(limit: 0)
            // Seed the cursor from the full fetch.
            let maxVer = remote.compactMap(\.storeVersion).max() ?? 0
            lastKnownStoreVersion = maxVer

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
                scheduleSessionBootstrapPersistence()
            }

            if let current = sessions.first(where: { $0.sessionId == activeSessionId }) {
                applyActiveSession(
                    id: current.sessionId,
                    title: current.title,
                    memoryMode: current.memoryMode
                )
                if messageRows.isEmpty {
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
                if !messageRows.isEmpty {
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

    private func mergeSessionsDelta(_ delta: [IPCSessionSummary]) {
        var byId: [String: SessionListItem] = Dictionary(
            sessions.map { ($0.sessionId, $0) },
            uniquingKeysWith: { _, last in last }
        )
        for payload in delta {
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
            byId[item.sessionId] = item
        }
        let sorted = byId.values.sorted(by: { $0.updatedAt > $1.updatedAt })
        if sorted != sessions {
            sessions = sorted
            scheduleSessionBootstrapPersistence()
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
            let page = try await ipcClient.sessionHistoryPage(
                sessionId: sessionId,
                direction: "latest",
                limit: initialHistoryPageSize
            )
            guard pendingHistoryLoadToken == loadToken, activeSessionId == sessionId else {
                return
            }
            let rows = page.messages.map(rowModel(from:))
            setConversationRows(
                rows,
                hasOlder: page.hasOlder,
                hasNewer: false,
                oldestTurnIndex: page.oldestTurnIndex,
                newestTurnIndex: page.newestTurnIndex
            )
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
        scheduleSessionBootstrapPersistence()
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
        flushSessionBootstrapPersistence()
    }

    private func setConversationRows(
        _ rows: [MessageRowModel],
        hasOlder: Bool = false,
        hasNewer: Bool = false,
        oldestTurnIndex: Int? = nil,
        newestTurnIndex: Int? = nil
    ) {
        messageRows = rows
        hasOlderMessages = hasOlder
        hasNewerMessages = hasNewer
        loadedOldestTurnIndex = oldestTurnIndex
        loadedNewestTurnIndex = newestTurnIndex
        updateCachedConversationWindowForActiveSession()
        flushSessionBootstrapPersistence()
    }

    private func resetConversationWindowState() {
        hasOlderMessages = false
        hasNewerMessages = false
        isLoadingOlderMessages = false
        loadedOldestTurnIndex = nil
        loadedNewestTurnIndex = nil
    }

    private func clearConversationRows() {
        messageRows = []
        resetConversationWindowState()
        updateCachedConversationWindowForActiveSession()
        flushSessionBootstrapPersistence()
    }

    private func updateCachedConversationWindowForActiveSession() {
        let sessionId = activeSessionId.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !sessionId.isEmpty else { return }

        let persistedMessages = messageRows.compactMap { row -> PersistedConversationMessage? in
            let trimmed = row.content.trimmingCharacters(in: .whitespacesAndNewlines)
            if row.isStreaming && trimmed.isEmpty {
                return nil
            }
            return PersistedConversationMessage(from: row)
        }

        if persistedMessages.isEmpty {
            cachedConversationWindows.removeValue(forKey: sessionId)
            return
        }

        cachedConversationWindows[sessionId] = PersistedConversationWindow(
            sessionId: sessionId,
            messages: persistedMessages,
            hasOlder: hasOlderMessages,
            hasNewer: hasNewerMessages,
            oldestTurnIndex: loadedOldestTurnIndex,
            newestTurnIndex: loadedNewestTurnIndex,
            updatedAt: Date().timeIntervalSince1970
        )
    }

    private func updateCachedStreamingMessageSnapshot(for row: MessageRowModel) {
        let sessionId = activeSessionId.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !sessionId.isEmpty else { return }

        guard var cachedWindow = cachedConversationWindows[sessionId] else {
            updateCachedConversationWindowForActiveSession()
            return
        }

        var messages = cachedWindow.messages
        guard let lastIndex = messages.lastIndex(where: { $0.id == row.id }) else {
            updateCachedConversationWindowForActiveSession()
            return
        }

        let trimmed = row.content.trimmingCharacters(in: .whitespacesAndNewlines)
        if row.isStreaming && trimmed.isEmpty {
            messages.remove(at: lastIndex)
        } else {
            messages[lastIndex] = PersistedConversationMessage(from: row)
        }

        if messages.isEmpty {
            cachedConversationWindows.removeValue(forKey: sessionId)
            return
        }

        cachedWindow = PersistedConversationWindow(
            sessionId: cachedWindow.sessionId,
            messages: messages,
            hasOlder: hasOlderMessages,
            hasNewer: hasNewerMessages,
            oldestTurnIndex: loadedOldestTurnIndex,
            newestTurnIndex: loadedNewestTurnIndex,
            updatedAt: Date().timeIntervalSince1970
        )
        cachedConversationWindows[sessionId] = cachedWindow
    }

    private func scheduleSessionBootstrapPersistence() {
        bootstrapPersistDirty = true
        bootstrapPersistTask?.cancel()
        let delay = bootstrapPersistDebounceNanoseconds
        bootstrapPersistTask = Task { @MainActor [weak self] in
            try? await Task.sleep(nanoseconds: delay)
            guard let self, self.bootstrapPersistDirty else { return }
            self.flushSessionBootstrapPersistence()
        }
    }

    private func flushSessionBootstrapPersistence() {
        bootstrapPersistTask?.cancel()
        bootstrapPersistTask = nil
        guard bootstrapPersistDirty || !cachedConversationWindows.isEmpty || !sessions.isEmpty else { return }
        bootstrapPersistDirty = false
        let state = PersistedSessionBootstrapState(
            sessions: sessions.map(PersistedSessionSummary.init),
            activeSessionId: activeSessionId,
            activeSessionTitle: activeSessionTitle,
            windows: cachedConversationWindows
                .values
                .sorted(by: { $0.updatedAt > $1.updatedAt })
                .prefix(Self.maxPersistedConversationWindows)
                .map { $0 }
        )
        let persistKey = Self.persistedSessionBootstrapStateKey
        bootstrapPersistSequence &+= 1
        let sequence = bootstrapPersistSequence
        Task.detached(priority: .utility) {
            do {
                let data = try JSONEncoder().encode(state)
                let shouldCommit = await MainActor.run { [weak self] in
                    guard let self else { return false }
                    return self.bootstrapPersistSequence == sequence
                }
                guard shouldCommit else { return }
                UserDefaults.standard.set(data, forKey: persistKey)
            } catch {
                DebugLogger.log("session_bootstrap_persist_failed", fields: ["error": error.localizedDescription])
            }
        }
    }

    @discardableResult
    private func restorePersistedSessionBootstrapState() -> Bool {
        guard let data = UserDefaults.standard.data(forKey: Self.persistedSessionBootstrapStateKey) else {
            return false
        }
        do {
            let decoded = try JSONDecoder().decode(PersistedSessionBootstrapState.self, from: data)
            let restoredSessions = decoded.sessions.map { $0.toSessionListItem() }
            if !restoredSessions.isEmpty {
                sessions = restoredSessions.sorted(by: { $0.updatedAt > $1.updatedAt })
            }

            cachedConversationWindows = Dictionary(
                uniqueKeysWithValues: decoded.windows.map { ($0.sessionId, $0) }
            )

            let restoredActiveSessionId = activeSessionId.isEmpty ? decoded.activeSessionId : activeSessionId
            if !restoredActiveSessionId.isEmpty,
               let restoredSession = sessions.first(where: { $0.sessionId == restoredActiveSessionId }) {
                activeSessionId = restoredSession.sessionId
                activeSessionTitle = restoredSession.title
                synchronizeActiveMemoryModeWithSession(
                    sessionId: restoredSession.sessionId,
                    sessionMode: restoredSession.memoryMode
                )
            } else if !decoded.activeSessionTitle.isEmpty, activeSessionTitle == "New Session" {
                activeSessionTitle = decoded.activeSessionTitle
            }

            if let window = cachedConversationWindows[activeSessionId], !window.messages.isEmpty {
                messageRows = window.messages.map { $0.toRowModel() }
                hasOlderMessages = window.hasOlder
                hasNewerMessages = window.hasNewer
                loadedOldestTurnIndex = window.oldestTurnIndex
                loadedNewestTurnIndex = window.newestTurnIndex
            }
            return !sessions.isEmpty || !messageRows.isEmpty
        } catch {
            DebugLogger.log("session_bootstrap_restore_failed", fields: ["error": error.localizedDescription])
            return false
        }
    }

    private func snapshotMessageRows() -> [Message] {
        messageRows.map { $0.snapshot() }
    }

    private func rebuildConversationRows(
        from snapshot: [Message],
        hasOlder: Bool = false
    ) {
        setConversationRows(snapshot.map { MessageRowModel(message: $0) }, hasOlder: hasOlder)
    }

    private func rowModel(from entry: IPCSessionMessage) -> MessageRowModel {
        let role: MessageRole
        switch entry.role {
        case "user":
            role = .user
        case "assistant":
            role = .assistant
        default:
            role = .system
        }
        return MessageRowModel(
            message: Message(
                id: UUID(uuidString: entry.messageId) ?? UUID(),
                role: role,
                content: entry.content,
                timestamp: Date(timeIntervalSince1970: entry.createdAt)
            ),
            backendMessageId: entry.messageId,
            turnIndex: entry.turnIndex
        )
    }

    private func appendRow(_ row: MessageRowModel) {
        messageRows.append(row)
        if let turnIndex = row.turnIndex {
            loadedNewestTurnIndex = max(loadedNewestTurnIndex ?? turnIndex, turnIndex)
            if loadedOldestTurnIndex == nil {
                loadedOldestTurnIndex = turnIndex
            }
        }
        updateCachedConversationWindowForActiveSession()
        scheduleSessionBootstrapPersistence()
    }

    private func trimLiveConversationTailIfNeeded() {
        guard messageRows.count > maxRenderedLiveRows else { return }
        let overflow = messageRows.count - maxRenderedLiveRows
        guard overflow > 0 else { return }
        messageRows.removeFirst(overflow)
        loadedOldestTurnIndex = messageRows.first?.turnIndex
        hasOlderMessages = hasOlderMessages || loadedOldestTurnIndex != nil
        hasNewerMessages = false
        updateCachedConversationWindowForActiveSession()
        scheduleSessionBootstrapPersistence()
    }

    func loadOlderMessages() async {
        guard isConnected else { return }
        guard !isLoadingOlderMessages else { return }
        guard let anchorTurnIndex = loadedOldestTurnIndex else { return }
        guard hasOlderMessages else { return }
        guard streamingMessageId == nil else { return }

        isLoadingOlderMessages = true
        defer { isLoadingOlderMessages = false }

        do {
            let page = try await ipcClient.sessionHistoryPage(
                sessionId: activeSessionId,
                direction: "older",
                anchorTurnIndex: anchorTurnIndex,
                limit: olderHistoryPageSize
            )
            let olderRows = page.messages.map(rowModel(from:))
            guard !olderRows.isEmpty else {
                hasOlderMessages = page.hasOlder
                loadedOldestTurnIndex = page.oldestTurnIndex
                return
            }
            messageRows.insert(contentsOf: olderRows, at: 0)
            if messageRows.count > maxRenderedLiveRows {
                let overflow = messageRows.count - maxRenderedLiveRows
                messageRows.removeLast(overflow)
                hasNewerMessages = true
            }
            hasOlderMessages = page.hasOlder
            loadedOldestTurnIndex = page.oldestTurnIndex
            loadedNewestTurnIndex = messageRows.last?.turnIndex
        } catch {
            let message = "Failed to load older messages: \(error.localizedDescription)"
            lastError = message
            status = .error(message: message)
        }
    }

    func restoreLatestMessagesWindow() async {
        guard isConnected else { return }
        guard hasNewerMessages else { return }
        guard !isLoadingOlderMessages else { return }
        guard !activeSessionId.isEmpty else { return }
        guard streamingMessageId == nil else { return }

        isLoadingOlderMessages = true
        defer { isLoadingOlderMessages = false }

        do {
            let page = try await ipcClient.sessionHistoryPage(
                sessionId: activeSessionId,
                direction: "latest",
                limit: initialHistoryPageSize
            )
            let rows = page.messages.map(rowModel(from:))
            setConversationRows(
                rows,
                hasOlder: page.hasOlder,
                hasNewer: false,
                oldestTurnIndex: page.oldestTurnIndex,
                newestTurnIndex: page.newestTurnIndex
            )
        } catch {
            let message = "Failed to restore latest messages: \(error.localizedDescription)"
            lastError = message
            status = .error(message: message)
        }
    }
    
    private func queueStreamingUpdate(delta: String, fullText: String, isDone: Bool) async {
        guard let row = resolveStreamingRow() else { return }
        let rowID = row.id
        await streamingRenderCoordinator.enqueue(
            rowID: rowID,
            delta: delta,
            finalText: isDone ? fullText : nil,
            isDone: isDone
        ) { [weak self] pendingDelta, finalText, shouldFinalize in
            self?.applyStreamingUpdate(
                rowID: rowID,
                delta: pendingDelta,
                finalText: finalText,
                finalize: shouldFinalize
            )
        }
    }

    private func applyStreamingUpdate(
        rowID: UUID,
        delta: String,
        finalText: String?,
        finalize: Bool
    ) {
        guard let row = resolveStreamingRow(expectedID: rowID) else { return }
        if let finalText {
            row.replaceContent(finalText)
        } else {
            row.appendContent(delta)
        }
        updateCachedStreamingMessageSnapshot(for: row)
        scheduleSessionBootstrapPersistence()
        if finalize {
            finalizeStreamingMessage()
        }
    }
    
    /// Finalizes the streaming message (marks as no longer streaming)
    private func finalizeStreamingMessage(removeIfEmpty: Bool = false) {
        guard let row = resolveStreamingRow() else {
            return
        }

        if removeIfEmpty,
           row.content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
           row.toolCall == nil,
           let index = resolveStreamingMessageIndex() {
            messageRows.remove(at: index)
            streamingMessageId = nil
            streamingMessageIndex = nil
            return
        }

        row.isStreaming = false
        
        // Attach tool call if present
        if let toolCall = currentToolCall {
            row.toolCall = toolCall
        }
        
        streamingMessageId = nil
        streamingMessageIndex = nil
        updateCachedStreamingMessageSnapshot(for: row)
        flushSessionBootstrapPersistence()
    }
    
    /// Handles completion of a response
    private func handleComplete(content: String?) {
        isCancellationInFlight = false
        activePromptExecutionMode = nil
        if let content = content, !content.isEmpty, let row = resolveStreamingRow() {
            row.replaceContent(ToolResultFormatter.normalizeContent(content))
        }
        finalizeStreamingMessage()
        if let toolCall = currentToolCall, toolCall.status.isComplete {
            scheduleToolCallCleanup(after: 2.0)
        } else if currentToolCall != nil {
            scheduleToolCallCleanup(after: 0.9)
        }
        status = .complete
        statusDetail = "Completed"
        finalizeDeferredPromptSideEffects()

        scheduleCompleteReset(after: 2.0)
    }

    private func handleCancellationCompletion() {
        isCancellationInFlight = false
        lastError = nil
        requestTimeoutNotice = nil
        pendingDestructiveToolCall = nil
        activeBrowsePolicyNotice = nil
        activePromptExecutionMode = nil
        markCurrentToolCallFailedIfNeeded(message: "Cancelled")
        finalizeStreamingMessage(removeIfEmpty: true)
        scheduleToolCallCleanup(after: 1.2)
        status = .idle
        statusDetail = ""
        finalizeDeferredPromptSideEffects()
    }

    private func isCancellationMessage(_ message: String) -> Bool {
        let normalized = message.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return normalized.contains("request cancelled by user")
            || normalized.contains("request canceled by user")
    }

    private func resetDisconnectedUIState() {
        pendingHistoryLoadToken = UUID()
        completeResetTask?.cancel()
        completeResetTask = nil
        toolCallCleanupTask?.cancel()
        toolCallCleanupTask = nil
        Task {
            await streamingRenderCoordinator.cancelAll()
        }
        isSessionHistoryLoading = false
        isSendingPrompt = false
        streamingMessageId = nil
        streamingMessageIndex = nil
        streamingText = ""
        currentToolCall = nil
        activeBrowsePolicyNotice = nil
        pendingDestructiveToolCall = nil
        isCancellationInFlight = false
        activePromptExecutionMode = nil
        requestTimeoutNotice = nil
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
        lastLifecycleSeq = 0
        lastKnownStoreVersion = 0
        isRefreshingSessions = false
        pendingSessionRefreshAllowAutoCreate = false
        lastAutoCreatedSessionAt = nil

        if !restorePersistedSessionBootstrapState() {
            sessions = []
            activeSessionTitle = "Disconnected"
            clearConversationRows()
        }
    }

    private func invalidateInFlightResponseState(resetStatus: Bool) {
        pendingHistoryLoadToken = UUID()
        completeResetTask?.cancel()
        completeResetTask = nil
        toolCallCleanupTask?.cancel()
        toolCallCleanupTask = nil
        Task {
            await streamingRenderCoordinator.cancelAll()
        }
        streamingMessageId = nil
        streamingMessageIndex = nil
        streamingText = ""
        currentToolCall = nil
        activeBrowsePolicyNotice = nil
        pendingDestructiveToolCall = nil
        isCancellationInFlight = false
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

        updateBrowsePolicyNotice(from: currentToolCall)

        if let toolCall = currentToolCall, toolCall.status.isComplete {
            if let row = resolveStreamingRow() {
                row.toolCall = toolCall
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
                let teacherModeActive = (activePromptExecutionMode ?? executionMode) == .teacher
                if streamingMessageId != nil {
                    pendingNotesRefreshAfterPrompt = true
                    pendingNotesPanelRevealAfterPrompt =
                        pendingNotesPanelRevealAfterPrompt || teacherModeActive || !isNotesPanelVisible
                } else {
                    loadNotes()
                    if teacherModeActive || !isNotesPanelVisible {
                        NotesPanelController.shared.show()
                        isNotesPanelVisible = true
                    }
                }
            }

            scheduleToolCallCleanup(after: 2.0)
        }
    }

    private func finalizeDeferredPromptSideEffects() {
        if pendingNotesRefreshAfterPrompt {
            pendingNotesRefreshAfterPrompt = false
            loadNotes()
        }
        if pendingNotesPanelRevealAfterPrompt {
            pendingNotesPanelRevealAfterPrompt = false
            NotesPanelController.shared.show()
            isNotesPanelVisible = true
        }
    }

    private func resolveStreamingMessageIndex() -> Int? {
        guard let messageId = streamingMessageId else {
            streamingMessageIndex = nil
            return nil
        }
        if let cachedIndex = streamingMessageIndex,
           messageRows.indices.contains(cachedIndex),
           messageRows[cachedIndex].id == messageId {
            return cachedIndex
        }
        guard let resolvedIndex = messageRows.firstIndex(where: { $0.id == messageId }) else {
            streamingMessageIndex = nil
            return nil
        }
        streamingMessageIndex = resolvedIndex
        return resolvedIndex
    }

    private func resolveStreamingRow(expectedID: UUID? = nil) -> MessageRowModel? {
        guard let index = resolveStreamingMessageIndex() else { return nil }
        let row = messageRows[index]
        if let expectedID, row.id != expectedID {
            return nil
        }
        return row
    }

    private func shouldSuppressToolCallCard(_ toolCall: ToolCall) -> Bool {
        let modeForActivePrompt = activePromptExecutionMode ?? executionMode
        guard modeForActivePrompt == .plan else { return false }
        return toolCall.name == "planner"
    }

    private func updateBrowsePolicyNotice(from toolCall: ToolCall?) {
        guard let toolCall, toolCall.name == "browse_web" else {
            if currentToolCall?.name != "browse_web" {
                activeBrowsePolicyNotice = nil
            }
            return
        }

        let preview = (toolCall.result ?? toolCall.error ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard !preview.isEmpty else {
            activeBrowsePolicyNotice = nil
            return
        }

        let lines = preview
            .components(separatedBy: .newlines)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }

        let profile = lines
            .compactMap { line -> BrowseRestrictionProfile? in
                guard line.lowercased().hasPrefix("browse profile:") else { return nil }
                let value = line
                    .replacingOccurrences(of: "Browse profile:", with: "", options: [.caseInsensitive])
                    .trimmingCharacters(in: CharacterSet(charactersIn: " `"))
                    .lowercased()
                return BrowseRestrictionProfile(rawValue: value)
            }
            .first ?? browseRestrictionProfile

        if let warningLine = lines.first(where: { $0.lowercased().hasPrefix("caution:") }) {
            let warningText = warningLine
                .replacingOccurrences(of: "Caution:", with: "", options: [.caseInsensitive])
                .trimmingCharacters(in: .whitespacesAndNewlines)
            activeBrowsePolicyNotice = BrowsePolicyNotice(
                profile: profile,
                message: warningText.isEmpty ? "Browse result returned policy warnings." : warningText,
                hasWarnings: true
            )
            return
        }

        guard profile != .strict else {
            activeBrowsePolicyNotice = nil
            return
        }

        activeBrowsePolicyNotice = BrowsePolicyNotice(
            profile: profile,
            message: "Relaxed \(profile.displayName.lowercased()) browsing rules were used for this result.",
            hasWarnings: false
        )
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

    private static func loadSelectedModel() -> String {
        let stored = UserDefaults.standard.string(forKey: selectedModelKey)?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if !stored.isEmpty {
            return stored
        }
        return ""
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

    private static func loadBrowseRestrictionProfile() -> BrowseRestrictionProfile {
        if let rawValue = UserDefaults.standard.string(forKey: browseRestrictionProfileKey),
           let profile = BrowseRestrictionProfile(rawValue: rawValue) {
            return profile
        }
        let fallback: BrowseRestrictionProfile = .standard
        UserDefaults.standard.set(fallback.rawValue, forKey: browseRestrictionProfileKey)
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
        case .initializing, .startingBackend, .connectingToBackend, .performingHealthCheck,
             .loadingDiagnostics, .loadingModels, .loadingSessions:
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
        state.rebuildConversationRows(from: [
            Message.user("Find all Python files in Documents"),
            Message.assistant("I found 15 Python files in your Documents folder:\n• main.py\n• config.py\n• utils.py")
        ])
        state.status = .idle
        state.isConnected = true
        state.startupPhase = .ready
        return state
    }
    
    /// Creates mock state showing streaming
    static var previewStreaming: AppState {
        let state = AppState.shared
        state.rebuildConversationRows(from: [
            Message.user("Find all Python files"),
            Message(role: .assistant, content: "Searching...", isStreaming: true)
        ])
        state.status = .streaming
        state.isConnected = true
        state.startupPhase = .ready
        return state
    }
    
    /// Creates mock state with tool call
    static var previewWithToolCall: AppState {
        let state = AppState.shared
        state.rebuildConversationRows(from: [
            Message.user("Search for Python files")
        ])
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
