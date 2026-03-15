//
//  AIAgentUIApp.swift
//  AIAgentUI
//
//  Created for Personal macOS AI Agent
//  Status: Active - Main app entry point
//

import SwiftUI
#if canImport(ServiceManagement)
import ServiceManagement
#endif

struct GeminiModelOption: Identifiable, Hashable, Codable {
    let name: String
    let displayName: String
    let description: String
    let supportedActions: [String]
    let inputTokenLimit: Int
    let outputTokenLimit: Int
    let isPreview: Bool
    let supportsDeepThink: Bool

    enum CodingKeys: String, CodingKey {
        case name
        case displayName = "display_name"
        case description
        case supportedActions = "supported_actions"
        case inputTokenLimit = "input_token_limit"
        case outputTokenLimit = "output_token_limit"
        case isPreview = "is_preview"
        case supportsDeepThink = "supports_deep_think"
    }

    var id: String { name }

    var resolvedDisplayName: String {
        displayName.isEmpty ? name : displayName
    }

    var resolvedDescription: String {
        if !description.isEmpty {
            return description
        }
        if supportsDeepThink {
            return "Supports native deep-think controls."
        }
        return "Live Gemini model discovered from the backend catalog."
    }

    static func placeholder(name: String) -> GeminiModelOption {
        let normalizedName = name.trimmingCharacters(in: .whitespacesAndNewlines)
        let fallbackName = normalizedName.isEmpty ? "Loading live Gemini catalog…" : normalizedName
        return GeminiModelOption(
            name: normalizedName,
            displayName: fallbackName,
            description: normalizedName.isEmpty
                ? "Model catalog will populate after the backend loads the live Gemini model list."
                : "Stored model selection. Connect to refresh the live Gemini catalog.",
            supportedActions: [],
            inputTokenLimit: 0,
            outputTokenLimit: 0,
            isPreview: Self.isPreviewModelIdentifier(normalizedName),
            supportsDeepThink: Self.supportsDeepThink(modelID: normalizedName)
        )
    }

    static func supportsDeepThink(modelID: String) -> Bool {
        let normalized = modelID.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard normalized.hasPrefix("gemini-") else { return false }
        let versionPart = normalized.dropFirst("gemini-".count)
        var digits = ""
        var components: [Int] = []
        for character in versionPart {
            if character.isNumber {
                digits.append(character)
                continue
            }
            if character == ".", !digits.isEmpty {
                components.append(Int(digits) ?? 0)
                digits.removeAll(keepingCapacity: true)
                continue
            }
            break
        }
        if !digits.isEmpty {
            components.append(Int(digits) ?? 0)
        }
        let major = components.indices.contains(0) ? components[0] : 0
        let minor = components.indices.contains(1) ? components[1] : 0
        if major >= 3 { return true }
        return major == 2 && minor >= 5
    }

    static func isPreviewModelIdentifier(_ modelID: String) -> Bool {
        let normalized = modelID.lowercased()
        return normalized.contains("preview") || normalized.contains("exp") || normalized.contains("experimental")
    }
}

#if os(macOS)

/// Main application entry point
@main
struct AIAgentUIApp: App {
    
    // MARK: - Properties
    
    /// App delegate for handling lifecycle events and hotkeys
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    
    /// Shared app state
    @StateObject private var appState = AppState.shared
    
    // MARK: - Body
    
    var body: some Scene {
        // Hidden window group - we use a floating panel instead
        Settings {
            SettingsView()
                .environmentObject(appState)
        }
        
        // Menu bar extra (optional - for status icon)
        MenuBarExtra("AI Agent", systemImage: "brain") {
            MenuBarView()
                .environmentObject(appState)
        }
    }
}

// MARK: - Settings View

/// Settings window content
struct SettingsView: View {
    
    @EnvironmentObject var appState: AppState
    @State private var selectedTab = "general"
    
    var body: some View {
        TabView(selection: $selectedTab) {
            GeneralSettingsView()
                .tabItem {
                    Label("General", systemImage: "gearshape")
                }
                .tag("general")
            
            ConnectionSettingsView()
                .tabItem {
                    Label("Connection", systemImage: "network")
                }
                .tag("connection")
            
            AppearanceSettingsView()
                .tabItem {
                    Label("Appearance", systemImage: "paintpalette")
                }
                .tag("appearance")
        }
        .frame(width: 450, height: 300)
    }
}

@MainActor
private enum LaunchAtLoginController {
    struct RuntimeSupport {
        let isAvailable: Bool
        let message: String
    }

    static func runtimeSupport() -> RuntimeSupport {
        #if canImport(ServiceManagement)
        if #available(macOS 13.0, *) {
            if Bundle.main.bundleURL.pathExtension.lowercased() != "app" {
                return RuntimeSupport(
                    isAvailable: false,
                    message: "Unavailable in development runtime. Use the packaged app build to enable Launch at login."
                )
            }
            return RuntimeSupport(
                isAvailable: true,
                message: "Available in this runtime."
            )
        }
        #endif
        return RuntimeSupport(
            isAvailable: false,
            message: "Requires macOS 13+ ServiceManagement support."
        )
    }

    static func currentState(defaultValue: Bool) -> Bool {
        guard runtimeSupport().isAvailable else {
            return defaultValue
        }
        #if canImport(ServiceManagement)
        if #available(macOS 13.0, *) {
            switch SMAppService.mainApp.status {
            case .enabled:
                return true
            case .notRegistered, .notFound, .requiresApproval:
                return false
            @unknown default:
                return false
            }
        }
        #endif
        return defaultValue
    }

    static func setEnabled(_ enabled: Bool) throws {
        let support = runtimeSupport()
        guard support.isAvailable else {
            throw NSError(
                domain: "AIAgentUI.Settings",
                code: -1,
                userInfo: [NSLocalizedDescriptionKey: support.message]
            )
        }
        #if canImport(ServiceManagement)
        if #available(macOS 13.0, *) {
            let service = SMAppService.mainApp
            if enabled {
                if service.status != .enabled {
                    try service.register()
                }
            } else if service.status == .enabled {
                try service.unregister()
            }
            return
        }
        #endif
        throw NSError(
            domain: "AIAgentUI.Settings",
            code: -1,
            userInfo: [NSLocalizedDescriptionKey: "Launch at login is not supported on this system configuration."]
        )
    }
}

// MARK: - General Settings

struct GeneralSettingsView: View {
    
    @EnvironmentObject var appState: AppState
    @AppStorage("launchAtLogin") private var launchAtLogin = false
    @AppStorage("showInDock") private var showInDock = true
    @AppStorage("enableSnapping") private var enableSnapping = true
    @State private var launchSyncTarget: Bool?

    private var launchAtLoginSupport: LaunchAtLoginController.RuntimeSupport {
        LaunchAtLoginController.runtimeSupport()
    }
    
    var body: some View {
        Form {
            Section("Startup") {
                Toggle("Launch at login", isOn: $launchAtLogin)
                    .disabled(!launchAtLoginSupport.isAvailable)
                Text(launchAtLoginStatusText)
                    .font(.caption2)
                    .foregroundColor(launchAtLoginStatusColor)
                Toggle("Show in Dock", isOn: $showInDock)
            }
            
            Section("Window Behavior") {
                Toggle("Enable edge snapping", isOn: $enableSnapping)
            }
            
            Section("Hotkey") {
                HStack {
                    Text("Toggle panel:")
                    Spacer()
                    Text("⌘K / ⇧⌘K / ⌥⌘K")
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(Color.secondary.opacity(0.2))
                        .cornerRadius(4)
                }
            }
        }
        .formStyle(.grouped)
        .padding()
        .onAppear {
            syncLaunchAtLoginState()
            PanelPositionManager.shared.isSnappingEnabled = enableSnapping
        }
        .onChange(of: launchAtLogin) { _, newValue in
            if launchSyncTarget == newValue {
                launchSyncTarget = nil
                return
            }
            do {
                try LaunchAtLoginController.setEnabled(newValue)
                appState.lastError = nil
            } catch {
                appState.lastError = "Launch at login could not be updated: \(error.localizedDescription)"
                syncLaunchAtLoginState()
            }
        }
        .onChange(of: showInDock) { _, newValue in
            AppDelegate.applyDockVisibility(newValue)
        }
        .onChange(of: enableSnapping) { _, newValue in
            PanelPositionManager.shared.isSnappingEnabled = newValue
        }
    }

    private func syncLaunchAtLoginState() {
        let resolvedState = LaunchAtLoginController.currentState(defaultValue: launchAtLogin)
        guard resolvedState != launchAtLogin else { return }
        launchSyncTarget = resolvedState
        launchAtLogin = resolvedState
    }

    private var launchAtLoginStatusText: String {
        if launchAtLoginSupport.isAvailable {
            return launchAtLogin ? "Launch at login is enabled." : "Launch at login is disabled."
        }
        return launchAtLoginSupport.message
    }

    private var launchAtLoginStatusColor: Color {
        launchAtLoginSupport.isAvailable ? .secondary : .orange
    }
}

// MARK: - Connection Settings

struct ConnectionSettingsView: View {
    
    @EnvironmentObject var appState: AppState
    @ObservedObject var connectionState: ConnectionState = .shared
    @ObservedObject var themeState: UIThemeState = .shared
    @AppStorage("autoConnect") private var autoConnect = true
    @AppStorage("reconnectOnFailure") private var reconnectOnFailure = true
    
    private var selectedModelBinding: Binding<String> {
        Binding(
            get: { appState.selectedModelId },
            set: { appState.setSelectedModel($0) }
        )
    }

    private var selectedMemoryModeBinding: Binding<SessionMemoryMode> {
        Binding(
            get: { appState.memoryMode },
            set: { appState.setMemoryMode($0) }
        )
    }

    private var responseVerbosityBinding: Binding<ResponseVerbosity> {
        Binding(
            get: { appState.responseVerbosity },
            set: { appState.setResponseVerbosity($0) }
        )
    }

    private var deepThinkBinding: Binding<Bool> {
        Binding(
            get: { appState.deepThinkEnabled },
            set: { appState.setDeepThinkEnabled($0) }
        )
    }

    // Style properties moved to UIThemeState in $themeState

    private var browseRestrictionProfileBinding: Binding<BrowseRestrictionProfile> {
        Binding(
            get: { appState.browseRestrictionProfile },
            set: { appState.setBrowseRestrictionProfile($0) }
        )
    }
    
    var body: some View {
        Form {
            Section("Connection") {
                HStack {
                    Text("Status:")
                    Spacer()
                    HStack(spacing: 4) {
                        Circle()
                            .fill(connectionState.isConnected ? Color.green : Color.red)
                            .frame(width: 8, height: 8)
                        Text(connectionState.isConnected ? "Connected" : "Disconnected")
                            .foregroundColor(.secondary)
                    }
                }
                
                Toggle("Auto-connect on launch", isOn: $autoConnect)
                Toggle("Reconnect on failure", isOn: $reconnectOnFailure)

                Text("Registered capabilities: \(appState.deviceBridgeManifest.capabilities.map(\.displayName).joined(separator: ", "))")
                    .font(.caption2)
                    .foregroundColor(.secondary)
            }

            
            Section("AI Model") {
                Picker("Model", selection: selectedModelBinding) {
                    ForEach(appState.modelSelectionOptions) { model in
                        Text(model.resolvedDisplayName)
                            .tag(model.id)
                    }
                }
                .pickerStyle(.menu)
                
                HStack {
                    Text(appState.selectedModel.resolvedDescription)
                    if appState.selectedModel.isPreview {
                        Text("•")
                        Text("Preview")
                            .foregroundColor(.orange)
                    }
                }
                .font(.caption)
                .foregroundColor(.secondary)
                
                Text("✓ Model selection is saved immediately")
                    .font(.caption2)
                    .foregroundColor(.green)
            }

            Section("Response Format") {
                Picker("Format Style", selection: $themeState.responsePresentationStyle) {
                    ForEach(ResponsePresentationStyle.allCases) { style in
                        Text(style.displayName).tag(style)
                    }
                }
                .pickerStyle(.menu)

                Text(themeState.responsePresentationStyle.description)
                    .font(.caption)
                    .foregroundColor(.secondary)

                Toggle("Readable Pro high contrast", isOn: $themeState.readableProHighContrastEnabled)
                    .disabled(themeState.responsePresentationStyle != .readablePro)

                Text(
                    themeState.responsePresentationStyle == .readablePro
                        ? (themeState.readableProHighContrastEnabled
                            ? "Higher contrast is active for maximum readability."
                            : "Standard Readable Pro contrast is active.")
                        : "Switch to Readable Pro to apply this contrast setting."
                )
                .font(.caption)
                .foregroundColor(.secondary)

                Picker("Streaming Animation", selection: $themeState.streamingAnimationStyle) {
                    ForEach(StreamingAnimationStyle.allCases) { style in
                        Text(style.displayName).tag(style)
                    }
                }
                .pickerStyle(.menu)

                Text(themeState.streamingAnimationStyle.description)
                    .font(.caption)
                    .foregroundColor(.secondary)

                Picker("Web Browsing", selection: browseRestrictionProfileBinding) {
                    ForEach(BrowseRestrictionProfile.allCases) { profile in
                        Text(profile.displayName).tag(profile)
                    }
                }
                .pickerStyle(.menu)

                Text(appState.browseRestrictionProfile.description)
                    .font(.caption)
                    .foregroundColor(.secondary)

                Picker("Verbosity", selection: responseVerbosityBinding) {
                    ForEach(ResponseVerbosity.allCases) { verbosity in
                        Text(verbosity.displayName).tag(verbosity)
                    }
                }
                .pickerStyle(.menu)

                Text(appState.responseVerbosity.description)
                    .font(.caption)
                    .foregroundColor(.secondary)

                Toggle("Deep Think", isOn: deepThinkBinding)

                Text(
                    appState.deepThinkEnabled
                        ? (appState.selectedModel.supportsDeepThink
                            ? "Forces deeper multi-step reasoning with verification before final answers."
                            : "Selected model does not support strict Deep Think. Use Gemini 3 or Gemini 2.5.")
                        : "Standard reasoning depth for faster turn-around."
                )
                .font(.caption)
                .foregroundColor(.secondary)

                Text("✓ Verbosity applies to all new replies immediately")
                    .font(.caption2)
                    .foregroundColor(.green)
            }

            Section("Memory & Sessions") {
                HStack {
                    Text("Active session")
                    Spacer()
                    Text(appState.activeSessionTitle)
                        .lineLimit(1)
                        .foregroundColor(.secondary)
                }

                Picker("Memory Mode", selection: selectedMemoryModeBinding) {
                    ForEach(SessionMemoryMode.allCases) { mode in
                        Text(mode.displayName).tag(mode)
                    }
                }
                .pickerStyle(.menu)

                HStack {
                    Button("New Session") {
                        Task {
                            await appState.createNewSession()
                        }
                    }

                    Button("Refresh Sessions") {
                        Task {
                            await appState.refreshSessions()
                        }
                    }
                }
            }
            
            Section {
                Button("Reconnect Now") {
                    Task {
                        await appState.reconnect()
                    }
                }
            }
        }
        .formStyle(.grouped)
        .padding()
        .onChange(of: autoConnect) { _, newValue in
            appState.handleAutoConnectPreferenceChanged(newValue)
        }
        .onChange(of: reconnectOnFailure) { _, newValue in
            appState.handleReconnectOnFailurePreferenceChanged(newValue)
        }

    }
}

// MARK: - Appearance Settings

struct AppearanceSettingsView: View {
    
    @AppStorage("panelOpacity") private var panelOpacity = 0.95
    @AppStorage("animationsEnabled") private var animationsEnabled = true
    
    var body: some View {
        Form {
            Section("Panel") {
                HStack {
                    Text("Opacity")
                    Slider(value: $panelOpacity, in: 0.5...1.0)
                    Text("\(Int(panelOpacity * 100))%")
                        .frame(width: 40)
                }
            }
            
            Section("Animations") {
                Toggle("Enable animations", isOn: $animationsEnabled)
            }
        }
        .formStyle(.grouped)
        .padding()
        .onAppear {
            FloatingPanelController.shared.applyAppearancePreferences(
                opacity: panelOpacity,
                animationsEnabled: animationsEnabled
            )
        }
        .onChange(of: panelOpacity) { _, newValue in
            FloatingPanelController.shared.applyAppearancePreferences(
                opacity: newValue,
                animationsEnabled: animationsEnabled
            )
        }
        .onChange(of: animationsEnabled) { _, newValue in
            FloatingPanelController.shared.applyAppearancePreferences(
                opacity: panelOpacity,
                animationsEnabled: newValue
            )
        }
    }
}

// MARK: - Menu Bar View

/// Menu bar dropdown content
struct MenuBarView: View {
    
    @EnvironmentObject var appState: AppState
    @ObservedObject var connectionState: ConnectionState = .shared
    
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Status row
            HStack {
                Circle()
                    .fill(connectionState.isConnected ? Color.green : Color.red)
                    .frame(width: 8, height: 8)
                Text(connectionState.isConnected ? "Connected" : "Disconnected")
                    .foregroundColor(.secondary)
            }
            .padding(.horizontal)
            .padding(.vertical, 8)
            
            Divider()
            
            // Actions
            Button(action: { FloatingPanelController.shared.toggle() }) {
                Label(
                    appState.isPanelVisible ? "Hide Panel" : "Show Panel",
                    systemImage: appState.isPanelVisible ? "eye.slash" : "eye"
                )
            }
            .keyboardShortcut("k", modifiers: .command)
            
            Button(action: { Task { await appState.reconnect() } }) {
                Label("Reconnect", systemImage: "arrow.clockwise")
            }
            .disabled(connectionState.isConnected)
            
            Divider()
            
            Button(action: { NSApplication.shared.terminate(nil) }) {
                Label("Quit AI Agent", systemImage: "power")
            }
            .keyboardShortcut("q", modifiers: .command)
        }
        .frame(width: 200)
    }
}

#else

@main
struct AIAgentUIApp: App {
    @StateObject private var appState = AppState.shared

    var body: some Scene {
        WindowGroup {
            MainPanelView(appState: appState)
                .background(Color.panelBackground.ignoresSafeArea())
                .task {
                    await appState.startup()
                }
        }
    }
}

#endif
