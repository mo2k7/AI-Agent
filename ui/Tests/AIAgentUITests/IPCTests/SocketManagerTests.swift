import Foundation
import Testing
@testable import AIAgentApp

@Test
func tailscaleEndpointRecognizesMagicDNSAndCGNATHosts() {
    #expect(TailscaleEndpoint.isTailscaleHost("100.85.139.105"))
    #expect(TailscaleEndpoint.isTailscaleHost("muhammads-macbook-pro.tail8a4dee.ts.net"))
    #expect(TailscaleEndpoint.isTailscaleHost("muhammads-macbook-pro.tail8a4dee.ts.net."))
    #expect(!TailscaleEndpoint.isTailscaleHost("example.com"))
}

@Test
func tailscaleEndpointUpgradesMagicDNSWebSocketsToTLS() {
    let url = URL(string: "ws://muhammads-macbook-pro.tail8a4dee.ts.net:8765")!
    let upgraded = TailscaleEndpoint.upgradeToTLS(url)
    #expect(upgraded.absoluteString == "wss://muhammads-macbook-pro.tail8a4dee.ts.net:8765")
}

@Test
@MainActor
func socketManagerFallsBackAcrossCandidatesUntilConnected() async {
    let manager = SocketManager()
    let candidates = ["ws://127.0.0.1:9001", "ws://127.0.0.1:9002", "ws://127.0.0.1:9003"]
    var attempts: [String] = []

    do {
        try await manager.connectUsingCandidates(candidates) { endpoint in
            attempts.append(endpoint)
            if endpoint != "ws://127.0.0.1:9002" {
                throw SocketError.connectionFailed("simulated failure")
            }
        }
    } catch {
        Issue.record("Expected fallback to succeed, got error: \(error)")
    }

    #expect(attempts == ["ws://127.0.0.1:9001", "ws://127.0.0.1:9002"])
}

@Test
@MainActor
func socketManagerStopsStateMachineAfterFirstSuccessfulCandidate() async {
    let manager = SocketManager()
    let candidates = ["ws://127.0.0.1:9101", "ws://127.0.0.1:9102"]
    var attempts: [String] = []

    do {
        try await manager.connectUsingCandidates(candidates) { endpoint in
            attempts.append(endpoint)
            if endpoint == "ws://127.0.0.1:9101" {
                return
            }
            throw SocketError.connectionFailed("should not be attempted")
        }
    } catch {
        Issue.record("Expected first candidate success, got \(error)")
    }

    #expect(attempts == ["ws://127.0.0.1:9101"])
}

@Test
@MainActor
func socketManagerReportsFailureAfterAllCandidatesFail() async {
    let manager = SocketManager()
    let candidates = ["ws://127.0.0.1:9201", "ws://127.0.0.1:9202"]
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
            #expect(reason.contains("ws://127.0.0.1:9201"))
            #expect(reason.contains("ws://127.0.0.1:9202"))
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
        Issue.record("Expected noConfiguredEndpoint for empty candidates.")
    } catch let error as SocketError {
        if case .noConfiguredEndpoint = error {
            #expect(true)
        } else {
            Issue.record("Expected noConfiguredEndpoint, got \(error)")
        }
    } catch {
        Issue.record("Expected SocketError, got \(error)")
    }
}

@Test
@MainActor
func socketManagerAllowsRetryAfterFailedDirectConnect() async {
    let manager = SocketManager()
    let missingEndpoint = "ws://127.0.0.1:65534"
    defer { manager.disconnect() }

    do {
        try await manager.connect(toURLString: missingEndpoint)
        Issue.record("Expected first connect attempt to fail for missing endpoint.")
    } catch {
        // Expected
    }

    do {
        try await manager.connect(toURLString: missingEndpoint)
        Issue.record("Expected second connect attempt to fail for missing endpoint.")
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

    manager.dispatcher.onStreamingUpdate = { requestId, _delta, text, done in
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
