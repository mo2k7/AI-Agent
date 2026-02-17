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
    @Binding var isPresented: Bool
    
    @AppStorage("autoConnect") private var autoConnect = true
    @AppStorage("reconnectOnFailure") private var reconnectOnFailure = true
    @AppStorage("panelOpacity") private var panelOpacity = 0.95
    @AppStorage("animationsEnabled") private var animationsEnabled = true
    @State private var sessionTitleDraft = ""
    
    private var selectedModelBinding: Binding<GeminiModel> {
        Binding(
            get: { appState.selectedModel },
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

    private var responsePresentationStyleBinding: Binding<ResponsePresentationStyle> {
        Binding(
            get: { appState.responsePresentationStyle },
            set: { appState.setResponsePresentationStyle($0) }
        )
    }

    private var readableProHighContrastBinding: Binding<Bool> {
        Binding(
            get: { appState.readableProHighContrastEnabled },
            set: { appState.setReadableProHighContrastEnabled($0) }
        )
    }

    private var streamingAnimationStyleBinding: Binding<StreamingAnimationStyle> {
        Binding(
            get: { appState.streamingAnimationStyle },
            set: { appState.setStreamingAnimationStyle($0) }
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
                    
                    // Model Section
                    settingsSection(title: "AI Model") {
                        Picker("Model", selection: selectedModelBinding) {
                            ForEach(GeminiModel.allCases) { model in
                                Text(model.displayName)
                                    .tag(model)
                            }
                        }
                        .pickerStyle(.menu)
                        .labelsHidden()
                        
                        HStack(spacing: 4) {
                            Text(appState.selectedModel.description)
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

                        Picker("Format Style", selection: responsePresentationStyleBinding) {
                            ForEach(ResponsePresentationStyle.allCases) { style in
                                Text(style.displayName)
                                    .tag(style)
                            }
                        }
                        .pickerStyle(.menu)
                        .labelsHidden()

                        Text(appState.responsePresentationStyle.description)
                            .font(.caption)
                            .foregroundColor(.secondary)

                        Toggle("Readable Pro high contrast", isOn: readableProHighContrastBinding)
                            .disabled(appState.responsePresentationStyle != .readablePro)

                        Text(
                            appState.responsePresentationStyle == .readablePro
                                ? (appState.readableProHighContrastEnabled
                                    ? "Higher contrast is active for maximum readability."
                                    : "Standard Readable Pro contrast is active.")
                                : "Switch to Readable Pro to apply this contrast setting."
                        )
                        .font(.caption)
                        .foregroundColor(.secondary)

                        Picker("Streaming Animation", selection: streamingAnimationStyleBinding) {
                            ForEach(StreamingAnimationStyle.allCases) { style in
                                Text(style.displayName)
                                    .tag(style)
                            }
                        }
                        .pickerStyle(.menu)
                        .labelsHidden()

                        Text(appState.streamingAnimationStyle.description)
                            .font(.caption)
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
            FloatingPanelController.shared.applyAppearancePreferences(
                opacity: panelOpacity,
                animationsEnabled: animationsEnabled
            )
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
        .onChange(of: animationsEnabled) { _, newValue in
            FloatingPanelController.shared.applyAppearancePreferences(
                opacity: panelOpacity,
                animationsEnabled: newValue
            )
        }
    }
    
    // MARK: - Components
    
    private var connectionStatus: some View {
        HStack {
            Text("Status:")
            Spacer()
            HStack(spacing: 4) {
                Circle()
                    .fill(appState.isConnected ? Color.green : Color.red)
                    .frame(width: 8, height: 8)
                Text(appState.isConnected ? "Connected" : "Disconnected")
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
