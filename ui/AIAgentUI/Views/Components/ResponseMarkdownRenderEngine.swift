//
//  ResponseMarkdownRenderEngine.swift
//  AIAgentUI
//

import SwiftUI

@MainActor
final class ResponseInlineMarkdownCache {
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

actor ResponseMarkdownRenderEngine {
    static let shared = ResponseMarkdownRenderEngine()

    private struct CacheKey: Hashable {
        let style: ResponsePresentationStyle
        let text: String
    }

    private let maxEntries = 192
    private let maxCachedTextLength = 24_000
    private var storage: [CacheKey: [MarkdownBlock]] = [:]
    private var insertionOrder: [CacheKey] = []

    func parse(text: String, style: ResponsePresentationStyle) -> [MarkdownBlock] {
        if text.count > maxCachedTextLength {
            return NoteMarkdownParser.parse(text)
        }
        let key = CacheKey(style: style, text: text)
        if let cached = storage[key] {
            return cached
        }
        let parsed = NoteMarkdownParser.parse(text)
        if insertionOrder.count >= maxEntries, let evicted = insertionOrder.first {
            insertionOrder.removeFirst()
            storage.removeValue(forKey: evicted)
        }
        insertionOrder.append(key)
        storage[key] = parsed
        return parsed
    }
}
