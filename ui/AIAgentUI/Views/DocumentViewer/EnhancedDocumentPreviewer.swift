//
//  EnhancedDocumentPreviewer.swift
//  AIAgentUI
//
//  Created for Personal macOS AI Agent
//  Status: Active - Reliable cross-platform document/web content renderer
//

import SwiftUI
import WebKit

#if os(iOS)

/// Universal iOS content renderer using WKWebView.
/// Handles local files (including iCloud Drive), web URLs, and any content type.
/// Never pre-checks file existence — always attempts to load and handles errors gracefully.
struct UniversalWebView: UIViewRepresentable {
    let url: URL
    
    func makeCoordinator() -> Coordinator {
        Coordinator()
    }
    
    func makeUIView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.allowsInlineMediaPlayback = true
        
        let webView = WKWebView(frame: .zero, configuration: config)
        webView.navigationDelegate = context.coordinator
        webView.backgroundColor = .systemBackground
        webView.scrollView.backgroundColor = .systemBackground
        webView.isOpaque = true
        
        context.coordinator.webView = webView
        loadContent(into: webView, coordinator: context.coordinator)
        
        // Listen for search requests
        let observer = NotificationCenter.default.addObserver(
            forName: .documentSearchRequested,
            object: nil,
            queue: .main
        ) { [weak webView] notification in
            guard let webView = webView,
                  let query = notification.userInfo?["query"] as? String,
                  !query.isEmpty else { return }
            if #available(iOS 16.0, *) {
                webView.find(query, configuration: WKFindConfiguration(), completionHandler: { _ in })
            } else {
                webView.evaluateJavaScript("window.find('\(query)')")
            }
        }
        context.coordinator.searchObserver = observer
        
        return webView
    }
    
    func updateUIView(_ webView: WKWebView, context: Context) {
        guard context.coordinator.currentURL != url else { return }
        loadContent(into: webView, coordinator: context.coordinator)
    }
    
    static func dismantleUIView(_ webView: WKWebView, coordinator: Coordinator) {
        if let observer = coordinator.searchObserver {
            NotificationCenter.default.removeObserver(observer)
            coordinator.searchObserver = nil
        }
        webView.stopLoading()
        if let tempURL = coordinator.tempFileURL {
            try? FileManager.default.removeItem(at: tempURL)
        }
    }
    
    private func loadContent(into webView: WKWebView, coordinator: Coordinator) {
        coordinator.currentURL = url
        coordinator.loadFailed = false
        
        if url.isFileURL {
            // For iCloud Drive files: trigger download if needed
            if url.path.contains("Mobile Documents") || url.path.contains("CloudDocs") {
                try? FileManager.default.startDownloadingUbiquitousItem(at: url)
            }
            
            // iOS Sandbox Fix: WKWebView cannot load files from outside the app sandbox (like iCloud/Files app).
            // We must copy the file into our app's Temp directory first.
            let tempDir = FileManager.default.temporaryDirectory
            let tempFileURL = tempDir.appendingPathComponent(UUID().uuidString + "_" + url.lastPathComponent)
            
            do {
                if FileManager.default.fileExists(atPath: tempFileURL.path) {
                    try FileManager.default.removeItem(at: tempFileURL)
                }
                try FileManager.default.copyItem(at: url, to: tempFileURL)
                coordinator.tempFileURL = tempFileURL
                
                // Now load the local copy which is safely inside our sandbox
                webView.loadFileURL(tempFileURL, allowingReadAccessTo: tempDir)
            } catch {
                coordinator.handleError(error, in: webView)
            }
        } else {
            // Remote URL — load directly
            webView.load(URLRequest(url: url, cachePolicy: .returnCacheDataElseLoad, timeoutInterval: 30))
        }
    }
    
    class Coordinator: NSObject, WKNavigationDelegate {
        weak var webView: WKWebView?
        var searchObserver: NSObjectProtocol?
        var currentURL: URL?
        var tempFileURL: URL?
        var loadFailed = false
        
        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            // Successfully loaded — nothing to do
        }
        
        func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
            handleError(error, in: webView)
        }
        
        func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
            handleError(error, in: webView)
        }
        
        func handleError(_ error: Error, in webView: WKWebView) {
            // Prevent infinite loop: if we already showed error page, don't try again
            guard !loadFailed else { return }
            loadFailed = true
            
            let urlStr = currentURL?.absoluteString ?? "Unknown"
            let errMsg = error.localizedDescription
            print("[DocumentPreviewer] Load failed for \(urlStr): \(errMsg)")
            
            let html = """
            <!DOCTYPE html>
            <html>
            <head>
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>
                    * { margin: 0; padding: 0; box-sizing: border-box; }
                    body {
                        font-family: -apple-system, BlinkMacSystemFont, sans-serif;
                        background: #1C1C1E; color: #FFF;
                        display: flex; align-items: center; justify-content: center;
                        min-height: 100vh; padding: 32px; text-align: center;
                    }
                    .container { max-width: 400px; }
                    .icon { font-size: 48px; margin-bottom: 16px; opacity: 0.5; }
                    h1 { font-size: 18px; margin-bottom: 8px; }
                    p { font-size: 14px; color: #8E8E93; line-height: 1.4; margin-bottom: 16px; }
                    .url { font-size: 11px; color: #636366; word-break: break-all; padding: 10px; background: rgba(255,255,255,0.05); border-radius: 8px; }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="icon">⚠️</div>
                    <h1>Unable to Load Content</h1>
                    <p>\(errMsg.replacingOccurrences(of: "<", with: "&lt;"))</p>
                    <div class="url">\(urlStr.replacingOccurrences(of: "<", with: "&lt;"))</div>
                </div>
            </body>
            </html>
            """
            webView.loadHTMLString(html, baseURL: nil)
        }
    }
}

#elseif os(macOS)
import Quartz

/// Wrapper for macOS QuickLook
struct QuickLookPreview: NSViewRepresentable {
    let url: URL
    
    func makeNSView(context: Context) -> QLPreviewView {
        guard let view = QLPreviewView(frame: .zero, style: .normal) else {
            return QLPreviewView()
        }
        view.autostarts = true
        view.previewItem = url as QLPreviewItem
        return view
    }
    
    func updateNSView(_ nsView: QLPreviewView, context: Context) {
        guard nsView.previewItem as? URL != url else { return }
        nsView.previewItem = url as QLPreviewItem
    }
}

/// Wrapper for macOS WebKit
struct WebViewPreview: NSViewRepresentable {
    let url: URL
    
    func makeCoordinator() -> Coordinator {
        Coordinator()
    }
    
    func makeNSView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.preferences.isTextInteractionEnabled = true
        
        let webView = WKWebView(frame: .zero, configuration: config)
        
        if url.isFileURL {
            webView.loadFileURL(url, allowingReadAccessTo: url.deletingLastPathComponent())
        } else {
            webView.load(URLRequest(url: url, cachePolicy: .returnCacheDataElseLoad))
        }
        
        let observer = NotificationCenter.default.addObserver(
            forName: .documentSearchRequested,
            object: nil,
            queue: .main
        ) { [weak webView] notification in
            guard let webView = webView,
                  let query = notification.userInfo?["query"] as? String else { return }
            if !query.isEmpty {
                if #available(macOS 11.0, *) {
                    webView.find(query, configuration: WKFindConfiguration(), completionHandler: { _ in })
                } else {
                    webView.evaluateJavaScript("window.find('\(query)')")
                }
            }
        }
        context.coordinator.searchObserver = observer
        
        return webView
    }
    
    func updateNSView(_ nsView: WKWebView, context: Context) {
        guard nsView.url != url else { return }
        if url.isFileURL {
            nsView.loadFileURL(url, allowingReadAccessTo: url.deletingLastPathComponent())
        } else {
            nsView.load(URLRequest(url: url, cachePolicy: .returnCacheDataElseLoad))
        }
    }
    
    static func dismantleNSView(_ nsView: WKWebView, coordinator: Coordinator) {
        if let observer = coordinator.searchObserver {
            NotificationCenter.default.removeObserver(observer)
            coordinator.searchObserver = nil
        }
        nsView.stopLoading()
    }
    
    class Coordinator {
        var searchObserver: NSObjectProtocol?
    }
}
#endif

/// A unified, cross-platform document previewer.
/// iOS: Uses WKWebView universally with iCloud Drive support
/// macOS: Uses QuickLook for local files, WebKit for web URLs
struct EnhancedDocumentPreviewer: View {
    let url: URL
    
    var body: some View {
        #if os(iOS)
        UniversalWebView(url: url)
        #elseif os(macOS)
        if url.isFileURL {
            QuickLookPreview(url: url)
        } else {
            WebViewPreview(url: url)
        }
        #endif
    }
}
