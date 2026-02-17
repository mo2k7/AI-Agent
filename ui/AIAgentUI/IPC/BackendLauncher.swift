//
//  BackendLauncher.swift
//  AIAgentUI
//
//  Created for Personal macOS AI Agent
//  Status: Active - Python backend process management
//

import Foundation

struct BackendReadyContext: Sendable {
    let socketPath: String
    let authToken: String
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
    
    /// Socket path for the backend
    private(set) var socketPath: String?

    /// Per-process IPC auth token required by backend auth.hello.
    private(set) var authToken: String?

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
        // Cleanup is synchronous and handles Process termination
        processRef?.terminateSync()
    }
    
    // MARK: - Public Methods
    
    /// Starts the Python backend server
    /// - Parameter customSocketPath: Optional custom socket path
    func start(customSocketPath: String? = nil) async throws {
        guard state == .notStarted || state == .terminated || state.isFailed else {
            return  // Already running or starting
        }
        
        updateState(.starting)
        serverReadyNotified = false
        let generatedAuthToken = UUID().uuidString

        // Find the Python executable and project path
        let (pythonPath, projectPath) = try findPythonEnvironment()
        
        // Set up arguments
        var args = ["-m", "agent_host.main", "--server"]
        if let socketPath = customSocketPath {
            args.append("--socket-path")
            args.append(socketPath)
        }
        let finalArgs = args  // Capture as let for Sendable
        
        // Create process reference with callbacks
        let ref = ProcessRef()
        self.processRef = ref
        
        // Store callbacks in ref for thread-safe access
        ref.onTermination = { [weak self] status in
            Task { @MainActor in
                guard let self = self else { return }
                if status == 0 {
                    self.updateState(.terminated)
                } else {
                    self.updateState(.failed("Backend exited with code \(status)"))
                }
            }
        }
        
        ref.onOutput = { [weak self] string in
            Task { @MainActor in
                guard let self = self else { return }
                self.onLogOutput?(string)
                
                // Check for server ready message
                if string.contains("IPC Server started") {
                    if let socketPath = self.socketPath {
                        do {
                            try self.notifyServerReady(socketPath)
                        } catch {
                            self.updateState(.failed(error.localizedDescription))
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
        
        // Start the process
        let result = await ref.startProcess(
            pythonPath: pythonPath,
            projectPath: projectPath,
            arguments: finalArgs,
            extraEnvironment: [
                "AI_AGENT_IPC_AUTH_TOKEN": generatedAuthToken,
                "AI_AGENT_ENV": ProcessInfo.processInfo.environment["AI_AGENT_ENV"] ?? "production",
            ]
        )
        
        switch result {
        case .success(let pid):
            updateState(.running(pid: pid))
            
            // Calculate socket path
            let socketPath = customSocketPath ?? "/tmp/ai-agent-\(pid).sock"
            self.socketPath = socketPath
            self.authToken = generatedAuthToken
            
            // Wait for socket to be ready
            do {
                try await waitForSocket(path: socketPath, timeout: 10.0)
            } catch {
                processRef?.terminateSync()
                processRef = nil
                updateState(.failed(error.localizedDescription))
                throw error
            }
            
        case .failure(let error):
            updateState(.failed("Failed to start backend: \(error.localizedDescription)"))
            throw BackendError.launchFailed(error.localizedDescription)
        }
    }
    
    /// Terminates the backend server
    func terminate() {
        processRef?.terminateSync()
        processRef = nil
        socketPath = nil
        authToken = nil
        updateState(.terminated)
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
    
    /// Finds the Python environment and project path
    private nonisolated func findPythonEnvironment() throws -> (pythonPath: String, projectPath: String) {
        let fileManager = FileManager.default

        if let configuredRoot = ProcessInfo.processInfo.environment["AI_AGENT_PROJECT_ROOT"]?
            .trimmingCharacters(in: .whitespacesAndNewlines),
           !configuredRoot.isEmpty {
            let rootURL = URL(fileURLWithPath: configuredRoot)
            let pyprojectPath = rootURL.appendingPathComponent("pyproject.toml")
            guard fileManager.fileExists(atPath: pyprojectPath.path) else {
                throw BackendError.projectNotFound
            }
            let pythonPath = try resolvePythonPath(root: rootURL, fileManager: fileManager)
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

        let pythonPath = try resolvePythonPath(root: root, fileManager: fileManager)
        
        return (pythonPath, root.path)
    }

    private nonisolated func resolvePythonPath(
        root: URL,
        fileManager: FileManager
    ) throws -> String {
        let venvPython = root.appendingPathComponent(".venv/bin/python").path
        let venvPython3 = root.appendingPathComponent(".venv/bin/python3").path
        if fileManager.fileExists(atPath: venvPython) {
            return venvPython
        }
        if fileManager.fileExists(atPath: venvPython3) {
            return venvPython3
        }
        do {
            if let poetry = try findPoetryPython(in: root.path) {
                return poetry
            }
            throw BackendError.pythonNotFound
        } catch {
            throw BackendError.launchFailed("Poetry python lookup failed: \(error.localizedDescription)")
        }
    }
    
    /// Finds Poetry-managed Python environment
    private nonisolated func findPoetryPython(in projectPath: String) throws -> String? {
        let task = Process()
        task.executableURL = URL(fileURLWithPath: "/usr/bin/env")
        task.arguments = ["poetry", "env", "info", "-p"]
        task.currentDirectoryURL = URL(fileURLWithPath: projectPath)
        
        let pipe = Pipe()
        task.standardOutput = pipe
        let errorPipe = Pipe()
        task.standardError = errorPipe
        
        try task.run()
        task.waitUntilExit()

        let stderrData = errorPipe.fileHandleForReading.readDataToEndOfFile()
        let stderrText = String(data: stderrData, encoding: .utf8)?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if task.terminationStatus != 0 {
            let reason = stderrText.isEmpty ? "unknown poetry error" : stderrText
            throw BackendError.launchFailed(reason)
        }

        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        if let envPath = String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines),
           !envPath.isEmpty {
            return envPath + "/bin/python"
        }
        
        return nil
    }
    
    /// Waits for a valid Unix socket file to appear
    private func waitForSocket(path: String, timeout: TimeInterval) async throws {
        let startTime = Date()
        
        while Date().timeIntervalSince(startTime) < timeout {
            if Self.isSocketPath(path) {
                // Additional delay to ensure server is listening
                try await Task.sleep(nanoseconds: 200_000_000)  // 200ms
                try notifyServerReady(path)
                return
            }
            try await Task.sleep(nanoseconds: 100_000_000)  // 100ms
        }
        
        throw BackendError.socketTimeout
    }

    private static func isSocketPath(_ path: String) -> Bool {
        let fileManager = FileManager.default
        guard let attributes = try? fileManager.attributesOfItem(atPath: path) else {
            return false
        }
        guard let fileType = attributes[.type] as? FileAttributeType else {
            return false
        }
        return fileType == .typeSocket
    }

    private func notifyServerReady(_ path: String) throws {
        guard !serverReadyNotified else { return }
        guard let authToken, !authToken.isEmpty else {
            throw BackendError.launchFailed("Missing backend auth token during startup")
        }
        serverReadyNotified = true
        onServerReady?(.init(socketPath: path, authToken: authToken))
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
                    guard !data.isEmpty,
                          let string = String(data: data, encoding: .utf8) else {
                        return
                    }
                    outputCallback?(string)
                }
                
                // Monitor error - capture callback
                let errorCallback = self.onError
                errorPipe.fileHandleForReading.readabilityHandler = { handle in
                    let data = handle.availableData
                    guard !data.isEmpty,
                          let string = String(data: data, encoding: .utf8) else {
                        return
                    }
                    errorCallback?(string)
                }
                
                do {
                    try process.run()
                    let pid = process.processIdentifier
                    continuation.resume(returning: .success(pid))
                } catch {
                    continuation.resume(returning: .failure(error))
                }
            }
        }
    }
    
    func terminateSync() {
        lock.lock()
        defer { lock.unlock() }
        
        guard let process = process, process.isRunning else {
            return
        }
        
        // Clean up handlers
        outputPipe?.fileHandleForReading.readabilityHandler = nil
        errorPipe?.fileHandleForReading.readabilityHandler = nil
        
        // Send SIGTERM first for graceful shutdown
        process.terminate()
        
        // Wait briefly for graceful shutdown
        let deadline = Date().addingTimeInterval(2)
        while process.isRunning && Date() < deadline {
            Thread.sleep(forTimeInterval: 0.1)
        }
        
        // Force kill if still running
        if process.isRunning {
            process.interrupt()
        }
        
        self.process = nil
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
