//
//  Note.swift
//  AIAgentUI
//
//  Created for Personal macOS AI Agent
//  Status: Active - Note model for session notes
//

import Foundation

/// Represents a note in the session's notes panel.
struct Note: Identifiable, Equatable, Sendable {
    let id: String          // note_id from backend
    var title: String
    var content: String
    var workspaceKind: String
    var isDefaultTab: Bool
    var tabOrder: Int
    var isPinned: Bool
    let source: String      // "user" or "agent"
    let createdAt: Date
    var updatedAt: Date

    /// Whether the note was created by the AI agent.
    var isAgentCreated: Bool { source == "agent" }
    var isSessionPad: Bool { workspaceKind == "session_pad" || isDefaultTab }
    var displayTitle: String {
        let trimmed = title.trimmingCharacters(in: .whitespacesAndNewlines)
        if !trimmed.isEmpty { return trimmed }
        if isSessionPad { return "Session Notes" }
        return "Untitled Tab"
    }

    /// Extracts the note type from an embedded `<!-- note-type:xxx -->` HTML comment.
    var noteType: String? {
        guard let range = content.range(of: "<!-- note-type:"),
              let endRange = content.range(of: " -->", range: range.upperBound..<content.endIndex)
        else { return nil }
        let typeStr = String(content[range.upperBound..<endRange.lowerBound])
        return typeStr.isEmpty ? nil : typeStr
    }

    /// Extracts tags from an embedded `<!-- tags:a,b,c -->` HTML comment.
    var tags: [String] {
        guard let range = content.range(of: "<!-- tags:"),
              let endRange = content.range(of: " -->", range: range.upperBound..<content.endIndex)
        else { return [] }
        let raw = String(content[range.upperBound..<endRange.lowerBound])
        return raw.components(separatedBy: ",")
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
    }

    /// The content with metadata HTML comments (note-type, tags) stripped out.
    var displayContent: String {
        var result = content
        // Strip note-type comment
        result = Self.stripHTMLComment(result, prefix: "<!-- note-type:")
        // Strip tags comment
        result = Self.stripHTMLComment(result, prefix: "<!-- tags:")
        return result.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    /// Strips an HTML comment from content by prefix (e.g. "<!-- note-type:").
    static func stripHTMLComment(_ text: String, prefix: String) -> String {
        guard let startRange = text.range(of: prefix) else { return text }
        // Try with trailing newline first
        if let endRange = text.range(of: " -->\n", range: startRange.upperBound..<text.endIndex) {
            var result = text
            result.removeSubrange(startRange.lowerBound..<endRange.upperBound)
            return result
        }
        // Without trailing newline
        if let endRange = text.range(of: " -->", range: startRange.upperBound..<text.endIndex) {
            var result = text
            result.removeSubrange(startRange.lowerBound..<endRange.upperBound)
            return result
        }
        return text
    }
}

// MARK: - IPC Decodable

/// Decodable representation of a note from the backend JSON-RPC response.
struct IPCNote: Decodable {
    let noteId: String
    let title: String
    let content: String
    let workspaceKind: String
    let isDefaultTab: Bool
    let tabOrder: Int
    let isPinned: Bool
    let source: String
    let createdAt: Double
    let updatedAt: Double

    enum CodingKeys: String, CodingKey {
        case noteId = "note_id"
        case title
        case content
        case workspaceKind = "workspace_kind"
        case isDefaultTab = "is_default_tab"
        case tabOrder = "tab_order"
        case isPinned = "is_pinned"
        case source
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }

    /// Converts the IPC representation to the app-level `Note` model.
    func toNote() -> Note {
        Note(
            id: noteId,
            title: title,
            content: content,
            workspaceKind: workspaceKind,
            isDefaultTab: isDefaultTab,
            tabOrder: tabOrder,
            isPinned: isPinned,
            source: source,
            createdAt: Date(timeIntervalSince1970: createdAt),
            updatedAt: Date(timeIntervalSince1970: updatedAt)
        )
    }
}

/// Decodable representation of a note image from the backend.
struct IPCNoteImage: Decodable {
    let imageId: String
    let noteId: String
    let imageData: String   // base64-encoded
    let mimeType: String
    let width: Int
    let height: Int
    let altText: String

    enum CodingKeys: String, CodingKey {
        case imageId = "image_id"
        case noteId = "note_id"
        case imageData = "image_data"
        case mimeType = "mime_type"
        case width
        case height
        case altText = "alt_text"
    }
}

/// Decodable representation of a note version from the backend.
struct IPCNoteVersion: Decodable, Identifiable {
    let versionId: String
    let noteId: String
    let content: String
    let createdAt: Double

    var id: String { versionId }

    /// Human-readable timestamp.
    var date: Date { Date(timeIntervalSince1970: createdAt) }

    enum CodingKeys: String, CodingKey {
        case versionId = "version_id"
        case noteId = "note_id"
        case content
        case createdAt = "created_at"
    }
}

/// Decodable result for delete operations.
struct IPCDeleteNoteResult: Decodable {
    let deleted: Bool
    let noteId: String

    enum CodingKeys: String, CodingKey {
        case deleted
        case noteId = "note_id"
    }
}
