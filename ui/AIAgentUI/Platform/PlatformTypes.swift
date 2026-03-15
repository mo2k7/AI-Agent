import SwiftUI

#if os(macOS)
import AppKit
typealias PlatformImage = NSImage
typealias PlatformColor = NSColor
#elseif canImport(UIKit)
import UIKit
typealias PlatformImage = UIImage
typealias PlatformColor = UIColor
#endif

@MainActor
enum PlatformAppActions {
    static func terminate() {
        #if os(macOS)
        NSApplication.shared.terminate(nil)
        #endif
    }

    static func activate() {
        #if os(macOS)
        NSApp.activate(ignoringOtherApps: true)
        #endif
    }
}
