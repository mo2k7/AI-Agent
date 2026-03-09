//
//  IOSToolExecutor.swift
//  AIAgentUI
//
//  Native iOS tool execution for Gemini function calling.
//  Each tool mirrors the Python backend's behavior within iOS sandbox constraints.
//

#if os(iOS)

import Foundation
import UIKit
import Photos
import Vision
import PDFKit

/// Executes tools natively on iOS, returning result dictionaries
/// suitable for feeding back into the Gemini function-calling loop.
@MainActor
final class IOSToolExecutor {

    static let shared = IOSToolExecutor()

    private init() {}

    /// Sendable wrapper for `[String: Any]` to cross task group boundaries safely.
    private struct SendableDictWrapper: @unchecked Sendable {
        let value: [String: Any]
    }

    // MARK: - Dispatch

    /// Execute a tool by name with the given arguments.
    /// Returns a result dictionary to feed back to Gemini as a function response.
    func execute(name: String, arguments: [String: Any]) async -> [String: Any] {
        var result: [String: Any]
        do {
            switch name {
            case "search_files":
                result = try await executeSearchFiles(arguments)
            case "open_item":
                result = try await executeOpenItem(arguments)
            case "read_screen":
                result = executeReadScreen(arguments)
            case "read_document":
                result = try executeReadDocument(arguments)
            case "browse_web":
                result = try await executeBrowseWeb(arguments)
            case "manage_notes":
                result = try executeManageNotes(arguments)
            case "generate_image":
                result = try await executeGenerateImage(arguments)
            case "create_directory":
                result = try executeCreateDirectory(arguments)
            case "grant_folder_access":
                result = await executeGrantFolderAccess(arguments)
            default:
                result = ["error": "Unknown tool: \(name)", "status": "failed"]
            }
        } catch {
            result = ["error": error.localizedDescription, "status": "failed"]
        }

        // Tag every result so the AI knows this ran on the user's device, NOT the Mac
        result["executed_on"] = "iPhone"
        result["execution_device"] = UIDevice.current.name
        result["execution_platform"] = "iOS"
        return result
    }

    // MARK: - search_files

    // ── Stopwords (mirrors Python _SEARCH_STOPWORDS) ──
    private static let searchStopwords: Set<String> = [
        "a", "an", "the", "is", "it", "in", "on", "to", "for", "of",
        "and", "or", "my", "me", "i", "find", "search", "look", "get",
        "show", "list", "where", "all", "any", "some", "file", "files",
        "folder", "called", "named", "with", "from", "that", "this",
    ]

    // ── Semantic extension hints (mirrors Python _SEMANTIC_EXTENSION_HINTS) ──
    private static let semanticExtensionHints: [String: Set<String>] = [
        "photo": ["jpg", "jpeg", "heic", "heif", "png", "gif", "webp", "tiff"],
        "photos": ["jpg", "jpeg", "heic", "heif", "png", "gif", "webp", "tiff"],
        "picture": ["jpg", "jpeg", "heic", "heif", "png", "gif", "webp"],
        "image": ["jpg", "jpeg", "heic", "heif", "png", "gif", "webp"],
        "screenshot": ["png", "jpg", "heic"],
        "video": ["mp4", "mov", "m4v", "avi", "mkv", "webm"],
        "movie": ["mp4", "mov", "m4v", "avi", "mkv"],
        "music": ["mp3", "m4a", "aac", "flac", "wav", "aiff"],
        "audio": ["mp3", "m4a", "aac", "flac", "wav", "ogg"],
        "document": ["pdf", "docx", "doc", "txt", "rtf", "pages", "odt"],
        "spreadsheet": ["xlsx", "xls", "csv", "numbers", "ods"],
        "presentation": ["pptx", "ppt", "key", "odp"],
        "code": ["swift", "py", "js", "ts", "java", "cpp", "c", "h", "rb", "go", "rs"],
        "script": ["sh", "bash", "zsh", "py", "rb", "pl"],
        "archive": ["zip", "tar", "gz", "rar", "7z", "dmg"],
        "text": ["txt", "md", "rtf", "log", "csv"],
        "pdf": ["pdf"],
        "note": ["md", "txt", "rtf"],
        "config": ["json", "yaml", "yml", "toml", "xml", "plist", "ini"],
        "database": ["db", "sqlite", "sqlite3", "realm"],
    ]

    private static let directExtensionTokens: Set<String> = [
        "pdf", "txt", "md", "csv", "json", "xml", "html", "css", "js", "ts",
        "py", "swift", "java", "cpp", "c", "h", "rb", "go", "rs", "sh",
        "jpg", "jpeg", "png", "gif", "heic", "webp", "svg",
        "mp3", "mp4", "mov", "m4a", "wav", "avi", "mkv", "zip", "tar", "gz",
        "docx", "xlsx", "pptx", "pages", "numbers", "key",
    ]

    private static let folderHintMap: [String: String] = [
        "download": "Downloads", "downloads": "Downloads",
        "document": "Documents", "documents": "Documents",
        "desktop": "Desktop",
        "picture": "Pictures", "pictures": "Pictures",
        "photo": "Photos", "photos": "Photos",
        "music": "Music",
        "video": "Movies", "videos": "Movies", "movie": "Movies",
        "project": "Projects", "projects": "Projects",
        "code": "Developer", "dev": "Developer",
    ]

    private func executeSearchFiles(_ args: [String: Any]) async throws -> [String: Any] {
        let query = args["query"] as? String ?? ""
        guard !query.isEmpty else {
            return ["error": "query is required", "status": "failed"]
        }

        let explicitExtensions = args["extensions"] as? [String]
        let limit = min(args["limit"] as? Int ?? 20, 100)
        let folderHint = args["folder_hint"] as? String
        let searchContent = args["search_content"] as? Bool ?? false
        let deepMode = args["deep"] as? Bool ?? false

        let queryLower = query.lowercased()
        let tokens = tokenizeQuery(queryLower)
        let extensionHints = deriveExtensionHints(tokens: tokens, explicit: explicitExtensions)
        let folderHints = deriveFolderHints(tokens: tokens, explicit: folderHint)
        let expandedTokens = expandTokenForms(tokens)

        let photoExtensions: Set<String> = ["jpg", "jpeg", "heic", "heif", "png", "gif", "webp",
                                             "mp4", "mov", "m4v", "avi"]
        let isPhotoSearch = !extensionHints.intersection(photoExtensions).isEmpty
            || ["photo", "photos", "picture", "image", "video", "selfie", "screenshot"]
                .contains(where: { queryLower.contains($0) })

        // ── Gather raw candidates from all sources ──
        typealias Candidate = (path: String, name: String, url: URL?, meta: [String: Any], source: String)
        var candidates: [Candidate] = []
        var searchSources: [String] = []

        let localResults = gatherLocalCandidates(
            extensionHints: extensionHints,
            explicitExtensions: explicitExtensions,
            deepMode: deepMode, scanLimit: deepMode ? 5000 : 2000
        )
        if !localResults.isEmpty { candidates += localResults; searchSources.append("local_filesystem") }

        if isPhotoSearch {
            let photoResults = await gatherPhotoCandidates(query: queryLower, limit: limit * 2)
            if !photoResults.isEmpty { candidates += photoResults; searchSources.append("photos_library") }
        }

        let spotlightResults = await gatherSpotlightCandidates(query: query, extensions: explicitExtensions, limit: limit * 3)
        if !spotlightResults.isEmpty { candidates += spotlightResults; searchSources.append("spotlight") }

        // ── Score every candidate ──
        var scored: [(score: Int, entry: [String: Any])] = []

        for c in candidates {
            let (score, signals) = scoreCandidate(
                queryLower: queryLower, tokens: tokens,
                expandedTokens: expandedTokens, extensionHints: extensionHints,
                folderHints: folderHints, name: c.name, path: c.path, source: c.source
            )

            var contentScore = 0
            var contentPreview: String?
            if searchContent, let url = c.url, isTextFile(url: url),
               let data = try? Data(contentsOf: url, options: .mappedIfSafe),
               data.count < 2_000_000,
               let text = String(data: data, encoding: .utf8) {
                let tl = text.lowercased()
                for token in tokens where tl.contains(token) {
                    contentScore += 25
                    if contentPreview == nil, let r = tl.range(of: token) {
                        let pos = text.distance(from: text.startIndex, to: r.lowerBound)
                        let s = text.index(text.startIndex, offsetBy: max(0, pos - 60))
                        let e = text.index(text.startIndex, offsetBy: min(text.count, pos + token.count + 60))
                        contentPreview = "…" + text[s..<e].replacingOccurrences(of: "\n", with: " ") + "…"
                    }
                }
            }

            let total = score + contentScore
            guard total > 0 else { continue }

            var entry = c.meta
            entry["relevance_score"] = total
            entry["source"] = c.source
            let topSignals = signals.sorted { $0.value > $1.value }.prefix(3)
                .map { "\($0.key):\(Int($0.value))" }.joined(separator: ", ")
            entry["match_reason"] = topSignals
            if let p = contentPreview { entry["content_preview"] = p }

            scored.append((score: total, entry: entry))
        }

        scored.sort { $0.score > $1.score }

        var seen = Set<String>()
        var finalResults: [[String: Any]] = []
        for item in scored {
            let key = item.entry["path"] as? String ?? item.entry["name"] as? String ?? UUID().uuidString
            guard !seen.contains(key) else { continue }
            seen.insert(key)
            finalResults.append(item.entry)
            if finalResults.count >= limit { break }
        }

        var resultDict: [String: Any] = [
            "status": "success",
            "results": finalResults,
            "count": finalResults.count,
            "search_sources": searchSources,
            "search_method": "ios_ranked_multi_source",
            "tokens_used": tokens,
            "extension_hints_derived": Array(extensionHints).sorted(),
            "candidates_scanned": candidates.count,
        ]

        // When nothing found, provide diagnostic info so the AI can guide the user
        if finalResults.isEmpty {
            let bookmarkCount = BookmarkedFolderManager.shared.count
            var diagnostics: [String: Any] = [
                "reason": "no_matching_files_found",
                "candidates_scanned": candidates.count,
                "sources_checked": searchSources.isEmpty ? ["local_sandbox", "spotlight_icloud"] : searchSources,
                "bookmarked_folders": bookmarkCount,
            ]
            if bookmarkCount == 0 {
                diagnostics["suggestion"] = "CRITICAL: iOS apps cannot see the user's files due to sandboxing. You MUST NOW call the `grant_folder_access` tool so the user can grant permission to search their folders. Do not give the user instructions on how to do this manually; use the tool."
                diagnostics["action_needed"] = "grant_folder_access"
            } else {
                diagnostics["suggestion"] = "No files matched the query in \(bookmarkCount) granted folder(s). Try a different query or grant access to more folders with grant_folder_access."
            }
            resultDict["diagnostics"] = diagnostics
        }

        return resultDict
    }

    // ── Tokenization (mirrors Python _tokenize_search_query) ──

    private func tokenizeQuery(_ q: String) -> [String] {
        let regex = try? NSRegularExpression(pattern: "[a-z0-9._+\\-]+")
        let matches = regex?.matches(in: q, range: NSRange(q.startIndex..., in: q)) ?? []
        var tokens: [String] = []; var seen = Set<String>()
        for m in matches {
            guard let r = Range(m.range, in: q) else { continue }
            let t = String(q[r]).trimmingCharacters(in: CharacterSet(charactersIn: "._-"))
            guard !t.isEmpty, !Self.searchStopwords.contains(t) else { continue }
            guard t.count > 1 || Self.directExtensionTokens.contains(t) else { continue }
            guard !seen.contains(t) else { continue }
            seen.insert(t); tokens.append(t)
        }
        return tokens
    }

    private func deriveExtensionHints(tokens: [String], explicit: [String]?) -> Set<String> {
        var h = Set<String>()
        if let e = explicit { h.formUnion(e.map { $0.lowercased().trimmingCharacters(in: CharacterSet(charactersIn: ".")) }) }
        for t in tokens {
            let n = t.lowercased().trimmingCharacters(in: CharacterSet(charactersIn: "."))
            if Self.directExtensionTokens.contains(n) { h.insert(n) }
            if let s = Self.semanticExtensionHints[n] { h.formUnion(s) }
        }
        return h
    }

    private func deriveFolderHints(tokens: [String], explicit: String?) -> Set<String> {
        var h = Set<String>()
        if let e = explicit, !e.isEmpty { h.insert(e) }
        for t in tokens { if let m = Self.folderHintMap[t] { h.insert(m) } }
        return h
    }

    private func expandTokenForms(_ tokens: [String]) -> Set<String> {
        var ex = Set<String>(tokens)
        for t in tokens {
            if t.hasSuffix("ies") && t.count > 4 { ex.insert(String(t.dropLast(3)) + "y") }
            else if t.hasSuffix("es") && t.count > 3 { ex.insert(String(t.dropLast(2))) }
            else if t.hasSuffix("s") && t.count > 3 { ex.insert(String(t.dropLast(1))) }
            if !t.hasSuffix("s") && t.count > 2 { ex.insert(t + "s") }
        }
        return ex
    }

    // ── Relevance scoring (mirrors Python _score_path_with_signals) ──

    private func scoreCandidate(
        queryLower: String, tokens: [String], expandedTokens: Set<String>,
        extensionHints: Set<String>, folderHints: Set<String>,
        name: String, path: String, source: String
    ) -> (Int, [String: Double]) {
        let nl = name.lowercased()
        let sl = (name as NSString).deletingPathExtension.lowercased()
        let pl = path.lowercased()
        let ext = (name as NSString).pathExtension.lowercased()

        var score = 0; var sig: [String: Double] = [:]
        var matched = 0

        // Exact filename match (180)
        if !queryLower.isEmpty && nl.contains(queryLower) { score += 180; sig["exact_filename"] = 180 }
        else if !queryLower.isEmpty && pl.contains(queryLower) { score += 90; sig["path_substring"] = 90 }

        // Normalized stem (60)
        let nq = queryLower.replacingOccurrences(of: "[^a-z0-9]", with: "", options: .regularExpression)
        let ns = sl.replacingOccurrences(of: "[^a-z0-9]", with: "", options: .regularExpression)
        if nq.count >= 4 && ns.contains(nq) { score += 60; sig["norm_stem"] = 60 }

        // Exact stem (30)
        if !queryLower.isEmpty && queryLower == sl { score += 30; sig["exact_stem"] = 30 }

        // Per-token scoring with prefix bonus
        let stemWords = sl.components(separatedBy: CharacterSet(charactersIn: "._- "))
        let parentWords = pl.components(separatedBy: CharacterSet(charactersIn: "/._- "))

        for token in tokens {
            var ts = 0
            if nl.contains(token) { ts = token.count >= 4 ? 40 : 28 }
            else if sl.contains(token) { ts = 32 }
            else if pl.contains(token) { ts = 8 }

            if token.count >= 3 {
                var pb = 0
                for w in stemWords where w.count >= 3 && w.hasPrefix(token) && w != token {
                    pb = ts == 0 ? 14 : 10; break
                }
                if pb == 0 {
                    for w in parentWords where w.count >= 3 && w.hasPrefix(token) && w != token {
                        pb = ts == 0 ? 8 : 6; break
                    }
                }
                ts += pb
            }

            if ts == 0 {
                for e in expandedTokens where e != token && (nl.contains(e) || pl.contains(e)) {
                    ts = 12; break
                }
            }

            if ts > 0 { score += ts; matched += 1; sig["token_score"] = (sig["token_score"] ?? 0) + Double(ts) }
        }

        // Extension hint (42)
        if !extensionHints.isEmpty {
            if extensionHints.contains(ext) { score += 42; sig["ext_hint"] = 42 }
            else if !ext.isEmpty { score -= 8; sig["ext_penalty"] = -8 }
        }

        // Folder hint (16 each)
        for f in folderHints where pl.contains("/\(f.lowercased())/") {
            score += 16; sig["folder_hint"] = (sig["folder_hint"] ?? 0) + 16
        }

        // Preferred folders (4)
        for pf in ["/documents/", "/desktop/", "/downloads/", "/projects/"] where pl.contains(pf) {
            score += 4; sig["preferred_folder"] = 4; break
        }

        // Coverage boost
        if !tokens.isEmpty {
            let cov = Double(matched) / Double(tokens.count)
            if cov >= 0.75 { score += 24; sig["coverage"] = 24 }
            else if cov >= 0.5 { score += 14; sig["coverage"] = 14 }
        }

        if source == "photos_library" { score += 20; sig["photos_boost"] = 20 }

        let minScore = 14 + min(24, tokens.count * 3)
        if score < minScore { return (0, ["below_threshold": Double(minScore - score)]) }
        return (score, sig)
    }

    // ── Candidate gathering: Local Filesystem ──

    private func gatherLocalCandidates(
        extensionHints: Set<String>, explicitExtensions: [String]?,
        deepMode: Bool, scanLimit: Int
    ) -> [(path: String, name: String, url: URL?, meta: [String: Any], source: String)] {
        let fm = FileManager.default
        var results: [(path: String, name: String, url: URL?, meta: [String: Any], source: String)] = []

        var dirs: [URL] = []
        // App sandbox directories
        if let d = fm.urls(for: .documentDirectory, in: .userDomainMask).first { dirs.append(d) }
        if let d = fm.urls(for: .downloadsDirectory, in: .userDomainMask).first, !dirs.contains(d) { dirs.append(d) }

        // iCloud Drive container
        if let icloudURL = fm.url(forUbiquityContainerIdentifier: nil)?.appendingPathComponent("Documents") {
            dirs.append(icloudURL)
        }

        // App Support + shared group containers
        if let d = fm.urls(for: .applicationSupportDirectory, in: .userDomainMask).first { dirs.append(d) }
        if let groupURL = fm.containerURL(forSecurityApplicationGroupIdentifier: "group.com.aiagent.shared") {
            dirs.append(groupURL)
        }

        // ── Security-scoped bookmarked folders (user-granted access) ──
        let bookmarkedFolders = BookmarkedFolderManager.shared.bookmarkedFolders()
        for bURL in bookmarkedFolders {
            if !dirs.contains(bURL) {
                dirs.append(bURL)
            }
        }

        if deepMode {
            if let d = fm.urls(for: .cachesDirectory, in: .userDomainMask).first { dirs.append(d) }
            dirs.append(fm.temporaryDirectory)
        }

        let extFilter: Set<String>? = explicitExtensions.map { Set($0.map { $0.lowercased() }) }
        var scanned = 0

        for dir in dirs {
            guard fm.fileExists(atPath: dir.path) else { continue }
            // Start accessing security-scoped resource for bookmarked folders
            let isBookmarked = bookmarkedFolders.contains(dir)
            if isBookmarked { _ = dir.startAccessingSecurityScopedResource() }
            defer { if isBookmarked { dir.stopAccessingSecurityScopedResource() } }
            guard let en = fm.enumerator(
                at: dir, includingPropertiesForKeys: [.fileSizeKey, .contentModificationDateKey, .creationDateKey, .isDirectoryKey, .typeIdentifierKey],
                options: [.skipsHiddenFiles]
            ) else { continue }

            while let url = en.nextObject() as? URL {
                scanned += 1; if scanned > scanLimit { break }
                let isDir = (try? url.resourceValues(forKeys: [.isDirectoryKey]))?.isDirectory ?? false
                // Include directories too — user might be looking for a folder
                let ext = url.pathExtension.lowercased()
                if !isDir, let ef = extFilter, !ef.isEmpty, !ef.contains(ext) { continue }
                let rv = try? url.resourceValues(forKeys: [.fileSizeKey, .contentModificationDateKey, .creationDateKey, .typeIdentifierKey])
                var meta: [String: Any] = [
                    "name": url.lastPathComponent, "path": url.path,
                    "size_bytes": rv?.fileSize ?? 0,
                    "modified": rv?.contentModificationDate?.ISO8601Format() ?? "unknown",
                    "created": rv?.creationDate?.ISO8601Format() ?? "unknown",
                    "type_identifier": rv?.typeIdentifier ?? "unknown",
                ]
                if isDir { meta["is_directory"] = true }
                results.append((path: url.path, name: url.lastPathComponent, url: url, meta: meta, source: "local_filesystem"))
            }
        }
        return results
    }

    // ── Candidate gathering: Photos Library ──

    private func gatherPhotoCandidates(query: String, limit: Int) async -> [(path: String, name: String, url: URL?, meta: [String: Any], source: String)] {
        let status = await PHPhotoLibrary.requestAuthorization(for: .readWrite)
        guard status == .authorized || status == .limited else { return [] }

        let opts = PHFetchOptions()
        opts.sortDescriptors = [NSSortDescriptor(key: "creationDate", ascending: false)]
        opts.fetchLimit = limit

        if query.contains("screenshot") {
            opts.predicate = NSPredicate(format: "mediaSubtype == %d", PHAssetMediaSubtype.photoScreenshot.rawValue)
        } else if query.contains("video") || query.contains("movie") {
            opts.predicate = NSPredicate(format: "mediaType == %d", PHAssetMediaType.video.rawValue)
        } else if query.contains("live") {
            opts.predicate = NSPredicate(format: "mediaSubtype == %d", PHAssetMediaSubtype.photoLive.rawValue)
        } else if query.contains("panorama") || query.contains("pano") {
            opts.predicate = NSPredicate(format: "mediaSubtype == %d", PHAssetMediaSubtype.photoPanorama.rawValue)
        } else if query.contains("favorite") || query.contains("favourite") {
            opts.predicate = NSPredicate(format: "isFavorite == YES")
        } else {
            opts.predicate = NSPredicate(format: "mediaType == %d OR mediaType == %d", PHAssetMediaType.image.rawValue, PHAssetMediaType.video.rawValue)
        }

        let assets = PHAsset.fetchAssets(with: opts)
        var results: [(path: String, name: String, url: URL?, meta: [String: Any], source: String)] = []

        assets.enumerateObjects { asset, i, stop in
            if i >= limit { stop.pointee = true; return }
            let t = asset.mediaType == .video ? "video" : "photo"
            let n = "\(t)_\(asset.localIdentifier.prefix(8))"
            var meta: [String: Any] = [
                "name": n, "path": "photos://\(asset.localIdentifier)",
                "type": t, "width": asset.pixelWidth, "height": asset.pixelHeight,
                "created": asset.creationDate?.ISO8601Format() ?? "unknown",
                "modified": asset.modificationDate?.ISO8601Format() ?? "unknown",
                "local_identifier": asset.localIdentifier,
            ]
            if asset.duration > 0 { meta["duration_seconds"] = Int(asset.duration) }
            if asset.location != nil { meta["has_location"] = true }
            if asset.isFavorite { meta["favorite"] = true }
            if asset.representsBurst { meta["burst"] = true }
            results.append((path: "photos://\(asset.localIdentifier)", name: n, url: nil, meta: meta, source: "photos_library"))
        }
        return results
    }

    // ── Candidate gathering: Spotlight ──

    private func gatherSpotlightCandidates(query: String, extensions: [String]?, limit: Int) async -> [(path: String, name: String, url: URL?, meta: [String: Any], source: String)] {
        // Tokenize the query for per-token matching
        let tokens = tokenizeQuery(query.lowercased())
        let searchTerms = tokens.isEmpty ? [query] : tokens

        return await withCheckedContinuation { continuation in
            let mq = NSMetadataQuery()
            mq.searchScopes = [
                NSMetadataQueryUbiquitousDocumentsScope,
                NSMetadataQueryAccessibleUbiquitousExternalDocumentsScope,
            ]

            // Build per-token OR predicates across multiple attributes
            var tokenPredicates: [NSPredicate] = []
            for term in searchTerms {
                tokenPredicates.append(NSPredicate(format: "kMDItemDisplayName CONTAINS[cd] %@", term))
                tokenPredicates.append(NSPredicate(format: "kMDItemFSName CONTAINS[cd] %@", term))
                tokenPredicates.append(NSPredicate(format: "kMDItemTextContent CONTAINS[cd] %@", term))
            }
            var mainPred: NSPredicate = NSCompoundPredicate(orPredicateWithSubpredicates: tokenPredicates)

            // Also try the full query as a phrase
            let phrasePredicates: [NSPredicate] = [
                NSPredicate(format: "kMDItemDisplayName CONTAINS[cd] %@", query),
                NSPredicate(format: "kMDItemFSName CONTAINS[cd] %@", query),
            ]
            let allPreds = tokenPredicates + phrasePredicates
            mainPred = NSCompoundPredicate(orPredicateWithSubpredicates: allPreds)

            // Extension filter
            if let exts = extensions, !exts.isEmpty {
                let extPred = NSCompoundPredicate(orPredicateWithSubpredicates: exts.map {
                    NSPredicate(format: "kMDItemFSName ENDSWITH[cd] %@", ".\($0)")
                })
                mainPred = NSCompoundPredicate(andPredicateWithSubpredicates: [mainPred, extPred])
            }

            mq.predicate = mainPred

            var obs: NSObjectProtocol?
            var hasResumed = false
            obs = NotificationCenter.default.addObserver(forName: .NSMetadataQueryDidFinishGathering, object: mq, queue: .main) { _ in
                mq.stop()
                if let obs { NotificationCenter.default.removeObserver(obs) }
                guard !hasResumed else { return }
                hasResumed = true

                var results: [(path: String, name: String, url: URL?, meta: [String: Any], source: String)] = []
                for i in 0..<min(mq.resultCount, limit) {
                    guard let item = mq.result(at: i) as? NSMetadataItem else { continue }
                    let name = item.value(forAttribute: NSMetadataItemDisplayNameKey) as? String ?? "unknown"
                    let path = item.value(forAttribute: NSMetadataItemPathKey) as? String ?? ""
                    let size = item.value(forAttribute: NSMetadataItemFSSizeKey) as? Int ?? 0
                    let ct = item.value(forAttribute: NSMetadataItemContentTypeKey) as? String ?? "unknown"
                    let meta: [String: Any] = ["name": name, "path": path, "size_bytes": size, "content_type": ct]
                    results.append((path: path, name: name, url: path.isEmpty ? nil : URL(fileURLWithPath: path), meta: meta, source: "spotlight_icloud"))
                }
                continuation.resume(returning: results)
            }
            // Longer timeout for Spotlight to gather
            DispatchQueue.main.asyncAfter(deadline: .now() + 8.0) {
                if mq.isGathering { mq.stop() }
                guard !hasResumed else { return }
                hasResumed = true
                continuation.resume(returning: [])
            }
            mq.start()
        }
    }

    private func isTextFile(url: URL) -> Bool {
        let textExts: Set<String> = ["txt", "md", "csv", "json", "xml", "html", "css", "js", "ts",
            "py", "swift", "java", "cpp", "c", "h", "rb", "go", "rs", "sh",
            "yaml", "yml", "toml", "ini", "log", "rtf", "tex", "sql"]
        return textExts.contains(url.pathExtension.lowercased())
    }

    // MARK: - grant_folder_access

    private func executeGrantFolderAccess(_ args: [String: Any]) async -> [String: Any] {
        let action = args["action"] as? String ?? "add"
        let reason = args["reason"] as? String

        if action == "list" {
            let folders = BookmarkedFolderManager.shared.bookmarkedFolders()
            return [
                "status": "success",
                "folders": folders.map { ["path": $0.path, "name": $0.lastPathComponent] },
                "count": folders.count,
                "hint": "These are the folders the app can currently search. Use action='add' to grant access to more folders.",
            ]
        }

        if action == "clear" {
            BookmarkedFolderManager.shared.clearBookmarks()
            return ["status": "success", "message": "All folder bookmarks cleared."]
        }

        // action == "add" — present folder picker
        guard let selectedURL = await BookmarkedFolderManager.shared.presentFolderPicker(reason: reason) else {
            return [
                "status": "cancelled",
                "message": "The user cancelled the folder picker. They can try again later.",
            ]
        }

        let saved = BookmarkedFolderManager.shared.addBookmark(for: selectedURL)
        if saved {
            return [
                "status": "success",
                "message": "Folder access granted and saved. The app can now search files in this folder.",
                "folder": selectedURL.path,
                "folder_name": selectedURL.lastPathComponent,
                "total_bookmarked": BookmarkedFolderManager.shared.count,
            ]
        } else {
            return [
                "status": "failed",
                "error": "Could not save bookmark for the selected folder.",
                "folder": selectedURL.path,
            ]
        }
    }

    // MARK: - open_item

    private func executeOpenItem(_ args: [String: Any]) async throws -> [String: Any] {
        let pathString = args["path"] as? String ?? ""
        guard !pathString.isEmpty else {
            return ["error": "path is required", "status": "failed"]
        }

        // iOS deep link mapping for common shortcuts
        let deepLinks: [String: String] = [
            "settings": UIApplication.openSettingsURLString,
            "wifi": "App-prefs:WIFI",
            "bluetooth": "App-prefs:Bluetooth",
            "battery": "App-prefs:BATTERY_USAGE",
            "storage": "App-prefs:STORAGE_AND_BACKUP",
            "notifications": "App-prefs:NOTIFICATIONS_ID",
            "privacy": "App-prefs:Privacy",
            "photos": "photos-redirect://",
            "camera": "camera://",
            "maps": "maps://",
            "mail": "mailto:",
            "phone": "tel:",
            "messages": "sms:",
            "music": "music://",
            "appstore": "itms-apps://",
            "safari": "x-safari-https://",
            "files": "shareddocuments://",
            "calendar": "calshow://",
            "contacts": "contacts://",
            "health": "x-apple-health://",
            "wallet": "shoebox://",
        ]

        // Try deep link alias first
        let lowered = pathString.lowercased().trimmingCharacters(in: .whitespaces)
        if let deepURL = deepLinks[lowered], let url = URL(string: deepURL) {
            let opened = await UIApplication.shared.open(url, options: [:])
            return opened
                ? ["status": "success", "opened": deepURL, "alias": lowered, "type": "deep_link"]
                : ["error": "Could not open deep link: \(lowered)", "status": "failed"]
        }

        // Try as URL first, then file path
        let url: URL
        if pathString.hasPrefix("http") || pathString.contains("://") {
            guard let parsed = URL(string: pathString) else {
                return ["error": "Invalid URL: \(pathString)", "status": "failed"]
            }
            url = parsed
        } else {
            url = URL(fileURLWithPath: pathString)
        }

        // Check canOpenURL first for better error messages
        let canOpen = UIApplication.shared.canOpenURL(url)
        if !canOpen && !url.isFileURL {
            return ["error": "No app available to open: \(pathString). Available shortcuts: \(Array(deepLinks.keys).sorted().joined(separator: ", "))", "status": "failed"]
        }

        let opened = await UIApplication.shared.open(url, options: [:])
        return opened
            ? ["status": "success", "opened": pathString, "type": url.isFileURL ? "file" : "url"]
            : ["error": "Could not open: \(pathString)", "status": "failed"]
    }

    // MARK: - read_screen

    private func executeReadScreen(_ args: [String: Any]) -> [String: Any] {
        let screenBounds = UIScreen.main.bounds
        let scale = UIScreen.main.scale

        var info: [String: Any] = [
            "status": "success",
            "platform": "iOS",
            "screen_width": Int(screenBounds.width),
            "screen_height": Int(screenBounds.height),
            "scale": scale,
            "resolution": "\(Int(screenBounds.width * scale))x\(Int(screenBounds.height * scale))",
        ]

        if let purpose = args["purpose"] as? String {
            info["purpose"] = purpose
        }

        // Capture the current app's window as a screenshot
        if let windowScene = UIApplication.shared.connectedScenes.first as? UIWindowScene,
           let window = windowScene.windows.first {
            let renderer = UIGraphicsImageRenderer(bounds: window.bounds)
            let image = renderer.image { ctx in
                window.drawHierarchy(in: window.bounds, afterScreenUpdates: true)
            }

            // Get image data for the AI
            if let imageData = image.jpegData(compressionQuality: 0.7) {
                info["screenshot_base64"] = imageData.base64EncodedString()
                info["screenshot_width"] = Int(image.size.width * image.scale)
                info["screenshot_height"] = Int(image.size.height * image.scale)
                info["screenshot_size_bytes"] = imageData.count
            }

            // Extract visible text using Vision OCR
            if let cgImage = image.cgImage {
                let ocrText = performOCR(on: cgImage)
                if !ocrText.isEmpty {
                    info["visible_text"] = ocrText
                }
            }

            info["interface_style"] = windowScene.traitCollection.userInterfaceStyle == .dark ? "dark" : "light"
            info["device_orientation"] = windowScene.interfaceOrientation.isLandscape ? "landscape" : "portrait"
        } else {
            info["note"] = "Could not capture app window"
        }

        // Device info
        info["device_model"] = UIDevice.current.model
        info["system_version"] = UIDevice.current.systemVersion
        info["battery_level"] = UIDevice.current.batteryLevel >= 0 ? UIDevice.current.batteryLevel : -1
        info["battery_state"] = batteryStateString(UIDevice.current.batteryState)

        return info
    }

    /// Perform Vision OCR on a CGImage and return recognized text.
    private func performOCR(on image: CGImage) -> String {
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = true

        let handler = VNImageRequestHandler(cgImage: image, options: [:])
        try? handler.perform([request])

        let observations = request.results ?? []
        return observations
            .compactMap { $0.topCandidates(1).first?.string }
            .joined(separator: "\n")
    }

    private func batteryStateString(_ state: UIDevice.BatteryState) -> String {
        switch state {
        case .unknown: return "unknown"
        case .unplugged: return "unplugged"
        case .charging: return "charging"
        case .full: return "full"
        @unknown default: return "unknown"
        }
    }

    // MARK: - read_document

    private func executeReadDocument(_ args: [String: Any]) throws -> [String: Any] {
        let pathString = args["path"] as? String ?? ""
        guard !pathString.isEmpty else {
            return ["error": "path is required", "status": "failed"]
        }

        let mode = args["mode"] as? String ?? "text"
        let fileURL = URL(fileURLWithPath: pathString)
        let fileManager = FileManager.default

        guard fileManager.fileExists(atPath: pathString) else {
            return ["error": "File not found: \(pathString)", "status": "failed"]
        }

        switch mode {
        case "metadata":
            let attributes = try fileManager.attributesOfItem(atPath: pathString)
            return [
                "status": "success",
                "path": pathString,
                "name": fileURL.lastPathComponent,
                "extension": fileURL.pathExtension,
                "size_bytes": attributes[.size] as? Int ?? 0,
                "created": (attributes[.creationDate] as? Date)?.ISO8601Format() ?? "unknown",
                "modified": (attributes[.modificationDate] as? Date)?.ISO8601Format() ?? "unknown",
                "type": attributes[.type] as? String ?? "unknown",
            ]

        case "text", "code":
            let maxBytes = 1024 * 1024  // 1MB limit
            let data = try Data(contentsOf: fileURL)
            if data.count > maxBytes {
                let truncated = data.prefix(maxBytes)
                let text = String(data: truncated, encoding: .utf8) ?? "[Binary content — cannot display as text]"
                return [
                    "status": "success",
                    "content": text,
                    "truncated": true,
                    "total_bytes": data.count,
                ]
            }
            let text = String(data: data, encoding: .utf8) ?? "[Binary content — cannot display as text]"
            return [
                "status": "success",
                "content": text,
                "truncated": false,
            ]

        case "pdf":
            return extractPDFText(from: fileURL)

        case "lines":
            // Read specific line range
            let startLine = args["start_line"] as? Int ?? 1
            let endLine = args["end_line"] as? Int ?? (startLine + 100)
            let data = try Data(contentsOf: fileURL)
            guard let fullText = String(data: data, encoding: .utf8) else {
                return ["error": "Cannot read file as text", "status": "failed"]
            }
            let allLines = fullText.components(separatedBy: "\n")
            let safeStart = max(0, startLine - 1)
            let safeEnd = min(allLines.count, endLine)
            let selectedLines = Array(allLines[safeStart..<safeEnd])
            return [
                "status": "success",
                "content": selectedLines.joined(separator: "\n"),
                "start_line": safeStart + 1,
                "end_line": safeEnd,
                "total_lines": allLines.count,
            ]

        default:
            return ["error": "Unknown mode: \(mode). Use text, code, pdf, lines, or metadata.", "status": "failed"]
        }
    }

    /// Full PDF text extraction using PDFKit.
    private func extractPDFText(from url: URL) -> [String: Any] {
        guard let pdfDoc = PDFDocument(url: url) else {
            return ["error": "Could not open PDF", "status": "failed"]
        }

        let pageCount = pdfDoc.pageCount
        let maxPages = min(pageCount, 100)
        var fullText = ""
        var pageTexts: [[String: Any]] = []

        for i in 0..<maxPages {
            guard let page = pdfDoc.page(at: i) else { continue }
            let pageText = page.string ?? ""
            fullText += pageText + "\n\n"
            if i < 5 { // Include per-page detail for first 5 pages
                pageTexts.append([
                    "page": i + 1,
                    "char_count": pageText.count,
                    "preview": String(pageText.prefix(200)),
                ])
            }
        }

        let truncated = fullText.count > 50000
        return [
            "status": "success",
            "page_count": pageCount,
            "pages_scanned": maxPages,
            "content": String(fullText.prefix(50000)),
            "truncated": truncated,
            "total_characters": fullText.count,
            "page_details": pageTexts,
        ]
    }

    // MARK: - browse_web

    private func executeBrowseWeb(_ args: [String: Any]) async throws -> [String: Any] {
        let urlString = args["url"] as? String
        let urls = args["urls"] as? [String]
        let searchQuery = args["search_query"] as? String
        let timeout = min(max(args["timeout_seconds"] as? Int ?? 15, 3), 60)

        // Web search mode
        if let searchQuery, !searchQuery.isEmpty {
            return try await executeWebSearch(query: searchQuery, timeout: timeout)
        }

        // Multi-URL mode
        if let urls, !urls.isEmpty {
            return try await fetchMultipleURLs(urls: urls, timeout: timeout)
        }

        // Single URL mode
        guard let urlString, !urlString.isEmpty else {
            return ["error": "Either url, urls, or search_query is required", "status": "failed"]
        }

        guard let url = URL(string: urlString) else {
            return ["error": "Invalid URL: \(urlString)", "status": "failed"]
        }

        return try await fetchAndExtractText(from: url, timeout: timeout)
    }

    /// Fetch multiple URLs with structured results.
    private func fetchMultipleURLs(urls: [String], timeout: Int) async throws -> [String: Any] {
        let limitedURLs = Array(urls.prefix(10)) // Cap at 10 URLs
        var results: [[String: Any]] = []

        for urlString in limitedURLs {
            guard let url = URL(string: urlString) else {
                results.append(["url": urlString, "error": "Invalid URL", "status": "failed"])
                continue
            }
            do {
                let result = try await fetchAndExtractText(from: url, timeout: timeout)
                results.append(result)
            } catch {
                results.append(["url": urlString, "error": error.localizedDescription, "status": "failed"])
            }
        }

        return [
            "status": "success",
            "results": results,
            "count": results.count,
        ]
    }

    private func fetchAndExtractText(from url: URL, timeout: Int) async throws -> [String: Any] {
        var request = URLRequest(url: url)
        request.timeoutInterval = TimeInterval(timeout)
        request.setValue(
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
            forHTTPHeaderField: "User-Agent"
        )
        request.setValue("text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", forHTTPHeaderField: "Accept")
        request.setValue("en-US,en;q=0.9", forHTTPHeaderField: "Accept-Language")

        let (data, response) = try await URLSession.shared.data(for: request)
        let httpResponse = response as? HTTPURLResponse
        let statusCode = httpResponse?.statusCode ?? 0

        guard (200..<400).contains(statusCode) else {
            return [
                "url": url.absoluteString,
                "status_code": statusCode,
                "error": "HTTP \(statusCode)",
                "status": "failed",
            ]
        }

        let contentType = httpResponse?.value(forHTTPHeaderField: "Content-Type") ?? ""

        // Handle non-HTML content types
        if contentType.contains("application/json") {
            let text = String(data: data, encoding: .utf8) ?? ""
            return [
                "status": "success",
                "url": url.absoluteString,
                "status_code": statusCode,
                "content_type": "json",
                "content": String(text.prefix(12000)),
                "truncated": text.count > 12000,
            ]
        }

        if contentType.contains("text/plain") || contentType.contains("text/csv") {
            let text = String(data: data, encoding: .utf8) ?? ""
            return [
                "status": "success",
                "url": url.absoluteString,
                "status_code": statusCode,
                "content_type": "text",
                "content": String(text.prefix(12000)),
                "truncated": text.count > 12000,
            ]
        }

        // HTML extraction
        guard let html = String(data: data, encoding: .utf8)
                ?? String(data: data, encoding: .isoLatin1) else {
            return [
                "url": url.absoluteString,
                "status_code": statusCode,
                "content": "[Binary content — not text/HTML]",
                "status": "success",
            ]
        }

        let title = extractHTMLTitle(html) ?? url.host ?? ""
        let metaDescription = extractMetaDescription(html)
        let articleText = extractArticleContent(html)
        let truncated = articleText.count > 10000
        let finalText = truncated ? String(articleText.prefix(10000)) : articleText

        var result: [String: Any] = [
            "status": "success",
            "url": url.absoluteString,
            "status_code": statusCode,
            "title": title,
            "content": finalText,
            "truncated": truncated,
            "content_length": articleText.count,
        ]
        if let metaDescription {
            result["description"] = metaDescription
        }
        return result
    }

    /// Multi-engine web search: queries DuckDuckGo and Brave, merges results.
    private func executeWebSearch(query: String, timeout: Int) async throws -> [String: Any] {
        let encoded = query.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? query

        let engines: [(name: String, url: String)] = [
            ("duckduckgo", "https://html.duckduckgo.com/html/?q=\(encoded)"),
            ("brave", "https://search.brave.com/search?q=\(encoded)&source=web"),
        ]

        var allResults: [[String: Any]] = []
        var engineResults: [String: Any] = [:]

        for engine in engines {
            guard let url = URL(string: engine.url) else {
                engineResults[engine.name] = ["error": "Invalid search URL"]
                continue
            }
            do {
                var result = try await fetchAndExtractText(from: url, timeout: timeout)
                if let content = result["content"] as? String {
                    let links = extractSearchResultLinks(from: content, engine: engine.name)
                    result["extracted_links"] = links
                    for link in links {
                        allResults.append(link as [String: Any])
                    }
                }
                engineResults[engine.name] = result
            } catch {
                engineResults[engine.name] = ["error": error.localizedDescription]
            }
        }

        return [
            "status": "success",
            "search_query": query,
            "engines_queried": engines.map(\.name),
            "results": allResults.prefix(15).map { $0 },
            "result_count": min(allResults.count, 15),
            "engine_details": engineResults,
        ]
    }

    /// Extract search result links from search engine HTML content.
    private func extractSearchResultLinks(from text: String, engine: String) -> [[String: String]] {
        // Look for URL patterns that look like search results
        var links: [[String: String]] = []
        let urlPattern = try? NSRegularExpression(
            pattern: "https?://(?!(?:html\\.duckduckgo|search\\.brave|www\\.google))[a-zA-Z0-9][a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}[/\\w.?&=%-]*",
            options: []
        )

        if let urlPattern {
            let matches = urlPattern.matches(in: text, range: NSRange(text.startIndex..., in: text))
            var seen = Set<String>()
            for match in matches.prefix(20) {
                guard let range = Range(match.range, in: text) else { continue }
                let urlString = String(text[range])
                let host = URL(string: urlString)?.host ?? ""
                // Skip common non-result domains
                if host.contains("duckduckgo") || host.contains("brave") || host.contains("google") { continue }
                if seen.contains(host) { continue }
                seen.insert(host)
                links.append(["url": urlString, "source": engine])
            }
        }

        return Array(links.prefix(10))
    }

    // MARK: - HTML Extraction Helpers

    /// Extract article content with boilerplate removal — mirrors Python's tiered extraction.
    private func extractArticleContent(_ html: String) -> String {
        var text = html

        // 1. Remove script, style, nav, header, footer, aside blocks
        let removePatterns = [
            "<script[^>]*>[\\s\\S]*?</script>",
            "<style[^>]*>[\\s\\S]*?</style>",
            "<nav[^>]*>[\\s\\S]*?</nav>",
            "<header[^>]*>[\\s\\S]*?</header>",
            "<footer[^>]*>[\\s\\S]*?</footer>",
            "<aside[^>]*>[\\s\\S]*?</aside>",
            "<noscript[^>]*>[\\s\\S]*?</noscript>",
            "<!--[\\s\\S]*?-->",
            // Cookie/consent banners
            "<div[^>]*(?:cookie|consent|gdpr|banner|popup|modal|overlay)[^>]*>[\\s\\S]*?</div>",
        ]
        for pattern in removePatterns {
            if let regex = try? NSRegularExpression(pattern: pattern, options: .caseInsensitive) {
                text = regex.stringByReplacingMatches(in: text, range: NSRange(text.startIndex..., in: text), withTemplate: " ")
            }
        }

        // 2. Try to extract <article> or <main> content first (higher signal)
        if let articleRegex = try? NSRegularExpression(pattern: "<(?:article|main)[^>]*>([\\s\\S]*?)</(?:article|main)>", options: .caseInsensitive),
           let match = articleRegex.firstMatch(in: text, range: NSRange(text.startIndex..., in: text)),
           let range = Range(match.range(at: 1), in: text) {
            let articleHTML = String(text[range])
            let articleText = stripHTMLTags(articleHTML)
            if articleText.count > 200 { // Only use if substantial
                return articleText
            }
        }

        // 3. Fallback: strip all tags from remaining content
        return stripHTMLTags(text)
    }

    /// Strip HTML tags and decode entities.
    private func stripHTMLTags(_ html: String) -> String {
        var text = html

        // Replace block-level closing tags with newlines
        if let blockRegex = try? NSRegularExpression(pattern: "</?(p|div|br|h[1-6]|li|tr|blockquote|pre|section)\\s*/?>", options: .caseInsensitive) {
            text = blockRegex.stringByReplacingMatches(in: text, range: NSRange(text.startIndex..., in: text), withTemplate: "\n")
        }

        // Remove all remaining tags
        if let tagRegex = try? NSRegularExpression(pattern: "<[^>]+>", options: []) {
            text = tagRegex.stringByReplacingMatches(in: text, range: NSRange(text.startIndex..., in: text), withTemplate: "")
        }

        // Decode HTML entities
        text = text
            .replacingOccurrences(of: "&amp;", with: "&")
            .replacingOccurrences(of: "&lt;", with: "<")
            .replacingOccurrences(of: "&gt;", with: ">")
            .replacingOccurrences(of: "&quot;", with: "\"")
            .replacingOccurrences(of: "&#39;", with: "'")
            .replacingOccurrences(of: "&nbsp;", with: " ")
            .replacingOccurrences(of: "&#x27;", with: "'")
            .replacingOccurrences(of: "&#x2F;", with: "/")
            .replacingOccurrences(of: "&apos;", with: "'")

        // Collapse whitespace
        if let wsRegex = try? NSRegularExpression(pattern: "[ \\t]+", options: []) {
            text = wsRegex.stringByReplacingMatches(in: text, range: NSRange(text.startIndex..., in: text), withTemplate: " ")
        }
        if let nlRegex = try? NSRegularExpression(pattern: "\\n{3,}", options: []) {
            text = nlRegex.stringByReplacingMatches(in: text, range: NSRange(text.startIndex..., in: text), withTemplate: "\n\n")
        }

        return text.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func extractHTMLTitle(_ html: String) -> String? {
        guard let regex = try? NSRegularExpression(pattern: "<title[^>]*>(.*?)</title>", options: [.caseInsensitive, .dotMatchesLineSeparators]),
              let match = regex.firstMatch(in: html, range: NSRange(html.startIndex..., in: html)),
              let range = Range(match.range(at: 1), in: html) else {
            return nil
        }
        return String(html[range])
            .replacingOccurrences(of: "&amp;", with: "&")
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func extractMetaDescription(_ html: String) -> String? {
        guard let regex = try? NSRegularExpression(
            pattern: "<meta[^>]+name=[\"']description[\"'][^>]+content=[\"']([^\"']*)[\"']",
            options: .caseInsensitive
        ),
              let match = regex.firstMatch(in: html, range: NSRange(html.startIndex..., in: html)),
              let range = Range(match.range(at: 1), in: html) else {
            return nil
        }
        let desc = String(html[range]).trimmingCharacters(in: .whitespacesAndNewlines)
        return desc.isEmpty ? nil : desc
    }

    // MARK: - manage_notes

    private func executeManageNotes(_ args: [String: Any]) throws -> [String: Any] {
        let action = args["action"] as? String ?? ""

        switch action {
        case "create":
            let content = args["content"] as? String ?? ""
            let title = args["title"] as? String
            let tags = args["tags"] as? [String]
            guard !content.isEmpty else {
                return ["error": "content is required for create", "status": "failed"]
            }
            let noteId = UUID().uuidString
            let note: [String: Any] = [
                "note_id": noteId,
                "title": title ?? "Untitled Note",
                "content": content,
                "tags": tags ?? [],
                "created_at": ISO8601DateFormatter().string(from: Date()),
            ]
            saveNoteToDefaults(noteId: noteId, note: note)
            return ["status": "success", "action": "created", "note": note]

        case "list":
            let notes = loadAllNotesFromDefaults()
            return ["status": "success", "notes": notes, "count": notes.count]

        case "get":
            let noteId = args["note_id"] as? String ?? ""
            guard !noteId.isEmpty else {
                return ["error": "note_id is required for get", "status": "failed"]
            }
            if let note = loadNoteFromDefaults(noteId: noteId) {
                return ["status": "success", "note": note]
            }
            return ["error": "Note not found: \(noteId)", "status": "failed"]

        case "update":
            let noteId = args["note_id"] as? String ?? ""
            guard !noteId.isEmpty else {
                return ["error": "note_id is required for update", "status": "failed"]
            }
            guard var note = loadNoteFromDefaults(noteId: noteId) else {
                return ["error": "Note not found: \(noteId)", "status": "failed"]
            }
            if let content = args["content"] as? String { note["content"] = content }
            if let title = args["title"] as? String { note["title"] = title }
            if let tags = args["tags"] as? [String] { note["tags"] = tags }
            note["updated_at"] = ISO8601DateFormatter().string(from: Date())
            saveNoteToDefaults(noteId: noteId, note: note)
            return ["status": "success", "action": "updated", "note": note]

        case "delete":
            let noteId = args["note_id"] as? String ?? ""
            guard !noteId.isEmpty else {
                return ["error": "note_id is required for delete", "status": "failed"]
            }
            deleteNoteFromDefaults(noteId: noteId)
            return ["status": "success", "action": "deleted", "note_id": noteId]

        default:
            return ["error": "Unknown action: \(action). Use create, list, get, update, or delete.", "status": "failed"]
        }
    }

    // Simple UserDefaults-based note storage for iOS
    // In the future, this should use the same SQLite store as macOS for CloudKit sync
    private let notesKey = "ios_agent_notes"

    private func loadAllNotesFromDefaults() -> [[String: Any]] {
        guard let data = UserDefaults.standard.data(forKey: notesKey),
              let notes = try? JSONSerialization.jsonObject(with: data) as? [String: [String: Any]] else {
            return []
        }
        return Array(notes.values)
    }

    private func loadNoteFromDefaults(noteId: String) -> [String: Any]? {
        guard let data = UserDefaults.standard.data(forKey: notesKey),
              let notes = try? JSONSerialization.jsonObject(with: data) as? [String: [String: Any]] else {
            return nil
        }
        return notes[noteId]
    }

    private func saveNoteToDefaults(noteId: String, note: [String: Any]) {
        var notes: [String: [String: Any]] = [:]
        if let data = UserDefaults.standard.data(forKey: notesKey),
           let existing = try? JSONSerialization.jsonObject(with: data) as? [String: [String: Any]] {
            notes = existing
        }
        notes[noteId] = note
        if let data = try? JSONSerialization.jsonObject(with: JSONSerialization.data(withJSONObject: notes)) {
            UserDefaults.standard.set(try? JSONSerialization.data(withJSONObject: data), forKey: notesKey)
        }
    }

    private func deleteNoteFromDefaults(noteId: String) {
        guard let data = UserDefaults.standard.data(forKey: notesKey),
              var notes = try? JSONSerialization.jsonObject(with: data) as? [String: [String: Any]] else {
            return
        }
        notes.removeValue(forKey: noteId)
        UserDefaults.standard.set(try? JSONSerialization.data(withJSONObject: notes), forKey: notesKey)
    }

    // MARK: - generate_image

    private func executeGenerateImage(_ args: [String: Any]) async throws -> [String: Any] {
        let prompt = args["prompt"] as? String ?? ""
        guard !prompt.isEmpty else {
            return ["error": "prompt is required", "status": "failed"]
        }

        let aspectRatio = args["aspect_ratio"] as? String ?? "1:1"

        // Use the same Gemini API key as the service
        guard let apiKey = UserDefaults.standard.string(forKey: "gemini_api_key"),
              !apiKey.isEmpty else {
            return ["error": "API key not configured for image generation", "status": "failed"]
        }

        // Call Gemini Imagen API
        let url = URL(string: "https://generativelanguage.googleapis.com/v1beta/models/imagen-3.0-generate-002:predict?key=\(apiKey)")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 60

        let body: [String: Any] = [
            "instances": [["prompt": prompt]],
            "parameters": [
                "sampleCount": 1,
                "aspectRatio": aspectRatio,
            ]
        ]
        request.httpBody = try JSONSerialization.data(withJSONObject: body)

        let (data, response) = try await URLSession.shared.data(for: request)
        let httpResponse = response as? HTTPURLResponse

        guard httpResponse?.statusCode == 200 else {
            let errorText = String(data: data, encoding: .utf8) ?? "Unknown error"
            return ["error": "Image generation failed (HTTP \(httpResponse?.statusCode ?? 0)): \(errorText)", "status": "failed"]
        }

        // Parse response and save image
        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let predictions = json["predictions"] as? [[String: Any]],
              let firstPrediction = predictions.first,
              let imageData = firstPrediction["bytesBase64Encoded"] as? String else {
            return ["error": "Unexpected image generation response format", "status": "failed"]
        }

        // Save to Documents
        guard let decodedData = Data(base64Encoded: imageData) else {
            return ["error": "Failed to decode image data", "status": "failed"]
        }

        let documentsURL = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first!
        let imagesDir = documentsURL.appendingPathComponent("generated_images")
        try FileManager.default.createDirectory(at: imagesDir, withIntermediateDirectories: true)
        let fileName = "image_\(UUID().uuidString.prefix(8)).png"
        let fileURL = imagesDir.appendingPathComponent(fileName)
        try decodedData.write(to: fileURL)

        return [
            "status": "success",
            "image_path": fileURL.path,
            "prompt": prompt,
            "aspect_ratio": aspectRatio,
        ]
    }

    // MARK: - create_directory

    private func executeCreateDirectory(_ args: [String: Any]) throws -> [String: Any] {
        let pathString = args["path"] as? String ?? ""
        guard !pathString.isEmpty else {
            return ["error": "path is required", "status": "failed"]
        }

        let url = URL(fileURLWithPath: pathString)
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true, attributes: nil)

        return [
            "status": "success",
            "path": pathString,
            "created": true,
        ]
    }
}

#endif
