//
//  InlineSettingsView.swift
//  AIAgentUI
//
//  Created for Personal macOS AI Agent
//  Status: Active - Inline settings panel shown within the main floating panel
//

import SwiftUI

/// Inline settings view displayed as a sheet within the main panel
/// This avoids focus issues with separate settings windows in agent apps
struct InlineSettingsView: View {
    
    @ObservedObject var appState: AppState
    @ObservedObject var connectionState: ConnectionState = .shared
    @ObservedObject var themeState: UIThemeState = .shared
    @Binding var isPresented: Bool
    
    @AppStorage("autoConnect") private var autoConnect = true
    @AppStorage("reconnectOnFailure") private var reconnectOnFailure = true
    @AppStorage("panelOpacity") private var panelOpacity = 0.95
    @AppStorage("animationsEnabled") private var animationsEnabled = true
    @State private var sessionTitleDraft = ""
    @State private var remoteMacEndpoint = UserDefaults.standard.string(forKey: "remote_mac_endpoint") ?? ""
    @State private var remoteMacAuthToken = UserDefaults.standard.string(forKey: "remote_mac_auth_token") ?? ""
    @State private var showAuthToken = false
    @State private var isConnectingRemote = false
    @State private var showTailscaleSetupGuide = false
    
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

    private var executionModeBinding: Binding<ExecutionMode> {
        Binding(
            get: { appState.executionMode },
            set: { appState.setExecutionMode($0) }
        )
    }

    private var deepThinkBinding: Binding<Bool> {
        Binding(
            get: { appState.deepThinkEnabled },
            set: { appState.setDeepThinkEnabled($0) }
        )
    }

    // Styles moved to UIThemeState in $themeState

    private var browseRestrictionProfileBinding: Binding<BrowseRestrictionProfile> {
        Binding(
            get: { appState.browseRestrictionProfile },
            set: { appState.setBrowseRestrictionProfile($0) }
        )
    }
    
    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Text("Settings")
                    .font(.headline)
                    .foregroundColor(.textPrimary)
                
                Spacer()
                
                Button(action: { isPresented = false }) {
                    Image(systemName: "xmark.circle.fill")
                        .font(.system(size: 20))
                        .foregroundColor(.textSecondary)
                }
                .buttonStyle(.plain)
            }
            .padding()
            .background(Color.cardBackground.opacity(0.5))
            
            Divider()
            
            // Settings content
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    // Connection Section
                    settingsSection(title: "Connection") {
                        connectionStatus
                        Toggle("Auto-connect on launch", isOn: $autoConnect)
                        Toggle("Reconnect on failure", isOn: $reconnectOnFailure)
                        
                        Button("Reconnect Now") {
                            Task {
                                await appState.reconnect()
                            }
                        }
                        .buttonStyle(.bordered)
                    }

                    // Connection Mode indicator (both platforms)
                    settingsSection(title: "Connection Mode") {
                        HStack(spacing: 8) {
                            Image(systemName: appState.connectionMode.systemImage)
                                .font(.title3)
                                .foregroundColor(connectionModeColor)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(appState.connectionMode.displayName)
                                    .font(.body.weight(.medium))
                                    .foregroundColor(.textPrimary)
                                Text(connectionModeDescription)
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                            Spacer()
                        }
                    }

                    #if os(macOS)
                    // macOS: show pairing info so user can copy to iOS
                    settingsSection(title: "iOS Pairing (Tailscale)") {
                        if let tailscaleEndpoint = appState.backendLauncher.tailscaleEndpointURL {
                            Label("Tailscale Active", systemImage: "checkmark.circle.fill")
                                .font(.caption.weight(.semibold))
                                .foregroundColor(.green)

                            VStack(alignment: .leading, spacing: 4) {
                                Text("Endpoint URL")
                                    .font(.caption.weight(.semibold))
                                    .foregroundColor(.secondary)
                                HStack {
                                    Text(tailscaleEndpoint)
                                        .font(.system(.body, design: .monospaced))
                                        .foregroundColor(.textPrimary)
                                        .textSelection(.enabled)
                                    Spacer()
                                    Button {
                                        NSPasteboard.general.clearContents()
                                        NSPasteboard.general.setString(tailscaleEndpoint, forType: .string)
                                    } label: {
                                        Image(systemName: "doc.on.doc")
                                            .font(.caption)
                                    }
                                    .buttonStyle(.plain)
                                    .help("Copy endpoint URL")
                                }
                            }

                            if let tailscaleDNSName = appState.backendLauncher.tailscaleDNSName {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text("MagicDNS Hostname")
                                        .font(.caption.weight(.semibold))
                                        .foregroundColor(.secondary)
                                    HStack {
                                        Text(tailscaleDNSName)
                                            .font(.system(.caption, design: .monospaced))
                                            .foregroundColor(.textPrimary)
                                            .textSelection(.enabled)
                                        Spacer()
                                        Button {
                                            NSPasteboard.general.clearContents()
                                            NSPasteboard.general.setString(tailscaleDNSName, forType: .string)
                                        } label: {
                                            Image(systemName: "doc.on.doc")
                                                .font(.caption)
                                        }
                                        .buttonStyle(.plain)
                                        .help("Copy MagicDNS hostname")
                                    }
                                }
                            }

                            if let tailscaleIP = appState.backendLauncher.tailscaleIP {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text("Tailscale IPv4")
                                        .font(.caption.weight(.semibold))
                                        .foregroundColor(.secondary)
                                    HStack {
                                        Text(tailscaleIP)
                                            .font(.system(.caption, design: .monospaced))
                                            .foregroundColor(.textPrimary)
                                            .textSelection(.enabled)
                                        Spacer()
                                        Button {
                                            NSPasteboard.general.clearContents()
                                            NSPasteboard.general.setString(tailscaleIP, forType: .string)
                                        } label: {
                                            Image(systemName: "doc.on.doc")
                                                .font(.caption)
                                        }
                                        .buttonStyle(.plain)
                                        .help("Copy Tailscale IPv4")
                                    }
                                }
                            }

                            VStack(alignment: .leading, spacing: 4) {
                                Text("Auth Token")
                                    .font(.caption.weight(.semibold))
                                    .foregroundColor(.secondary)
                                HStack {
                                    let token = appState.backendLauncher.pairingAuthToken ?? appState.backendLauncher.authToken ?? "—"
                                    if showAuthToken {
                                        Text(token)
                                            .font(.system(.caption, design: .monospaced))
                                            .foregroundColor(.textPrimary)
                                            .textSelection(.enabled)
                                            .lineLimit(1)
                                    } else {
                                        Text(String(repeating: "•", count: min(token.count, 24)))
                                            .font(.system(.caption, design: .monospaced))
                                            .foregroundColor(.textSecondary)
                                    }
                                    Spacer()
                                    Button {
                                        showAuthToken.toggle()
                                    } label: {
                                        Image(systemName: showAuthToken ? "eye.slash" : "eye")
                                            .font(.caption)
                                    }
                                    .buttonStyle(.plain)
                                    Button {
                                        NSPasteboard.general.clearContents()
                                        NSPasteboard.general.setString(token, forType: .string)
                                    } label: {
                                        Image(systemName: "doc.on.doc")
                                            .font(.caption)
                                    }
                                    .buttonStyle(.plain)
                                    .help("Copy auth token")
                                }
                            }

                            Text("Use the endpoint URL and token in the iPhone app. The MagicDNS hostname is preferred because it stays stable when the Tailscale IP changes.")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        } else {
                            Label("Tailscale Not Detected", systemImage: "wifi.slash")
                                .font(.caption.weight(.semibold))
                                .foregroundColor(.secondary)
                            Text("Install Tailscale on this Mac and sign in. The backend is bound to 0.0.0.0 and will accept Tailscale connections automatically.")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                    #endif

                    #if os(iOS)
                    settingsSection(title: "Connect to Mac (Tailscale)") {
                        // Setup guide toggle
                        DisclosureGroup(isExpanded: $showTailscaleSetupGuide) {
                            VStack(alignment: .leading, spacing: 12) {
                                setupStep(
                                    number: 1,
                                    icon: "arrow.down.app",
                                    title: "Install Tailscale on both devices",
                                    detail: "Download Tailscale from the App Store on this iPhone and from tailscale.com on your Mac. Sign in with the same account on both."
                                )

                                setupStep(
                                    number: 2,
                                    icon: "network",
                                    title: "Copy your Mac's Full domain",
                                    detail: "Open Tailscale on your Mac and copy the Full domain. It ends in .ts.net. Do not use the 100.x IPv4 here."
                                )

                                setupStep(
                                    number: 3,
                                    icon: "bolt.fill",
                                    title: "Tap Connect",
                                    detail: "Once connected, your iPhone uses your Mac's full AI backend — screen capture, file system, terminal, and all tools."
                                )
                            }
                        } label: {
                            HStack(spacing: 6) {
                                Image(systemName: "questionmark.circle")
                                    .foregroundColor(.blue)
                                Text("How to set up")
                                    .font(.subheadline.weight(.medium))
                                    .foregroundColor(.blue)
                            }
                        }

                        Divider()

                        // Tailscale address field
                        VStack(alignment: .leading, spacing: 6) {
                            HStack(spacing: 4) {
                                Image(systemName: "network")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                                Text("Mac Full Domain")
                                    .font(.caption.weight(.semibold))
                                    .foregroundColor(.secondary)
                            }
                            TextField("muhammads-macbook-pro.tailxxxx.ts.net", text: $remoteMacEndpoint)
                                .textFieldStyle(.roundedBorder)
                                .autocapitalization(.none)
                                .disableAutocorrection(true)
                                .keyboardType(.URL)
                            if remoteMacEndpoint.isEmpty {
                                Text("Paste the Full domain from Tailscale on your Mac. It must end in .ts.net")
                                    .font(.caption2)
                                    .foregroundColor(.secondary)
                            } else if isDeprecatedRemoteMacAddress(remoteMacEndpoint) {
                                Label("Use the Full domain from Tailscale on your Mac. 100.x IPs are not accepted here.", systemImage: "exclamationmark.triangle.fill")
                                    .font(.caption2)
                                    .foregroundColor(.orange)
                            } else if let endpointPreview = normalizedTailscaleEndpoint(remoteMacEndpoint) {
                                Label("Will connect to \(endpointPreview)", systemImage: "checkmark")
                                    .font(.caption2)
                                    .foregroundColor(.green)
                            } else {
                                Label("Enter your Mac's Full domain from Tailscale. Example: name.tailxxxx.ts.net", systemImage: "exclamationmark.triangle")
                                    .font(.caption2)
                                    .foregroundColor(.orange)
                            }
                        }

                        VStack(alignment: .leading, spacing: 6) {
                            HStack(spacing: 4) {
                                Image(systemName: "key")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                                Text("Mac Pairing Token")
                                    .font(.caption.weight(.semibold))
                                    .foregroundColor(.secondary)
                            }
                            TextField("Paste token from the Mac app", text: $remoteMacAuthToken)
                                .textFieldStyle(.roundedBorder)
                                .autocapitalization(.none)
                                .disableAutocorrection(true)
                            if remoteMacAuthToken.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                                Text("Copy this from the Mac app's Tailscale pairing section")
                                    .font(.caption2)
                                    .foregroundColor(.secondary)
                            } else {
                                Label("Token ready", systemImage: "checkmark")
                                    .font(.caption2)
                                    .foregroundColor(.green)
                            }
                        }

                        // Connect button + status
                        HStack(spacing: 10) {
                            Button(action: {
                                isConnectingRemote = true
                                UserDefaults.standard.set(remoteMacEndpoint.trimmingCharacters(in: .whitespacesAndNewlines), forKey: "remote_mac_endpoint")
                                UserDefaults.standard.set(remoteMacAuthToken.trimmingCharacters(in: .whitespacesAndNewlines), forKey: "remote_mac_auth_token")
                                Task {
                                    await appState.connectToRemoteMac()
                                    isConnectingRemote = false
                                }
                            }) {
                                if isConnectingRemote {
                                    HStack(spacing: 6) {
                                        ProgressView()
                                            .controlSize(.small)
                                        Text("Connecting…")
                                    }
                                } else {
                                    Label("Connect", systemImage: "bolt.fill")
                                }
                            }
                            .buttonStyle(.borderedProminent)
                            .disabled(
                                remoteMacEndpoint.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                                || isDeprecatedRemoteMacAddress(remoteMacEndpoint)
                                || normalizedTailscaleEndpoint(remoteMacEndpoint) == nil
                                || remoteMacAuthToken.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                                || isConnectingRemote
                            )

                            if appState.connectionMode.isRemote {
                                Label("Connected", systemImage: "checkmark.circle.fill")
                                    .font(.caption.weight(.semibold))
                                    .foregroundColor(.green)
                            }
                        }

                        // Error display
                        if let error = appState.lastError, appState.connectionMode == .standalone {
                            HStack(spacing: 4) {
                                Image(systemName: "exclamationmark.triangle.fill")
                                    .foregroundColor(.red)
                                Text(error)
                                    .font(.caption)
                                    .foregroundColor(.red)
                            }
                            .padding(8)
                            .background(Color.red.opacity(0.1))
                            .clipShape(RoundedRectangle(cornerRadius: 6))
                        }

                        // Disconnect
                        if !remoteMacEndpoint.isEmpty {
                            Divider()
                            Button(role: .destructive) {
                                UserDefaults.standard.removeObject(forKey: "remote_mac_endpoint")
                                UserDefaults.standard.removeObject(forKey: "remote_mac_auth_token")
                                remoteMacEndpoint = ""
                                remoteMacAuthToken = ""
                                Task {
                                    await appState.disconnectRemoteAndGoStandalone()
                                }
                            } label: {
                                Label("Disconnect & Use Standalone", systemImage: "wifi.slash")
                                    .font(.caption)
                            }
                        }
                    }
                    #endif

                    settingsSection(title: "Device Info") {
                        Text("Device: \(appState.deviceBridgeManifest.deviceName) · \(appState.deviceBridgeManifest.platform)")
                            .font(.caption)
                            .foregroundColor(.secondary)

                        Text(appState.deviceBridgeManifest.capabilities.map(\.displayName).joined(separator: " · "))
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }
                    
                    // Model Section
                    settingsSection(title: "AI Model") {
                        Picker("Model", selection: selectedModelBinding) {
                            ForEach(appState.modelSelectionOptions) { model in
                                Text(model.resolvedDisplayName)
                                    .tag(model.id)
                            }
                        }
                        .pickerStyle(.menu)
                        .labelsHidden()
                        
                        HStack(spacing: 4) {
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

                    settingsSection(title: "Response Format") {
                        Picker("Execution Mode", selection: executionModeBinding) {
                            ForEach(ExecutionMode.allCases) { mode in
                                Text(mode.displayName)
                                    .tag(mode)
                            }
                        }
                        .pickerStyle(.menu)
                        .labelsHidden()

                        Text(appState.executionMode.description)
                            .font(.caption)
                            .foregroundColor(.secondary)

                        Toggle("Deep Think", isOn: deepThinkBinding)

                        Text(
                            appState.deepThinkEnabled
                                ? (appState.selectedModel.supportsDeepThink
                                    ? "Forces deeper multi-step reasoning with extra verification."
                                    : "Selected model does not support strict Deep Think. Use Gemini 3 or Gemini 2.5.")
                                : "Use standard reasoning depth for faster responses."
                        )
                        .font(.caption)
                        .foregroundColor(.secondary)

                        Picker("Format Style", selection: $themeState.responsePresentationStyle) {
                            ForEach(ResponsePresentationStyle.allCases) { style in
                                Text(style.displayName)
                                    .tag(style)
                            }
                        }
                        .pickerStyle(.menu)
                        .labelsHidden()

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
                                Text(style.displayName)
                                    .tag(style)
                            }
                        }
                        .pickerStyle(.menu)
                        .labelsHidden()

                        Text(themeState.streamingAnimationStyle.description)
                            .font(.caption)
                            .foregroundColor(.secondary)

                        VStack(alignment: .leading, spacing: 6) {
                            Text("Web Browsing")
                                .font(.caption.weight(.semibold))
                                .foregroundColor(.secondary)

                            Picker("Web Browsing", selection: browseRestrictionProfileBinding) {
                                ForEach(BrowseRestrictionProfile.allCases) { profile in
                                    Text(profile.displayName)
                                        .tag(profile)
                                }
                            }
                            .pickerStyle(.menu)
                            .labelsHidden()

                            Text(appState.browseRestrictionProfile.description)
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }

                        VStack(alignment: .leading, spacing: 6) {
                            Text("Verbosity")
                                .font(.caption.weight(.semibold))
                                .foregroundColor(.secondary)

                            Picker("Verbosity", selection: responseVerbosityBinding) {
                                ForEach(ResponseVerbosity.allCases) { verbosity in
                                    Text(verbosity.displayName)
                                        .tag(verbosity)
                                }
                            }
                            .pickerStyle(.menu)
                            .labelsHidden()

                            Text(appState.responseVerbosity.description)
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }

                    settingsSection(title: "Memory & Sessions") {
                        HStack {
                            Text("Active Session")
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
                        .labelsHidden()

                        Text(appState.memoryMode.description)
                            .font(.caption)
                            .foregroundColor(.secondary)

                        HStack(spacing: 8) {
                            Button("New Session") {
                                Task {
                                    await appState.createNewSession()
                                }
                            }
                            .buttonStyle(.borderedProminent)

                            Button("Refresh") {
                                Task {
                                    await appState.refreshSessions()
                                }
                            }
                            .buttonStyle(.bordered)
                        }

                        TextField("Session name", text: $sessionTitleDraft)
                            .textFieldStyle(.roundedBorder)

                        Button("Rename Active Session") {
                            let title = sessionTitleDraft
                            Task {
                                await appState.renameActiveSession(to: title)
                                sessionTitleDraft = appState.activeSessionTitle
                            }
                        }
                        .buttonStyle(.bordered)
                        .disabled(sessionTitleDraft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)

                        Text("Known sessions: \(appState.sessions.count)")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }
                    
                    // Appearance Section
                    settingsSection(title: "Appearance") {
                        Toggle("Enable animations", isOn: $animationsEnabled)
                    }
                }
                .padding()
            }
        }
        .frame(minWidth: 320, minHeight: 350)
        .background(Color.panelBackground)
        .onAppear {
            sessionTitleDraft = appState.activeSessionTitle
            #if os(macOS)
            FloatingPanelController.shared.applyAppearancePreferences(
                opacity: panelOpacity,
                animationsEnabled: animationsEnabled
            )
            #endif
        }
        .onChange(of: appState.activeSessionTitle) { _, newValue in
            sessionTitleDraft = newValue
        }
        .onChange(of: autoConnect) { _, newValue in
            appState.handleAutoConnectPreferenceChanged(newValue)
        }
        .onChange(of: reconnectOnFailure) { _, newValue in
            appState.handleReconnectOnFailurePreferenceChanged(newValue)
        }
        #if os(macOS)
        .onChange(of: animationsEnabled) { _, newValue in
            FloatingPanelController.shared.applyAppearancePreferences(
                opacity: panelOpacity,
                animationsEnabled: newValue
            )
        }
        #endif
    }
    
    // MARK: - Components
    
    private var connectionStatus: some View {
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
    }
    
    private func settingsSection<Content: View>(
        title: String,
        @ViewBuilder content: () -> Content
    ) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(title)
                .font(.subheadline)
                .fontWeight(.semibold)
                .foregroundColor(.textSecondary)
            
            VStack(alignment: .leading, spacing: 10) {
                content()
            }
            .padding()
            .background(
                RoundedRectangle(cornerRadius: 10)
                    .fill(Color.cardBackground)
            )
        }
    }

    // MARK: - Connection Mode Helpers

    private var connectionModeColor: Color {
        switch appState.connectionMode {
        case .localBackend: return .green
        case .remoteMac: return .blue
        case .standalone: return .orange
        case .reconnecting: return .yellow
        case .disconnected: return .red
        }
    }

    private var connectionModeDescription: String {
        switch appState.connectionMode {
        case .localBackend:
            return "Connected to local Python backend with full tool access."
        case .remoteMac(let ip):
            return "Connected to Mac at \(ip) via Tailscale. Full macOS tools available."
        case .standalone:
            return "Running with native iOS tools. Connect to Mac for full capabilities."
        case .reconnecting(let n):
            return "Attempting to reconnect to Mac (\(n)/3)…"
        case .disconnected:
            return "Not connected to any backend."
        }
    }

    private func isValidEndpointURL(_ url: String) -> Bool {
        let trimmed = url.trimmingCharacters(in: .whitespacesAndNewlines)
        return (trimmed.hasPrefix("ws://") || trimmed.hasPrefix("wss://")) && URL(string: trimmed) != nil
    }

    // MARK: - Setup Step Helper

    private func setupStep(number: Int, icon: String, title: String, detail: String) -> some View {
        HStack(alignment: .top, spacing: 10) {
            ZStack {
                Circle()
                    .fill(Color.blue.opacity(0.15))
                    .frame(width: 28, height: 28)
                Text("\(number)")
                    .font(.caption.weight(.bold))
                    .foregroundColor(.blue)
            }

            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 4) {
                    Image(systemName: icon)
                        .font(.caption)
                        .foregroundColor(.blue)
                    Text(title)
                        .font(.subheadline.weight(.semibold))
                        .foregroundColor(.textPrimary)
                }
                Text(detail)
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    /// Returns the normalized remote endpoint preview if the input looks usable.
    private func normalizedTailscaleEndpoint(_ input: String) -> String? {
        let trimmed = input.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        if isValidEndpointURL(trimmed) {
            return isDeprecatedRemoteMacAddress(trimmed) ? nil : trimmed
        }
        let normalizedHost = trimmed.hasSuffix(".") ? String(trimmed.dropLast()) : trimmed
        if isValidTailscaleHostname(normalizedHost) {
            return "wss://\(normalizedHost):8765"
        }
        return nil
    }

    private func isDeprecatedRemoteMacAddress(_ input: String) -> Bool {
        let trimmed = input.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return false }
        let host: String
        if trimmed.hasPrefix("ws://") || trimmed.hasPrefix("wss://") {
            guard let url = URL(string: trimmed), let parsedHost = url.host else { return false }
            host = parsedHost
        } else {
            host = trimmed
        }
        return TailscaleEndpoint.isTailscaleIP(host.hasSuffix(".") ? String(host.dropLast()) : host)
    }

    private func isValidTailscaleHostname(_ input: String) -> Bool {
        let normalized = input.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard normalized.hasSuffix(".ts.net") else { return false }
        let labels = normalized.split(separator: ".")
        guard labels.count >= 3 else { return false }
        let allowed = CharacterSet(charactersIn: "abcdefghijklmnopqrstuvwxyz0123456789-")
        return labels.allSatisfy { label in
            guard !label.isEmpty else { return false }
            return label.unicodeScalars.allSatisfy { allowed.contains($0) }
        }
    }
}

#if DEBUG
struct InlineSettingsView_Previews: PreviewProvider {
    static var previews: some View {
        InlineSettingsView(
            appState: AppState.shared,
            isPresented: .constant(true)
        )
        .frame(width: 350, height: 450)
    }
}
#endif
