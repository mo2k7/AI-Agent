//
//  DebugLogger.swift
//  AIAgentUI
//
//  Lightweight debug logging for IPC/session diagnostics.
//

import Foundation
import os

enum DebugLogger {
    private static let subsystem = "com.aiagent.ui"
    private static let logger = Logger(subsystem: subsystem, category: "ipc")

    static var isEnabled: Bool {
        let value = ProcessInfo.processInfo.environment["AI_AGENT_DEBUG_FRONTEND_LOGS"] ?? "0"
        return value == "1"
    }

    static func log(_ message: String, fields: [String: String] = [:]) {
        guard isEnabled else { return }
        let timestamp = ISO8601DateFormatter().string(from: Date())
        let metadata = fields
            .sorted(by: { $0.key < $1.key })
            .map { "\($0.key)=\($0.value)" }
            .joined(separator: " ")
        let payload = metadata.isEmpty ? message : "\(message) \(metadata)"
        logger.log("\(timestamp, privacy: .public) \(payload, privacy: .public)")
        print("[DEBUG] \(timestamp) \(payload)")
    }
}
