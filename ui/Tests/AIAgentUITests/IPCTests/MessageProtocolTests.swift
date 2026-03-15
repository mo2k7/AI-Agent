import Foundation
import Testing
@testable import AIAgentApp

@Test
func promptRequestEncodesPromptKeyAndModel() throws {
    let request = PromptRequest(
        id: "prompt-1",
        text: "hello",
        model: "gemini-2.5-flash"
    )

    let payload = try decodeJSONObject(from: request)
    let params = payload["params"] as? [String: Any]

    #expect(payload["id"] as? String == "prompt-1")
    #expect(payload["method"] as? String == "prompt")
    #expect(params?["prompt"] as? String == "hello")
    #expect(params?["text"] == nil)
    #expect(params?["model"] as? String == "gemini-2.5-flash")
    #expect(params?["stream"] == nil)
}

@Test
func promptRequestEncodesSessionAndMemoryModeWhenProvided() throws {
    let request = PromptRequest(
        id: "prompt-2",
        text: "remember this",
        model: "gemini-2.5-pro",
        sessionId: "session-abc",
        memoryMode: "ephemeral",
        executionMode: "plan",
        inputPaths: ["/tmp/a.txt", "/tmp/b.txt"],
        verbosity: "high",
        presentationStyle: "readable_pro",
        streamingAnimation: "wave_reveal",
        browseProfile: "flexible",
        deepThink: true,
        correlationId: "corr-123"
    )

    let payload = try decodeJSONObject(from: request)
    let params = payload["params"] as? [String: Any]

    #expect(params?["session_id"] as? String == "session-abc")
    #expect(params?["memory_mode"] as? String == "ephemeral")
    #expect(params?["execution_mode"] as? String == "plan")
    #expect((params?["input_paths"] as? [String]) == ["/tmp/a.txt", "/tmp/b.txt"])
    #expect(params?["verbosity"] as? String == "high")
    #expect(params?["presentation_style"] as? String == "readable_pro")
    #expect(params?["stream_animation"] as? String == "wave_reveal")
    #expect(params?["browse_profile"] as? String == "flexible")
    #expect(params?["deep_think"] as? Bool == true)
    #expect(params?["correlation_id"] as? String == "corr-123")
}

@Test
func cancelRequestEncodesTargetRequestId() throws {
    let request = CancelRequest(id: "cancel-1", targetRequestId: "prompt-1")

    let payload = try decodeJSONObject(from: request)
    let params = payload["params"] as? [String: Any]

    #expect(payload["method"] as? String == "cancel")
    #expect(params?["request_id"] as? String == "prompt-1")
}

@Test
func cancelRequestOmitsRequestIdWhenNil() throws {
    let request = CancelRequest(id: "cancel-2", targetRequestId: nil)

    let payload = try decodeJSONObject(from: request)
    let params = payload["params"] as? [String: Any]

    #expect(payload["method"] as? String == "cancel")
    #expect(params?["request_id"] == nil)
}

@Test
func ipcRequestEncodesSessionSetModeRPCParams() throws {
    let request = IPCRequest(
        id: "rpc-set-mode-1",
        method: "session.set_mode",
        params: [
            "session_id": AnyCodable("session-abc"),
            "memory_mode": AnyCodable("off"),
        ]
    )

    let payload = try decodeJSONObject(from: request)
    let params = payload["params"] as? [String: Any]

    #expect(payload["id"] as? String == "rpc-set-mode-1")
    #expect(payload["method"] as? String == "session.set_mode")
    #expect(params?["session_id"] as? String == "session-abc")
    #expect(params?["memory_mode"] as? String == "off")
}

@Test
func ipcMessageParserParsesStatusAndErrorMessages() throws {
    let statusJSON = """
    {"jsonrpc":"2.0","id":"req-1","type":"status","status":"thinking","detail":"Working"}
    """
    let errorJSON = """
    {"jsonrpc":"2.0","id":"req-1","type":"error","error":{"code":-32800,"message":"Request cancelled by user"}}
    """

    switch IPCMessageParser.parse(statusJSON) {
    case .success(.status(let response)):
            #expect(response.id == "req-1")
            #expect(response.status == "thinking")
            #expect(response.detail == "Working")
    case .success:
        Issue.record("Expected status response.")
    case .failure(let error):
        Issue.record("Status JSON was not parsed: \(error.localizedDescription)")
    }

    switch IPCMessageParser.parse(errorJSON) {
    case .success(.error(let response)):
            #expect(response.id == "req-1")
            #expect(response.error?.code == -32800)
            #expect(response.error?.message == "Request cancelled by user")
    case .success:
        Issue.record("Expected error response.")
    case .failure(let error):
        Issue.record("Error JSON was not parsed: \(error.localizedDescription)")
    }
}

@Test
func geminiModelCatalogDecodesLiveMetadata() throws {
    let json = """
    {
      "default_model": "gemini-2.5-flash",
      "models": [
        {
          "name": "gemini-2.5-flash",
          "display_name": "Gemini 2.5 Flash",
          "description": "Stable fast model",
          "supported_actions": ["generateContent"],
          "input_token_limit": 1048576,
          "output_token_limit": 65536,
          "is_preview": false,
          "supports_deep_think": true
        }
      ]
    }
    """

    let decoded = try JSONDecoder().decode(IPCModelCatalog.self, from: Data(json.utf8))

    #expect(decoded.defaultModel == "gemini-2.5-flash")
    #expect(decoded.models.count == 1)
    #expect(decoded.models.first?.resolvedDisplayName == "Gemini 2.5 Flash")
    #expect(decoded.models.first?.supportsDeepThink == true)
}

@Test
func ipcMessageParserParsesPlanModeStatuses() {
    let planningJSON = """
    {"jsonrpc":"2.0","id":"req-plan-1","type":"status","status":"planning","detail":"Building plan"}
    """
    let awaitingJSON = """
    {"jsonrpc":"2.0","id":"req-plan-1","type":"status","status":"awaiting_approval","detail":"Awaiting approval for apply_ops"}
    """

    switch IPCMessageParser.parse(planningJSON) {
    case .success(.status(let response)):
            #expect(response.toAgentStatus() == .planning)
    case .success:
        Issue.record("Expected planning status response.")
    case .failure(let error):
        Issue.record("Planning JSON was not parsed: \(error.localizedDescription)")
    }

    switch IPCMessageParser.parse(awaitingJSON) {
    case .success(.status(let response)):
            #expect(
                response.toAgentStatus()
                    == .awaitingApproval(detail: "Awaiting approval for apply_ops")
            )
    case .success:
        Issue.record("Expected awaiting_approval status response.")
    case .failure(let error):
        Issue.record("Awaiting-approval JSON was not parsed: \(error.localizedDescription)")
    }
}

@Test
func ipcMessageParserReturnsFailureForInvalidJSON() {
    let invalidJSON = #"{"jsonrpc":"2.0","id":"bad","type":"status","status":"thinking""#
    switch IPCMessageParser.parse(invalidJSON) {
    case .success:
        Issue.record("Expected invalid JSON parse failure.")
    case .failure:
        #expect(true)
    }
}

private func decodeJSONObject<T: Encodable>(from value: T) throws -> [String: Any] {
    let data = try JSONEncoder().encode(value)
    let object = try JSONSerialization.jsonObject(with: data)
    guard let dictionary = object as? [String: Any] else {
        throw TestDecodeError.invalidJSONObject
    }
    return dictionary
}

private enum TestDecodeError: Error {
    case invalidJSONObject
}
