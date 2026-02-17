import Foundation
import Testing
@testable import AIAgentApp

@Test
func toolCallResponseParsesLifecycleStatusesFromJSON() {
    let payloads: [(json: String, expectedStatus: ToolCallStatus)] = [
        (#"{"jsonrpc":"2.0","id":"req-1","type":"tool_call","tool":{"name":"search_files","arguments":{"query":"swift"},"status":"pending"}}"#, .pending),
        (#"{"jsonrpc":"2.0","id":"req-1","type":"tool_call","tool":{"name":"search_files","arguments":{"query":"swift"},"status":"executing"}}"#, .executing),
        (#"{"jsonrpc":"2.0","id":"req-1","type":"tool_call","tool":{"name":"search_files","arguments":{"query":"swift"},"status":"success","result":"done"}}"#, .success),
        (#"{"jsonrpc":"2.0","id":"req-1","type":"tool_call","tool":{"name":"search_files","arguments":{"query":"swift"},"status":"failed","error":"boom"}}"#, .failed),
    ]

    for entry in payloads {
        switch IPCMessageParser.parse(entry.json) {
        case .success(.toolCall(let response)):
            do {
                let toolCall = try response.toToolCall()
                #expect(toolCall.status == entry.expectedStatus)
            } catch {
                Issue.record("Expected tool call lifecycle status parse to succeed.")
            }
        case .success:
            Issue.record("Expected parsed tool_call response")
        case .failure:
            Issue.record("Expected parsable tool_call payload")
        }
    }
}

@Test
func toolCallResponseRejectsUnknownStatus() {
    let json = #"{"jsonrpc":"2.0","id":"req-x","type":"tool_call","tool":{"name":"search_files","arguments":{},"status":"queued_elsewhere"}}"#

    switch IPCMessageParser.parse(json) {
    case .success(.toolCall(let response)):
        do {
            _ = try response.toToolCall()
            Issue.record("Unknown tool status should fail parsing.")
        } catch {
            #expect(true)
        }
    case .success:
        Issue.record("Expected parsed tool_call response")
    case .failure:
        Issue.record("Expected parsable tool_call payload")
    }
}

@Test
func toolCallResponseParsesNestedArgumentsForRenderMapping() {
    let json = #"{"jsonrpc":"2.0","id":"req-9","type":"tool_call","tool":{"name":"open_item","arguments":{"path":"/tmp/a.txt","flags":[true,false],"meta":{"depth":2,"owner":"me"}},"status":"executing"}}"#

    let parsed: IPCParsedMessage
    switch IPCMessageParser.parse(json) {
    case .success(let message):
        parsed = message
    case .failure:
        Issue.record("Expected parsable tool_call payload")
        return
    }
    guard case .toolCall(let response) = parsed else {
        Issue.record("Expected parsed tool_call response")
        return
    }
    let toolCall: ToolCall
    do {
        toolCall = try response.toToolCall()
    } catch {
        Issue.record("Expected tool_call payload to parse into ToolCall.")
        return
    }

    #expect(toolCall.arguments["path"] == .string("/tmp/a.txt"))
    #expect(toolCall.arguments["flags"] == .array([.bool(true), .bool(false)]))

    if case .dictionary(let dict)? = toolCall.arguments["meta"] {
        #expect(dict["depth"] == .int(2))
        #expect(dict["owner"] == .string("me"))
    } else {
        Issue.record("Expected nested dictionary argument")
    }
}

@Test
func messageDispatcherDeliversToolCallLifecycleSequence() {
    let dispatcher = MessageDispatcher()
    var statuses: [ToolCallStatus] = []

    dispatcher.onToolCall = { toolCall, requestId in
        #expect(requestId == "req-life")
        statuses.append(toolCall.status)
    }

    let updates: [ToolCallStatus] = [.pending, .executing, .success]
    for status in updates {
        dispatcher.dispatch(
            .toolCall(
                ToolCallResponse(
                    jsonrpc: "2.0",
                    id: "req-life",
                    type: "tool_call",
                    tool: .init(
                        name: "search_files",
                        arguments: ["query": AnyCodable("swift")],
                        status: status.rawValue,
                        result: status == .success ? "done" : nil,
                        error: nil
                    )
                )
            )
        )
    }

    #expect(statuses == updates)
}
