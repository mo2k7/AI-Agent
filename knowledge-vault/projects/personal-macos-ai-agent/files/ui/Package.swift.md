# File Doc: `ui/Package.swift`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `ui/Package.swift` |
| Doc Path | `projects/personal-macos-ai-agent/files/ui/Package.swift.md` |
| Language | Swift |
| File Role | Swift Package Manager Configuration |
| Ownership | Core Team |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-02-07 |
| Last Major Edit (YYYY-MM-DD) | 2026-02-07 |
| Modified By | AI Agent (Codex) |
| WHY (Reason for last change) | Added explicit `swift-testing` dependency and test-target integration to restore runnable Swift tests |
| Lines of Code (LOC) | 47 |
| Cyclomatic Complexity | N/A (configuration) |
| Test Coverage | N/A |

---

## Purpose & Responsibilities

### What this file does
**Single-sentence summary:**
Defines the Swift Package Manager configuration for the AI Agent UI macOS application.

**Detailed responsibilities:**
- Specifies minimum platform requirement (macOS 14.0)
- Defines single executable product `AIAgentApp`
- Configures Swift strict concurrency checking
- Includes asset resources from `Assets.xcassets`
- Enables upcoming Swift features

### What this file must NOT do (boundaries)
**Out of scope:**
- Xcode project settings (this is SPM-based)
- CocoaPods or Carthage configuration
- External dependencies (all SwiftUI/AppKit are system frameworks)

---

## Configuration Details

### Package Information
| Field | Value |
|---|---|
| Name | `AIAgentUI` |
| Swift Tools Version | 6.0 |
| Platforms | macOS 14.0+ |

### Products
| Product | Type | Targets | Purpose |
|---|---|---|---|
| `AIAgentApp` | executable | `AIAgentApp` | Main macOS application |

### Targets
| Target | Type | Path | Dependencies | Resources |
|---|---|---|---|---|
| `AIAgentApp` | executable | `AIAgentUI/` | None | `Assets.xcassets` |
| `AIAgentUITests` | test | `Tests/AIAgentUITests/` | `AIAgentApp`, `Testing` | None |

### Swift Settings
| Setting | Value | Purpose |
|---|---|---|
| `StrictConcurrency` | `complete` | Full Swift 6 concurrency checking |
| `InternalImportsByDefault` | enabled | Upcoming Swift feature |

---

## Build Commands

### Build the Application
```bash
cd ui
swift build
```

### Build Release Version
```bash
cd ui
swift build -c release
```

### Run the Application
```bash
cd ui
swift run AIAgentApp
```

### Clean Build
```bash
cd ui
swift package clean
```

---

## Configuration Source

```swift
// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "AIAgentUI",
    platforms: [
        .macOS(.v14)
    ],
    products: [
        .executable(
            name: "AIAgentApp",
            targets: ["AIAgentApp"]
        ),
    ],
    dependencies: [
        .package(url: "https://github.com/swiftlang/swift-testing.git", from: "0.6.0"),
    ],
    targets: [
        .executableTarget(
            name: "AIAgentApp",
            dependencies: [],
            path: "AIAgentUI",
            exclude: [
                "App/Info.plist"
            ],
            resources: [
                .process("Resources/Assets.xcassets")
            ],
            swiftSettings: [
                .enableExperimentalFeature("StrictConcurrency=complete"),
                .enableUpcomingFeature("InternalImportsByDefault"),
            ]
        ),
        .testTarget(
            name: "AIAgentUITests",
            dependencies: [
                "AIAgentApp",
                .product(name: "Testing", package: "swift-testing"),
            ],
            path: "Tests/AIAgentUITests"
        )
    ]
)
```

---

## Platform Requirements

### macOS 14 (Sonoma) Features Used
| Feature | Usage | Fallback if Unavailable |
|---|---|---|
| `onKeyPress` modifier | Keyboard handling | Not available on macOS 13 |
| `#Preview` macro | SwiftUI previews | Use `PreviewProvider` (currently used) |
| Material effects | Glass UI | Would need custom implementation |
| `@Observable` | State management | Use `@ObservableObject` |

### Why macOS 14 Minimum
1. **`onKeyPress`** - Used in `InputField.swift` for keyboard handling
2. **StrictConcurrency** - Full Swift 6 concurrency requires modern runtime
3. **SwiftUI improvements** - Better material/blur support
4. **Network framework** - Improved Unix socket support

---

## Migration Notes

### From Xcode Project to SPM
The original plan called for `AIAgentUI.xcodeproj`, but SPM was chosen because:
1. Simpler configuration
2. No Xcode dependency for builds
3. Better CI/CD integration
4. Command-line build support

### PreviewProvider vs #Preview
Due to SPM limitations, `#Preview` macros were replaced with `PreviewProvider` structs:
```swift
// Instead of:
#Preview { MyView() }

// Use:
struct MyView_Previews: PreviewProvider {
    static var previews: some View {
        MyView()
    }
}
```

---

## Related Documentation

### Related Files
| File Path | Relationship | Why Related |
|---|---|---|
| `ui/AIAgentUI/App/AIAgentUIApp.swift` | Entry point | Main app file |
| `ui/AIAgentUI/Resources/Assets.xcassets/` | Resource | Asset catalog |
| `ui/AIAgentUI/` | Source directory | All source files |

---

## Maintainer Notes

### When to Update This File
- [ ] When adding external dependencies
- [ ] When changing minimum platform version
- [ ] When adding new targets (e.g., tests)
- [ ] When modifying Swift settings

### Adding Test Target
```swift
.testTarget(
    name: "AIAgentUITests",
    dependencies: [
        "AIAgentApp",
        .product(name: "Testing", package: "swift-testing"),
    ],
    path: "Tests/AIAgentUITests"
)
```

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-01-18 | AI Agent (Codex) | Dependency refresh | Updated Swift tools version to 6.0 and strict concurrency settings | Medium |
| 2026-01-18 | AI Assistant | Initial creation | Created SPM configuration | New file |
| 2026-01-18 | AI Assistant | Build fix | Updated to macOS 14, single target | Build compatibility |
| 2026-02-07 | AI Agent (Codex) | Swift test enablement | Added explicit `swift-testing` dependency and test target dependency to restore executable Swift tests in current toolchain | High |
| 2026-01-18 | AI Agent (Codex) | SPM test path fix | Updated test target path to Tests/AIAgentUITests | Low |
