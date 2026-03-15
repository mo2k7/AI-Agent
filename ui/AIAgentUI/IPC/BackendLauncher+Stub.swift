#if !os(macOS)
import Foundation

struct BackendReadyContext: Sendable {
    let endpointURL: String
    let authToken: String
}

@MainActor
final class BackendLauncher {
    enum State: Equatable, Sendable {
        case notStarted
        case starting
        case running(pid: Int32)
        case failed(String)
        case terminated
    }

    private(set) var state: State = .notStarted
    var onStateChange: (@MainActor @Sendable (State) -> Void)?
    var onServerReady: (@MainActor @Sendable (BackendReadyContext) -> Void)?
    var onLogOutput: (@MainActor @Sendable (String) -> Void)?
    var onErrorOutput: (@MainActor @Sendable (String) -> Void)?

    nonisolated init() {}

    func start(customEndpointURL: String? = nil) async throws {
        let message = "Local backend launch is unavailable on this platform. Configure AI_AGENT_BACKEND_URL."
        state = .failed(message)
        onStateChange?(state)
        throw NSError(domain: "AIAgentUI.BackendLauncher", code: -1, userInfo: [NSLocalizedDescriptionKey: message])
    }

    func terminate() {
        state = .terminated
        onStateChange?(state)
    }

    var isRunning: Bool { false }
}

extension BackendLauncher.State {
    var isFailed: Bool {
        if case .failed = self { return true }
        return false
    }

    var errorMessage: String? {
        if case .failed(let message) = self { return message }
        return nil
    }
}
#endif
