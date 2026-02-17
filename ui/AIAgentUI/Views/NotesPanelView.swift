//
//  NotesPanelView.swift
//  AIAgentUI
//
//  Created for Personal macOS AI Agent
//  Status: Active - Session notes panel UI with full CRUD
//

import SwiftUI
import UniformTypeIdentifiers

/// Root view for the floating notes panel.
struct NotesPanelView: View {
    @ObservedObject var appState: AppState
    @State private var newNoteText: String = ""
    @FocusState private var isInputFocused: Bool
    @State private var selectedTag: String?
    @State private var isSearchVisible: Bool = false
    @State private var searchText: String = ""
    @State private var highlightedNoteId: String?

    /// All unique tags across all notes, sorted alphabetically.
    private var allTags: [String] {
        let tags = Set(appState.notes.flatMap(\.tags))
        return tags.sorted()
    }

    /// Notes filtered by selected tag and/or search text.
    private var filteredNotes: [Note] {
        var result = appState.notes
        if let tag = selectedTag {
            result = result.filter { $0.tags.contains(tag) }
        }
        let query = searchText.trimmingCharacters(in: .whitespacesAndNewlines)
        if !query.isEmpty {
            result = result.filter {
                $0.displayContent.localizedCaseInsensitiveContains(query)
            }
        }
        return result
    }

    var body: some View {
        VStack(spacing: 0) {
            headerView
            if !allTags.isEmpty {
                tagFilterBar
            }
            Divider().background(Color.glassStroke)
            notesListView
            Divider().background(Color.glassStroke)
            createNoteBar
        }
        .frame(
            minWidth: 280, idealWidth: 340, maxWidth: .infinity,
            minHeight: 300, idealHeight: 520, maxHeight: .infinity
        )
        .liquidGlass()
        .onAppear {
            appState.loadNotes()
        }
    }

    // MARK: - Header

    @ViewBuilder
    private var headerView: some View {
        HStack(spacing: ThemeConstants.spacingS) {
            Image(systemName: "note.text")
                .font(.system(size: 16))
                .foregroundColor(.primaryBlue)

            Text("Notes")
                .font(.headline)
                .foregroundColor(.textPrimary)

            if !filteredNotes.isEmpty {
                Text("\(filteredNotes.count)")
                    .font(.caption2.monospacedDigit())
                    .fontWeight(.semibold)
                    .foregroundColor(.textSecondary)
                    .padding(.horizontal, 5)
                    .padding(.vertical, 1)
                    .background(
                        Capsule().fill(Color.textSecondary.opacity(0.15))
                    )
            }

            Spacer()

            if appState.isNotesLoading {
                ProgressView()
                    .controlSize(.small)
                    .scaleEffect(0.7)
            }

            Button(action: {
                withAnimation(.easeInOut(duration: 0.2)) {
                    isSearchVisible.toggle()
                    if !isSearchVisible { searchText = "" }
                }
            }) {
                Image(systemName: isSearchVisible ? "magnifyingglass.circle.fill" : "magnifyingglass")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(isSearchVisible ? .primaryBlue : .textSecondary)
            }
            .buttonStyle(.plain)
            .help("Search Notes")

            Menu {
                Button(action: { exportNotes(format: .markdown) }) {
                    Label("Markdown (.md)", systemImage: "doc.richtext")
                }
                Button(action: { exportNotes(format: .plainText) }) {
                    Label("Plain Text (.txt)", systemImage: "doc.plaintext")
                }
            } label: {
                Image(systemName: "square.and.arrow.up")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(.textSecondary)
            }
            .menuStyle(.borderlessButton)
            .fixedSize()
            .help("Export Notes")
            .disabled(filteredNotes.isEmpty)

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

        if isSearchVisible {
            HStack(spacing: 6) {
                Image(systemName: "magnifyingglass")
                    .font(.system(size: 11))
                    .foregroundColor(.textSecondary)
                TextField("Search notes\u{2026}", text: $searchText)
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
            .padding(.vertical, 5)
            .background(Color.textPrimary.opacity(0.04))
        }
    }

    // MARK: - Tag Filter Bar

    private var tagFilterBar: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 4) {
                // "All" chip
                Button(action: { selectedTag = nil }) {
                    Text("All")
                        .font(.system(size: 9, weight: selectedTag == nil ? .bold : .medium, design: .rounded))
                        .foregroundColor(selectedTag == nil ? .white : .textSecondary)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 3)
                        .background(
                            RoundedRectangle(cornerRadius: 4)
                                .fill(selectedTag == nil ? Color.primaryBlue : Color.textPrimary.opacity(0.06))
                        )
                }
                .buttonStyle(.plain)

                ForEach(allTags, id: \.self) { tag in
                    Button(action: { selectedTag = selectedTag == tag ? nil : tag }) {
                        Text(tag)
                            .font(.system(size: 9, weight: selectedTag == tag ? .bold : .medium, design: .rounded))
                            .foregroundColor(selectedTag == tag ? .white : .textSecondary)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 3)
                            .background(
                                RoundedRectangle(cornerRadius: 4)
                                    .fill(selectedTag == tag ? Color.primaryBlue : Color.textPrimary.opacity(0.06))
                            )
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, ThemeConstants.spacingM)
            .padding(.vertical, 4)
        }
    }

    // MARK: - Notes List

    private var notesListView: some View {
        Group {
            if appState.notes.isEmpty && !appState.isNotesLoading {
                emptyState
            } else if filteredNotes.isEmpty {
                VStack(spacing: ThemeConstants.spacingS) {
                    Spacer()
                    Text("No notes matching tag")
                        .font(.callout)
                        .foregroundColor(.textSecondary)
                    Button("Clear filter") { selectedTag = nil }
                        .buttonStyle(.plain)
                        .font(.caption.weight(.medium))
                        .foregroundColor(.primaryBlue)
                    Spacer()
                }
            } else {
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(spacing: ThemeConstants.spacingS) {
                            ForEach(filteredNotes) { note in
                                NoteCard(
                                    note: note,
                                    appState: appState,
                                    isHighlighted: highlightedNoteId == note.id,
                                    onNoteLinkTapped: { prefix in
                                        scrollToNote(prefix: prefix, proxy: proxy)
                                    }
                                )
                                .id(note.id)
                            }
                        }
                        .padding(ThemeConstants.spacingM)
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var emptyState: some View {
        VStack(spacing: ThemeConstants.spacingM) {
            Spacer()
            Image(systemName: "note.text")
                .font(.system(size: 36))
                .foregroundStyle(
                    LinearGradient(
                        colors: [Color.secondaryBlue.opacity(0.5), Color.primaryBlue.opacity(0.3)],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
            Text("No notes yet")
                .font(.headline)
                .foregroundColor(.textSecondary)
            Text("Create a note below or ask\nthe agent to take notes for you.")
                .font(.caption)
                .foregroundColor(.textSecondary.opacity(0.7))
                .multilineTextAlignment(.center)
            Spacer()
        }
        .frame(maxWidth: .infinity)
    }

    // MARK: - Create Note Bar

    private var createNoteBar: some View {
        HStack(spacing: ThemeConstants.spacingS) {
            Menu {
                ForEach(NoteTemplate.all) { tmpl in
                    Button(action: { newNoteText = tmpl.content; isInputFocused = true }) {
                        Label(tmpl.name, systemImage: tmpl.icon)
                    }
                }
            } label: {
                Image(systemName: "doc.text.fill")
                    .font(.system(size: 14))
                    .foregroundColor(.textSecondary.opacity(0.6))
            }
            .menuStyle(.borderlessButton)
            .fixedSize()
            .help("Insert Template")

            TextField("Write a note...", text: $newNoteText)
                .textFieldStyle(.plain)
                .font(.body)
                .focused($isInputFocused)
                .onSubmit { submitNote() }

            Button(action: submitNote) {
                Image(systemName: "plus.circle.fill")
                    .font(.system(size: 20))
                    .foregroundColor(
                        newNoteText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                            ? .textSecondary.opacity(0.3)
                            : .primaryBlue
                    )
            }
            .buttonStyle(.plain)
            .disabled(newNoteText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            .help("Add Note")
        }
        .padding(.horizontal, ThemeConstants.spacingM)
        .padding(.vertical, 10)
        .background(Color.textPrimary.opacity(0.02))
    }

    private func submitNote() {
        let trimmed = newNoteText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        appState.createNote(content: trimmed)
        newNoteText = ""
    }

    /// Scrolls to a note matching the given ID prefix and briefly highlights it.
    private func scrollToNote(prefix: String, proxy: ScrollViewProxy) {
        guard let note = appState.notes.first(where: { $0.id.hasPrefix(prefix) }) else { return }
        selectedTag = nil
        searchText = ""
        withAnimation(.easeInOut(duration: 0.3)) {
            proxy.scrollTo(note.id, anchor: .center)
            highlightedNoteId = note.id
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
            withAnimation { highlightedNoteId = nil }
        }
    }

    // MARK: - Export

    private enum ExportFormat { case markdown, plainText }

    private func exportNotes(format: ExportFormat) {
        let notes = filteredNotes
        guard !notes.isEmpty else { return }

        let ext = format == .markdown ? "md" : "txt"
        let separator = format == .markdown ? "\n\n---\n\n" : "\n\n────────────────────\n\n"

        let document = notes.enumerated().map { index, note in
            var header: String
            if format == .markdown {
                let typeLabel = note.noteType.map { " `[\($0)]`" } ?? ""
                let tagLabels = note.tags.isEmpty ? "" : " " + note.tags.map { "#\($0)" }.joined(separator: " ")
                let pin = note.isPinned ? " [pinned]" : ""
                header = "## Note \(index + 1)\(typeLabel)\(tagLabels)\(pin)"
            } else {
                header = "NOTE \(index + 1)"
                if note.isPinned { header += " [PINNED]" }
            }
            return "\(header)\n\(note.displayContent)"
        }.joined(separator: separator)

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
    }
}

// MARK: - Note Card

/// A single note card with view/edit/delete capabilities.
struct NoteCard: View {
    let note: Note
    @ObservedObject var appState: AppState
    var isHighlighted: Bool = false
    var onNoteLinkTapped: ((String) -> Void)?
    @State private var isEditing: Bool = false
    @State private var editText: String = ""
    @State private var isHovering: Bool = false
    @State private var isExpanded: Bool = false
    @State private var contentHeight: CGFloat = 0
    @State private var showFullView: Bool = false
    @State private var showStudyView: Bool = false
    @State private var showHistory: Bool = false
    @State private var versions: [IPCNoteVersion] = []
    @State private var isLoadingVersions: Bool = false

    /// Whether this note can be studied as flashcards.
    private var isFlashcardNote: Bool {
        let t = note.noteType
        return t == "flashcards" || t == "study_guide"
    }

    var body: some View {
        HStack(spacing: 0) {
            // Accent bar for agent-created notes
            if note.isAgentCreated {
                RoundedRectangle(cornerRadius: 2)
                    .fill(
                        LinearGradient(
                            colors: [Color.secondaryBlue, Color.primaryBlue],
                            startPoint: .top,
                            endPoint: .bottom
                        )
                    )
                    .frame(width: 3)
                    .padding(.vertical, 6)
            }

            VStack(alignment: .leading, spacing: 6) {
                // Top row: badges + timestamp + actions
                HStack(spacing: 4) {
                    if note.isPinned {
                        Image(systemName: "pin.fill")
                            .font(.system(size: 9))
                            .foregroundColor(.orange)
                    }
                    if note.isAgentCreated {
                        Text("AI")
                            .font(.system(size: 9, weight: .bold, design: .rounded))
                            .foregroundColor(.primaryBlue)
                            .padding(.horizontal, 4)
                            .padding(.vertical, 1)
                            .background(
                                RoundedRectangle(cornerRadius: 3)
                                    .fill(Color.primaryBlue.opacity(0.12))
                            )
                    }
                    if let noteType = note.noteType {
                        NoteTypeChip(type: noteType)
                    }
                    ForEach(note.tags.prefix(3), id: \.self) { tag in
                        NoteTagChip(tag: tag)
                    }
                    Text(relativeTimestamp)
                        .font(.caption2)
                        .foregroundColor(.textSecondary.opacity(0.6))
                    Spacer()

                    if isHovering && !isEditing {
                        actionButtons
                    }
                }

                // Content or editor
                if isEditing {
                    editView
                } else {
                    noteContentView
                }
            }
            .padding(10)
        }
        .background(
            RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusMedium)
                .fill(cardBackground)
        )
        .overlay(
            RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusMedium)
                .stroke(
                    isHighlighted ? Color.primaryBlue.opacity(0.8)
                        : Color.glassStroke.opacity(isHovering ? 0.7 : 0.4),
                    lineWidth: isHighlighted ? 1.5 : 0.5
                )
        )
        .shadow(
            color: Color.glassShadow.opacity(isHovering ? 0.12 : 0.05),
            radius: isHovering ? 6 : 2,
            y: isHovering ? 3 : 1
        )
        .scaleEffect(isHovering ? 1.01 : 1.0)
        .animation(.easeInOut(duration: 0.15), value: isHovering)
        .onHover { hovering in
            withAnimation(.easeInOut(duration: 0.15)) {
                isHovering = hovering
            }
        }
        .sheet(isPresented: $showFullView) {
            NoteFullView(note: note, appState: appState)
        }
        .sheet(isPresented: $showStudyView) {
            let cards = FlashcardParser.parse(note.displayContent)
            let title = note.displayContent.components(separatedBy: "\n").first.flatMap {
                $0.replacingOccurrences(of: "**", with: "").trimmingCharacters(in: .whitespaces)
            } ?? "Flashcards"
            FlashcardStudyView(noteTitle: title, cards: cards)
        }
        .sheet(isPresented: $showHistory) {
            NoteHistoryView(
                noteId: note.id,
                versions: versions,
                isLoading: isLoadingVersions,
                onRestore: { content in
                    appState.updateNote(noteId: note.id, content: content)
                    showHistory = false
                }
            )
        }
    }

    private func loadAndShowHistory() {
        isLoadingVersions = true
        showHistory = true
        Task { @MainActor in
            versions = await appState.fetchNoteVersions(noteId: note.id)
            isLoadingVersions = false
        }
    }

    // MARK: - Subviews

    private var actionButtons: some View {
        HStack(spacing: 6) {
            Button(action: {
                appState.updateNote(noteId: note.id, isPinned: !note.isPinned)
            }) {
                Image(systemName: note.isPinned ? "pin.slash" : "pin")
                    .font(.system(size: 10))
                    .foregroundColor(.textSecondary)
            }
            .buttonStyle(.plain)
            .help(note.isPinned ? "Unpin" : "Pin")

            if isFlashcardNote {
                Button(action: { showStudyView = true }) {
                    Image(systemName: "rectangle.on.rectangle.angled")
                        .font(.system(size: 10))
                        .foregroundColor(.primaryBlue)
                }
                .buttonStyle(.plain)
                .help("Study Flashcards")
            }

            Button(action: { showFullView = true }) {
                Image(systemName: "arrow.up.left.and.arrow.down.right")
                    .font(.system(size: 10))
                    .foregroundColor(.textSecondary)
            }
            .buttonStyle(.plain)
            .help("Full View")

            Button(action: {
                editText = note.content
                isEditing = true
            }) {
                Image(systemName: "pencil")
                    .font(.system(size: 10))
                    .foregroundColor(.textSecondary)
            }
            .buttonStyle(.plain)
            .help("Edit")

            Button(action: loadAndShowHistory) {
                Image(systemName: "clock.arrow.circlepath")
                    .font(.system(size: 10))
                    .foregroundColor(.textSecondary)
            }
            .buttonStyle(.plain)
            .help("Version History")

            Button(action: {
                appState.deleteNote(noteId: note.id)
            }) {
                Image(systemName: "trash")
                    .font(.system(size: 10))
                    .foregroundColor(.red.opacity(0.7))
            }
            .buttonStyle(.plain)
            .help("Delete")
        }
        .transition(.opacity)
    }

    private var editView: some View {
        VStack(alignment: .trailing, spacing: 6) {
            TextEditor(text: $editText)
                .font(.body)
                .frame(minHeight: 60, maxHeight: 150)
                .scrollContentBackground(.hidden)
                .padding(4)
                .background(
                    RoundedRectangle(cornerRadius: 4)
                        .fill(Color.textPrimary.opacity(0.05))
                )

            HStack(spacing: 8) {
                Button("Cancel") {
                    isEditing = false
                    editText = ""
                }
                .buttonStyle(.plain)
                .font(.caption)
                .foregroundColor(.textSecondary)

                Button("Save") {
                    let trimmed = editText.trimmingCharacters(in: .whitespacesAndNewlines)
                    if !trimmed.isEmpty {
                        appState.updateNote(noteId: note.id, content: trimmed)
                    }
                    isEditing = false
                    editText = ""
                }
                .buttonStyle(.plain)
                .font(.caption.weight(.semibold))
                .foregroundColor(.primaryBlue)
                .disabled(editText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
        }
    }

    // MARK: - Markdown Content

    private static let collapseThreshold: CGFloat = 120

    /// Renders note content using the shared `NoteMarkdownView` with expand/collapse.
    private var noteContentView: some View {
        let blocks = NoteMarkdownParser.parse(note.displayContent)
        let needsCollapse = contentHeight > Self.collapseThreshold && !isExpanded

        return VStack(alignment: .leading, spacing: 0) {
            NoteMarkdownView(blocks: blocks, imageFetcher: { imageId in
                    await appState.fetchNoteImage(imageId: imageId)
                }, noteType: note.noteType, onNoteTapped: onNoteLinkTapped)
                .background(
                    GeometryReader { geo in
                        Color.clear.preference(
                            key: NoteContentHeightKey.self,
                            value: geo.size.height
                        )
                    }
                )
                .onPreferenceChange(NoteContentHeightKey.self) { height in
                    contentHeight = height
                }
                .frame(maxHeight: needsCollapse ? Self.collapseThreshold : .infinity, alignment: .top)
                .clipped()

            if needsCollapse {
                // Gradient fade overlay + "Show more" button
                LinearGradient(
                    colors: [cardBackground.opacity(0), cardBackground],
                    startPoint: .top,
                    endPoint: .bottom
                )
                .frame(height: 20)
                .offset(y: -20)
                .allowsHitTesting(false)

                Button(action: { withAnimation(.easeInOut(duration: 0.2)) { isExpanded = true } }) {
                    Text("Show more")
                        .font(.caption2.weight(.medium))
                        .foregroundColor(.secondaryBlue)
                }
                .buttonStyle(.plain)
            } else if isExpanded && contentHeight > Self.collapseThreshold {
                Button(action: { withAnimation(.easeInOut(duration: 0.2)) { isExpanded = false } }) {
                    Text("Show less")
                        .font(.caption2.weight(.medium))
                        .foregroundColor(.secondaryBlue)
                }
                .buttonStyle(.plain)
                .padding(.top, 4)
            }
        }
    }

    // MARK: - Helpers

    private var cardBackground: Color {
        if note.isPinned {
            return Color.orange.opacity(isHovering ? 0.10 : 0.06)
        }
        if note.isAgentCreated {
            return Color.primaryBlue.opacity(isHovering ? 0.08 : 0.04)
        }
        return Color.textPrimary.opacity(isHovering ? 0.06 : 0.03)
    }

    private static let relativeDateFormatter: RelativeDateTimeFormatter = {
        let f = RelativeDateTimeFormatter()
        f.unitsStyle = .abbreviated
        return f
    }()

    private var relativeTimestamp: String {
        Self.relativeDateFormatter.localizedString(for: note.updatedAt, relativeTo: Date())
    }
}

// MARK: - Note Full View

/// Full-size modal view for a single note with rich markdown rendering.
struct NoteFullView: View {
    let note: Note
    @ObservedObject var appState: AppState
    @Environment(\.dismiss) private var dismiss
    @State private var isEditing: Bool = false
    @State private var editText: String = ""

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack(spacing: ThemeConstants.spacingS) {
                if note.isAgentCreated {
                    Text("AI")
                        .font(.system(size: 10, weight: .bold, design: .rounded))
                        .foregroundColor(.primaryBlue)
                        .padding(.horizontal, 5)
                        .padding(.vertical, 2)
                        .background(
                            RoundedRectangle(cornerRadius: 4)
                                .fill(Color.primaryBlue.opacity(0.12))
                        )
                }
                if note.isPinned {
                    Image(systemName: "pin.fill")
                        .font(.system(size: 11))
                        .foregroundColor(.orange)
                }
                if let noteType = note.noteType {
                    NoteTypeChip(type: noteType)
                }
                Text(fullTimestamp)
                    .font(.caption)
                    .foregroundColor(.textSecondary)
                Spacer()

                Button(action: {
                    editText = note.content
                    isEditing.toggle()
                }) {
                    Image(systemName: isEditing ? "xmark" : "pencil")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(.textSecondary)
                }
                .buttonStyle(.plain)
                .help(isEditing ? "Cancel Edit" : "Edit")

                Button(action: {
                    appState.updateNote(noteId: note.id, isPinned: !note.isPinned)
                }) {
                    Image(systemName: note.isPinned ? "pin.slash" : "pin")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(.textSecondary)
                }
                .buttonStyle(.plain)
                .help(note.isPinned ? "Unpin" : "Pin")

                Button(action: { dismiss() }) {
                    Image(systemName: "xmark.circle.fill")
                        .font(.system(size: 14))
                        .foregroundColor(.textSecondary.opacity(0.6))
                }
                .buttonStyle(.plain)
                .help("Close")
            }
            .padding(.horizontal, ThemeConstants.spacingM)
            .padding(.vertical, ThemeConstants.spacingS)

            Divider().background(Color.glassStroke)

            // Content
            if isEditing {
                VStack(alignment: .trailing, spacing: ThemeConstants.spacingS) {
                    TextEditor(text: $editText)
                        .font(.body)
                        .scrollContentBackground(.hidden)
                        .padding(8)
                        .background(
                            RoundedRectangle(cornerRadius: 6)
                                .fill(Color.textPrimary.opacity(0.04))
                        )

                    Button("Save") {
                        let trimmed = editText.trimmingCharacters(in: .whitespacesAndNewlines)
                        if !trimmed.isEmpty {
                            appState.updateNote(noteId: note.id, content: trimmed)
                        }
                        isEditing = false
                        editText = ""
                    }
                    .buttonStyle(.plain)
                    .font(.callout.weight(.semibold))
                    .foregroundColor(.primaryBlue)
                    .disabled(editText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
                .padding(ThemeConstants.spacingM)
            } else {
                ScrollView {
                    NoteMarkdownView(
                        blocks: NoteMarkdownParser.parse(note.displayContent),
                        imageFetcher: { imageId in
                            await appState.fetchNoteImage(imageId: imageId)
                        },
                        noteType: note.noteType
                    )
                    .padding(ThemeConstants.spacingM)
                }
            }
        }
        .frame(minWidth: 400, idealWidth: 520, maxWidth: 700,
               minHeight: 300, idealHeight: 480, maxHeight: .infinity)
        .background(Color.glassBg)
    }

    private static let dateFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateStyle = .medium
        f.timeStyle = .short
        return f
    }()

    private var fullTimestamp: String {
        Self.dateFormatter.string(from: note.updatedAt)
    }
}

// MARK: - Note Type Chip

/// Colored badge displaying the note's semantic type.
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

// MARK: - Tag Chip

// MARK: - Note History View

/// Sheet showing version history for a note with content previews and restore option.
private struct NoteHistoryView: View {
    let noteId: String
    let versions: [IPCNoteVersion]
    let isLoading: Bool
    var onRestore: ((String) -> Void)?
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Image(systemName: "clock.arrow.circlepath")
                    .foregroundColor(.primaryBlue)
                Text("Version History")
                    .font(.headline)
                    .foregroundColor(.textPrimary)
                Spacer()
                if !versions.isEmpty {
                    Text("\(versions.count) version\(versions.count == 1 ? "" : "s")")
                        .font(.caption)
                        .foregroundColor(.textSecondary)
                }
                Button(action: { dismiss() }) {
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
                    ProgressView("Loading history\u{2026}")
                        .font(.callout)
                    Spacer()
                }
            } else if versions.isEmpty {
                VStack(spacing: ThemeConstants.spacingS) {
                    Spacer()
                    Image(systemName: "clock")
                        .font(.system(size: 28))
                        .foregroundColor(.textSecondary.opacity(0.4))
                    Text("No previous versions")
                        .font(.callout)
                        .foregroundColor(.textSecondary)
                    Text("Versions are saved each time the note is edited.")
                        .font(.caption)
                        .foregroundColor(.textSecondary.opacity(0.7))
                    Spacer()
                }
            } else {
                ScrollView {
                    LazyVStack(spacing: ThemeConstants.spacingS) {
                        ForEach(versions) { version in
                            versionCard(version)
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

    @ViewBuilder
    private func versionCard(_ version: IPCNoteVersion) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(formattedDate(version.date))
                    .font(.caption.weight(.medium))
                    .foregroundColor(.secondaryBlue)
                Spacer()
                Button(action: { onRestore?(version.content) }) {
                    Label("Restore", systemImage: "arrow.uturn.backward")
                        .font(.caption.weight(.medium))
                        .foregroundColor(.primaryBlue)
                }
                .buttonStyle(.plain)
            }

            // Content preview (first 4 lines, stripped of metadata)
            let stripped = Note.stripHTMLComment(
                Note.stripHTMLComment(version.content, prefix: "<!-- note-type:"),
                prefix: "<!-- tags:"
            ).trimmingCharacters(in: .whitespacesAndNewlines)
            let preview = stripped.components(separatedBy: "\n").prefix(4).joined(separator: "\n")
            Text(preview)
                .font(.caption)
                .foregroundColor(.textSecondary)
                .lineLimit(4)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(ThemeConstants.spacingS)
        .background(
            RoundedRectangle(cornerRadius: 6)
                .fill(Color.textPrimary.opacity(0.03))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 6)
                .stroke(Color.glassStroke.opacity(0.3), lineWidth: 0.5)
        )
    }

    private static let dateFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateStyle = .medium
        f.timeStyle = .short
        return f
    }()

    private func formattedDate(_ date: Date) -> String {
        Self.dateFormatter.string(from: date)
    }
}

private struct NoteTagChip: View {
    let tag: String

    /// Deterministic color from tag string hash.
    private var chipColor: Color {
        let colors: [Color] = [.blue, .green, .orange, .purple, .pink, .cyan, .mint, .indigo, .teal, .yellow]
        let hash = abs(tag.hashValue)
        return colors[hash % colors.count]
    }

    var body: some View {
        Text(tag)
            .font(.system(size: 7, weight: .semibold, design: .rounded))
            .foregroundColor(chipColor)
            .padding(.horizontal, 4)
            .padding(.vertical, 1)
            .background(
                RoundedRectangle(cornerRadius: 3)
                    .fill(chipColor.opacity(0.10))
            )
    }
}

// MARK: - Preference Key for Content Height Measurement

private struct NoteContentHeightKey: PreferenceKey {
    static let defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) {
        value = max(value, nextValue())
    }
}

// MARK: - Note Templates

struct NoteTemplate: Identifiable {
    let id: String
    let name: String
    let icon: String
    let content: String

    static var all: [NoteTemplate] { [
        NoteTemplate(
            id: "meeting",
            name: "Meeting Notes",
            icon: "person.3",
            content: """
            ## Meeting Notes
            **Date:** \(Self.todayString)
            **Attendees:**
            -

            ## Agenda
            1.

            ## Action Items
            - [ ]

            ## Key Decisions
            -
            """
        ),
        NoteTemplate(
            id: "lecture",
            name: "Lecture Notes",
            icon: "book",
            content: """
            ## Lecture Notes
            **Topic:**
            **Date:** \(Self.todayString)

            ## Key Concepts
            -

            ## Definitions
            - **Term:** Definition

            ## Questions
            -

            ## Summary

            """
        ),
        NoteTemplate(
            id: "research",
            name: "Research Notes",
            icon: "magnifyingglass",
            content: """
            ## Research Notes
            **Topic:**

            ## Sources
            -

            ## Key Findings
            -

            ## Open Questions
            -

            ## Next Steps
            -
            """
        ),
        NoteTemplate(
            id: "proscons",
            name: "Pros & Cons",
            icon: "scale.3d",
            content: """
            ## Pros & Cons
            **Decision:**

            ## Pros
            -

            ## Cons
            -

            ## Verdict

            """
        ),
        NoteTemplate(
            id: "weekly",
            name: "Weekly Review",
            icon: "calendar",
            content: """
            ## Weekly Review
            **Week of:** \(Self.todayString)

            ## Accomplishments
            -

            ## Challenges
            -

            ## Learnings
            -

            ## Next Week Goals
            -
            """
        ),
    ] }

    private static let mediumDateFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateStyle = .medium
        return f
    }()

    private static var todayString: String {
        mediumDateFormatter.string(from: Date())
    }
}
