import Foundation
import Security

enum TailscaleEndpoint {
    static func isTailscaleIP(_ host: String) -> Bool {
        let parts = host.split(separator: ".").compactMap { UInt8($0) }
        guard parts.count == 4, parts[0] == 100 else { return false }
        return parts[1] >= 64 && parts[1] <= 127
    }

    static func isTailscaleDNSName(_ host: String) -> Bool {
        let normalized = normalizedHost(host)
        return normalized.hasSuffix(".ts.net")
    }

    static func isTailscaleHost(_ host: String) -> Bool {
        isTailscaleIP(host) || isTailscaleDNSName(host)
    }

    static func normalizedHost(_ host: String) -> String {
        let trimmed = host.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return trimmed.hasSuffix(".") ? String(trimmed.dropLast()) : trimmed
    }

    static func upgradeToTLS(_ url: URL) -> URL {
        guard let host = url.host,
              isTailscaleHost(host),
              url.scheme?.lowercased() == "ws" else {
            return url
        }
        guard var components = URLComponents(url: url, resolvingAgainstBaseURL: false) else {
            return url
        }
        components.scheme = "wss"
        return components.url ?? url
    }
}

/// URLSession delegate that validates the backend's self-signed TLS certificate
/// when connecting over Tailscale. All other connections use the system default.
private final class TailscaleSessionDelegate: NSObject, URLSessionDelegate, URLSessionTaskDelegate {

    // Session-level server trust challenge
    func urlSession(
        _ session: URLSession,
        didReceive challenge: URLAuthenticationChallenge,
        completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void
    ) {
        handleChallenge(challenge, completionHandler: completionHandler)
    }

    // Task-level server trust challenge (URLSessionWebSocketTask routes challenges here)
    func urlSession(
        _ session: URLSession,
        task: URLSessionTask,
        didReceive challenge: URLAuthenticationChallenge,
        completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void
    ) {
        handleChallenge(challenge, completionHandler: completionHandler)
    }

    private func handleChallenge(
        _ challenge: URLAuthenticationChallenge,
        completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void
    ) {
        guard challenge.protectionSpace.authenticationMethod == NSURLAuthenticationMethodServerTrust,
              let serverTrust = challenge.protectionSpace.serverTrust else {
            completionHandler(.performDefaultHandling, nil)
            return
        }

        let host = TailscaleEndpoint.normalizedHost(challenge.protectionSpace.host)
        if TailscaleEndpoint.isTailscaleHost(host),
           Self.validatePinnedSelfSignedTrust(serverTrust, host: host) {
            let credential = URLCredential(trust: serverTrust)
            DebugLogger.log("tailscale_tls_trust", fields: ["host": host, "result": "accepted"])
            completionHandler(.useCredential, credential)
        } else {
            DebugLogger.log("tailscale_tls_trust", fields: [
                "host": host,
                "result": TailscaleEndpoint.isTailscaleHost(host) ? "rejected" : "default"
            ])
            if TailscaleEndpoint.isTailscaleHost(host) {
                completionHandler(.cancelAuthenticationChallenge, nil)
            } else {
                completionHandler(.performDefaultHandling, nil)
            }
        }
    }

    private static func validatePinnedSelfSignedTrust(_ serverTrust: SecTrust, host: String) -> Bool {
        guard let certificateChain = SecTrustCopyCertificateChain(serverTrust) as? [SecCertificate],
              let leafCertificate = certificateChain.first else {
            return false
        }
        let policy = SecPolicyCreateSSL(true, host as CFString)
        SecTrustSetPolicies(serverTrust, policy)
        SecTrustSetAnchorCertificates(serverTrust, [leafCertificate] as CFArray)
        SecTrustSetAnchorCertificatesOnly(serverTrust, true)
        return SecTrustEvaluateWithError(serverTrust, nil)
    }
}

/// Manages the WebSocket connection to the backend.
@MainActor
final class SocketManager {

    enum ConnectionState: Equatable {
        case disconnected
        case connecting
        case connected
        case failed(String)
    }

    private(set) var state: ConnectionState = .disconnected
    private var connectionWaiters: [UUID: CheckedContinuation<Void, Error>] = [:]
    private var session: URLSession?
    private var sessionDelegate: URLSessionDelegate?
    private var webSocketTask: URLSessionWebSocketTask?
    private var connectionGeneration: UInt64 = 0
    private let queue = DispatchQueue(label: "com.aiagent.websocketmanager", qos: .userInitiated)
    private var currentEndpointURL: URL?
    private var lastSuccessfulEndpointURL: URL?
    private var connectionProbeTask: Task<Void, Never>?
    private let parser = StreamingParser()
    let dispatcher = MessageDispatcher()

    var onStateChange: ((ConnectionState) -> Void)?
    var onDataReceived: ((Data) -> Void)?
    var onError: ((SocketError) -> Void)?

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

    func connect() async throws {
        guard let rawURL = ProcessInfo.processInfo.environment["AI_AGENT_BACKEND_URL"]?
            .trimmingCharacters(in: .whitespacesAndNewlines),
              !rawURL.isEmpty else {
            throw SocketError.noConfiguredEndpoint
        }
        try await connect(toURLString: rawURL)
    }

    func connect(toURLString urlString: String) async throws {
        guard let rawURL = URL(string: urlString), let scheme = rawURL.scheme?.lowercased(), ["ws", "wss"].contains(scheme) else {
            throw SocketError.connectionFailed("Invalid WebSocket URL: \(urlString)")
        }
        // Auto-upgrade ws:// → wss:// for Tailscale IPs (backend serves TLS)
        let url = TailscaleEndpoint.upgradeToTLS(rawURL)

        switch state {
        case .connected:
            if currentEndpointURL == url { return }
            disconnect()
        case .connecting:
            if currentEndpointURL == url {
                try await waitForConnection(timeout: 5.0)
                return
            }
            throw SocketError.alreadyConnecting
        case .failed:
            disconnect()
        case .disconnected:
            break
        }

        updateState(.connecting)
        currentEndpointURL = url
        connectionGeneration &+= 1
        let generation = connectionGeneration

        // Use the self-signed cert trust delegate for Tailscale IPs;
        // all other connections enforce standard ATS certificate validation.
        let config = URLSessionConfiguration.default
        let isTailscale = TailscaleEndpoint.isTailscaleHost(url.host ?? "")
        let sessionDelegate: URLSessionDelegate? = isTailscale ? TailscaleSessionDelegate() : nil
        self.sessionDelegate = sessionDelegate
        let session = URLSession(configuration: config, delegate: sessionDelegate, delegateQueue: nil)
        let task = session.webSocketTask(with: url)
        self.session = session
        self.webSocketTask = task
        task.resume()
        startReceiving(generation: generation)
        startConnectionProbe(generation: generation)

        do {
            try await waitForConnection(timeout: 5.0)
        } catch {
            clearConnectionResources(cancelTask: true)
            updateState(.failed(error.localizedDescription))
            throw error
        }
    }

    func disconnect() {
        clearConnectionResources(cancelTask: true)
        updateState(.disconnected)
    }

    func reconnect() async throws {
        if let currentEndpointURL {
            disconnect()
            try await connect(toURLString: currentEndpointURL.absoluteString)
            return
        }
        if let lastSuccessfulEndpointURL {
            disconnect()
            try await connect(toURLString: lastSuccessfulEndpointURL.absoluteString)
            return
        }
        disconnect()
        try await connect()
    }

    func send(_ data: Data) async throws {
        guard state == .connected, let webSocketTask else {
            throw SocketError.notConnected
        }
        return try await withCheckedThrowingContinuation { continuation in
            webSocketTask.send(.data(data)) { error in
                if let error {
                    continuation.resume(throwing: SocketError.sendFailed(error.localizedDescription))
                } else {
                    continuation.resume()
                }
            }
        }
    }

    func send(_ string: String) async throws {
        guard state == .connected, let webSocketTask else {
            throw SocketError.notConnected
        }
        return try await withCheckedThrowingContinuation { continuation in
            webSocketTask.send(.string(string)) { error in
                if let error {
                    continuation.resume(throwing: SocketError.sendFailed(error.localizedDescription))
                } else {
                    continuation.resume()
                }
            }
        }
    }

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
        browseProfile: String?,
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
            browseProfile: browseProfile,
            deepThink: deepThink,
            correlationId: correlationId
        )
        guard let json = request.toJSONString() else {
            throw SocketError.encodingError
        }
        try await send(json)
        return resolvedRequestId
    }

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

    func sendCancel(targetRequestId: String? = nil) async throws {
        let request = CancelRequest(targetRequestId: targetRequestId)
        guard let json = request.toJSONString() else {
            throw SocketError.encodingError
        }
        try await send(json)
    }

    func sendPing() async throws -> String {
        let request = PingRequest()
        guard let json = request.toJSONString() else {
            throw SocketError.encodingError
        }
        try await send(json)
        return request.id
    }

    private func updateState(_ newState: ConnectionState) {
        guard state != newState else { return }
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
        DebugLogger.log("socket_state_transition", fields: ["state": String(describing: newState)])
        DispatchQueue.main.async { [weak self] in
            self?.onStateChange?(newState)
        }
    }

    private func waitForConnection(timeout: TimeInterval) async throws {
        if state == .connected { return }
        if case .failed(let error) = state { throw SocketError.connectionFailed(error) }

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

    private func startConnectionProbe(generation: UInt64) {
        connectionProbeTask?.cancel()
        guard let webSocketTask else { return }
        connectionProbeTask = Task { [weak self] in
            do {
                try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
                    webSocketTask.sendPing { error in
                        if let error {
                            continuation.resume(throwing: error)
                        } else {
                            continuation.resume()
                        }
                    }
                }
                await MainActor.run {
                    guard let self else { return }
                    guard generation == self.connectionGeneration else { return }
                    self.lastSuccessfulEndpointURL = self.currentEndpointURL
                    self.updateState(.connected)
                }
            } catch {
                await MainActor.run {
                    guard let self else { return }
                    guard generation == self.connectionGeneration else { return }
                    self.clearConnectionResources(cancelTask: true)
                    self.updateState(.failed(error.localizedDescription))
                    self.onError?(.connectionFailed(error.localizedDescription))
                }
            }
        }
    }

    private func startReceiving(generation: UInt64) {
        guard let webSocketTask else { return }
        webSocketTask.receive { [weak self] result in
            Task { @MainActor [weak self] in
                guard let self else { return }
                guard generation == self.connectionGeneration else { return }
                switch result {
                case .success(let message):
                    self.lastSuccessfulEndpointURL = self.currentEndpointURL
                    if self.state != .connected {
                        self.updateState(.connected)
                    }
                    let data: Data?
                    switch message {
                    case .data(let payload):
                        data = Self.delimitedData(payload)
                    case .string(let payload):
                        data = Self.delimitedData(payload.data(using: .utf8) ?? Data())
                    @unknown default:
                        data = nil
                    }
                    if let data, !data.isEmpty {
                        self.queue.async {
                            self.parser.processData(data)
                        }
                        self.onDataReceived?(data)
                    }
                    self.startReceiving(generation: generation)
                case .failure(let error):
                    self.clearConnectionResources(cancelTask: false)
                    self.updateState(.failed(error.localizedDescription))
                    self.onError?(.receiveError(error.localizedDescription))
                }
            }
        }
    }

    private static func delimitedData(_ data: Data) -> Data {
        guard let newline = "\n".data(using: .utf8) else { return data }
        if data.suffix(1) == newline { return data }
        var framed = data
        framed.append(newline)
        return framed
    }

    private func clearConnectionResources(cancelTask: Bool) {
        connectionGeneration &+= 1
        connectionProbeTask?.cancel()
        connectionProbeTask = nil
        if cancelTask {
            webSocketTask?.cancel(with: .goingAway, reason: nil)
        }
        webSocketTask = nil
        session?.invalidateAndCancel()
        session = nil
        sessionDelegate = nil
        currentEndpointURL = nil
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
            throw SocketError.noConfiguredEndpoint
        }

        let connectImpl = connector ?? { [weak self] endpoint in
            guard let self else {
                throw SocketError.connectionFailed("WebSocket manager is unavailable")
            }
            try await self.connect(toURLString: endpoint)
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
            "Unable to connect to any endpoint candidate (\(candidates.count) attempted). \(errors.joined(separator: " | "))"
        )
    }
}

enum SocketError: Error, LocalizedError {
    case noConfiguredEndpoint
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
        case .noConfiguredEndpoint:
            return "No backend WebSocket endpoint is configured."
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
