#if !os(macOS)
import SwiftUI
import UserNotifications
import AVFoundation
import Photos

// MARK: - Permission Types (iOS / iPadOS)

enum PermissionType: String, CaseIterable, Identifiable {
    case notifications = "Notifications"
    case camera = "Camera"
    case microphone = "Microphone"
    case photos = "Photos"

    var id: String { rawValue }

    var description: String {
        switch self {
        case .notifications:
            return "Required for sending you alerts, reminders, and task updates."
        case .camera:
            return "Required for capturing images and scanning documents."
        case .microphone:
            return "Required for voice input and audio dictation."
        case .photos:
            return "Required for saving and accessing images in your photo library."
        }
    }

    var symbolName: String {
        switch self {
        case .notifications: return "bell.badge"
        case .camera: return "camera"
        case .microphone: return "mic"
        case .photos: return "photo.on.rectangle"
        }
    }

    var settingsURL: URL? {
        // On iOS, all permissions are managed in the app's section of Settings
        URL(string: UIApplication.openSettingsURLString)
    }

    /// Recovery instructions shown when the permission is denied
    var recoveryInstructions: String {
        switch self {
        case .notifications:
            return "Open Settings → AI Agent → Notifications and enable 'Allow Notifications'."
        case .camera:
            return "Open Settings → AI Agent → Camera and toggle the switch on."
        case .microphone:
            return "Open Settings → AI Agent → Microphone and toggle the switch on."
        case .photos:
            return "Open Settings → AI Agent → Photos and select 'Full Access'."
        }
    }
}

// MARK: - Permission Status

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

    var isAuthorized: Bool { self == .authorized }
}

// MARK: - Permissions Manager (iOS / iPadOS)

@MainActor
final class PermissionsManager: ObservableObject {
    static let shared = PermissionsManager()

    @Published private(set) var permissionStatuses: [PermissionType: PermissionStatus] = [:]
    @Published var showPermissionsModal = false
    @Published private(set) var allPermissionsGranted = true
    @Published var activeGuidance: PermissionType?
    @Published var bulkGuidanceTypes: [PermissionType]?

    /// Fires when any individual permission status changes.
    var onPermissionChange: ((PermissionType, PermissionStatus) -> Void)?

    private init() {
        checkAllPermissions()
        startLifecycleObserving()
    }

    // MARK: - Lifecycle Re-checks

    /// Registers for app activation notifications.
    /// When the user returns from iOS Settings, permissions are re-checked instantly.
    /// No need to store/remove the observer — PermissionsManager is a singleton
    /// that lives for the entire app lifecycle.
    private func startLifecycleObserving() {
        NotificationCenter.default.addObserver(
            forName: UIApplication.didBecomeActiveNotification,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            guard let self else { return }
            Task { @MainActor in
                self.handleAppDidBecomeActive()
            }
        }
    }

    private func handleAppDidBecomeActive() {
        let previousStatuses = permissionStatuses
        checkAllPermissions()

        // Fire callbacks for any permission that changed
        for permissionType in PermissionType.allCases {
            let oldStatus = previousStatuses[permissionType]
            let newStatus = permissionStatuses[permissionType]
            if oldStatus != newStatus, let newStatus {
                onPermissionChange?(permissionType, newStatus)
            }
        }

        // Auto-dismiss modal when all permissions are granted
        if allPermissionsGranted && showPermissionsModal {
            showPermissionsModal = false
        }
    }

    // MARK: - Check Permissions

    func checkAllPermissions(performAutomationProbe: Bool = true) {
        var statuses: [PermissionType: PermissionStatus] = [:]
        for permissionType in PermissionType.allCases {
            statuses[permissionType] = checkPermission(permissionType)
        }
        permissionStatuses = statuses
        allPermissionsGranted = statuses.values.allSatisfy { $0 == .authorized }
    }

    func checkPermission(_ type: PermissionType, performAutomationProbe: Bool = true) -> PermissionStatus {
        switch type {
        case .notifications:
            return checkNotificationPermission()
        case .camera:
            return mapAVAuthorizationStatus(AVCaptureDevice.authorizationStatus(for: .video))
        case .microphone:
            return mapAVAuthorizationStatus(AVCaptureDevice.authorizationStatus(for: .audio))
        case .photos:
            return mapPHAuthorizationStatus(PHPhotoLibrary.authorizationStatus(for: .readWrite))
        }
    }

    // MARK: - Request Permissions

    func requestPermission(_ type: PermissionType) {
        switch type {
        case .notifications:
            requestNotificationPermission()
        case .camera:
            AVCaptureDevice.requestAccess(for: .video) { [weak self] _ in
                Task { @MainActor in self?.checkAllPermissions() }
            }
        case .microphone:
            AVCaptureDevice.requestAccess(for: .audio) { [weak self] _ in
                Task { @MainActor in self?.checkAllPermissions() }
            }
        case .photos:
            PHPhotoLibrary.requestAuthorization(for: .readWrite) { [weak self] _ in
                Task { @MainActor in self?.checkAllPermissions() }
            }
        }
    }

    func grantAllPermissions() {
        for type in PermissionType.allCases where permissionStatuses[type] != .authorized {
            requestPermission(type)
        }
    }

    func openSystemSettings(for type: PermissionType) {
        guard let url = type.settingsURL else { return }
        UIApplication.shared.open(url)
    }

    func showPermissionExplanation() { showPermissionsModal = true }
    var missingPermissions: [PermissionType] { PermissionType.allCases.filter { permissionStatuses[$0] != .authorized } }
    var statusSummary: String {
        let granted = permissionStatuses.values.filter { $0 == .authorized }.count
        return "\(granted)/\(PermissionType.allCases.count) permissions granted"
    }

    func startPermissionPolling() {} // No-op — lifecycle re-checks replace polling
    func stopPermissionPolling() {}
    func restartApp() {} // Not available on iOS

    func performStartupCheck() {
        checkAllPermissions()
        if !allPermissionsGranted {
            showPermissionsModal = true
        }
    }

    func awaitInitialProbes() async {
        // On iOS, permission checks are synchronous — no probes to await
        checkAllPermissions()
    }

    // MARK: - Private Helpers

    /// Checks notification authorization status synchronously by reading cached state.
    /// The async re-check will fire on the next didBecomeActive cycle.
    private var cachedNotificationStatus: PermissionStatus = .notDetermined

    private func checkNotificationPermission() -> PermissionStatus {
        // Kick off async status fetch for next cycle
        UNUserNotificationCenter.current().getNotificationSettings { settings in
            let authStatus = settings.authorizationStatus
            Task { @MainActor [weak self] in
                guard let self else { return }
                let newStatus: PermissionStatus = switch authStatus {
                case .authorized, .provisional, .ephemeral: .authorized
                case .denied: .denied
                case .notDetermined: .notDetermined
                @unknown default: .notDetermined
                }
                if self.cachedNotificationStatus != newStatus {
                    self.cachedNotificationStatus = newStatus
                    self.permissionStatuses[.notifications] = newStatus
                    self.allPermissionsGranted = PermissionType.allCases.allSatisfy {
                        self.permissionStatuses[$0] == .authorized
                    }
                }
            }
        }
        return cachedNotificationStatus
    }

    private func requestNotificationPermission() {
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .badge, .sound]) { [weak self] _, _ in
            Task { @MainActor in self?.checkAllPermissions() }
        }
    }

    private func mapAVAuthorizationStatus(_ status: AVAuthorizationStatus) -> PermissionStatus {
        switch status {
        case .authorized: return .authorized
        case .denied: return .denied
        case .restricted: return .restricted
        case .notDetermined: return .notDetermined
        @unknown default: return .notDetermined
        }
    }

    private func mapPHAuthorizationStatus(_ status: PHAuthorizationStatus) -> PermissionStatus {
        switch status {
        case .authorized, .limited: return .authorized
        case .denied: return .denied
        case .restricted: return .restricted
        case .notDetermined: return .notDetermined
        @unknown default: return .notDetermined
        }
    }
}
#endif
