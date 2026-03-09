//
//  BookmarkedFolderManager.swift
//  AIAgentUI
//
//  Manages security-scoped bookmarks for user-granted folder access on iOS.
//  iOS apps cannot search arbitrary filesystem locations — users must explicitly
//  grant access via UIDocumentPickerViewController, and access is preserved
//  via security-scoped URL bookmarks stored in UserDefaults.
//

#if os(iOS)

import Foundation
import UIKit
import UniformTypeIdentifiers

/// Manages security-scoped bookmarks so the app can search user-granted folders.
@MainActor
final class BookmarkedFolderManager: NSObject {

    static let shared = BookmarkedFolderManager()

    private let bookmarkKey = "com.aiagent.bookmarked_folders"

    private override init() {
        super.init()
    }

    // MARK: - Public API

    /// All currently bookmarked folder URLs (resolved from stored bookmarks).
    func bookmarkedFolders() -> [URL] {
        guard let bookmarkDatas = UserDefaults.standard.array(forKey: bookmarkKey) as? [Data] else {
            return []
        }
        var urls: [URL] = []
        for data in bookmarkDatas {
            var isStale = false
            if let url = try? URL(resolvingBookmarkData: data, bookmarkDataIsStale: &isStale) {
                if isStale {
                    // Re-bookmark if stale
                    if let fresh = try? url.bookmarkData(options: .minimalBookmark) {
                        replaceBookmark(old: data, new: fresh)
                    }
                }
                urls.append(url)
            }
        }
        return urls
    }

    /// Save a security-scoped bookmark for a URL the user granted access to.
    func addBookmark(for url: URL) -> Bool {
        guard url.startAccessingSecurityScopedResource() else { return false }
        defer { url.stopAccessingSecurityScopedResource() }

        guard let bookmarkData = try? url.bookmarkData(options: .minimalBookmark) else {
            return false
        }

        var existing = UserDefaults.standard.array(forKey: bookmarkKey) as? [Data] ?? []

        // Don't duplicate — check if we already have this path
        let existingPaths = Set(bookmarkedFolders().map { $0.path })
        if existingPaths.contains(url.path) { return true }

        existing.append(bookmarkData)
        UserDefaults.standard.set(existing, forKey: bookmarkKey)
        return true
    }

    /// Remove all bookmarks.
    func clearBookmarks() {
        UserDefaults.standard.removeObject(forKey: bookmarkKey)
    }

    /// Number of bookmarked folders.
    var count: Int {
        (UserDefaults.standard.array(forKey: bookmarkKey) as? [Data])?.count ?? 0
    }

    // MARK: - Folder Picker

    /// Present a folder picker and return the selected URL.
    /// The caller should call `addBookmark(for:)` with the result.
    func presentFolderPicker(reason: String? = nil) async -> URL? {
        await withCheckedContinuation { continuation in
            guard let windowScene = UIApplication.shared.connectedScenes
                .compactMap({ $0 as? UIWindowScene }).first,
                  let rootVC = windowScene.windows.first(where: { $0.isKeyWindow })?.rootViewController else {
                continuation.resume(returning: nil)
                return
            }

            // Find the topmost presented view controller
            var topVC = rootVC
            while let presented = topVC.presentedViewController {
                topVC = presented
            }

            let showPicker = {
                let picker = UIDocumentPickerViewController(forOpeningContentTypes: [UTType.folder])
                picker.allowsMultipleSelection = false
                picker.directoryURL = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first

                let delegate = FolderPickerDelegate { url in
                    continuation.resume(returning: url)
                }
                // Store delegate to prevent deallocation
                objc_setAssociatedObject(picker, &FolderPickerDelegate.associatedKey, delegate, .OBJC_ASSOCIATION_RETAIN)
                picker.delegate = delegate
                topVC.present(picker, animated: true)
            }

            if let reason = reason, !reason.isEmpty {
                let alert = UIAlertController(title: "Allow Folder Access", message: reason, preferredStyle: .alert)
                alert.addAction(UIAlertAction(title: "Cancel", style: .cancel) { _ in
                    continuation.resume(returning: nil)
                })
                alert.addAction(UIAlertAction(title: "Select Folder", style: .default) { _ in
                    showPicker()
                })
                topVC.present(alert, animated: true)
            } else {
                showPicker()
            }
        }
    }

    // MARK: - Private

    private func replaceBookmark(old: Data, new: Data) {
        var existing = UserDefaults.standard.array(forKey: bookmarkKey) as? [Data] ?? []
        if let idx = existing.firstIndex(of: old) {
            existing[idx] = new
            UserDefaults.standard.set(existing, forKey: bookmarkKey)
        }
    }
}

// MARK: - Folder Picker Delegate

private final class FolderPickerDelegate: NSObject, UIDocumentPickerDelegate {
    nonisolated(unsafe) static var associatedKey: UInt8 = 0
    private let completion: @Sendable (URL?) -> Void

    init(completion: @escaping @Sendable (URL?) -> Void) {
        self.completion = completion
    }

    func documentPicker(_ controller: UIDocumentPickerViewController, didPickDocumentsAt urls: [URL]) {
        completion(urls.first)
    }

    func documentPickerWasCancelled(_ controller: UIDocumentPickerViewController) {
        completion(nil)
    }
}

#endif
