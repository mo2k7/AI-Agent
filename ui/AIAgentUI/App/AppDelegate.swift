#if os(macOS)
//
//  AppDelegate.swift
//  AIAgentUI
//
//  Created for Personal macOS AI Agent
//  Status: Active - Application lifecycle and hotkey management
//

import Foundation
import AppKit
import SwiftUI
import ApplicationServices

/// Application delegate for handling lifecycle events, hotkeys, and system integration
@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    
    // MARK: - Properties
    
    /// Reference to the floating panel controller
    private let panelController = FloatingPanelController.shared

    /// Reference to the notes panel controller
    private let notesPanelController = NotesPanelController.shared

    /// Reference to the global hotkey manager
    private let hotkeyManager = GlobalHotkeyManager.shared
    
    /// Reference to the permissions manager
    private let permissionsManager = PermissionsManager.shared

    /// Prevents duplicate toggles when multiple hotkey paths fire for one keypress
    private var lastToggleUptime: TimeInterval = 0
    private let toggleDebounceInterval: TimeInterval = 0.25
    
    /// Reference to the app state
    private var appState: AppState {
        AppState.shared
    }

    private let bootstrapScriptRelativePath = "scripts/start_latest_app.sh"

    private enum PreferenceKeys {
        static let showInDock = "showInDock"
        static let enableSnapping = "enableSnapping"
        static let panelOpacity = "panelOpacity"
        static let animationsEnabled = "animationsEnabled"
    }
    
    // MARK: - Lifecycle
    
    func applicationDidFinishLaunching(_ notification: Notification) {
        if relaunchViaLatestBuildBootstrapIfNeeded() {
            NSApp.terminate(nil)
            return
        }

        // Configure app to be an agent (no dock icon by default)
        configureAppBehavior()
        
        // Check and request permissions
        checkPermissions()
        
        // Re-register global hotkey when Accessibility is granted mid-session
        permissionsManager.onPermissionChange = { [weak self] permissionType, newStatus in
            guard self != nil, permissionType == .accessibility, newStatus == .authorized else { return }
            // Accessibility was just granted — enable the global NSEvent monitor
            HotKeyMonitor.shared.startMonitoring(includeGlobalMonitor: true)
        }
        
        // Set up the floating panel
        setupFloatingPanel()

        // Set up the notes panel
        setupNotesPanel()

        // Register global hotkey (Cmd+K)
        setupGlobalHotkey()
        
        // Start the app (auto-start backend and connect)
        Task {
            await appState.startup()
        }
        
        // Show panel on launch
        panelController.show()
    }

    private func relaunchViaLatestBuildBootstrapIfNeeded() -> Bool {
        let env = ProcessInfo.processInfo.environment
        let bootstrapped = env["AI_AGENT_BOOTSTRAPPED"] == "1"
        let bootstrapParentPID = env["AI_AGENT_BOOTSTRAP_PARENT_PID"]?.trimmingCharacters(in: .whitespacesAndNewlines)
        let disableReexec = env["AI_AGENT_DISABLE_BOOTSTRAP_REEXEC"] == "1"

        // Already launched via start_latest_app.sh — skip re-exec entirely.
        if bootstrapped && (disableReexec || (bootstrapParentPID?.isEmpty == false)) {
            NSLog("Bootstrap re-exec skipped: process already bootstrapped.")
            return false
        }
        // Explicitly disabled.
        if disableReexec {
            NSLog("Bootstrap re-exec skipped: AI_AGENT_DISABLE_BOOTSTRAP_REEXEC=1.")
            return false
        }
        // Running inside a test harness.
        if env["XCTestConfigurationFilePath"] != nil {
            NSLog("Bootstrap re-exec skipped: XCTest environment detected.")
            return false
        }

        guard let (projectRoot, scriptURL) = locateBootstrapScript() else {
            NSLog("Bootstrap re-exec skipped: start_latest_app.sh not found.")
            return false
        }
        NSLog("Bootstrap re-exec launching clean startup script: %@", scriptURL.path)

        // Run the startup script end-to-end so swift run triggers the same
        // full clean bootstrap flow as running scripts/start_latest_app.sh directly.
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/bash")
        process.arguments = [scriptURL.path]
        process.currentDirectoryURL = projectRoot
        var childEnv = env
        childEnv["AI_AGENT_BOOTSTRAPPED"] = "1"
        childEnv["AI_AGENT_DISABLE_BOOTSTRAP_REEXEC"] = "1"
        childEnv["AI_AGENT_BOOTSTRAP_PARENT_PID"] = "\(ProcessInfo.processInfo.processIdentifier)"
        process.environment = childEnv

        do {
            try process.run()
            return true
        } catch {
            NSLog("Bootstrap relaunch failed: %@", error.localizedDescription)
            return false
        }
    }

    private func locateBootstrapScript() -> (URL, URL)? {
        let fileManager = FileManager.default

        var seeds: [URL] = [
            URL(fileURLWithPath: fileManager.currentDirectoryPath),
            URL(fileURLWithPath: NSHomeDirectory()).appendingPathComponent("AI Automation Agent macOS"),
        ]
        if let executableURL = Bundle.main.executableURL {
            seeds.append(executableURL.deletingLastPathComponent())
        }
        seeds.append(Bundle.main.bundleURL.deletingLastPathComponent())

        var visited = Set<String>()
        for seed in seeds {
            var probe = seed.standardizedFileURL
            for _ in 0..<10 {
                if !visited.insert(probe.path).inserted {
                    break
                }

                let scriptURL = probe.appendingPathComponent(bootstrapScriptRelativePath)
                let pyprojectURL = probe.appendingPathComponent("pyproject.toml")
                if fileManager.isExecutableFile(atPath: scriptURL.path),
                   fileManager.fileExists(atPath: pyprojectURL.path) {
                    return (probe, scriptURL)
                }

                let parent = probe.deletingLastPathComponent()
                if parent.path == probe.path {
                    break
                }
                probe = parent
            }
        }

        return nil
    }
    
    /// Checks required macOS permissions and prompts user if needed
    private func checkPermissions() {
        // Perform initial permission check
        permissionsManager.performStartupCheck()

        // Only trigger permission requests (which start background polling) when
        // the permissions modal was actually shown — i.e. critical permissions
        // (accessibility / automation) are missing.  Avoid starting polling when
        // the only "missing" permission is screen recording whose async probe
        // hasn't resolved yet; that false-negative causes the polling loop to
        // fire showPermissionsGrantedNotification() spuriously.
        if permissionsManager.showPermissionsModal {
            // Request accessibility permission (required for hotkey)
            permissionsManager.requestPermission(.accessibility)
        }
    }
    
    func applicationWillTerminate(_ notification: Notification) {
        // Unregister hotkey
        hotkeyManager.unregisterHotkey()
        HotKeyMonitor.shared.stopMonitoring()
        
        // Shutdown backend and disconnect
        appState.shutdown()
    }
    
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        // Show panel when clicking dock icon (if shown)
        if !flag {
            panelController.show()
        }
        return true
    }
    
    func applicationSupportsSecureRestorableState(_ app: NSApplication) -> Bool {
        return true
    }
    
    // MARK: - Configuration
    
    /// Configures app behavior (agent mode, dock visibility, etc.)
    private func configureAppBehavior() {
        // Default to dock-visible mode for reliable activation/hotkey focus semantics.
        // Users can disable this later in settings.
        let defaults = UserDefaults.standard
        let showInDock: Bool
        if defaults.object(forKey: PreferenceKeys.showInDock) == nil {
            defaults.set(true, forKey: PreferenceKeys.showInDock)
            showInDock = true
        } else {
            showInDock = defaults.bool(forKey: PreferenceKeys.showInDock)
        }

        Self.applyDockVisibility(showInDock)
    }
    
    /// Sets up the floating panel
    private func setupFloatingPanel() {
        PanelPositionManager.shared.isSnappingEnabled = Self.loadBool(
            key: PreferenceKeys.enableSnapping,
            defaultValue: true
        )
        panelController.setup(appState: appState)
        panelController.applyAppearancePreferences(
            opacity: Self.loadDouble(
                key: PreferenceKeys.panelOpacity,
                defaultValue: 0.95
            ),
            animationsEnabled: Self.loadBool(
                key: PreferenceKeys.animationsEnabled,
                defaultValue: true
            )
        )
    }
    
    /// Sets up the notes panel (hidden by default, shown on demand)
    private func setupNotesPanel() {
        notesPanelController.setup(appState: appState)
    }

    /// Sets up the global Cmd+K hotkey
    private func setupGlobalHotkey() {
        // Set up the primary Carbon callback
        hotkeyManager.onHotkeyPressed = { [weak self] in
            self?.togglePanelDebounced()
        }
        
        // Register Carbon hotkeys first (works globally without Accessibility permission)
        let carbonRegistered = hotkeyManager.registerHotkey()
        if !carbonRegistered {
            print("Global hotkey registration via Carbon failed. Falling back to NSEvent monitors.")
        }

        // Always keep local monitor active (works when app is focused).
        // Enable global monitor only when Accessibility permission is granted.
        HotKeyMonitor.shared.onHotkeyPressed = { [weak self] in
            self?.togglePanelDebounced()
        }

        let accessibilityTrusted = AXIsProcessTrusted()
        HotKeyMonitor.shared.startMonitoring(includeGlobalMonitor: accessibilityTrusted)

        if !accessibilityTrusted {
            print("Accessibility permission is not granted. NSEvent global hotkey monitor is disabled.")
        }

        if !carbonRegistered && !accessibilityTrusted {
            print("No working global hotkey path available yet. Grant Accessibility in System Settings.")
        }
    }

    private func togglePanelDebounced() {
        let now = ProcessInfo.processInfo.systemUptime
        guard now - lastToggleUptime >= toggleDebounceInterval else {
            return
        }
        lastToggleUptime = now
        togglePanel()
    }
    
    // MARK: - Actions
    
    /// Toggles panel visibility
    @objc func togglePanel() {
        panelController.toggle()
    }
    
    /// Shows the panel
    @objc func showPanel() {
        panelController.show()
    }
    
    /// Hides the panel
    @objc func hidePanel() {
        panelController.hide()
    }

    /// Toggles the notes panel
    @objc func toggleNotes() {
        notesPanelController.toggle()
    }

    /// Reconnects to the backend
    @objc func reconnect() {
        Task {
            await appState.reconnect()
        }
    }
    
    /// Clears all messages
    @objc func clearMessages() {
        Task { @MainActor in
            appState.clearMessages()
        }
    }
    
    /// Quits the application
    @objc func quitApp() {
        NSApplication.shared.terminate(nil)
    }
}
#endif

// MARK: - Runtime Preference Application

extension AppDelegate {
    static func applyDockVisibility(_ showInDock: Bool) {
        // Defer the policy change to the next run-loop turn so the window
        // server has finished initialising this process.  Calling
        // setActivationPolicy too early triggers the harmless but noisy
        // "Task policy set failed: 4 ((os/kern) invalid argument)" log.
        DispatchQueue.main.async {
            let targetPolicy: NSApplication.ActivationPolicy = showInDock ? .regular : .accessory
            if NSApp.activationPolicy() != targetPolicy {
                _ = NSApp.setActivationPolicy(targetPolicy)
            }
            if showInDock && !NSApp.isActive {
                NSApp.activate(ignoringOtherApps: true)
            }
        }
    }

    private static func loadBool(key: String, defaultValue: Bool) -> Bool {
        let defaults = UserDefaults.standard
        guard defaults.object(forKey: key) != nil else { return defaultValue }
        return defaults.bool(forKey: key)
    }

    private static func loadDouble(key: String, defaultValue: Double) -> Double {
        let defaults = UserDefaults.standard
        guard defaults.object(forKey: key) != nil else { return defaultValue }
        return defaults.double(forKey: key)
    }
}

// MARK: - Menu Actions

extension AppDelegate {
    
    /// Creates the application menu
    func createApplicationMenu() -> NSMenu {
        let menu = NSMenu()
        
        // Toggle panel
        let toggleItem = NSMenuItem(
            title: "Toggle Panel",
            action: #selector(togglePanel),
            keyEquivalent: "k"
        )
        toggleItem.keyEquivalentModifierMask = .command
        menu.addItem(toggleItem)
        
        menu.addItem(.separator())
        
        // Reconnect
        let reconnectItem = NSMenuItem(
            title: "Reconnect",
            action: #selector(reconnect),
            keyEquivalent: "r"
        )
        reconnectItem.keyEquivalentModifierMask = [.command, .shift]
        menu.addItem(reconnectItem)
        
        // Toggle notes panel
        let notesItem = NSMenuItem(
            title: "Toggle Notes",
            action: #selector(toggleNotes),
            keyEquivalent: "n"
        )
        notesItem.keyEquivalentModifierMask = [.command, .shift]
        menu.addItem(notesItem)

        // Clear messages
        let clearItem = NSMenuItem(
            title: "Clear Messages",
            action: #selector(clearMessages),
            keyEquivalent: ""
        )
        menu.addItem(clearItem)
        
        menu.addItem(.separator())
        
        // Permissions
        let permissionsItem = NSMenuItem(
            title: "Permissions...",
            action: #selector(showPermissions),
            keyEquivalent: ""
        )
        menu.addItem(permissionsItem)
        
        // Preferences
        let prefsItem = NSMenuItem(
            title: "Settings...",
            action: #selector(showPreferences),
            keyEquivalent: ","
        )
        prefsItem.keyEquivalentModifierMask = .command
        menu.addItem(prefsItem)
        
        menu.addItem(.separator())
        
        // Quit
        let quitItem = NSMenuItem(
            title: "Quit AI Agent",
            action: #selector(quitApp),
            keyEquivalent: "q"
        )
        quitItem.keyEquivalentModifierMask = .command
        menu.addItem(quitItem)
        
        return menu
    }
    
    @objc func showPreferences() {
        // First activate the app to ensure windows can open properly
        // This is especially important when running as a background agent (.accessory)
        NSApp.activate(ignoringOtherApps: true)
        
        // Open settings scene using the appropriate selector
        // Try showSettingsWindow: first (macOS 13+), fall back to showPreferencesWindow:
        DispatchQueue.main.async {
            if #available(macOS 13.0, *) {
                if !NSApp.sendAction(Selector(("showSettingsWindow:")), to: nil, from: nil) {
                    // If that fails, try the standard preferences action
                    NSApp.sendAction(Selector(("showPreferencesWindow:")), to: nil, from: nil)
                }
            } else {
                NSApp.sendAction(Selector(("showPreferencesWindow:")), to: nil, from: nil)
            }
        }
    }
    
    @objc func showPermissions() {
        // Set the flag to show the permissions modal
        permissionsManager.showPermissionsModal = true
    }
}

// MARK: - Status Item (Menu Bar Icon)

extension AppDelegate {
    
    /// Creates and configures the status bar item
    func setupStatusBarItem() -> NSStatusItem {
        let statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        
        if let button = statusItem.button {
            button.image = NSImage(systemSymbolName: "brain", accessibilityDescription: "AI Agent")
            button.image?.isTemplate = true
        }
        
        statusItem.menu = createStatusBarMenu()
        
        return statusItem
    }
    
    /// Creates the status bar menu
    private func createStatusBarMenu() -> NSMenu {
        let menu = NSMenu()
        
        // Connection status
        let statusItem = NSMenuItem(title: "Disconnected", action: nil, keyEquivalent: "")
        statusItem.isEnabled = false
        menu.addItem(statusItem)
        
        menu.addItem(.separator())
        
        // Toggle panel
        let toggleItem = NSMenuItem(
            title: "Show/Hide Panel",
            action: #selector(togglePanel),
            keyEquivalent: "k"
        )
        toggleItem.keyEquivalentModifierMask = .command
        menu.addItem(toggleItem)
        
        // Reconnect
        let reconnectItem = NSMenuItem(
            title: "Reconnect",
            action: #selector(reconnect),
            keyEquivalent: ""
        )
        menu.addItem(reconnectItem)
        
        menu.addItem(.separator())
        
        // Settings
        let settingsItem = NSMenuItem(
            title: "Settings...",
            action: #selector(showPreferences),
            keyEquivalent: ","
        )
        settingsItem.keyEquivalentModifierMask = .command
        menu.addItem(settingsItem)
        
        menu.addItem(.separator())
        
        // Quit
        let quitItem = NSMenuItem(
            title: "Quit",
            action: #selector(quitApp),
            keyEquivalent: "q"
        )
        quitItem.keyEquivalentModifierMask = .command
        menu.addItem(quitItem)
        
        return menu
    }
    
    /// Updates the status bar item to reflect current connection status
    func updateStatusBarItem(_ statusItem: NSStatusItem) {
        Task { @MainActor in
            guard let menu = statusItem.menu,
                  let statusMenuItem = menu.items.first else { return }
            
            if appState.isConnected {
                statusMenuItem.title = "Connected"
            } else {
                statusMenuItem.title = "Disconnected"
            }
        }
    }
}
