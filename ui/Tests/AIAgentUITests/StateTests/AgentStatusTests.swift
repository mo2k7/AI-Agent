import Foundation
import Testing
@testable import AIAgentApp

@Test
func agentStatusMapsCallingToolAndErrorDetails() {
    let calling = AgentStatus.from(rawStatus: "calling_tool", detail: "search_files")
    let error = AgentStatus.from(rawStatus: "error", detail: "boom")
    let planning = AgentStatus.from(rawStatus: "planning", detail: "Building")
    let awaiting = AgentStatus.from(rawStatus: "awaiting_approval", detail: "Awaiting approval")

    #expect(calling == .callingTool(toolName: "search_files"))
    #expect(error == .error(message: "boom"))
    #expect(planning == .planning)
    #expect(awaiting == .awaitingApproval(detail: "Awaiting approval"))
    #expect(calling.toolName == "search_files")
    #expect(error.errorMessage == "boom")
}

@Test
func agentStatusBusyAndSubmitFlags() {
    #expect(AgentStatus.connecting.isBusy)
    #expect(AgentStatus.streaming.isBusy)
    #expect(AgentStatus.planning.isBusy)
    #expect(AgentStatus.awaitingApproval(detail: "").isBusy)
    #expect(AgentStatus.idle.isBusy == false)

    #expect(AgentStatus.connecting.canSubmit == false)
    #expect(AgentStatus.thinking.canSubmit == false)
    #expect(AgentStatus.executingPlan(detail: "").canSubmit == false)
    #expect(AgentStatus.complete.canSubmit)
    #expect(AgentStatus.error(message: "x").canSubmit)
}

@Test
func agentStatusCodableRoundTripForStructuredStatuses() throws {
    let values: [AgentStatus] = [
        .idle,
        .planning,
        .planReady(detail: "Plan 1"),
        .awaitingApproval(detail: "Approve"),
        .executingPlan(detail: "Executing"),
        .callingTool(toolName: "open_item"),
        .error(message: "Request cancelled by user"),
        .complete,
    ]

    let encoded = try JSONEncoder().encode(values)
    let decoded = try JSONDecoder().decode([AgentStatus].self, from: encoded)

    #expect(decoded == values)
}
