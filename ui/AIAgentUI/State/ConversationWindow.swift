import Foundation
import SwiftUI

@MainActor
final class MessageRowModel: ObservableObject, Identifiable {
    let id: UUID
    let backendMessageId: String?
    let role: MessageRole
    let timestamp: Date
    let turnIndex: Int?

    @Published var content: String
    @Published var toolCall: ToolCall?
    @Published var isStreaming: Bool

    init(
        id: UUID = UUID(),
        backendMessageId: String? = nil,
        role: MessageRole,
        content: String,
        timestamp: Date = Date(),
        turnIndex: Int? = nil,
        toolCall: ToolCall? = nil,
        isStreaming: Bool = false
    ) {
        self.id = id
        self.backendMessageId = backendMessageId
        self.role = role
        self.content = content
        self.timestamp = timestamp
        self.turnIndex = turnIndex
        self.toolCall = toolCall
        self.isStreaming = isStreaming
    }

    convenience init(message: Message, backendMessageId: String? = nil, turnIndex: Int? = nil) {
        let resolvedID: UUID
        if let backendMessageId,
           let parsed = UUID(uuidString: backendMessageId) {
            resolvedID = parsed
        } else {
            resolvedID = message.id
        }
        self.init(
            id: resolvedID,
            backendMessageId: backendMessageId,
            role: message.role,
            content: message.content,
            timestamp: message.timestamp,
            turnIndex: turnIndex,
            toolCall: message.toolCall,
            isStreaming: message.isStreaming
        )
    }

    func snapshot() -> Message {
        Message(
            id: id,
            role: role,
            content: content,
            timestamp: timestamp,
            toolCall: toolCall,
            isStreaming: isStreaming
        )
    }

    func replaceContent(_ text: String) {
        guard content != text else { return }
        content = text
    }

    func appendContent(_ delta: String) {
        guard !delta.isEmpty else { return }
        content.append(delta)
    }
}

actor StreamingRenderCoordinator {
    private let baseFrameIntervalNanoseconds: UInt64
    private let heavyFrameIntervalNanoseconds: UInt64
    private let saturatedFrameIntervalNanoseconds: UInt64
    private let heavyPendingCharacterThreshold: Int
    private let saturatedPendingCharacterThreshold: Int
    private var pendingByRowID: [UUID: PendingUpdate] = [:]
    private var flushTask: Task<Void, Never>?
    private var scheduledFlushIntervalNanoseconds: UInt64?

    private struct PendingUpdate {
        var delta: String = ""
        var finalText: String?
        var isDone: Bool = false
        let apply: @MainActor (String, String?, Bool) -> Void
    }

    init(
        frameIntervalNanoseconds: UInt64 = 33_000_000,
        heavyFrameIntervalNanoseconds: UInt64 = 66_000_000,
        saturatedFrameIntervalNanoseconds: UInt64 = 100_000_000,
        heavyPendingCharacterThreshold: Int = 1_200,
        saturatedPendingCharacterThreshold: Int = 4_000
    ) {
        self.baseFrameIntervalNanoseconds = frameIntervalNanoseconds
        self.heavyFrameIntervalNanoseconds = max(frameIntervalNanoseconds, heavyFrameIntervalNanoseconds)
        self.saturatedFrameIntervalNanoseconds = max(heavyFrameIntervalNanoseconds, saturatedFrameIntervalNanoseconds)
        self.heavyPendingCharacterThreshold = max(1, heavyPendingCharacterThreshold)
        self.saturatedPendingCharacterThreshold = max(
            self.heavyPendingCharacterThreshold + 1,
            saturatedPendingCharacterThreshold
        )
    }

    func enqueue(
        rowID: UUID,
        delta: String,
        finalText: String?,
        isDone: Bool,
        apply: @escaping @MainActor (String, String?, Bool) -> Void
    ) {
        var pending = pendingByRowID[rowID] ?? PendingUpdate(apply: apply)
        pending.delta.append(delta)
        if let finalText {
            pending.finalText = finalText
        }
        pending.isDone = pending.isDone || isDone
        pendingByRowID[rowID] = pending

        let desiredInterval = flushIntervalNanoseconds()
        if flushTask == nil || desiredInterval < (scheduledFlushIntervalNanoseconds ?? desiredInterval) {
            flushTask?.cancel()
            scheduleFlush(after: desiredInterval)
        }
    }

    func cancelAll() {
        flushTask?.cancel()
        flushTask = nil
        scheduledFlushIntervalNanoseconds = nil
        pendingByRowID.removeAll()
    }

    private func scheduleFlush(after intervalNanoseconds: UInt64) {
        scheduledFlushIntervalNanoseconds = intervalNanoseconds
        flushTask = Task {
            if intervalNanoseconds > 0 {
                try? await Task.sleep(nanoseconds: intervalNanoseconds)
            }
            await flushPending()
        }
    }

    private func flushIntervalNanoseconds() -> UInt64 {
        if pendingByRowID.values.contains(where: \.isDone) {
            return 0
        }

        let pendingCharacters = pendingByRowID.values.reduce(into: 0) { partialResult, pending in
            partialResult += pending.delta.count
            partialResult += pending.finalText?.count ?? 0
        }

        if pendingCharacters >= saturatedPendingCharacterThreshold {
            return saturatedFrameIntervalNanoseconds
        }
        if pendingCharacters >= heavyPendingCharacterThreshold {
            return heavyFrameIntervalNanoseconds
        }
        return baseFrameIntervalNanoseconds
    }

    private func flushPending() async {
        let pendingValues = pendingByRowID.values
        pendingByRowID.removeAll()
        flushTask = nil
        scheduledFlushIntervalNanoseconds = nil

        for pending in pendingValues {
            await pending.apply(pending.delta, pending.finalText, pending.isDone)
        }
    }
}
