//
//  ToolDeclarations.swift
//  AIAgentUI
//
//  Tool function schemas for Gemini function calling.
//  These mirror the JSON schemas in /schemas/*.json and are used
//  by IOSGeminiService to register available tools with the API.
//  On macOS, tools are registered by the Python backend — these are not used.
//

import Foundation

/// Registry of all tool declarations available for Gemini function calling.
enum ToolRegistry {

    /// Returns the full set of tool declarations for iOS.
    static func allIOSTools() -> [ToolDeclaration] {
        [
            searchFiles,
            openItem,
            readScreen,
            readDocument,
            browseWeb,
            manageNotes,
            generateImage,
            createDirectory,
            grantFolderAccess,
        ]
    }

    // MARK: - Tool Definitions

    static let searchFiles = ToolDeclaration(
        name: "search_files",
        description: "Find files based on metadata or content",
        parameters: ToolParameters(
            properties: [
                "query": ToolProperty(type: "string", description: "Search query — use specific filenames or content keywords, NOT the full natural-language prompt"),
                "extensions": ToolProperty(type: "array", description: "File extensions to filter by (without leading dot), e.g. [\"pdf\", \"docx\", \"txt\"]", items: ToolPropertyItems(type: "string")),
                "folder_hint": ToolProperty(type: "string", description: "Preferred folder name to search in first, e.g. \"downloads\", \"documents\""),
                "path_filter": ToolProperty(type: "string", description: "Optional path substring filter (case-insensitive)"),
                "mode": ToolProperty(type: "string", description: "Search strategy: auto, fast, or deep", enumValues: ["auto", "fast", "deep"]),
                "limit": ToolProperty(type: "integer", description: "Maximum number of results (1–100, default 10)"),
            ],
            required: ["query"]
        )
    )

    static let openItem = ToolDeclaration(
        name: "open_item",
        description: "Open a file, URL, or item using the system default handler or share sheet",
        parameters: ToolParameters(
            properties: [
                "path": ToolProperty(type: "string", description: "Path or URL to open"),
                "application": ToolProperty(type: "string", description: "Optional application name to open with"),
            ],
            required: ["path"]
        )
    )

    static let readScreen = ToolDeclaration(
        name: "read_screen",
        description: "Capture and OCR the current screen or app view. Returns text content from what is visible on screen. Read-only — no modifications.",
        parameters: ToolParameters(
            properties: [
                "purpose": ToolProperty(type: "string", description: "Optional description of what to look for on screen"),
            ],
            required: []
        )
    )

    static let readDocument = ToolDeclaration(
        name: "read_document",
        description: "Read text, code, PDF content, or file metadata from a local file",
        parameters: ToolParameters(
            properties: [
                "path": ToolProperty(type: "string", description: "Absolute path to the target file"),
                "mode": ToolProperty(type: "string", description: "Observation mode: text, code, pdf, or metadata", enumValues: ["text", "code", "pdf", "metadata"]),
            ],
            required: ["path"]
        )
    )

    static let browseWeb = ToolDeclaration(
        name: "browse_web",
        description: "Browse and extract content from web pages. Supports URL fetching and web search.",
        parameters: ToolParameters(
            properties: [
                "url": ToolProperty(type: "string", description: "URL to fetch and extract content from"),
                "search_query": ToolProperty(type: "string", description: "Run a web search query and fetch result pages"),
                "timeout_seconds": ToolProperty(type: "integer", description: "Per-request timeout in seconds (3–60, default 15)"),
            ],
            required: []
        )
    )

    static let manageNotes = ToolDeclaration(
        name: "manage_notes",
        description: "Create, update, delete, list, and manage session notes",
        parameters: ToolParameters(
            properties: [
                "action": ToolProperty(type: "string", description: "The note operation to perform", enumValues: ["create", "update", "delete", "list", "get"]),
                "note_id": ToolProperty(type: "string", description: "Note ID (required for update, delete, get)"),
                "content": ToolProperty(type: "string", description: "Note content in markdown (required for create, optional for update)"),
                "title": ToolProperty(type: "string", description: "Optional note title"),
                "tags": ToolProperty(type: "array", description: "Optional tags for categorization", items: ToolPropertyItems(type: "string")),
            ],
            required: ["action"]
        )
    )

    static let generateImage = ToolDeclaration(
        name: "generate_image",
        description: "Generate images from text prompts using AI image generation",
        parameters: ToolParameters(
            properties: [
                "prompt": ToolProperty(type: "string", description: "Detailed text description of the image to generate"),
                "aspect_ratio": ToolProperty(type: "string", description: "Aspect ratio: 1:1, 16:9, 9:16, 4:3, 3:4", enumValues: ["1:1", "16:9", "9:16", "4:3", "3:4"]),
                "note_id": ToolProperty(type: "string", description: "Optional note ID to embed the image in"),
                "alt_text": ToolProperty(type: "string", description: "Accessibility text describing the image"),
            ],
            required: ["prompt"]
        )
    )

    static let createDirectory = ToolDeclaration(
        name: "create_directory",
        description: "Create a new directory at the specified path, including intermediate directories",
        parameters: ToolParameters(
            properties: [
                "path": ToolProperty(type: "string", description: "Absolute path for the new directory"),
            ],
            required: ["path"]
        )
    )

    static let grantFolderAccess = ToolDeclaration(
        name: "grant_folder_access",
        description: "Grant the app access to search files in a folder on the user's iOS device. iOS apps cannot search arbitrary files — the user must explicitly grant access to specific folders. To give the app the widest scope, ask the user to select the root 'iCloud Drive' or 'On My iPhone' folder. Once granted, search_files will automatically include them. You MUST provide a clear 'reason' explaining what you are trying to search for.",
        parameters: ToolParameters(
            properties: [
                "action": ToolProperty(type: "string", description: "The action to perform: add (open folder picker), list (show granted folders), clear (remove all grants)", enumValues: ["add", "list", "clear"]),
                "reason": ToolProperty(type: "string", description: "A short, user-facing explanation of why you need access to a folder. This will be shown to the user in a confirmation modal.")
            ],
            required: ["action", "reason"]
        )
    )
}
