//
//  PermissionsView.swift
//  AIAgentUI
//
//  Created for Personal macOS AI Agent
//  Status: Active - Displays and manages macOS permissions
//

import SwiftUI

/// Main view for displaying and managing permissions
struct PermissionsView: View {
    @ObservedObject var permissionsManager = PermissionsManager.shared
    
    var body: some View {
        VStack(spacing: 0) {
            // Header
            header
            
            Divider()
            
            // Permission list
            ScrollView {
                VStack(spacing: ThemeConstants.spacingM) {
                    ForEach(PermissionType.allCases) { permission in
                        PermissionRow(
                            permission: permission,
                            status: permissionsManager.permissionStatuses[permission] ?? .notDetermined,
                            onRequest: {
                                permissionsManager.requestPermission(permission)
                            },
                            onOpenSettings: {
                                permissionsManager.openSystemSettings(for: permission)
                            }
                        )
                    }
                }
                .padding(ThemeConstants.spacingL)
            }
            
            Divider()
            
            // Footer
            footer
        }
        .frame(width: 520, height: 620)
        .background(Color.panelBackground)
        .overlay {
            // Guidance overlay for System Settings
            if let guidanceType = permissionsManager.activeGuidance {
                GuidanceOverlay(
                    title: "Grant \(guidanceType.rawValue)",
                    message: "System Settings has been opened. Find 'AI Agent' in the list and toggle the switch to enable it." + (guidanceType == .fullDiskAccess ? "\n\nYou may need to restart the app for this change to take effect." : ""),
                    onDismiss: { permissionsManager.activeGuidance = nil },
                    showRestart: guidanceType == .fullDiskAccess,
                    onRestart: { permissionsManager.restartApp() }
                )
            }
            
            if let bulkTypes = permissionsManager.bulkGuidanceTypes {
                GuidanceOverlay(
                    title: "Complete Permission Setup",
                    message: "System Settings has been opened. Please enable the following permissions:\n\n• " + bulkTypes.map { $0.rawValue }.joined(separator: "\n• ") + (bulkTypes.contains(.fullDiskAccess) ? "\n\nYou may need to restart the app for Full Disk Access to take effect." : ""),
                    onDismiss: { permissionsManager.bulkGuidanceTypes = nil },
                    showRestart: bulkTypes.contains(.fullDiskAccess),
                    onRestart: { permissionsManager.restartApp() }
                )
            }
        }
    }
    
    // MARK: - Header
    
    private var header: some View {
        VStack(spacing: ThemeConstants.spacingS) {
            Image(systemName: "lock.shield")
                .font(.system(size: 48))
                .foregroundColor(.primaryBlue)
            
            Text("System Permissions Required")
                .font(.title2.bold())
                .foregroundColor(.textPrimary)
            
            Text("AI Agent needs the following permissions to function properly. These permissions allow the agent to control your Mac and automate tasks on your behalf.")
                .font(.body)
                .foregroundColor(.textSecondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, ThemeConstants.spacingL)
        }
        .padding(.vertical, ThemeConstants.spacingL)
    }
    
    // MARK: - Footer
    
    private var footer: some View {
        VStack(spacing: ThemeConstants.spacingM) {
            // Grant All button (if there are missing permissions)
            if !permissionsManager.allPermissionsGranted {
                Button(action: {
                    permissionsManager.grantAllPermissions()
                }) {
                    HStack(spacing: 8) {
                        Image(systemName: "checkmark.shield")
                        Text("Grant All Permissions")
                    }
                    .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .tint(.primaryBlue)
                .controlSize(.large)
            }
            
            HStack {
                // Status summary
                Text(permissionsManager.statusSummary)
                    .font(.caption)
                    .foregroundColor(.textTertiary)
                
                Spacer()
                
                // Refresh button
                Button(action: {
                    permissionsManager.checkAllPermissions()
                }) {
                    Label("Refresh", systemImage: "arrow.clockwise")
                }
                .buttonStyle(.plain)
                .foregroundColor(.primaryBlue)
                
                // Continue button (only when all permissions are granted)
                if permissionsManager.allPermissionsGranted {
                    Button("Continue") {
                        permissionsManager.showPermissionsModal = false
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(.green)
                }
            }
        }
        .padding(ThemeConstants.spacingM)
    }
}

// MARK: - Guidance Overlay

struct GuidanceOverlay: View {
    let title: String
    let message: String
    let onDismiss: () -> Void
    var showRestart: Bool = false
    var onRestart: (() -> Void)? = nil
    
    var body: some View {
        ZStack {
            Color.black.opacity(0.4)
                .ignoresSafeArea()
            
            VStack(spacing: ThemeConstants.spacingL) {
                Image(systemName: "switch.2")
                    .font(.system(size: 48))
                    .foregroundColor(.primaryBlue)
                
                Text(title)
                    .font(.title3.bold())
                    .foregroundColor(.textPrimary)
                
                Text(message)
                    .font(.body)
                    .foregroundColor(.textSecondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal)
                
                VStack(spacing: ThemeConstants.spacingM) {
                    Button("I've Enabled It") {
                        onDismiss()
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(.primaryBlue)
                    .controlSize(.large)
                    
                    if showRestart {
                        Button("Restart App") {
                            onRestart?()
                        }
                        .buttonStyle(.bordered)
                        .tint(.orange)
                    }
                }
            }
            .padding(ThemeConstants.spacingXL)
            .frame(maxWidth: 400)
            .background(Color.panelBackground)
            .clipShape(RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusLarge))
            .shadow(radius: 20)
        }
    }
}

// MARK: - Permission Row

struct PermissionRow: View {
    let permission: PermissionType
    let status: PermissionStatus
    let onRequest: () -> Void
    let onOpenSettings: () -> Void
    
    var body: some View {
        HStack(spacing: ThemeConstants.spacingM) {
            // Icon
            Image(systemName: permission.symbolName)
                .font(.title2)
                .foregroundColor(.primaryBlue)
                .frame(width: 40)
            
            // Info
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(permission.rawValue)
                        .font(.headline)
                        .foregroundColor(.textPrimary)
                    
                    Spacer()
                    
                    // Status badge
                    StatusBadge(status: status)
                }
                
                Text(permission.description)
                    .font(.caption)
                    .foregroundColor(.textSecondary)
                    .lineLimit(2)
            }
            
            // Action button
            actionButton
        }
        .padding(ThemeConstants.spacingM)
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusMedium))
        .overlay(
            RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusMedium)
                .stroke(borderColor, lineWidth: 1)
        )
    }
    
    @ViewBuilder
    private var actionButton: some View {
        switch status {
        case .authorized:
            Image(systemName: "checkmark.circle.fill")
                .foregroundColor(.green)
                .font(.title2)
        case .denied, .restricted:
            Button("Open Settings") {
                onOpenSettings()
            }
            .buttonStyle(.bordered)
            .tint(.orange)
        case .notDetermined:
            Button(action: onRequest) {
                HStack(spacing: 4) {
                    Image(systemName: "shield.checkered")
                        .font(.caption)
                    Text("Grant")
                }
            }
            .buttonStyle(.borderedProminent)
            .tint(.primaryBlue)
        }
    }
    
    private var borderColor: Color {
        switch status {
        case .authorized:
            return Color.green.opacity(0.3)
        case .denied, .restricted:
            return Color.red.opacity(0.3)
        case .notDetermined:
            return Color.glassStroke
        }
    }
}

// MARK: - Status Badge

struct StatusBadge: View {
    let status: PermissionStatus
    
    var body: some View {
        Text(status.displayName)
            .font(.caption.bold())
            .foregroundColor(foregroundColor)
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(backgroundColor)
            .clipShape(Capsule())
    }
    
    private var foregroundColor: Color {
        switch status {
        case .authorized: return .green
        case .denied: return .red
        case .notDetermined: return .orange
        case .restricted: return .gray
        }
    }
    
    private var backgroundColor: Color {
        switch status {
        case .authorized: return .green.opacity(0.15)
        case .denied: return .red.opacity(0.15)
        case .notDetermined: return .orange.opacity(0.15)
        case .restricted: return .gray.opacity(0.15)
        }
    }
}

// MARK: - Compact Permission Indicator

/// A compact indicator showing overall permission status
struct PermissionIndicator: View {
    @ObservedObject var permissionsManager = PermissionsManager.shared
    
    var body: some View {
        Button(action: {
            permissionsManager.showPermissionsModal = true
        }) {
            HStack(spacing: 4) {
                Image(systemName: statusIcon)
                    .foregroundColor(statusColor)
                
                if !permissionsManager.allPermissionsGranted {
                    Text("Permissions")
                        .font(.caption)
                        .foregroundColor(.textSecondary)
                }
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(statusColor.opacity(0.15))
            .clipShape(Capsule())
        }
        .buttonStyle(.plain)
        .help(permissionsManager.allPermissionsGranted ? 
              "All permissions granted" : 
              "Some permissions missing - click to review")
    }
    
    private var statusIcon: String {
        if permissionsManager.allPermissionsGranted {
            return "lock.shield.fill"
        } else {
            return "exclamationmark.shield.fill"
        }
    }
    
    private var statusColor: Color {
        permissionsManager.allPermissionsGranted ? .green : .orange
    }
}

// MARK: - Alert Version

/// An alert-style permission request for first-time setup
struct PermissionAlert: View {
    @ObservedObject var permissionsManager = PermissionsManager.shared
    let onDismiss: () -> Void
    
    var body: some View {
        VStack(spacing: ThemeConstants.spacingL) {
            // Icon
            Image(systemName: "shield.lefthalf.filled.badge.checkmark")
                .font(.system(size: 64))
                .foregroundColor(.primaryBlue)
                .symbolRenderingMode(.hierarchical)
            
            // Title
            Text("Allow AI Agent to Control Your Mac")
                .font(.title2.bold())
                .foregroundColor(.textPrimary)
                .multilineTextAlignment(.center)
            
            // Description
            Text("AI Agent needs permission to interact with other apps and the system. This includes:")
                .font(.body)
                .foregroundColor(.textSecondary)
                .multilineTextAlignment(.center)
            
            // Permission list
            VStack(alignment: .leading, spacing: 12) {
                permissionBullet("Accessibility", "Control windows and UI elements")
                permissionBullet("Automation", "Run AppleScript commands")
                permissionBullet("Full Disk Access", "Read and write files")
            }
            .padding()
            .background(Color.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusMedium))
            
            // Security note
            HStack(spacing: 8) {
                Image(systemName: "lock.fill")
                    .foregroundColor(.green)
                Text("Your data stays on your Mac. AI Agent never sends personal data to external servers without your explicit consent.")
                    .font(.caption)
                    .foregroundColor(.textSecondary)
            }
            .padding()
            .background(Color.green.opacity(0.1))
            .clipShape(RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusSmall))
            
            // Actions
            VStack(spacing: ThemeConstants.spacingM) {
                // Grant All
                Button(action: {
                    permissionsManager.grantAllPermissions()
                }) {
                    HStack(spacing: 8) {
                        Image(systemName: "checkmark.shield")
                        Text("Grant All Permissions")
                    }
                    .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .tint(.primaryBlue)
                .controlSize(.large)
                
                HStack(spacing: ThemeConstants.spacingM) {
                    Button("Later") {
                        onDismiss()
                    }
                    .buttonStyle(.bordered)
                    
                    Button("Review Individual") {
                        permissionsManager.showPermissionsModal = true
                    }
                    .buttonStyle(.bordered)
                }
            }
        }
        .padding(ThemeConstants.spacingXL)
        .frame(maxWidth: 450)
        .background(Color.panelBackground)
        .clipShape(RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusLarge))
        .shadow(color: .black.opacity(0.3), radius: 20, y: 10)
    }
    
    private func permissionBullet(_ title: String, _ description: String) -> some View {
        HStack(spacing: 12) {
            Image(systemName: "checkmark.circle.fill")
                .foregroundColor(.primaryBlue)
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.subheadline.bold())
                    .foregroundColor(.textPrimary)
                Text(description)
                    .font(.caption)
                    .foregroundColor(.textTertiary)
            }
        }
    }
}

// MARK: - Permissions Overlay

/// Full-screen overlay wrapper for PermissionsView.
/// Uses a ZStack overlay instead of .sheet() because .sheet() on an NSPanel
/// with hidden titlebar renders invisibly while still blocking all interaction,
/// causing the app to appear frozen.
struct PermissionsOverlayView: View {
    @ObservedObject var permissionsManager: PermissionsManager

    var body: some View {
        ZStack {
            Color.black.opacity(0.4)
                .ignoresSafeArea()

            VStack(spacing: 0) {
                // Always-visible close button (prevents permanent freeze)
                HStack {
                    Spacer()
                    Button(action: { permissionsManager.showPermissionsModal = false }) {
                        Image(systemName: "xmark.circle.fill")
                            .font(.system(size: 20))
                            .foregroundColor(.secondary)
                    }
                    .buttonStyle(.plain)
                    .help("Dismiss (review later from the menu)")
                }
                .padding(.trailing, ThemeConstants.spacingM)
                .padding(.top, ThemeConstants.spacingS)

                PermissionsView(permissionsManager: permissionsManager)
            }
            .frame(width: 520, height: 660)
            .background(
                RoundedRectangle(cornerRadius: 20)
                    .fill(.ultraThinMaterial)
                    .shadow(color: .black.opacity(0.3), radius: 20, x: 0, y: 10)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 20)
                    .stroke(Color.white.opacity(0.2), lineWidth: 1)
            )
            .clipShape(RoundedRectangle(cornerRadius: 20))
        }
        .transition(.opacity.combined(with: .scale(scale: 0.95)))
    }
}

// MARK: - Preview

#if DEBUG
struct PermissionsView_Previews: PreviewProvider {
    static var previews: some View {
        PermissionsView()
            .preferredColorScheme(.dark)
        
        PermissionAlert(onDismiss: {})
            .preferredColorScheme(.dark)
            .padding()
            .background(Color.black.opacity(0.5))
    }
}
#endif
