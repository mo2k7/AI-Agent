//
//  StreamingParser.swift
//  AIAgentUI
//
//  Created for Personal macOS AI Agent
//  Status: Active - Incremental response parser
//

import Foundation

/// Parses streaming data from the WebSocket transport
/// Handles buffering and JSON line separation
final class StreamingParser: @unchecked Sendable {
    
    /// Buffer for incomplete JSON lines
    private var buffer = Data()

    /// Maximum number of bytes retained in the incremental buffer
    private let maxBufferBytes: Int
    
    /// Line delimiter used in the protocol
    private let delimiter: UInt8 = 0x0A
    
    /// Closure called for each complete message parsed
    var onMessageReceived: ((IPCParsedMessage) -> Void)?
    
    /// Closure called when an error occurs during parsing
    var onError: ((StreamingParserError) -> Void)?

    init(maxBufferBytes: Int = 1_048_576) {
        self.maxBufferBytes = max(1, maxBufferBytes)
    }
    
    /// Resets the parser state
    func reset() {
        buffer.removeAll(keepingCapacity: false)
    }
    
    /// Processes incoming data chunks
    /// - Parameter data: Raw data received from the socket
    func processData(_ data: Data) {
        guard !data.isEmpty else { return }

        // Reject oversized chunks immediately and reset to recover.
        guard data.count <= maxBufferBytes else {
            onError?(.bufferOverflow)
            reset()
            return
        }

        // Drop incomplete buffered data when combined size exceeds the bound.
        if buffer.count + data.count > maxBufferBytes {
            onError?(.bufferOverflow)
            reset()
        }

        buffer.append(data)
        
        // Split buffer into lines by newline byte
        while let delimiterIndex = buffer.firstIndex(of: delimiter) {
            let lineData = buffer[..<delimiterIndex]
            buffer.removeSubrange(buffer.startIndex...delimiterIndex)
            
            processLine(lineData)
        }
    }
    
    /// Processes incoming string data
    /// - Parameter string: String data to process
    func processString(_ string: String) {
        guard let data = string.data(using: .utf8) else {
            onError?(.invalidEncoding)
            return
        }
        processData(data)
    }
    
    /// Processes a complete JSON line
    /// - Parameter line: A complete JSON string
    private func processLine(_ lineData: Data) {
        guard let line = String(data: lineData, encoding: .utf8) else {
            onError?(.invalidEncoding)
            return
        }
        // Skip empty lines
        guard !line.trimmingCharacters(in: .whitespaces).isEmpty else {
            return
        }
        
        // Parse the JSON message
        switch IPCMessageParser.parse(line) {
        case .success(let message):
            onMessageReceived?(message)
        case .failure(let error):
            onError?(.protocolError(error.localizedDescription))
        }
    }
}

// MARK: - Errors

enum StreamingParserError: Error, LocalizedError {
    case invalidEncoding
    case invalidJSON(String)
    case bufferOverflow
    case protocolError(String)
    
    var errorDescription: String? {
        switch self {
        case .invalidEncoding:
            return "Failed to decode data as UTF-8"
        case .invalidJSON(let line):
            return "Invalid JSON received: \(line.prefix(100))..."
        case .bufferOverflow:
            return "Buffer overflow - message too large"
        case .protocolError(let reason):
            return "IPC protocol parse failed: \(reason)"
        }
    }
}

// MARK: - Stream Accumulator

/// Accumulates streaming text chunks for display
final class StreamAccumulator {
    
    /// Current accumulated text
    private(set) var text: String = ""
    
    /// Request ID this accumulator is tracking
    let requestId: String
    
    /// Whether the stream has completed
    private(set) var isComplete: Bool = false
    
    /// Closure called when text is updated
    var onTextUpdate: ((String) -> Void)?
    
    /// Closure called when streaming is complete
    var onComplete: ((String) -> Void)?
    
    init(requestId: String) {
        self.requestId = requestId
    }
    
    /// Appends a delta chunk to the accumulated text
    /// - Parameters:
    ///   - delta: The new text chunk to append
    ///   - done: Whether this is the final chunk
    func append(delta: String, done: Bool) {
        text.append(delta)
        onTextUpdate?(text)
        
        if done {
            isComplete = true
            onComplete?(text)
        }
    }
    
    /// Resets the accumulator
    func reset() {
        text = ""
        isComplete = false
    }
}

// MARK: - Message Dispatcher

/// Dispatches parsed messages to appropriate handlers
final class MessageDispatcher {
    
    /// Stream accumulators keyed by request ID
    private var accumulators: [String: StreamAccumulator] = [:]
    
    /// Handler for status updates
    var onStatusUpdate: ((AgentStatus, String, String?) -> Void)?
    
    /// Handler for streaming text updates
    var onStreamingUpdate: ((String, String, String, Bool) -> Void)? // requestId, delta, text, isDone
    
    /// Handler for tool call updates
    var onToolCall: ((ToolCall, String) -> Void)? // toolCall, requestId
    
    /// Handler for completion
    var onComplete: ((String, String?) -> Void)? // requestId, finalContent
    
    /// Handler for errors
    var onError: ((String, String, Int?, [String: Any]?) -> Void)? // requestId, message, code, data
    
    /// Handler for system messages (version, reload, etc.)
    var onSystemMessage: ((SystemResponse, String) -> Void)? // response, requestId
    
    /// Dispatches a parsed message to the appropriate handler
    /// - Parameter message: The parsed IPC message
    func dispatch(_ message: IPCParsedMessage) {
        switch message {
        case .status(let response):
            let status = response.toAgentStatus()
            onStatusUpdate?(status, response.id, response.detail)
            
        case .stream(let response):
            handleStream(response)
            
        case .toolCall(let response):
            do {
                let toolCall = try response.toToolCall()
                onToolCall?(toolCall, response.id)
            } catch {
                onError?(response.id, error.localizedDescription, nil, nil)
            }
            
        case .result(let response):
            handleResult(response)
            
        case .error(let response):
            handleError(response)
            
        case .system(let response):
            onSystemMessage?(response, response.id)
        }
    }
    
    /// Creates or retrieves an accumulator for a request
    func getAccumulator(for requestId: String) -> StreamAccumulator {
        if let existing = accumulators[requestId] {
            return existing
        }
        let accumulator = StreamAccumulator(requestId: requestId)
        accumulators[requestId] = accumulator
        return accumulator
    }
    
    /// Removes an accumulator for a request
    func removeAccumulator(for requestId: String) {
        accumulators.removeValue(forKey: requestId)
    }
    
    /// Clears all accumulators
    func clearAll() {
        accumulators.removeAll()
    }
    
    // MARK: - Private Handlers
    
    private func handleStream(_ response: StreamResponse) {
        if response.delta.isEmpty && !response.done {
            return
        }
        let accumulator = getAccumulator(for: response.id)
        accumulator.append(delta: response.delta, done: response.done)
        onStreamingUpdate?(response.id, response.delta, accumulator.text, response.done)
        
        if response.done {
            removeAccumulator(for: response.id)
        }
    }
    
    private func handleResult(_ response: ResultResponse) {
        if let error = response.error {
            let payload = error.data?.mapValues { $0.value }
            onError?(response.id, error.message, error.code, payload)
        } else if let result = response.result {
            onComplete?(response.id, result.content)
        }
        removeAccumulator(for: response.id)
    }
    
    private func handleError(_ response: ResultResponse) {
        let message = response.error?.message ?? "Unknown error"
        let code = response.error?.code
        let payload = response.error?.data?.mapValues { $0.value }
        onError?(response.id, message, code, payload)
        removeAccumulator(for: response.id)
    }
}
