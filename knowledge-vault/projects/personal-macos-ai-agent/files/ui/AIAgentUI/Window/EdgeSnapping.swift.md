# File Doc: `ui/AIAgentUI/Window/EdgeSnapping.swift`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `ui/AIAgentUI/Window/EdgeSnapping.swift` |
| Doc Path | `projects/personal-macos-ai-agent/files/ui/AIAgentUI/Window/EdgeSnapping.swift.md` |
| Language | Swift |
| File Role | Window Edge Detection and Snapping |
| Ownership | Core Team |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-01-18 |
| Last Major Edit (YYYY-MM-DD) | 2026-01-18 |
| Modified By | AI Agent (Codex) |
| WHY (Reason for last change) | Snap only on drag end with velocity gating and position persistence |
| Lines of Code (LOC) | 389 |
| Cyclomatic Complexity | Low |
| Test Coverage | 0% |

---

## Purpose & Responsibilities

### What this file does
**Single-sentence summary:**
Provides edge detection and snap positioning logic for the floating panel window.

**Detailed responsibilities:**
- Defines `EdgeSnapping.Edge` enum for screen edges and corners
- Implements `detectNearestEdge()` to find closest edge within threshold
- Calculates snap positions with `snapPosition(for:panelSize:screen:)`
- Constrains panel to screen bounds with `constrainToScreen()`
- Provides `PanelPositionManager` singleton for position tracking
- Tracks drag state and velocity for snap decisions
- Animates snap transitions after drag ends
- Persists/restores panel frame in user defaults
- Stores last free-floating position for restoration

### What this file must NOT do (boundaries)
**Out of scope:**
- Window creation/management (handled by `FloatingPanelController`)
- User input handling
- Global hotkey registration
- SwiftUI view rendering

### Who/what calls it
| Caller | Purpose | Frequency | Error Handling |
|---|---|---|---|
| `FloatingPanelController` | Position management | On window move/resize | N/A |

### What it calls
| Callee | Purpose | Error Handling | Fallback Strategy |
|---|---|---|---|
| `NSAnimationContext` | Smooth animations | N/A | N/A |
| `NSPanel` | Window positioning | N/A | N/A |
| `NSScreen` | Screen bounds | Nil check | Use main screen |
| `UserDefaults` | Persist frame | Optional read | Skip restore |

---

## Imports / Dependencies

### Framework Dependencies
| Framework | What's Used | Why Needed |
|---|---|---|
| Foundation | Basic types | Core functionality |
| AppKit | NSPanel, NSScreen, NSAnimationContext | Window management |
| QuartzCore | CACurrentMediaTime | Drag velocity calculation |

---

## Public Surface (Document EVERYTHING Exposed)

### Exports / Public Symbols
| Symbol | Type (func/class/const/type) | Visibility | Status | Brief Description |
|---|---|---|---|---|
| `EdgeSnapping` | class | public | Stable | Static utility methods |
| `EdgeSnapping.Edge` | enum | public | Stable | Edge/corner positions |
| `PanelPositionManager` | class | public | Stable | Position tracking singleton |

---

## Types (Classes / Structs / Enums / Interfaces)

### `EdgeSnapping`
| Metadata | Value |
|---|---|
| Kind | class |
| Purpose | Static utility class for edge detection and snapping |
| Thread-Safe | Yes (all static, stateless) |
| Immutable | N/A (no instances) |
| Serializable | No |

#### Static Constants
| Name | Type | Value | Purpose |
|---|---|---|---|
| `snapThreshold` | CGFloat | `20.0` | Distance in points to trigger snap |
| `edgeMargin` | CGFloat | `10.0` | Gap between panel and screen edge |
| `snapDuration` | TimeInterval | `0.25` | Animation duration in seconds |

#### Static Methods
| Method | Signature | Visibility | Parameters | Returns | Purpose |
|---|---|---|---|---|---|
| `detectNearestEdge` | `(frame: NSRect, screen: NSRect) -> Edge` | static | Panel frame, screen bounds | Nearest edge | Find closest edge within threshold |
| `snapPosition` | `(for: Edge, panelSize: NSSize, screen: NSRect) -> NSPoint?` | static | Edge, panel size, screen | Snap origin | Calculate snap position |
| `constrainToScreen` | `(frame: NSRect, screen: NSRect) -> NSRect` | static | Panel frame, screen | Constrained frame | Keep panel on screen |

---

### `EdgeSnapping.Edge`
| Metadata | Value |
|---|---|
| Kind | enum |
| Purpose | Screen edge and corner positions |
| Thread-Safe | Yes (immutable) |
| Immutable | Yes |
| Serializable | No |

#### Inheritance & Implementation
- **Extends:** N/A
- **Implements:** `Equatable`

#### Cases
| Case | Purpose | Snap Position |
|---|---|---|
| `left` | Left screen edge | Vertically centered on left |
| `right` | Right screen edge | Vertically centered on right |
| `top` | Top screen edge | Horizontally centered at top |
| `bottom` | Bottom screen edge | Horizontally centered at bottom |
| `topLeft` | Top-left corner | Top-left with margins |
| `topRight` | Top-right corner | Top-right with margins |
| `bottomLeft` | Bottom-left corner | Bottom-left with margins |
| `bottomRight` | Bottom-right corner | Bottom-right with margins |
| `none` | Not near any edge | No snapping |

---

### `PanelPositionManager`
| Metadata | Value |
|---|---|
| Kind | class |
| Purpose | Singleton for tracking and managing panel position |
| Thread-Safe | No (main thread only) |
| Immutable | No |
| Serializable | No |

#### Fields / Properties
| Name | Type | Visibility | Default | Required | Mutable | Purpose |
|---|---|---|---|---|---|---|
| `shared` | PanelPositionManager | static | Singleton | N/A | No | Global instance |
| `currentEdge` | EdgeSnapping.Edge | public(set) | `.none` | N/A | Yes | Currently snapped edge |
| `lastFreePosition` | NSPoint? | private | `nil` | No | Yes | Last non-snapped position |
| `isSnappingEnabled` | Bool | public | `true` | N/A | Yes | Enable/disable snapping |
| `isDragging` | Bool | private | `false` | No | Yes | Tracks active drag state |
| `dragStartedFromEdge` | EdgeSnapping.Edge | private | `.none` | No | Yes | Edge where drag began (if snapped) |
| `positionHistory` | `[(position: NSPoint, timestamp: TimeInterval)]` | private | `[]` | No | Yes | Recent position samples for velocity |
| `snapVelocityThreshold` | CGFloat | private | `500` | N/A | No | Points/sec cutoff for snapping |
| `positionKey` | String | private static | `"panelPosition"` | N/A | No | UserDefaults key for frame persistence |

#### Methods
| Method | Signature | Visibility | Parameters | Returns | Purpose |
|---|---|---|---|---|---|
| `panelDidMove` | `(_ panel: NSPanel)` | public | Panel | None | Called on window move |
| `panelDragEnded` | `(_ panel: NSPanel)` | public | Panel | None | Called when drag ends |
| `panelResizeEnded` | `(_ panel: NSPanel)` | public | Panel | None | Constrains and saves after resize |
| `restoreLastPosition` | `(_ panel: NSPanel)` | public | Panel | None | Return to free position |
| `snapTo` | `(panel: NSPanel, edge: Edge)` | public | Panel, edge | None | Snap programmatically |
| `defaultPosition` | `(for: NSRect, panelSize: NSSize) -> NSPoint` | static | Screen, size | Default position | Initial position |
| `restorePosition` | `(_ panel: NSPanel) -> Bool` | public | Panel | Bool | Restore persisted frame if available |
| `savePosition` | `(_ panel: NSPanel)` | public | Panel | None | Persist current panel frame |

---

## Algorithms & Logic

### Edge Detection Algorithm
```swift
static func detectNearestEdge(frame: NSRect, screen: NSRect) -> Edge {
    let distanceToLeft = frame.minX - screen.minX
    let distanceToRight = screen.maxX - frame.maxX
    let distanceToTop = screen.maxY - frame.maxY
    let distanceToBottom = frame.minY - screen.minY
    
    // Check corners first (have priority)
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
    case distanceToLeft: return .left
    case distanceToRight: return .right
    case distanceToTop: return .top
    case distanceToBottom: return .bottom
    default: return .none
    }
}
```

### Drag Velocity Calculation
```swift
private func calculateDragVelocity() -> CGFloat {
    guard positionHistory.count >= 2 else { return 0 }
    let first = positionHistory.first!
    let last = positionHistory.last!
    let timeDelta = last.timestamp - first.timestamp
    guard timeDelta > 0 else { return 0 }
    let distance = hypot(
        last.position.x - first.position.x,
        last.position.y - first.position.y
    )
    return distance / CGFloat(timeDelta)
}
```

### Snap Position Calculation
| Edge | X Position | Y Position |
|---|---|---|
| `left` | `screen.minX + edgeMargin` | `screen.midY - height/2` |
| `right` | `screen.maxX - width - edgeMargin` | `screen.midY - height/2` |
| `top` | `screen.midX - width/2` | `screen.maxY - height - edgeMargin` |
| `bottom` | `screen.midX - width/2` | `screen.minY + edgeMargin` |
| `topLeft` | `screen.minX + edgeMargin` | `screen.maxY - height - edgeMargin` |
| `topRight` | `screen.maxX - width - edgeMargin` | `screen.maxY - height - edgeMargin` |
| `bottomLeft` | `screen.minX + edgeMargin` | `screen.minY + edgeMargin` |
| `bottomRight` | `screen.maxX - width - edgeMargin` | `screen.minY + edgeMargin` |

### Screen Constraint
```swift
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
```

---

## Animation Implementation

### Snap Animation
Snapping is triggered only in `panelDragEnded` after drag velocity falls below the threshold and the panel is near an edge.

```swift
func snapTo(panel: NSPanel, edge: EdgeSnapping.Edge) {
    guard edge != .none else { return }
    guard let screen = panel.screen?.visibleFrame ?? NSScreen.main?.visibleFrame else { return }
    guard let position = EdgeSnapping.snapPosition(
        for: edge,
        panelSize: panel.frame.size,
        screen: screen
    ) else { return }
    
    // Store current position as last free position
    if currentEdge == .none {
        lastFreePosition = panel.frame.origin
    }
    
    NSAnimationContext.runAnimationGroup { context in
        context.duration = EdgeSnapping.snapDuration
        context.timingFunction = AnimationConstants.appKitTimingFunction()
        panel.animator().setFrameOrigin(position)
    }
    currentEdge = edge
}
```

### Restore Animation
```swift
func restoreLastPosition(_ panel: NSPanel) {
    guard let position = lastFreePosition else { return }
    
    NSAnimationContext.runAnimationGroup { context in
        context.duration = EdgeSnapping.snapDuration
        context.timingFunction = AnimationConstants.appKitTimingFunction()
        panel.animator().setFrameOrigin(position)
    }
    currentEdge = .none
}
```

---

## State Management

### Position State
| State | `currentEdge` | `lastFreePosition` |
|---|---|---|
| Free floating | `.none` | Current position |
| Snapped to edge | `.left`, `.right`, etc. | Previous free position |
| Being dragged | `.none` | Preserved until drag end |

### State Transitions
```
[Free] --drag--> [Dragging]
[Dragging] --release + slow + near edge--> [Snapped]
[Dragging] --release + fast OR not near edge--> [Free]
[Snapped] --drag away--> [Dragging]
[Snapped] --restore()--> [Free] (to lastFreePosition)
[Any] --snapTo(edge)--> [Snapped]
```

---

## Default Position

### Initial Position Calculation
```swift
static func defaultPosition(for screen: NSRect, panelSize: NSSize) -> NSPoint {
    return NSPoint(
        x: screen.maxX - panelSize.width - edgeMargin - 50,  // 50pt from right edge
        y: screen.midY - panelSize.height / 2  // Vertically centered
    )
}
```

This places the panel near the right edge, vertically centered - a common position for assistant panels.

---

## Example Usage

### Basic Snapping
```swift
// In FloatingPanelController
func windowDidMove(_ notification: Notification) {
    guard let panel = panel else { return }
    positionManager.panelDidMove(panel)
}

func windowDidEndLiveResize(_ notification: Notification) {
    guard let panel = panel else { return }
    positionManager.panelResizeEnded(panel)
}
```

### Drag End Handling
```swift
// FloatingPanelController schedules panelDragEnded once dragging stops
private func scheduleDragEnd() {
    dragEndWorkItem?.cancel()
    let workItem = DispatchWorkItem { [weak self] in
        guard let self = self, let panel = self.panel else { return }
        self.positionManager.panelDragEnded(panel)
    }
    dragEndWorkItem = workItem
    DispatchQueue.main.asyncAfter(deadline: .now() + 0.12, execute: workItem)
}
```

### Programmatic Snapping
```swift
// Snap to right edge
FloatingPanelController.shared.snapTo(edge: .right)

// Snap to top-right corner
FloatingPanelController.shared.snapTo(edge: .topRight)

// Return to free position
PanelPositionManager.shared.restoreLastPosition(panel)
```

### Disable Snapping
```swift
// Temporarily disable
PanelPositionManager.shared.isSnappingEnabled = false

// Re-enable
PanelPositionManager.shared.isSnappingEnabled = true
```

---

## Related Documentation

### Related Files
| File Path | Relationship | Why Related |
|---|---|---|
| `ui/AIAgentUI/Window/FloatingPanelController.swift` | Used by | Position management |
| `ui/AIAgentUI/Views/Styles/BlueTheme.swift` | Uses | ThemeConstants |

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-01-18 | AI Assistant | Initial implementation | Created edge snapping | New file |
| 2026-01-18 | AI Agent (Codex) | Drag jitter fix | Snap only on drag end with velocity gating and persisted frames | High |
