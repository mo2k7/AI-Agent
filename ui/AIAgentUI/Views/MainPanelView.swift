//
//  MainPanelView.swift
//  AIAgentUI
//
//  Created for Personal macOS AI Agent
//  Status: Active - Root container view
//

import SwiftUI
import UniformTypeIdentifiers

/// Main container view for the floating AI Agent panel
struct MainPanelView: View {

    private enum SessionDeleteTarget: Identifiable {
        case single(SessionListItem)
        case batch([SessionListItem])

        var id: String {
            switch self {
            case .single(let session):
                return "single:\(session.sessionId)"
            case .batch(let sessions):
                let ids = sessions.map(\.sessionId).sorted().joined(separator: ",")
                return "batch:\(ids)"
            }
        }
    }
    
    // MARK: - State
    
    @ObservedObject var appState: AppState
    @ObservedObject var permissionsManager = PermissionsManager.shared
    @State private var showSettingsSheet = false
    @State private var showRenameSessionSheet = false
    @State private var showSessionManagerSheet = false
    @State private var renameSessionDraft = ""
    @State private var isFileDropTargeted = false
    @State private var selectedSessionIdsForBulkDelete: Set<String> = []
    @State private var pendingSessionDeleteTarget: SessionDeleteTarget?
    @State private var isSessionDeleteDialogPresented = false
    @State private var isDeletingSelectedSessions = false
    
    // MARK: - Body
    
    var body: some View {
        ZStack {
            // Main panel content
            // IMPORTANT: Do NOT use .drawingGroup() on views containing text input!
            // The drawingGroup modifier flattens views into a Metal texture which breaks
            // the macOS Input Method framework, causing the yellow "prohibited input" banner.
            VStack(spacing: 0) {
                // Header
                headerView
                
                Divider()
                    .background(Color.glassStroke)
                
                // Content area
                contentArea

                Divider()
                    .background(Color.glassStroke)
                
                // Input area
                inputArea
            }
            .frame(
                minWidth: ThemeConstants.panelMinWidth,
                idealWidth: ThemeConstants.panelWidth,
                maxWidth: .infinity,
                minHeight: ThemeConstants.panelMinHeight,
                idealHeight: ThemeConstants.panelHeight,
                maxHeight: .infinity
            )
            .liquidGlass()
            .overlay(
                RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusMedium)
                    .stroke(
                        isFileDropTargeted ? Color.primaryBlue.opacity(0.65) : Color.clear,
                        lineWidth: 2
                    )
            )
            .onDrop(
                of: [UTType.fileURL.identifier],
                isTargeted: $isFileDropTargeted,
                perform: handleFileDrop(providers:)
            )
            // REMOVED: .drawingGroup(opaque: false, colorMode: .nonLinear)
            // This was causing the yellow prohibition banner on text input
            
            // Permissions overlay (rendered in ZStack instead of .sheet() because
            // .sheet() on NSPanel with hidden titlebar is invisible but modal)
            if permissionsManager.showPermissionsModal {
                PermissionsOverlayView(permissionsManager: permissionsManager)
            }

            // Startup overlay (shown during initialization — on top of permissions)
            StartupOverlay(appState: appState)
        }
        // NOTE: These sheets may also be invisible on NSPanel with hidden titlebar.
        // Convert to ZStack overlays if users report frozen UI when opening settings/sessions.
        // For now, users can press Escape to dismiss these sheets.
        .sheet(isPresented: $showSettingsSheet) {
            InlineSettingsView(appState: appState, isPresented: $showSettingsSheet)
        }
        .sheet(isPresented: $showRenameSessionSheet) {
            renameSessionSheet
        }
        .sheet(isPresented: $showSessionManagerSheet) {
            sessionManagerSheet
        }
        .alert(
            "Approve Destructive Operation",
            isPresented: Binding(
                get: { appState.pendingDestructiveToolCall != nil },
                set: { isPresented in
                    if !isPresented {
                        Task {
                            await appState.respondToDestructiveToolConfirmation(approved: false)
                        }
                    }
                }
            )
        ) {
            Button("Deny", role: .destructive) {
                Task {
                    await appState.respondToDestructiveToolConfirmation(approved: false)
                }
            }
            Button("Approve") {
                Task {
                    await appState.respondToDestructiveToolConfirmation(approved: true)
                }
            }
        } message: {
            if let pending = appState.pendingDestructiveToolCall {
                Text(
                    "Tool `\(pending.name)` wants to modify files.\n\nArguments: \(pending.argumentsSummary)"
                )
            } else {
                Text("Approve this file operation?")
            }
        }
    }
    
    // MARK: - Header View
    
    private var headerView: some View {
        HStack(spacing: ThemeConstants.spacingS) {
            // App icon
            Image(systemName: "brain")
                .font(.system(size: 18))
                .foregroundColor(.primaryBlue)
            
            Text("AI Agent")
                .font(.headline)
                .foregroundColor(.textPrimary)

            Text(appState.activeSessionTitle)
                .font(.caption2)
                .foregroundColor(.textSecondary)
                .lineLimit(1)
                .frame(maxWidth: 160, alignment: .leading)

            executionModeBadge
            deepThinkBadge
            
            Spacer()
            
            // Permission indicator (if missing permissions)
            if !permissionsManager.allPermissionsGranted {
                PermissionIndicator()
            }
            
            // Notes toggle
            Button(action: { appState.toggleNotesPanel() }) {
                Image(systemName: appState.isNotesPanelVisible ? "note.text" : "note.text.badge.plus")
                    .font(.system(size: 13))
                    .foregroundColor(appState.isNotesPanelVisible ? .primaryBlue : .textSecondary)
            }
            .buttonStyle(.plain)
            .help("Toggle Notes (Cmd+Shift+N)")

            // Connection status
            connectionIndicator

            // Menu button
            menuButton
        }
        .padding(.horizontal, ThemeConstants.spacingM)
        .padding(.vertical, ThemeConstants.spacingS)
        .background(Color.clear)
    }
    
    private var connectionIndicator: some View {
        HStack(spacing: ThemeConstants.spacingXS) {
            Circle()
                .fill(appState.isConnected ? Color.statusComplete : Color.statusError)
                .frame(width: 8, height: 8)
            
            Text(appState.isConnected ? "Connected" : "Disconnected")
                .font(.caption)
                .foregroundColor(.textSecondary)
        }
    }

    private var executionModeBadge: some View {
        Text(appState.executionMode.badgeText)
            .font(.caption2.monospaced())
            .fontWeight(.semibold)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(
                RoundedRectangle(cornerRadius: 5)
                    .fill(executionModeBadgeBackground)
            )
            .foregroundColor(executionModeBadgeForeground)
    }

    private var executionModeBadgeForeground: Color {
        switch appState.executionMode {
        case .plan:
            return .orange
        case .teacher:
            return .statusComplete
        case .direct:
            return .primaryBlue
        }
    }

    private var executionModeBadgeBackground: Color {
        switch appState.executionMode {
        case .plan:
            return Color.orange.opacity(0.22)
        case .teacher:
            return Color.statusComplete.opacity(0.2)
        case .direct:
            return Color.primaryBlue.opacity(0.18)
        }
    }

    private var deepThinkBadge: some View {
        HStack(spacing: 4) {
            Image(systemName: "brain")
                .font(.system(size: 10, weight: .semibold))
            Text(appState.deepThinkEnabled ? "DEEP THINK ON" : "DEEP THINK OFF")
                .font(.caption2.monospaced())
                .fontWeight(.semibold)
        }
        .padding(.horizontal, 6)
        .padding(.vertical, 2)
        .background(
            RoundedRectangle(cornerRadius: 5)
                .fill(deepThinkBadgeBackground)
        )
        .foregroundColor(deepThinkBadgeForeground)
        .help(
            appState.deepThinkEnabled
                ? "Deep Think is enabled for new prompts."
                : "Deep Think is disabled for new prompts."
        )
    }

    private var deepThinkBadgeForeground: Color {
        appState.deepThinkEnabled ? .statusThinking : .textTertiary
    }

    private var deepThinkBadgeBackground: Color {
        appState.deepThinkEnabled ? Color.statusThinking.opacity(0.15) : Color.cardBackground.opacity(0.55)
    }
    
    private var menuButton: some View {
        Menu {
            Button(action: { Task { await appState.createNewSession() } }) {
                Label("New Session", systemImage: "plus.rectangle.on.rectangle")
            }

            Menu {
                if appState.sessions.isEmpty {
                    Text("No sessions yet")
                } else {
                    ForEach(Array(appState.sessions.prefix(15))) { session in
                        Button(action: {
                            Task {
                                await appState.switchSession(session)
                            }
                        }) {
                            HStack {
                                Text(session.shortLabel)
                                if session.sessionId == appState.activeSessionId {
                                    Image(systemName: "checkmark")
                                }
                            }
                        }
                    }
                }
            } label: {
                Label("Switch Session", systemImage: "rectangle.stack")
            }

            Button(action: {
                showSessionManagerSheet = true
            }) {
                Label("Manage Sessions", systemImage: "square.stack.3d.down.right")
            }

            Menu {
                ForEach(SessionMemoryMode.allCases) { mode in
                    Button(action: { appState.setMemoryMode(mode) }) {
                        HStack {
                            Text(mode.displayName)
                            if appState.memoryMode == mode {
                                Image(systemName: "checkmark")
                            }
                        }
                    }
                }
            } label: {
                Label("Memory: \(appState.memoryMode.displayName)", systemImage: "memorychip")
            }

            Button(action: { Task { await appState.refreshSessions() } }) {
                Label("Refresh Sessions", systemImage: "arrow.clockwise")
            }

            Button(action: {
                renameSessionDraft = appState.activeSessionTitle
                showRenameSessionSheet = true
            }) {
                Label("Rename Active Session", systemImage: "pencil")
            }

            Divider()

            // Model submenu for quick selection
            Menu {
                ForEach(GeminiModel.allCases) { model in
                    Button(action: {
                        appState.setSelectedModel(model)
                    }) {
                        HStack {
                            Text(model.displayName)
                            if appState.selectedModel == model {
                                Image(systemName: "checkmark")
                            }
                        }
                    }
                }
            } label: {
                Label(currentModelDisplayName, systemImage: "cpu")
            }

            Menu {
                ForEach(ResponseVerbosity.allCases) { verbosity in
                    Button(action: {
                        appState.setResponseVerbosity(verbosity)
                    }) {
                        HStack {
                            Text(verbosity.displayName)
                            if appState.responseVerbosity == verbosity {
                                Image(systemName: "checkmark")
                            }
                        }
                    }
                }
            } label: {
                Label("Verbosity: \(appState.responseVerbosity.displayName)", systemImage: "text.alignleft")
            }

            Button(action: {
                appState.setDeepThinkEnabled(!appState.deepThinkEnabled)
            }) {
                HStack {
                    Label("Deep Think", systemImage: "brain")
                    if appState.deepThinkEnabled {
                        Image(systemName: "checkmark")
                    }
                }
            }

            Menu {
                ForEach(ResponsePresentationStyle.allCases) { style in
                    Button(action: {
                        appState.setResponsePresentationStyle(style)
                    }) {
                        HStack {
                            Text(style.displayName)
                            if appState.responsePresentationStyle == style {
                                Image(systemName: "checkmark")
                            }
                        }
                    }
                }

                Divider()

                Button(action: {
                    appState.setReadableProHighContrastEnabled(!appState.readableProHighContrastEnabled)
                }) {
                    HStack {
                        Text("Readable Pro High Contrast")
                        if appState.readableProHighContrastEnabled {
                            Image(systemName: "checkmark")
                        }
                    }
                }
                .disabled(appState.responsePresentationStyle != .readablePro)
            } label: {
                Label("Format: \(appState.responsePresentationStyle.displayName)", systemImage: "textformat")
            }

            Menu {
                ForEach(StreamingAnimationStyle.allCases) { style in
                    Button(action: {
                        appState.setStreamingAnimationStyle(style)
                    }) {
                        HStack {
                            Text(style.displayName)
                            if appState.streamingAnimationStyle == style {
                                Image(systemName: "checkmark")
                            }
                        }
                    }
                }
            } label: {
                Label("Animation: \(appState.streamingAnimationStyle.displayName)", systemImage: "sparkles")
            }

            Menu {
                ForEach(ExecutionMode.allCases) { mode in
                    Button(action: {
                        appState.setExecutionMode(mode)
                    }) {
                        HStack {
                            Text(mode.displayName)
                            if appState.executionMode == mode {
                                Image(systemName: "checkmark")
                            }
                        }
                    }
                }
            } label: {
                Label("Execution: \(appState.executionMode.displayName)", systemImage: "checklist")
            }
            
            Divider()
            
            Button(action: { Task { await appState.reconnect() } }) {
                Label("Reconnect", systemImage: "arrow.clockwise")
            }
            
            Button(action: { appState.clearMessages() }) {
                Label("Clear Messages", systemImage: "trash")
            }
            
            Divider()
            
            Button(action: { permissionsManager.showPermissionsModal = true }) {
                Label("Permissions...", systemImage: "lock.shield")
            }
            
            Button(action: { showSettingsSheet = true }) {
                Label("Settings...", systemImage: "gearshape")
            }
        } label: {
            Image(systemName: "ellipsis.circle")
                .font(.system(size: 18))
                .foregroundColor(.textSecondary)
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
    }
    
    private var currentModelDisplayName: String {
        appState.selectedModel.displayName
    }

    private var renameSessionSheet: some View {
        VStack(alignment: .leading, spacing: ThemeConstants.spacingM) {
            Text("Rename Session")
                .font(.headline)

            TextField("Session name", text: $renameSessionDraft)
                .textFieldStyle(.roundedBorder)

            HStack {
                Spacer()
                Button("Cancel") {
                    showRenameSessionSheet = false
                }
                Button("Save") {
                    let newTitle = renameSessionDraft
                    Task {
                        await appState.renameActiveSession(to: newTitle)
                        showRenameSessionSheet = false
                    }
                }
                .keyboardShortcut(.defaultAction)
                .disabled(renameSessionDraft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
        }
        .padding(ThemeConstants.spacingL)
        .frame(minWidth: 360)
    }

    private var sessionManagerSheet: some View {
        VStack(alignment: .leading, spacing: ThemeConstants.spacingM) {
            HStack {
                Text("Sessions")
                    .font(.headline)
                if !appState.sessions.isEmpty {
                    Text("\(selectedSessionIdsForBulkDelete.count) selected")
                        .font(.caption)
                        .foregroundColor(.textSecondary)
                }
                Spacer()
                Button("Done") {
                    showSessionManagerSheet = false
                }
                .keyboardShortcut(.cancelAction)
            }

            if !appState.sessions.isEmpty {
                HStack(spacing: ThemeConstants.spacingS) {
                    Button("Select All") {
                        selectedSessionIdsForBulkDelete = Set(appState.sessions.map(\.sessionId))
                    }
                    .buttonStyle(.bordered)
                    .disabled(isDeletingSelectedSessions)

                    Button("Clear Selection") {
                        selectedSessionIdsForBulkDelete.removeAll()
                    }
                    .buttonStyle(.bordered)
                    .disabled(selectedSessionIdsForBulkDelete.isEmpty || isDeletingSelectedSessions)

                    Spacer()

                    Button("Delete Selected", role: .destructive) {
                        requestDeleteSelectedSessions()
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(selectedSessionIdsForBulkDelete.isEmpty || isDeletingSelectedSessions)
                }
            }

            if appState.sessions.isEmpty {
                Text("No sessions yet")
                    .font(.subheadline)
                    .foregroundColor(.textSecondary)
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .center)
            } else {
                ScrollView {
                    LazyVStack(spacing: ThemeConstants.spacingXS) {
                        ForEach(appState.sessions) { session in
                            SessionManagerRow(
                                session: session,
                                isActive: session.sessionId == appState.activeSessionId,
                                isSelectedForDeletion: selectedSessionIdsForBulkDelete.contains(session.sessionId),
                                onSelect: {
                                    Task {
                                        await appState.switchSession(session)
                                        showSessionManagerSheet = false
                                    }
                                },
                                onToggleSelection: {
                                    toggleSessionSelection(sessionId: session.sessionId)
                                },
                                onDelete: {
                                    guard !isDeletingSelectedSessions else { return }
                                    pendingSessionDeleteTarget = .single(session)
                                    isSessionDeleteDialogPresented = true
                                }
                            )
                        }
                    }
                }
            }

            HStack(spacing: ThemeConstants.spacingS) {
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
        }
        .onChange(of: appState.sessions.map(\.sessionId)) { _, updatedIds in
            let available = Set(updatedIds)
            selectedSessionIdsForBulkDelete = selectedSessionIdsForBulkDelete.intersection(available)
        }
        .onChange(of: isSessionDeleteDialogPresented) { _, isPresented in
            if !isPresented && !isDeletingSelectedSessions {
                pendingSessionDeleteTarget = nil
            }
        }
        .confirmationDialog(
            sessionDeleteDialogTitle,
            isPresented: $isSessionDeleteDialogPresented,
            titleVisibility: .visible
        ) {
            Button(sessionDeleteConfirmButtonTitle, role: .destructive) {
                let target = pendingSessionDeleteTarget
                Task {
                    await performSessionDeletion(target)
                    pendingSessionDeleteTarget = nil
                }
            }
            Button("Cancel", role: .cancel) {
                pendingSessionDeleteTarget = nil
            }
        } message: {
            Text(sessionDeleteDialogMessage)
        }
        .padding(ThemeConstants.spacingL)
        .frame(minWidth: 520, minHeight: 380)
    }
    
    // MARK: - Content Area
    
    @ViewBuilder
    private var contentArea: some View {
        if appState.isSessionHistoryLoading {
            SessionHistoryLoadingView()
        } else if appState.messages.isEmpty {
            EmptyMessageView()
        } else {
            MessageListView(
                messages: appState.messages,
                sessionId: appState.activeSessionId
            )
        }
    }
    
    // MARK: - Input Area
    
    private var inputArea: some View {
        VStack(spacing: ThemeConstants.spacingXS) {
            // Error message if present
            if let error = appState.lastError, appState.status.isError {
                errorBanner(error)
            }

            if isFileDropTargeted {
                HStack(spacing: ThemeConstants.spacingS) {
                    Image(systemName: "square.and.arrow.down")
                        .foregroundColor(.primaryBlue)
                    Text("Drop files to attach them to this request")
                        .font(.caption)
                        .foregroundColor(.textSecondary)
                    Spacer()
                }
                .padding(ThemeConstants.spacingS)
                .background(Color.primaryBlue.opacity(0.08))
                .clipShape(RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusSmall))
            }

            if !appState.droppedFilePaths.isEmpty {
                droppedFilesSection
            }

            executionModeInfoBanner
            
            // Input field
            InputField(
                text: $appState.currentInput,
                placeholder: inputPlaceholderText,
                isDisabled: appState.status.isBusy || appState.isSendingPrompt || appState.isSessionHistoryLoading,
                onSubmit: {
                    Task {
                        await appState.sendPrompt()
                    }
                }
            )
        }
        .padding(ThemeConstants.spacingM)
        .transaction { $0.animation = nil }
    }

    private var inputPlaceholderText: String {
        switch appState.executionMode {
        case .plan:
            return "Describe what to plan..."
        case .teacher:
            return "Ask a study question..."
        case .direct:
            return "Ask me anything..."
        }
    }



    private var executionModeInfoBanner: some View {
        let banner = executionModeBannerConfiguration
        return HStack(spacing: ThemeConstants.spacingS) {
            Image(systemName: banner.icon)
                .foregroundColor(banner.foreground)
            Text(banner.message)
            .font(.caption)
            .foregroundColor(.textSecondary)
            Spacer(minLength: ThemeConstants.spacingS)
        }
        .padding(ThemeConstants.spacingS)
        .background(banner.background)
        .clipShape(RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusSmall))
    }

    private var executionModeBannerConfiguration: (icon: String, foreground: Color, background: Color, message: String) {
        switch appState.executionMode {
        case .plan:
            return (
                "list.bullet.clipboard",
                .orange,
                Color.orange.opacity(0.12),
                "Plan Mode: builds a plan only. No file-changing tools will execute."
            )
        case .teacher:
            return (
                "graduationcap.fill",
                .statusComplete,
                Color.statusComplete.opacity(0.12),
                "Teacher Mode: teaches conversationally and auto-saves highlighted study notes."
            )
        case .direct:
            return (
                "bolt.fill",
                .primaryBlue,
                Color.primaryBlue.opacity(0.1),
                "Direct Mode: can execute tools immediately (with destructive-operation confirmation)."
            )
        }
    }

    private var droppedFilesSection: some View {
        VStack(alignment: .leading, spacing: ThemeConstants.spacingXS) {
            HStack {
                Text("Attached Paths (\(appState.droppedFilePaths.count))")
                    .font(.caption)
                    .foregroundColor(.textSecondary)
                Spacer()
                Button("Clear") {
                    appState.clearDroppedFiles()
                }
                .font(.caption2)
                .buttonStyle(.plain)
                .foregroundColor(.statusError)
            }

            ForEach(appState.droppedFilePaths, id: \.self) { path in
                HStack(spacing: ThemeConstants.spacingXS) {
                    Image(systemName: "doc")
                        .foregroundColor(.primaryBlue)
                    Text(URL(fileURLWithPath: path).lastPathComponent)
                        .font(.caption2)
                        .lineLimit(1)
                        .foregroundColor(.textPrimary)
                    Spacer(minLength: ThemeConstants.spacingXS)
                    Text(path)
                        .font(.caption2)
                        .lineLimit(1)
                        .truncationMode(.middle)
                        .foregroundColor(.textTertiary)
                    Button(action: { appState.removeDroppedFile(path: path) }) {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundColor(.textTertiary)
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .padding(ThemeConstants.spacingS)
        .background(Color.cardBackground.opacity(0.65))
        .clipShape(RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusSmall))
    }
    
    private func errorBanner(_ message: String) -> some View {
        HStack(spacing: ThemeConstants.spacingS) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundColor(.statusError)
            
            Text(message)
                .font(.caption)
                .foregroundColor(.statusError)
            
            Spacer()
            
            Button(action: { appState.lastError = nil }) {
                Image(systemName: "xmark")
                    .font(.caption)
                    .foregroundColor(.statusError)
            }
            .buttonStyle(.plain)
        }
        .padding(ThemeConstants.spacingS)
        .background(Color.statusError.opacity(0.1))
        .clipShape(RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusSmall))
    }

    private var sessionDeleteDialogTitle: String {
        guard let target = pendingSessionDeleteTarget else {
            return "Delete session?"
        }
        switch target {
        case .single:
            return "Delete this session?"
        case .batch(let sessions):
            return "Delete \(sessions.count) sessions?"
        }
    }

    private var sessionDeleteConfirmButtonTitle: String {
        guard let target = pendingSessionDeleteTarget else {
            return "Delete"
        }
        switch target {
        case .single:
            return "Delete Session"
        case .batch(let sessions):
            return "Delete \(sessions.count) Sessions"
        }
    }

    private var sessionDeleteDialogMessage: String {
        guard let target = pendingSessionDeleteTarget else {
            return ""
        }
        switch target {
        case .single(let session):
            return "Session \"\(session.title)\" and all its stored chat data will be permanently removed."
        case .batch(let sessions):
            let activeIncluded = sessions.contains { $0.sessionId == appState.activeSessionId }
            if activeIncluded {
                return "Selected sessions, including the active one, will be permanently removed from storage."
            }
            return "Selected sessions and their stored chat data will be permanently removed."
        }
    }

    private func toggleSessionSelection(sessionId: String) {
        if selectedSessionIdsForBulkDelete.contains(sessionId) {
            selectedSessionIdsForBulkDelete.remove(sessionId)
            return
        }
        selectedSessionIdsForBulkDelete.insert(sessionId)
    }

    private func requestDeleteSelectedSessions() {
        guard !isDeletingSelectedSessions else { return }
        let selected = appState.sessions.filter { selectedSessionIdsForBulkDelete.contains($0.sessionId) }
        guard !selected.isEmpty else { return }
        pendingSessionDeleteTarget = .batch(selected)
        isSessionDeleteDialogPresented = true
    }

    private func performSessionDeletion(_ target: SessionDeleteTarget?) async {
        guard let target else { return }
        isDeletingSelectedSessions = true
        defer { isDeletingSelectedSessions = false }

        switch target {
        case .single(let session):
            await appState.deleteSession(session)
            selectedSessionIdsForBulkDelete.remove(session.sessionId)
        case .batch(let sessions):
            let requestedIds = Set(sessions.map(\.sessionId))
            await appState.deleteSessions(sessions)
            selectedSessionIdsForBulkDelete.subtract(requestedIds)
        }
    }
    
    // MARK: - Actions

    private func handleFileDrop(providers: [NSItemProvider]) -> Bool {
        var accepted = false
        for provider in providers {
            guard provider.hasItemConformingToTypeIdentifier(UTType.fileURL.identifier) else {
                continue
            }
            accepted = true
            provider.loadItem(
                forTypeIdentifier: UTType.fileURL.identifier,
                options: nil
            ) { item, _ in
                var urls: [URL] = []
                if let data = item as? Data,
                   let url = URL(dataRepresentation: data, relativeTo: nil) {
                    urls = [url]
                } else if let url = item as? URL {
                    urls = [url]
                } else if let text = item as? String,
                          let url = URL(string: text) {
                    urls = [url]
                }
                guard !urls.isEmpty else { return }
                Task { @MainActor in
                    appState.addDroppedFiles(urls: urls)
                }
            }
        }
        return accepted
    }

    /// Opens the Settings window
    private func openSettings() {
        NSApp.activate(ignoringOtherApps: true)
        _ = NSApp.sendAction(Selector(("showSettingsWindow:")), to: nil, from: nil)
    }
}

private struct SessionManagerRow: View {
    let session: SessionListItem
    let isActive: Bool
    let isSelectedForDeletion: Bool
    let onSelect: () -> Void
    let onToggleSelection: () -> Void
    let onDelete: () -> Void

    @State private var isHovered = false

    var body: some View {
        HStack(spacing: ThemeConstants.spacingS) {
            Button(action: onToggleSelection) {
                Image(systemName: isSelectedForDeletion ? "checkmark.circle.fill" : "circle")
                    .foregroundColor(isSelectedForDeletion ? .primaryBlue : .textTertiary)
                    .font(.system(size: 16))
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .help(isSelectedForDeletion ? "Unselect for deletion" : "Select for deletion")

            Button(action: onSelect) {
                HStack(spacing: ThemeConstants.spacingS) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(session.title)
                            .font(.subheadline.weight(.medium))
                            .lineLimit(1)
                        Text(session.sessionId)
                            .font(.caption2.monospaced())
                            .foregroundColor(.textTertiary)
                            .lineLimit(1)
                    }

                    Spacer(minLength: ThemeConstants.spacingS)

                    if isActive {
                        Text("Active")
                            .font(.caption2.weight(.semibold))
                            .padding(.horizontal, 8)
                            .padding(.vertical, 3)
                            .background(Color.primaryBlue.opacity(0.16))
                            .foregroundColor(.primaryBlue)
                            .clipShape(Capsule())
                    }
                }
            }
            .buttonStyle(.plain)

            Button(role: .destructive, action: onDelete) {
                Image(systemName: "trash")
                    .font(.caption)
                    .padding(6)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .foregroundColor(.statusError)
            .opacity(isHovered ? 1 : 0)
            .help("Delete session")
        }
        .padding(.horizontal, ThemeConstants.spacingS)
        .padding(.vertical, 8)
        .background(
            RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusSmall)
                .fill(isActive ? Color.primaryBlue.opacity(0.1) : Color.cardBackground.opacity(0.45))
        )
        .overlay(
            RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusSmall)
                .stroke(isHovered ? Color.primaryBlue.opacity(0.35) : Color.clear, lineWidth: 1)
        )
        .contentShape(Rectangle())
        .onHover { hovering in
            withAnimation(.easeOut(duration: 0.12)) {
                isHovered = hovering
            }
        }
    }
}

// MARK: - Compact Panel View

/// A more compact version of the panel for smaller displays
struct CompactPanelView: View {
    
    @ObservedObject var appState: AppState
    
    var body: some View {
        VStack(spacing: 0) {
            // Minimal header
            HStack {
                Image(systemName: "brain")
                    .foregroundColor(.primaryBlue)
                
                Spacer()
                
                InlineStatusView(status: appState.status, isConnected: appState.isConnected)
            }
            .padding(.horizontal, ThemeConstants.spacingS)
            .padding(.vertical, ThemeConstants.spacingXS)
            
            // Messages (limited height)
            if !appState.messages.isEmpty {
                ScrollView {
                    LazyVStack(spacing: ThemeConstants.spacingS) {
                        ForEach(appState.messages.suffix(3)) { message in
                            ResponseBubble(message: message, animate: message.isStreaming)
                        }
                    }
                    .padding(.horizontal, ThemeConstants.spacingS)
                }
                .frame(maxHeight: 200)
            }
            
            // Input
            SimpleInputField(
                text: $appState.currentInput,
                placeholder: "Ask...",
                isDisabled: appState.status.isBusy || appState.isSendingPrompt || appState.isSessionHistoryLoading,
                onSubmit: {
                    Task {
                        await appState.sendPrompt()
                    }
                }
            )
            .padding(ThemeConstants.spacingS)
        }
        .frame(width: 300, height: 300)
        .liquidGlass(cornerRadius: ThemeConstants.cornerRadiusMedium)
    }
}

// MARK: - Preview

#if DEBUG
struct MainPanelViewPreview: View {
    var body: some View {
        ZStack {
            // Background to show glass effect
            LinearGradient(
                colors: [.blue.opacity(0.2), .purple.opacity(0.2)],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            
            MainPanelView(appState: .preview)
                .frame(width: 400, height: 600)
        }
        .frame(width: 500, height: 700)
    }
}

struct MainPanelStreamingPreview: View {
    var body: some View {
        ZStack {
            LinearGradient(
                colors: [.blue.opacity(0.2), .purple.opacity(0.2)],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            
            MainPanelView(appState: .previewStreaming)
                .frame(width: 400, height: 600)
        }
        .frame(width: 500, height: 700)
    }
}

struct MainPanelToolCallPreview: View {
    var body: some View {
        ZStack {
            LinearGradient(
                colors: [.blue.opacity(0.2), .purple.opacity(0.2)],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            
            MainPanelView(appState: .previewWithToolCall)
                .frame(width: 400, height: 600)
        }
        .frame(width: 500, height: 700)
    }
}

struct MainPanelView_Previews: PreviewProvider {
    static var previews: some View {
        Group {
            MainPanelViewPreview()
                .previewDisplayName("Main Panel")
            
            MainPanelStreamingPreview()
                .previewDisplayName("Streaming")
            
            MainPanelToolCallPreview()
                .previewDisplayName("Tool Call")
            
            ZStack {
                LinearGradient(
                    colors: [.blue.opacity(0.2), .purple.opacity(0.2)],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
                
                CompactPanelView(appState: .preview)
            }
            .frame(width: 400, height: 400)
            .previewDisplayName("Compact")
        }
    }
}
#endif
