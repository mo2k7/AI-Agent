//
//  MainContentAreaView.swift
//  AIAgentUI
//

import SwiftUI

// State wrapper for fullScreenCover to avoid timing/nil races
struct DocumentURLWrapper: Identifiable {
    let id = UUID()
    let url: URL
}

/// Isolated content area extracted from MainPanelView.
/// Prevents text streaming (ChatState mutations) from re-rendering the root app window.
struct MainContentAreaView: View {
    @ObservedObject var appState: AppState
    @ObservedObject var chatState: ChatState = .shared
    
    // State for the Document Viewer
    @State private var documentWrapper: DocumentURLWrapper?
    
    var body: some View {
        Group {
            if appState.isSessionHistoryLoading {
                SessionHistoryLoadingView()
            } else if chatState.messageRows.isEmpty {
                WelcomeView(
                    executionMode: appState.executionMode,
                    onSuggestionTapped: { text in
                        chatState.currentInput = text
                    }
                )
                .transition(.opacity)
            } else {
                MessageListView(
                    rows: chatState.messageRows,
                    sessionId: appState.activeSessionId,
                    hasOlderMessages: chatState.hasOlderMessages,
                    hasNewerMessages: chatState.hasNewerMessages,
                    isLoadingOlderMessages: chatState.isLoadingOlderMessages,
                    status: chatState.status,
                    statusDetail: chatState.statusDetail,
                    activeToolCall: chatState.currentToolCall,
                    browseNotice: chatState.activeBrowsePolicyNotice,
                    isCancellationInFlight: chatState.isCancellationInFlight,
                    onLoadOlderMessages: {
                        await appState.loadOlderMessages()
                    },
                    onRestoreLatestMessages: {
                        await appState.restoreLatestMessagesWindow()
                    }
                )
                .transition(.opacity)
            }
        }
        .environment(\.openURL, OpenURLAction { url in
            // Intercept link clicks and route to Document Viewer
            withAnimation(.spring(response: 0.3, dampingFraction: 0.8)) {
                documentWrapper = DocumentURLWrapper(url: url)
            }
            return .handled
        })
        #if os(iOS)
        // Native iOS full screen cover — covers everything including parent views.
        // Using 'item:' instead of 'isPresented:' guarantees the URL is non-nil upon evaluation, fixing the blank screen bug.
        .fullScreenCover(item: $documentWrapper) { wrapper in
            ZStack {
                Color(UIColor.systemBackground).edgesIgnoringSafeArea(.all)
                DocumentViewerModal(url: wrapper.url) {
                    documentWrapper = nil
                }
                .overlay(
                    SiriMeshAnimationView(cornerRadius: 0, lineWidth: 2.0)
                        .allowsHitTesting(false)
                )
            }
        }
        #else
        // macOS: floating overlay window
        .overlay(
            Group {
                if let wrapper = documentWrapper {
                    GeometryReader { geo in
                        ZStack {
                            Color.black.opacity(0.4)
                                .edgesIgnoringSafeArea(.all)
                                .onTapGesture {
                                    withAnimation(.spring(response: 0.3, dampingFraction: 0.8)) {
                                        documentWrapper = nil
                                    }
                                }
                            
                            DocumentViewerModal(url: wrapper.url) {
                                withAnimation(.spring(response: 0.3, dampingFraction: 0.8)) {
                                    documentWrapper = nil
                                }
                            }
                            .frame(
                                width: min(geo.size.width * 0.85, 1200),
                                height: min(geo.size.height * 0.85, 900)
                            )
                            .background(Color(NSColor.windowBackgroundColor))
                            .clipShape(RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusLarge, style: .continuous))
                            .overlay(
                                SiriMeshAnimationView(cornerRadius: ThemeConstants.cornerRadiusLarge, lineWidth: 2.0)
                                    .clipShape(RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusLarge + 2, style: .continuous))
                                    .padding(-2)
                                    .allowsHitTesting(false)
                            )
                            .shadow(color: Color.black.opacity(0.3), radius: 30, x: 0, y: 15)
                        }
                        .frame(width: geo.size.width, height: geo.size.height)
                    }
                    .edgesIgnoringSafeArea(.all)
                    .transition(.opacity.combined(with: .scale(scale: 0.95)))
                    .zIndex(100)
                }
            }
        )
        #endif
    }
}
