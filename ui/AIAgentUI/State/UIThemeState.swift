//
//  UIThemeState.swift
//  AIAgentUI
//

import SwiftUI
import Combine

/// Manages all UI styling and animation preferences to decouple layout updates
/// from global app state changes.
@MainActor
final class UIThemeState: ObservableObject {
    static let shared = UIThemeState()

    private static let responsePresentationStyleKey = "responsePresentationStyle"
    private static let readableProHighContrastKey = "readableProHighContrastEnabled"
    private static let streamingAnimationStyleKey = "streamingAnimationStyle"

    /// Visual presentation style for rendered assistant responses.
    @Published var responsePresentationStyle: ResponsePresentationStyle {
        didSet {
            UserDefaults.standard.set(
                responsePresentationStyle.rawValue,
                forKey: Self.responsePresentationStyleKey
            )
        }
    }

    /// Additional contrast boost for the Readable Pro presentation style.
    @Published var readableProHighContrastEnabled: Bool {
        didSet {
            UserDefaults.standard.set(
                readableProHighContrastEnabled,
                forKey: Self.readableProHighContrastKey
            )
        }
    }

    /// Streaming animation style for in-progress assistant responses.
    @Published var streamingAnimationStyle: StreamingAnimationStyle {
        didSet {
            UserDefaults.standard.set(
                streamingAnimationStyle.rawValue,
                forKey: Self.streamingAnimationStyleKey
            )
        }
    }

    private init() {
        let defaults = UserDefaults.standard
        let storedStyle = defaults.string(forKey: Self.responsePresentationStyleKey) ?? ""
        self.responsePresentationStyle = ResponsePresentationStyle(rawValue: storedStyle) ?? .readablePro

        self.readableProHighContrastEnabled = defaults.bool(forKey: Self.readableProHighContrastKey)
        // If the key is not present, UserDefaults returns false. Let's make the default true if it's nil.
        if defaults.object(forKey: Self.readableProHighContrastKey) == nil {
            self.readableProHighContrastEnabled = true
        }

        let storedAnim = defaults.string(forKey: Self.streamingAnimationStyleKey) ?? ""
        self.streamingAnimationStyle = StreamingAnimationStyle(rawValue: storedAnim) ?? .waveReveal
    }
}
