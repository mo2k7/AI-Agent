#if os(macOS)
//
//  EdgeSnapping.swift
//  AIAgentUI
//
//  Created for Personal macOS AI Agent
//  Status: Active - Window edge detection and snapping
//

import Foundation
import AppKit
import QuartzCore

/// Handles edge detection and snapping for the floating panel
final class EdgeSnapping {
    
    // MARK: - Constants
    
    /// Distance threshold (in points) for edge snapping
    static let snapThreshold: CGFloat = 20.0
    
    /// Margin from edge when snapped
    static let edgeMargin: CGFloat = 10.0
    
    /// Animation duration for snap
    static let snapDuration: TimeInterval = 0.25
    
    // MARK: - Edge Types
    
    /// Screen edge positions
    enum Edge: Equatable {
        case left
        case right
        case top
        case bottom
        case topLeft
        case topRight
        case bottomLeft
        case bottomRight
        case none
    }
    
    // MARK: - Detection
    
    /// Detects which edge(s) the panel is near
    /// - Parameters:
    ///   - frame: The panel's current frame
    ///   - screen: The screen's visible frame
    /// - Returns: The nearest edge, or .none if not near any edge
    static func detectNearestEdge(frame: NSRect, screen: NSRect) -> Edge {
        let distanceToLeft = frame.minX - screen.minX
        let distanceToRight = screen.maxX - frame.maxX
        let distanceToTop = screen.maxY - frame.maxY
        let distanceToBottom = frame.minY - screen.minY
        
        // Check corners first
        if distanceToLeft <= snapThreshold && distanceToTop <= snapThreshold {
            return .topLeft
        }
        if distanceToRight <= snapThreshold && distanceToTop <= snapThreshold {
            return .topRight
        }
        if distanceToLeft <= snapThreshold && distanceToBottom <= snapThreshold {
            return .bottomLeft
        }
        if distanceToRight <= snapThreshold && distanceToBottom <= snapThreshold {
            return .bottomRight
        }
        
        // Check edges
        let minDistance = min(distanceToLeft, distanceToRight, distanceToTop, distanceToBottom)
        
        if minDistance > snapThreshold {
            return .none
        }
        
        switch minDistance {
        case distanceToLeft:
            return .left
        case distanceToRight:
            return .right
        case distanceToTop:
            return .top
        case distanceToBottom:
            return .bottom
        default:
            return .none
        }
    }
    
    /// Calculates the snap position for a given edge
    /// - Parameters:
    ///   - edge: The edge to snap to
    ///   - panelSize: The panel's size
    ///   - screen: The screen's visible frame
    /// - Returns: The origin point for the snapped position
    static func snapPosition(for edge: Edge, panelSize: NSSize, screen: NSRect) -> NSPoint? {
        switch edge {
        case .left:
            return NSPoint(
                x: screen.minX + edgeMargin,
                y: screen.midY - panelSize.height / 2
            )
            
        case .right:
            return NSPoint(
                x: screen.maxX - panelSize.width - edgeMargin,
                y: screen.midY - panelSize.height / 2
            )
            
        case .top:
            return NSPoint(
                x: screen.midX - panelSize.width / 2,
                y: screen.maxY - panelSize.height - edgeMargin
            )
            
        case .bottom:
            return NSPoint(
                x: screen.midX - panelSize.width / 2,
                y: screen.minY + edgeMargin
            )
            
        case .topLeft:
            return NSPoint(
                x: screen.minX + edgeMargin,
                y: screen.maxY - panelSize.height - edgeMargin
            )
            
        case .topRight:
            return NSPoint(
                x: screen.maxX - panelSize.width - edgeMargin,
                y: screen.maxY - panelSize.height - edgeMargin
            )
            
        case .bottomLeft:
            return NSPoint(
                x: screen.minX + edgeMargin,
                y: screen.minY + edgeMargin
            )
            
        case .bottomRight:
            return NSPoint(
                x: screen.maxX - panelSize.width - edgeMargin,
                y: screen.minY + edgeMargin
            )
            
        case .none:
            return nil
        }
    }
    
    /// Checks if a position would be off-screen and returns a corrected position
    /// - Parameters:
    ///   - frame: The proposed frame
    ///   - screen: The screen's visible frame
    /// - Returns: A corrected frame that is fully on screen
    static func constrainToScreen(frame: NSRect, screen: NSRect) -> NSRect {
        var corrected = frame
        
        // Constrain horizontally
        if corrected.minX < screen.minX + edgeMargin {
            corrected.origin.x = screen.minX + edgeMargin
        } else if corrected.maxX > screen.maxX - edgeMargin {
            corrected.origin.x = screen.maxX - corrected.width - edgeMargin
        }
        
        // Constrain vertically
        if corrected.minY < screen.minY + edgeMargin {
            corrected.origin.y = screen.minY + edgeMargin
        } else if corrected.maxY > screen.maxY - edgeMargin {
            corrected.origin.y = screen.maxY - corrected.height - edgeMargin
        }
        
        return corrected
    }
}

// MARK: - Panel Position Manager

/// Manages panel position and edge snapping behavior
@MainActor
final class PanelPositionManager {
    
    // MARK: - Properties
    
    /// Currently snapped edge
    private(set) var currentEdge: EdgeSnapping.Edge = .none
    
    /// Last free-floating position (not snapped)
    private var lastFreePosition: NSPoint?
    
    /// Whether snapping is enabled
    var isSnappingEnabled: Bool = true

    /// Whether panel movement/snapping animations are enabled
    var animationsEnabled: Bool = true

    /// Whether the panel is currently being dragged
    private var isDragging: Bool = false

    /// Edge the drag started from (if snapped)
    private var dragStartedFromEdge: EdgeSnapping.Edge = .none

    /// Recent position samples for velocity calculation
    private var positionHistory: [(position: NSPoint, timestamp: TimeInterval)] = []

    /// Velocity threshold to allow snapping (points per second)
    private let snapVelocityThreshold: CGFloat = 500

    /// UserDefaults key for persisted panel frame
    private static let positionKey = "panelPosition"
    
    // MARK: - Singleton
    
    static let shared = PanelPositionManager()
    private init() {}
    
    // MARK: - Methods
    
    /// Called when the panel is being dragged
    /// - Parameter panel: The panel being dragged
    func panelDidMove(_ panel: NSPanel) {
        guard isSnappingEnabled else { return }
        
        if !isDragging {
            isDragging = true
            dragStartedFromEdge = currentEdge
            positionHistory.removeAll()
        }
        
        if currentEdge != .none {
            currentEdge = .none
        }
        
        recordPosition(panel.frame.origin)
    }
    
    /// Called when the panel drag ends
    /// - Parameter panel: The panel that was dragged
    func panelDragEnded(_ panel: NSPanel) {
        guard let screen = panel.screen?.visibleFrame ?? NSScreen.main?.visibleFrame else {
            resetDragState()
            return
        }

        let velocity = calculateDragVelocity()
        let edge = EdgeSnapping.detectNearestEdge(frame: panel.frame, screen: screen)
        let shouldSnap = isSnappingEnabled && velocity < snapVelocityThreshold && edge != .none

        if shouldSnap {
            let storeLastPosition = dragStartedFromEdge == .none
            snapTo(panel: panel, edge: edge, storeLastPosition: storeLastPosition)
        } else {
            // Ensure panel is on screen
            let constrained = EdgeSnapping.constrainToScreen(frame: panel.frame, screen: screen)
            if constrained != panel.frame {
                if snapAnimationDuration > 0 {
                    NSAnimationContext.runAnimationGroup { context in
                        context.duration = snapAnimationDuration
                        context.timingFunction = AnimationConstants.appKitTimingFunction()
                        panel.animator().setFrame(constrained, display: true)
                    }
                } else {
                    panel.setFrame(constrained, display: true)
                }
            }
            currentEdge = .none
            lastFreePosition = constrained.origin
            saveFrame(constrained)
        }

        resetDragState()
    }

    /// Called when the panel finishes resizing
    /// - Parameter panel: The panel that was resized
    func panelResizeEnded(_ panel: NSPanel) {
        guard let screen = panel.screen?.visibleFrame ?? NSScreen.main?.visibleFrame else { return }
        let constrained = EdgeSnapping.constrainToScreen(frame: panel.frame, screen: screen)
        if constrained != panel.frame {
            if snapAnimationDuration > 0 {
                NSAnimationContext.runAnimationGroup { context in
                    context.duration = snapAnimationDuration
                    context.timingFunction = AnimationConstants.appKitTimingFunction()
                    panel.animator().setFrame(constrained, display: true)
                }
            } else {
                panel.setFrame(constrained, display: true)
            }
        }
        saveFrame(constrained)
    }
    
    /// Returns the panel to its last free position
    /// - Parameter panel: The panel to restore
    func restoreLastPosition(_ panel: NSPanel) {
        guard let position = lastFreePosition else { return }

        if snapAnimationDuration > 0 {
            NSAnimationContext.runAnimationGroup { context in
                context.duration = snapAnimationDuration
                context.timingFunction = AnimationConstants.appKitTimingFunction()
                panel.animator().setFrameOrigin(position)
            }
        } else {
            panel.setFrameOrigin(position)
        }
        currentEdge = .none
        saveFrame(NSRect(origin: position, size: panel.frame.size))
    }
    
    /// Snaps the panel to a specific edge
    /// - Parameters:
    ///   - panel: The panel to snap
    ///   - edge: The edge to snap to
    func snapTo(panel: NSPanel, edge: EdgeSnapping.Edge) {
        snapTo(panel: panel, edge: edge, storeLastPosition: true)
    }

    private func snapTo(panel: NSPanel, edge: EdgeSnapping.Edge, storeLastPosition: Bool) {
        guard edge != .none else { return }
        guard let screen = panel.screen?.visibleFrame ?? NSScreen.main?.visibleFrame else { return }
        guard let position = EdgeSnapping.snapPosition(
            for: edge,
            panelSize: panel.frame.size,
            screen: screen
        ) else { return }
        
        // Store current position as last free position
        if storeLastPosition && currentEdge == .none {
            lastFreePosition = panel.frame.origin
        }

        if snapAnimationDuration > 0 {
            NSAnimationContext.runAnimationGroup { context in
                context.duration = snapAnimationDuration
                context.timingFunction = AnimationConstants.appKitTimingFunction()
                panel.animator().setFrameOrigin(position)
            }
        } else {
            panel.setFrameOrigin(position)
        }
        currentEdge = edge
        saveFrame(NSRect(origin: position, size: panel.frame.size))
    }
    
    /// Gets the default position for the panel
    /// - Parameter screen: The screen to position on
    /// - Returns: The default center-right position
    static func defaultPosition(for screen: NSRect, panelSize: NSSize) -> NSPoint {
        return NSPoint(
            x: screen.maxX - panelSize.width - EdgeSnapping.edgeMargin - 50,
            y: screen.midY - panelSize.height / 2
        )
    }

    /// Restores the panel position from user defaults
    /// - Parameter panel: The panel to restore
    /// - Returns: True if a saved position was applied
    func restorePosition(_ panel: NSPanel) -> Bool {
        guard let frameString = UserDefaults.standard.string(forKey: Self.positionKey) else {
            return false
        }
        let savedFrame = NSRectFromString(frameString)
        guard let screen = panel.screen?.visibleFrame ?? NSScreen.main?.visibleFrame else { return false }
        let constrained = EdgeSnapping.constrainToScreen(frame: savedFrame, screen: screen)
        panel.setFrame(constrained, display: false)
        return true
    }

    /// Saves the current panel frame to user defaults
    /// - Parameter panel: The panel to persist
    func savePosition(_ panel: NSPanel) {
        saveFrame(panel.frame)
    }

    private func saveFrame(_ frame: NSRect) {
        UserDefaults.standard.set(NSStringFromRect(frame), forKey: Self.positionKey)
    }

    private var snapAnimationDuration: TimeInterval {
        animationsEnabled ? EdgeSnapping.snapDuration : 0
    }

    private func recordPosition(_ position: NSPoint) {
        let now = CACurrentMediaTime()
        positionHistory.append((position, now))
        if positionHistory.count > 5 {
            positionHistory.removeFirst(positionHistory.count - 5)
        }
    }

    private func calculateDragVelocity() -> CGFloat {
        guard positionHistory.count >= 2 else { return 0 }
        guard let first = positionHistory.first,
              let last = positionHistory.last else {
            return 0
        }
        let timeDelta = last.timestamp - first.timestamp
        guard timeDelta > 0 else { return 0 }
        let distance = hypot(
            last.position.x - first.position.x,
            last.position.y - first.position.y
        )
        return distance / CGFloat(timeDelta)
    }

    private func resetDragState() {
        isDragging = false
        dragStartedFromEdge = .none
        positionHistory.removeAll()
    }
}
#endif
