//
//  MainInputAreaView.swift
//  AIAgentUI
//

import SwiftUI
import UniformTypeIdentifiers

/// Isolated input area extracted from MainPanelView.
/// Prevents text input typing and ChatState mutations from re-rendering the root app window.
struct MainInputAreaView: View {
    @ObservedObject var appState: AppState
    @ObservedObject var chatState: ChatState = .shared
    @Binding var isFileDropTargeted: Bool

    @State private var showFilePicker: Bool = false

    var body: some View {
        VStack(spacing: ThemeConstants.spacingXS) {
            // Error message if present
            if let error = appState.lastError, chatState.status.isError {
                errorBanner(error)
            }

            if isFileDropTargeted {
                HStack(spacing: ThemeConstants.spacingS) {
                    Image(systemName: "square.and.arrow.down")
                        .foregroundColor(.primaryBlue)
                    Text("Drop files to attach them to this request")
                        .font(.caption)
                        .foregroundColor(.textSecondary)
                    Spacer()
                }
                .padding(ThemeConstants.spacingS)
                .background(Color.primaryBlue.opacity(0.08))
                .clipShape(RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusSmall))
            }

            if !appState.droppedFilePaths.isEmpty {
                droppedFilesSection
            }

            InputContextBar(
                executionMode: appState.executionMode,
                status: chatState.status,
                browseProfile: appState.browseRestrictionProfile,
                accentColor: inputAccentColor
            )
            
            // Input field with mode-aware accent color and busy pulse
            InputField(
                text: $chatState.currentInput,
                placeholder: inputPlaceholderText,
                isDisabled: chatState.status.isBusy || appState.isSendingPrompt || appState.isSessionHistoryLoading,
                accentColor: inputAccentColor,
                isBusy: chatState.status.isBusy,
                onAttach: {
                    showFilePicker = true
                },
                onSubmit: {
                    Task {
                        await appState.sendPrompt()
                    }
                }
            )
        }
        .padding(ThemeConstants.spacingM)
        #if os(iOS)
        .padding(.bottom, ThemeConstants.spacingXS) // Extra clearance above the home indicator
        #endif
        .transaction { $0.animation = nil }
        .fileImporter(
            isPresented: $showFilePicker,
            allowedContentTypes: [.item],
            allowsMultipleSelection: true
        ) { result in
            switch result {
            case .success(let urls):
                appState.addDroppedFiles(urls: urls)
            case .failure(let error):
                appState.lastError = "Failed to select files: \(error.localizedDescription)"
            }
        }
    }

    /// Mode-aware accent color for the input border
    private var inputAccentColor: Color {
        appState.executionMode.config.themeColor
    }

    private var inputPlaceholderText: String {
        appState.executionMode.config.placeholderText
    }
    
    private var droppedFilesSection: some View {
        VStack(alignment: .leading, spacing: ThemeConstants.spacingXS) {
            HStack {
                Text("Attached Paths (\(appState.droppedFilePaths.count))")
                    .font(.caption)
                    .foregroundColor(.textSecondary)
                Spacer()
                Button("Clear") {
                    appState.clearDroppedFiles()
                }
                .font(.caption2)
                .buttonStyle(.plain)
                .foregroundColor(.statusError)
            }

            ForEach(appState.droppedFilePaths, id: \.self) { path in
                HStack(spacing: ThemeConstants.spacingXS) {
                    Image(systemName: "doc")
                        .foregroundColor(.primaryBlue)
                    Text(URL(fileURLWithPath: path).lastPathComponent)
                        .font(.caption2)
                        .lineLimit(1)
                        .foregroundColor(.textPrimary)
                    Spacer(minLength: ThemeConstants.spacingXS)
                    Text(path)
                        .font(.caption2)
                        .lineLimit(1)
                        .truncationMode(.middle)
                        .foregroundColor(.textTertiary)
                    Button(action: { appState.removeDroppedFile(path: path) }) {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundColor(.textTertiary)
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .padding(ThemeConstants.spacingS)
        .glassSurface(cornerRadius: ThemeConstants.cornerRadiusSmall)
    }
    
    private func errorBanner(_ message: String) -> some View {
        HStack(spacing: ThemeConstants.spacingS) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundColor(.statusError)
            
            Text(message)
                .font(.caption)
                .foregroundColor(.statusError)
            
            Spacer()
            
            Button(action: { appState.lastError = nil }) {
                Image(systemName: "xmark")
                    .font(.caption)
                    .foregroundColor(.statusError)
            }
            .buttonStyle(.plain)
        }
        .padding(ThemeConstants.spacingS)
        .background(Color.statusError.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusSmall))
        .overlay(
            RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusSmall)
                .stroke(Color.statusError.opacity(0.18), lineWidth: 0.8)
        )
    }
}
