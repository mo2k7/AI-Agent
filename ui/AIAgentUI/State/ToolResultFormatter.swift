//
//  ToolResultFormatter.swift
//  AIAgentUI
//
//  Normalizes raw backend tool JSON into human-readable markdown.
//  The Python backend is the PRIMARY formatter — this Swift layer
//  acts as a DEFENSIVE FALLBACK for any raw JSON that slips through.
//

import Foundation

enum ToolResultFormatter {
    static func normalizeContent(_ content: String) -> String {
        guard let payload = decodeJSONObject(from: content) else {
            return content
        }

        let toolName = (payload["tool"] as? String)?
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased() ?? ""

        // Dispatch to per-tool fallback renderers
        switch toolName {
        case "search_files":
            return renderSearchFiles(payload: payload) ?? content
        case "get_metadata":
            return renderGetMetadata(payload: payload) ?? content
        case "read_text":
            return renderReadText(payload: payload) ?? content
        case "extract_content":
            return renderExtractContent(payload: payload) ?? content
        case "plan_ops":
            return renderPlanOps(payload: payload) ?? content
        case "apply_ops":
            return renderApplyOps(payload: payload) ?? content
        case "open_item":
            return renderOpenItem(payload: payload) ?? content
        case "run_automation":
            return renderRunAutomation(payload: payload) ?? content
        case "generate_image":
            return renderGenerateImage(payload: payload) ?? content
        case "browse_web":
            return renderBrowseWeb(payload: payload) ?? content
        default:
            // Try search_files heuristic for untagged payloads
            if let rendered = renderSearchFiles(payload: payload) {
                return rendered
            }
            return content
        }
    }

    // MARK: - search_files

    private static func renderSearchFiles(payload: [String: Any]) -> String? {
        var output = payload["output"] as? [String: Any]
        if output == nil, let outputText = payload["output"] as? String {
            output = decodeJSONObject(from: outputText)
        }
        if output == nil, payload["query"] != nil || payload["matches"] != nil {
            output = payload
        }

        let toolName = (payload["tool"] as? String)?
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()

        guard toolName == "search_files" || output != nil else {
            return nil
        }
        guard let data = output else {
            return nil
        }

        let query = (data["query"] as? String)?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let rawMatches = data["matches"] as? [Any] ?? []
        let matches = rawMatches.compactMap { $0 as? [String: Any] }

        if matches.isEmpty {
            var message = "No files found."
            if !query.isEmpty {
                message += " Query: \(query)."
            }
            message += " Try a more specific filename, extension, or folder keyword."
            return message
        }

        var lines: [String] = ["Found \(matches.count) matching file(s). Click any link to open it:"]
        var rendered = 0

        for item in matches.prefix(20) {
            let path = (item["path"] as? String)?
                .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            if path.isEmpty {
                continue
            }
            let displayPath = ((item["display_path"] as? String)?
                .trimmingCharacters(in: .whitespacesAndNewlines)).flatMap { $0.isEmpty ? nil : $0 } ?? path
            let name = ((item["name"] as? String)?
                .trimmingCharacters(in: .whitespacesAndNewlines)).flatMap { $0.isEmpty ? nil : $0 } ??
                URL(fileURLWithPath: path).lastPathComponent

            let uri = ((item["uri"] as? String)?
                .trimmingCharacters(in: .whitespacesAndNewlines)).flatMap { $0.isEmpty ? nil : $0 } ??
                URL(fileURLWithPath: path).absoluteString

            let escapedName = name.replacingOccurrences(of: "[", with: "\\[")
                .replacingOccurrences(of: "]", with: "\\]")
            let escapedPath = displayPath.replacingOccurrences(of: "`", with: "\\`")
            lines.append("- [\(escapedName)](\(uri)) (`\(escapedPath)`)")
            rendered += 1
        }

        if rendered == 0 {
            var message = "No files found."
            if !query.isEmpty {
                message += " Query: \(query)."
            }
            message += " Try a more specific filename, extension, or folder keyword."
            return message
        }

        if (data["truncated"] as? Bool) == true {
            let reason = (data["truncated_reason"] as? String)?
                .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            if reason.isEmpty {
                lines.append("Search scan reached the limit; refine query for deeper results.")
            } else {
                lines.append("Search scan truncated: \(reason). Refine query for deeper results.")
            }
        }
        if let scannedEntries = data["scanned_entries"] as? Int {
            lines.append("Scanned entries: \(scannedEntries).")
        }
        return lines.joined(separator: "\n")
    }

    // MARK: - get_metadata

    private static func renderGetMetadata(payload: [String: Any]) -> String? {
        let output = extractOutput(from: payload)
        guard let items = output["items"] as? [[String: Any]], !items.isEmpty else {
            return nil
        }

        var lines: [String] = ["**File Metadata** for \(items.count) path(s):\n"]
        for item in items {
            let path = (item["path"] as? String) ?? "—"
            let exists = (item["exists"] as? Bool) == true
            let isFile = (item["is_file"] as? Bool) == true
            let isDir = (item["is_dir"] as? Bool) == true
            let ftype = isFile ? "File" : (isDir ? "Directory" : "—")
            let size = humanSize(item["size_bytes"])
            let created = tsToStr(item["created_at"])
            let modified = tsToStr(item["modified_at"])
            let perms = (item["permissions_octal"] as? String) ?? "—"
            let error = (item["error"] as? String) ?? ""

            lines.append("| Property | Value |")
            lines.append("|----------|-------|")
            lines.append("| Path | \(path) |")
            lines.append("| Exists | \(exists ? "Yes" : "No") |")
            if exists {
                lines.append("| Type | \(ftype) |")
                lines.append("| Size | \(size) |")
                lines.append("| Created | \(created) |")
                lines.append("| Modified | \(modified) |")
                lines.append("| Permissions | \(perms) |")
            }
            if !error.isEmpty {
                lines.append("| Error | \(error) |")
            }
            lines.append("")
        }
        return lines.joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
    }

    // MARK: - read_text

    private static func renderReadText(payload: [String: Any]) -> String? {
        let output = extractOutput(from: payload)
        let path = (output["path"] as? String) ?? "unknown"
        let content = (output["content"] as? String) ?? ""
        let byteRange = output["byte_range"] as? [Int]
        var rangeStr = ""
        if let br = byteRange, br.count == 2 {
            rangeStr = " (bytes \(br[0])–\(br[1]))"
        }
        return "**File Content**: `\(path)`\(rangeStr)\n\n```\n\(content)\n```"
    }

    // MARK: - extract_content

    private static func renderExtractContent(payload: [String: Any]) -> String? {
        let output = extractOutput(from: payload)
        let mode = (output["mode"] as? String) ?? "text"
        let path = (output["path"] as? String) ?? "unknown"
        let content = (output["content"] as? String) ?? ""
        let lineCount = output["line_count"] as? Int
        let warning = (output["warning"] as? String) ?? ""

        let ext = URL(fileURLWithPath: path).pathExtension
        var header = "**Extracted Content** (mode: \(mode)): `\(path)`"
        if let lc = lineCount {
            header += "\nLines: \(lc)"
        }
        if !warning.isEmpty {
            header += "\n⚠️ \(warning)"
        }
        return "\(header)\n\n```\(ext)\n\(content)\n```"
    }

    // MARK: - plan_ops

    private static func renderPlanOps(payload: [String: Any]) -> String? {
        let output = extractOutput(from: payload)
        let planId = (output["plan_id"] as? String) ?? (payload["plan_id"] as? String) ?? ""
        guard let ops = output["ops"] as? [[String: Any]] else { return nil }
        let issues = (output["issues"] as? [String]) ?? []

        var lines: [String] = ["**Operation Plan** `\(planId)`", ""]
        lines.append("| # | Op | Source | Destination | Valid |")
        lines.append("|---|-----|--------|-------------|-------|")
        for (idx, op) in ops.enumerated() {
            let opKind = (op["op"] as? String) ?? "—"
            let src = (op["src"] as? String) ?? "—"
            let dest = (op["dest"] as? String) ?? "—"
            let valid = (op["valid"] as? Bool) == true ? "✅" : "❌"
            lines.append("| \(idx + 1) | \(opKind) | \(src) | \(dest) | \(valid) |")
        }
        lines.append("")
        if issues.isEmpty {
            lines.append("Issues: none")
        } else {
            lines.append("Issues:")
            for issue in issues {
                lines.append("- \(issue)")
            }
        }
        return lines.joined(separator: "\n")
    }

    // MARK: - apply_ops

    private static func renderApplyOps(payload: [String: Any]) -> String? {
        let planId = (payload["plan_id"] as? String) ?? ""
        let applied = (payload["applied"] as? Int) ?? 0
        let failed = (payload["failed"] as? Int) ?? 0
        guard let results = payload["results"] as? [[String: Any]] else { return nil }

        var lines: [String] = [
            "**Operations Applied** — plan `\(planId)`",
            "Applied: \(applied) | Failed: \(failed)",
            ""
        ]
        for result in results {
            let idx = (result["index"] as? Int) ?? 0
            let opKind = (result["op"] as? String) ?? "—"
            let ok = (result["ok"] as? Bool) == true
            let src = (result["src"] as? String) ?? "—"
            let dest = result["dest"] as? String
            let error = (result["error"] as? String) ?? ""
            let deleteMode = (result["delete_mode"] as? String) ?? ""
            let icon = ok ? "✅" : "❌"

            if ok, let d = dest {
                lines.append("\(idx + 1). \(icon) **\(opKind)** `\(src)` → `\(d)`")
            } else if ok && opKind == "delete" {
                let suffix = deleteMode.contains("trash") ? " (moved to Trash)" : ""
                lines.append("\(idx + 1). \(icon) **\(opKind)** `\(src)`\(suffix)")
            } else if ok {
                lines.append("\(idx + 1). \(icon) **\(opKind)** `\(src)`")
            } else {
                lines.append("\(idx + 1). \(icon) **\(opKind)** `\(src)` — \(error)")
            }
        }
        return lines.joined(separator: "\n")
    }

    // MARK: - open_item

    private static func renderOpenItem(payload: [String: Any]) -> String? {
        let output = extractOutput(from: payload)
        let path = (output["path"] as? String) ?? "unknown"
        let ok = (payload["ok"] as? Bool) ?? (output["ok"] as? Bool) ?? false
        let icon = ok ? "✅" : "❌"
        return "\(icon) Opened `\(path)`"
    }

    // MARK: - run_automation

    private static func renderRunAutomation(payload: [String: Any]) -> String? {
        let output = extractOutput(from: payload)
        let name = (output["name"] as? String) ?? (payload["name"] as? String) ?? "unknown"
        let exitCode = output["exit_code"] ?? payload["exit_code"]
        let ok = (payload["ok"] as? Bool) ?? (output["ok"] as? Bool) ?? false
        let timedOut = (output["timed_out"] as? Bool) ?? (payload["timed_out"] as? Bool) ?? false
        let stdout = ((output["stdout"] as? String) ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        let stderr = ((output["stderr"] as? String) ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        let error = ((output["error"] as? String) ?? "").trimmingCharacters(in: .whitespacesAndNewlines)

        let exitDisplay: String
        if let ec = exitCode as? Int {
            exitDisplay = "\(ec)"
        } else {
            exitDisplay = "—"
        }
        let icon = timedOut ? "⏱️" : (ok ? "✅" : "❌")

        var lines: [String] = ["**Automation**: `\(name)` — Exit code: \(exitDisplay) \(icon)"]
        if !error.isEmpty {
            lines.append("\n⚠️ \(error)")
        }
        if !stdout.isEmpty {
            lines.append(contentsOf: ["", "**stdout**:", "```", stdout, "```"])
        }
        if !stderr.isEmpty {
            lines.append(contentsOf: ["", "**stderr**:", "```", stderr, "```"])
        }
        return lines.joined(separator: "\n")
    }

    // MARK: - generate_image

    private static func renderGenerateImage(payload: [String: Any]) -> String? {
        let output = extractOutput(from: payload)
        guard output["images"] != nil || output["model"] != nil || output["summary"] != nil else {
            return nil
        }

        let model = ((output["model"] as? String)?
            .trimmingCharacters(in: .whitespacesAndNewlines)).flatMap { $0.isEmpty ? nil : $0 } ?? "unknown"
        let summary = ((output["summary"] as? String)?
            .trimmingCharacters(in: .whitespacesAndNewlines)).flatMap { $0.isEmpty ? nil : $0 }
        let images = output["images"] as? [[String: Any]] ?? []

        var lines: [String] = ["**Image Generation** — model `\(model)`"]
        if let summary {
            lines.append(summary)
        }

        if images.isEmpty {
            lines.append("No saved images were returned.")
            return lines.joined(separator: "\n")
        }

        lines.append("")
        lines.append("Generated \(images.count) image(s):")

        for (index, image) in images.prefix(12).enumerated() {
            let path = ((image["path"] as? String)?
                .trimmingCharacters(in: .whitespacesAndNewlines)).flatMap { $0.isEmpty ? nil : $0 } ?? "unknown-path"
            let mime = ((image["mime_type"] as? String)?
                .trimmingCharacters(in: .whitespacesAndNewlines)).flatMap { $0.isEmpty ? nil : $0 } ?? "unknown"
            let width = image["width"] as? Int ?? 0
            let height = image["height"] as? Int ?? 0
            let dims = (width > 0 && height > 0) ? "\(width)x\(height)" : "unknown size"
            let embedded = (image["note_embedded"] as? Bool) == true
            let embedText = embedded ? "embedded in note" : "saved to file"

            let url = URL(fileURLWithPath: path)
            let name = url.lastPathComponent.isEmpty ? path : url.lastPathComponent
            let link = "[\(name)](\(url.absoluteString))"
            lines.append("- \(index + 1). \(link) — \(dims), \(mime), \(embedText)")
        }
        if images.count > 12 {
            lines.append("- ... \(images.count - 12) additional image(s) omitted")
        }
        return lines.joined(separator: "\n")
    }

    // MARK: - browse_web

    private static func renderBrowseWeb(payload: [String: Any]) -> String? {
        let output = extractOutput(from: payload)
        guard output["final_url"] != nil || output["url"] != nil || output["content"] != nil else {
            return nil
        }

        let finalURL = ((output["final_url"] as? String)?
            .trimmingCharacters(in: .whitespacesAndNewlines)).flatMap { $0.isEmpty ? nil : $0 }
            ?? ((output["url"] as? String)?
                .trimmingCharacters(in: .whitespacesAndNewlines)).flatMap { $0.isEmpty ? nil : $0 }
        let title = ((output["title"] as? String)?
            .trimmingCharacters(in: .whitespacesAndNewlines)).flatMap { $0.isEmpty ? nil : $0 }
        let profile = ((output["effective_browse_profile"] as? String)?
            .trimmingCharacters(in: .whitespacesAndNewlines)).flatMap { $0.isEmpty ? nil : $0 }
        let content = ((output["content"] as? String)?
            .trimmingCharacters(in: .whitespacesAndNewlines)) ?? ""
        let contentType = ((output["content_type"] as? String)?
            .trimmingCharacters(in: .whitespacesAndNewlines)).flatMap { $0.isEmpty ? nil : $0 } ?? "unknown"
        let warningLine = compactWarningLine(from: output["policy_warnings"], limit: 1)

        var lines: [String] = ["**Web Browse**"]
        if let finalURL {
            let label = (title ?? finalURL).replacingOccurrences(of: "[", with: "\\[")
                .replacingOccurrences(of: "]", with: "\\]")
            lines.append("Source: [\(label)](\(finalURL))")
        } else {
            lines.append("Source: \(title ?? "unknown")")
        }
        if let profile, profile.lowercased() != "strict" {
            lines.append("Browse profile: `\(profile.lowercased())`")
            if !warningLine.isEmpty {
                lines.append("Policy notice: `\(profile.lowercased())` browsing allowed this result with policy warnings.")
            } else {
                lines.append("Policy notice: relaxed `\(profile.lowercased())` browsing rules were active for this fetch.")
            }
        }
        if !warningLine.isEmpty {
            lines.append("")
            lines.append("Caution: \(warningLine)")
        }
        if content.isEmpty {
            lines.append("")
            lines.append("No extractable text was returned (`\(contentType)`).")
        } else {
            lines.append("")
            lines.append(content)
        }
        return lines.joined(separator: "\n")
    }

    // MARK: - Helpers

    private static func extractOutput(from payload: [String: Any]) -> [String: Any] {
        if let output = payload["output"] as? [String: Any] {
            return output
        }
        if let outputText = payload["output"] as? String,
           let parsed = decodeJSONObject(from: outputText) {
            return parsed
        }
        return payload
    }

    private static func decodeJSONObject(from text: String) -> [String: Any]? {
        guard let data = text.data(using: .utf8) else {
            return nil
        }
        guard let parsed = try? JSONSerialization.jsonObject(with: data) else {
            return nil
        }
        return parsed as? [String: Any]
    }

    private static func compactWarningLine(from value: Any?, limit: Int) -> String {
        guard let warnings = value as? [Any] else { return "" }
        var normalized: [String] = []
        for warning in warnings {
            guard let text = warning as? String else { continue }
            let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
            if !trimmed.isEmpty {
                normalized.append(trimmed)
            }
        }
        guard !normalized.isEmpty else { return "" }
        let cappedLimit = max(1, limit)
        let visible = Array(normalized.prefix(cappedLimit))
        var summary = visible.joined(separator: " | ")
        if summary.count > 180 {
            summary = String(summary.prefix(177)).trimmingCharacters(in: .whitespacesAndNewlines) + "..."
        }
        let remaining = normalized.count - visible.count
        if remaining > 0 {
            summary += " (+\(remaining) more)"
        }
        return summary
    }

    private static func humanSize(_ value: Any?) -> String {
        guard let bytes = value as? Int else { return "—" }
        if bytes < 1024 { return "\(bytes) B" }
        let units = ["KB", "MB", "GB", "TB"]
        var size = Double(bytes)
        for unit in units {
            size /= 1024.0
            if size < 1024.0 {
                return String(format: "%.1f %@", size, unit)
            }
        }
        return String(format: "%.1f PB", size / 1024.0)
    }

    private static func tsToStr(_ value: Any?) -> String {
        guard let ts = value as? Double else { return "—" }
        let date = Date(timeIntervalSince1970: ts)
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd HH:mm"
        return formatter.string(from: date)
    }
}
