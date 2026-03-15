#if !os(macOS)
import SwiftUI

@MainActor
final class NotesPanelController {
    static let shared = NotesPanelController()
    private(set) var isVisible = false
    private init() {}
    func setup(appState: AppState) {}
    func show() { isVisible = true }
    func hide() { isVisible = false }
    func toggle() { isVisible.toggle() }
}
#endif
