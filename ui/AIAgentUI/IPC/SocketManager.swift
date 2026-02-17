//
//  SocketManager.swift
//  AIAgentUI
//
//  Created for Personal macOS AI Agent
//  Status: Active - Unix Domain Socket connection management
//

import Foundation
import Network
import Darwin

/// Manages the Unix Domain Socket connection to the Python backend
/// Uses NWConnection for modern async networking
@MainActor
final class SocketManager {
    
    // MARK: - Properties
    
    /// Connection state
    enum ConnectionState: Equatable {
        case disconnected
        case connecting
        case connected
        case failed(String)
    }
    
    /// Current connection state
    private(set) var state: ConnectionState = .disconnected

    /// Awaiters waiting for connection completion.
    private var connectionWaiters: [UUID: CheckedContinuation<Void, Error>] = [:]
    
    /// The NWConnection instance
    private var connection: NWConnection?
    
    /// Dispatch queue for network operations
    private let queue = DispatchQueue(label: "com.aiagent.socketmanager", qos: .userInitiated)
    
    /// Socket path template - PID will be substituted
    private let socketPathTemplate = "/tmp/ai-agent-%d.sock"
    
    /// Current socket path
    private var currentSocketPath: String?
    
    /// Streaming parser for incoming data
    private let parser = StreamingParser()
    
    /// Message dispatcher
    let dispatcher = MessageDispatcher()
    
    // MARK: - Callbacks
    
    /// Called when connection state changes
    var onStateChange: ((ConnectionState) -> Void)?
    
    /// Called when data is received
    var onDataReceived: ((Data) -> Void)?
    
    /// Called when an error occurs
    var onError: ((SocketError) -> Void)?
    
    // MARK: - Initialization
    
    init() {
        setupParser()
    }
    
    private func setupParser() {
        parser.onMessageReceived = { [weak self] message in
            self?.dispatcher.dispatch(message)
        }
        
        parser.onError = { [weak self] error in
            self?.onError?(.parsingError(error.localizedDescription))
        }
    }
    
    // MARK: - Connection Management
    
    /// Connects to the Python backend socket
    /// - Parameter pid: Process ID of the Python backend (optional, will scan if not provided)
    func connect(pid: Int? = nil) async throws {
        // If PID provided, try direct connection
        if let pid = pid {
            let path = String(format: socketPathTemplate, pid)
            try await connect(toPath: path)
            return
        }
        
        // Otherwise, scan for available sockets
        let candidates = findAvailableSockets()
        guard !candidates.isEmpty else {
            throw SocketError.noAvailableSocket
        }

        try await connectUsingCandidates(candidates)
    }
    
    /// Connects to a specific socket path
    /// - Parameter path: The Unix socket path
    func connect(toPath path: String) async throws {
        switch state {
        case .connected:
            return  // Already connected
        case .connecting:
            // Allow idempotent connect calls when the same socket is already
            // in-flight. This prevents duplicate startup/reconnect paths from
            // failing with a transient "Already attempting to connect" error.
            if currentSocketPath == path {
                try await waitForConnection(timeout: 5.0)
                return
            }
            throw SocketError.alreadyConnecting
        case .failed:
            // Reset stale failed connection state before retrying.
            disconnect()
        case .disconnected:
            break
        }
        
        updateState(.connecting)
        currentSocketPath = path
        
        // Create Unix socket endpoint
        let endpoint = NWEndpoint.unix(path: path)
        
        // Create connection with parameters
        let parameters = NWParameters()
        parameters.defaultProtocolStack.transportProtocol = NWProtocolTCP.Options()
        
        let connection = NWConnection(to: endpoint, using: parameters)
        self.connection = connection
        
        // Set up state handler
        connection.stateUpdateHandler = { [weak self] state in
            Task { @MainActor [weak self] in
                self?.handleStateUpdate(state)
            }
        }
        
        // Start the connection
        connection.start(queue: queue)
        
        // Wait for connection with timeout
        try await waitForConnection(timeout: 5.0)
        
        // Start receiving data
        startReceiving()
    }
    
    /// Disconnects from the socket
    func disconnect() {
        clearConnectionResources(cancelConnection: true)
        updateState(.disconnected)
    }
    
    /// Reconnects to the socket
    func reconnect() async throws {
        disconnect()
        try await connect()
    }
    
    // MARK: - Data Transmission
    
    /// Sends data through the socket
    /// - Parameter data: Data to send
    func send(_ data: Data) async throws {
        guard state == .connected, let connection = connection else {
            throw SocketError.notConnected
        }
        
        return try await withCheckedThrowingContinuation { continuation in
            connection.send(content: data, completion: .contentProcessed { error in
                if let error = error {
                    continuation.resume(throwing: SocketError.sendFailed(error.localizedDescription))
                } else {
                    continuation.resume()
                }
            })
        }
    }
    
    /// Sends a string through the socket (with newline delimiter)
    /// - Parameter string: String to send
    func send(_ string: String) async throws {
        let terminated = string.hasSuffix("\n") ? string : string + "\n"
        guard let data = terminated.data(using: .utf8) else {
            throw SocketError.encodingError
        }
        try await send(data)
    }
    
    /// Sends a prompt request.
    /// - Parameters:
    ///   - text: The prompt text.
    ///   - model: The Gemini model to use for this request.
    ///   - sessionId: Session identifier for memory partitioning.
    ///   - memoryMode: Memory behavior (`on`, `off`, `ephemeral`).
    ///   - executionMode: Prompt execution mode (`direct`, `plan`).
    ///   - inputPaths: Optional user-selected file paths for this prompt.
    ///   - verbosity: Response verbosity (`low`, `medium`, `high`, `extra_high`).
    ///   - presentationStyle: Response rendering style (`readable_pro`, `glass_editorial`, `dense_technical`).
    ///   - streamingAnimation: Streaming animation style (`wave_reveal`, `typewriter_luxe`, `minimal_motion`).
    ///   - deepThink: Enables stronger reasoning mode when supported by backend/model.
    ///   - correlationId: Correlation id generated at UI action boundary.
    ///   - requestId: Optional request identifier to enforce before send.
    /// - Returns: The request ID for tracking responses.
    func sendPrompt(
        _ text: String,
        model: String,
        sessionId: String?,
        memoryMode: String?,
        executionMode: String?,
        inputPaths: [String]?,
        verbosity: String?,
        presentationStyle: String?,
        streamingAnimation: String?,
        deepThink: Bool?,
        correlationId: String?,
        requestId: String? = nil
    ) async throws -> String {
        let resolvedRequestId = requestId ?? UUID().uuidString
        let request = PromptRequest(
            id: resolvedRequestId,
            text: text,
            model: model,
            sessionId: sessionId,
            memoryMode: memoryMode,
            executionMode: executionMode,
            inputPaths: inputPaths,
            verbosity: verbosity,
            presentationStyle: presentationStyle,
            streamingAnimation: streamingAnimation,
            deepThink: deepThink,
            correlationId: correlationId
        )
        guard let json = request.toJSONString() else {
            throw SocketError.encodingError
        }
        try await send(json)
        return resolvedRequestId
    }

    /// Sends a generic JSON-RPC request.
    /// - Parameters:
    ///   - method: RPC method.
    ///   - params: JSON-RPC params map.
    /// - Returns: The generated request id.
    func sendRequest(method: String, params: [String: AnyCodable] = [:]) async throws -> String {
        let request = IPCRequest(method: method, params: params)
        let encoder = JSONEncoder()
        let data = try encoder.encode(request)
        guard let json = String(data: data, encoding: .utf8) else {
            throw SocketError.encodingError
        }
        try await send(json)
        return request.id
    }
    
    /// Sends a cancel request
    func sendCancel(targetRequestId: String? = nil) async throws {
        let request = CancelRequest(targetRequestId: targetRequestId)
        guard let json = request.toJSONString() else {
            throw SocketError.encodingError
        }
        try await send(json)
    }
    
    /// Sends a ping request for health check
    /// - Returns: The request ID for tracking response
    func sendPing() async throws -> String {
        let request = PingRequest()
        guard let json = request.toJSONString() else {
            throw SocketError.encodingError
        }
        try await send(json)
        return request.id
    }
    
    // MARK: - Private Methods
    
    private func updateState(_ newState: ConnectionState) {
        state = newState
        switch newState {
        case .connected:
            resolveConnectionWaiters(result: .success(()))
        case .failed(let error):
            resolveConnectionWaiters(result: .failure(SocketError.connectionFailed(error)))
        case .disconnected:
            if !connectionWaiters.isEmpty {
                resolveConnectionWaiters(result: .failure(SocketError.notConnected))
            }
        case .connecting:
            break
        }
        DebugLogger.log(
            "socket_state_transition",
            fields: ["state": String(describing: newState)]
        )
        DispatchQueue.main.async { [weak self] in
            self?.onStateChange?(newState)
        }
    }
    
    private func handleStateUpdate(_ state: NWConnection.State) {
        switch state {
        case .ready:
            DebugLogger.log("nwconnection_ready")
            updateState(.connected)
        case .waiting(let error):
            DebugLogger.log("nwconnection_waiting", fields: ["error": error.localizedDescription])
            updateState(.failed(error.localizedDescription))
        case .failed(let error):
            DebugLogger.log("nwconnection_failed", fields: ["error": error.localizedDescription])
            updateState(.failed(error.localizedDescription))
            onError?(.connectionFailed(error.localizedDescription))
        case .cancelled:
            DebugLogger.log("nwconnection_cancelled")
            updateState(.disconnected)
        default:
            break
        }
    }
    
    private func waitForConnection(timeout: TimeInterval) async throws {
        if state == .connected {
            return
        }
        if case .failed(let error) = state {
            throw SocketError.connectionFailed(error)
        }

        let waiterId = UUID()
        let timeoutTask = Task { [weak self] in
            try? await Task.sleep(nanoseconds: UInt64(timeout * 1_000_000_000))
            await MainActor.run {
                guard let self else { return }
                guard let continuation = self.connectionWaiters.removeValue(forKey: waiterId) else { return }
                continuation.resume(throwing: SocketError.connectionTimeout)
            }
        }
        defer { timeoutTask.cancel() }

        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            connectionWaiters[waiterId] = continuation
        }
    }
    
    private func startReceiving() {
        connection?.receive(minimumIncompleteLength: 1, maximumLength: 65536) { [weak self] data, _, isComplete, error in
            Task { @MainActor [weak self] in
                guard let self else { return }
                if let error = error {
                    self.clearConnectionResources(cancelConnection: false)
                    self.updateState(.failed(error.localizedDescription))
                    self.onError?(.receiveError(error.localizedDescription))
                    return
                }

                if let data = data, !data.isEmpty {
                    self.parser.processData(data)
                    self.onDataReceived?(data)
                }

                if isComplete {
                    self.clearConnectionResources(cancelConnection: false)
                    self.updateState(.disconnected)
                    return
                }

                self.startReceiving()
            }
        }
    }

    private func clearConnectionResources(cancelConnection: Bool) {
        if cancelConnection {
            connection?.cancel()
        }
        connection = nil
        currentSocketPath = nil
        parser.reset()
        dispatcher.clearAll()
    }

    private func resolveConnectionWaiters(result: Result<Void, Error>) {
        guard !connectionWaiters.isEmpty else { return }
        let waiters = connectionWaiters.values
        connectionWaiters.removeAll()
        for continuation in waiters {
            switch result {
            case .success:
                continuation.resume()
            case .failure(let error):
                continuation.resume(throwing: error)
            }
        }
    }

    func connectUsingCandidates(
        _ candidates: [String],
        connector: ((String) async throws -> Void)? = nil
    ) async throws {
        guard !candidates.isEmpty else {
            throw SocketError.noAvailableSocket
        }

        let connectImpl = connector ?? { [weak self] path in
            guard let self else {
                throw SocketError.connectionFailed("Socket manager is unavailable")
            }
            try await self.connect(toPath: path)
        }

        var errors: [String] = []
        for candidate in candidates {
            do {
                try await connectImpl(candidate)
                return
            } catch {
                errors.append("\(candidate): \(error.localizedDescription)")
                disconnect()
            }
        }

        throw SocketError.connectionFailed(
            "Unable to connect to any socket candidate (\(candidates.count) attempted). \(errors.joined(separator: " | "))"
        )
    }

    private func findAvailableSockets() -> [String] {
        let fileManager = FileManager.default
        let tmpURL = URL(fileURLWithPath: "/tmp", isDirectory: true)
        let keys: [URLResourceKey] = [.contentModificationDateKey]
        let currentUID = Int(getuid())

        guard let entries = try? fileManager.contentsOfDirectory(
            at: tmpURL,
            includingPropertiesForKeys: keys,
            options: [.skipsHiddenFiles]
        ) else {
            return []
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
            .map(\.path)

        return candidates
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
}

// MARK: - Errors

enum SocketError: Error, LocalizedError {
    case noAvailableSocket
    case alreadyConnecting
    case connectionFailed(String)
    case connectionTimeout
    case notConnected
    case sendFailed(String)
    case receiveError(String)
    case encodingError
    case parsingError(String)
    
    var errorDescription: String? {
        switch self {
        case .noAvailableSocket:
            return "No Python backend socket found. Is the agent running?"
        case .alreadyConnecting:
            return "Already attempting to connect"
        case .connectionFailed(let reason):
            return "Connection failed: \(reason)"
        case .connectionTimeout:
            return "Connection timed out"
        case .notConnected:
            return "Not connected to backend"
        case .sendFailed(let reason):
            return "Failed to send data: \(reason)"
        case .receiveError(let reason):
            return "Failed to receive data: \(reason)"
        case .encodingError:
            return "Failed to encode message"
        case .parsingError(let reason):
            return "Failed to parse response: \(reason)"
        }
    }
}
