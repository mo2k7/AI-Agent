//
//  ResponseBubble.swift
//  AIAgentUI
//
//  Created for Personal macOS AI Agent
//  Status: Active - Modern message rendering + streaming feedback
//

import SwiftUI

// Extracted to ResponseMarkdownRenderEngine.swift and PlanClarificationModels.swift

/// Displays a message bubble with style-aware markdown rendering and streaming animations.
struct ResponseBubble: View {

    // MARK: - Properties

    @ObservedObject var row: MessageRowModel

    /// Whether to animate the text (for streaming)
    var animate: Bool = false
    var isLatestStreamingRow: Bool = false
    var liveStatus: AgentStatus? = nil
    var liveStatusDetail: String? = nil
    var activeToolCall: ToolCall? = nil
    var browseNotice: BrowsePolicyNotice? = nil
    var isCancellationInFlight: Bool = false

    @AppStorage("animationsEnabled") private var animationsEnabled = true
    @AppStorage("responsePresentationStyle") private var responsePresentationStyleRaw = ResponsePresentationStyle.readablePro.rawValue
    @AppStorage("readableProHighContrastEnabled") private var readableProHighContrastEnabled = true
    @AppStorage("streamingAnimationStyle") private var streamingAnimationStyleRaw = StreamingAnimationStyle.waveReveal.rawValue
    @Environment(\.colorScheme) private var colorScheme

    // MARK: - State

    @State private var displayedText: String = ""
    @State private var parsedBlocks: [MarkdownBlock] = []
    @State private var waveProgress: CGFloat = 1.0
    @State private var luxeEventToken = 0

    // --- Wave-reveal: velocity tracker (rolling window + EMA) ---
    @State private var streamVelocity: CGFloat = 0.0      // EMA-smoothed 0…1
    @State private var waveChunkEvent: Int = 0
    @State private var velocityWindowStamps: [TimeInterval] = []
    @State private var velocityWindowChars: [Int] = []
    @State private var lastChunkDate: Date = .distantPast

    // --- Wave-reveal: text reveal mask ---
    @State private var revealTargetHeight: CGFloat = 0
    @State private var revealMaskHeight: CGFloat = 0
    @State private var fullTextHeight: CGFloat = 0

    // --- Wave-reveal: aurora rim phase tracking ---
    @State private var auroraPhase: WaveRevealPhase = .idle
    @State private var auroraDoneOpacity: CGFloat = 0
    @State private var clarificationSelections: [Int: String] = [:]
    @State private var clarificationCustomResponse: String = ""
    @State private var parseTask: Task<Void, Never>?

    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var message: Message {
        row.snapshot()
    }

    private var responsePresentationStyle: ResponsePresentationStyle {
        ResponsePresentationStyle(rawValue: responsePresentationStyleRaw) ?? .readablePro
    }

    private var streamingAnimationStyle: StreamingAnimationStyle {
        StreamingAnimationStyle(rawValue: streamingAnimationStyleRaw) ?? .waveReveal
    }

    // MARK: - Body

    var body: some View {
        // Chat-app style: user right-aligned, assistant left-aligned with accent bar
        HStack(alignment: .top, spacing: 0) {
            if message.role == .user {
                Spacer(minLength: 40)
            }

            if message.role == .assistant {
                // Left accent bar for assistant messages
                RoundedRectangle(cornerRadius: 1.5)
                    .fill(assistantAccentBarColor)
                    .frame(width: 3)
                    .padding(.vertical, 4)
                    .padding(.trailing, ThemeConstants.spacingS)
            }

            bubbleColumn

            if message.role == .assistant {
                Spacer(minLength: 0)
            }
        }
        .padding(.horizontal, ThemeConstants.spacingM)
        .padding(.vertical, ThemeConstants.spacingS)
        .frame(maxWidth: .infinity, alignment: message.role == .user ? .trailing : .leading)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(roleLabel): \(message.content)")
        .accessibilityHint(message.isStreaming ? Text("Message is still loading") : Text(""))
        .onAppear {
            if animate && message.isStreaming {
                animateTyping()
            } else {
                updateDisplayedText(message.content)
            }
        }
        .onChange(of: row.content) { _, newValue in
            if message.isStreaming {
                animateTyping(to: newValue)
            } else {
                updateDisplayedText(newValue)
            }
        }
        .onChange(of: row.isStreaming) { _, isStreaming in
            if !isStreaming {
                // Reset clarification selections when streaming finishes with new content
                clarificationSelections.removeAll()
                clarificationCustomResponse = ""
                updateDisplayedText(message.content)
                // Wave-reveal: transition aurora to .done → fade out
                if effectiveStreamingStyle == .waveReveal && !guardedStreamingEffects {
                    auroraPhase = .done
                    withAnimation(.easeOut(duration: 0.8)) {
                        auroraDoneOpacity = 0
                    }
                    // Reveal full text
                    withAnimation(.easeOut(duration: 0.2)) {
                        revealMaskHeight = fullTextHeight + 200
                    }
                    // Reset phase after fade completes
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.85) {
                        auroraPhase = .idle
                        auroraDoneOpacity = 0
                    }
                }
            }
        }
        .onChange(of: responsePresentationStyle) { _, _ in
            scheduleMarkdownParse(for: displayedText)
        }
        .onDisappear {
            parseTask?.cancel()
            parseTask = nil
        }
    }

    private var bubbleColumn: some View {
        VStack(alignment: message.role == .user ? .trailing : .leading, spacing: ThemeConstants.spacingXS) {
            if message.role == .assistant {
                HStack(spacing: 6) {
                    roleIcon

                    Text(roleLabel)
                        .font(.caption)
                        .foregroundColor(metaTextColor)

                    if isActiveStreamingRow {
                        BubbleThinkingIndicator(
                            status: liveStatus ?? .thinking,
                            statusDetail: liveStatusDetail ?? "",
                            activeToolCall: activeToolCall,
                            browseNotice: browseNotice,
                            guarded: guardedStreamingEffects,
                            canCancel: (liveStatus ?? .idle).isBusy,
                            isCancelling: isCancellationInFlight,
                            onCancel: {
                                Task { @MainActor in
                                    await AppState.shared.cancel()
                                }
                            }
                        )
                    }
                }
            } else {
                userRolePill
            }

            userScopedBubbleShell

            timestampLabel
        }
        .frame(
            maxWidth: message.role == .user ? 560 : .infinity,
            alignment: message.role == .user ? .trailing : .leading
        )
    }

    @ViewBuilder
    private var userScopedBubbleShell: some View {
        if message.role == .user {
            HStack(spacing: 0) {
                Spacer(minLength: 0)
                bubbleShell
                    .frame(maxWidth: userBubbleMaxWidth, alignment: .trailing)
            }
        } else {
            bubbleShell
        }
    }

    private var userRolePill: some View {
        Text("You")
            .font(.caption.weight(.semibold))
            .foregroundColor(Color.primaryBlue.opacity(0.92))
            .padding(.horizontal, 9)
            .padding(.vertical, 4)
            .background(
                Capsule()
                    .fill(Color.primaryBlue.opacity(0.11))
            )
    }

    private var timestampLabel: some View {
        Text(formattedTimestamp)
            .font(.caption2)
            .foregroundColor(metaTextColor.opacity(0.92))
            .frame(
                maxWidth: message.role == .user ? userBubbleMaxWidth : .infinity,
                alignment: message.role == .user ? .trailing : .leading
            )
    }

    private var bubbleShell: some View {
        messageContent
            .padding(ThemeConstants.spacingM)
            .background(bubbleBackground)
            .overlay(
                UnevenRoundedRectangle(
                    topLeadingRadius: ThemeConstants.cornerRadiusMedium,
                    bottomLeadingRadius: ThemeConstants.cornerRadiusMedium,
                    bottomTrailingRadius: message.role == .user ? 4 : ThemeConstants.cornerRadiusMedium,
                    topTrailingRadius: ThemeConstants.cornerRadiusMedium
                )
                    .stroke(bubbleBorderColor, lineWidth: bubbleBorderWidth)
            )
            .overlay {
                if isActiveStreamingRow && effectiveStreamingStyle == .waveReveal && !guardedStreamingEffects
                    && (message.isStreaming || auroraPhase == .done) {
                    AuroraRimOverlay(
                        velocity: streamVelocity,
                        phase: auroraPhase,
                        doneOpacity: auroraDoneOpacity,
                        reduceMotion: reduceMotion,
                        cornerRadius: ThemeConstants.cornerRadiusMedium
                    )
                    .allowsHitTesting(false)
                }
            }
            .clipShape(
                UnevenRoundedRectangle(
                    topLeadingRadius: ThemeConstants.cornerRadiusMedium,
                    bottomLeadingRadius: ThemeConstants.cornerRadiusMedium,
                    bottomTrailingRadius: message.role == .user ? 4 : ThemeConstants.cornerRadiusMedium,
                    topTrailingRadius: ThemeConstants.cornerRadiusMedium
                )
            )
            .shadow(
                color: bubbleShadowColor,
                radius: bubbleShadowRadius,
                x: 0,
                y: bubbleShadowRadius > 0 ? 4 : 0
            )
    }

    // MARK: - Assistant Accent Bar Color

    private var assistantAccentBarColor: Color {
        if isActiveStreamingRow {
            switch liveStatus ?? .thinking {
            case .streaming:
                return .statusStreaming
            case .callingTool, .executingPlan, .awaitingApproval, .capturingScreen:
                return .statusToolCall
            case .thinking, .planning:
                return .statusThinking
            default:
                return .secondaryBlue.opacity(0.4)
            }
        }
        return .secondaryBlue.opacity(0.4)
    }

    // MARK: - Subviews

    @ViewBuilder
    private var roleIcon: some View {
        // Only shown for assistant messages — user messages are identified by position
        Image(systemName: "brain")
            .font(.system(size: 14))
            .foregroundColor(.secondaryBlue)
            .frame(width: 24, height: 24)
            .background(
                Circle()
                    .fill(
                        RadialGradient(
                            colors: [Color.secondaryBlue.opacity(0.15), Color.secondaryBlue.opacity(0.05)],
                            center: .center,
                            startRadius: 0,
                            endRadius: 16
                        )
                    )
            )
    }

    @ViewBuilder
    private var messageContent: some View {
        if let clarificationPayload = planClarificationPayload {
            planClarificationView(payload: clarificationPayload)
        } else if displayedText.isEmpty && isActiveStreamingRow {
            VStack(alignment: .leading, spacing: ThemeConstants.spacingS) {
                StreamingPlaceholderCard(
                    title: streamingStatusTitle,
                    detail: streamingStatusSubtitle,
                    activeToolCall: activeToolCall,
                    guarded: guardedStreamingEffects
                )
            }
        } else {
            VStack(alignment: .leading, spacing: blockSpacing) {
                // Text content — rendered fully, masked by reveal animation
                // when wave-reveal is active during streaming.
                textBlocks
                    .background {
                        if !showPlainTextStreamingContent {
                            textHeightReader
                        }
                    }
                    .modifier(
                        WaveRevealMaskModifier(
                            isActive: isActiveStreamingRow
                                && effectiveStreamingStyle == .waveReveal
                                && !reduceMotion
                                && !guardedStreamingEffects,
                            maskHeight: revealMaskHeight,
                            featherSize: 22
                        )
                    )
                    // Prevent implicit layout animation from text changes
                    .transaction { txn in txn.animation = nil }

                // Bottom streaming indicator — only for non-waveReveal styles
                if isActiveStreamingRow && (effectiveStreamingStyle != .waveReveal || guardedStreamingEffects) {
                    streamingFeedback
                        .padding(.top, 4)
                }

                if message.role == .assistant, let inlineToolCall = message.toolCall {
                    InlineToolCallChip(toolCall: inlineToolCall)
                        .padding(.top, 6)
                }
            }
            .frame(maxWidth: messageContentMaxWidth, alignment: .leading)
            .textSelection(.enabled)
            .tint(.secondaryBlue)
        }
    }

    private func planClarificationView(payload: PlanClarificationPayload) -> some View {
        VStack(alignment: .leading, spacing: ThemeConstants.spacingS) {
            if !payload.intro.isEmpty {
                Text(payload.intro)
                    .font(paragraphFont)
                    .foregroundColor(primaryTextColor)
                    .lineSpacing(paragraphLineSpacing)
                    .fixedSize(horizontal: false, vertical: true)
            }

            ForEach(payload.questions) { question in
                VStack(alignment: .leading, spacing: ThemeConstants.spacingXS) {
                    Text("Q\(question.number). \(question.prompt)")
                        .font(.system(.subheadline, design: .rounded).weight(.semibold))
                        .foregroundColor(primaryTextColor)
                        .fixedSize(horizontal: false, vertical: true)

                    ForEach(question.options) { option in
                        let isSelected = clarificationSelections[question.number] == option.key
                        Button(action: {
                            let hadSelection = clarificationSelections[question.number] != nil
                            clarificationSelections[question.number] = option.key
                            let finalQuestionNumber = payload.questions.map(\.number).max() ?? question.number
                            let hasCompletedAllSelections =
                                clarificationSelections.count == payload.questions.count
                            if question.number == finalQuestionNumber
                                && hasCompletedAllSelections
                                && !hadSelection
                                && (liveStatus ?? .idle).canSubmit {
                                Task {
                                    await AppState.shared.submitPlanClarificationResponse(
                                        composeClarificationAnswer(payload)
                                    )
                                }
                            }
                        }) {
                            HStack(spacing: ThemeConstants.spacingXS) {
                                Text("\(option.key)) \(option.text)")
                                    .font(.system(.caption, design: .rounded))
                                    .foregroundColor(isSelected ? .white : primaryTextColor)
                                    .fixedSize(horizontal: false, vertical: true)
                                Spacer(minLength: ThemeConstants.spacingXS)
                                if isSelected {
                                    Image(systemName: "checkmark.circle.fill")
                                        .font(.caption)
                                        .foregroundColor(.white)
                                }
                            }
                            .padding(.horizontal, ThemeConstants.spacingS)
                            .padding(.vertical, ThemeConstants.spacingXS)
                            .background(
                                RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusSmall)
                                    .fill(isSelected ? Color.primaryBlue : Color.cardBackground.opacity(0.7))
                            )
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.vertical, 2)
            }

            TextField("Optional custom details (free-form)", text: $clarificationCustomResponse)
                .textFieldStyle(.roundedBorder)

            HStack(spacing: ThemeConstants.spacingS) {
                Button("Send Answers") {
                    Task {
                        await AppState.shared.submitPlanClarificationResponse(composeClarificationAnswer(payload))
                    }
                }
                .buttonStyle(.borderedProminent)
                .disabled(clarificationSelections.count < payload.questions.count || (liveStatus ?? .idle).isBusy)

                Button("Send Custom") {
                    let custom = clarificationCustomResponse.trimmingCharacters(in: .whitespacesAndNewlines)
                    guard !custom.isEmpty else { return }
                    Task {
                        await AppState.shared.submitPlanClarificationResponse(custom)
                    }
                }
                .buttonStyle(.bordered)
                .disabled(
                    clarificationCustomResponse.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                        || (liveStatus ?? .idle).isBusy
                )
            }
        }
        .frame(maxWidth: messageContentMaxWidth, alignment: .leading)
    }

    private func composeClarificationAnswer(_ payload: PlanClarificationPayload) -> String {
        var parts: [String] = []
        for question in payload.questions {
            guard let selectedKey = clarificationSelections[question.number] else {
                continue
            }
            parts.append("Q\(question.number):\(selectedKey)")
        }

        let selectedSummary = parts.joined(separator: ", ")
        let custom = clarificationCustomResponse.trimmingCharacters(in: .whitespacesAndNewlines)
        if custom.isEmpty {
            return selectedSummary
        }
        if selectedSummary.isEmpty {
            return custom
        }
        return "\(selectedSummary)\nNotes: \(custom)"
    }

    /// The rendered text blocks, extracted so the reveal mask can wrap them.
    @ViewBuilder
    private var textBlocks: some View {
        if showPlainTextStreamingContent || parsedBlocks.isEmpty {
            Text(displayedText)
                .font(paragraphFont)
                .foregroundColor(primaryTextColor)
                .lineSpacing(paragraphLineSpacing)
                .fixedSize(horizontal: false, vertical: true)
        } else {
            VStack(alignment: .leading, spacing: blockSpacing) {
                ForEach(Array(parsedBlocks.enumerated()), id: \.element.id) { index, block in
                    renderBlock(
                        block,
                        isLeadParagraph: message.role == .assistant
                            && index == 0
                            && isLeadParagraphBlock(block)
                    )
                }
            }
        }
    }

    /// Invisible GeometryReader to track the full rendered text height.
    private var textHeightReader: some View {
        GeometryReader { proxy in
            Color.clear
                .preference(key: TextHeightPreferenceKey.self, value: proxy.size.height)
        }
        .onPreferenceChange(TextHeightPreferenceKey.self) { newHeight in
            fullTextHeight = newHeight
            if isActiveStreamingRow && effectiveStreamingStyle == .waveReveal && !guardedStreamingEffects {
                animateRevealMask(to: newHeight)
            } else {
                // Not streaming — show everything instantly
                revealMaskHeight = newHeight
                revealTargetHeight = newHeight
            }
        }
    }

    @ViewBuilder
    private func renderBlock(
        _ block: MarkdownBlock,
        isLeadParagraph: Bool = false
    ) -> some View {
        switch block.kind {
        case .heading(let level, let text):
            HStack(alignment: .center, spacing: ThemeConstants.spacingS) {
                if responsePresentationStyle != .denseTechnical {
                    RoundedRectangle(cornerRadius: 3)
                        .fill(Color.secondaryBlue.opacity(0.65))
                        .frame(width: 3, height: headingAccentHeight(level: level))
                }
                Text(inlineMarkdown(text))
                    .font(headingFont(level: level))
                    .fontWeight(.semibold)
                    .foregroundColor(primaryTextColor)
                    .lineLimit(nil)
                    .fixedSize(horizontal: false, vertical: true)
            }
        case .paragraph(let text):
            paragraphView(text, isLeadParagraph: isLeadParagraph)
        case .bullet(let items):
            VStack(alignment: .leading, spacing: bulletItemSpacing) {
                ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                    if responsePresentationStyle == .readablePro {
                        HStack(alignment: .top, spacing: 10) {
                            Circle()
                                .fill(Color.secondaryBlue.opacity(0.95))
                                .frame(width: 6, height: 6)
                                .padding(.top, 7)
                            Text(inlineMarkdown(item))
                                .font(paragraphFont)
                                .foregroundColor(primaryTextColor)
                                .lineSpacing(paragraphLineSpacing)
                                .lineLimit(nil)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        .padding(.leading, 4)
                        .padding(.vertical, 2)
                    } else {
                        HStack(alignment: .top, spacing: ThemeConstants.spacingS) {
                            Image(systemName: "checkmark.circle.fill")
                                .font(.system(size: 11, weight: .semibold))
                                .foregroundColor(.secondaryBlue)
                                .padding(.top, 2)
                            Text(inlineMarkdown(item))
                                .font(paragraphFont)
                                .foregroundColor(primaryTextColor)
                                .lineSpacing(paragraphLineSpacing)
                                .lineLimit(nil)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        .padding(.horizontal, 10)
                        .padding(.vertical, 7)
                        .background(
                            RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusSmall)
                                .fill(listRowBackground.opacity(0.85))
                        )
                    }
                }
            }
        case .numbered(let items):
            VStack(alignment: .leading, spacing: bulletItemSpacing) {
                ForEach(Array(items.enumerated()), id: \.offset) { index, item in
                    if responsePresentationStyle == .readablePro {
                        HStack(alignment: .top, spacing: 10) {
                            Text("\(index + 1).")
                                .font(.system(.body, design: .rounded))
                                .fontWeight(.semibold)
                                .foregroundColor(.secondaryBlue)
                                .frame(minWidth: 24, alignment: .leading)
                                .padding(.top, 1)
                            Text(inlineMarkdown(item))
                                .font(paragraphFont)
                                .foregroundColor(primaryTextColor)
                                .lineSpacing(paragraphLineSpacing)
                                .lineLimit(nil)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        .padding(.leading, 2)
                        .padding(.vertical, 2)
                    } else {
                        HStack(alignment: .top, spacing: ThemeConstants.spacingS) {
                            Text("\(index + 1)")
                                .font(numberBadgeFont)
                                .fontWeight(.semibold)
                                .foregroundColor(.white)
                                .frame(width: 20, height: 20)
                                .background(
                                    Circle()
                                        .fill(
                                            LinearGradient(
                                                colors: [Color.secondaryBlue, Color.primaryBlue],
                                                startPoint: .topLeading,
                                                endPoint: .bottomTrailing
                                            )
                                        )
                                )
                                .padding(.top, 1)
                            Text(inlineMarkdown(item))
                                .font(paragraphFont)
                                .foregroundColor(primaryTextColor)
                                .lineSpacing(paragraphLineSpacing)
                                .lineLimit(nil)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        .padding(.horizontal, 10)
                        .padding(.vertical, 7)
                        .background(
                            RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusSmall)
                                .fill(listRowBackground.opacity(0.85))
                        )
                    }
                }
            }
        case .quote(let text):
            HStack(alignment: .top, spacing: ThemeConstants.spacingS) {
                RoundedRectangle(cornerRadius: 2)
                    .fill(Color.secondaryBlue.opacity(0.55))
                    .frame(width: 3)
                Text(inlineMarkdown(text))
                    .font(paragraphFont.italic())
                    .foregroundColor(secondaryTextColor)
                    .lineSpacing(paragraphLineSpacing)
                    .lineLimit(nil)
                    .fixedSize(horizontal: false, vertical: true)
            }
        case .code(let code):
            ScrollView(.horizontal, showsIndicators: false) {
                Text(code)
                    .font(.system(.callout, design: .monospaced))
                    .foregroundColor(primaryTextColor)
                    .lineSpacing(3)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .padding(ThemeConstants.spacingS)
            .background(codeBackground)
            .clipShape(RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusSmall))
        case .table(let headers, let rows):
            VStack(spacing: 0) {
                HStack(spacing: 0) {
                    ForEach(headers.indices, id: \.self) { i in
                        Text(inlineMarkdown(headers[i]))
                            .font(paragraphFont.weight(.semibold))
                            .foregroundColor(primaryTextColor)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 6)
                    }
                }
                .background(Color.secondaryBlue.opacity(0.12))
                Divider()
                ForEach(rows.indices, id: \.self) { rowIdx in
                    HStack(spacing: 0) {
                        let row = rows[rowIdx]
                        ForEach(row.indices, id: \.self) { colIdx in
                            Text(inlineMarkdown(row[colIdx]))
                                .font(paragraphFont)
                                .foregroundColor(primaryTextColor)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding(.horizontal, 8)
                                .padding(.vertical, 5)
                        }
                    }
                    .background(rowIdx % 2 == 1 ? Color.textPrimary.opacity(0.02) : Color.clear)
                    if rowIdx < rows.count - 1 {
                        Divider().opacity(0.5)
                    }
                }
            }
            .clipShape(RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusSmall))
            .overlay(
                RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusSmall)
                    .stroke(Color.glassStroke.opacity(0.5), lineWidth: 0.5)
            )
        case .image:
            EmptyView()
        }
    }

    @ViewBuilder
    private var streamingFeedback: some View {
        ZStack(alignment: .leading) {
            if guardedStreamingEffects {
                StreamingStatusFooter(
                    title: streamingStatusTitle,
                    detail: guardedStreamingEffects ? "Stable update mode for long output" : streamingStatusSubtitle,
                    guarded: true,
                    velocity: streamVelocity
                )
            } else {
                switch effectiveStreamingStyle {
                case .waveReveal:
                    EmptyView() // handled by aurora rim overlay + reveal mask
                case .typewriterLuxe:
                    LuxeStreamingIndicator(
                        eventToken: luxeEventToken,
                        title: streamingStatusTitle,
                        detail: streamingStatusSubtitle
                    )
                case .minimalMotion:
                    StreamingStatusFooter(
                        title: streamingStatusTitle,
                        detail: streamingStatusSubtitle,
                        guarded: false,
                        velocity: streamVelocity
                    )
                }
            }
        }
        // Keep a stable row height while switching animation modes so the
        // surrounding chat container does not jump.
        .frame(
            maxWidth: .infinity,
            minHeight: streamingIndicatorHeight,
            maxHeight: streamingIndicatorHeight,
            alignment: .leading
        )
        .id(effectiveStreamingStyle.rawValue)
        .transaction { txn in
            txn.animation = nil
        }
    }

    private var bubbleBackground: some View {
        Group {
            if message.role == .user {
                LinearGradient(
                    colors: [
                        Color.primaryBlue.opacity(0.16),
                        Color.primaryBlue.opacity(0.11),
                    ],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
            } else {
                switch responsePresentationStyle {
                case .readablePro:
                    Group {
                        if readableProHighContrastActive {
                            if colorScheme == .dark {
                                Color(hex: "1E242C")
                            } else {
                                Color.white
                            }
                        } else {
                            Color.cardBackground
                        }
                    }
                case .glassEditorial:
                    LinearGradient(
                        colors: [
                            Color.cardBackground.opacity(0.95),
                            Color.secondaryBlue.opacity(0.08),
                            Color.primaryBlue.opacity(0.06),
                        ],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                case .denseTechnical:
                    Color.panelBackground.opacity(0.93)
                }
            }
        }
    }

    @ViewBuilder
    private func paragraphView(_ text: String, isLeadParagraph: Bool) -> some View {
        if isCautionParagraph(text) {
            cautionParagraphView(text, isLeadParagraph: isLeadParagraph)
        } else {
            standardParagraphView(text, isLeadParagraph: isLeadParagraph)
        }
    }

    private func standardParagraphView(_ text: String, isLeadParagraph: Bool) -> some View {
        Text(inlineMarkdown(text))
            .font(isLeadParagraph ? leadParagraphFont : paragraphFont)
            .foregroundColor(primaryTextColor)
            .lineSpacing(isLeadParagraph ? leadParagraphLineSpacing : paragraphLineSpacing)
            .lineLimit(nil)
            .fixedSize(horizontal: false, vertical: true)
            .padding(isLeadParagraph ? EdgeInsets(top: 10, leading: 12, bottom: 10, trailing: 12) : EdgeInsets())
            .background(
                Group {
                    if isLeadParagraph {
                        RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusSmall)
                            .fill(leadParagraphBackground)
                    }
                }
            )
    }

    private func cautionParagraphView(_ text: String, isLeadParagraph: Bool) -> some View {
        Text(inlineMarkdown(text))
            .font(isLeadParagraph ? leadParagraphFont : paragraphFont)
            .foregroundColor(cautionTextColor)
            .lineSpacing(isLeadParagraph ? leadParagraphLineSpacing : paragraphLineSpacing)
            .lineLimit(nil)
            .fixedSize(horizontal: false, vertical: true)
            .padding(cautionParagraphPadding(isLeadParagraph: isLeadParagraph))
            .background(
                RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusSmall)
                    .fill(cautionParagraphBackground)
            )
            .overlay(
                RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusSmall)
                    .stroke(cautionParagraphBorder, lineWidth: 1)
            )
    }

    private var bubbleBorderColor: Color {
        if message.role == .user {
            return Color.primaryBlue.opacity(0.18)
        }
        switch responsePresentationStyle {
        case .readablePro:
            if readableProHighContrastActive {
                return colorScheme == .dark
                    ? Color.white.opacity(0.16)
                    : Color.black.opacity(0.10)
            }
            return Color.glassStroke.opacity(0.45)
        case .glassEditorial:
            return Color.secondaryBlue.opacity(0.35)
        case .denseTechnical:
            return Color.glassStroke.opacity(0.58)
        }
    }

    private var bubbleBorderWidth: CGFloat {
        if message.role == .user { return 0.8 }
        return responsePresentationStyle == .glassEditorial ? 1.05 : 0.85
    }

    private var bubbleShadowColor: Color {
        guard message.role == .assistant else { return .clear }
        switch responsePresentationStyle {
        case .readablePro:
            if readableProHighContrastActive {
                return colorScheme == .dark ? .black.opacity(0.22) : .black.opacity(0.08)
            }
            return .black.opacity(0.06)
        case .glassEditorial:
            return .secondaryBlue.opacity(0.16)
        case .denseTechnical:
            return .black.opacity(0.04)
        }
    }

    private var bubbleShadowRadius: CGFloat {
        guard message.role == .assistant else { return 0 }
        switch responsePresentationStyle {
        case .readablePro:
            return readableProHighContrastActive ? 6 : 4
        case .glassEditorial:
            return 8
        case .denseTechnical:
            return 2
        }
    }

    private var codeBackground: some View {
        Group {
            switch responsePresentationStyle {
            case .readablePro:
                Color.inputBackground.opacity(0.72)
            case .glassEditorial:
                LinearGradient(
                    colors: [
                        Color.inputBackground.opacity(0.82),
                        Color.secondaryBlue.opacity(0.08),
                    ],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
            case .denseTechnical:
                Color.inputBackground.opacity(0.92)
            }
        }
    }

    private var leadParagraphBackground: some ShapeStyle {
        switch responsePresentationStyle {
        case .readablePro:
            if readableProHighContrastActive {
                return AnyShapeStyle(
                    colorScheme == .dark
                        ? Color.secondaryBlue.opacity(0.20)
                        : Color.secondaryBlue.opacity(0.12)
                )
            }
            return AnyShapeStyle(Color.secondaryBlue.opacity(0.08))
        case .glassEditorial:
            return AnyShapeStyle(
                LinearGradient(
                    colors: [
                        Color.secondaryBlue.opacity(0.16),
                        Color.primaryBlue.opacity(0.10),
                    ],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
            )
        case .denseTechnical:
            return AnyShapeStyle(Color.inputBackground.opacity(0.9))
        }
    }

    private var cautionParagraphBackground: some ShapeStyle {
        switch responsePresentationStyle {
        case .readablePro:
            return AnyShapeStyle(
                colorScheme == .dark
                    ? Color.warning.opacity(0.16)
                    : Color.warning.opacity(0.10)
            )
        case .glassEditorial:
            return AnyShapeStyle(
                LinearGradient(
                    colors: [
                        Color.warning.opacity(0.16),
                        Color.warning.opacity(0.08),
                    ],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
            )
        case .denseTechnical:
            return AnyShapeStyle(Color.warning.opacity(0.08))
        }
    }

    private var cautionParagraphBorder: Color {
        switch responsePresentationStyle {
        case .readablePro:
            return Color.warning.opacity(colorScheme == .dark ? 0.34 : 0.26)
        case .glassEditorial:
            return Color.warning.opacity(0.28)
        case .denseTechnical:
            return Color.warning.opacity(0.22)
        }
    }

    private var listRowBackground: Color {
        switch responsePresentationStyle {
        case .readablePro:
            return Color.secondaryBlue.opacity(0.09)
        case .glassEditorial:
            return Color.secondaryBlue.opacity(0.12)
        case .denseTechnical:
            return Color.inputBackground.opacity(0.72)
        }
    }

    // MARK: - Typographic Tokens

    private var blockSpacing: CGFloat {
        switch responsePresentationStyle {
        case .readablePro:
            return 13
        case .glassEditorial:
            return 12
        case .denseTechnical:
            return 7
        }
    }

    private var bulletItemSpacing: CGFloat {
        switch responsePresentationStyle {
        case .readablePro:
            return 8
        case .glassEditorial:
            return 7
        case .denseTechnical:
            return 4
        }
    }

    private var paragraphLineSpacing: CGFloat {
        switch responsePresentationStyle {
        case .readablePro:
            return 6
        case .glassEditorial:
            return 5
        case .denseTechnical:
            return 2
        }
    }

    private var leadParagraphLineSpacing: CGFloat {
        switch responsePresentationStyle {
        case .readablePro:
            return 5
        case .glassEditorial:
            return 6
        case .denseTechnical:
            return 3
        }
    }

    private var paragraphFont: Font {
        switch responsePresentationStyle {
        case .readablePro:
            return .system(.body, design: .rounded)
        case .glassEditorial:
            return .system(.body, design: .rounded)
        case .denseTechnical:
            return .system(.body, design: .monospaced)
        }
    }

    private var leadParagraphFont: Font {
        switch responsePresentationStyle {
        case .readablePro:
            return .system(.title3, design: .rounded).weight(.semibold)
        case .glassEditorial:
            return .system(.title3, design: .rounded).weight(.semibold)
        case .denseTechnical:
            return .system(.body, design: .monospaced).weight(.medium)
        }
    }

    private var numberBadgeFont: Font {
        switch responsePresentationStyle {
        case .denseTechnical:
            return .system(.callout, design: .monospaced)
        default:
            return .callout
        }
    }

    private func headingFont(level: Int) -> Font {
        let normalized = max(1, min(level, 3))
        switch normalized {
        case 1:
            return responsePresentationStyle == .denseTechnical ? .headline : .title3
        case 2:
            return .headline
        default:
            return .subheadline
        }
    }

    private func headingAccentHeight(level: Int) -> CGFloat {
        switch max(1, min(level, 3)) {
        case 1:
            return 24
        case 2:
            return 20
        default:
            return 16
        }
    }

    // MARK: - Computed Properties

    private var roleLabel: String {
        switch message.role {
        case .user: return "You"
        case .assistant: return "AI Agent"
        case .system: return "System"
        }
    }

    private var formattedTimestamp: String {
        Self.timestampFormatter.string(from: message.timestamp)
    }

    private var effectiveStreamingStyle: StreamingAnimationStyle {
        guard animationsEnabled else { return .minimalMotion }
        return streamingAnimationStyle
    }

    private var streamingIndicatorHeight: CGFloat {
        38
    }

    private var messageContentMaxWidth: CGFloat? {
        if message.role == .user {
            return userBubbleContentMaxWidth
        }
        switch responsePresentationStyle {
        case .readablePro:
            return 760
        case .glassEditorial, .denseTechnical:
            return nil
        }
    }

    private var userBubbleMaxWidth: CGFloat {
        540
    }

    private var userBubbleContentMaxWidth: CGFloat {
        500
    }

    private var primaryTextColor: Color {
        if readableProHighContrastActive {
            return colorScheme == .dark ? Color.white.opacity(0.98) : Color.black.opacity(0.92)
        }
        return .textPrimary
    }

    private var cautionTextColor: Color {
        switch responsePresentationStyle {
        case .readablePro:
            return colorScheme == .dark ? Color.warning.opacity(0.96) : Color.warning.opacity(0.92)
        case .glassEditorial:
            return colorScheme == .dark ? Color.warning.opacity(0.94) : Color.warning.opacity(0.88)
        case .denseTechnical:
            return colorScheme == .dark ? Color.warning.opacity(0.90) : Color.warning.opacity(0.82)
        }
    }

    private var secondaryTextColor: Color {
        if readableProHighContrastActive {
            return colorScheme == .dark ? Color.white.opacity(0.84) : Color.black.opacity(0.74)
        }
        return .textSecondary
    }

    private var metaTextColor: Color {
        if readableProHighContrastActive {
            return colorScheme == .dark ? Color.white.opacity(0.70) : Color.black.opacity(0.62)
        }
        return .textTertiary
    }

    private var readableProHighContrastActive: Bool {
        responsePresentationStyle == .readablePro
            && readableProHighContrastEnabled
    }

    private var isActiveStreamingRow: Bool {
        message.role == .assistant
            && message.isStreaming
            && isLatestStreamingRow
    }

    private var guardedStreamingEffects: Bool {
        guard isActiveStreamingRow else { return false }
        return message.content.count > 8_000
            || streamVelocity > 0.72
            || isCancellationInFlight
    }

    private var showPlainTextStreamingContent: Bool {
        isActiveStreamingRow && message.isStreaming
    }

    private var streamingStatusTitle: String {
        switch liveStatus ?? .thinking {
        case .thinking:
            return "Thinking"
        case .planning:
            return "Planning"
        case .awaitingApproval:
            return "Awaiting approval"
        case .executingPlan:
            return "Executing plan"
        case .streaming:
            return "Generating"
        case .callingTool:
            return "Using tool"
        case .capturingScreen:
            return "Capturing screen"
        case .planReady:
            return "Plan ready"
        case .complete:
            return "Finishing"
        case .error:
            return "Recovering"
        case .idle:
            return "Preparing"
        case .connecting:
            return "Connecting"
        }
    }

    private var streamingStatusSubtitle: String {
        let trimmed = (liveStatusDetail ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        if !trimmed.isEmpty {
            return trimmed
        }
        if let activeToolCall = activeToolCall {
            return "Working with \(activeToolCall.name)"
        }
        return "Building the response"
    }

    private var planClarificationPayload: PlanClarificationPayload? {
        guard message.role == .assistant else { return nil }
        guard !message.isStreaming else { return nil }
        return Self.parsePlanClarificationPayload(displayedText)
    }

    // MARK: - Animation / Parsing

    private func animateTyping() {
        animateTyping(to: message.content)
    }

    private func animateTyping(to target: String) {
        // Backend already streams chunk-wise text; animate the presentation, not token generation.
        updateDisplayedText(target)
    }

    private func updateDisplayedText(_ text: String) {
        let previousCount = displayedText.count

        var txn = Transaction()
        txn.animation = nil
        withTransaction(txn) {
            displayedText = text
        }
        scheduleMarkdownParse(for: text)

        if isActiveStreamingRow && text.count > previousCount {
            let charDelta = text.count - previousCount
            let now = Date().timeIntervalSinceReferenceDate

            // --- Rolling window velocity (spec §B) ---
            velocityWindowStamps.append(now)
            velocityWindowChars.append(charDelta)

            // Trim window to ~0.8s
            let windowStart = now - 0.8
            while let first = velocityWindowStamps.first, first < windowStart {
                velocityWindowStamps.removeFirst()
                velocityWindowChars.removeFirst()
            }

            let windowChars = velocityWindowChars.reduce(0, +)
            let windowDuration = (velocityWindowStamps.last ?? now) - (velocityWindowStamps.first ?? now)

            let vRaw: CGFloat
            if windowDuration > 0.01 {
                // Approximate tokens ≈ chars / 4
                let approxTokensPerSec = CGFloat(windowChars) / 4.0 / CGFloat(windowDuration)
                // VMAX ~ 40 tokens/sec
                vRaw = min(approxTokensPerSec / 40.0, 1.0)
            } else {
                vRaw = min(CGFloat(charDelta) / 4.0 / 40.0, 1.0)
            }

            // EMA smooth: lerp(prev, raw, 0.15)
            streamVelocity = streamVelocity * 0.85 + vRaw * 0.15

            lastChunkDate = Date()
            waveChunkEvent += 1

            // Aurora phase: start streaming on first chunk
            if auroraPhase != .streaming {
                auroraPhase = .streaming
                auroraDoneOpacity = 1.0
            }

            if !guardedStreamingEffects {
                triggerStreamingFeedback()
            }
        }
    }

    private func scheduleMarkdownParse(for text: String) {
        parseTask?.cancel()
        if isActiveStreamingRow && message.isStreaming {
            parsedBlocks = []
            parseTask = nil
            return
        }
        let style = responsePresentationStyle
        parseTask = Task {
            let blocks = await ResponseMarkdownRenderEngine.shared.parse(text: text, style: style)
            guard !Task.isCancelled else { return }
            await MainActor.run {
                guard displayedText == text else { return }
                var txn = Transaction()
                txn.animation = nil
                withTransaction(txn) {
                    parsedBlocks = blocks
                }
                parseTask = nil
            }
        }
    }

    /// Animate the reveal mask height toward the new target.
    private func animateRevealMask(to height: CGFloat) {
        revealTargetHeight = height
        guard !reduceMotion else {
            revealMaskHeight = height
            return
        }
        withAnimation(.easeOut(duration: 0.18)) {
            revealMaskHeight = height
        }
    }

    private func triggerStreamingFeedback() {
        guard !guardedStreamingEffects else { return }
        switch effectiveStreamingStyle {
        case .waveReveal:
            break // velocity + chunkEvent drive aurora rim + mask
        case .typewriterLuxe:
            luxeEventToken += 1
        case .minimalMotion:
            break
        }
    }

    @MainActor
    private func inlineMarkdown(_ source: String) -> AttributedString {
        ResponseInlineMarkdownCache.shared.value(for: source) {
            let options = AttributedString.MarkdownParsingOptions(
                interpretedSyntax: .inlineOnlyPreservingWhitespace
            )
            return (try? AttributedString(markdown: source, options: options)) ?? AttributedString(source)
        }
    }

    private func isLeadParagraphBlock(_ block: MarkdownBlock) -> Bool {
        if case .paragraph(let text) = block.kind {
            return text.count <= 320
        }
        return false
    }

    private func isCautionParagraph(_ text: String) -> Bool {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.range(of: "Caution:", options: [.caseInsensitive, .anchored]) != nil
    }

    private func cautionParagraphPadding(isLeadParagraph: Bool) -> EdgeInsets {
        if isLeadParagraph {
            return EdgeInsets(top: 10, leading: 12, bottom: 10, trailing: 12)
        }
        switch responsePresentationStyle {
        case .readablePro:
            return EdgeInsets(top: 8, leading: 10, bottom: 8, trailing: 10)
        case .glassEditorial:
            return EdgeInsets(top: 8, leading: 10, bottom: 8, trailing: 10)
        case .denseTechnical:
            return EdgeInsets(top: 6, leading: 8, bottom: 6, trailing: 8)
        }
    }

    private static func parsePlanClarificationPayload(_ text: String) -> PlanClarificationPayload? {
        let normalized = text.replacingOccurrences(of: "\r\n", with: "\n")
        let lowered = normalized.lowercased()
        guard lowered.contains("plan mode"), lowered.contains("clarification") else {
            return nil
        }

        let lines = normalized.components(separatedBy: "\n")
        var introLines: [String] = []
        var questions: [PlanClarificationQuestion] = []
        var currentNumber: Int?
        var currentPrompt = ""
        var currentOptions: [PlanClarificationOption] = []

        func flushCurrentQuestion() {
            guard let questionNumber = currentNumber else { return }
            guard !currentPrompt.isEmpty else { return }
            guard !currentOptions.isEmpty else { return }
            let sortedOptions = currentOptions.sorted { lhs, rhs in
                lhs.key.localizedStandardCompare(rhs.key) == .orderedAscending
            }
            questions.append(
                PlanClarificationQuestion(
                    id: questions.count,
                    number: questionNumber,
                    prompt: currentPrompt,
                    options: sortedOptions
                )
            )
            currentNumber = nil
            currentPrompt = ""
            currentOptions = []
        }

        for rawLine in lines {
            let line = rawLine.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !line.isEmpty else { continue }

            if let (number, prompt) = parseClarificationQuestionLine(line) {
                flushCurrentQuestion()
                currentNumber = number
                currentPrompt = prompt
                continue
            }

            if let (key, optionText) = parseClarificationOptionLine(line), currentNumber != nil {
                currentOptions.append(
                    PlanClarificationOption(
                        id: "\(currentNumber ?? 0)-\(key)",
                        key: key,
                        text: optionText
                    )
                )
                continue
            }

            if currentNumber == nil {
                introLines.append(line)
            }
        }

        flushCurrentQuestion()
        guard !questions.isEmpty else { return nil }
        questions.sort { lhs, rhs in lhs.number < rhs.number }

        let intro = introLines.joined(separator: "\n")
        return PlanClarificationPayload(intro: intro, questions: questions)
    }

    private static func parseClarificationQuestionLine(_ line: String) -> (Int, String)? {
        guard line.count >= 4 else { return nil }
        guard line.uppercased().hasPrefix("Q") else { return nil }
        guard let dotIndex = line.firstIndex(of: ".") else { return nil }
        let numberPart = line[line.index(after: line.startIndex)..<dotIndex]
        guard let questionNumber = Int(numberPart) else { return nil }
        let prompt = line[line.index(after: dotIndex)...].trimmingCharacters(in: .whitespaces)
        guard !prompt.isEmpty else { return nil }
        return (questionNumber, prompt)
    }

    private static func parseClarificationOptionLine(_ line: String) -> (String, String)? {
        guard line.count >= 4 else { return nil }
        guard let first = line.first else { return nil }
        let key = String(first).uppercased()
        guard ["A", "B", "C", "D"].contains(key) else { return nil }
        let secondIndex = line.index(after: line.startIndex)
        guard secondIndex < line.endIndex, line[secondIndex] == ")" else { return nil }
        let textStart = line.index(after: secondIndex)
        let optionText = line[textStart...].trimmingCharacters(in: .whitespaces)
        guard !optionText.isEmpty else { return nil }
        return (key, optionText)
    }

    private static let timestampFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.timeStyle = .short
        return formatter
    }()
}


#if DEBUG
struct ResponseBubblePreview: View {
    var body: some View {
        VStack(spacing: ThemeConstants.spacingM) {
            ResponseBubble(
                row: MessageRowModel(message: Message.user("Find all Python files in my Documents folder"))
            )

            ResponseBubble(
                row: MessageRowModel(
                    message: Message(
                        role: .assistant,
                        content: """
                        ## Search Summary

                        - Found **15** matching files.
                        - Sorted by most recently modified.

                        1. `main.py`
                        2. `config.py`
                        3. `utils.py`
                        """
                    )
                )
            )

            ResponseBubble(
                row: MessageRowModel(
                    message: Message(
                        role: .assistant,
                        content: "Processing your request and preparing final output...",
                        isStreaming: true
                    )
                ),
                animate: true
            )
        }
        .padding()
        .background(Color.panelBackground)
        .frame(width: 420)
    }
}

struct ResponseBubble_Previews: PreviewProvider {
    static var previews: some View {
        ResponseBubblePreview()
    }
}
#endif
