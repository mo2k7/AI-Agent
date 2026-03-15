import Foundation
import Testing
@testable import AIAgentApp

@Test
func messageDispatcherKeepsInterleavedStreamsIsolatedByRequest() {
    let dispatcher = MessageDispatcher()
    var updates: [(requestId: String, text: String, done: Bool)] = []
    var completions: [String: String] = [:]

    dispatcher.onStreamingUpdate = { requestId, _delta, text, done in
        updates.append((requestId, text, done))
    }
    dispatcher.onComplete = { requestId, content in
        completions[requestId] = content ?? ""
    }

    dispatcher.dispatch(
        .stream(
            StreamResponse(
                jsonrpc: "2.0",
                id: "req-a",
                type: "stream",
                delta: "Al",
                done: false
            )
        )
    )
    dispatcher.dispatch(
        .stream(
            StreamResponse(
                jsonrpc: "2.0",
                id: "req-b",
                type: "stream",
                delta: "Be",
                done: false
            )
        )
    )
    dispatcher.dispatch(
        .stream(
            StreamResponse(
                jsonrpc: "2.0",
                id: "req-a",
                type: "stream",
                delta: "pha",
                done: true
            )
        )
    )
    dispatcher.dispatch(
        .result(
            ResultResponse(
                jsonrpc: "2.0",
                id: "req-a",
                type: "result",
                result: .init(content: "Alpha", toolCalls: nil),
                error: nil
            )
        )
    )
    dispatcher.dispatch(
        .stream(
            StreamResponse(
                jsonrpc: "2.0",
                id: "req-b",
                type: "stream",
                delta: "ta",
                done: true
            )
        )
    )
    dispatcher.dispatch(
        .result(
            ResultResponse(
                jsonrpc: "2.0",
                id: "req-b",
                type: "result",
                result: .init(content: "Beta", toolCalls: nil),
                error: nil
            )
        )
    )

    #expect(updates.contains { $0.requestId == "req-a" && $0.text == "Alpha" && $0.done })
    #expect(updates.contains { $0.requestId == "req-b" && $0.text == "Beta" && $0.done })
    #expect(completions["req-a"] == "Alpha")
    #expect(completions["req-b"] == "Beta")
}

@Test
func streamingParserRecoversAfterInvalidLineAndParsesNextMessage() {
    let parser = StreamingParser()
    var errors: [StreamingParserError] = []
    var received: [IPCParsedMessage] = []

    parser.onError = { errors.append($0) }
    parser.onMessageReceived = { received.append($0) }

    parser.processString(#"{"jsonrpc":"2.0","id":"broken""# + "\n")
    parser.processString(
        #"{"jsonrpc":"2.0","id":"req-ok","type":"status","status":"thinking","detail":"Working"}"# + "\n"
    )

    #expect(errors.count == 1)
    if let firstError = errors.first {
        if case .protocolError(let detail) = firstError {
            #expect(detail.contains("header"))
        } else {
            Issue.record("Expected protocolError error type.")
        }
    } else {
        Issue.record("Expected one parser error.")
    }

    #expect(received.count == 1)
    if let firstMessage = received.first {
        if case .status(let status) = firstMessage {
            #expect(status.id == "req-ok")
            #expect(status.status == "thinking")
            #expect(status.detail == "Working")
        } else {
            Issue.record("Expected parsed status message after recovery.")
        }
    }
}

@Test
func ipcMessageParserParsesSystemVersionPayload() {
    let json = """
    {"jsonrpc":"2.0","id":"req-version","type":"system","system":{"event":"version","protocol_version":"1.1.0","code_version":7,"features":["prompt","cancel","session.list"]}}
    """

    switch IPCMessageParser.parse(json) {
    case .success(.system(let response)):
        #expect(response.id == "req-version")
        #expect(response.system.event == "version")
        #expect(response.system.protocolVersion == "1.1.0")
        #expect(response.system.codeVersion == 7)
        #expect(response.system.features?.contains("session.list") == true)
    case .success:
        Issue.record("Expected system message.")
    case .failure(let error):
        Issue.record("System version payload failed to parse: \(error.localizedDescription)")
    }
}

@Test
func dispatcherErrorForOneRequestDoesNotResetAnotherStreamAccumulator() {
    let dispatcher = MessageDispatcher()
    var updates: [(requestId: String, text: String, done: Bool)] = []
    var errors: [(requestId: String, message: String, code: Int?, data: [String: Any]?)] = []

    dispatcher.onStreamingUpdate = { requestId, _delta, text, done in
        updates.append((requestId, text, done))
    }
    dispatcher.onError = { requestId, message, code, data in
        errors.append((requestId, message, code, data))
    }

    dispatcher.dispatch(
        .stream(
            StreamResponse(
                jsonrpc: "2.0",
                id: "req-main",
                type: "stream",
                delta: "Hel",
                done: false
            )
        )
    )
    dispatcher.dispatch(
        .error(
            ResultResponse(
                jsonrpc: "2.0",
                id: "req-other",
                type: "error",
                result: nil,
                error: .init(code: -32600, message: "Invalid request", data: nil)
            )
        )
    )
    dispatcher.dispatch(
        .stream(
            StreamResponse(
                jsonrpc: "2.0",
                id: "req-main",
                type: "stream",
                delta: "lo",
                done: true
            )
        )
    )

    #expect(errors.count == 1)
    #expect(errors.first?.requestId == "req-other")
    #expect(errors.first?.code == -32600)
    #expect(updates.contains { $0.requestId == "req-main" && $0.text == "Hello" && $0.done })
}
