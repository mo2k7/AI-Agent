import Foundation
import Testing
@testable import AIAgentApp

@Test
@MainActor
func streamingRenderCoordinatorCoalescesRapidUpdatesIntoSingleFlush() async {
    let coordinator = StreamingRenderCoordinator(
        frameIntervalNanoseconds: 5_000_000,
        heavyFrameIntervalNanoseconds: 10_000_000,
        saturatedFrameIntervalNanoseconds: 15_000_000
    )
    var applied: [(delta: String, finalText: String?, done: Bool)] = []
    let rowID = UUID()

    await coordinator.enqueue(
        rowID: rowID,
        delta: "Hel",
        finalText: nil,
        isDone: false
    ) { delta, finalText, done in
        applied.append((delta, finalText, done))
    }
    await coordinator.enqueue(
        rowID: rowID,
        delta: "lo",
        finalText: nil,
        isDone: false
    ) { delta, finalText, done in
        applied.append((delta, finalText, done))
    }

    try? await Task.sleep(nanoseconds: 40_000_000)

    #expect(applied.count == 1)
    #expect(applied.first?.delta == "Hello")
    #expect(applied.first?.finalText == nil)
    #expect(applied.first?.done == false)
}

@Test
@MainActor
func streamingRenderCoordinatorCancelAllDropsPendingFlush() async {
    let coordinator = StreamingRenderCoordinator(
        frameIntervalNanoseconds: 20_000_000,
        heavyFrameIntervalNanoseconds: 25_000_000,
        saturatedFrameIntervalNanoseconds: 30_000_000
    )
    var applyCount = 0

    await coordinator.enqueue(
        rowID: UUID(),
        delta: "partial",
        finalText: nil,
        isDone: false
    ) { _, _, _ in
        applyCount += 1
    }

    await coordinator.cancelAll()
    try? await Task.sleep(nanoseconds: 60_000_000)

    #expect(applyCount == 0)
}
