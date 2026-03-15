import Foundation
import Testing
@testable import AIAgentApp

@Test
func streamingParserHandlesFragmentedJSONLines() {
    let parser = StreamingParser()
    var received: [IPCParsedMessage] = []
    parser.onMessageReceived = { received.append($0) }

    let part1 = Data(#"{"jsonrpc":"2.0","id":"req-1","type":"stream","delta":"hel"#.utf8)
    let part2 = Data(#"lo","done":false}"#.utf8)
    let delimiter = Data("\n".utf8)

    parser.processData(part1)
    #expect(received.isEmpty)

    parser.processData(part2 + delimiter)
    #expect(received.count == 1)

    if let first = received.first {
        if case .stream(let stream) = first {
            #expect(stream.id == "req-1")
            #expect(stream.delta == "hello")
            #expect(stream.done == false)
        } else {
            Issue.record("Expected stream message.")
        }
    } else {
        Issue.record("Expected one parsed stream message.")
    }
}

@Test
func streamingParserReportsInvalidJSON() {
    let parser = StreamingParser()
    var reportedError: StreamingParserError?
    parser.onError = { reportedError = $0 }

    parser.processString(#"{"jsonrpc":"2.0","id":"bad""# + "\n")

    if case .protocolError(let detail)? = reportedError {
        #expect(detail.contains("header"))
    } else {
        Issue.record("Expected protocolError parsing error.")
    }
}

@Test
func streamingParserResetsOnBufferOverflowAndRecovers() {
    let parser = StreamingParser(maxBufferBytes: 128)
    var errors: [StreamingParserError] = []
    var received: [IPCParsedMessage] = []
    parser.onError = { errors.append($0) }
    parser.onMessageReceived = { received.append($0) }

    parser.processData(Data(repeating: 0x41, count: 256))
    #expect(errors.count == 1)
    if case .bufferOverflow? = errors.first {
        #expect(true)
    } else {
        Issue.record("Expected bufferOverflow error.")
    }

    parser.processString(
        #"{"jsonrpc":"2.0","id":"req-recover","type":"status","status":"thinking","detail":"ok"}"# + "\n"
    )

    #expect(received.count == 1)
    if let message = received.first {
        if case .status(let status) = message {
            #expect(status.id == "req-recover")
            #expect(status.detail == "ok")
        } else {
            Issue.record("Expected status message after overflow recovery.")
        }
    } else {
        Issue.record("Expected parsed message after overflow recovery.")
    }
}

@Test
func streamingParserOverflowFromCombinedBufferDropsStalePartialData() {
    let parser = StreamingParser(maxBufferBytes: 120)
    var errors: [StreamingParserError] = []
    var received: [IPCParsedMessage] = []
    parser.onError = { errors.append($0) }
    parser.onMessageReceived = { received.append($0) }

    parser.processString(String(repeating: "x", count: 100))
    parser.processString(
        #"{"jsonrpc":"2.0","id":"req-after-reset","type":"status","status":"thinking","detail":"fresh"}"# + "\n"
    )

    #expect(errors.count == 1)
    if case .bufferOverflow? = errors.first {
        #expect(true)
    } else {
        Issue.record("Expected combined-buffer overflow error.")
    }

    #expect(received.count == 1)
    if let message = received.first {
        if case .status(let status) = message {
            #expect(status.id == "req-after-reset")
            #expect(status.detail == "fresh")
        } else {
            Issue.record("Expected status message from post-reset data.")
        }
    } else {
        Issue.record("Expected one parsed message from post-reset data.")
    }
}

@Test
func messageDispatcherEmitsStreamingAndCompletion() {
    let dispatcher = MessageDispatcher()

    var streamSnapshots: [(requestId: String, text: String, done: Bool)] = []
    var completion: (requestId: String, content: String?)?

    dispatcher.onStreamingUpdate = { requestId, _delta, text, done in
        streamSnapshots.append((requestId, text, done))
    }
    dispatcher.onComplete = { requestId, content in
        completion = (requestId, content)
    }

    dispatcher.dispatch(
        .stream(
            StreamResponse(
                jsonrpc: "2.0",
                id: "req-2",
                type: "stream",
                delta: "Hel",
                done: false
            )
        )
    )
    dispatcher.dispatch(
        .stream(
            StreamResponse(
                jsonrpc: "2.0",
                id: "req-2",
                type: "stream",
                delta: "lo",
                done: true
            )
        )
    )
    dispatcher.dispatch(
        .result(
            ResultResponse(
                jsonrpc: "2.0",
                id: "req-2",
                type: "result",
                result: .init(content: "Hello", toolCalls: nil),
                error: nil
            )
        )
    )

    #expect(streamSnapshots.count == 2)
    #expect(streamSnapshots[0].text == "Hel")
    #expect(streamSnapshots[0].done == false)
    #expect(streamSnapshots[1].text == "Hello")
    #expect(streamSnapshots[1].done == true)
    #expect(completion?.requestId == "req-2")
    #expect(completion?.content == "Hello")
}

@Test
func messageDispatcherSkipsNoOpEmptyStreamChunks() {
    let dispatcher = MessageDispatcher()
    var streamSnapshots: [(requestId: String, text: String, done: Bool)] = []

    dispatcher.onStreamingUpdate = { requestId, _delta, text, done in
        streamSnapshots.append((requestId, text, done))
    }

    dispatcher.dispatch(
        .stream(
            StreamResponse(
                jsonrpc: "2.0",
                id: "req-empty",
                type: "stream",
                delta: "",
                done: false
            )
        )
    )
    dispatcher.dispatch(
        .stream(
            StreamResponse(
                jsonrpc: "2.0",
                id: "req-empty",
                type: "stream",
                delta: "Hi",
                done: false
            )
        )
    )

    #expect(streamSnapshots.count == 1)
    #expect(streamSnapshots.first?.requestId == "req-empty")
    #expect(streamSnapshots.first?.text == "Hi")
    #expect(streamSnapshots.first?.done == false)
}

@Test
func messageDispatcherEmitsErrorWithCode() {
    let dispatcher = MessageDispatcher()
    var receivedError: (requestId: String, message: String, code: Int?, data: [String: Any]?)?

    dispatcher.onError = { requestId, message, code, data in
        receivedError = (requestId, message, code, data)
    }

    dispatcher.dispatch(
        .error(
            ResultResponse(
                jsonrpc: "2.0",
                id: "req-3",
                type: "error",
                result: nil,
                error: .init(code: -32001, message: "API error", data: nil)
            )
        )
    )

    #expect(receivedError?.requestId == "req-3")
    #expect(receivedError?.message == "API error")
    #expect(receivedError?.code == -32001)
    #expect(receivedError?.data == nil)
}

@Test
func messageDispatcherEmitsStructuredErrorData() {
    let dispatcher = MessageDispatcher()
    var receivedError: (requestId: String, message: String, code: Int?, data: [String: Any]?)?

    dispatcher.onError = { requestId, message, code, data in
        receivedError = (requestId, message, code, data)
    }

    dispatcher.dispatch(
        .error(
            ResultResponse(
                jsonrpc: "2.0",
                id: "req-timeout",
                type: "error",
                result: nil,
                error: .init(
                    code: -32014,
                    message: "Request timed out",
                    data: [
                        "code": AnyCodable("model_timeout"),
                        "phase": AnyCodable("model_generation"),
                        "timeout_seconds": AnyCodable(180.0),
                    ]
                )
            )
        )
    )

    #expect(receivedError?.requestId == "req-timeout")
    #expect(receivedError?.message == "Request timed out")
    #expect(receivedError?.code == -32014)
    #expect(receivedError?.data?["code"] as? String == "model_timeout")
}
