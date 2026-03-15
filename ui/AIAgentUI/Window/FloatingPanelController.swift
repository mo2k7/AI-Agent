#if os(macOS)
//
//  FloatingPanelController.swift
//  AIAgentUI
//
//  Created for Personal macOS AI Agent
//  Status: Active - NSPanel wrapper for floating behavior
//

import Foundation
import AppKit
import SwiftUI

/// Manages the floating panel window
@MainActor
final class FloatingPanelController: NSObject {
    
    // MARK: - Singleton
    
    static let shared = FloatingPanelController()
    
    // MARK: - Properties
    
    /// The floating panel window
    private var panel: FloatingPanel?
    
    /// The SwiftUI hosting view
    private var hostingView: NSHostingView<AnyView>?
    
    /// Whether the panel is currently visible
    private(set) var isVisible: Bool = false
    
    /// Position manager for edge snapping
    private let positionManager = PanelPositionManager.shared

    /// Drag end debounce work item
    private var dragEndWorkItem: DispatchWorkItem?

    /// Delay to detect drag end
    private let dragEndDelay: TimeInterval = 0.12

    /// Configured opacity for the visible panel
    private var panelOpacity: CGFloat = 0.95

    /// Whether window-level animations are enabled
    private var animationsEnabled: Bool = true
    
    // MARK: - Initialization
    
    private override init() {
        super.init()
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(screenParametersDidChange(_:)),
            name: NSApplication.didChangeScreenParametersNotification,
            object: nil
        )
    }

    deinit {
        NotificationCenter.default.removeObserver(self)
    }

    @objc private func screenParametersDidChange(_ notification: Notification) {
        guard let panel else { return }
        // Update maxSize to the screen the panel currently lives on.
        if let screenSize = (panel.screen ?? NSScreen.main)?.visibleFrame.size {
            panel.maxSize = screenSize
        }
        // Ensure the panel is still fully visible on the (possibly smaller) screen.
        guard let screen = (panel.screen ?? NSScreen.main)?.visibleFrame else { return }
        let constrained = EdgeSnapping.constrainToScreen(frame: panel.frame, screen: screen)
        if constrained != panel.frame {
            panel.setFrame(constrained, display: true)
            positionManager.savePosition(panel)
        }
    }
    
    // MARK: - Setup
    
    /// Sets up the panel with the main content view
    /// - Parameter appState: The app state to bind to
    func setup(appState: AppState) {
        // Create the panel if it doesn't exist
        if panel == nil {
            createPanel()
        }
        
        // Create the SwiftUI view
        let contentView = MainPanelView(appState: appState)
        let hostingView = NSHostingView(rootView: AnyView(contentView))
        self.hostingView = hostingView
        
        panel?.contentView = hostingView

        applyAppearancePreferences(
            opacity: Self.loadDoubleSetting(key: "panelOpacity", defaultValue: 0.95),
            animationsEnabled: Self.loadBoolSetting(key: "animationsEnabled", defaultValue: true)
        )
        
        // Position the panel
        positionPanel()
    }
    
    /// Creates the floating panel
    private func createPanel() {
        let panel = FloatingPanel(
            contentRect: NSRect(
                x: 0,
                y: 0,
                width: ThemeConstants.panelWidth,
                height: ThemeConstants.panelHeight
            ),
            // IMPORTANT: Remove .nonactivatingPanel to allow keyboard focus for text input
            // The .nonactivatingPanel style prevents text fields from receiving keyboard input
            // which causes the yellow "prohibited input" banner on macOS
            styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
            backing: .buffered,
            defer: false
        )
        
        // Configure panel properties
        panel.title = "AI Agent"
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
        panel.alphaValue = panelOpacity
        
        // Allow the panel to accept keyboard input even when not main
        panel.becomesKeyOnlyIfNeeded = false
        
        // Set size constraints
        panel.minSize = NSSize(
            width: ThemeConstants.panelMinWidth,
            height: ThemeConstants.panelMinHeight
        )
        // No maxSize — let the window resize freely up to the screen bounds,
        // matching native macOS app behavior.  Use the screen the panel is on
        // (falls back to main screen) so multi-monitor setups work correctly.
        if let screenSize = (panel.screen ?? NSScreen.main)?.visibleFrame.size {
            panel.maxSize = screenSize
        }
        
        // Set up delegate
        panel.delegate = self
        
        self.panel = panel
    }
    
    /// Positions the panel at its default or last known position
    private func positionPanel() {
        guard let panel = panel else { return }
        guard let screen = (panel.screen ?? NSScreen.main)?.visibleFrame else { return }

        if positionManager.restorePosition(panel) {
            return
        }

        let position = PanelPositionManager.defaultPosition(
            for: screen,
            panelSize: panel.frame.size
        )

        panel.setFrameOrigin(position)
    }
    
    // MARK: - Visibility
    
    /// Shows the panel with animation
    func show() {
        guard let panel = panel else { return }
        
        if !isVisible {
            let finalFrame = panel.frame
            let startFrame = scaledFrame(from: finalFrame, scale: 0.98, offsetY: -10)

            NSApp.activate(ignoringOtherApps: true)
            panel.alphaValue = 0
            panel.setFrame(startFrame, display: false)
            panel.orderFrontRegardless()
            panel.makeKeyAndOrderFront(nil)

            if showAnimationDuration > 0 {
                NSAnimationContext.runAnimationGroup { context in
                    context.duration = showAnimationDuration
                    context.timingFunction = AnimationConstants.appKitTimingFunction()
                    panel.animator().alphaValue = panelOpacity
                    panel.animator().setFrame(finalFrame, display: true)
                }
            } else {
                panel.alphaValue = panelOpacity
                panel.setFrame(finalFrame, display: true)
            }
        }
        
        isVisible = true
    }
    
    /// Hides the panel with animation
    func hide() {
        guard let panel = panel, isVisible else { return }
        dragEndWorkItem?.cancel()

        let originalFrame = panel.frame
        let targetFrame = scaledFrame(from: originalFrame, scale: 0.98, offsetY: -10)

        if hideAnimationDuration > 0 {
            NSAnimationContext.runAnimationGroup({ context in
                context.duration = hideAnimationDuration
                context.timingFunction = AnimationConstants.appKitTimingFunction()
                panel.animator().alphaValue = 0
                panel.animator().setFrame(targetFrame, display: true)
            }, completionHandler: { [panel] in
                Task { @MainActor in
                    panel.setFrame(originalFrame, display: false)
                    panel.orderOut(nil)
                }
            })
        } else {
            panel.alphaValue = 0
            panel.setFrame(originalFrame, display: false)
            panel.orderOut(nil)
        }
        
        isVisible = false
    }
    
    /// Toggles panel visibility
    func toggle() {
        if isVisible {
            hide()
        } else {
            show()
        }
        
        // Update app state on main actor
        Task { @MainActor in
            AppState.shared.isPanelVisible = isVisible
        }
    }
    
    // MARK: - Position Control
    
    /// Snaps the panel to a specific edge
    func snapTo(edge: EdgeSnapping.Edge) {
        guard let panel = panel else { return }
        positionManager.snapTo(panel: panel, edge: edge)
    }
    
    /// Centers the panel on screen
    func center() {
        guard let panel = panel else { return }
        panel.center()
        positionManager.restoreLastPosition(panel)
    }

    /// Applies panel opacity and animation preferences at runtime.
    func applyAppearancePreferences(opacity: Double, animationsEnabled: Bool) {
        self.panelOpacity = CGFloat(max(0.5, min(1.0, opacity)))
        self.animationsEnabled = animationsEnabled
        positionManager.animationsEnabled = animationsEnabled

        if let panel, isVisible {
            panel.alphaValue = panelOpacity
        }
    }
}

// MARK: - NSWindowDelegate

extension FloatingPanelController: NSWindowDelegate {
    
    func windowDidMove(_ notification: Notification) {
        guard let panel = panel else { return }
        positionManager.panelDidMove(panel)
        scheduleDragEnd()
    }
    
    func windowDidEndLiveResize(_ notification: Notification) {
        guard let panel = panel else { return }
        positionManager.panelResizeEnded(panel)
    }
    
    func windowWillClose(_ notification: Notification) {
        isVisible = false
        dragEndWorkItem?.cancel()
        Task { @MainActor in
            AppState.shared.isPanelVisible = false
        }
    }
}

// MARK: - Custom NSPanel

/// Custom NSPanel subclass with floating behavior
final class FloatingPanel: NSPanel {
    
    // MARK: - Overrides
    
    /// Allows the panel to become key without activating the app
    override var canBecomeKey: Bool {
        return true
    }
    
    /// Allows the panel to become main
    override var canBecomeMain: Bool {
        return true
    }
    
    /// Prevents the panel from hiding when the app deactivates
    override func resignMain() {
        super.resignMain()
        // Keep visible even when not main
    }
    
    /// Custom close behavior
    override func close() {
        // Hide instead of close to preserve state
        FloatingPanelController.shared.hide()
    }
    
    /// Handle key events
    override func keyDown(with event: NSEvent) {
        // Handle Escape to close
        if event.keyCode == 53 { // Escape key
            FloatingPanelController.shared.hide()
            return
        }
        
        super.keyDown(with: event)
    }
}

// MARK: - Window Accessor for SwiftUI

/// Provides access to the window for SwiftUI views
struct WindowAccessor: NSViewRepresentable {
    
    @Binding var window: NSWindow?
    
    func makeNSView(context: Context) -> NSView {
        let view = NSView()
        DispatchQueue.main.async {
            self.window = view.window
        }
        return view
    }
    
    func updateNSView(_ nsView: NSView, context: Context) {
        DispatchQueue.main.async {
            self.window = nsView.window
        }
    }
}

// MARK: - SwiftUI Panel Wrapper

/// A SwiftUI wrapper for presenting content in the floating panel
struct FloatingPanelPresenter<Content: View>: View {
    
    let content: Content
    @State private var window: NSWindow?
    
    init(@ViewBuilder content: () -> Content) {
        self.content = content()
    }
    
    var body: some View {
        content
            .background(WindowAccessor(window: $window))
    }
}

// MARK: - Animation Helpers

private extension FloatingPanelController {
    static func loadBoolSetting(key: String, defaultValue: Bool) -> Bool {
        let defaults = UserDefaults.standard
        guard defaults.object(forKey: key) != nil else { return defaultValue }
        return defaults.bool(forKey: key)
    }

    static func loadDoubleSetting(key: String, defaultValue: Double) -> Double {
        let defaults = UserDefaults.standard
        guard defaults.object(forKey: key) != nil else { return defaultValue }
        return defaults.double(forKey: key)
    }

    var showAnimationDuration: TimeInterval {
        animationsEnabled ? 0.25 : 0
    }

    var hideAnimationDuration: TimeInterval {
        animationsEnabled ? 0.2 : 0
    }

    func scaledFrame(from frame: NSRect, scale: CGFloat, offsetY: CGFloat) -> NSRect {
        let scaledWidth = frame.width * scale
        let scaledHeight = frame.height * scale
        let x = frame.origin.x + (frame.width - scaledWidth) / 2
        let y = frame.origin.y + (frame.height - scaledHeight) / 2 + offsetY
        return NSRect(x: x, y: y, width: scaledWidth, height: scaledHeight)
    }

    func scheduleDragEnd() {
        dragEndWorkItem?.cancel()
        let workItem = DispatchWorkItem { [weak self] in
            guard let self = self, let panel = self.panel else { return }
            guard NSEvent.pressedMouseButtons == 0 else {
                self.scheduleDragEnd()
                return
            }
            self.positionManager.panelDragEnded(panel)
        }
        dragEndWorkItem = workItem
        DispatchQueue.main.asyncAfter(deadline: .now() + dragEndDelay, execute: workItem)
    }
}
#endif
