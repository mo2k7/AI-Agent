//
//  FlashcardView.swift
//  AIAgentUI
//
//  Created for Personal macOS AI Agent
//  Status: Active - Interactive flashcard study mode for quiz-type notes
//

import SwiftUI

// MARK: - Flashcard Model

/// A single flashcard parsed from note content.
struct Flashcard: Identifiable {
    let id: Int
    let question: String
    let answer: String
}

// MARK: - Flashcard Parser

/// Parses flashcard content from a note.
/// Supported formats:
///   **Q:** question / **A:** answer, separated by --- dividers.
///   This canonical format is required.
enum FlashcardParser {

    static func parse(_ content: String) -> [Flashcard] {
        let normalized = content.replacingOccurrences(of: "\r\n", with: "\n")
        // Split by --- dividers
        let blocks = normalized.components(separatedBy: "\n---\n")
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }

        var cards: [Flashcard] = []
        for (index, block) in blocks.enumerated() {
            if let card = parseQABlock(block, index: index) {
                cards.append(card)
            }
        }
        return cards
    }

    /// Parses a single Q/A block.
    /// Looks for **Q:** and **A:** markers.
    private static func parseQABlock(_ block: String, index: Int) -> Flashcard? {
        let lines = block.components(separatedBy: "\n")
        var questionLines: [String] = []
        var answerLines: [String] = []
        var inAnswer = false

        for line in lines {
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            if trimmed.hasPrefix("**Q:**") {
                inAnswer = false
                let q = stripQAPrefix(trimmed, prefixes: ["**Q:**"])
                if !q.isEmpty { questionLines.append(q) }
            } else if trimmed.hasPrefix("**A:**") {
                inAnswer = true
                let a = stripQAPrefix(trimmed, prefixes: ["**A:**"])
                if !a.isEmpty { answerLines.append(a) }
            } else if inAnswer {
                answerLines.append(trimmed)
            } else {
                questionLines.append(trimmed)
            }
        }

        let question = questionLines.joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
        let answer = answerLines.joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)

        guard !question.isEmpty, !answer.isEmpty else { return nil }
        return Flashcard(id: index, question: question, answer: answer)
    }

    /// Strips known Q/A prefixes from a line.
    private static func stripQAPrefix(_ line: String, prefixes: [String]) -> String {
        for prefix in prefixes {
            if line.hasPrefix(prefix) {
                var rest = String(line.dropFirst(prefix.count))
                // Remove trailing ** if the prefix was like **Q:
                if rest.hasSuffix("**") { rest = String(rest.dropLast(2)) }
                return rest.trimmingCharacters(in: .whitespaces)
            }
        }
        return line
    }
}

// MARK: - FlashcardStudyView

/// Interactive flashcard study view with card flip animation, progress tracking,
/// and score-based review.
struct FlashcardStudyView: View {
    let noteTitle: String
    let cards: [Flashcard]
    var onClose: (() -> Void)? = nil

    @State private var currentIndex: Int = 0
    @State private var isFlipped: Bool = false
    @State private var gotItCount: Int = 0
    @State private var reviewAgainCount: Int = 0
    @State private var reviewQueue: [Int] = []      // indices to review again
    @State private var isComplete: Bool = false
    @State private var isShuffled: Bool = false
    @State private var displayOrder: [Int] = []

    var body: some View {
        VStack(spacing: 0) {
            headerView
            Divider().background(Color.glassStroke)

            if isComplete {
                completionView
            } else if !displayOrder.isEmpty {
                cardView
                Divider().background(Color.glassStroke)
                controlsView
            } else {
                emptyView
            }
        }
        .frame(minWidth: 380, idealWidth: 460, maxWidth: 580,
               minHeight: 340, idealHeight: 440, maxHeight: 600)
        .background(Color.glassBg)
        .onAppear {
            displayOrder = Array(cards.indices)
        }
    }

    // MARK: - Header

    private var headerView: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(noteTitle)
                    .font(.headline)
                    .foregroundColor(.textPrimary)
                    .lineLimit(1)
                Text("\(cards.count) cards")
                    .font(.caption)
                    .foregroundColor(.textSecondary)
            }
            Spacer()

            // Shuffle toggle
            Button(action: toggleShuffle) {
                Image(systemName: isShuffled ? "shuffle" : "arrow.right")
                    .font(.system(size: 13, weight: .medium))
                    .foregroundColor(isShuffled ? .primaryBlue : .textSecondary)
            }
            .buttonStyle(.plain)
            .help(isShuffled ? "Sequential order" : "Shuffle")

            Button(action: { onClose?() }) {
                Image(systemName: "xmark.circle.fill")
                    .font(.system(size: 16))
                    .foregroundColor(.textSecondary.opacity(0.7))
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, ThemeConstants.spacingM)
        .padding(.vertical, ThemeConstants.spacingS)
    }

    // MARK: - Progress Bar

    private var progressView: some View {
        let total = displayOrder.count
        let answered = gotItCount + reviewAgainCount
        let progress = total > 0 ? Double(answered) / Double(total) : 0

        return VStack(spacing: 4) {
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 3)
                        .fill(Color.textPrimary.opacity(0.08))
                        .frame(height: 6)
                    RoundedRectangle(cornerRadius: 3)
                        .fill(Color.primaryBlue)
                        .frame(width: geo.size.width * progress, height: 6)
                        .animation(.easeInOut(duration: 0.3), value: progress)
                }
            }
            .frame(height: 6)

            HStack {
                Text("Card \(min(currentIndex + 1, total)) of \(total)")
                    .font(.caption2)
                    .foregroundColor(.textSecondary)
                Spacer()
                HStack(spacing: 8) {
                    Label("\(gotItCount)", systemImage: "checkmark.circle.fill")
                        .font(.caption2)
                        .foregroundColor(.green)
                    Label("\(reviewAgainCount)", systemImage: "arrow.counterclockwise.circle.fill")
                        .font(.caption2)
                        .foregroundColor(.orange)
                }
            }
        }
        .padding(.horizontal, ThemeConstants.spacingM)
        .padding(.top, ThemeConstants.spacingS)
    }

    // MARK: - Card

    private var cardView: some View {
        let cardIdx = displayOrder[currentIndex]
        let card = cards[cardIdx]

        return VStack(spacing: 0) {
            progressView

            // The flippable card
            ZStack {
                // Front (question)
                cardFace(
                    label: "QUESTION",
                    labelColor: .primaryBlue,
                    content: card.question,
                    icon: "questionmark.circle"
                )
                .opacity(isFlipped ? 0 : 1)
                .rotation3DEffect(
                    .degrees(isFlipped ? 180 : 0),
                    axis: (x: 0, y: 1, z: 0)
                )

                // Back (answer)
                cardFace(
                    label: "ANSWER",
                    labelColor: .green,
                    content: card.answer,
                    icon: "lightbulb.fill"
                )
                .opacity(isFlipped ? 1 : 0)
                .rotation3DEffect(
                    .degrees(isFlipped ? 0 : -180),
                    axis: (x: 0, y: 1, z: 0)
                )
            }
            .animation(.easeInOut(duration: 0.4), value: isFlipped)
            .onTapGesture { withAnimation { isFlipped.toggle() } }
            .padding(ThemeConstants.spacingM)

            if !isFlipped {
                Text("Tap card to reveal answer")
                    .font(.caption2)
                    .foregroundColor(.textSecondary.opacity(0.6))
                    .padding(.bottom, ThemeConstants.spacingS)
            }
        }
    }

    private func cardFace(label: String, labelColor: Color, content: String, icon: String) -> some View {
        VStack(alignment: .leading, spacing: ThemeConstants.spacingS) {
            HStack(spacing: 6) {
                Image(systemName: icon)
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(labelColor)
                Text(label)
                    .font(.system(size: 10, weight: .bold, design: .rounded))
                    .foregroundColor(labelColor)
                    .tracking(1.2)
            }

            ScrollView {
                Text(noteInlineMarkdown(content))
                    .font(.callout)
                    .foregroundColor(.textPrimary)
                    .lineSpacing(3)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(ThemeConstants.spacingM)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(Color.textPrimary.opacity(0.03))
        .clipShape(RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusSmall))
        .overlay(
            RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusSmall)
                .stroke(labelColor.opacity(0.25), lineWidth: 1)
        )
    }

    // MARK: - Controls

    private var controlsView: some View {
        HStack(spacing: ThemeConstants.spacingM) {
            // Review Again
            Button(action: markReviewAgain) {
                Label("Review Again", systemImage: "arrow.counterclockwise")
                    .font(.callout.weight(.medium))
                    .foregroundColor(.orange)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 10)
                    .background(Color.orange.opacity(0.1))
                    .clipShape(RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusSmall))
                    .overlay(
                        RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusSmall)
                            .stroke(Color.orange.opacity(0.3), lineWidth: 1)
                    )
            }
            .buttonStyle(.plain)
            .disabled(!isFlipped)
            .opacity(isFlipped ? 1 : 0.4)

            // Got It
            Button(action: markGotIt) {
                Label("Got It", systemImage: "checkmark")
                    .font(.callout.weight(.medium))
                    .foregroundColor(.green)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 10)
                    .background(Color.green.opacity(0.1))
                    .clipShape(RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusSmall))
                    .overlay(
                        RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusSmall)
                            .stroke(Color.green.opacity(0.3), lineWidth: 1)
                    )
            }
            .buttonStyle(.plain)
            .disabled(!isFlipped)
            .opacity(isFlipped ? 1 : 0.4)
        }
        .padding(ThemeConstants.spacingM)
    }

    // MARK: - Completion

    private var completionView: some View {
        VStack(spacing: ThemeConstants.spacingL) {
            Spacer()

            Image(systemName: "trophy.fill")
                .font(.system(size: 40))
                .foregroundColor(.yellow)

            Text("Study Complete!")
                .font(.title2.weight(.bold))
                .foregroundColor(.textPrimary)

            VStack(spacing: 6) {
                HStack(spacing: 16) {
                    VStack {
                        Text("\(gotItCount)")
                            .font(.title.weight(.bold))
                            .foregroundColor(.green)
                        Text("Got It")
                            .font(.caption)
                            .foregroundColor(.textSecondary)
                    }
                    VStack {
                        Text("\(reviewAgainCount)")
                            .font(.title.weight(.bold))
                            .foregroundColor(.orange)
                        Text("Review")
                            .font(.caption)
                            .foregroundColor(.textSecondary)
                    }
                }

                let total = gotItCount + reviewAgainCount
                let pct = total > 0 ? Int(Double(gotItCount) / Double(total) * 100) : 0
                Text("\(pct)% mastery")
                    .font(.callout.weight(.medium))
                    .foregroundColor(.textSecondary)
                    .padding(.top, 4)
            }

            if !reviewQueue.isEmpty {
                Button(action: startReviewRound) {
                    Label("Review \(reviewQueue.count) cards again", systemImage: "arrow.counterclockwise")
                        .font(.callout.weight(.semibold))
                        .foregroundColor(.primaryBlue)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 8)
                        .background(Color.primaryBlue.opacity(0.12))
                        .clipShape(RoundedRectangle(cornerRadius: ThemeConstants.cornerRadiusSmall))
                }
                .buttonStyle(.plain)
            }

            Button(action: { onClose?() }) {
                Text("Done")
                    .font(.callout.weight(.medium))
                    .foregroundColor(.textSecondary)
            }
            .buttonStyle(.plain)

            Spacer()
        }
        .padding(ThemeConstants.spacingM)
    }

    // MARK: - Empty

    private var emptyView: some View {
        VStack(spacing: ThemeConstants.spacingM) {
            Spacer()
            Image(systemName: "rectangle.on.rectangle.slash")
                .font(.system(size: 30))
                .foregroundColor(.textSecondary.opacity(0.5))
            Text("No flashcards found")
                .font(.callout)
                .foregroundColor(.textSecondary)
            Text("Expected format: **Q:** question / **A:** answer, separated by ---")
                .font(.caption)
                .foregroundColor(.textSecondary.opacity(0.7))
                .multilineTextAlignment(.center)
            Spacer()
        }
        .padding(ThemeConstants.spacingM)
    }

    // MARK: - Actions

    private func markGotIt() {
        gotItCount += 1
        advanceCard()
    }

    private func markReviewAgain() {
        reviewAgainCount += 1
        reviewQueue.append(displayOrder[currentIndex])
        advanceCard()
    }

    private func advanceCard() {
        withAnimation(.easeInOut(duration: 0.2)) {
            isFlipped = false
        }

        DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) {
            if currentIndex + 1 < displayOrder.count {
                currentIndex += 1
            } else {
                isComplete = true
            }
        }
    }

    private func toggleShuffle() {
        isShuffled.toggle()
        if isShuffled {
            displayOrder = Array(cards.indices).shuffled()
        } else {
            displayOrder = Array(cards.indices)
        }
        // Reset study progress
        currentIndex = 0
        gotItCount = 0
        reviewAgainCount = 0
        reviewQueue = []
        isComplete = false
        isFlipped = false
    }

    private func startReviewRound() {
        displayOrder = reviewQueue
        reviewQueue = []
        currentIndex = 0
        gotItCount = 0
        reviewAgainCount = 0
        isComplete = false
        isFlipped = false
    }
}
