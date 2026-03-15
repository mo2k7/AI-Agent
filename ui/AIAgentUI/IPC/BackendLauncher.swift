#if os(macOS)
//
//  BackendLauncher.swift
//  AIAgentUI
//
//  Created for Personal macOS AI Agent
//  Status: Active - Python backend process management
//

import Darwin
import Foundation

struct BackendReadyContext: Sendable {
    let endpointURL: String
    let authToken: String
}

struct TailscaleIdentity: Sendable, Equatable {
    let dnsName: String?
    let ipAddress: String?
}

struct CapturedProcessResult: Sendable {
    let terminationStatus: Int32
    let stdout: String
    let stderr: String
}

enum ChildProcessCapture {
    static func run(
        executableURL: URL,
        arguments: [String],
        currentDirectoryURL: URL,
        environment: [String: String]
    ) async throws -> CapturedProcessResult {
        try await withCheckedThrowingContinuation { continuation in
            DispatchQueue.global(qos: .userInitiated).async {
                let process = Process()
                process.executableURL = executableURL
                process.arguments = arguments
                process.currentDirectoryURL = currentDirectoryURL
                process.environment = environment

                let stdoutPipe = Pipe()
                let stderrPipe = Pipe()
                process.standardOutput = stdoutPipe
                process.standardError = stderrPipe

                do {
                    try process.run()
                } catch {
                    stdoutPipe.fileHandleForReading.closeFile()
                    stdoutPipe.fileHandleForWriting.closeFile()
                    stderrPipe.fileHandleForReading.closeFile()
                    stderrPipe.fileHandleForWriting.closeFile()
                    continuation.resume(throwing: error)
                    return
                }

                let group = DispatchGroup()
                let stdoutData = DataCaptureBox()
                let stderrData = DataCaptureBox()

                group.enter()
                DispatchQueue.global(qos: .userInitiated).async {
                    stdoutData.store(stdoutPipe.fileHandleForReading.readDataToEndOfFile())
                    group.leave()
                }

                group.enter()
                DispatchQueue.global(qos: .userInitiated).async {
                    stderrData.store(stderrPipe.fileHandleForReading.readDataToEndOfFile())
                    group.leave()
                }

                process.waitUntilExit()
                stdoutPipe.fileHandleForWriting.closeFile()
                stderrPipe.fileHandleForWriting.closeFile()
                group.wait()
                stdoutPipe.fileHandleForReading.closeFile()
                stderrPipe.fileHandleForReading.closeFile()

                continuation.resume(
                    returning: CapturedProcessResult(
                        terminationStatus: process.terminationStatus,
                        stdout: String(data: stdoutData.load(), encoding: .utf8) ?? "",
                        stderr: String(data: stderrData.load(), encoding: .utf8) ?? ""
                    )
                )
            }
        }
    }
}

private final class DataCaptureBox: @unchecked Sendable {
    private let lock = NSLock()
    private var data = Data()

    func store(_ newValue: Data) {
        lock.lock()
        data = newValue
        lock.unlock()
    }

    func load() -> Data {
        lock.lock()
        defer { lock.unlock() }
        return data
    }
}

/// Manages the lifecycle of the Python backend process
/// Spawns, monitors, and terminates the backend server
@MainActor
final class BackendLauncher {
    
    // MARK: - Properties
    
    /// Backend launch state
    enum State: Equatable, Sendable {
        case notStarted
        case starting
        case running(pid: Int32)
        case failed(String)
        case terminated
    }
    
    /// Current state
    private(set) var state: State = .notStarted
    
    /// The running process (wrapped in unchecked for Sendable isolation)
    private var processRef: ProcessRef?
    
    /// WebSocket endpoint URL for the backend
    private(set) var endpointURL: String?

    /// Per-process IPC auth token required by backend auth.hello.
    private(set) var authToken: String?

    /// Stable pairing token shared with the background daemon.
    var pairingAuthToken: String? { try? Self.loadOrCreatePairingAuthToken() }

    /// Detected Tailscale identity for remote pairing.
    var tailscaleIdentity: TailscaleIdentity? { Self.detectTailscaleIdentity() }

    /// Detected Tailscale MagicDNS hostname for remote pairing.
    var tailscaleDNSName: String? { tailscaleIdentity?.dnsName }

    /// Detected Tailscale IP address for remote pairing.
    var tailscaleIP: String? { tailscaleIdentity?.ipAddress }

    /// Full Tailscale WebSocket endpoint URL for iOS pairing.
    var tailscaleEndpointURL: String? {
        if let dnsName = tailscaleDNSName {
            return "wss://\(dnsName):8765"
        }
        if let ip = tailscaleIP {
            return "wss://\(ip):8765"
        }
        return nil
    }

    /// Detect the Tailscale network interface IP (100.x.x.x CGNAT range).
    nonisolated static func detectTailscaleIdentity() -> TailscaleIdentity? {
        if let cliURL = tailscaleCLIExecutableURL(),
           let statusData = captureProcessOutput(
                executableURL: cliURL,
                arguments: ["status", "--json"]
           ),
           let identity = parseTailscaleIdentity(fromStatusData: statusData) {
            return identity
        }

        if let ipAddress = detectTailscaleIPFromInterfaces() {
            return TailscaleIdentity(dnsName: nil, ipAddress: ipAddress)
        }

        return nil
    }

    nonisolated static func parseTailscaleIdentity(fromStatusData data: Data) -> TailscaleIdentity? {
        guard let root = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] else {
            return nil
        }

        let selfNode = root["Self"] as? [String: Any]
        let dnsName = normalizeTailscaleDNSName(selfNode?["DNSName"] as? String)
        let selfIPs = selfNode?["TailscaleIPs"] as? [String] ?? []
        let rootIPs = root["TailscaleIPs"] as? [String] ?? []
        let ipAddress = (selfIPs + rootIPs).first(where: isTailscaleIP)

        if dnsName == nil, ipAddress == nil {
            return nil
        }

        return TailscaleIdentity(dnsName: dnsName, ipAddress: ipAddress)
    }

    nonisolated static func isTailscaleIP(_ input: String) -> Bool {
        let parts = input.split(separator: ".")
        guard parts.count == 4,
              let first = Int(parts[0]),
              let second = Int(parts[1]),
              (0...255).contains(first),
              (0...255).contains(second),
              first == 100,
              (64...127).contains(second) else {
            return false
        }
        return parts[2...3].allSatisfy { octet in
            guard let value = Int(octet) else { return false }
            return (0...255).contains(value)
        }
    }

    private nonisolated static func detectTailscaleIPFromInterfaces() -> String? {
        var ifaddr: UnsafeMutablePointer<ifaddrs>?
        guard getifaddrs(&ifaddr) == 0, let firstAddr = ifaddr else { return nil }
        defer { freeifaddrs(ifaddr) }

        var tailscaleIP: String?
        var current: UnsafeMutablePointer<ifaddrs>? = firstAddr
        while let addr = current {
            let interface = addr.pointee
            let family = interface.ifa_addr.pointee.sa_family
            if family == UInt8(AF_INET) {  // IPv4
                var hostname = [CChar](repeating: 0, count: Int(NI_MAXHOST))
                getnameinfo(
                    interface.ifa_addr, socklen_t(interface.ifa_addr.pointee.sa_len),
                    &hostname, socklen_t(hostname.count),
                    nil, 0, NI_NUMERICHOST
                )
                let ip = hostname.withUnsafeBufferPointer { buffer in
                    let scalars = buffer.prefix { $0 != 0 }.map { UInt8(bitPattern: $0) }
                    return String(decoding: scalars, as: UTF8.self)
                }
                if isTailscaleIP(ip) {
                    tailscaleIP = ip
                    break
                }
            }
            current = interface.ifa_next
        }
        return tailscaleIP
    }

    private nonisolated static func normalizeTailscaleDNSName(_ value: String?) -> String? {
        guard let trimmed = value?.trimmingCharacters(in: .whitespacesAndNewlines),
              !trimmed.isEmpty else {
            return nil
        }
        let normalized = trimmed.hasSuffix(".") ? String(trimmed.dropLast()) : trimmed
        return normalized.hasSuffix(".ts.net") ? normalized : nil
    }

    private nonisolated static func tailscaleCLIExecutableURL(
        fileManager: FileManager = .default
    ) -> URL? {
        let candidates = [
            "/Applications/Tailscale.app/Contents/MacOS/Tailscale",
            "/opt/homebrew/bin/tailscale",
            "/usr/local/bin/tailscale",
            "/usr/bin/tailscale",
        ]
        for path in candidates where fileManager.isExecutableFile(atPath: path) {
            return URL(fileURLWithPath: path)
        }
        return nil
    }

    private nonisolated static func captureProcessOutput(
        executableURL: URL,
        arguments: [String]
    ) -> Data? {
        let process = Process()
        process.executableURL = executableURL
        process.arguments = arguments
        process.environment = ProcessInfo.processInfo.environment

        let stdoutPipe = Pipe()
        let stderrPipe = Pipe()
        process.standardOutput = stdoutPipe
        process.standardError = stderrPipe

        do {
            try process.run()
        } catch {
            return nil
        }

        process.waitUntilExit()
        guard process.terminationStatus == 0 else {
            return nil
        }
        return stdoutPipe.fileHandleForReading.readDataToEndOfFile()
    }

    /// Whether the server ready callback has been fired
    private var serverReadyNotified: Bool = false
    
    /// State change callback
    var onStateChange: (@MainActor @Sendable (State) -> Void)?
    
    /// Server ready callback
    var onServerReady: (@MainActor @Sendable (BackendReadyContext) -> Void)?
    
    /// Log output callback
    var onLogOutput: (@MainActor @Sendable (String) -> Void)?
    
    /// Error output callback
    var onErrorOutput: (@MainActor @Sendable (String) -> Void)?
    
    // MARK: - Initialization
    
    nonisolated init() {}
    
    deinit {
        processRef?.requestTermination()
    }
    
    // MARK: - Public Methods
    
    /// Starts the Python backend server
    /// - Parameter customEndpointURL: Optional custom WebSocket endpoint URL.
    func start(customEndpointURL: String? = nil) async throws {
        guard state == .notStarted || state == .terminated || state.isFailed else {
            return  // Already running or starting
        }
        
        updateState(.starting)
        serverReadyNotified = false
        let generatedAuthToken = try Self.loadOrCreatePairingAuthToken()

        // Find the Python executable and project path
        let (pythonPath, projectPath) = try await findPythonEnvironment()
        
        // Set up arguments
        let endpoint = try Self.resolveEndpointURL(customEndpointURL)
        let host = endpoint.host ?? "127.0.0.1"
        let port = endpoint.port ?? 8765
        let args = [
            "-m", "agent_host.main",
            "--server",
            "--host", host,
            "--port", String(port),
        ]
        let finalArgs = args  // Capture as let for Sendable
        
        // Create process reference with callbacks
        let ref = ProcessRef()
        self.processRef = ref
        
        // Store callbacks in ref for thread-safe access
        ref.onTermination = { [weak self, weak ref] status in
            Task { @MainActor in
                guard let self, let ref else { return }
                self.handleProcessTermination(for: ref, status: status)
            }
        }
        
        ref.onOutput = { [weak self, weak ref] string in
            Task { @MainActor in
                guard let self, let ref else { return }
                self.onLogOutput?(string)
                
                // Check for server ready message
                if self.processRef === ref, string.contains("IPC Server started") {
                    if let endpointURL = self.endpointURL {
                        do {
                            try self.notifyServerReady(endpointURL)
                        } catch {
                            self.failLaunch(for: ref, message: error.localizedDescription)
                        }
                    }
                }
            }
        }
        
        ref.onError = { [weak self] string in
            Task { @MainActor in
                guard let self = self else { return }
                self.onErrorOutput?(string)
            }
        }
        
        // Resolve the API key: prefer UserDefaults (set from the UI), then env vars
        let storedAPIKey = UserDefaults.standard.string(forKey: "gemini_api_key")?
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let envGoogleKey = ProcessInfo.processInfo.environment["GOOGLE_API_KEY"]?
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let envGeminiKey = ProcessInfo.processInfo.environment["GEMINI_API_KEY"]?
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let apiKey = [storedAPIKey, envGoogleKey, envGeminiKey]
            .compactMap { $0 }
            .first(where: { !$0.isEmpty }) ?? ""

        // Start the process
        var extraEnv: [String: String] = [
            "AI_AGENT_IPC_AUTH_TOKEN": generatedAuthToken,
            "AI_AGENT_ENV": ProcessInfo.processInfo.environment["AI_AGENT_ENV"] ?? "production",
            "AI_AGENT_IPC_HOST": "0.0.0.0",
        ]
        if !apiKey.isEmpty {
            extraEnv["GOOGLE_API_KEY"] = apiKey
        }
        if Self.shouldEnableTLS(for: endpoint) {
            let tlsConfig = try await Self.loadPairingTLSConfig(projectPath: projectPath)
            extraEnv["AI_AGENT_TLS_CERT"] = tlsConfig.certPath
            extraEnv["AI_AGENT_TLS_KEY"] = tlsConfig.keyPath
            extraEnv["AI_AGENT_REQUIRE_TLS"] = "1"
        }

        let result = await ref.startProcess(
            pythonPath: pythonPath,
            projectPath: projectPath,
            arguments: finalArgs,
            extraEnvironment: extraEnv
        )
        
        switch result {
        case .success(let pid):
            updateState(.running(pid: pid))
            
            self.endpointURL = endpoint.absoluteString
            self.authToken = generatedAuthToken
            
            // Wait for the WebSocket server to become ready.
            do {
                try await waitForServerReady(timeout: 10.0)
            } catch {
                failLaunch(for: ref, message: error.localizedDescription)
                throw error
            }
            
        case .failure(let error):
            if processRef === ref {
                processRef = nil
            }
            updateState(.failed("Failed to start backend: \(error.localizedDescription)"))
            throw BackendError.launchFailed(error.localizedDescription)
        }
    }
    
    /// Terminates the backend server
    func terminate() {
        let ref = processRef
        processRef = nil
        endpointURL = nil
        authToken = nil
        serverReadyNotified = false
        updateState(.terminated)
        ref?.requestTermination()
    }
    
    /// Checks if the backend is running
    var isRunning: Bool {
        if case .running = state {
            return processRef?.isRunning ?? false
        }
        return false
    }
    
    // MARK: - Private Methods

    private func updateState(_ newState: State) {
        state = newState
        onStateChange?(newState)
    }

    private struct PairingTLSConfig: Sendable {
        let certPath: String
        let keyPath: String
    }

    private nonisolated static func shouldEnableTLS(for endpoint: URL) -> Bool {
        if endpoint.scheme?.lowercased() == "wss" {
            return true
        }
        guard let host = endpoint.host?.lowercased() else {
            return false
        }
        return !["127.0.0.1", "localhost"].contains(host)
    }

    private nonisolated static func pairingRuntimeDirectory(fileManager: FileManager = .default) throws -> URL {
        let base = try fileManager.url(
            for: .applicationSupportDirectory,
            in: .userDomainMask,
            appropriateFor: nil,
            create: true
        )
        let runtimeDir = base.appendingPathComponent("AIAgent", isDirectory: true)
        try fileManager.createDirectory(
            at: runtimeDir,
            withIntermediateDirectories: true,
            attributes: nil
        )
        try? fileManager.setAttributes([.posixPermissions: 0o700], ofItemAtPath: runtimeDir.path)
        return runtimeDir
    }

    private nonisolated static func loadOrCreatePairingAuthToken(
        fileManager: FileManager = .default
    ) throws -> String {
        let runtimeDir = try pairingRuntimeDirectory(fileManager: fileManager)
        let tokenURL = runtimeDir.appendingPathComponent("pairing-auth-token", isDirectory: false)

        if let existing = try? String(contentsOf: tokenURL, encoding: .utf8)
            .trimmingCharacters(in: .whitespacesAndNewlines),
           !existing.isEmpty {
            return existing
        }

        let token = UUID().uuidString
        try token.write(to: tokenURL, atomically: true, encoding: .utf8)
        try? fileManager.setAttributes([.posixPermissions: 0o600], ofItemAtPath: tokenURL.path)
        return token
    }

    private nonisolated static func loadPairingTLSConfig(projectPath: String) async throws -> PairingTLSConfig {
        let scriptURL = URL(fileURLWithPath: projectPath)
            .appendingPathComponent("scripts/ensure-backend-tls.sh")
        let result = try await ChildProcessCapture.run(
            executableURL: URL(fileURLWithPath: "/bin/bash"),
            arguments: [scriptURL.path],
            currentDirectoryURL: URL(fileURLWithPath: projectPath),
            environment: ProcessInfo.processInfo.environment
        )

        let stderrText = result.stderr.trimmingCharacters(in: .whitespacesAndNewlines)
        if result.terminationStatus != 0 {
            let reason = stderrText.isEmpty ? "TLS provisioning script failed." : stderrText
            throw BackendError.launchFailed(reason)
        }

        var certPath: String?
        var keyPath: String?
        for rawLine in result.stdout.split(whereSeparator: \.isNewline) {
            let line = String(rawLine)
            let parts = line.split(separator: "=", maxSplits: 1).map(String.init)
            guard parts.count == 2 else { continue }
            switch parts[0] {
            case "TLS_CERT_PATH":
                certPath = parts[1]
            case "TLS_KEY_PATH":
                keyPath = parts[1]
            default:
                continue
            }
        }

        guard let certPath, !certPath.isEmpty, let keyPath, !keyPath.isEmpty else {
            throw BackendError.launchFailed("TLS provisioning script did not return cert/key paths.")
        }
        return PairingTLSConfig(certPath: certPath, keyPath: keyPath)
    }
    
    /// Finds the Python environment and project path
    private func handleProcessTermination(for ref: ProcessRef, status: Int32) {
        guard processRef === ref else { return }
        processRef = nil
        endpointURL = nil
        authToken = nil
        serverReadyNotified = false
        if status == 0 {
            updateState(.terminated)
        } else {
            updateState(.failed("Backend exited with code \(status)"))
        }
    }

    private func failLaunch(for ref: ProcessRef, message: String) {
        guard processRef === ref else { return }
        processRef = nil
        endpointURL = nil
        authToken = nil
        serverReadyNotified = false
        ref.requestTermination()
        updateState(.failed(message))
    }

    private nonisolated func findPythonEnvironment() async throws -> (pythonPath: String, projectPath: String) {
        let fileManager = FileManager.default

        if let configuredRoot = ProcessInfo.processInfo.environment["AI_AGENT_PROJECT_ROOT"]?
            .trimmingCharacters(in: .whitespacesAndNewlines),
           !configuredRoot.isEmpty {
            let rootURL = URL(fileURLWithPath: configuredRoot)
            let pyprojectPath = rootURL.appendingPathComponent("pyproject.toml")
            guard fileManager.fileExists(atPath: pyprojectPath.path) else {
                throw BackendError.projectNotFound
            }
            let pythonPath = try await resolvePythonPath(root: rootURL, fileManager: fileManager)
            return (pythonPath, rootURL.path)
        }
        
        // Get the directory containing the app bundle or executable
        let executableURL = Bundle.main.executableURL ?? URL(fileURLWithPath: ProcessInfo.processInfo.arguments[0])
        var searchPath = executableURL.deletingLastPathComponent()
        
        // Walk up to find the project root (where pyproject.toml is)
        var projectRoot: URL?
        var attempts = 0
        while attempts < 10 {
            let pyprojectPath = searchPath.appendingPathComponent("pyproject.toml")
            if fileManager.fileExists(atPath: pyprojectPath.path) {
                projectRoot = searchPath
                break
            }
            searchPath = searchPath.deletingLastPathComponent()
            attempts += 1
        }
        
        guard let root = projectRoot else {
            throw BackendError.projectNotFound
        }

        let pythonPath = try await resolvePythonPath(root: root, fileManager: fileManager)
        
        return (pythonPath, root.path)
    }

    private nonisolated func resolvePythonPath(
        root: URL,
        fileManager: FileManager
    ) async throws -> String {
        let venvPython = root.appendingPathComponent(".venv/bin/python").path
        let venvPython3 = root.appendingPathComponent(".venv/bin/python3").path
        if fileManager.fileExists(atPath: venvPython) {
            return venvPython
        }
        if fileManager.fileExists(atPath: venvPython3) {
            return venvPython3
        }
        do {
            if let poetry = try await findPoetryPython(in: root.path) {
                return poetry
            }
            throw BackendError.pythonNotFound
        } catch {
            throw BackendError.launchFailed("Poetry python lookup failed: \(error.localizedDescription)")
        }
    }

    /// Finds Poetry-managed Python environment
    private nonisolated func findPoetryPython(in projectPath: String) async throws -> String? {
        let result = try await ChildProcessCapture.run(
            executableURL: URL(fileURLWithPath: "/usr/bin/env"),
            arguments: ["poetry", "env", "info", "-p"],
            currentDirectoryURL: URL(fileURLWithPath: projectPath),
            environment: ProcessInfo.processInfo.environment
        )

        let stderrText = result.stderr.trimmingCharacters(in: .whitespacesAndNewlines)
        if result.terminationStatus != 0 {
            let reason = stderrText.isEmpty ? "unknown poetry error" : stderrText
            throw BackendError.launchFailed(reason)
        }

        let envPath = result.stdout.trimmingCharacters(in: .whitespacesAndNewlines)
        if !envPath.isEmpty {
            return envPath + "/bin/python"
        }
        
        return nil
    }
    
    private func waitForServerReady(timeout: TimeInterval) async throws {
        let startTime = Date()
        
        while Date().timeIntervalSince(startTime) < timeout {
            if serverReadyNotified {
                return
            }
            try await Task.sleep(nanoseconds: 100_000_000)  // 100ms
        }
        
        throw BackendError.socketTimeout
    }

    private func notifyServerReady(_ endpointURL: String) throws {
        guard !serverReadyNotified else { return }
        guard let authToken, !authToken.isEmpty else {
            throw BackendError.launchFailed("Missing backend auth token during startup")
        }
        serverReadyNotified = true
        onServerReady?(.init(endpointURL: endpointURL, authToken: authToken))
    }

    private static func resolveEndpointURL(_ rawURL: String?) throws -> URL {
        if let rawURL, !rawURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            guard let endpoint = URL(string: rawURL),
                  let scheme = endpoint.scheme?.lowercased(),
                  ["ws", "wss"].contains(scheme),
                  endpoint.host != nil else {
                throw BackendError.launchFailed("Invalid backend endpoint URL: \(rawURL)")
            }
            return endpoint
        }

        let port = findAvailableLoopbackPort()
        return URL(string: "ws://127.0.0.1:\(port)")!
    }

    private static func findAvailableLoopbackPort() -> Int {
        let socketFD = Darwin.socket(AF_INET, SOCK_STREAM, 0)
        guard socketFD >= 0 else { return 8765 }
        defer { Darwin.close(socketFD) }

        var value: Int32 = 1
        _ = withUnsafePointer(to: &value) {
            setsockopt(socketFD, SOL_SOCKET, SO_REUSEADDR, $0, socklen_t(MemoryLayout<Int32>.size))
        }

        var address = sockaddr_in()
        address.sin_len = UInt8(MemoryLayout<sockaddr_in>.stride)
        address.sin_family = sa_family_t(AF_INET)
        address.sin_port = in_port_t(0).bigEndian
        address.sin_addr = in_addr(s_addr: inet_addr("127.0.0.1"))

        let bindResult = withUnsafePointer(to: &address) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                Darwin.bind(socketFD, $0, socklen_t(MemoryLayout<sockaddr_in>.stride))
            }
        }
        guard bindResult == 0 else { return 8765 }

        var boundAddress = sockaddr_in()
        var length = socklen_t(MemoryLayout<sockaddr_in>.stride)
        let nameResult = withUnsafeMutablePointer(to: &boundAddress) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                getsockname(socketFD, $0, &length)
            }
        }
        guard nameResult == 0 else { return 8765 }
        return Int(UInt16(bigEndian: boundAddress.sin_port))
    }
}

// MARK: - Process Reference Wrapper

/// Thread-safe wrapper for Process to handle cross-isolation access
final class ProcessRef: @unchecked Sendable {
    var process: Process?
    var outputPipe: Pipe?
    var errorPipe: Pipe?
    
    private let lock = NSLock()
    
    /// Callbacks (stored here for thread-safe access)
    var onTermination: (@Sendable (Int32) -> Void)?
    var onOutput: (@Sendable (String) -> Void)?
    var onError: (@Sendable (String) -> Void)?
    
    var isRunning: Bool {
        lock.lock()
        defer { lock.unlock() }
        return process?.isRunning ?? false
    }
    
    /// Starts the process on a background thread
    func startProcess(
        pythonPath: String,
        projectPath: String,
        arguments: [String],
        extraEnvironment: [String: String]
    ) async -> Result<Int32, Error> {
        await withCheckedContinuation { continuation in
            DispatchQueue.global(qos: .userInitiated).async { [self] in
                let process = Process()
                process.executableURL = URL(fileURLWithPath: pythonPath)
                process.arguments = arguments
                process.currentDirectoryURL = URL(fileURLWithPath: projectPath)
                
                // Set up environment (inherit current environment)
                var env = ProcessInfo.processInfo.environment
                env["PYTHONUNBUFFERED"] = "1"  // Ensure unbuffered output
                for (key, value) in extraEnvironment {
                    env[key] = value
                }
                process.environment = env
                
                // Set up pipes for I/O
                let outputPipe = Pipe()
                let errorPipe = Pipe()
                process.standardOutput = outputPipe
                process.standardError = errorPipe
                
                lock.lock()
                self.process = process
                self.outputPipe = outputPipe
                self.errorPipe = errorPipe
                lock.unlock()
                
                // Handle termination - capture callback
                let terminationCallback = self.onTermination
                process.terminationHandler = { proc in
                    terminationCallback?(proc.terminationStatus)
                }
                
                // Monitor output - capture callback
                let outputCallback = self.onOutput
                outputPipe.fileHandleForReading.readabilityHandler = { handle in
                    let data = handle.availableData
                    guard !data.isEmpty else {
                        handle.readabilityHandler = nil
                        return
                    }
                    guard let string = String(data: data, encoding: .utf8) else {
                        return
                    }
                    outputCallback?(string)
                }
                
                // Monitor error - capture callback
                let errorCallback = self.onError
                errorPipe.fileHandleForReading.readabilityHandler = { handle in
                    let data = handle.availableData
                    guard !data.isEmpty else {
                        handle.readabilityHandler = nil
                        return
                    }
                    guard let string = String(data: data, encoding: .utf8) else {
                        return
                    }
                    errorCallback?(string)
                }
                
                do {
                    try process.run()
                    let pid = process.processIdentifier
                    continuation.resume(returning: .success(pid))
                } catch {
                    outputPipe.fileHandleForReading.readabilityHandler = nil
                    errorPipe.fileHandleForReading.readabilityHandler = nil
                    process.terminationHandler = nil
                    outputPipe.fileHandleForReading.closeFile()
                    outputPipe.fileHandleForWriting.closeFile()
                    errorPipe.fileHandleForReading.closeFile()
                    errorPipe.fileHandleForWriting.closeFile()
                    lock.lock()
                    if self.process === process {
                        self.process = nil
                        self.outputPipe = nil
                        self.errorPipe = nil
                    }
                    lock.unlock()
                    continuation.resume(returning: .failure(error))
                }
            }
        }
    }
    
    func requestTermination(gracePeriod: TimeInterval = 2.0) {
        let snapshot: (process: Process, outputPipe: Pipe?, errorPipe: Pipe?)
        lock.lock()
        guard let process else {
            lock.unlock()
            return
        }
        process.terminationHandler = nil
        outputPipe?.fileHandleForReading.readabilityHandler = nil
        errorPipe?.fileHandleForReading.readabilityHandler = nil
        snapshot = (process, outputPipe, errorPipe)
        self.process = nil
        self.outputPipe = nil
        self.errorPipe = nil
        lock.unlock()

        DispatchQueue.global(qos: .utility).async {
            defer {
                snapshot.outputPipe?.fileHandleForReading.closeFile()
                snapshot.outputPipe?.fileHandleForWriting.closeFile()
                snapshot.errorPipe?.fileHandleForReading.closeFile()
                snapshot.errorPipe?.fileHandleForWriting.closeFile()
            }

            guard snapshot.process.isRunning else { return }

            snapshot.process.terminate()
            let deadline = Date().addingTimeInterval(gracePeriod)
            while snapshot.process.isRunning && Date() < deadline {
                Thread.sleep(forTimeInterval: 0.05)
            }

            if snapshot.process.isRunning {
                Darwin.kill(snapshot.process.processIdentifier, SIGKILL)
                let killDeadline = Date().addingTimeInterval(1.0)
                while snapshot.process.isRunning && Date() < killDeadline {
                    Thread.sleep(forTimeInterval: 0.02)
                }
            }
        }
    }
}

// MARK: - Errors

enum BackendError: Error, LocalizedError, Sendable {
    case projectNotFound
    case pythonNotFound
    case launchFailed(String)
    case socketTimeout
    
    var errorDescription: String? {
        switch self {
        case .projectNotFound:
            return "Could not find project root (pyproject.toml)"
        case .pythonNotFound:
            return "Could not find Python interpreter"
        case .launchFailed(let reason):
            return "Failed to start backend: \(reason)"
        case .socketTimeout:
            return "Backend server did not start in time"
        }
    }
}

// MARK: - State Extensions

extension BackendLauncher.State {
    var isFailed: Bool {
        if case .failed = self {
            return true
        }
        return false
    }
    
    var errorMessage: String? {
        if case .failed(let message) = self {
            return message
        }
        return nil
    }
}
#endif
