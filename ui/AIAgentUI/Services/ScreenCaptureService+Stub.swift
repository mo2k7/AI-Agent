#if !os(macOS)
import Foundation

struct ScreenCaptureResult: Sendable {
    let imageData: Data
    let ocrText: String
    let width: Int
    let height: Int
}

enum ScreenCaptureError: LocalizedError, Sendable {
    case unsupportedRuntime
    var errorDescription: String? { "Screen capture is not supported on this device." }
}

final class ScreenCaptureService: Sendable {
    static let shared = ScreenCaptureService()
    func captureScreen() async throws -> ScreenCaptureResult {
        throw ScreenCaptureError.unsupportedRuntime
    }
}
#endif
