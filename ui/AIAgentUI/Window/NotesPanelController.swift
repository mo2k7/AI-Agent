#if os(macOS)
//
//  NotesPanelController.swift
//  AIAgentUI
//
//  Created for Personal macOS AI Agent
//  Status: Active - Floating NSPanel for session notes
//

import Foundation
import AppKit
import SwiftUI

/// Manages the separate floating notes panel window.
///
/// Follows the same singleton + NSPanel pattern as `FloatingPanelController`,
/// but for the dedicated notes view. The panel can be shown/hidden independently
/// and persists its position separately via UserDefaults.
@MainActor
final class NotesPanelController: NSObject {

    // MARK: - Singleton

    static let shared = NotesPanelController()

    // MARK: - Properties

    private var panel: NSPanel?
    private var hostingView: NSHostingView<AnyView>?
    private(set) var isVisible: Bool = false

    private static let positionKey = "notesPanelPosition"
    private static let defaultWidth: CGFloat = 340
    private static let defaultHeight: CGFloat = 520
    private static let minWidth: CGFloat = 280
    private static let minHeight: CGFloat = 300

    // MARK: - Initialization

    private override init() {
        super.init()
    }

    // MARK: - Setup

    /// Sets up the notes panel with the SwiftUI content view.
    func setup(appState: AppState) {
        if panel == nil { createPanel() }
        let contentView = NotesPanelView(appState: appState)
        let hostingView = NSHostingView(rootView: AnyView(contentView))
        self.hostingView = hostingView
        panel?.contentView = hostingView
        positionPanel()
    }

    // MARK: - Panel Creation

    private func createPanel() {
        let panel = NSPanel(
            contentRect: NSRect(
                x: 0, y: 0,
                width: Self.defaultWidth,
                height: Self.defaultHeight
            ),
            styleMask: [.titled, .closable, .resizable, .fullSizeContentView],
            backing: .buffered,
            defer: false
        )

        panel.title = "Notes"
        panel.titleVisibility = .hidden
        panel.titlebarAppearsTransparent = true
        panel.isMovableByWindowBackground = true
        panel.level = .floating
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = true
        panel.hidesOnDeactivate = false
        panel.isFloatingPanel = true
        panel.alphaValue = 0.95
        panel.becomesKeyOnlyIfNeeded = false

        panel.minSize = NSSize(width: Self.minWidth, height: Self.minHeight)
        if let screenSize = NSScreen.main?.visibleFrame.size {
            panel.maxSize = screenSize
        }

        panel.delegate = self
        self.panel = panel
    }

    private func positionPanel() {
        guard let panel else { return }
        guard let screen = NSScreen.main?.visibleFrame else { return }

        // Try to restore saved position
        if let frameString = UserDefaults.standard.string(forKey: Self.positionKey) {
            let frame = NSRectFromString(frameString)
            if frame.width > 0, frame.height > 0, screen.intersects(frame) {
                panel.setFrame(frame, display: false)
                return
            }
        }

        // Default: right side of screen, vertically centered
        let x = screen.maxX - Self.defaultWidth - 20
        let y = screen.midY - Self.defaultHeight / 2
        panel.setFrameOrigin(NSPoint(x: x, y: y))
    }

    private func savePosition() {
        guard let panel else { return }
        let frameString = NSStringFromRect(panel.frame)
        UserDefaults.standard.set(frameString, forKey: Self.positionKey)
    }

    // MARK: - Visibility

    func show() {
        guard let panel else { return }
        if !isVisible {
            let finalFrame = panel.frame
            let startScale: CGFloat = 0.98
            let startW = finalFrame.width * startScale
            let startH = finalFrame.height * startScale
            let startX = finalFrame.origin.x + (finalFrame.width - startW) / 2
            let startY = finalFrame.origin.y + (finalFrame.height - startH) / 2 - 10
            let startFrame = NSRect(x: startX, y: startY, width: startW, height: startH)

            NSApp.activate(ignoringOtherApps: true)
            panel.alphaValue = 0
            panel.setFrame(startFrame, display: false)
            panel.orderFrontRegardless()
            panel.makeKeyAndOrderFront(nil)

            NSAnimationContext.runAnimationGroup { context in
                context.duration = 0.25
                context.timingFunction = CAMediaTimingFunction(controlPoints: 0.16, 1, 0.3, 1)
                panel.animator().alphaValue = 0.95
                panel.animator().setFrame(finalFrame, display: true)
            }
        }
        isVisible = true
    }

    func hide() {
        guard let panel, isVisible else { return }
        let originalFrame = panel.frame
        let targetScale: CGFloat = 0.98
        let targetW = originalFrame.width * targetScale
        let targetH = originalFrame.height * targetScale
        let targetX = originalFrame.origin.x + (originalFrame.width - targetW) / 2
        let targetY = originalFrame.origin.y + (originalFrame.height - targetH) / 2 - 10
        let targetFrame = NSRect(x: targetX, y: targetY, width: targetW, height: targetH)

        NSAnimationContext.runAnimationGroup({ context in
            context.duration = 0.2
            context.timingFunction = CAMediaTimingFunction(controlPoints: 0.16, 1, 0.3, 1)
            panel.animator().alphaValue = 0
            panel.animator().setFrame(targetFrame, display: true)
        }, completionHandler: { [panel, originalFrame] in
            Task { @MainActor in
                panel.setFrame(originalFrame, display: false)
                panel.orderOut(nil)
            }
        })
        isVisible = false
    }

    func toggle() {
        if isVisible {
            hide()
        } else {
            show()
        }
        Task { @MainActor in
            AppState.shared.isNotesPanelVisible = isVisible
        }
    }
}

// MARK: - NSWindowDelegate

extension NotesPanelController: NSWindowDelegate {
    func windowDidMove(_ notification: Notification) {
        savePosition()
    }

    func windowDidEndLiveResize(_ notification: Notification) {
        savePosition()
    }

    func windowWillClose(_ notification: Notification) {
        isVisible = false
        Task { @MainActor in
            AppState.shared.isNotesPanelVisible = false
        }
    }
}
#endif
