import Foundation
import Testing
@testable import AIAgentApp

@Test
func toolCallStatusBadgeTextMappingIsStable() {
    #expect(ToolCallStatus.pending.badgeText == "Queued")
    #expect(ToolCallStatus.executing.badgeText == "Running")
    #expect(ToolCallStatus.success.badgeText == "Success")
    #expect(ToolCallStatus.failed.badgeText == "Failed")
}

@Test
func toolCallMergeUpdatesLifecycleInPlace() {
    let base = ToolCall(
        id: UUID(uuidString: "AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE")!,
        name: "search_files",
        arguments: ["query": .string("*.swift")],
        status: .pending
    )

    let runningUpdate = ToolCall(
        id: UUID(uuidString: "11111111-2222-3333-4444-555555555555")!,
        name: "search_files",
        arguments: ["query": .string("*.swift")],
        status: .executing
    )

    let merged = base.merged(with: runningUpdate)

    #expect(merged.id == base.id)
    #expect(merged.status == .executing)
    #expect(merged.name == "search_files")
    #expect(merged.arguments == base.arguments)
}

@Test
func toolCallMergeCarriesForwardExistingResultWhenUpdateOmitsIt() {
    let base = ToolCall(
        name: "read_text",
        arguments: ["path": .string("/tmp/file.txt")],
        status: .executing,
        result: "cached-result"
    )

    let successUpdate = ToolCall(
        name: "read_text",
        arguments: ["path": .string("/tmp/file.txt")],
        status: .success,
        result: nil
    )

    let merged = base.merged(with: successUpdate)

    #expect(merged.status == .success)
    #expect(merged.result == "cached-result")
}

@Test
func toolCallMergeReplacesDifferentToolSignature() {
    let base = ToolCall(
        name: "search_files",
        arguments: ["query": .string("*.swift")],
        status: .executing
    )

    let unrelatedUpdate = ToolCall(
        name: "open_item",
        arguments: ["path": .string("/tmp/a.txt")],
        status: .pending
    )

    let merged = base.merged(with: unrelatedUpdate)

    #expect(merged == unrelatedUpdate)
}

@Test
func toolCallStatusCompletionFlagsRemainCorrect() {
    #expect(ToolCallStatus.pending.isComplete == false)
    #expect(ToolCallStatus.executing.isComplete == false)
    #expect(ToolCallStatus.success.isComplete)
    #expect(ToolCallStatus.failed.isComplete)
}
