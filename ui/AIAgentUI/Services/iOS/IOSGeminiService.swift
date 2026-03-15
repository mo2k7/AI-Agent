//
//  IOSGeminiService.swift
//  AIAgentUI
//
//  iOS implementation of GeminiServiceProtocol.
//  Calls the Gemini REST API directly via URLSession with SSE streaming.
//  Handles the multi-turn function calling loop natively.
//

#if os(iOS)

import Foundation

/// Sendable wrapper for tool result data passed across concurrency boundaries.
/// Safe because all access is gated on @MainActor.
private struct ToolResultPayload: @unchecked Sendable {
    let name: String
    let result: [String: Any]
}

@MainActor
final class IOSGeminiService: GeminiServiceProtocol {

    // MARK: - Properties

    private let baseURL = "https://generativelanguage.googleapis.com/v1beta"
    private var apiKey: String?
    private var activeTask: Task<Void, Never>?
    private var activeContinuation: AsyncThrowingStream<StreamEvent, Error>.Continuation?
    private var isCancelled = false

    /// Pending tool result continuations.
    /// When the model emits a `functionCall`, the stream suspends and
    /// waits for the caller to supply the tool result via `submitToolResult`.
    private var toolResultContinuation: CheckedContinuation<ToolResultPayload, Never>?

    var isReady: Bool {
        apiKey != nil && !(apiKey?.isEmpty ?? true)
    }

    // MARK: - Init

    init(apiKey: String? = nil) {
        self.apiKey = apiKey
    }

    /// Update the stored API key (e.g. after user enters it in Settings).
    func setAPIKey(_ key: String?) {
        apiKey = key?.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    // MARK: - GeminiServiceProtocol

    func sendPrompt(_ config: PromptConfiguration) -> AsyncThrowingStream<StreamEvent, Error> {
        // Cancel any prior request.
        activeTask?.cancel()
        activeContinuation?.finish()
        activeContinuation = nil
        toolResultContinuation = nil
        isCancelled = false

        return AsyncThrowingStream { continuation in
            self.activeContinuation = continuation

            self.activeTask = Task { @MainActor in
                do {
                    guard let key = self.apiKey, !key.isEmpty else {
                        throw GeminiServiceError.apiKeyMissing
                    }

                    try await self.executePromptLoop(
                        config: config,
                        apiKey: key,
                        continuation: continuation
                    )
                } catch is CancellationError {
                    continuation.yield(.cancelled)
                    continuation.finish()
                } catch {
                    continuation.yield(.error(error.localizedDescription))
                    continuation.finish()
                }

                self.activeContinuation = nil
                self.activeTask = nil
            }
        }
    }

    func submitToolResult(requestId: String, name: String, result: [String: Any]) async throws {
        toolResultContinuation?.resume(returning: ToolResultPayload(name: name, result: result))
        toolResultContinuation = nil
    }

    func cancelCurrentRequest() async {
        isCancelled = true
        activeTask?.cancel()
        toolResultContinuation?.resume(returning: ToolResultPayload(name: "", result: ["cancelled": true]))
        toolResultContinuation = nil
    }

    // MARK: - Core Streaming Loop

    /// Executes the full prompt → stream → function-call → continue loop.
    private func executePromptLoop(
        config: PromptConfiguration,
        apiKey: String,
        continuation: AsyncThrowingStream<StreamEvent, Error>.Continuation
    ) async throws {
        // Build initial contents from history + current prompt.
        var contents = buildContents(from: config)
        let tools = buildTools(from: config.tools)
        let systemInstruction = config.systemInstruction.map {
            GeminiContent(role: nil, parts: [GeminiPart(text: $0)])
        }

        var loopCount = 0
        let maxToolLoops = 10  // Safety limit to prevent infinite tool loops

        while loopCount < maxToolLoops {
            loopCount += 1
            try Task.checkCancellation()

            let request = GeminiRequest(
                contents: contents,
                tools: tools.isEmpty ? nil : [GeminiTool(functionDeclarations: tools)],
                systemInstruction: systemInstruction,
                generationConfig: GeminiGenerationConfig(
                    temperature: nil,
                    topP: nil,
                    topK: nil,
                    maxOutputTokens: 8192,
                    candidateCount: 1
                )
            )

            let (functionCalls, textAccumulated) = try await streamRequest(
                request: request,
                model: config.model,
                apiKey: apiKey,
                continuation: continuation
            )

            // If no function calls, we're done.
            if functionCalls.isEmpty {
                continuation.yield(.complete(content: textAccumulated.isEmpty ? nil : textAccumulated))
                return
            }

            // Model wants to call tools — append model's response and wait for results.
            let modelParts = functionCalls.map { call in
                GeminiPart(functionCall: call)
            }
            contents.append(GeminiContent(role: "model", parts: modelParts))

            // Execute each function call via the native tool executor.
            var responseParts: [GeminiPart] = []
            for call in functionCalls {
                try Task.checkCancellation()

                // Emit tool call event for UI.
                var args: [String: AnySendable] = [:]
                for (key, value) in call.args {
                    args[key] = AnySendable(value.anyValue)
                }
                let toolCallId = UUID().uuidString
                continuation.yield(.toolCall(ToolCallEvent(
                    name: call.name,
                    id: toolCallId,
                    arguments: args,
                    status: "executing",
                    result: nil,
                    error: nil
                )))

                // Execute the tool natively.
                var rawArgs: [String: Any] = [:]
                for (key, value) in call.args {
                    rawArgs[key] = value.anyValue
                }
                let toolResult = await IOSToolExecutor.shared.execute(
                    name: call.name,
                    arguments: rawArgs
                )

                guard !isCancelled else {
                    continuation.yield(.cancelled)
                    return
                }

                // Build function response.
                let responseValues = toolResult.mapValues { JSONValue.from($0) }
                responseParts.append(GeminiPart(
                    functionResponse: GeminiFunctionResponse(
                        name: call.name,
                        response: responseValues
                    )
                ))

                continuation.yield(.toolResult(
                    name: call.name,
                    content: String(describing: toolResult)
                ))
            }

            // Append function responses and loop back for the model to continue.
            contents.append(GeminiContent(role: "user", parts: responseParts))
        }

        // Exhausted tool loops.
        continuation.yield(.error("Exceeded maximum tool call iterations (\(maxToolLoops))"))
        continuation.yield(.complete(content: nil))
    }

    // MARK: - HTTP + SSE Streaming

    /// Streams a single `streamGenerateContent` request and collects text + function calls.
    private func streamRequest(
        request: GeminiRequest,
        model: String,
        apiKey: String,
        continuation: AsyncThrowingStream<StreamEvent, Error>.Continuation
    ) async throws -> (functionCalls: [GeminiFunctionCall], text: String) {
        let urlString = "\(baseURL)/models/\(model):streamGenerateContent?alt=sse&key=\(apiKey)"
        guard let url = URL(string: urlString) else {
            throw GeminiServiceError.invalidResponse("Invalid URL for model: \(model)")
        }

        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = "POST"
        urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let encoder = JSONEncoder()
        urlRequest.httpBody = try encoder.encode(request)

        let (bytes, response) = try await URLSession.shared.bytes(for: urlRequest)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw GeminiServiceError.invalidResponse("Non-HTTP response")
        }

        guard (200...299).contains(httpResponse.statusCode) else {
            // Try to read the error body.
            var errorBody = ""
            for try await line in bytes.lines {
                errorBody += line
                if errorBody.count > 2000 { break }
            }
            throw GeminiServiceError.httpError(
                statusCode: httpResponse.statusCode,
                message: errorBody.isEmpty ? "HTTP \(httpResponse.statusCode)" : errorBody
            )
        }

        var accumulatedText = ""
        var functionCalls: [GeminiFunctionCall] = []
        let decoder = JSONDecoder()

        for try await line in bytes.lines {
            try Task.checkCancellation()

            // SSE format: lines prefixed with "data: "
            let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
            guard trimmed.hasPrefix("data: ") else { continue }
            let jsonString = String(trimmed.dropFirst(6))
            guard !jsonString.isEmpty, jsonString != "[DONE]" else { continue }

            guard let jsonData = jsonString.data(using: .utf8) else { continue }

            let chunk: GeminiStreamChunk
            do {
                chunk = try decoder.decode(GeminiStreamChunk.self, from: jsonData)
            } catch {
                // Skip malformed chunks.
                continue
            }

            // Check for API-level errors.
            if let apiError = chunk.error {
                throw GeminiServiceError.httpError(
                    statusCode: apiError.code ?? 500,
                    message: apiError.message ?? "Unknown API error"
                )
            }

            guard let candidate = chunk.candidates?.first,
                  let content = candidate.content else {
                continue
            }

            for part in content.parts {
                if let text = part.text, !text.isEmpty {
                    accumulatedText += text
                    continuation.yield(.text(text))
                }
                if let fc = part.functionCall {
                    functionCalls.append(fc)
                }
            }

            // Check for finish reason.
            if let reason = candidate.finishReason {
                if reason == "SAFETY" {
                    throw GeminiServiceError.streamingError(
                        "Response blocked by safety filters"
                    )
                }
                // "STOP" or "MAX_TOKENS" — normal completion, handled by caller.
            }
        }

        return (functionCalls, accumulatedText)
    }

    // MARK: - Content Building

    /// Converts `PromptConfiguration` into the `contents` array for the API.
    private func buildContents(from config: PromptConfiguration) -> [GeminiContent] {
        var contents: [GeminiContent] = []

        // Add conversation history.
        for message in config.history {
            let role: String
            switch message.role {
            case .user: role = "user"
            case .model: role = "model"
            case .system: continue  // System goes in systemInstruction, not contents.
            }
            contents.append(GeminiContent(
                role: role,
                parts: [GeminiPart(text: message.content)]
            ))
        }

        // Add current prompt.
        contents.append(GeminiContent(
            role: "user",
            parts: [GeminiPart(text: config.text)]
        ))

        return contents
    }

    /// Converts `[ToolDeclaration]` to Gemini API function declarations.
    private func buildTools(from declarations: [ToolDeclaration]) -> [GeminiFunctionDeclaration] {
        declarations.map { decl in
            let properties = decl.parameters.properties.mapValues { prop in
                GeminiFunctionProperty(
                    type: prop.type,
                    description: prop.description,
                    enum: prop.enumValues,
                    items: prop.items.map { GeminiFunctionPropertyItems(type: $0.type) }
                )
            }
            return GeminiFunctionDeclaration(
                name: decl.name,
                description: decl.description,
                parameters: GeminiFunctionParameters(
                    type: "object",
                    properties: properties.isEmpty ? nil : properties,
                    required: decl.parameters.required.isEmpty ? nil : decl.parameters.required
                )
            )
        }
    }
}

#endif
