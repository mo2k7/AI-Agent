//
//  NoteMarkdownRenderer.swift
//  AIAgentUI
//
//  Created for Personal macOS AI Agent
//  Status: Active - Shared markdown parser + note-optimized renderer
//

import SwiftUI

// MARK: - Shared Markdown Block Model

/// A single parsed markdown block. Shared between ResponseBubble and NoteCard.
struct MarkdownBlock: Identifiable, Sendable {
    enum Kind: Sendable {
        case heading(level: Int, text: String)
        case paragraph(String)
        case bullet(items: [String])
        case numbered(items: [String])
        case quote(String)
        case code(String)
        case table(headers: [String], rows: [[String]])
        case image(altText: String, imageRef: String)
    }

    let id: Int
    let kind: Kind
}

// MARK: - Markdown Parser

/// Parses raw markdown text into structured blocks.
enum NoteMarkdownParser {

    private static let headingRegex = try? NSRegularExpression(pattern: #"^(#{1,3})\s+(.+)$"#)

    /// Parse a markdown string into an array of `MarkdownBlock` values.
    static func parse(_ text: String) -> [MarkdownBlock] {
        let normalized = text.replacingOccurrences(of: "\r\n", with: "\n")
        if normalized.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return []
        }

        let lines = normalized.components(separatedBy: "\n")
        var parsedKinds: [MarkdownBlock.Kind] = []
        parsedKinds.reserveCapacity(max(4, lines.count / 2))

        var paragraphLines: [String] = []
        var bulletItems: [String] = []
        var numberedItems: [String] = []
        var quoteLines: [String] = []
        var codeLines: [String] = []
        var inCodeFence = false

        // Table accumulator
        var tableHeaderLine: String?
        var tableRows: [String] = []
        var awaitingTableSeparator = false

        func flushParagraph() {
            guard !paragraphLines.isEmpty else { return }
            parsedKinds.append(.paragraph(paragraphLines.joined(separator: "\n")))
            paragraphLines.removeAll(keepingCapacity: true)
        }

        func flushBullets() {
            guard !bulletItems.isEmpty else { return }
            parsedKinds.append(.bullet(items: bulletItems))
            bulletItems.removeAll(keepingCapacity: true)
        }

        func flushNumbered() {
            guard !numberedItems.isEmpty else { return }
            parsedKinds.append(.numbered(items: numberedItems))
            numberedItems.removeAll(keepingCapacity: true)
        }

        func flushQuote() {
            guard !quoteLines.isEmpty else { return }
            parsedKinds.append(.quote(quoteLines.joined(separator: "\n")))
            quoteLines.removeAll(keepingCapacity: true)
        }

        func flushCode() {
            guard !codeLines.isEmpty else { return }
            parsedKinds.append(.code(codeLines.joined(separator: "\n")))
            codeLines.removeAll(keepingCapacity: true)
        }

        func flushTable() {
            guard let headerLine = tableHeaderLine else { return }
            let headers = parseTableCells(headerLine)
            let rows = tableRows.map { parseTableCells($0) }
            if !headers.isEmpty {
                parsedKinds.append(.table(headers: headers, rows: rows))
            }
            tableHeaderLine = nil
            tableRows.removeAll(keepingCapacity: true)
            awaitingTableSeparator = false
        }

        func flushNonCode() {
            flushParagraph()
            flushBullets()
            flushNumbered()
            flushQuote()
            flushTable()
        }

        for line in lines {
            let trimmed = line.trimmingCharacters(in: .whitespaces)

            // --- Code fence handling ---
            if inCodeFence {
                if trimmed.hasPrefix("```") {
                    flushCode()
                    inCodeFence = false
                } else {
                    codeLines.append(line)
                }
                continue
            }

            if trimmed.hasPrefix("```") {
                flushNonCode()
                inCodeFence = true
                continue
            }

            // --- Table handling ---
            if awaitingTableSeparator {
                if isTableSeparator(trimmed) {
                    // Confirmed: previous line was a header, this is the separator.
                    awaitingTableSeparator = false
                    continue
                } else {
                    // Not a table — flush the header line as a paragraph.
                    if let header = tableHeaderLine {
                        paragraphLines.append(header)
                    }
                    tableHeaderLine = nil
                    awaitingTableSeparator = false
                    // Fall through to process current line normally.
                }
            }

            if tableHeaderLine != nil && !awaitingTableSeparator {
                // We're inside a table body.
                if isTableRow(trimmed) {
                    tableRows.append(trimmed)
                    continue
                } else {
                    flushTable()
                    // Fall through to process current line normally.
                }
            }

            if isTableRow(trimmed) && tableHeaderLine == nil {
                flushNonCode()
                tableHeaderLine = trimmed
                awaitingTableSeparator = true
                continue
            }

            // --- Image reference handling ---
            if let imageMatch = parseImageLine(trimmed) {
                flushNonCode()
                parsedKinds.append(.image(altText: imageMatch.alt, imageRef: imageMatch.ref))
                continue
            }

            // --- Empty line ---
            if trimmed.isEmpty {
                flushNonCode()
                continue
            }

            // --- Heading ---
            if let (level, heading) = parseHeadingLine(trimmed) {
                flushNonCode()
                parsedKinds.append(.heading(level: level, text: heading))
                continue
            }

            // --- Bullet ---
            if let bullet = parseBulletItem(trimmed) {
                flushParagraph()
                flushNumbered()
                flushQuote()
                bulletItems.append(bullet)
                continue
            }

            // --- Numbered ---
            if let numbered = parseNumberedItem(trimmed) {
                flushParagraph()
                flushBullets()
                flushQuote()
                numberedItems.append(numbered)
                continue
            }

            // --- Quote ---
            if let quote = parseQuoteLine(trimmed) {
                flushParagraph()
                flushBullets()
                flushNumbered()
                quoteLines.append(quote)
                continue
            }

            // --- Paragraph (default) ---
            flushBullets()
            flushNumbered()
            flushQuote()
            paragraphLines.append(trimmed)
        }

        flushNonCode()
        if inCodeFence {
            flushCode()
        }

        return parsedKinds.enumerated().map { idx, kind in
            MarkdownBlock(id: idx, kind: kind)
        }
    }

    // MARK: - Line Parsers

    private static func parseHeadingLine(_ line: String) -> (Int, String)? {
        guard let regex = headingRegex else { return nil }
        let range = NSRange(location: 0, length: (line as NSString).length)
        guard let match = regex.firstMatch(in: line, range: range),
              match.numberOfRanges == 3 else {
            return nil
        }
        let hashes = (line as NSString).substring(with: match.range(at: 1))
        let title = (line as NSString).substring(with: match.range(at: 2))
        return (max(1, min(hashes.count, 3)), title)
    }

    static func parseBulletItem(_ line: String) -> String? {
        if line.hasPrefix("- ") || line.hasPrefix("* ") || line.hasPrefix("• ") {
            return String(line.dropFirst(2)).trimmingCharacters(in: .whitespaces)
        }
        return nil
    }

    private static func parseNumberedItem(_ line: String) -> String? {
        guard let dotIndex = line.firstIndex(of: ".") else { return nil }
        let prefix = line[..<dotIndex]
        guard !prefix.isEmpty, prefix.allSatisfy(\.isNumber) else { return nil }
        let restStart = line.index(after: dotIndex)
        let rest = line[restStart...].trimmingCharacters(in: .whitespaces)
        return rest.isEmpty ? nil : rest
    }

    private static func parseQuoteLine(_ line: String) -> String? {
        guard line.hasPrefix("> ") else { return nil }
        return String(line.dropFirst(2))
    }

    // MARK: - Table Parsers

    private static func isTableRow(_ line: String) -> Bool {
        let trimmed = line.trimmingCharacters(in: .whitespaces)
        return trimmed.hasPrefix("|") && trimmed.hasSuffix("|") && trimmed.count > 2
    }

    private static func isTableSeparator(_ line: String) -> Bool {
        let trimmed = line.trimmingCharacters(in: .whitespaces)
        guard trimmed.hasPrefix("|") && trimmed.hasSuffix("|") else { return false }
        let inner = trimmed.dropFirst().dropLast()
        // Must contain only dashes, pipes, spaces, and colons (for alignment)
        return inner.allSatisfy { $0 == "-" || $0 == "|" || $0 == " " || $0 == ":" }
    }

    static func parseTableCells(_ line: String) -> [String] {
        let trimmed = line.trimmingCharacters(in: .whitespaces)
        let inner = trimmed.hasPrefix("|") ? String(trimmed.dropFirst()) : trimmed
        let cleaned = inner.hasSuffix("|") ? String(inner.dropLast()) : inner
        return cleaned.components(separatedBy: "|").map {
            $0.trimmingCharacters(in: .whitespaces)
        }
    }

    // MARK: - Image Parser

    private static func parseImageLine(_ line: String) -> (alt: String, ref: String)? {
        // Matches: ![alt text](note-image://uuid) or ![alt text](any-url)
        guard line.hasPrefix("![") else { return nil }
        guard let closeBracket = line.firstIndex(of: "]"),
              closeBracket > line.index(line.startIndex, offsetBy: 2) else { return nil }
        let alt = String(line[line.index(line.startIndex, offsetBy: 2)..<closeBracket])
        let afterBracket = line.index(after: closeBracket)
        guard afterBracket < line.endIndex,
              line[afterBracket] == "(" else { return nil }
        let parenStart = line.index(after: afterBracket)
        guard let closeParen = line.lastIndex(of: ")"),
              closeParen > parenStart else { return nil }
        let ref = String(line[parenStart..<closeParen])
        return (alt, ref)
    }
}

// MARK: - Inline Markdown Helper

/// Regex matching `[[note-id-prefix]]` cross-reference syntax.
private let _noteLinkRegex = try! NSRegularExpression(pattern: #"\[\[([a-zA-Z0-9_-]{4,36})\]\]"#)

/// Converts `[[id]]` references to markdown links before parsing.
private func expandNoteLinks(_ source: String) -> String {
    let range = NSRange(location: 0, length: (source as NSString).length)
    return _noteLinkRegex.stringByReplacingMatches(
        in: source, range: range,
        withTemplate: "[$1](notelink://$1)"
    )
}

/// Parses inline markdown (bold, italic, code) using AttributedString.
func noteInlineMarkdown(_ source: String) -> AttributedString {
    let expanded = expandNoteLinks(source)
    let options = AttributedString.MarkdownParsingOptions(
        interpretedSyntax: .inlineOnlyPreservingWhitespace
    )
    return (try? AttributedString(markdown: expanded, options: options)) ?? AttributedString(expanded)
}

/// Study-type note types that get key-term pill treatment.
private let _studyNoteTypes: Set<String> = ["study_guide", "key_points", "flashcards", "cheat_sheet", "formula_sheet"]

/// Parses inline markdown with study-mode visual treatment: bold text gets a colored pill background.
func noteInlineMarkdownStudy(_ source: String) -> AttributedString {
    var attr = noteInlineMarkdown(source)
    // Walk the attributed string and add background color to bold runs
    for run in attr.runs {
        if let inlinePresentationIntent = run.inlinePresentationIntent,
           inlinePresentationIntent.contains(.stronglyEmphasized) {
            let range = run.range
            attr[range].backgroundColor = Color.primaryBlue.opacity(0.10)
        }
    }
    return attr
}

// MARK: - NoteMarkdownView

/// Renders an array of MarkdownBlocks with note-appropriate compact styling.
struct NoteMarkdownView: View {
    let blocks: [MarkdownBlock]
    /// Optional async closure to fetch a note image by ID. When nil, image blocks show a placeholder.
    var imageFetcher: ((String) async -> PlatformImage?)?
    /// Optional note type — study-type notes get key-term pill treatment on bold text.
    var noteType: String?
    /// Optional callback when a `[[note-id]]` cross-reference link is tapped.
    var onNoteTapped: ((String) -> Void)?

    /// Whether this note type qualifies for study-mode visual treatment.
    private var isStudyType: Bool {
        guard let noteType else { return false }
        return _studyNoteTypes.contains(noteType)
    }

    /// Renders inline markdown, applying study-mode pill treatment when appropriate.
    private func inlineMD(_ source: String) -> AttributedString {
        isStudyType ? noteInlineMarkdownStudy(source) : noteInlineMarkdown(source)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            ForEach(blocks) { block in
                renderBlock(block)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .environment(\.openURL, OpenURLAction { url in
            if url.scheme == "notelink", let noteId = url.host {
                onNoteTapped?(noteId)
                return .handled
            }
            return .systemAction
        })
    }

    @ViewBuilder
    private func renderBlock(_ block: MarkdownBlock) -> some View {
        switch block.kind {

        case .heading(let level, let text):
            HStack(alignment: .center, spacing: 6) {
                RoundedRectangle(cornerRadius: 2)
                    .fill(Color.secondaryBlue.opacity(0.65))
                    .frame(width: 3, height: headingHeight(level))
                Text(inlineMD(text))
                    .font(headingFont(level))
                    .fontWeight(.semibold)
                    .foregroundColor(.textPrimary)
                    .lineLimit(nil)
                    .fixedSize(horizontal: false, vertical: true)
            }

        case .paragraph(let text):
            Text(inlineMD(text))
                .font(.callout)
                .foregroundColor(.textPrimary)
                .lineSpacing(2)
                .lineLimit(nil)
                .fixedSize(horizontal: false, vertical: true)

        case .bullet(let items):
            VStack(alignment: .leading, spacing: 3) {
                ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                    HStack(alignment: .top, spacing: 6) {
                        Circle()
                            .fill(Color.secondaryBlue.opacity(0.8))
                            .frame(width: 4, height: 4)
                            .padding(.top, 6)
                        Text(inlineMD(item))
                            .font(.callout)
                            .foregroundColor(.textPrimary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }

        case .numbered(let items):
            VStack(alignment: .leading, spacing: 3) {
                ForEach(Array(items.enumerated()), id: \.offset) { index, item in
                    HStack(alignment: .top, spacing: 6) {
                        Text("\(index + 1).")
                            .font(.system(.callout, design: .rounded))
                            .fontWeight(.semibold)
                            .foregroundColor(.secondaryBlue)
                            .frame(minWidth: 20, alignment: .trailing)
                        Text(inlineMD(item))
                            .font(.callout)
                            .foregroundColor(.textPrimary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }

        case .quote(let text):
            HStack(alignment: .top, spacing: 6) {
                RoundedRectangle(cornerRadius: 2)
                    .fill(Color.secondaryBlue.opacity(0.55))
                    .frame(width: 3)
                Text(inlineMD(text))
                    .font(.callout.italic())
                    .foregroundColor(.textSecondary)
                    .lineSpacing(2)
                    .fixedSize(horizontal: false, vertical: true)
            }

        case .code(let code):
            ScrollView(.horizontal, showsIndicators: false) {
                Text(code)
                    .font(.system(.caption, design: .monospaced))
                    .foregroundColor(.textPrimary)
                    .lineSpacing(2)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .padding(8)
            .background(Color.textPrimary.opacity(0.05))
            .clipShape(RoundedRectangle(cornerRadius: 6))

        case .table(let headers, let rows):
            tableView(headers: headers, rows: rows)

        case .image(let altText, let imageRef):
            NoteImageView(altText: altText, imageRef: imageRef, fetcher: imageFetcher)
        }
    }

    // MARK: - Table Renderer

    @ViewBuilder
    private func tableView(headers: [String], rows: [[String]]) -> some View {
        VStack(spacing: 0) {
            // Header row
            HStack(spacing: 0) {
                ForEach(headers.indices, id: \.self) { i in
                    Text(inlineMD(headers[i]))
                        .font(.caption.weight(.semibold))
                        .foregroundColor(.textPrimary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 5)
                }
            }
            .background(Color.secondaryBlue.opacity(0.12))

            Divider()

            // Data rows
            ForEach(rows.indices, id: \.self) { rowIdx in
                HStack(spacing: 0) {
                    let row = rows[rowIdx]
                    ForEach(row.indices, id: \.self) { colIdx in
                        Text(inlineMD(row[colIdx]))
                            .font(.caption)
                            .foregroundColor(.textPrimary)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 4)
                    }
                }
                .background(rowIdx % 2 == 1 ? Color.textPrimary.opacity(0.02) : Color.clear)
                if rowIdx < rows.count - 1 {
                    Divider().opacity(0.5)
                }
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: 6))
        .overlay(
            RoundedRectangle(cornerRadius: 6)
                .stroke(Color.glassStroke.opacity(0.5), lineWidth: 0.5)
        )
    }

    // MARK: - Helpers

    private func headingFont(_ level: Int) -> Font {
        switch level {
        case 1: return .system(.body, design: .default).weight(.bold)
        case 2: return .system(.callout, design: .default).weight(.semibold)
        default: return .system(.caption, design: .default).weight(.semibold)
        }
    }

    private func headingHeight(_ level: Int) -> CGFloat {
        switch level {
        case 1: return 18
        case 2: return 15
        default: return 12
        }
    }
}

// MARK: - NoteImageView

/// Async-loading image view for note-embedded images.
/// Extracts the image_id from a `note-image://` URI, fetches via the provided closure,
/// and renders the image with rounded corners and an alt-text caption.
struct NoteImageView: View {
    let altText: String
    let imageRef: String
    var fetcher: ((String) async -> PlatformImage?)?

    @State private var platformImage: PlatformImage?
    @State private var isLoading: Bool = false
    @State private var didFail: Bool = false

    /// Extracts image ID from "note-image://uuid" URI.
    private var imageId: String? {
        guard imageRef.hasPrefix("note-image://") else { return nil }
        let id = String(imageRef.dropFirst("note-image://".count))
        return id.isEmpty ? nil : id
    }

    var body: some View {
        Group {
            if let platformImage {
                VStack(spacing: 4) {
                    platformImageView(platformImage)
                        .resizable()
                        .aspectRatio(contentMode: .fit)
                        .frame(maxWidth: .infinity, maxHeight: 300)
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                    if !altText.isEmpty {
                        Text(altText)
                            .font(.caption2)
                            .foregroundColor(.textSecondary)
                            .lineLimit(2)
                    }
                }
            } else if isLoading {
                HStack(spacing: 8) {
                    ProgressView()
                        .controlSize(.small)
                    Text("Loading image\u{2026}")
                        .font(.caption)
                        .foregroundColor(.textSecondary)
                }
                .padding(12)
                .frame(maxWidth: .infinity, alignment: .center)
                .background(Color.textPrimary.opacity(0.03))
                .clipShape(RoundedRectangle(cornerRadius: 8))
            } else if didFail {
                HStack(spacing: 6) {
                    Image(systemName: "exclamationmark.triangle")
                        .foregroundColor(.orange)
                    Text(altText.isEmpty ? "Image failed to load" : altText)
                        .font(.caption)
                        .foregroundColor(.textSecondary)
                        .italic()
                }
                .padding(8)
                .frame(maxWidth: .infinity, alignment: .center)
                .background(Color.textPrimary.opacity(0.03))
                .clipShape(RoundedRectangle(cornerRadius: 6))
            } else {
                // Placeholder for non-note-image refs or no fetcher
                HStack(spacing: 6) {
                    Image(systemName: "photo")
                        .foregroundColor(.secondaryBlue)
                    Text(altText.isEmpty ? "Image" : altText)
                        .font(.caption)
                        .foregroundColor(.textSecondary)
                        .italic()
                }
                .padding(8)
                .frame(maxWidth: .infinity, alignment: .center)
                .background(Color.textPrimary.opacity(0.03))
                .clipShape(RoundedRectangle(cornerRadius: 6))
            }
        }
        .task {
            await loadImage()
        }
    }

    private func loadImage() async {
        guard let imageId, let fetcher, !isLoading else { return }
        isLoading = true
        defer { isLoading = false }
        if let image = await fetcher(imageId) {
            platformImage = image
        } else {
            didFail = true
        }
    }

    @ViewBuilder
    private func platformImageView(_ image: PlatformImage) -> Image {
        #if os(macOS)
        Image(nsImage: image)
        #else
        Image(uiImage: image)
        #endif
    }
}
