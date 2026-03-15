//
//  GeminiAPITypes.swift
//  AIAgentUI
//
//  Codable types matching the Gemini REST API request/response schema.
//  Used exclusively by IOSGeminiService for direct API calls.
//

import Foundation

// MARK: - Request Types

/// Top-level request body for `streamGenerateContent`.
struct GeminiRequest: Encodable {
    let contents: [GeminiContent]
    let tools: [GeminiTool]?
    let systemInstruction: GeminiContent?
    let generationConfig: GeminiGenerationConfig?

    enum CodingKeys: String, CodingKey {
        case contents
        case tools
        case systemInstruction = "system_instruction"
        case generationConfig = "generation_config"
    }
}

/// A single content block (user turn, model turn, or system instruction).
struct GeminiContent: Codable {
    let role: String?
    let parts: [GeminiPart]
}

/// A part within a content block — text, function call, or function response.
struct GeminiPart: Codable {
    let text: String?
    let functionCall: GeminiFunctionCall?
    let functionResponse: GeminiFunctionResponse?

    enum CodingKeys: String, CodingKey {
        case text
        case functionCall = "functionCall"
        case functionResponse = "functionResponse"
    }

    /// Convenience: text-only part.
    init(text: String) {
        self.text = text
        self.functionCall = nil
        self.functionResponse = nil
    }

    /// Convenience: function call part.
    init(functionCall: GeminiFunctionCall) {
        self.text = nil
        self.functionCall = functionCall
        self.functionResponse = nil
    }

    /// Convenience: function response part.
    init(functionResponse: GeminiFunctionResponse) {
        self.text = nil
        self.functionCall = nil
        self.functionResponse = functionResponse
    }
}

/// A function call emitted by the model.
struct GeminiFunctionCall: Codable {
    let name: String
    let args: [String: JSONValue]
}

/// A function response to feed back to the model.
struct GeminiFunctionResponse: Codable {
    let name: String
    let response: [String: JSONValue]
}

/// Tool definition containing function declarations.
struct GeminiTool: Encodable {
    let functionDeclarations: [GeminiFunctionDeclaration]

    enum CodingKeys: String, CodingKey {
        case functionDeclarations = "function_declarations"
    }
}

/// A single function declaration for Gemini function calling.
struct GeminiFunctionDeclaration: Encodable {
    let name: String
    let description: String
    let parameters: GeminiFunctionParameters?
}

/// JSON Schema for function parameters.
struct GeminiFunctionParameters: Encodable {
    let type: String
    let properties: [String: GeminiFunctionProperty]?
    let required: [String]?
}

/// A single property in the function parameter schema.
struct GeminiFunctionProperty: Encodable {
    let type: String
    let description: String?
    let `enum`: [String]?
    let items: GeminiFunctionPropertyItems?
}

/// Item schema for array properties.
struct GeminiFunctionPropertyItems: Encodable {
    let type: String
}

/// Generation configuration.
struct GeminiGenerationConfig: Encodable {
    let temperature: Double?
    let topP: Double?
    let topK: Int?
    let maxOutputTokens: Int?
    let candidateCount: Int?

    enum CodingKeys: String, CodingKey {
        case temperature
        case topP = "top_p"
        case topK = "top_k"
        case maxOutputTokens = "max_output_tokens"
        case candidateCount = "candidate_count"
    }
}

// MARK: - Response Types (SSE Streaming)

/// A single SSE chunk from `streamGenerateContent`.
struct GeminiStreamChunk: Decodable {
    let candidates: [GeminiCandidate]?
    let usageMetadata: GeminiUsageMetadata?
    let error: GeminiErrorResponse?
}

/// A candidate response.
struct GeminiCandidate: Decodable {
    let content: GeminiContent?
    let finishReason: String?
    let safetyRatings: [GeminiSafetyRating]?

    enum CodingKeys: String, CodingKey {
        case content
        case finishReason = "finishReason"
        case safetyRatings = "safetyRatings"
    }
}

/// Safety rating for a candidate.
struct GeminiSafetyRating: Decodable {
    let category: String
    let probability: String
}

/// Usage statistics.
struct GeminiUsageMetadata: Decodable {
    let promptTokenCount: Int?
    let candidatesTokenCount: Int?
    let totalTokenCount: Int?
}

/// Error response from the API.
struct GeminiErrorResponse: Decodable {
    let code: Int?
    let message: String?
    let status: String?
}

// MARK: - JSON Value (Type-Erased Codable)

/// Type-erased JSON value for function call arguments and responses.
enum JSONValue: Codable, Sendable {
    case string(String)
    case int(Int)
    case double(Double)
    case bool(Bool)
    case array([JSONValue])
    case object([String: JSONValue])
    case null

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()

        if container.decodeNil() {
            self = .null
            return
        }
        if let bool = try? container.decode(Bool.self) {
            self = .bool(bool)
            return
        }
        if let int = try? container.decode(Int.self) {
            self = .int(int)
            return
        }
        if let double = try? container.decode(Double.self) {
            self = .double(double)
            return
        }
        if let string = try? container.decode(String.self) {
            self = .string(string)
            return
        }
        if let array = try? container.decode([JSONValue].self) {
            self = .array(array)
            return
        }
        if let object = try? container.decode([String: JSONValue].self) {
            self = .object(object)
            return
        }

        throw DecodingError.dataCorruptedError(
            in: container,
            debugDescription: "JSONValue: unsupported type"
        )
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .string(let s): try container.encode(s)
        case .int(let i): try container.encode(i)
        case .double(let d): try container.encode(d)
        case .bool(let b): try container.encode(b)
        case .array(let a): try container.encode(a)
        case .object(let o): try container.encode(o)
        case .null: try container.encodeNil()
        }
    }

    /// Convert to a plain Swift `Any` for bridging with untyped APIs.
    var anyValue: Any {
        switch self {
        case .string(let s): return s
        case .int(let i): return i
        case .double(let d): return d
        case .bool(let b): return b
        case .array(let a): return a.map(\.anyValue)
        case .object(let o): return o.mapValues(\.anyValue)
        case .null: return NSNull()
        }
    }

    /// Create from a plain Swift `Any`.
    static func from(_ value: Any) -> JSONValue {
        switch value {
        case let s as String: return .string(s)
        case let b as Bool: return .bool(b)
        case let i as Int: return .int(i)
        case let d as Double: return .double(d)
        case let a as [Any]: return .array(a.map { from($0) })
        case let o as [String: Any]: return .object(o.mapValues { from($0) })
        default: return .null
        }
    }
}
