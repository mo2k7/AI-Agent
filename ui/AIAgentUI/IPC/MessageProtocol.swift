//
//  MessageProtocol.swift
//  AIAgentUI
//
//  Created for Personal macOS AI Agent
//  Status: Active - IPC communication protocol
//

import Foundation

// MARK: - JSON-RPC Protocol Version

/// The JSON-RPC version used for IPC communication
let kJSONRPCVersion = "2.0"

// MARK: - Request Messages (Swift → Python)

/// Base request structure for IPC messages
struct IPCRequest: Encodable {
    let jsonrpc: String = kJSONRPCVersion
    let id: String
    let method: String
    let params: [String: AnyCodable]
    
    init(id: String = UUID().uuidString, method: String, params: [String: AnyCodable] = [:]) {
        self.id = id
        self.method = method
        self.params = params
    }
}

/// Request to send a prompt to the agent
struct PromptRequest: Encodable {
    let jsonrpc: String = kJSONRPCVersion
    let id: String
    let method: String = "prompt"
    let params: PromptParams
    
    struct PromptParams: Encodable {
        let prompt: String  // Changed from 'text' to 'prompt' to match Python backend expectation
        let model: String   // The Gemini model to use for this request
        let sessionId: String?
        let memoryMode: String?
        let executionMode: String?
        let inputPaths: [String]?
        let verbosity: String?
        let presentationStyle: String?
        let streamingAnimation: String?
        let deepThink: Bool?
        let correlationId: String?

        enum CodingKeys: String, CodingKey {
            case prompt
            case model
            case sessionId = "session_id"
            case memoryMode = "memory_mode"
            case executionMode = "execution_mode"
            case inputPaths = "input_paths"
            case verbosity
            case presentationStyle = "presentation_style"
            case streamingAnimation = "stream_animation"
            case deepThink = "deep_think"
            case correlationId = "correlation_id"
        }
    }
    
    init(
        id: String = UUID().uuidString,
        text: String,
        model: String,
        sessionId: String? = nil,
        memoryMode: String? = nil,
        executionMode: String? = nil,
        inputPaths: [String]? = nil,
        verbosity: String? = nil,
        presentationStyle: String? = nil,
        streamingAnimation: String? = nil,
        deepThink: Bool? = nil,
        correlationId: String? = nil
    ) {
        self.id = id
        self.params = PromptParams(
            prompt: text,
            model: model,
            sessionId: sessionId,
            memoryMode: memoryMode,
            executionMode: executionMode,
            inputPaths: inputPaths,
            verbosity: verbosity,
            presentationStyle: presentationStyle,
            streamingAnimation: streamingAnimation,
            deepThink: deepThink,
            correlationId: correlationId
        )
    }
    
    func toJSONString() -> String? {
        let encoder = JSONEncoder()
        guard let data = try? encoder.encode(self) else { return nil }
        return String(data: data, encoding: .utf8)
    }
}

/// Request to cancel the current operation
struct CancelRequest: Encodable {
    let jsonrpc: String = kJSONRPCVersion
    let id: String
    let method: String = "cancel"
    let params: CancelParams
    
    struct CancelParams: Encodable {
        let requestId: String?
        
        enum CodingKeys: String, CodingKey {
            case requestId = "request_id"
        }
    }
    
    init(id: String = UUID().uuidString, targetRequestId: String? = nil) {
        self.id = id
        self.params = CancelParams(requestId: targetRequestId)
    }
    
    func toJSONString() -> String? {
        let encoder = JSONEncoder()
        guard let data = try? encoder.encode(self) else { return nil }
        return String(data: data, encoding: .utf8)
    }
}

/// Request to ping the backend for health check
struct PingRequest: Encodable {
    let jsonrpc: String = kJSONRPCVersion
    let id: String
    let method: String = "ping"
    
    init(id: String = UUID().uuidString) {
        self.id = id
    }
    
    func toJSONString() -> String? {
        let encoder = JSONEncoder()
        guard let data = try? encoder.encode(self) else { return nil }
        return String(data: data, encoding: .utf8)
    }
}

/// Request to reload the backend code (hot reload)
struct ReloadRequest: Encodable {
    let jsonrpc: String = kJSONRPCVersion
    let id: String
    let method: String = "reload"
    let params: ReloadParams
    
    struct ReloadParams: Encodable {
        let trigger: String  // 'ipc', 'user', etc.
    }
    
    init(id: String = UUID().uuidString, trigger: String = "ipc") {
        self.id = id
        self.params = ReloadParams(trigger: trigger)
    }
    
    func toJSONString() -> String? {
        let encoder = JSONEncoder()
        guard let data = try? encoder.encode(self) else { return nil }
        return String(data: data, encoding: .utf8)
    }
}

/// Request to get the backend version information
struct VersionRequest: Encodable {
    let jsonrpc: String = kJSONRPCVersion
    let id: String
    let method: String = "version"
    
    init(id: String = UUID().uuidString) {
        self.id = id
    }
    
    func toJSONString() -> String? {
        let encoder = JSONEncoder()
        guard let data = try? encoder.encode(self) else { return nil }
        return String(data: data, encoding: .utf8)
    }
}

// MARK: - Response Messages (Python → Swift)

/// Type of response message received from the backend
enum IPCMessageType: String, Decodable {
    case status
    case stream
    case toolCall = "tool_call"
    case result
    case error
    case system  // System-level messages (version, reload, etc.)
}

/// Base response structure for parsing message type
struct IPCResponseHeader: Decodable {
    let jsonrpc: String
    let id: String
    let type: IPCMessageType
}

/// Status update message from the backend
struct StatusResponse: Decodable {
    let jsonrpc: String
    let id: String
    let type: String
    let status: String
    let detail: String?
    
    /// Parse the status into AgentStatus enum
    func toAgentStatus() -> AgentStatus {
        return AgentStatus.from(rawStatus: status, detail: detail)
    }
}

/// Streaming response chunk from the backend
struct StreamResponse: Decodable {
    let jsonrpc: String
    let id: String
    let type: String
    let delta: String
    let done: Bool
}

/// Tool call notification from the backend
struct ToolCallResponse: Decodable {
    let jsonrpc: String
    let id: String
    let type: String
    let tool: ToolCallData
    
    struct ToolCallData: Decodable {
        let name: String
        let arguments: [String: AnyCodable]
        let status: String
        let result: String?
        let error: String?
    }
    
    /// Parse into a ToolCall model
    func toToolCall() throws -> ToolCall {
        var args: [String: ArgumentValue] = [:]
        for (key, value) in tool.arguments {
            if let argValue = ArgumentValue.from(value.value) {
                args[key] = argValue
            }
        }
        
        let status: ToolCallStatus
        switch tool.status {
        case "pending": status = .pending
        case "executing": status = .executing
        case "success": status = .success
        case "failed": status = .failed
        default:
            throw IPCMessageParseError.unknownToolStatus(tool.status)
        }
        
        return ToolCall(
            name: tool.name,
            arguments: args,
            status: status,
            result: tool.result,
            error: tool.error
        )
    }
}

/// Final result message from the backend
struct ResultResponse: Decodable {
    let jsonrpc: String
    let id: String
    let type: String
    let result: ResultData?
    let error: ErrorData?
    
    struct ResultData: Decodable {
        let content: String
        let toolCalls: [SimpleToolCallData]?
        
        enum CodingKeys: String, CodingKey {
            case content
            case toolCalls = "tool_calls"
        }
    }
    
    /// Simplified tool call data for result messages (only name and arguments)
    struct SimpleToolCallData: Decodable {
        let name: String
        let arguments: [String: AnyCodable]
    }
    
    struct ErrorData: Decodable {
        let code: Int
        let message: String
    }
}

/// System message response from the backend (version, reload, etc.)
struct SystemResponse: Decodable {
    let jsonrpc: String
    let id: String
    let type: String
    let system: SystemData
    
    struct SystemData: Decodable {
        let event: String
        let protocolVersion: String?
        let codeVersion: Int?
        let features: [String]?
        let trigger: String?
        let success: Bool?
        let newVersion: Int?
        let error: String?
        let changedFiles: [String]?
        let domain: String?
        let action: String?
        let payload: [String: AnyCodable]?
        
        enum CodingKeys: String, CodingKey {
            case event
            case protocolVersion = "protocol_version"
            case codeVersion = "code_version"
            case features
            case trigger
            case success
            case newVersion = "new_version"
            case error
            case changedFiles = "changed_files"
            case domain
            case action
            case payload
        }
    }
}

// MARK: - AnyCodable Type

/// Type-erased Codable wrapper for handling dynamic JSON values
struct AnyCodable: Codable {
    let value: Any
    
    init(_ value: Any) {
        self.value = value
    }
    
    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        
        if container.decodeNil() {
            self.value = NSNull()
        } else if let bool = try? container.decode(Bool.self) {
            self.value = bool
        } else if let int = try? container.decode(Int.self) {
            self.value = int
        } else if let double = try? container.decode(Double.self) {
            self.value = double
        } else if let string = try? container.decode(String.self) {
            self.value = string
        } else if let array = try? container.decode([AnyCodable].self) {
            self.value = array.map { $0.value }
        } else if let dictionary = try? container.decode([String: AnyCodable].self) {
            self.value = dictionary.mapValues { $0.value }
        } else {
            throw DecodingError.dataCorruptedError(
                in: container,
                debugDescription: "AnyCodable value cannot be decoded"
            )
        }
    }
    
    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        
        switch value {
        case is NSNull:
            try container.encodeNil()
        case let bool as Bool:
            try container.encode(bool)
        case let int as Int:
            try container.encode(int)
        case let double as Double:
            try container.encode(double)
        case let string as String:
            try container.encode(string)
        case let array as [Any]:
            try container.encode(array.map { AnyCodable($0) })
        case let dictionary as [String: Any]:
            try container.encode(dictionary.mapValues { AnyCodable($0) })
        default:
            let context = EncodingError.Context(
                codingPath: container.codingPath,
                debugDescription: "AnyCodable value cannot be encoded"
            )
            throw EncodingError.invalidValue(value, context)
        }
    }
}

// MARK: - Message Parser

/// Parses incoming IPC messages into appropriate response types
enum IPCMessageParser {
    
    /// Parses a raw JSON string into the appropriate response type
    /// - Parameter jsonString: The raw JSON message
    /// - Returns: A parsed response or parse error
    static func parse(_ jsonString: String) -> Result<IPCParsedMessage, IPCMessageParseError> {
        guard let data = jsonString.data(using: .utf8) else {
            return .failure(.invalidEncoding)
        }
        
        let decoder = JSONDecoder()
        
        // First, determine the message type
        let header: IPCResponseHeader
        do {
            header = try decoder.decode(IPCResponseHeader.self, from: data)
        } catch {
            return .failure(.invalidHeader(error.localizedDescription))
        }
        
        // Parse the full message based on type
        switch header.type {
        case .status:
            do {
                let response = try decoder.decode(StatusResponse.self, from: data)
                return .success(.status(response))
            } catch {
                return .failure(.decodeFailure(type: "status", detail: error.localizedDescription))
            }
            
        case .stream:
            do {
                let response = try decoder.decode(StreamResponse.self, from: data)
                return .success(.stream(response))
            } catch {
                return .failure(.decodeFailure(type: "stream", detail: error.localizedDescription))
            }
            
        case .toolCall:
            do {
                let response = try decoder.decode(ToolCallResponse.self, from: data)
                return .success(.toolCall(response))
            } catch {
                return .failure(.decodeFailure(type: "tool_call", detail: error.localizedDescription))
            }
            
        case .result:
            do {
                let response = try decoder.decode(ResultResponse.self, from: data)
                return .success(.result(response))
            } catch {
                return .failure(.decodeFailure(type: "result", detail: error.localizedDescription))
            }
            
        case .error:
            do {
                let response = try decoder.decode(ResultResponse.self, from: data)
                return .success(.error(response))
            } catch {
                return .failure(.decodeFailure(type: "error", detail: error.localizedDescription))
            }
            
        case .system:
            do {
                let response = try decoder.decode(SystemResponse.self, from: data)
                return .success(.system(response))
            } catch {
                return .failure(.decodeFailure(type: "system", detail: error.localizedDescription))
            }
        }
    }
}

/// Parsed IPC message types
enum IPCParsedMessage {
    case status(StatusResponse)
    case stream(StreamResponse)
    case toolCall(ToolCallResponse)
    case result(ResultResponse)
    case error(ResultResponse)
    case system(SystemResponse)
}

enum IPCMessageParseError: Error, LocalizedError {
    case invalidEncoding
    case invalidHeader(String)
    case decodeFailure(type: String, detail: String)
    case unknownToolStatus(String)

    var errorDescription: String? {
        switch self {
        case .invalidEncoding:
            return "IPC message is not valid UTF-8."
        case .invalidHeader(let detail):
            return "IPC message header parse failed: \(detail)"
        case .decodeFailure(let type, let detail):
            return "IPC \(type) decode failed: \(detail)"
        case .unknownToolStatus(let status):
            return "Unknown tool status received from backend: \(status)"
        }
    }
}
