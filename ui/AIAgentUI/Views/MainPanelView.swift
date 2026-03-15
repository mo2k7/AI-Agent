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
    @ObservedObject var chatState: ChatState = .shared
    @ObservedObject var themeState: UIThemeState = .shared
    @ObservedObject var connectionState: ConnectionState = .shared
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
    @State private var isHeaderHovered = false
    @State private var pendingHeaderHideTask: Task<Void, Never>?
    
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
                    .sectionFade(edge: .bottom, height: 6)

                // Content area
                MainContentAreaView(appState: appState)

                // Input area
                MainInputAreaView(appState: appState, isFileDropTargeted: $isFileDropTargeted)
                    .sectionFade(edge: .top, height: 8)
            }
            #if os(macOS)
            .frame(
                minWidth: ThemeConstants.panelMinWidth,
                idealWidth: ThemeConstants.panelWidth,
                maxWidth: .infinity,
                minHeight: ThemeConstants.panelMinHeight,
                idealHeight: ThemeConstants.panelHeight,
                maxHeight: .infinity
            )
            .glassBase()
            .overlay(
                RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusMedium)
                    .stroke(
                        isFileDropTargeted ? Color.primaryBlue.opacity(0.65) : Color.clear,
                        lineWidth: 2
                    )
            )
            #else
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color.panelBackground)
            #endif
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

            if let timeoutNotice = appState.requestTimeoutNotice {
                timeoutOverlay(timeoutNotice)
            }

            // Settings overlay (ZStack instead of .sheet() — NSPanel .sheet() can be invisible)
            if showSettingsSheet {
                OverlayContainer(isPresented: $showSettingsSheet) {
                    InlineSettingsView(appState: appState, isPresented: $showSettingsSheet)
                }
            }

            // Rename session overlay
            if showRenameSessionSheet {
                OverlayContainer(isPresented: $showRenameSessionSheet) {
                    renameSessionSheet
                }
            }

            // Session manager overlay
            if showSessionManagerSheet {
                OverlayContainer(isPresented: $showSessionManagerSheet) {
                    sessionManagerSheet
                }
            }
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
        VStack(spacing: 0) {
            #if os(iOS)
            // Extra top padding on iOS to clear the status bar / notch / Dynamic Island
            Spacer()
                .frame(height: 0)
                .safeAreaInset(edge: .top) { Color.clear.frame(height: 0) }
            #endif

            // Primary bar — always visible
            HStack(alignment: .center, spacing: ThemeConstants.spacingS) {
                // Status-reactive app icon (replaces static brain + connection dot)
                AmbientAppIcon(status: chatState.status, isConnected: connectionState.isConnected)

                VStack(alignment: .leading, spacing: 1) {
                    Text("AI Agent")
                        .font(.headline)
                        .foregroundColor(.textPrimary)
                    Text(appState.activeSessionTitle)
                        .font(.caption2)
                        .foregroundColor(.textSecondary)
                        .lineLimit(1)
                        .truncationMode(.tail)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }

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
                        .frame(width: 28, height: 28)
                        .background(
                            Circle()
                                .fill(
                                    (appState.isNotesPanelVisible ? Color.primaryBlue : Color.cardBackground)
                                        .opacity(appState.isNotesPanelVisible ? 0.14 : 0.42)
                                )
                        )
                }
                .buttonStyle(.plain)
                .help("Toggle Notes (Cmd+Shift+N)")

                // Menu button
                menuButton
            }
            .padding(.horizontal, ThemeConstants.spacingM)
            .padding(.vertical, ThemeConstants.spacingS)
            .background(
                LinearGradient(
                    colors: [Color.white.opacity(0.05), Color.clear],
                    startPoint: .top,
                    endPoint: .bottom
                )
            )

            // Hover-reveal badge tray
            HeaderContextTray(appState: appState, isVisible: isHeaderHovered)
        }
        .background(Color.clear)
        #if os(macOS)
        .onHover { hovering in
            setHeaderHover(hovering)
        }
        #endif
    }
    
    // Badge properties moved to HeaderContextTray.swift
    // Connection indicator embedded in AmbientAppIcon.swift

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
                ForEach(appState.modelSelectionOptions) { model in
                    Button(action: {
                        appState.setSelectedModel(model.id)
                    }) {
                        HStack {
                            Text(model.resolvedDisplayName)
                            if appState.selectedModelId == model.id {
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
                        themeState.responsePresentationStyle = style
                    }) {
                        HStack {
                            Text(style.displayName)
                            if themeState.responsePresentationStyle == style {
                                Image(systemName: "checkmark")
                            }
                        }
                    }
                }

                Divider()

                Button(action: {
                    themeState.readableProHighContrastEnabled.toggle()
                }) {
                    HStack {
                        Text("Readable Pro High Contrast")
                        if themeState.readableProHighContrastEnabled {
                            Image(systemName: "checkmark")
                        }
                    }
                }
                .disabled(themeState.responsePresentationStyle != .readablePro)
            } label: {
                Label("Format: \(themeState.responsePresentationStyle.displayName)", systemImage: "textformat")
            }

            Menu {
                ForEach(StreamingAnimationStyle.allCases) { style in
                    Button(action: {
                        themeState.streamingAnimationStyle = style
                    }) {
                        HStack {
                            Text(style.displayName)
                            if themeState.streamingAnimationStyle == style {
                                Image(systemName: "checkmark")
                            }
                        }
                    }
                }
            } label: {
                Label("Animation: \(themeState.streamingAnimationStyle.displayName)", systemImage: "sparkles")
            }

            Menu {
                ForEach(BrowseRestrictionProfile.allCases) { profile in
                    Button(action: {
                        appState.setBrowseRestrictionProfile(profile)
                    }) {
                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(profile.displayName)
                                Text(profile.quickMenuDescription)
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                            if appState.browseRestrictionProfile == profile {
                                Spacer(minLength: ThemeConstants.spacingS)
                                Image(systemName: "checkmark")
                            }
                        }
                    }
                }
            } label: {
                Label("Web Browsing: \(appState.browseRestrictionProfile.displayName)", systemImage: "globe")
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
                .frame(width: 28, height: 28)
                .background(
                    Circle()
                        .fill(Color.cardBackground.opacity(0.42))
                )
        }
        #if os(macOS)
        .menuStyle(.borderlessButton)
        #endif
        .menuIndicator(.hidden)
        // Force Menu recreation when relevant state changes — fixes iOS UIContextMenuInteraction
        // caching stale content (the _UIReparentingView issue)
        .id(menuIdentityKey)
    }

    /// Combined identity key for the 3-dots Menu so iOS recreates it on state changes.
    private var menuIdentityKey: String {
        [
            appState.selectedModelId,
            appState.memoryMode.rawValue,
            appState.responseVerbosity.rawValue,
            appState.executionMode.rawValue,
            appState.deepThinkEnabled.description,
            appState.browseRestrictionProfile.rawValue,
            themeState.responsePresentationStyle.rawValue,
            themeState.streamingAnimationStyle.rawValue,
            themeState.readableProHighContrastEnabled.description,
            appState.activeSessionId,
            String(appState.sessions.count),
        ].joined(separator: "|")
    }
    
    private var currentModelDisplayName: String {
        appState.selectedModel.resolvedDisplayName
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
    
    // MARK: - Content Area & Input Area Extracted
    // The implementations of contentArea and inputArea have been moved to isolated structs
    // to prevent ChatState high-frequency updates from invalidating the root MainPanelView.



    private func timeoutOverlay(_ notice: RequestTimeoutNotice) -> some View {
        VStack {
            Spacer()
            HStack(spacing: ThemeConstants.spacingS) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Request Timed Out")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(.textPrimary)
                    Text(notice.userMessage)
                        .font(.caption)
                        .foregroundColor(.textSecondary)
                        .lineLimit(3)
                    Text("Phase: \(notice.phase)  •  Operation: \(notice.operation)")
                        .font(.caption2)
                        .foregroundColor(.textTertiary)
                }
                Spacer()
                Button("Dismiss") {
                    appState.dismissRequestTimeoutNotice()
                }
                .font(.caption)
                .buttonStyle(.plain)
                .foregroundColor(.primaryBlue)
            }
            .padding(ThemeConstants.spacingM)
            .background(Color.cardBackground.opacity(0.95))
            .clipShape(RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusSmall))
            .overlay(
                RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusSmall)
                    .stroke(Color.statusError.opacity(0.35), lineWidth: 1)
            )
            .padding(.horizontal, ThemeConstants.spacingM)
            .padding(.bottom, ThemeConstants.spacingM)
        }
        .transition(.opacity.combined(with: .move(edge: .bottom)))
        .animation(AnimationConstants.standard, value: notice.id)
    }



    private func setHeaderHover(_ hovering: Bool) {
        pendingHeaderHideTask?.cancel()
        pendingHeaderHideTask = nil

        if hovering {
            withAnimation(AnimationConstants.snappy) {
                isHeaderHovered = true
            }
            return
        }

        pendingHeaderHideTask = Task { @MainActor in
            try? await Task.sleep(for: .milliseconds(300))
            guard !Task.isCancelled else { return }
            withAnimation(AnimationConstants.fast) {
                isHeaderHovered = false
            }
            pendingHeaderHideTask = nil
        }
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
        showSettingsSheet = true
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
    @ObservedObject var connectionState: ConnectionState = .shared
    @ObservedObject var chatState: ChatState = .shared
    
    var body: some View {
        VStack(spacing: 0) {
            // Minimal header
            HStack {
                Image(systemName: "brain")
                    .foregroundColor(.primaryBlue)
                
                Spacer()
                
                InlineStatusView(status: chatState.status, isConnected: connectionState.isConnected)
            }
            .padding(.horizontal, ThemeConstants.spacingS)
            .padding(.vertical, ThemeConstants.spacingXS)
            
            // Messages (limited height)
            if !chatState.messageRows.isEmpty {
                ScrollView {
                    LazyVStack(spacing: ThemeConstants.spacingS) {
                        ForEach(chatState.messageRows.suffix(3)) { row in
                            ResponseBubble(row: row, animate: row.isStreaming)
                        }
                    }
                    .padding(.horizontal, ThemeConstants.spacingS)
                }
                .frame(maxHeight: 200)
            }
            
            // Input
            SimpleInputField(
                text: $chatState.currentInput,
                placeholder: "Ask...",
                isDisabled: chatState.status.isBusy || appState.isSendingPrompt || appState.isSessionHistoryLoading,
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
