import Foundation
import Testing
@testable import AIAgentApp

@Test
func executionModeDisplayNamesAreStable() {
    #expect(ExecutionMode.direct.displayName == "Direct")
    #expect(ExecutionMode.plan.displayName == "Plan")
    #expect(ExecutionMode.teacher.displayName == "Teacher")
    #expect(ExecutionMode.direct.badgeText == "DIRECT")
    #expect(ExecutionMode.plan.badgeText == "PLAN")
    #expect(ExecutionMode.teacher.badgeText == "TEACHER")
}

@Test
func normalizeDroppedFilePathsDeduplicatesAndKeepsFileURLs() {
    let first = URL(fileURLWithPath: "/tmp/demo-a.txt")
    let duplicate = URL(fileURLWithPath: "/tmp/demo-a.txt")
    let second = URL(fileURLWithPath: "/tmp/demo-b.txt")
    let remote = URL(string: "https://example.com/file.txt")!

    let normalized = AppState.normalizeDroppedFilePaths(
        urls: [first, duplicate, second, remote]
    )

    #expect(normalized == ["/tmp/demo-a.txt", "/tmp/demo-b.txt"])
}
