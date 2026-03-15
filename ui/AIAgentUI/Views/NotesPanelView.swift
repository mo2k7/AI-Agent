//
//  NotesPanelView.swift
//  AIAgentUI
//
//  Created for Personal macOS AI Agent
//  Status: Active - Session-pad-first notes workspace
//

import SwiftUI
import UniformTypeIdentifiers

#if os(macOS)
import AppKit
#elseif canImport(UIKit)
import UIKit
#endif

struct NotesPanelView: View {
    @ObservedObject var appState: AppState
    @State private var selectedNoteId: String?
    @State private var isEditing: Bool = false
    @State private var draftTitle: String = ""
    @State private var draftContent: String = ""
    @State private var isSearchVisible: Bool = false
    @State private var searchText: String = ""
    @State private var showNewTabSheet: Bool = false
    @State private var showHistory: Bool = false
    @State private var versions: [IPCNoteVersion] = []
    @State private var isLoadingVersions: Bool = false
    @State private var showStudyView: Bool = false
    @State private var exportShareItem: ExportShareItem?

    private var sessionPad: Note? {
        appState.notes.first(where: \.isSessionPad)
    }

    private var secondaryTabs: [Note] {
        appState.notes.filter { !$0.isSessionPad }
    }

    private var visibleSecondaryTabs: [Note] {
        Array(secondaryTabs.prefix(3))
    }

    private var overflowSecondaryTabs: [Note] {
        Array(secondaryTabs.dropFirst(3))
    }

    private var activeNote: Note? {
        if let selectedNoteId,
           let selected = appState.notes.first(where: { $0.id == selectedNoteId }) {
            return selected
        }
        return sessionPad ?? appState.notes.first
    }

    private var searchResults: [Note] {
        let query = searchText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !query.isEmpty else { return [] }
        return appState.notes.filter {
            $0.displayTitle.localizedCaseInsensitiveContains(query)
                || $0.displayContent.localizedCaseInsensitiveContains(query)
        }
    }

    private var activeBlocks: [MarkdownBlock] {
        guard let activeNote else { return [] }
        return NoteMarkdownParser.parse(activeNote.displayContent)
    }

    private var activeIsFlashcardNote: Bool {
        guard let noteType = activeNote?.noteType else { return false }
        return noteType == "flashcards" || noteType == "study_guide"
    }

    var body: some View {
        ZStack {
            VStack(spacing: 0) {
                headerView
                Divider().background(Color.glassStroke)
                tabStrip
                if isSearchVisible {
                    searchBar
                }
                if !searchResults.isEmpty {
                    searchResultsView
                }
                Divider().background(Color.glassStroke.opacity(0.5))
                editorToolbar
                Divider().background(Color.glassStroke.opacity(0.5))
                contentView
                Divider().background(Color.glassStroke)
                footerView
            }
            #if os(macOS)
            .frame(
                minWidth: 360, idealWidth: 460, maxWidth: .infinity,
                minHeight: 360, idealHeight: 620, maxHeight: .infinity
            )
            .glassBase()
            #else
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color.panelBackground)
            #endif

            if showNewTabSheet {
                OverlayContainer(isPresented: $showNewTabSheet) {
                    NewNoteTabSheet(
                        onCancel: { showNewTabSheet = false },
                        onCreate: { title, content in
                            appState.createNote(content: content, title: title, workspaceKind: "tab") { note in
                                select(note: note)
                            }
                            showNewTabSheet = false
                        }
                    )
                }
            }

            if showHistory {
                OverlayContainer(isPresented: $showHistory) {
                    NoteHistoryView(
                        noteId: activeNote?.id ?? "",
                        versions: versions,
                        isLoading: isLoadingVersions,
                        onClose: { showHistory = false },
                        onRestore: { restoredContent in
                            guard let activeNote else { return }
                            appState.updateNote(noteId: activeNote.id, content: restoredContent)
                            showHistory = false
                        }
                    )
                }
            }

            if showStudyView, let activeNote {
                OverlayContainer(isPresented: $showStudyView) {
                    let cards = FlashcardParser.parse(activeNote.displayContent)
                    FlashcardStudyView(
                        noteTitle: activeNote.displayTitle,
                        cards: cards,
                        onClose: { showStudyView = false }
                    )
                }
            }

            #if !os(macOS)
            if let exportShareItem {
                OverlayContainer(
                    isPresented: Binding(
                        get: { self.exportShareItem != nil },
                        set: { isPresented in
                            if !isPresented {
                                self.exportShareItem = nil
                            }
                        }
                    ),
                    tapOutsideToDismiss: false
                ) {
                    ExportShareOverlay(
                        item: exportShareItem,
                        onDismiss: { self.exportShareItem = nil }
                    )
                }
            }
            #endif
        }
        .onAppear {
            appState.loadNotes()
            synchronizeSelection()
        }
        .onChange(of: appState.activeSessionId) { _, _ in
            resetEditorState()
            synchronizeSelection(forceSessionPad: true)
        }
        .onChange(of: appState.notes) { _, _ in
            synchronizeSelection()
            refreshDraftFromActiveNoteIfNeeded()
        }
    }

    private var headerView: some View {
        HStack(spacing: ThemeConstants.spacingS) {
            Image(systemName: "note.text")
                .font(.system(size: 16, weight: .semibold))
                .foregroundColor(.primaryBlue)

            VStack(alignment: .leading, spacing: 2) {
                Text(activeNote?.displayTitle ?? "Session Notes")
                    .font(.headline)
                    .foregroundColor(.textPrimary)
                    .lineLimit(1)
                Text(activeNote?.isSessionPad == true ? "Unified session pad" : "Secondary notes tab")
                    .font(.caption)
                    .foregroundColor(.textSecondary)
            }

            Spacer()

            if appState.isNotesLoading {
                ProgressView()
                    .controlSize(.small)
                    .scaleEffect(0.7)
            }

            Button(action: {
                withAnimation(.easeInOut(duration: 0.15)) {
                    isSearchVisible.toggle()
                    if !isSearchVisible {
                        searchText = ""
                    }
                }
            }) {
                Image(systemName: isSearchVisible ? "magnifyingglass.circle.fill" : "magnifyingglass")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(isSearchVisible ? .primaryBlue : .textSecondary)
            }
            .buttonStyle(.plain)
            .help("Search all notes tabs")

            Menu {
                Button(action: { exportNotes(format: .markdown) }) {
                    Label("Export All as Markdown", systemImage: "doc.richtext")
                }
                Button(action: { exportNotes(format: .plainText) }) {
                    Label("Export All as Plain Text", systemImage: "doc.plaintext")
                }
            } label: {
                Image(systemName: "square.and.arrow.up")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(.textSecondary)
            }
            #if os(macOS)
            .menuStyle(.borderlessButton)
            #endif
            .help("Export notes")
            .disabled(appState.notes.isEmpty)

            Button(action: { NotesPanelController.shared.hide() }) {
                Image(systemName: "xmark")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(.textSecondary)
            }
            .buttonStyle(.plain)
            .help("Close Notes")
        }
        .padding(.horizontal, ThemeConstants.spacingM)
        .padding(.vertical, ThemeConstants.spacingS)
    }

    private var tabStrip: some View {
        HStack(spacing: 8) {
            if let sessionPad {
                NoteTabPill(
                    title: sessionPad.displayTitle,
                    isActive: activeNote?.id == sessionPad.id,
                    isPrimary: true
                ) {
                    select(note: sessionPad)
                }
            }

            ForEach(visibleSecondaryTabs) { note in
                NoteTabPill(
                    title: note.displayTitle,
                    isActive: activeNote?.id == note.id,
                    isPrimary: false
                ) {
                    select(note: note)
                }
            }

            if !overflowSecondaryTabs.isEmpty {
                Menu {
                    ForEach(overflowSecondaryTabs) { note in
                        Button(note.displayTitle) {
                            select(note: note)
                        }
                    }
                } label: {
                    HStack(spacing: 4) {
                        Text("+\(overflowSecondaryTabs.count)")
                            .font(.caption.weight(.semibold))
                        Image(systemName: "chevron.down")
                            .font(.system(size: 9, weight: .bold))
                    }
                    .foregroundColor(.textSecondary)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(
                        Capsule()
                            .fill(Color.textPrimary.opacity(0.05))
                    )
                #if os(macOS)
                .menuStyle(.borderlessButton)
                #endif
                }
            }

            Spacer()

            Button(action: { showNewTabSheet = true }) {
                Label("New Tab", systemImage: "plus")
                    .font(.caption.weight(.semibold))
                    .foregroundColor(.textSecondary)
            }
            .buttonStyle(.plain)
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(
                Capsule()
                    .fill(Color.textPrimary.opacity(0.05))
            )
            .help("Create a separate notes tab")
        }
        .padding(.horizontal, ThemeConstants.spacingM)
        .padding(.vertical, 8)
    }

    private var searchBar: some View {
        HStack(spacing: 6) {
            Image(systemName: "magnifyingglass")
                .font(.system(size: 11))
                .foregroundColor(.textSecondary)
            TextField("Search notes and tabs...", text: $searchText)
                .textFieldStyle(.plain)
                .font(.callout)
            if !searchText.isEmpty {
                Button(action: { searchText = "" }) {
                    Image(systemName: "xmark.circle.fill")
                        .font(.system(size: 11))
                        .foregroundColor(.textSecondary.opacity(0.6))
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, ThemeConstants.spacingM)
        .padding(.vertical, 8)
        .background(Color.textPrimary.opacity(0.03))
    }

    private var searchResultsView: some View {
        VStack(alignment: .leading, spacing: 4) {
            ForEach(searchResults.prefix(6)) { note in
                Button(action: { select(note: note) }) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(note.displayTitle)
                            .font(.caption.weight(.semibold))
                            .foregroundColor(.textPrimary)
                        Text(note.displayContent)
                            .font(.caption2)
                            .foregroundColor(.textSecondary)
                            .lineLimit(2)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, ThemeConstants.spacingM)
                    .padding(.vertical, 6)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.vertical, 4)
        .background(Color.textPrimary.opacity(0.02))
    }

    private var editorToolbar: some View {
        HStack(spacing: 8) {
            if let activeNote {
                if activeNote.isSessionPad {
                    Text("Agent writes here by default")
                        .font(.caption.weight(.semibold))
                        .foregroundColor(.secondaryBlue)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(
                            Capsule().fill(Color.secondaryBlue.opacity(0.12))
                        )
                } else {
                    Text("Secondary Tab")
                        .font(.caption.weight(.semibold))
                        .foregroundColor(.textSecondary)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(
                            Capsule().fill(Color.textPrimary.opacity(0.06))
                        )
                }

                if let noteType = activeNote.noteType {
                    NoteTypeChip(type: noteType)
                }

                ForEach(activeNote.tags.prefix(3), id: \.self) { tag in
                    NoteTagChip(tag: tag)
                }

                Text(relativeTimestamp(for: activeNote.updatedAt))
                    .font(.caption)
                    .foregroundColor(.textSecondary)
            }

            Spacer()

            if activeIsFlashcardNote {
                Button(action: { showStudyView = true }) {
                    Label("Study", systemImage: "rectangle.on.rectangle.angled")
                        .font(.caption.weight(.semibold))
                        .foregroundColor(.primaryBlue)
                }
                .buttonStyle(.plain)
            }

            Button(action: loadAndShowHistory) {
                Image(systemName: "clock.arrow.circlepath")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundColor(.textSecondary)
            }
            .buttonStyle(.plain)
            .disabled(activeNote == nil)
            .help("Version History")

            if let activeNote, !activeNote.isSessionPad {
                Button(action: { appState.updateNote(noteId: activeNote.id, isPinned: !activeNote.isPinned) }) {
                    Image(systemName: activeNote.isPinned ? "pin.slash" : "pin")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundColor(.textSecondary)
                }
                .buttonStyle(.plain)
                .help(activeNote.isPinned ? "Unpin Tab" : "Pin Tab")
            }

            Button(action: toggleEditMode) {
                Text(isEditing ? "Cancel" : "Edit")
                    .font(.caption.weight(.semibold))
                    .foregroundColor(isEditing ? .textSecondary : .primaryBlue)
            }
            .buttonStyle(.plain)

            if let activeNote, !activeNote.isSessionPad {
                Menu {
                    Button("Rename Tab") {
                        beginRename(for: activeNote)
                    }
                    Button("Delete Tab", role: .destructive) {
                        appState.deleteNote(noteId: activeNote.id)
                    }
                } label: {
                    Image(systemName: "ellipsis.circle")
                        .font(.system(size: 13, weight: .medium))
                        .foregroundColor(.textSecondary)
                #if os(macOS)
                .menuStyle(.borderlessButton)
                #endif
                }
            }
        }
        .padding(.horizontal, ThemeConstants.spacingM)
        .padding(.vertical, 8)
    }

    @ViewBuilder
    private var contentView: some View {
        if let activeNote {
            if isEditing {
                editingView(for: activeNote)
            } else {
                ScrollView {
                    VStack(alignment: .leading, spacing: ThemeConstants.spacingM) {
                        NoteMarkdownView(
                            blocks: activeBlocks,
                            imageFetcher: { imageId in
                                await appState.fetchNoteImage(imageId: imageId)
                            },
                            noteType: activeNote.noteType,
                            onNoteTapped: { prefix in
                                guard let match = appState.notes.first(where: { $0.id.hasPrefix(prefix) }) else { return }
                                select(note: match)
                            }
                        )
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(ThemeConstants.spacingM)
                }
            }
        } else if appState.isNotesLoading {
            VStack {
                Spacer()
                ProgressView("Loading notes…")
                Spacer()
            }
        } else {
            VStack(spacing: ThemeConstants.spacingM) {
                Spacer()
                Image(systemName: "note.text")
                    .font(.system(size: 40))
                    .foregroundColor(.textSecondary.opacity(0.4))
                Text("No notes yet")
                    .font(.headline)
                    .foregroundColor(.textSecondary)
                Text("The session pad will appear here and the agent will keep writing into it.")
                    .font(.callout)
                    .foregroundColor(.textSecondary.opacity(0.7))
                    .multilineTextAlignment(.center)
                Spacer()
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    private func editingView(for note: Note) -> some View {
        VStack(alignment: .leading, spacing: ThemeConstants.spacingS) {
            if !note.isSessionPad {
                TextField("Tab title", text: $draftTitle)
                    .textFieldStyle(.roundedBorder)
            }

            TextEditor(text: $draftContent)
                .font(.body)
                .scrollContentBackground(.hidden)
                .padding(8)
                .background(
                    RoundedRectangle(cornerRadius: 8)
                        .fill(Color.textPrimary.opacity(0.04))
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(Color.glassStroke.opacity(0.35), lineWidth: 0.5)
                )

            HStack {
                if note.isSessionPad {
                    Text("Session Notes is the default destination for agent note-taking.")
                        .font(.caption)
                        .foregroundColor(.textSecondary)
                }
                Spacer()
                Button("Save") {
                    saveEdits(for: note)
                }
                .buttonStyle(.plain)
                .font(.caption.weight(.semibold))
                .foregroundColor(.primaryBlue)
            }
        }
        .padding(ThemeConstants.spacingM)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var footerView: some View {
        HStack {
            Text("Default behavior: the agent keeps writing in Session Notes unless you explicitly ask for a separate tab.")
                .font(.caption)
                .foregroundColor(.textSecondary)
            Spacer()
            if let activeNote, activeNote.isSessionPad {
                Text("Primary Workspace")
                    .font(.caption.weight(.semibold))
                    .foregroundColor(.secondaryBlue)
            }
        }
        .padding(.horizontal, ThemeConstants.spacingM)
        .padding(.vertical, 8)
    }

    private func synchronizeSelection(forceSessionPad: Bool = false) {
        if forceSessionPad, let sessionPad {
            selectedNoteId = sessionPad.id
            return
        }
        if let selectedNoteId,
           appState.notes.contains(where: { $0.id == selectedNoteId }) {
            return
        }
        selectedNoteId = sessionPad?.id ?? appState.notes.first?.id
    }

    private func select(note: Note) {
        selectedNoteId = note.id
        isEditing = false
        draftTitle = note.displayTitle
        draftContent = note.content
    }

    private func toggleEditMode() {
        guard let activeNote else { return }
        if isEditing {
            resetEditorState()
        } else {
            draftTitle = activeNote.displayTitle
            draftContent = activeNote.content
            isEditing = true
        }
    }

    private func beginRename(for note: Note) {
        select(note: note)
        isEditing = true
    }

    private func resetEditorState() {
        isEditing = false
        draftTitle = activeNote?.displayTitle ?? ""
        draftContent = activeNote?.content ?? ""
    }

    private func refreshDraftFromActiveNoteIfNeeded() {
        guard isEditing, let activeNote else { return }
        if draftContent.isEmpty && draftTitle.isEmpty {
            draftTitle = activeNote.displayTitle
            draftContent = activeNote.content
        }
    }

    private func saveEdits(for note: Note) {
        let trimmedContent = draftContent.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedContent.isEmpty else { return }
        let title: String? = note.isSessionPad ? nil : draftTitle.trimmingCharacters(in: .whitespacesAndNewlines)
        appState.updateNote(
            noteId: note.id,
            content: trimmedContent,
            title: title?.isEmpty == true ? nil : title
        )
        isEditing = false
    }

    private func loadAndShowHistory() {
        guard let activeNote else { return }
        isLoadingVersions = true
        showHistory = true
        Task { @MainActor in
            versions = await appState.fetchNoteVersions(noteId: activeNote.id)
            isLoadingVersions = false
        }
    }

    private enum ExportFormat { case markdown, plainText }

    private func exportNotes(format: ExportFormat) {
        let notes = appState.notes
        guard !notes.isEmpty else { return }

        let ext = format == .markdown ? "md" : "txt"
        let separator = format == .markdown ? "\n\n---\n\n" : "\n\n────────────────────\n\n"
        let document = notes.enumerated().map { index, note in
            let heading = format == .markdown
                ? "## \(note.displayTitle)"
                : "NOTE \(index + 1): \(note.displayTitle)"
            return "\(heading)\n\(note.displayContent)"
        }.joined(separator: separator)

        #if os(macOS)
        let panel = NSSavePanel()
        panel.nameFieldStringValue = "notes-export.\(ext)"
        panel.allowedContentTypes = format == .markdown
            ? [UTType(filenameExtension: "md") ?? .plainText]
            : [.plainText]
        panel.canCreateDirectories = true

        guard panel.runModal() == .OK, let url = panel.url else { return }
        do {
            try document.write(to: url, atomically: true, encoding: .utf8)
        } catch {
            DebugLogger.log("notes_export_error", fields: ["error": error.localizedDescription])
        }
        #else
        let tempURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("notes-export-\(UUID().uuidString).\(ext)")
        do {
            try document.write(to: tempURL, atomically: true, encoding: .utf8)
            exportShareItem = ExportShareItem(url: tempURL)
        } catch {
            DebugLogger.log("notes_export_error", fields: ["error": error.localizedDescription])
        }
        #endif
    }

    private static let relativeDateFormatter: RelativeDateTimeFormatter = {
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .abbreviated
        return formatter
    }()

    private func relativeTimestamp(for date: Date) -> String {
        Self.relativeDateFormatter.localizedString(for: date, relativeTo: Date())
    }
}

private struct ExportShareItem: Identifiable {
    let id = UUID()
    let url: URL
}

#if canImport(UIKit) && !os(macOS)
private struct ExportShareOverlay: View {
    let item: ExportShareItem
    let onDismiss: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: ThemeConstants.spacingM) {
            Text("Share Notes Export")
                .font(.headline)
                .foregroundColor(.textPrimary)

            Text("The system share sheet is open for the exported notes file.")
                .font(.subheadline)
                .foregroundColor(.textSecondary)

            ExportSharePresenter(item: item, onDismiss: onDismiss)
                .frame(width: 1, height: 1)

            HStack {
                Spacer()
                Button("Close") {
                    onDismiss()
                }
                .buttonStyle(GlassButtonStyle())
            }
        }
        .padding(ThemeConstants.spacingL)
        .frame(width: 360)
    }
}

private struct ExportSharePresenter: UIViewControllerRepresentable {
    let item: ExportShareItem
    let onDismiss: () -> Void

    func makeUIViewController(context: Context) -> ExportShareHostController {
        let controller = ExportShareHostController()
        controller.item = item
        controller.onDismiss = onDismiss
        return controller
    }

    func updateUIViewController(_ uiViewController: ExportShareHostController, context: Context) {
        uiViewController.item = item
        uiViewController.onDismiss = onDismiss
        uiViewController.presentIfNeeded()
    }
}

private final class ExportShareHostController: UIViewController {
    var item: ExportShareItem?
    var onDismiss: (() -> Void)?
    private var hasPresented = false

    override func viewDidAppear(_ animated: Bool) {
        super.viewDidAppear(animated)
        presentIfNeeded()
    }

    func presentIfNeeded() {
        guard !hasPresented, presentedViewController == nil, let item else { return }
        hasPresented = true
        let controller = UIActivityViewController(activityItems: [item.url], applicationActivities: nil)
        controller.completionWithItemsHandler = { [weak self] _, _, _, _ in
            self?.onDismiss?()
        }
        present(controller, animated: true)
    }
}
#endif

private struct NoteTabPill: View {
    let title: String
    let isActive: Bool
    let isPrimary: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(title)
                .font(.caption.weight(isPrimary ? .semibold : .medium))
                .foregroundColor(isActive ? .white : (isPrimary ? .primaryBlue : .textSecondary))
                .lineLimit(1)
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(
                    Capsule().fill(backgroundColor)
                )
        }
        .buttonStyle(.plain)
    }

    private var backgroundColor: Color {
        if isActive {
            return isPrimary ? .primaryBlue : .secondaryBlue
        }
        return isPrimary ? Color.primaryBlue.opacity(0.14) : Color.textPrimary.opacity(0.05)
    }
}

private struct NewNoteTabSheet: View {
    @State private var title: String = ""
    @State private var content: String = ""
    let onCancel: () -> Void
    let onCreate: (String, String) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: ThemeConstants.spacingM) {
            Text("New Notes Tab")
                .font(.headline)
                .foregroundColor(.textPrimary)

            TextField("Tab title", text: $title)
                .textFieldStyle(.roundedBorder)

            TextEditor(text: $content)
                .font(.body)
                .frame(minHeight: 180)
                .scrollContentBackground(.hidden)
                .padding(8)
                .background(
                    RoundedRectangle(cornerRadius: 8)
                        .fill(Color.textPrimary.opacity(0.04))
                )

            HStack {
                Spacer()
                Button("Cancel") {
                    onCancel()
                }
                .buttonStyle(.plain)
                .foregroundColor(.textSecondary)

                Button("Create Tab") {
                    let resolvedTitle = title.trimmingCharacters(in: .whitespacesAndNewlines)
                    let resolvedContent = content.trimmingCharacters(in: .whitespacesAndNewlines)
                    guard !resolvedContent.isEmpty else { return }
                    onCreate(resolvedTitle.isEmpty ? "New Tab" : resolvedTitle, resolvedContent)
                }
                .buttonStyle(.plain)
                .font(.callout.weight(.semibold))
                .foregroundColor(.primaryBlue)
                .disabled(content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
        }
        .padding(ThemeConstants.spacingM)
        .frame(minWidth: 380, idealWidth: 440, maxWidth: 520, minHeight: 300)
        .background(Color.glassBg)
    }
}

private struct NoteTypeChip: View {
    let type: String

    var body: some View {
        Text(displayLabel)
            .font(.system(size: 8, weight: .bold, design: .rounded))
            .foregroundColor(chipColor)
            .padding(.horizontal, 4)
            .padding(.vertical, 1)
            .background(
                RoundedRectangle(cornerRadius: 3)
                    .fill(chipColor.opacity(0.12))
            )
    }

    private var displayLabel: String {
        switch type {
        case "summary": return "Summary"
        case "key_points": return "Key Points"
        case "study_guide": return "Study Guide"
        case "comparison_table": return "Compare"
        case "timeline": return "Timeline"
        case "formula_sheet": return "Formulas"
        case "flashcards": return "Flashcards"
        case "cheat_sheet": return "Cheat Sheet"
        default: return type.replacingOccurrences(of: "_", with: " ").capitalized
        }
    }

    private var chipColor: Color {
        switch type {
        case "summary": return .secondaryBlue
        case "key_points": return .green
        case "study_guide": return .purple
        case "comparison_table": return .orange
        case "timeline": return .cyan
        case "formula_sheet": return .pink
        case "flashcards": return .yellow
        case "cheat_sheet": return .mint
        default: return .textSecondary
        }
    }
}

private struct NoteTagChip: View {
    let tag: String

    var body: some View {
        Text(tag)
            .font(.system(size: 8, weight: .semibold, design: .rounded))
            .foregroundColor(.textSecondary)
            .padding(.horizontal, 5)
            .padding(.vertical, 2)
            .background(
                Capsule().fill(Color.textPrimary.opacity(0.06))
            )
    }
}

private struct NoteHistoryView: View {
    let noteId: String
    let versions: [IPCNoteVersion]
    let isLoading: Bool
    var onClose: (() -> Void)?
    var onRestore: ((String) -> Void)?

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Image(systemName: "clock.arrow.circlepath")
                    .foregroundColor(.primaryBlue)
                Text("Version History")
                    .font(.headline)
                    .foregroundColor(.textPrimary)
                Spacer()
                Button(action: { onClose?() }) {
                    Image(systemName: "xmark.circle.fill")
                        .font(.system(size: 16))
                        .foregroundColor(.textSecondary.opacity(0.7))
                }
                .buttonStyle(.plain)
            }
            .padding(ThemeConstants.spacingM)

            Divider()

            if isLoading {
                VStack {
                    Spacer()
                    ProgressView("Loading history…")
                    Spacer()
                }
            } else if versions.isEmpty {
                VStack(spacing: ThemeConstants.spacingS) {
                    Spacer()
                    Text("No previous versions")
                        .font(.callout)
                        .foregroundColor(.textSecondary)
                    Spacer()
                }
            } else {
                ScrollView {
                    LazyVStack(spacing: ThemeConstants.spacingS) {
                        ForEach(versions) { version in
                            VStack(alignment: .leading, spacing: 6) {
                                HStack {
                                    Text(formattedDate(version.date))
                                        .font(.caption.weight(.medium))
                                        .foregroundColor(.secondaryBlue)
                                    Spacer()
                                    Button("Restore") {
                                        onRestore?(version.content)
                                    }
                                    .buttonStyle(.plain)
                                    .font(.caption.weight(.medium))
                                    .foregroundColor(.primaryBlue)
                                }

                                let stripped = Note.stripHTMLComment(
                                    Note.stripHTMLComment(version.content, prefix: "<!-- note-type:"),
                                    prefix: "<!-- tags:"
                                ).trimmingCharacters(in: .whitespacesAndNewlines)
                                Text(stripped)
                                    .font(.caption)
                                    .foregroundColor(.textSecondary)
                                    .lineLimit(5)
                            }
                            .padding(ThemeConstants.spacingS)
                            .background(
                                RoundedRectangle(cornerRadius: 6)
                                    .fill(Color.textPrimary.opacity(0.03))
                            )
                        }
                    }
                    .padding(ThemeConstants.spacingM)
                }
            }
        }
        .frame(minWidth: 360, idealWidth: 440, maxWidth: 560,
               minHeight: 280, idealHeight: 400, maxHeight: .infinity)
        .background(Color.glassBg)
    }

    private func formattedDate(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.dateStyle = .medium
        formatter.timeStyle = .short
        return formatter.string(from: date)
    }
}
