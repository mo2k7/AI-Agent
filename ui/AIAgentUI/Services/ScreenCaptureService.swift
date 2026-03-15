#if os(macOS)
import CoreGraphics
import Vision
import AppKit
import ScreenCaptureKit

// MARK: - Result Type

/// Encapsulates a screen capture with OCR text and scaled image data.
struct ScreenCaptureResult: Sendable {
    let imageData: Data   // JPEG bytes (scaled to maxDimension)
    let ocrText: String   // Vision-framework OCR text
    let width: Int
    let height: Int
}
#endif

// MARK: - Errors

enum ScreenCaptureError: LocalizedError, Sendable {
    case captureFailedNoPermission
    case encodingFailed
    case noDisplayFound
    case unsupportedRuntime

    var errorDescription: String? {
        switch self {
        case .captureFailedNoPermission:
            return "Screen capture failed — screen recording permission may not be granted"
        case .encodingFailed:
            return "Failed to encode screenshot as JPEG"
        case .noDisplayFound:
            return "No display found to capture"
        case .unsupportedRuntime:
            return "Screen capture requires macOS 26 or newer runtime APIs"
        }
    }
}

// MARK: - Service

/// Read-only screen capture service using native ScreenCaptureKit + Vision.
///
/// Captures the full screen via `SCScreenshotManager`, runs accurate
/// OCR through Vision's text recognition APIs, and scales the image
/// down to a max dimension for efficient IPC transmission.
///
/// Production features:
/// - Dynamic Retina scale factor (not hardcoded × 2)
/// - Self-exclusion: excludes the AI Agent's own window from capture
/// - HDR screenshot presets on macOS 15+ (WWDC24)
/// - RecognizeDocumentsRequest for paragraph-level OCR on macOS 26+ (WWDC25)
final class ScreenCaptureService: Sendable {

    static let shared = ScreenCaptureService()

    /// Maximum pixel dimension (longest edge) for the transmitted image.
    /// Full-resolution is used for OCR; only the transmitted copy is scaled.
    private let maxDimension: CGFloat = 2048

    // MARK: - Capture

    /// Captures the full screen, runs OCR at native resolution, and returns
    /// a scaled JPEG plus the extracted text.
    ///
    /// - The agent's own window is excluded from the capture to avoid the
    ///   "hall of mirrors" effect and reduce token waste.
    /// - On macOS 15+, uses HDR screenshot presets for better detail.
    /// - On macOS 26+, uses `RecognizeDocumentsRequest` for paragraph-level OCR.
    ///
    /// - Throws: `ScreenCaptureError` if the capture or encoding fails.
    func captureScreen() async throws -> ScreenCaptureResult {
        guard #available(macOS 26, *) else {
            throw ScreenCaptureError.unsupportedRuntime
        }

        // 1. Get the main display + running applications via ScreenCaptureKit
        let content = try await SCShareableContent.excludingDesktopWindows(
            false, onScreenWindowsOnly: true
        )
        guard let display = content.displays.first else {
            throw ScreenCaptureError.noDisplayFound
        }

        // 2. Build a content filter that excludes our own app
        let selfApp = content.applications.first {
            $0.bundleIdentifier == Bundle.main.bundleIdentifier
        }
        let excludedApps = selfApp.map { [$0] } ?? []
        let filter = SCContentFilter(
            display: display,
            excludingApplications: excludedApps,
            exceptingWindows: []
        )

        // 3. Configure capture for HDR screenshot quality
        let config = SCStreamConfiguration(preset: .captureHDRScreenshotLocalDisplay)

        // Dynamic Retina scale factor (not hardcoded × 2)
        let scaleFactor = Int(NSScreen.main?.backingScaleFactor ?? 2.0)
        config.width = display.width * scaleFactor
        config.height = display.height * scaleFactor
        config.showsCursor = true

        // 4. Take the screenshot
        let cgImage = try await SCScreenshotManager.captureImage(
            contentFilter: filter, configuration: config
        )

        // 5. OCR at full resolution for best text recognition
        let ocrText = try await performOCR(on: cgImage)

        // 6. Scale for IPC / model input (keeps token cost sane)
        let scaled = scaleImage(cgImage, maxDimension: maxDimension)

        // 7. Encode as JPEG
        let bitmapRep = NSBitmapImageRep(cgImage: scaled)
        guard let jpegData = bitmapRep.representation(
            using: .jpeg,
            properties: [.compressionFactor: 0.85]
        ) else {
            throw ScreenCaptureError.encodingFailed
        }

        return ScreenCaptureResult(
            imageData: jpegData,
            ocrText: ocrText,
            width: scaled.width,
            height: scaled.height
        )
    }

    // MARK: - Private Helpers — OCR

    /// Performs OCR on the given image, using the best available API.
    ///
    /// - macOS 26+: `RecognizeDocumentsRequest` (WWDC25) — returns structured
    ///   paragraphs, tables, and semantic entities (emails, URLs, phones).
    private func performOCR(on image: CGImage) async throws -> String {
        guard #available(macOS 26, *) else {
            throw ScreenCaptureError.unsupportedRuntime
        }
        return try await performDocumentOCR(on: image)
    }

    /// Modern OCR using RecognizeDocumentsRequest (macOS 26+).
    /// Returns paragraph-grouped text with double-newline separators.
    @available(macOS 26, *)
    private func performDocumentOCR(on image: CGImage) async throws -> String {
        var request = RecognizeDocumentsRequest()
        request.textRecognitionOptions.useLanguageCorrection = true
        let observations = try await request.perform(on: image)
        let paragraphs = observations.first?.document.paragraphs
            .map { $0.transcript } ?? []
        return paragraphs.joined(separator: "\n\n")
    }

    // MARK: - Private Helpers — Image Scaling

    private func scaleImage(_ image: CGImage, maxDimension: CGFloat) -> CGImage {
        let w = CGFloat(image.width)
        let h = CGFloat(image.height)
        let longest = max(w, h)

        // No scaling needed if already within bounds
        if longest <= maxDimension { return image }

        let scale = maxDimension / longest
        let newW = Int(w * scale)
        let newH = Int(h * scale)

        guard let context = CGContext(
            data: nil,
            width: newW,
            height: newH,
            bitsPerComponent: image.bitsPerComponent,
            bytesPerRow: 0,
            space: image.colorSpace ?? CGColorSpaceCreateDeviceRGB(),
            bitmapInfo: image.bitmapInfo.rawValue
        ) else {
            return image  // Fallback: return unscaled
        }

        context.interpolationQuality = .high
        context.draw(image, in: CGRect(x: 0, y: 0, width: newW, height: newH))
        return context.makeImage() ?? image
    }
}
