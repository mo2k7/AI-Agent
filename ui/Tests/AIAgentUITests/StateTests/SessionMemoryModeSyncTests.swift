import Testing
@testable import AIAgentApp

@Test
func shouldApplyRemoteSessionMemoryModeWithoutPendingUpdate() {
    #expect(
        AppState.shouldApplyRemoteSessionMemoryMode(
            localMode: .ephemeral,
            remoteMode: .on,
            pendingDesiredMode: nil
        )
    )
}

@Test
func shouldNotApplyRemoteSessionMemoryModeWhenPendingDesiredDiffers() {
    #expect(
        AppState.shouldApplyRemoteSessionMemoryMode(
            localMode: .ephemeral,
            remoteMode: .on,
            pendingDesiredMode: .ephemeral
        ) == false
    )
}

@Test
func shouldApplyRemoteSessionMemoryModeWhenPendingDesiredMatchesRemote() {
    #expect(
        AppState.shouldApplyRemoteSessionMemoryMode(
            localMode: .off,
            remoteMode: .ephemeral,
            pendingDesiredMode: .ephemeral
        )
    )
}

@Test
func shouldSkipRemoteApplyWhenModesAlreadyMatch() {
    #expect(
        AppState.shouldApplyRemoteSessionMemoryMode(
            localMode: .on,
            remoteMode: .on,
            pendingDesiredMode: nil
        ) == false
    )
}
