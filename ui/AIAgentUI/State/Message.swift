//
//  Message.swift
//  AIAgentUI
//
//  Created for Personal macOS AI Agent
//  Status: Active - Message and tool call models
//

import Foundation

/// Represents a message in the conversation history.
struct Message: Identifiable, Equatable, Sendable {
    let id: UUID
    let role: MessageRole
    var content: String
    let timestamp: Date
    var toolCall: ToolCall?
    var isStreaming: Bool
    
    init(
        id: UUID = UUID(),
        role: MessageRole,
        content: String,
        timestamp: Date = Date(),
        toolCall: ToolCall? = nil,
        isStreaming: Bool = false
    ) {
        self.id = id
        self.role = role
        self.content = content
        self.timestamp = timestamp
        self.toolCall = toolCall
        self.isStreaming = isStreaming
    }
    
    /// Creates a user message
    static func user(_ content: String) -> Message {
        Message(role: .user, content: content)
    }
    
    /// Creates an assistant message
    static func assistant(_ content: String, isStreaming: Bool = false) -> Message {
        Message(role: .assistant, content: content, isStreaming: isStreaming)
    }
    
    /// Creates a streaming assistant message (empty content, streaming flag set)
    static func streamingAssistant() -> Message {
        Message(role: .assistant, content: "", isStreaming: true)
    }
    
    /// Creates an error message
    static func error(_ content: String) -> Message {
        Message(role: .system, content: content)
    }
}

/// The role of a message sender
enum MessageRole: String, Codable, Equatable, Sendable {
    case user
    case assistant
    case system
}

/// Represents a tool call made by the agent
struct ToolCall: Identifiable, Equatable, Sendable {
    let id: UUID
    let name: String
    let arguments: [String: ArgumentValue]
    var status: ToolCallStatus
    var result: String?
    var error: String?
    let timestamp: Date
    
    init(
        id: UUID = UUID(),
        name: String,
        arguments: [String: ArgumentValue],
        status: ToolCallStatus = .pending,
        result: String? = nil,
        error: String? = nil,
        timestamp: Date = Date()
    ) {
        self.id = id
        self.name = name
        self.arguments = arguments
        self.status = status
        self.result = result
        self.error = error
        self.timestamp = timestamp
    }
    
    /// Human-readable summary of arguments
    var argumentsSummary: String {
        arguments.map { "\($0.key): \($0.value.displayValue)" }.joined(separator: ", ")
    }
}

/// Status of a tool call execution
enum ToolCallStatus: String, Codable, Equatable, Sendable {
    case pending
    case executing
    case success
    case failed
    
    var displayText: String {
        switch self {
        case .pending: return "Pending"
        case .executing: return "Executing..."
        case .success: return "Success"
        case .failed: return "Failed"
        }
    }

    var badgeText: String {
        switch self {
        case .pending:
            return "Queued"
        case .executing:
            return "Running"
        case .success:
            return "Success"
        case .failed:
            return "Failed"
        }
    }
    
    var isComplete: Bool {
        self == .success || self == .failed
    }
    
    /// SF Symbol icon name for this status
    var iconName: String {
        switch self {
        case .pending: return "clock"
        case .executing: return "arrow.trianglehead.2.counterclockwise.rotate.90"
        case .success: return "checkmark.circle.fill"
        case .failed: return "xmark.circle.fill"
        }
    }
}

extension ToolCall {
    func merged(with update: ToolCall) -> ToolCall {
        guard name == update.name, arguments == update.arguments else {
            return update
        }

        var merged = self
        merged.status = update.status
        if let updateResult = update.result {
            merged.result = updateResult
        }
        if let updateError = update.error {
            merged.error = updateError
        }
        return merged
    }
}

/// Type-safe argument value wrapper for tool call arguments
enum ArgumentValue: Equatable, Sendable {
    case string(String)
    case int(Int)
    case double(Double)
    case bool(Bool)
    case null
    case array([ArgumentValue])
    case dictionary([String: ArgumentValue])
    
    /// Display-friendly string representation
    var displayValue: String {
        switch self {
        case .string(let s): return "\"\(s)\""
        case .int(let i): return String(i)
        case .double(let d): return String(d)
        case .bool(let b): return b ? "true" : "false"
        case .null: return "null"
        case .array(let arr):
            return "[\(arr.map { $0.displayValue }.joined(separator: ", "))]"
        case .dictionary(let dict):
            let pairs = dict.map { "\"\($0.key)\": \($0.value.displayValue)" }
            return "{\(pairs.joined(separator: ", "))}"
        }
    }
    
    /// Raw value for JSON encoding
    var rawValue: Any {
        switch self {
        case .string(let s): return s
        case .int(let i): return i
        case .double(let d): return d
        case .bool(let b): return b
        case .null: return NSNull()
        case .array(let arr): return arr.map { $0.rawValue }
        case .dictionary(let dict): return dict.mapValues { $0.rawValue }
        }
    }
}

// MARK: - ArgumentValue Factory

extension ArgumentValue {
    /// Creates an ArgumentValue from an Any value
    /// Returns nil if the value type is not supported
    static func from(_ value: Any) -> ArgumentValue? {
        switch value {
        case is NSNull:
            return .null
        case let bool as Bool:
            return .bool(bool)
        case let int as Int:
            return .int(int)
        case let double as Double:
            return .double(double)
        case let string as String:
            return .string(string)
        case let array as [Any]:
            let converted = array.compactMap { ArgumentValue.from($0) }
            return .array(converted)
        case let dict as [String: Any]:
            var converted: [String: ArgumentValue] = [:]
            for (key, val) in dict {
                if let argVal = ArgumentValue.from(val) {
                    converted[key] = argVal
                }
            }
            return .dictionary(converted)
        default:
            return nil
        }
    }
}

// MARK: - ArgumentValue Codable

extension ArgumentValue: Codable {
    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        
        if container.decodeNil() {
            self = .null
        } else if let bool = try? container.decode(Bool.self) {
            self = .bool(bool)
        } else if let int = try? container.decode(Int.self) {
            self = .int(int)
        } else if let double = try? container.decode(Double.self) {
            self = .double(double)
        } else if let string = try? container.decode(String.self) {
            self = .string(string)
        } else if let array = try? container.decode([ArgumentValue].self) {
            self = .array(array)
        } else if let dict = try? container.decode([String: ArgumentValue].self) {
            self = .dictionary(dict)
        } else {
            throw DecodingError.dataCorruptedError(
                in: container,
                debugDescription: "Unable to decode ArgumentValue"
            )
        }
    }
    
    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        
        switch self {
        case .null:
            try container.encodeNil()
        case .bool(let b):
            try container.encode(b)
        case .int(let i):
            try container.encode(i)
        case .double(let d):
            try container.encode(d)
        case .string(let s):
            try container.encode(s)
        case .array(let arr):
            try container.encode(arr)
        case .dictionary(let dict):
            try container.encode(dict)
        }
    }
}

// MARK: - ArgumentValue ExpressibleBy Literals

extension ArgumentValue: ExpressibleByStringLiteral {
    init(stringLiteral value: String) {
        self = .string(value)
    }
}

extension ArgumentValue: ExpressibleByIntegerLiteral {
    init(integerLiteral value: Int) {
        self = .int(value)
    }
}

extension ArgumentValue: ExpressibleByFloatLiteral {
    init(floatLiteral value: Double) {
        self = .double(value)
    }
}

extension ArgumentValue: ExpressibleByBooleanLiteral {
    init(booleanLiteral value: Bool) {
        self = .bool(value)
    }
}

extension ArgumentValue: ExpressibleByNilLiteral {
    init(nilLiteral: ()) {
        self = .null
    }
}

extension ArgumentValue: ExpressibleByArrayLiteral {
    init(arrayLiteral elements: ArgumentValue...) {
        self = .array(elements)
    }
}

extension ArgumentValue: ExpressibleByDictionaryLiteral {
    init(dictionaryLiteral elements: (String, ArgumentValue)...) {
        var dict: [String: ArgumentValue] = [:]
        for (key, value) in elements {
            dict[key] = value
        }
        self = .dictionary(dict)
    }
}
