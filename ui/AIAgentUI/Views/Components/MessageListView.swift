//
//  MessageListView.swift
//  AIAgentUI
//
//  Extracted from ResponseBubble.swift
//  Status: Active - Scrollable message list with auto-scroll and pagination
//

import SwiftUI

// MARK: - Message List View

/// A scrollable list of message bubbles
struct MessageListView: View {
    private struct MessageListSignature: Equatable {
        let count: Int
        let firstID: UUID?
        let lastID: UUID?
    }

    private struct LiveResponseSignature: Equatable {
        let isStreaming: Bool
        let statusKey: String
        let statusDetail: String
        let toolName: String?
        let toolStatus: String?
        let browseMessage: String?
        let isCancellationInFlight: Bool
    }

    let rows: [MessageRowModel]
    let sessionId: String
    let hasOlderMessages: Bool
    let hasNewerMessages: Bool
    let isLoadingOlderMessages: Bool
    let status: AgentStatus
    let statusDetail: String
    let activeToolCall: ToolCall?
    let browseNotice: BrowsePolicyNotice?
    let isCancellationInFlight: Bool
    let onLoadOlderMessages: () async -> Void
    let onRestoreLatestMessages: () async -> Void

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var scrollProxy: ScrollViewProxy?
    @State private var pendingScrollTask: Task<Void, Never>?
    @State private var isPinnedToBottom = true
    @State private var pendingTopAnchorID: UUID?
    @State private var pendingTopAnchorBaseID: UUID?
    @State private var isNearTop = false
    @State private var isNearBottom = true
    @State private var hasPerformedInitialLayoutScroll = false
    @State private var pendingTopProbeTask: Task<Void, Never>?
    @State private var pendingBottomProbeTask: Task<Void, Never>?
    @State private var lastBottomProbeDate: Date = .distantPast
    @State private var lastTopProbeDate: Date = .distantPast
    private let bottomAnchorID = "message-list-bottom-anchor"
    private let bottomProbeID = "message-list-bottom-probe"
    private let topProbeID = "message-list-top-probe"

    var body: some View {
        GeometryReader { outerProxy in
            ScrollViewReader { proxy in
                ScrollView {
                    VStack(spacing: 0) {
                        Color.clear
                            .frame(height: 1)
                            .background(
                                GeometryReader { topProxy in
                                    Color.clear
                                        .preference(
                                            key: MessageListTopOffsetKey.self,
                                            value: topProxy.frame(in: .named("message-list-scroll")).minY
                                        )
                                }
                            )
                            .id(topProbeID)

                        if isLoadingOlderMessages {
                            HStack(spacing: ThemeConstants.spacingS) {
                                ProgressView()
                                    .controlSize(.small)
                                Text("Loading older messages...")
                                    .font(.caption)
                                    .foregroundColor(.textSecondary)
                            }
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, ThemeConstants.spacingXS)
                        }

                        ForEach(Array(rows.enumerated()), id: \.element.id) { index, row in
                            let isLast = row.id == rows.last?.id
                            ResponseBubble(
                                row: row,
                                animate: row.isStreaming,
                                isLatestStreamingRow: isLast && row.isStreaming,
                                liveStatus: isLast && row.isStreaming ? status : nil,
                                liveStatusDetail: isLast && row.isStreaming ? statusDetail : nil,
                                activeToolCall: isLast && row.isStreaming ? activeToolCall : nil,
                                browseNotice: isLast && row.isStreaming ? browseNotice : nil,
                                isCancellationInFlight: isLast && row.isStreaming
                                    ? isCancellationInFlight
                                    : false
                            )
                            .padding(.top, messageSpacing(at: index))
                            .transition(
                                reduceMotion
                                    ? .opacity
                                    : .asymmetric(
                                        insertion: .opacity.combined(with: .scale(scale: 0.98)),
                                        removal: .opacity
                                    )
                            )
                        }
                        Color.clear
                            .frame(height: 1)
                            .background(
                                GeometryReader { bottomProxy in
                                    Color.clear
                                        .preference(
                                            key: MessageListBottomOffsetKey.self,
                                            value: bottomProxy.frame(in: .named("message-list-scroll")).maxY
                                        )
                                }
                            )
                            .id(bottomProbeID)
                        Color.clear
                            .frame(height: 1)
                            .id(bottomAnchorID)
                    }
                    .padding(ThemeConstants.spacingM)
                }
                .coordinateSpace(name: "message-list-scroll")
                .onAppear {
                    scrollProxy = proxy
                    hasPerformedInitialLayoutScroll = false
                    if !rows.isEmpty {
                        scheduleInitialLayoutScroll()
                    }
                }
                .onDisappear {
                    pendingScrollTask?.cancel()
                    pendingTopProbeTask?.cancel()
                    pendingBottomProbeTask?.cancel()
                    pendingScrollTask = nil
                    pendingTopProbeTask = nil
                    pendingBottomProbeTask = nil
                    hasPerformedInitialLayoutScroll = false
                }
                .onChange(of: sessionId) { _, _ in
                    pendingTopAnchorID = nil
                    pendingTopAnchorBaseID = nil
                    hasPerformedInitialLayoutScroll = false
                    if !rows.isEmpty {
                        scheduleInitialLayoutScroll()
                    }
                }
                .onChange(of: rows.count) { _, _ in
                    guard !hasPerformedInitialLayoutScroll, !rows.isEmpty else { return }
                    scheduleInitialLayoutScroll()
                }
                .onChange(of: messageListSignature) { _, _ in
                    if let pendingTopAnchorID {
                        guard rows.first?.id != pendingTopAnchorBaseID else { return }
                        scheduleScrollToTopAnchor(pendingTopAnchorID)
                    } else if isPinnedToBottom {
                        scheduleScrollToBottom(animated: false)
                    }
                }
                .onChange(of: rows.last?.content) { _, _ in
                    guard isPinnedToBottom else { return }
                    scheduleScrollToBottom(animated: false)
                }
                .onChange(of: liveResponseSignature) { _, _ in
                    guard shouldStickToBottomForLiveUpdates else { return }
                    scheduleScrollToBottom(animated: false)
                }
                .onPreferenceChange(MessageListBottomOffsetKey.self) { bottomMaxY in
                    scheduleBottomProbeUpdate(bottomMaxY, viewportHeight: outerProxy.size.height)
                }
                .onPreferenceChange(MessageListTopOffsetKey.self) { topMinY in
                    scheduleTopProbeUpdate(topMinY)
                }
            }
        }
    }

    private func scrollToBottom(animated: Bool = true) {
        guard scrollProxy != nil else { return }
        if !animated || reduceMotion || isStreaming {
            scrollProxy?.scrollTo(bottomAnchorID, anchor: .bottom)
        } else {
            withAnimation(AnimationConstants.snappy) {
                scrollProxy?.scrollTo(bottomAnchorID, anchor: .bottom)
            }
        }
    }

    private var isStreaming: Bool {
        rows.last?.isStreaming == true
    }

    private var shouldStickToBottomForLiveUpdates: Bool {
        isStreaming && (isPinnedToBottom || isNearBottom)
    }

    private var messageListSignature: MessageListSignature {
        MessageListSignature(
            count: rows.count,
            firstID: rows.first?.id,
            lastID: rows.last?.id
        )
    }

    private var liveResponseSignature: LiveResponseSignature {
        LiveResponseSignature(
            isStreaming: isStreaming,
            statusKey: status.signatureKey,
            statusDetail: statusDetail,
            toolName: activeToolCall?.name,
            toolStatus: activeToolCall.map { String(describing: $0.status) },
            browseMessage: browseNotice?.message,
            isCancellationInFlight: isCancellationInFlight
        )
    }

    private func scheduleScrollToBottom(animated: Bool) {
        pendingScrollTask?.cancel()
        pendingScrollTask = Task { @MainActor in
            await Task.yield()
            scrollToBottom(animated: animated)
            pendingScrollTask = nil
        }
    }

    private func scheduleInitialLayoutScroll() {
        pendingScrollTask?.cancel()
        pendingScrollTask = Task { @MainActor in
            try? await Task.sleep(nanoseconds: 80_000_000)
            scrollToBottom(animated: false)
            hasPerformedInitialLayoutScroll = true
            pendingScrollTask = nil
        }
    }

    private func scheduleBottomProbeUpdate(_ bottomMaxY: CGFloat, viewportHeight: CGFloat) {
        // Throttle: skip if a probe ran within the last 80ms
        let now = Date()
        guard now.timeIntervalSince(lastBottomProbeDate) >= 0.08 else { return }
        pendingBottomProbeTask?.cancel()
        pendingBottomProbeTask = Task { @MainActor in
            try? await Task.sleep(nanoseconds: 80_000_000)
            guard !Task.isCancelled else { return }
            lastBottomProbeDate = Date()
            let distanceFromBottom = viewportHeight - bottomMaxY
            if distanceFromBottom >= -140 {
                isPinnedToBottom = true
            } else if distanceFromBottom <= -300 {
                isPinnedToBottom = false
            }
            let nearBottom = distanceFromBottom >= -320
            let shouldRestoreLatest = nearBottom
                && !isNearBottom
                && hasNewerMessages
                && !isLoadingOlderMessages
                && !rows.isEmpty
            isNearBottom = nearBottom
            if shouldRestoreLatest {
                await onRestoreLatestMessages()
            }
            pendingBottomProbeTask = nil
        }
    }

    /// Variable spacing between messages for visual rhythm:
    /// - user → assistant: 16px (tight connection between question and answer)
    /// - assistant → user: 24px (breathing room after long answers)
    /// - same role consecutive: 6px (grouped together)
    /// - first message: 0px
    private func messageSpacing(at index: Int) -> CGFloat {
        guard index > 0 else { return 0 }
        let currentRole = rows[index].role
        let previousRole = rows[index - 1].role
        if currentRole == previousRole { return 6 }
        if previousRole == .user && currentRole == .assistant { return 16 }
        return 24  // assistant → user
    }

    private func scheduleScrollToTopAnchor(_ rowID: UUID) {
        pendingScrollTask?.cancel()
        pendingScrollTask = Task { @MainActor in
            await Task.yield()
            scrollProxy?.scrollTo(rowID, anchor: .top)
            pendingTopAnchorID = nil
            pendingTopAnchorBaseID = nil
            pendingScrollTask = nil
        }
    }

    private func scheduleTopProbeUpdate(_ topMinY: CGFloat) {
        // Throttle: skip if a probe ran within the last 80ms
        let now = Date()
        guard now.timeIntervalSince(lastTopProbeDate) >= 0.08 else { return }
        pendingTopProbeTask?.cancel()
        pendingTopProbeTask = Task { @MainActor in
            try? await Task.sleep(nanoseconds: 80_000_000)
            guard !Task.isCancelled else { return }
            lastTopProbeDate = Date()
            let nearTop = topMinY >= -220
            let shouldLoad = nearTop
                && !isNearTop
                && !isStreaming
                && !isPinnedToBottom
                && !isNearBottom
                && hasOlderMessages
                && !isLoadingOlderMessages
                && !rows.isEmpty
            isNearTop = nearTop
            if shouldLoad {
                pendingTopAnchorID = rows.first?.id
                pendingTopAnchorBaseID = rows.first?.id
                await onLoadOlderMessages()
            }
            pendingTopProbeTask = nil
        }
    }
}

// MARK: - Preference Keys

private struct MessageListBottomOffsetKey: PreferenceKey {
    static let defaultValue: CGFloat = 0

    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) {
        value = nextValue()
    }
}

private struct MessageListTopOffsetKey: PreferenceKey {
    static let defaultValue: CGFloat = 0

    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) {
        value = nextValue()
    }
}

// MARK: - Empty State View

/// Shown when there are no messages
struct EmptyMessageView: View {
    var body: some View {
        VStack(spacing: ThemeConstants.spacingL) {
            Image(systemName: "bubble.left.and.bubble.right")
                .font(.system(size: 48))
                .foregroundColor(.textTertiary)

            Text("Start a conversation")
                .font(.headline)
                .foregroundColor(.textSecondary)

            Text("Type a message below to get started")
                .font(.subheadline)
                .foregroundColor(.textTertiary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }
}

struct SessionHistoryLoadingView: View {
    @State private var isAnimating = false

    var body: some View {
        VStack(spacing: ThemeConstants.spacingM) {
            ZStack {
                Circle()
                    .stroke(Color.statusConnecting.opacity(0.2), lineWidth: 4)
                    .frame(width: 28, height: 28)

                Circle()
                    .trim(from: 0.1, to: 0.85)
                    .stroke(Color.statusConnecting, style: StrokeStyle(lineWidth: 4, lineCap: .round))
                    .frame(width: 28, height: 28)
                    .rotationEffect(.degrees(isAnimating ? 360 : 0))
                    .animation(.linear(duration: 1.0).repeatForever(autoreverses: false), value: isAnimating)
            }

            Text("Loading session history...")
                .font(.subheadline)
                .foregroundColor(.textSecondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .onAppear {
            isAnimating = true
        }
    }
}
