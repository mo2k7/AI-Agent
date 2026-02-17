//
//  ResponseBubble.swift
//  AIAgentUI
//
//  Created for Personal macOS AI Agent
//  Status: Active - Modern message rendering + streaming feedback
//

import SwiftUI

@MainActor
private final class ResponseInlineMarkdownCache {
    static let shared = ResponseInlineMarkdownCache()

    private let maxEntries = 256
    private let maxCachedSourceLength = 480
    private var storage: [String: AttributedString] = [:]
    private var insertionOrder: [String] = []

    private init() {}

    func value(for source: String, builder: () -> AttributedString) -> AttributedString {
        if source.count > maxCachedSourceLength {
            return builder()
        }
        if let cached = storage[source] {
            return cached
        }
        let rendered = builder()
        if insertionOrder.count >= maxEntries, let evictedKey = insertionOrder.first {
            insertionOrder.removeFirst()
            storage.removeValue(forKey: evictedKey)
        }
        insertionOrder.append(source)
        storage[source] = rendered
        return rendered
    }
}

private struct PlanClarificationOption: Identifiable {
    let id: String
    let key: String
    let text: String
}

private struct PlanClarificationQuestion: Identifiable {
    let id: Int
    let number: Int
    let prompt: String
    let options: [PlanClarificationOption]
}

private struct PlanClarificationPayload {
    let intro: String
    let questions: [PlanClarificationQuestion]
}

/// Displays a message bubble with style-aware markdown rendering and streaming animations.
struct ResponseBubble: View {

    // MARK: - Properties

    /// The message to display
    let message: Message

    /// Whether to animate the text (for streaming)
    var animate: Bool = false

    @ObservedObject private var appState = AppState.shared
    @AppStorage("animationsEnabled") private var animationsEnabled = true
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

    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    // MARK: - Body

    var body: some View {
        HStack(alignment: .top, spacing: ThemeConstants.spacingS) {
            roleIcon

            VStack(alignment: .leading, spacing: ThemeConstants.spacingXS) {
                HStack(spacing: 6) {
                    Text(roleLabel)
                        .font(.caption)
                        .foregroundColor(metaTextColor)

                    if message.role == .assistant && message.isStreaming {
                        BubbleThinkingIndicator(
                            status: appState.status,
                            statusDetail: appState.statusDetail,
                            activeToolCall: appState.currentToolCall
                        )
                    }
                }

                messageContent

                if let toolCall = message.toolCall {
                    ToolCallCard(toolCall: toolCall)
                        .padding(.top, ThemeConstants.spacingXS)
                }

                Text(formattedTimestamp)
                    .font(.caption2)
                    .foregroundColor(metaTextColor.opacity(0.92))
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(ThemeConstants.spacingM)
        .background(bubbleBackground)
        .overlay(
            RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusMedium)
                .stroke(bubbleBorderColor, lineWidth: bubbleBorderWidth)
        )
        // Aurora rim overlay — only for wave-reveal on assistant streaming bubbles
        .overlay {
            if message.role == .assistant && effectiveStreamingStyle == .waveReveal
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
        .clipShape(RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusMedium))
        .shadow(
            color: bubbleShadowColor,
            radius: bubbleShadowRadius,
            x: 0,
            y: bubbleShadowRadius > 0 ? 4 : 0
        )
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
        .onChange(of: message.content) { _, newValue in
            if message.isStreaming {
                animateTyping(to: newValue)
            } else {
                updateDisplayedText(newValue)
            }
        }
        .onChange(of: message.isStreaming) { _, isStreaming in
            if !isStreaming {
                // Reset clarification selections when streaming finishes with new content
                clarificationSelections.removeAll()
                clarificationCustomResponse = ""
                updateDisplayedText(message.content)
                // Wave-reveal: transition aurora to .done → fade out
                if effectiveStreamingStyle == .waveReveal {
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
        .onChange(of: appState.responsePresentationStyle) { _, _ in
            // Re-parse to apply style updates instantly across existing content.
            parsedBlocks = NoteMarkdownParser.parse(displayedText)
        }
    }

    // MARK: - Subviews

    private var roleIcon: some View {
        Image(systemName: message.role == .user ? "person.fill" : "brain")
            .font(.system(size: 16))
            .foregroundColor(message.role == .user ? .primaryBlue : .secondaryBlue)
            .frame(width: 28, height: 28)
            .background(
                Circle()
                    .fill(
                        message.role == .user
                            ? Color.primaryBlue.opacity(0.1)
                            : Color.secondaryBlue.opacity(0.1)
                    )
            )
    }

    @ViewBuilder
    private var messageContent: some View {
        if let clarificationPayload = planClarificationPayload {
            planClarificationView(payload: clarificationPayload)
        } else if displayedText.isEmpty && message.isStreaming {
            VStack(alignment: .leading, spacing: ThemeConstants.spacingS) {
                LoadingShimmer()
                    .padding(.vertical, 2)
                liveToolCallDuringStreaming
            }
        } else {
            VStack(alignment: .leading, spacing: blockSpacing) {
                // Text content — rendered fully, masked by reveal animation
                // when wave-reveal is active during streaming.
                textBlocks
                    .background(textHeightReader)
                    .modifier(
                        WaveRevealMaskModifier(
                            isActive: message.isStreaming
                                && effectiveStreamingStyle == .waveReveal
                                && !reduceMotion,
                            maskHeight: revealMaskHeight,
                            featherSize: 22
                        )
                    )
                    // Prevent implicit layout animation from text changes
                    .transaction { txn in txn.animation = nil }

                // Bottom streaming indicator — only for non-waveReveal styles
                if message.isStreaming && effectiveStreamingStyle != .waveReveal {
                    streamingFeedback
                        .padding(.top, 4)
                }

                liveToolCallDuringStreaming
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
                                && appState.status.canSubmit {
                                Task {
                                    await appState.submitPlanClarificationResponse(
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
                        await appState.submitPlanClarificationResponse(composeClarificationAnswer(payload))
                    }
                }
                .buttonStyle(.borderedProminent)
                .disabled(clarificationSelections.count < payload.questions.count || appState.status.isBusy)

                Button("Send Custom") {
                    let custom = clarificationCustomResponse.trimmingCharacters(in: .whitespacesAndNewlines)
                    guard !custom.isEmpty else { return }
                    Task {
                        await appState.submitPlanClarificationResponse(custom)
                    }
                }
                .buttonStyle(.bordered)
                .disabled(
                    clarificationCustomResponse.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                        || appState.status.isBusy
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

    @ViewBuilder
    private var liveToolCallDuringStreaming: some View {
        if message.role == .assistant,
           message.isStreaming,
           let activeToolCall = appState.currentToolCall {
            ActiveToolCallView(
                toolCall: activeToolCall,
                isExpanded: $appState.isToolCallExpanded
            )
            .padding(.top, ThemeConstants.spacingXS)
        }
    }

    /// The rendered text blocks, extracted so the reveal mask can wrap them.
    @ViewBuilder
    private var textBlocks: some View {
        if parsedBlocks.isEmpty {
            Text(displayedText)
                .font(paragraphFont)
                .foregroundColor(primaryTextColor)
                .lineSpacing(paragraphLineSpacing)
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
            if message.isStreaming && effectiveStreamingStyle == .waveReveal {
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
                if appState.responsePresentationStyle != .denseTechnical {
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
        case .bullet(let items):
            VStack(alignment: .leading, spacing: bulletItemSpacing) {
                ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                    if appState.responsePresentationStyle == .readablePro {
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
                    if appState.responsePresentationStyle == .readablePro {
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
            switch effectiveStreamingStyle {
            case .waveReveal:
                EmptyView() // handled by aurora rim overlay + reveal mask
            case .typewriterLuxe:
                LuxeStreamingIndicator(eventToken: luxeEventToken)
            case .minimalMotion:
                MinimalStreamingIndicator()
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
                Color.primaryBlue.opacity(0.1)
            } else {
                switch appState.responsePresentationStyle {
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

    private var bubbleBorderColor: Color {
        if message.role == .user {
            return Color.primaryBlue.opacity(0.12)
        }
        switch appState.responsePresentationStyle {
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
        return appState.responsePresentationStyle == .glassEditorial ? 1.05 : 0.85
    }

    private var bubbleShadowColor: Color {
        guard message.role == .assistant else { return .clear }
        switch appState.responsePresentationStyle {
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
        switch appState.responsePresentationStyle {
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
            switch appState.responsePresentationStyle {
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
        switch appState.responsePresentationStyle {
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

    private var listRowBackground: Color {
        switch appState.responsePresentationStyle {
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
        switch appState.responsePresentationStyle {
        case .readablePro:
            return 13
        case .glassEditorial:
            return 12
        case .denseTechnical:
            return 7
        }
    }

    private var bulletItemSpacing: CGFloat {
        switch appState.responsePresentationStyle {
        case .readablePro:
            return 8
        case .glassEditorial:
            return 7
        case .denseTechnical:
            return 4
        }
    }

    private var paragraphLineSpacing: CGFloat {
        switch appState.responsePresentationStyle {
        case .readablePro:
            return 6
        case .glassEditorial:
            return 5
        case .denseTechnical:
            return 2
        }
    }

    private var leadParagraphLineSpacing: CGFloat {
        switch appState.responsePresentationStyle {
        case .readablePro:
            return 5
        case .glassEditorial:
            return 6
        case .denseTechnical:
            return 3
        }
    }

    private var paragraphFont: Font {
        switch appState.responsePresentationStyle {
        case .readablePro:
            return .system(.body, design: .rounded)
        case .glassEditorial:
            return .system(.body, design: .rounded)
        case .denseTechnical:
            return .system(.body, design: .monospaced)
        }
    }

    private var leadParagraphFont: Font {
        switch appState.responsePresentationStyle {
        case .readablePro:
            return .system(.title3, design: .rounded).weight(.semibold)
        case .glassEditorial:
            return .system(.title3, design: .rounded).weight(.semibold)
        case .denseTechnical:
            return .system(.body, design: .monospaced).weight(.medium)
        }
    }

    private var numberBadgeFont: Font {
        switch appState.responsePresentationStyle {
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
            return appState.responsePresentationStyle == .denseTechnical ? .headline : .title3
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
        return appState.streamingAnimationStyle
    }

    private var streamingIndicatorHeight: CGFloat {
        24
    }

    private var messageContentMaxWidth: CGFloat? {
        switch appState.responsePresentationStyle {
        case .readablePro:
            return 760
        case .glassEditorial, .denseTechnical:
            return nil
        }
    }

    private var primaryTextColor: Color {
        if readableProHighContrastActive {
            return colorScheme == .dark ? Color.white.opacity(0.98) : Color.black.opacity(0.92)
        }
        return .textPrimary
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
        appState.responsePresentationStyle == .readablePro
            && appState.readableProHighContrastEnabled
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

        // Wrap the text/block mutation in a non-animated transaction to
        // prevent SwiftUI from implicitly animating layout changes.
        var txn = Transaction()
        txn.animation = nil
        withTransaction(txn) {
            displayedText = text
            parsedBlocks = NoteMarkdownParser.parse(text)
        }

        if message.isStreaming && text.count > previousCount {
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

            triggerStreamingFeedback()
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

// MARK: - Wave Reveal Phase

/// Describes the lifecycle of the aurora rim animation.
private enum WaveRevealPhase {
    case idle       // no streaming
    case thinking   // streaming started, no text yet
    case streaming  // text arriving
    case done       // streaming complete, fading out
}

// MARK: - Text Height Preference Key

private struct TextHeightPreferenceKey: PreferenceKey {
    static let defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) {
        value = max(value, nextValue())
    }
}

// MARK: - Wave Reveal Mask Modifier (spec §D)

/// A feathered top-to-bottom reveal mask applied to the text content.
/// The full text is rendered normally; a mask reveals from top as content
/// grows. The feathered bottom edge creates a smooth "materializing" effect.
private struct WaveRevealMaskModifier: ViewModifier {
    let isActive: Bool
    let maskHeight: CGFloat
    let featherSize: CGFloat

    func body(content: Content) -> some View {
        if isActive {
            content.mask(
                VStack(spacing: 0) {
                    // Fully opaque region
                    Rectangle()
                        .frame(height: max(0, maskHeight - featherSize))
                    // Feathered edge — linear fade from opaque to transparent
                    LinearGradient(
                        colors: [.white, .clear],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                    .frame(height: featherSize)
                    // Transparent region below the reveal
                    Spacer(minLength: 0)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
            )
        } else {
            content
        }
    }
}

// MARK: - Aurora Rim Overlay (spec §A, §C)

/// A velocity-reactive gradient stroke around the response bubble.
///
/// Uses `TimelineView(.animation)` as the render heartbeat (spec §A).
/// The gradient rotates continuously; its opacity, blur, and line width
/// are mapped from the smoothed token velocity (spec §C).
private struct AuroraRimOverlay: View {

    let velocity: CGFloat          // EMA-smoothed 0…1
    let phase: WaveRevealPhase
    let doneOpacity: CGFloat       // animated to 0 on .done
    let reduceMotion: Bool
    let cornerRadius: CGFloat

    // Aurora color palette
    private static let auroraColors: [Color] = [
        Color.secondaryBlue.opacity(0.8),
        Color.statusStreaming.opacity(0.7),
        Color.primaryBlue.opacity(0.6),
        Color.secondaryBlue.opacity(0.5),
        Color.statusStreaming.opacity(0.7),
        Color.primaryBlue.opacity(0.8),
        Color.secondaryBlue.opacity(0.8),
    ]

    var body: some View {
        if reduceMotion {
            // Respect Reduce Motion: simple static glow, no drift
            RoundedRectangle(cornerRadius: cornerRadius)
                .stroke(Color.secondaryBlue.opacity(Double(rimOpacity)), lineWidth: Double(rimLineWidth))
                .opacity(Double(doneOpacity))
        } else {
            TimelineView(.animation) { context in
                let t = context.date.timeIntervalSinceReferenceDate
                let v = effectiveVelocity

                // Rotation period: 12s idle → 7s fast (spec §C)
                let period = 12.0 - 5.0 * Double(v)
                let angle = Angle.degrees(t.truncatingRemainder(dividingBy: period) / period * 360)

                RoundedRectangle(cornerRadius: cornerRadius)
                    .stroke(
                        AngularGradient(
                            colors: Self.auroraColors,
                            center: .center,
                            angle: angle
                        ),
                        lineWidth: Double(rimLineWidth)
                    )
                    .blur(radius: Double(rimBlur))
                    .opacity(Double(rimOpacity) * Double(doneOpacity))
            }
        }
    }

    // MARK: - Velocity → visual parameter mapping (spec §C)

    private var effectiveVelocity: CGFloat {
        switch phase {
        case .idle:
            return 0
        case .thinking:
            return 0.05 // slow pulse
        case .streaming:
            return velocity
        case .done:
            return 0.05
        }
    }

    /// opacity = 0.18 + 0.55 * v
    private var rimOpacity: CGFloat {
        0.18 + 0.55 * effectiveVelocity
    }

    /// blurRadius = 1.0 + 4.0 * v
    private var rimBlur: CGFloat {
        1.0 + 4.0 * effectiveVelocity
    }

    /// lineWidth = 1.2 + 1.0 * v
    private var rimLineWidth: CGFloat {
        1.2 + 1.0 * effectiveVelocity
    }
}

private struct LuxeStreamingIndicator: View {
    let eventToken: Int
    @State private var phase = false

    var body: some View {
        HStack(spacing: ThemeConstants.spacingS) {
            HStack(spacing: 5) {
                ForEach(0..<3, id: \.self) { idx in
                    Circle()
                        .fill(
                            LinearGradient(
                                colors: [Color.secondaryBlue, Color.primaryBlue],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            )
                        )
                        .frame(width: 6, height: 6)
                        .scaleEffect(phase ? (idx == 1 ? 1.45 : 1.2) : 0.82)
                        .opacity(phase ? 1.0 : 0.6)
                        .animation(
                            .easeInOut(duration: 0.42).delay(Double(idx) * 0.06),
                            value: phase
                        )
                }
            }
            Text("Composing")
                .font(.caption2)
                .foregroundColor(.textSecondary)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(
            Capsule()
                .fill(Color.secondaryBlue.opacity(0.14))
        )
        .onAppear {
            phase.toggle()
        }
        .onChange(of: eventToken) { _, _ in
            phase.toggle()
        }
    }
}

private struct MinimalStreamingIndicator: View {
    var body: some View {
        HStack(spacing: ThemeConstants.spacingS) {
            Circle()
                .fill(Color.statusStreaming.opacity(0.65))
                .frame(width: 6, height: 6)
            Text("Updating")
                .font(.caption2)
                .foregroundColor(.textSecondary)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(
            Capsule()
                .fill(Color.statusStreaming.opacity(0.1))
        )
    }
}

// MARK: - Bubble Thinking Indicator

/// Compact thinking indicator with timer for message bubbles
struct BubbleThinkingIndicator: View {

    let status: AgentStatus
    let statusDetail: String
    let activeToolCall: ToolCall?

    @State private var elapsedTime: TimeInterval = 0
    @State private var startTime: Date = Date()
    @State private var dotPhase = 0
    @State private var isExpanded = false

    private let timer = Timer.publish(every: 0.1, on: .main, in: .common).autoconnect()
    private let dotTimer = Timer.publish(every: 0.4, on: .main, in: .common).autoconnect()

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Button(action: { withAnimation(.easeInOut(duration: 0.2)) { isExpanded.toggle() } }) {
                HStack(spacing: 6) {
                    Text(activityTitle)
                        .font(.system(size: 11, weight: .medium))
                        .foregroundColor(activityColor)

                    HStack(spacing: 2) {
                        ForEach(0..<3, id: \.self) { i in
                            Circle()
                                .fill(activityColor)
                                .frame(width: 4, height: 4)
                                .opacity(dotPhase == i ? 1.0 : 0.4)
                        }
                    }

                    Text(formattedTime)
                        .font(.system(size: 11, weight: .medium, design: .monospaced))
                        .foregroundColor(activityColor)

                    Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                        .font(.system(size: 8, weight: .semibold))
                        .foregroundColor(activityColor.opacity(0.7))
                }
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(
                    Capsule()
                        .fill(activityColor.opacity(0.15))
                )
            }
            .buttonStyle(.plain)

            if isExpanded {
                VStack(alignment: .leading, spacing: 6) {
                    Text(activityDetail)
                        .font(.caption)
                        .foregroundColor(.textSecondary)
                        .lineLimit(nil)
                        .fixedSize(horizontal: false, vertical: true)

                    HStack(spacing: 8) {
                        Label(activityLabel, systemImage: activitySymbol)
                        Spacer()
                        Text(formattedTime)
                            .font(.system(size: 11, design: .monospaced))
                    }
                    .font(.caption2)
                    .foregroundColor(.textTertiary)

                    if let activeToolCall {
                        HStack(spacing: 8) {
                            Label(toolLine(activeToolCall), systemImage: "hammer")
                                .lineLimit(1)
                            Spacer()
                            Text(activeToolCall.status.badgeText)
                                .font(.caption2.weight(.semibold))
                                .foregroundColor(activityColor)
                        }
                        .font(.caption2)
                        .foregroundColor(.textTertiary)
                    }
                }
                .padding(10)
                .background(
                    RoundedRectangle(cornerRadius: 8)
                        .fill(Color.cardBackground.opacity(0.8))
                )
                .transition(.opacity.combined(with: .move(edge: .top)))
            }
        }
        .onReceive(timer) { _ in
            elapsedTime = Date().timeIntervalSince(startTime)
        }
        .onReceive(dotTimer) { _ in
            dotPhase = (dotPhase + 1) % 3
        }
        .onAppear {
            startTime = Date()
            elapsedTime = 0
        }
        .onChange(of: phaseKey) { _, _ in
            startTime = Date()
            elapsedTime = 0
        }
    }

    private var formattedTime: String {
        let seconds = elapsedTime
        if seconds < 60 {
            return String(format: "%.1fs", seconds)
        } else {
            let mins = Int(seconds) / 60
            let secs = seconds.truncatingRemainder(dividingBy: 60)
            return String(format: "%d:%04.1f", mins, secs)
        }
    }

    private var activityColor: Color {
        switch status {
        case .error:
            return .statusError
        case .complete:
            return .statusComplete
        case .streaming:
            return .statusStreaming
        default:
            return .statusThinking
        }
    }

    private var activityTitle: String {
        // For planning/thinking, show a short dynamic phase label from the
        // backend's statusDetail when available, so the user sees which step
        // of the pipeline is currently active (e.g. "Preparing context" vs.
        // "Drafting plan") instead of a static "Planning" label.
        switch status {
        case .planning, .thinking, .executingPlan:
            let trimmed = statusDetail.trimmingCharacters(in: .whitespacesAndNewlines)
            if !trimmed.isEmpty {
                // Truncate long details to keep the pill compact
                return trimmed.count > 36 ? String(trimmed.prefix(33)) + "..." : trimmed
            }
            if case .planning = status { return "Planning" }
            if case .executingPlan = status { return "Executing" }
            return "Thinking"
        case .callingTool:
            return "Tooling"
        case .capturingScreen:
            return "Reading Screen"
        case .streaming:
            return "Responding"
        case .awaitingApproval:
            return "Approval"
        case .complete:
            return "Done"
        case .error:
            return "Issue"
        default:
            return "Thinking"
        }
    }

    private var activitySymbol: String {
        switch status {
        case .planning:
            return "list.bullet.clipboard"
        case .callingTool:
            return "hammer"
        case .capturingScreen:
            return "eye"
        case .streaming:
            return "text.bubble"
        case .awaitingApproval:
            return "hand.raised"
        case .complete:
            return "checkmark.circle"
        case .error:
            return "exclamationmark.triangle"
        default:
            return "brain"
        }
    }

    private var activityLabel: String {
        switch status {
        case .planning:
            return "Plan mode active"
        case .callingTool:
            return "Running a tool"
        case .capturingScreen:
            return "Reading screen contents"
        case .streaming:
            return "Sending answer"
        case .awaitingApproval:
            return "Waiting for approval"
        case .complete:
            return "Finished"
        case .error:
            return "Needs attention"
        default:
            return "Analyzing request"
        }
    }

    private var activityDetail: String {
        let trimmed = statusDetail.trimmingCharacters(in: .whitespacesAndNewlines)
        if !trimmed.isEmpty {
            return trimmed
        }
        return activityLabel
    }

    private var phaseKey: String {
        // Include statusDetail so the timer resets whenever the backend sends
        // a new phase description (e.g. "Preparing context..." → "Analyzing
        // your request...").  Without this, the timer never resets within a
        // single status enum case like `.planning`.
        let detailSuffix = statusDetail.trimmingCharacters(in: .whitespacesAndNewlines)
        let base: String
        switch status {
        case .idle:
            base = "idle"
        case .connecting:
            base = "connecting"
        case .thinking:
            base = "thinking"
        case .planning:
            base = "planning"
        case .planReady:
            base = "plan_ready"
        case .awaitingApproval:
            base = "awaiting_approval"
        case .executingPlan:
            base = "executing_plan"
        case .callingTool(let toolName):
            base = "calling_tool:\(toolName)"
        case .capturingScreen:
            base = "capturing_screen"
        case .streaming:
            base = "streaming"
        case .error(let message):
            base = "error:\(message)"
        case .complete:
            base = "complete"
        }
        return detailSuffix.isEmpty ? base : "\(base)|\(detailSuffix)"
    }

    private func toolLine(_ toolCall: ToolCall) -> String {
        switch toolCall.status {
        case .pending:
            return "Queued: \(toolCall.name)"
        case .executing:
            return "Running: \(toolCall.name)"
        case .success:
            return "Finished: \(toolCall.name)"
        case .failed:
            return "Failed: \(toolCall.name)"
        }
    }
}

// MARK: - Message List View

/// A scrollable list of message bubbles
struct MessageListView: View {

    let messages: [Message]
    let sessionId: String

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var scrollProxy: ScrollViewProxy?
    @State private var pendingScrollTask: Task<Void, Never>?
    private let bottomAnchorID = "message-list-bottom-anchor"

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: ThemeConstants.spacingM) {
                    ForEach(messages) { message in
                        ResponseBubble(
                            message: message,
                            animate: message.isStreaming
                        )
                        .id(message.id)
                    }
                    Color.clear
                        .frame(height: 1)
                        .id(bottomAnchorID)
                }
                .padding(ThemeConstants.spacingM)
            }
            .onAppear {
                scrollProxy = proxy
                scrollToBottom(animated: false)
            }
            .onDisappear {
                pendingScrollTask?.cancel()
                pendingScrollTask = nil
            }
            .onChange(of: sessionId) { _, _ in
                scheduleScrollToBottom(animated: false)
            }
            .onChange(of: messageIDSequence) { _, _ in
                scheduleScrollToBottom(animated: false)
            }
            .onChange(of: messages.last?.content) { _, _ in
                scheduleScrollToBottom(animated: false)
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
        messages.last?.isStreaming == true
    }

    private var messageIDSequence: [AnyHashable] {
        messages.map { AnyHashable($0.id) }
    }

    private func scheduleScrollToBottom(animated: Bool) {
        pendingScrollTask?.cancel()
        pendingScrollTask = Task { @MainActor in
            await Task.yield()
            scrollToBottom(animated: animated)
            pendingScrollTask = nil
        }
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

#if DEBUG
struct ResponseBubblePreview: View {
    var body: some View {
        VStack(spacing: ThemeConstants.spacingM) {
            ResponseBubble(
                message: Message.user("Find all Python files in my Documents folder")
            )

            ResponseBubble(
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

            ResponseBubble(
                message: Message(
                    role: .assistant,
                    content: "Processing your request and preparing final output...",
                    isStreaming: true
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
