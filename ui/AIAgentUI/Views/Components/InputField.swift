//
//  InputField.swift
//  AIAgentUI
//
//  Created for Personal macOS AI Agent
//  Status: Active - Feature-rich user input component
//

import SwiftUI
import AppKit

// MARK: - Enhanced Input Field

/// Feature-rich text input field for user prompts.
/// Uses NSTextView under the hood for macOS-native spellcheck, autocorrect,
/// grammar check, smart quotes, undo/redo, and dynamic text wrapping.
struct InputField: View {

    // MARK: - Properties

    /// Binding to the input text
    @Binding var text: String

    /// Placeholder text shown when empty
    var placeholder: String = "Ask me anything..."

    /// Whether the input is disabled
    var isDisabled: Bool = false

    /// Called when the user submits (presses Enter)
    var onSubmit: () -> Void

    // MARK: - State

    @State private var isFocused: Bool = false
    @State private var textViewHeight: CGFloat = 34  // single-line default
    @State private var wordCount: Int = 0
    @State private var charCount: Int = 0

    /// Minimum height (single line + inset)
    private let minHeight: CGFloat = 34
    /// Maximum height before internal scrolling kicks in (~12 lines)
    private let maxHeight: CGFloat = 260

    // MARK: - Body

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .bottom, spacing: ThemeConstants.spacingS) {
                // NSTextView-backed input
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

                // Submit button
                Button(action: submitIfPossible) {
                    Image(systemName: isDisabled ? "hourglass" : "arrow.up.circle.fill")
                        .font(.system(size: 24))
                        .foregroundColor(canSubmit ? .primaryBlue : .textTertiary)
                        .contentTransition(.symbolEffect(.replace))
                }
                .buttonStyle(.plain)
                .disabled(!canSubmit)
                .help("Send (Enter)")
            }
            .padding(ThemeConstants.spacingM)
            .background(Color.inputBackground.opacity(0.95))
            .clipShape(RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusMedium))
            .overlay(
                RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusMedium)
                    .stroke(
                        isFocused ? Color.primaryBlue.opacity(0.5) : Color.glassStroke,
                        lineWidth: isFocused ? 2 : 1
                    )
            )
            .animation(AnimationConstants.fast, value: isFocused)

            // Live stats bar
            HStack(spacing: ThemeConstants.spacingS) {
                if !text.isEmpty {
                    Text("\(wordCount) word\(wordCount == 1 ? "" : "s") · \(charCount) char\(charCount == 1 ? "" : "s")")
                        .font(.caption2.monospacedDigit())
                        .foregroundColor(.textTertiary)
                        .transition(.opacity.combined(with: .move(edge: .leading)))
                }

                Spacer()

                if isFocused {
                    Text("⏎ Send · ⇧⏎ Newline")
                        .font(.caption2)
                        .foregroundColor(.textTertiary)
                        .transition(.opacity.combined(with: .move(edge: .trailing)))
                }
            }
            .animation(.easeInOut(duration: 0.2), value: text.isEmpty)
            .animation(.easeInOut(duration: 0.2), value: isFocused)
        }
    }

    // MARK: - Computed Properties

    /// Clamp the height between min and max for smooth dynamic sizing
    private var clampedHeight: CGFloat {
        min(max(textViewHeight, minHeight), maxHeight)
    }

    private var canSubmit: Bool {
        !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !isDisabled
    }

    private func submitIfPossible() {
        guard canSubmit else { return }
        onSubmit()
    }
}

// MARK: - Enhanced Text View (NSViewRepresentable)

/// NSTextView-backed text input with full macOS text system support:
/// spellcheck, autocorrect, grammar, smart quotes, undo, dynamic height.
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

        // Rich text system features
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

        // ✅ Intelligent text features
        textView.isContinuousSpellCheckingEnabled = true
        textView.isGrammarCheckingEnabled = true
        textView.isAutomaticSpellingCorrectionEnabled = true
        textView.isAutomaticQuoteSubstitutionEnabled = true
        textView.isAutomaticDashSubstitutionEnabled = true
        textView.isAutomaticTextReplacementEnabled = true
        textView.isAutomaticDataDetectionEnabled = false
        textView.isAutomaticLinkDetectionEnabled = false
        textView.smartInsertDeleteEnabled = true

        // Scroll view (borderless)
        let scrollView = NSScrollView()
        scrollView.documentView = textView
        scrollView.hasVerticalScroller = true
        scrollView.hasHorizontalScroller = false
        scrollView.autohidesScrollers = true
        scrollView.borderType = .noBorder
        scrollView.drawsBackground = false
        scrollView.backgroundColor = .clear
        scrollView.scrollerStyle = .overlay

        // Word wrapping
        textView.textContainer?.widthTracksTextView = true
        textView.textContainer?.containerSize = NSSize(
            width: 0,
            height: CGFloat.greatestFiniteMagnitude
        )
        textView.isHorizontallyResizable = false
        textView.isVerticallyResizable = true
        textView.autoresizingMask = [.width]

        // Keep reference for height calculations
        context.coordinator.textView = textView
        context.coordinator.scrollView = scrollView

        return scrollView
    }

    func updateNSView(_ scrollView: NSScrollView, context: Context) {
        guard let textView = scrollView.documentView as? SmartSubmitTextView else { return }

        // Update text if changed externally (e.g. after submit clears it)
        if textView.string != text {
            textView.string = text
            context.coordinator.recalculateHeightAndStats()
        }

        // Update disabled state
        textView.isEditable = !isDisabled
        textView.textColor = isDisabled ? NSColor.tertiaryLabelColor : NSColor.labelColor

        // Update submit handler
        textView.submitAction = onSubmit

        // Update placeholder
        textView.placeholderString = placeholder
        textView.needsDisplay = true
    }

    // MARK: - Coordinator

    @MainActor
    class Coordinator: NSObject, NSTextViewDelegate {
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

            // Word & char count
            let trimmed = content.trimmingCharacters(in: .whitespacesAndNewlines)
            let words = trimmed.isEmpty ? 0 : trimmed.components(separatedBy: .whitespacesAndNewlines)
                .filter { !$0.isEmpty }.count
            let chars = content.count

            // Dynamic height calculation
            let layoutManager = textView.layoutManager!
            let textContainer = textView.textContainer!
            layoutManager.ensureLayout(for: textContainer)
            let usedRect = layoutManager.usedRect(for: textContainer)
            let inset = textView.textContainerInset
            let newHeight = usedRect.height + inset.height * 2

            parent.wordCount = words
            parent.charCount = chars
            parent.desiredHeight = newHeight
        }
    }
}

// MARK: - Smart Submit Text View

/// Custom NSTextView: Enter submits, Shift+Enter inserts newline.
/// Draws placeholder text when empty.
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

    // Draw placeholder when empty
    override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)

        if string.isEmpty {
            let attributes: [NSAttributedString.Key: Any] = [
                .foregroundColor: NSColor.tertiaryLabelColor,
                .font: font ?? NSFont.systemFont(ofSize: NSFont.systemFontSize)
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
    }

    // Ensure placeholder redraws when text changes
    override func didChangeText() {
        super.didChangeText()
        needsDisplay = true
    }

    // Accept first responder for immediate focus
    override var acceptsFirstResponder: Bool { true }
}

// MARK: - Simple Input Field (Single Line)

/// A simpler single-line input field variant
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

// MARK: - Preview

#if DEBUG
struct InputFieldPreview: View {
    @State private var text = ""
    @State private var simpleText = ""

    var body: some View {
        VStack(spacing: ThemeConstants.spacingL) {
            // Enhanced multi-line input
            VStack(alignment: .leading, spacing: ThemeConstants.spacingS) {
                Text("Enhanced Input (spellcheck · autocorrect · grammar)")
                    .font(.caption)
                    .foregroundColor(.textSecondary)

                InputField(
                    text: $text,
                    placeholder: "Ask me anything...",
                    onSubmit: { print("Submitted: \(text)") }
                )
            }

            // Simple input
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

            // Disabled state
            VStack(alignment: .leading, spacing: ThemeConstants.spacingS) {
                Text("Disabled Input")
                    .font(.caption)
                    .foregroundColor(.textSecondary)

                InputField(
                    text: .constant(""),
                    placeholder: "Processing...",
                    isDisabled: true,
                    onSubmit: {}
                )
            }
        }
        .padding()
        .frame(width: 400)
        .background(Color.panelBackground)
    }
}

struct InputField_Previews: PreviewProvider {
    static var previews: some View {
        InputFieldPreview()
    }
}
#endif
