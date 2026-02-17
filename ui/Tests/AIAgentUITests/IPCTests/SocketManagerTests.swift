import Foundation
import Testing
@testable import AIAgentApp

@Test
@MainActor
func socketManagerFallsBackAcrossCandidatesUntilConnected() async {
    let manager = SocketManager()
    let candidates = ["/tmp/ai-agent-old.sock", "/tmp/ai-agent-new.sock", "/tmp/ai-agent-final.sock"]
    var attempts: [String] = []

    do {
        try await manager.connectUsingCandidates(candidates) { path in
            attempts.append(path)
            if path != "/tmp/ai-agent-new.sock" {
                throw SocketError.connectionFailed("simulated failure")
            }
        }
    } catch {
        Issue.record("Expected fallback to succeed, got error: \(error)")
    }

    #expect(attempts == ["/tmp/ai-agent-old.sock", "/tmp/ai-agent-new.sock"])
}

@Test
@MainActor
func socketManagerStopsStateMachineAfterFirstSuccessfulCandidate() async {
    let manager = SocketManager()
    let candidates = ["/tmp/ai-agent-first.sock", "/tmp/ai-agent-second.sock"]
    var attempts: [String] = []

    do {
        try await manager.connectUsingCandidates(candidates) { path in
            attempts.append(path)
            if path == "/tmp/ai-agent-first.sock" {
                return
            }
            throw SocketError.connectionFailed("should not be attempted")
        }
    } catch {
        Issue.record("Expected first candidate success, got \(error)")
    }

    #expect(attempts == ["/tmp/ai-agent-first.sock"])
}

@Test
@MainActor
func socketManagerReportsFailureAfterAllCandidatesFail() async {
    let manager = SocketManager()
    let candidates = ["/tmp/ai-agent-a.sock", "/tmp/ai-agent-b.sock"]
    var attempts: [String] = []

    do {
        try await manager.connectUsingCandidates(candidates) { path in
            attempts.append(path)
            throw SocketError.connectionTimeout
        }
        Issue.record("Expected connection failure after exhausting candidates.")
    } catch let error as SocketError {
        if case .connectionFailed(let reason) = error {
            #expect(reason.contains("2 attempted"))
            #expect(reason.contains("/tmp/ai-agent-a.sock"))
            #expect(reason.contains("/tmp/ai-agent-b.sock"))
        } else {
            Issue.record("Expected connectionFailed error, got \(error)")
        }
    } catch {
        Issue.record("Expected SocketError, got \(error)")
    }

    #expect(attempts == candidates)
}

@Test
@MainActor
func socketManagerRejectsEmptyCandidateList() async {
    let manager = SocketManager()

    do {
        try await manager.connectUsingCandidates([])
        Issue.record("Expected noAvailableSocket for empty candidates.")
    } catch let error as SocketError {
        if case .noAvailableSocket = error {
            #expect(true)
        } else {
            Issue.record("Expected noAvailableSocket, got \(error)")
        }
    } catch {
        Issue.record("Expected SocketError, got \(error)")
    }
}

@Test
@MainActor
func socketManagerAllowsRetryAfterFailedDirectConnect() async {
    let manager = SocketManager()
    let missingPath = "/tmp/ai-agent-missing-\(UUID().uuidString).sock"
    defer { manager.disconnect() }

    do {
        try await manager.connect(toPath: missingPath)
        Issue.record("Expected first connect attempt to fail for missing socket.")
    } catch {
        // Expected
    }

    do {
        try await manager.connect(toPath: missingPath)
        Issue.record("Expected second connect attempt to fail for missing socket.")
    } catch let error as SocketError {
        if case .alreadyConnecting = error {
            Issue.record("Retry path should not be blocked by stale connecting state.")
        }
    } catch {
        Issue.record("Expected SocketError, got \(error)")
    }
}

@Test
@MainActor
func socketManagerDisconnectClearsDispatcherAccumulators() {
    let manager = SocketManager()
    var updates: [(requestId: String, text: String, done: Bool)] = []

    manager.dispatcher.onStreamingUpdate = { requestId, text, done in
        updates.append((requestId, text, done))
    }

    manager.dispatcher.dispatch(
        .stream(
            StreamResponse(
                jsonrpc: "2.0",
                id: "req-clear",
                type: "stream",
                delta: "hello",
                done: false
            )
        )
    )
    #expect(updates.last?.text == "hello")

    manager.disconnect()

    manager.dispatcher.dispatch(
        .stream(
            StreamResponse(
                jsonrpc: "2.0",
                id: "req-clear",
                type: "stream",
                delta: "x",
                done: false
            )
        )
    )
    #expect(updates.last?.text == "x")
}
