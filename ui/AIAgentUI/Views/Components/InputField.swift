//
//  InputField.swift
//  AIAgentUI
//
//  Shared input component across macOS, iPhone, and iPad.
//

import SwiftUI

#if os(macOS)
import AppKit
#endif

struct InputField: View {
    @Binding var text: String
    var placeholder: String = "Ask me anything..."
    var isDisabled: Bool = false
    var accentColor: Color = .primaryBlue
    var isBusy: Bool = false
    var onAttach: (() -> Void)? = nil
    var onSubmit: () -> Void

    @State private var isFocused: Bool = false
    @State private var textViewHeight: CGFloat = 34
    @State private var wordCount: Int = 0
    @State private var charCount: Int = 0
    @State private var busyPulse: Bool = false
    @Environment(\.colorScheme) private var colorScheme

    private let minHeight: CGFloat = 34
    private let maxHeight: CGFloat = 260

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .bottom, spacing: ThemeConstants.spacingS) {
                if let onAttach = onAttach {
                    Button(action: onAttach) {
                        Image(systemName: "paperclip")
                            .font(.system(size: 18, weight: .medium))
                            .foregroundColor(isDisabled ? .textTertiary : .textSecondary)
                    }
                    .buttonStyle(.plain)
                    .disabled(isDisabled)
                    .padding(.bottom, 6)
                    .help("Attach files")
                }

                EnhancedTextView(
                    text: $text,
                    placeholder: placeholder,
                    isFocused: $isFocused,
                    isDisabled: isDisabled,
                    desiredHeight: $textViewHeight,
                    wordCount: $wordCount,
                    charCount: $charCount,
                    minHeight: minHeight,
                    maxHeight: maxHeight,
                    onSubmit: submitIfPossible
                )
                .frame(height: clampedHeight)

                Button(action: submitIfPossible) {
                    ZStack {
                        Circle()
                            .fill(canSubmit ? accentColor.opacity(0.15) : Color.cardBackground.opacity(0.55))
                            .frame(width: 32, height: 32)

                        Image(systemName: isDisabled ? "hourglass" : "arrow.up")
                            .font(.system(size: 14, weight: .bold))
                            .foregroundColor(canSubmit ? accentColor : .textTertiary)
                    }
                    .contentTransition(.symbolEffect(.replace))
                    .scaleEffect(canSubmit ? 1.0 : 0.88)
                    .animation(.spring(duration: 0.25, bounce: 0.3), value: canSubmit)
                }
                .buttonStyle(.plain)
                .disabled(!canSubmit)
                .help("Send")
            }
            .padding(ThemeConstants.spacingM)
            .background(
                RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusMedium)
                    .fill(.regularMaterial)
                    .overlay(
                        RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusMedium)
                            .fill(composerTint)
                    )
            )
            .clipShape(RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusMedium))
            .overlay(
                RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusMedium)
                    .stroke(borderStrokeColor, lineWidth: isFocused ? 2 : 1)
            )
            .animation(AnimationConstants.fast, value: isFocused)
            .animation(
                isBusy ? Animation.easeInOut(duration: 1.5).repeatForever(autoreverses: true) : .default,
                value: busyPulse
            )
            .onChange(of: isBusy) { _, busy in
                busyPulse = busy
            }

            HStack(spacing: ThemeConstants.spacingS) {
                if charCount > 100 {
                    Text("\(wordCount) word\(wordCount == 1 ? "" : "s") · \(charCount) char\(charCount == 1 ? "" : "s")")
                        .font(.caption2.monospacedDigit())
                        .foregroundColor(.textTertiary)
                        .transition(.opacity.combined(with: .move(edge: .leading)))
                }

                Spacer()

                if isFocused {
                    Text(keyboardHint)
                        .font(.caption2)
                        .foregroundColor(.textTertiary)
                        .transition(.opacity.combined(with: .move(edge: .trailing)))
                }
            }
            .animation(.easeInOut(duration: 0.2), value: charCount > 100)
            .animation(.easeInOut(duration: 0.2), value: isFocused)
        }
    }

    private var clampedHeight: CGFloat {
        min(max(textViewHeight, minHeight), maxHeight)
    }

    private var borderStrokeColor: Color {
        if isBusy {
            return accentColor.opacity(busyPulse ? 0.58 : 0.22)
        }
        return isFocused ? accentColor.opacity(0.52) : Color.glassStroke.opacity(0.85)
    }

    private var composerTint: Color {
        colorScheme == .dark ? Color.black.opacity(0.10) : Color.black.opacity(0.03)
    }

    private var canSubmit: Bool {
        !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !isDisabled
    }

    private var keyboardHint: String {
        #if os(macOS)
        return "⏎ Send · ⇧⏎ Newline"
        #else
        return "Use Send to submit"
        #endif
    }

    private func submitIfPossible() {
        guard canSubmit else { return }
        onSubmit()
    }
}

#if os(macOS)

struct EnhancedTextView: NSViewRepresentable {
    @Binding var text: String
    var placeholder: String
    @Binding var isFocused: Bool
    var isDisabled: Bool
    @Binding var desiredHeight: CGFloat
    @Binding var wordCount: Int
    @Binding var charCount: Int
    var minHeight: CGFloat
    var maxHeight: CGFloat
    var onSubmit: () -> Void

    func makeCoordinator() -> Coordinator {
        Coordinator(self)
    }

    func makeNSView(context: Context) -> NSScrollView {
        let textView = SmartSubmitTextView()
        textView.delegate = context.coordinator
        textView.submitAction = onSubmit
        textView.placeholderString = placeholder
        textView.isRichText = false
        textView.allowsUndo = true
        textView.font = NSFont.systemFont(ofSize: NSFont.systemFontSize)
        textView.textColor = NSColor.labelColor
        textView.insertionPointColor = NSColor.labelColor
        textView.backgroundColor = .clear
        textView.drawsBackground = false
        textView.isEditable = !isDisabled
        textView.isSelectable = true
        textView.textContainerInset = NSSize(width: 2, height: 6)
        textView.isContinuousSpellCheckingEnabled = true
        textView.isGrammarCheckingEnabled = true
        textView.isAutomaticSpellingCorrectionEnabled = true
        textView.isAutomaticQuoteSubstitutionEnabled = true
        textView.isAutomaticDashSubstitutionEnabled = true
        textView.isAutomaticTextReplacementEnabled = true
        textView.isAutomaticDataDetectionEnabled = false
        textView.isAutomaticLinkDetectionEnabled = false
        textView.smartInsertDeleteEnabled = true

        let scrollView = NSScrollView()
        scrollView.documentView = textView
        scrollView.hasVerticalScroller = true
        scrollView.hasHorizontalScroller = false
        scrollView.autohidesScrollers = true
        scrollView.borderType = .noBorder
        scrollView.drawsBackground = false
        scrollView.backgroundColor = .clear
        scrollView.scrollerStyle = .overlay

        textView.textContainer?.widthTracksTextView = true
        textView.textContainer?.containerSize = NSSize(width: 0, height: CGFloat.greatestFiniteMagnitude)
        textView.isHorizontallyResizable = false
        textView.isVerticallyResizable = true
        textView.autoresizingMask = [.width]

        context.coordinator.textView = textView
        context.coordinator.scrollView = scrollView
        return scrollView
    }

    func updateNSView(_ scrollView: NSScrollView, context: Context) {
        guard let textView = scrollView.documentView as? SmartSubmitTextView else { return }
        if textView.string != text {
            textView.string = text
            context.coordinator.recalculateHeightAndStats()
        }
        textView.isEditable = !isDisabled
        textView.textColor = isDisabled ? NSColor.tertiaryLabelColor : NSColor.labelColor
        textView.submitAction = onSubmit
        textView.placeholderString = placeholder
        textView.needsDisplay = true
    }

    @MainActor
    final class Coordinator: NSObject, NSTextViewDelegate {
        var parent: EnhancedTextView
        weak var textView: SmartSubmitTextView?
        weak var scrollView: NSScrollView?

        init(_ parent: EnhancedTextView) {
            self.parent = parent
        }

        func textDidChange(_ notification: Notification) {
            guard let textView = notification.object as? NSTextView else { return }
            parent.text = textView.string
            recalculateHeightAndStats()
        }

        func textDidBeginEditing(_ notification: Notification) {
            parent.isFocused = true
        }

        func textDidEndEditing(_ notification: Notification) {
            parent.isFocused = false
        }

        func recalculateHeightAndStats() {
            guard let textView else { return }
            let content = textView.string
            let trimmed = content.trimmingCharacters(in: .whitespacesAndNewlines)
            parent.wordCount = trimmed.isEmpty ? 0 : trimmed.components(separatedBy: .whitespacesAndNewlines).filter { !$0.isEmpty }.count
            parent.charCount = content.count

            guard let layoutManager = textView.layoutManager, let textContainer = textView.textContainer else { return }
            layoutManager.ensureLayout(for: textContainer)
            let usedRect = layoutManager.usedRect(for: textContainer)
            let inset = textView.textContainerInset
            parent.desiredHeight = usedRect.height + inset.height * 2
        }
    }
}

final class SmartSubmitTextView: NSTextView {
    var submitAction: (() -> Void)?
    var placeholderString: String = "Ask me anything..."

    override func keyDown(with event: NSEvent) {
        let isEnterKey = event.keyCode == 36
        let hasShift = event.modifierFlags.contains(.shift)
        if isEnterKey && !hasShift {
            submitAction?()
            return
        }
        super.keyDown(with: event)
    }

    override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)
        guard string.isEmpty else { return }
        let attributes: [NSAttributedString.Key: Any] = [
            .foregroundColor: NSColor.tertiaryLabelColor,
            .font: font ?? NSFont.systemFont(ofSize: NSFont.systemFontSize),
        ]
        let inset = textContainerInset
        let origin = textContainerOrigin
        let rect = NSRect(
            x: origin.x + 5,
            y: inset.height,
            width: bounds.width - origin.x * 2 - 10,
            height: bounds.height - inset.height * 2
        )
        placeholderString.draw(in: rect, withAttributes: attributes)
    }

    override func didChangeText() {
        super.didChangeText()
        needsDisplay = true
    }

    override var acceptsFirstResponder: Bool { true }
}

#else

struct EnhancedTextView: View {
    @Binding var text: String
    var placeholder: String
    @Binding var isFocused: Bool
    var isDisabled: Bool
    @Binding var desiredHeight: CGFloat
    @Binding var wordCount: Int
    @Binding var charCount: Int
    var minHeight: CGFloat
    var maxHeight: CGFloat
    var onSubmit: () -> Void

    @FocusState private var focused: Bool

    var body: some View {
        ZStack(alignment: .topLeading) {
            if text.isEmpty {
                Text(placeholder)
                    .foregroundColor(.textTertiary)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 8)
                    .allowsHitTesting(false)
            }

            TextEditor(text: $text)
                .focused($focused)
                .disabled(isDisabled)
                .scrollContentBackground(.hidden)
                .background(Color.clear)
                .padding(.horizontal, 2)
                .padding(.vertical, 2)
        }
        .onAppear {
            recalculateMetrics()
        }
        .onChange(of: text) { _, _ in
            recalculateMetrics()
        }
        .onChange(of: focused) { _, newValue in
            isFocused = newValue
        }
    }

    private func recalculateMetrics() {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        wordCount = trimmed.isEmpty ? 0 : trimmed.components(separatedBy: .whitespacesAndNewlines).filter { !$0.isEmpty }.count
        charCount = text.count
        let lineCount = max(1, text.components(separatedBy: "\n").count)
        desiredHeight = min(max(CGFloat(lineCount) * 22 + 14, minHeight), maxHeight)
    }
}

#endif

struct SimpleInputField: View {
    @Binding var text: String
    var placeholder: String = "Type here..."
    var isDisabled: Bool = false
    var onSubmit: () -> Void = {}

    @FocusState private var isFocused: Bool

    var body: some View {
        TextField(placeholder, text: $text)
            .textFieldStyle(.plain)
            .font(.body)
            .foregroundColor(.textPrimary)
            .padding(ThemeConstants.spacingM)
            .background(Color.inputBackground.opacity(0.8))
            .clipShape(RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusSmall))
            .overlay(
                RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusSmall)
                    .stroke(
                        isFocused ? Color.primaryBlue.opacity(0.5) : Color.glassStroke,
                        lineWidth: isFocused ? 2 : 1
                    )
            )
            .focused($isFocused)
            .disabled(isDisabled)
            .onSubmit(onSubmit)
            .animation(AnimationConstants.fast, value: isFocused)
    }
}

#if DEBUG
struct InputFieldPreview: View {
    @State private var text = ""
    @State private var simpleText = ""

    var body: some View {
        VStack(spacing: ThemeConstants.spacingL) {
            VStack(alignment: .leading, spacing: ThemeConstants.spacingS) {
                Text("Enhanced Input")
                    .font(.caption)
                    .foregroundColor(.textSecondary)

                InputField(
                    text: $text,
                    placeholder: "Ask me anything...",
                    onSubmit: { print("Submitted: \(text)") }
                )
            }

            VStack(alignment: .leading, spacing: ThemeConstants.spacingS) {
                Text("Simple Input")
                    .font(.caption)
                    .foregroundColor(.textSecondary)

                SimpleInputField(
                    text: $simpleText,
                    placeholder: "Type here...",
                    onSubmit: { print("Submitted: \(simpleText)") }
                )
            }
        }
        .padding()
        .frame(width: 400)
        .background(Color.panelBackground)
    }
}
#endif
