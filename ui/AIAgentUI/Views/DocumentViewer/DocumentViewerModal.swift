//
//  DocumentViewerModal.swift
//  AIAgentUI
//
//  Created for Personal macOS AI Agent
//  Status: Active - Full screen immersive viewer with contextual chat
//

import SwiftUI

extension Notification.Name {
    static let documentSearchRequested = Notification.Name("documentSearchRequested")
}

/// Main modal for viewing a document and engaging in a scoped, persistent chat about it.
struct DocumentViewerModal: View {
    let url: URL
    let onDismiss: () -> Void
    
    @ObservedObject var appState: AppState = .shared
    
    @State private var searchQuery: String = ""
    @State private var searchDebounceTask: Task<Void, Never>?
    
    var body: some View {
        VStack(spacing: 0) {
            // Header: sits below safe area on iOS
            modalHeader
            
            // Content: fills remaining space
            ZStack(alignment: .bottom) {
                EnhancedDocumentPreviewer(url: url)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                
                // Chat overlay anchored to bottom
                DocumentChatOverlay(appState: appState, documentURL: url)
            }
        }
        #if os(iOS)
        .edgesIgnoringSafeArea(.bottom) // Let content extend to bottom, but respect top safe area
        #endif
    }
    
    private var modalHeader: some View {
        HStack(spacing: 8) {
            // Document Icon
            Image(systemName: url.isFileURL ? "doc.fill" : "globe")
                .foregroundColor(.primaryBlue)
                .font(.system(size: 16))
            
            // Flexible title
            Text(url.lastPathComponent)
                .font(.headline)
                .foregroundColor(.primary)
                .lineLimit(1)
                .truncationMode(.middle)
            
            Spacer()
            
            // Search Bar — hidden on small screens
            #if os(macOS)
            searchBar
                .frame(width: 220)
                .padding(.trailing, 4)
            #endif
            
            // Close Button
            Button(action: onDismiss) {
                Text("Done")
                    .fontWeight(.semibold)
            }
            .buttonStyle(.borderedProminent)
            .tint(.primaryBlue)
            .cornerRadius(ThemeConstants.cornerRadiusSmall)
        }
        .padding(.horizontal, ThemeConstants.spacingM)
        .padding(.vertical, ThemeConstants.spacingS)
        .background(.regularMaterial)
        .shadow(color: Color.black.opacity(0.15), radius: 8, x: 0, y: 4)
    }
    
    private var searchBar: some View {
        HStack(spacing: 6) {
            Image(systemName: "magnifyingglass")
                .foregroundColor(.secondary)
                .font(.system(size: 12, weight: .semibold))
            
            TextField("Search preview...", text: $searchQuery)
                .textFieldStyle(.plain)
                .font(.subheadline)
                .onSubmit {
                    performSearch(searchQuery)
                }
                .onChange(of: searchQuery) { newValue in
                    searchDebounceTask?.cancel()
                    searchDebounceTask = Task { @MainActor in
                        try? await Task.sleep(nanoseconds: 300_000_000)
                        guard !Task.isCancelled else { return }
                        performSearch(newValue)
                    }
                }
            
            if !searchQuery.isEmpty {
                Button(action: {
                    searchQuery = ""
                    performSearch("")
                }) {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundColor(.secondary)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 6)
        .background(Color.primary.opacity(0.05))
        .cornerRadius(8)
    }
    
    private func performSearch(_ query: String) {
        NotificationCenter.default.post(
            name: .documentSearchRequested,
            object: nil,
            userInfo: ["query": query]
        )
    }
}

#if DEBUG
struct DocumentViewerModal_Previews: PreviewProvider {
    static var previews: some View {
        DocumentViewerModal(url: URL(string: "https://apple.com")!) {}
    }
}
#endif
