// swift-tools-version:6.0
// The swift-tools-version declares the minimum version of Swift required to build this package.

import PackageDescription

let package = Package(
    name: "AIAgentUI",
    platforms: [
        .macOS(.v14),
        .iOS(.v17)
    ],
    products: [
        .executable(
            name: "AIAgentApp",
            targets: ["AIAgentApp"]
        )
    ],
    dependencies: [
        .package(url: "https://github.com/swiftlang/swift-testing.git", from: "0.6.0"),
    ],
    targets: [
        // Main executable target with all UI components
        .executableTarget(
            name: "AIAgentApp",
            dependencies: [],
            path: "AIAgentUI",
            exclude: [
                "App/Info.plist",
                "App/Info-iOS.plist",
                "App/AIAgent.entitlements"
            ],
            resources: [
                .process("Resources/Assets.xcassets")
            ],
            swiftSettings: [
                .enableExperimentalFeature("StrictConcurrency=complete"),
                .enableUpcomingFeature("InternalImportsByDefault"),
            ]
        ),
        
        // Test target
        .testTarget(
            name: "AIAgentUITests",
            dependencies: [
                "AIAgentApp",
                .product(name: "Testing", package: "swift-testing"),
            ],
            path: "Tests/AIAgentUITests",
            swiftSettings: [
                .unsafeFlags(["-suppress-warnings"]),
            ]
        )
    ]
)
