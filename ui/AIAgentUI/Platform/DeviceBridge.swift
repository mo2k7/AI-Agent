import Foundation
#if canImport(UIKit)
import UIKit
#endif


enum DeviceCapability: String, CaseIterable, Identifiable, Codable {
    case screenCapture = "screen_capture"
    case localWorkspace = "local_workspace"
    case documentImport = "document_import"
    case shareSheet = "share_sheet"
    case openExternalURLs = "open_external_urls"

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .screenCapture: return "Screen Capture"
        case .localWorkspace: return "Local Workspace"
        case .documentImport: return "Document Import"
        case .shareSheet: return "Share Sheet"
        case .openExternalURLs: return "Open External URLs"
        }
    }
}

struct DeviceBridgeManifest: Codable, Equatable {
    let deviceId: String
    let platform: String
    let deviceName: String
    let appVersion: String
    let capabilities: [DeviceCapability]
    let supportedTools: [String]

    var capabilityNames: [String] {
        capabilities.map(\.rawValue).sorted()
    }

    @MainActor
    static func current() -> DeviceBridgeManifest {
        let defaults = UserDefaults.standard
        let deviceIdKey = "deviceBridgeId"
        let deviceId: String
        if let existing = defaults.string(forKey: deviceIdKey), !existing.isEmpty {
            deviceId = existing
        } else {
            let created = UUID().uuidString
            defaults.set(created, forKey: deviceIdKey)
            deviceId = created
        }

        let info = Bundle.main.infoDictionary ?? [:]
        let version = (info["CFBundleShortVersionString"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines)
        let build = (info["CFBundleVersion"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines)
        let appVersion = [version, build].compactMap { value in
            guard let value, !value.isEmpty else { return nil }
            return value
        }.joined(separator: " (")
        let resolvedVersion = appVersion.isEmpty ? "development" : (appVersion.contains("(") ? appVersion + ")" : appVersion)

        return DeviceBridgeManifest(
            deviceId: deviceId,
            platform: currentPlatformName(),
            deviceName: currentDeviceName(),
            appVersion: resolvedVersion,
            capabilities: currentCapabilities(),
            supportedTools: currentSupportedTools()
        )
    }

    /// Tools this device can execute natively via IOSToolExecutor.
    private static func currentSupportedTools() -> [String] {
        #if os(iOS)
        return ["search_files", "read_document", "open_item",
                "read_screen", "browse_web", "manage_notes",
                "generate_image", "create_directory", "grant_folder_access"]
        #elseif os(macOS)
        return []  // Mac uses local backend executor
        #else
        return []
        #endif
    }

    @MainActor
    private static func currentPlatformName() -> String {
        #if os(macOS)
        return "macOS"
        #elseif os(iOS)
        #if targetEnvironment(macCatalyst)
        return "macCatalyst"
        #else
        return UIDevice.current.userInterfaceIdiom == .pad ? "iPadOS" : "iOS"
        #endif
        #else
        return "unknown"
        #endif
    }

    @MainActor
    private static func currentDeviceName() -> String {
        #if os(macOS)
        return Host.current().localizedName ?? "Mac"
        #elseif canImport(UIKit)
        return UIDevice.current.name
        #else
        return "Unknown Device"
        #endif
    }

    private static func currentCapabilities() -> [DeviceCapability] {
        #if os(macOS)
        return [.screenCapture, .localWorkspace, .openExternalURLs]
        #elseif canImport(UIKit)
        return [.localWorkspace, .documentImport, .shareSheet, .openExternalURLs]
        #else
        return []
        #endif
    }
}
