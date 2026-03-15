#if !os(macOS)
import SwiftUI

@MainActor
final class FloatingPanelController {
    static let shared = FloatingPanelController()
    private(set) var isVisible = true
    private init() {}
    func setup(appState: AppState) {}
    func show() { isVisible = true }
    func hide() { isVisible = false }
    func toggle() { isVisible.toggle() }
    func applyAppearancePreferences(opacity: Double, animationsEnabled: Bool) {}
}
#endif
