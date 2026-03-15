//
//  MacOSGeminiService.swift
//  AIAgentUI
//
//  macOS implementation of GeminiServiceProtocol.
//  Thin adapter that wraps IPCClient's callback-based API
//  into AsyncThrowingStream<StreamEvent>.
//

#if os(macOS)

import Foundation

@MainActor
final class MacOSGeminiService: GeminiServiceProtocol {

    // MARK: - Properties

    private let ipcClient: IPCClient
    private var activeContinuation: AsyncThrowingStream<StreamEvent, Error>.Continuation?
    private var activeRequestId: String?

    var isReady: Bool {
        ipcClient.isConnected
    }

    // MARK: - Init

    init(ipcClient: IPCClient) {
        self.ipcClient = ipcClient
    }

    // MARK: - GeminiServiceProtocol

    func sendPrompt(_ config: PromptConfiguration) -> AsyncThrowingStream<StreamEvent, Error> {
        // Tear down any prior stream.
        activeContinuation?.finish()
        activeContinuation = nil
        activeRequestId = nil

        return AsyncThrowingStream { continuation in
            self.activeContinuation = continuation

            // Wire IPCClient callbacks → stream events.
            self.installCallbacks(continuation: continuation)

            Task { @MainActor in
                let requestId = await self.ipcClient.send(
                    prompt: config.text,
                    model: config.model,
                    sessionId: config.sessionId,
                    memoryMode: config.memoryMode,
                    executionMode: config.executionMode,
                    inputPaths: config.inputPaths,
                    verbosity: config.verbosity,
                    presentationStyle: config.presentationStyle,
                    streamingAnimation: config.streamingAnimation,
                    browseProfile: config.browseProfile,
                    deepThink: config.deepThink,
                    correlationId: config.correlationId
                )

                if let requestId {
                    self.activeRequestId = requestId
                } else {
                    continuation.yield(.error("Prompt was not sent to backend"))
                    continuation.finish()
                    self.activeContinuation = nil
                }
            }
        }
    }

    func submitToolResult(requestId: String, name: String, result: [String: Any]) async throws {
        // On macOS, tools are executed by the Python backend.
        // The Swift side only confirms/rejects tool execution via tool.confirm.
        try await ipcClient.confirmCurrentToolExecution(approved: true)
    }

    func cancelCurrentRequest() async {
        await ipcClient.cancel()
    }

    // MARK: - Callback Wiring

    private func installCallbacks(continuation: AsyncThrowingStream<StreamEvent, Error>.Continuation) {
        ipcClient.onStreamUpdate = { [weak self] delta, _, isDone in
            guard self?.activeContinuation != nil else { return }
            continuation.yield(.text(delta))
        }

        ipcClient.onToolCall = { [weak self] toolCall in
            guard self?.activeContinuation != nil else { return }
            // Convert ArgumentValue → AnySendable for the protocol type.
            var args: [String: AnySendable] = [:]
            for (key, value) in toolCall.arguments {
                args[key] = AnySendable(value.rawValue)
            }
            let statusStr: String? = {
                switch toolCall.status {
                case .pending: return "pending"
                case .executing: return "executing"
                case .success: return "success"
                case .failed: return "failed"
                }
            }()
            let event = ToolCallEvent(
                name: toolCall.name,
                id: toolCall.id.uuidString,
                arguments: args,
                status: statusStr,
                result: toolCall.result,
                error: toolCall.error
            )
            continuation.yield(.toolCall(event))
        }

        ipcClient.onComplete = { [weak self] finalContent in
            guard let self, self.activeContinuation != nil else { return }
            continuation.yield(.complete(content: finalContent))
            continuation.finish()
            self.activeContinuation = nil
            self.activeRequestId = nil
        }

        ipcClient.onError = { [weak self] message in
            guard let self, self.activeContinuation != nil else { return }
            continuation.yield(.error(message))
            continuation.finish()
            self.activeContinuation = nil
            self.activeRequestId = nil
        }

        ipcClient.onCancelled = { [weak self] in
            guard let self, self.activeContinuation != nil else { return }
            continuation.yield(.cancelled)
            continuation.finish()
            self.activeContinuation = nil
            self.activeRequestId = nil
        }

        ipcClient.onStatusChange = { [weak self] status, detail in
            guard self?.activeContinuation != nil else { return }
            continuation.yield(.statusUpdate(status: status.shortText, detail: detail))
        }
    }

}

#endif
