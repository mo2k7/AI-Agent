//
//  PermissionsManager.swift
//  AIAgentUI
//
//  Created for Personal macOS AI Agent
//  Status: Active - Manages macOS TCC permissions for system automation
//

import Foundation
import AppKit
import ApplicationServices
import ScreenCaptureKit
import os.log

/// Represents the types of permissions the AI Agent needs
enum PermissionType: String, CaseIterable, Identifiable {
    case accessibility = "Accessibility"
    case automation = "Automation"
    case fullDiskAccess = "Full Disk Access"
    case screenRecording = "Screen Recording"

    var id: String { rawValue }

    /// Human-readable description of what the permission enables
    var description: String {
        switch self {
        case .accessibility:
            return "Required for controlling UI elements, clicking buttons, and typing text in other applications."
        case .automation:
            return "Required for executing AppleScript commands and controlling other applications via System Events."
        case .fullDiskAccess:
            return "Required for reading and writing files across the system, including protected directories."
        case .screenRecording:
            return "Allows the AI Agent to read and understand what's on your screen."
        }
    }

    /// The SF Symbol name for this permission type
    var symbolName: String {
        switch self {
        case .accessibility:
            return "accessibility"
        case .automation:
            return "gearshape.2"
        case .fullDiskAccess:
            return "folder.badge.gearshape"
        case .screenRecording:
            return "eye.fill"
        }
    }

    /// The settings pane URL for this permission type
    var settingsURL: URL? {
        switch self {
        case .accessibility:
            return URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility")
        case .automation:
            return URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation")
        case .fullDiskAccess:
            return URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles")
        case .screenRecording:
            return URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture")
        }
    }
}

/// Represents the authorization status for a permission
enum PermissionStatus: Equatable {
    case authorized
    case denied
    case notDetermined
    case restricted
    
    var displayName: String {
        switch self {
        case .authorized: return "Granted"
        case .denied: return "Denied"
        case .notDetermined: return "Not Requested"
        case .restricted: return "Restricted"
        }
    }
    
    var color: String {
        switch self {
        case .authorized: return "green"
        case .denied: return "red"
        case .notDetermined: return "yellow"
        case .restricted: return "gray"
        }
    }
}

/// Manages macOS TCC (Transparency, Consent, and Control) permissions
/// 
/// ## Technical Note on macOS Permissions
/// macOS TCC permissions (Accessibility, Automation, Full Disk Access) are
/// managed by the OS kernel and **cannot be granted programmatically** by any third-party app.
///
/// What this manager provides:
/// 1. **Permission status checking** - Detects which permissions are granted/missing
/// 2. **System prompt triggering** - For Accessibility and Automation, we can trigger the OS prompt
/// 3. **Guided flow** - Opens the correct System Settings pane
///
@MainActor
final class PermissionsManager: ObservableObject {
    struct FullDiskAccessProbeResult: Equatable {
        let exists: Bool
        let readable: Bool
        let permissionDenied: Bool
    }

    private nonisolated static let fullDiskAccessProbeRelativePaths: [String] = [
        "Library/Application Support/com.apple.TCC/TCC.db",
        "Library/Safari/History.db",
        "Library/Messages/chat.db",
        "Library/Mail/V7/MailData/Envelope Index",
        "Library/Mail/V8/MailData/Envelope Index",
        "Library/Mail/V9/MailData/Envelope Index",
        "Library/Mail/V10/MailData/Envelope Index",
        "Library/Mail/V11/MailData/Envelope Index",
    ]
    
    // MARK: - Singleton
    
    static let shared = PermissionsManager()
    
    // MARK: - Published Properties
    
    /// Current status of all permissions
    @Published private(set) var permissionStatuses: [PermissionType: PermissionStatus] = [:]
    
    /// Whether the permissions modal should be shown
    @Published var showPermissionsModal: Bool = false
    
    /// Whether all required permissions are granted
    @Published private(set) var allPermissionsGranted: Bool = false
    
    /// The permission currently requiring user action in System Settings
    @Published var activeGuidance: PermissionType?
    
    /// List of permissions requiring action for bulk flow
    @Published var bulkGuidanceTypes: [PermissionType]?
    
    // MARK: - Private Properties
    
    private let logger = Logger(subsystem: "com.aiagent.ui", category: "Permissions")
    private var screenRecordingProbeInFlight = false
    
    // MARK: - Initialization
    
    private init() {
        checkAllPermissions()
    }
    
    // MARK: - Public Methods
    
    /// Checks all permission statuses.
    /// - Parameter performAutomationProbe: When false, avoids AppleScript probe for
    ///   automation status to prevent repeated intrusive checks during background polling.
    func checkAllPermissions(performAutomationProbe: Bool = true) {
        var statuses: [PermissionType: PermissionStatus] = [:]
        
        for permissionType in PermissionType.allCases {
            statuses[permissionType] = checkPermission(
                permissionType,
                performAutomationProbe: performAutomationProbe
            )
        }
        
        permissionStatuses = statuses
        allPermissionsGranted = statuses.values.allSatisfy { $0 == .authorized }
        
        logger.info("Permission check complete. All granted: \(self.allPermissionsGranted)")
    }
    
    /// Checks a specific permission.
    /// - Parameter performAutomationProbe: Controls whether automation probe is allowed.
    func checkPermission(
        _ type: PermissionType,
        performAutomationProbe: Bool = true
    ) -> PermissionStatus {
        switch type {
        case .accessibility:
            return checkAccessibilityPermission()
        case .automation:
            if !performAutomationProbe {
                return permissionStatuses[.automation] ?? .notDetermined
            }
            return checkAutomationPermission()
        case .fullDiskAccess:
            return checkFullDiskAccessPermission()
        case .screenRecording:
            return checkScreenRecordingPermission()
        }
    }
    
    /// Requests a specific permission
    /// This is the primary method to use when the user clicks "Grant" in the UI
    func requestPermission(_ type: PermissionType) {
        logger.info("Requesting permission: \(type.rawValue)")
        triggerSystemPermissionRequest(type)
    }
    
    /// Grants all missing permissions
    /// This provides a streamlined "Grant All" experience
    func grantAllPermissions() {
        guard !missingPermissions.isEmpty else {
            logger.info("All permissions already granted")
            return
        }
        
        triggerAllPermissionRequests()
    }
    
    /// Triggers the appropriate system permission request flow
    private func triggerSystemPermissionRequest(_ type: PermissionType) {
        switch type {
        case .accessibility:
            // Accessibility can show a system prompt
            let _ = Self.requestAccessibilityWithPrompt()
            logger.info("Triggered accessibility permission system prompt")

        case .automation:
            // Automation triggers when we attempt an automation action
            requestAutomationPermission()

        case .fullDiskAccess:
            // These MUST be granted in System Settings - no programmatic option
            openSystemSettings(for: type)
            activeGuidance = type

        case .screenRecording:
            // Triggers macOS TCC prompt for screen recording
            requestScreenRecordingPermission()
        }
        
        // Start polling for permission changes to update UI when user completes action
        startPermissionPolling()
    }
    
    /// Triggers system permission requests for all missing permissions
    private func triggerAllPermissionRequests() {
        // Request permissions in order of priority
        let orderedMissing = missingPermissions.sorted { p1, p2 in
            let order: [PermissionType] = [.accessibility, .automation, .fullDiskAccess, .screenRecording]
            guard let p1Index = order.firstIndex(of: p1),
                  let p2Index = order.firstIndex(of: p2) else {
                return p1.rawValue < p2.rawValue
            }
            return p1Index < p2Index
        }
        
        // For permissions that can show system prompts, trigger them
        // For others, open System Settings
        var systemSettingsTypes: [PermissionType] = []
        
        for permission in orderedMissing {
            switch permission {
            case .accessibility:
                let _ = Self.requestAccessibilityWithPrompt()
            case .automation:
                requestAutomationPermission()
            case .fullDiskAccess:
                systemSettingsTypes.append(permission)
            case .screenRecording:
                requestScreenRecordingPermission()
            }
        }
        
        // If there are permissions requiring System Settings, show guidance
        if !systemSettingsTypes.isEmpty {
            bulkGuidanceTypes = systemSettingsTypes
            
            // Open the first required settings pane automatically
            if let firstType = systemSettingsTypes.first {
                openSystemSettings(for: firstType)
            }
        }
        
        // Start polling for permission changes
        startPermissionPolling()
    }
    
    /// Opens System Settings to the appropriate privacy pane
    func openSystemSettings(for type: PermissionType) {
        guard let url = type.settingsURL else {
            logger.error("No settings URL for permission type: \(type.rawValue)")
            return
        }
        
        NSWorkspace.shared.open(url)
        logger.info("Opened System Settings for: \(type.rawValue)")
    }
    
    /// Shows an alert explaining why permissions are needed
    func showPermissionExplanation() {
        showPermissionsModal = true
    }
    
    // MARK: - Accessibility Permission
    
    private func checkAccessibilityPermission() -> PermissionStatus {
        // AXIsProcessTrusted() returns true if accessibility is enabled
        let trusted = AXIsProcessTrusted()
        return trusted ? .authorized : .notDetermined
    }
    
    private func requestAccessibilityPermission() {
        // This will show the system prompt to enable accessibility
        let trusted = Self.requestAccessibilityWithPrompt()
        
        if trusted {
            logger.info("Accessibility permission already granted")
        } else {
            logger.info("Accessibility permission prompt shown")
        }
        
        // Refresh status after a delay to allow user to grant permission
        Task {
            try? await Task.sleep(nanoseconds: 2_000_000_000) // 2 seconds
            await MainActor.run {
                self.checkAllPermissions()
            }
        }
    }
    
    /// Static helper to access kAXTrustedCheckOptionPrompt in a concurrency-safe way
    /// The string "AXTrustedCheckOptionPrompt" is the constant value of kAXTrustedCheckOptionPrompt
    private nonisolated static func requestAccessibilityWithPrompt() -> Bool {
        let promptKey = "AXTrustedCheckOptionPrompt" as CFString
        let options = [promptKey: kCFBooleanTrue as Any] as CFDictionary
        return AXIsProcessTrustedWithOptions(options)
    }
    
    // MARK: - Automation Permission
    
    private func checkAutomationPermission() -> PermissionStatus {
        // Try to create a System Events scripting target to check automation permission
        // This is a heuristic - actual permission check requires attempting an automation action
        
        // Check if we can target Finder (more reliable trigger than System Events)
        let script = """
        tell application "Finder"
            return name
        end tell
        """
        
        var error: NSDictionary?
        if let scriptObject = NSAppleScript(source: script) {
            _ = scriptObject.executeAndReturnError(&error)
            
            if error == nil {
                return .authorized
            }
            
            // Check for specific error codes
            if let errorDict = error,
               let code = errorDict[NSAppleScript.errorNumber] as? Int {
                // -1743: errAEEventNotPermitted (User denied permission)
                if code == -1743 {
                    return .denied
                }
            }
        }
        
        return .notDetermined
    }
    
    private func requestAutomationPermission() {
        // Attempting to automate Finder will trigger the permission prompt
        let script = """
        tell application "Finder"
            return name
        end tell
        """
        
        var error: NSDictionary?
        if let scriptObject = NSAppleScript(source: script) {
            _ = scriptObject.executeAndReturnError(&error)
            
            if let error = error {
                logger.info("Automation permission prompt triggered: \(error)")
                
                // If we get a denial error, we should probably open settings
                if let code = error[NSAppleScript.errorNumber] as? Int, code == -1743 {
                    Task { @MainActor in
                        self.openSystemSettings(for: .automation)
                        self.activeGuidance = .automation
                    }
                }
            }
        }
        
        // Refresh status
        Task {
            try? await Task.sleep(nanoseconds: 2_000_000_000)
            await MainActor.run {
                self.checkAllPermissions()
            }
        }
    }
    
    // MARK: - Full Disk Access Permission
    
    private func checkFullDiskAccessPermission() -> PermissionStatus {
        let homeDirectory = FileManager.default.homeDirectoryForCurrentUser
        let fileManager = FileManager.default
        let probeResults: [FullDiskAccessProbeResult] = Self.fullDiskAccessProbeRelativePaths.map { relativePath in
            let targetURL = homeDirectory.appendingPathComponent(relativePath)
            guard fileManager.fileExists(atPath: targetURL.path) else {
                return FullDiskAccessProbeResult(exists: false, readable: false, permissionDenied: false)
            }

            do {
                let fileHandle = try FileHandle(forReadingFrom: targetURL)
                _ = try fileHandle.read(upToCount: 1)
                try? fileHandle.close()
                return FullDiskAccessProbeResult(exists: true, readable: true, permissionDenied: false)
            } catch {
                return FullDiskAccessProbeResult(
                    exists: true,
                    readable: false,
                    permissionDenied: Self.isPermissionDeniedError(error)
                )
            }
        }

        return Self.evaluateFullDiskAccessStatus(from: probeResults)
    }

    nonisolated static func evaluateFullDiskAccessStatus(
        from probeResults: [FullDiskAccessProbeResult]
    ) -> PermissionStatus {
        let existingTargets = probeResults.filter(\.exists)
        guard !existingTargets.isEmpty else {
            return .notDetermined
        }

        if existingTargets.contains(where: \.readable) {
            return .authorized
        }

        if existingTargets.contains(where: \.permissionDenied) {
            return .denied
        }

        return .notDetermined
    }

    private nonisolated static func isPermissionDeniedError(_ error: Error) -> Bool {
        return isPermissionDeniedNSError(error as NSError)
    }

    private nonisolated static func isPermissionDeniedNSError(_ error: NSError) -> Bool {
        if error.domain == NSCocoaErrorDomain {
            if error.code == NSFileReadNoPermissionError || error.code == NSFileWriteNoPermissionError {
                return true
            }
        }
        if error.domain == NSPOSIXErrorDomain && (error.code == Int(EACCES) || error.code == Int(EPERM)) {
            return true
        }
        if let underlying = error.userInfo[NSUnderlyingErrorKey] as? NSError {
            return isPermissionDeniedNSError(underlying)
        }
        return false
    }
    
    // MARK: - Screen Recording Permission

    /// Checks screen recording permission using ScreenCaptureKit probing.
    private func checkScreenRecordingPermission() -> PermissionStatus {
        if !screenRecordingProbeInFlight {
            screenRecordingProbeInFlight = true
            Task { [weak self] in
                let status = await Self.probeScreenRecordingPermissionStatus()
                await MainActor.run {
                    guard let self else { return }
                    self.screenRecordingProbeInFlight = false
                    self.permissionStatuses[.screenRecording] = status
                    self.allPermissionsGranted = PermissionType.allCases.allSatisfy {
                        self.permissionStatuses[$0] == .authorized
                    }
                }
            }
        }
        return permissionStatuses[.screenRecording] ?? .notDetermined
    }

    private func requestScreenRecordingPermission() {
        Task {
            _ = await Self.probeScreenRecordingPermissionStatus()
            try? await Task.sleep(nanoseconds: 1_000_000_000)
            await MainActor.run {
                self.checkAllPermissions()
            }
        }
    }

    private nonisolated static func probeScreenRecordingPermissionStatus() async -> PermissionStatus {
        do {
            _ = try await SCShareableContent.excludingDesktopWindows(
                false,
                onScreenWindowsOnly: true
            )
            return .authorized
        } catch {
            return .denied
        }
    }

    // MARK: - Utility Methods
    
    /// Returns the permissions that are not yet authorized
    var missingPermissions: [PermissionType] {
        return PermissionType.allCases.filter { permissionStatuses[$0] != .authorized }
    }
    
    /// Returns a summary of permission statuses
    var statusSummary: String {
        let granted = permissionStatuses.values.filter { $0 == .authorized }.count
        let total = PermissionType.allCases.count
        return "\(granted)/\(total) permissions granted"
    }
    
    // MARK: - Permission Polling
    
    private var pollingTask: Task<Void, Never>?
    
    /// Starts polling for permission changes (useful after opening System Settings)
    func startPermissionPolling() {
        stopPermissionPolling()
        
        pollingTask = Task {
            // Poll every 2 seconds for 60 seconds
            for iteration in 0..<30 {
                if Task.isCancelled { break }
                
                try? await Task.sleep(nanoseconds: 2_000_000_000)
                
                await MainActor.run {
                    // Only run AppleScript-based automation probe periodically
                    // to avoid repeated intrusive checks during polling.
                    let shouldProbeAutomation = iteration % 5 == 0
                    self.checkAllPermissions(performAutomationProbe: shouldProbeAutomation)
                }
                
                // Stop polling if all permissions are granted
                if await MainActor.run(body: { self.allPermissionsGranted }) {
                    await MainActor.run {
                        self.logger.info("All permissions granted - stopping poll")
                        self.showPermissionsGrantedNotification()
                    }
                    break
                }
            }
        }
    }
    
    /// Stops permission polling
    func stopPermissionPolling() {
        pollingTask?.cancel()
        pollingTask = nil
    }
    
    /// Shows a notification when all permissions are granted.
    ///
    /// IMPORTANT: Must NOT use NSAlert.runModal() here. This app uses a floating
    /// NSPanel (window level .floating). runModal() enters a modal event loop that
    /// blocks ALL other windows while the alert renders beside/behind the panel,
    /// making the entire app appear frozen with beeps on every click.
    private func showPermissionsGrantedNotification() {
        showPermissionsModal = false
        logger.info("All permissions granted — dismissed permissions modal.")
    }
    
    /// Relaunches the application
    /// Useful when permissions require a restart (like Full Disk Access)
    func restartApp() {
        let url = URL(fileURLWithPath: Bundle.main.bundlePath)
        let config = NSWorkspace.OpenConfiguration()
        config.createsNewApplicationInstance = true
        
        NSWorkspace.shared.openApplication(at: url, configuration: config) { _, _ in
            DispatchQueue.main.async {
                NSApp.terminate(nil)
            }
        }
    }
}

// MARK: - Permission Check on App Launch

extension PermissionsManager {
    
    /// Performs initial permission check and shows modal if needed
    func performStartupCheck() {
        checkAllPermissions()
        
        // Show modal if critical permissions are missing
        let accessibilityAuthorized = permissionStatuses[.accessibility]?.isAuthorized ?? false
        let automationAuthorized = permissionStatuses[.automation]?.isAuthorized ?? false
        if !accessibilityAuthorized || !automationAuthorized {
            showPermissionsModal = true
        }
    }
}

// MARK: - PermissionStatus Extension

extension PermissionStatus {
    var isAuthorized: Bool {
        self == .authorized
    }
}
