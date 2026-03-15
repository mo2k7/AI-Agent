import Darwin
import Foundation
import Testing
@testable import AIAgentApp

@Test
func backendLauncherParsesMagicDNSIdentityFromStatusJSON() throws {
    let statusJSON = """
    {
      "TailscaleIPs": ["100.85.139.105"],
      "Self": {
        "DNSName": "muhammads-macbook-pro.tail8a4dee.ts.net.",
        "TailscaleIPs": ["100.85.139.105", "fd7a:115c:a1e0::b001:8b9c"]
      }
    }
    """

    let identity = BackendLauncher.parseTailscaleIdentity(fromStatusData: Data(statusJSON.utf8))
    #expect(identity == TailscaleIdentity(
        dnsName: "muhammads-macbook-pro.tail8a4dee.ts.net",
        ipAddress: "100.85.139.105"
    ))
}

@Test
func childProcessCaptureDrainsLargeStdoutAndStderr() async throws {
    let payloadSize = 250_000
    let script = """
    import sys
    sys.stdout.write("A" * \(payloadSize))
    sys.stderr.write("B" * \(payloadSize))
    """

    let result = try await ChildProcessCapture.run(
        executableURL: URL(fileURLWithPath: "/usr/bin/python3"),
        arguments: ["-c", script],
        currentDirectoryURL: URL(fileURLWithPath: FileManager.default.currentDirectoryPath),
        environment: ProcessInfo.processInfo.environment
    )

    #expect(result.terminationStatus == 0)
    #expect(result.stdout.count == payloadSize)
    #expect(result.stderr.count == payloadSize)
}

@Test
func processRefForceKillsUnresponsiveChild() async throws {
    let ref = ProcessRef()
    let result = await ref.startProcess(
        pythonPath: "/bin/zsh",
        projectPath: FileManager.default.currentDirectoryPath,
        arguments: ["-lc", "trap '' TERM INT; while true; do sleep 1; done"],
        extraEnvironment: [:]
    )

    let pid: Int32
    switch result {
    case .success(let startedPid):
        pid = startedPid
    case .failure(let error):
        throw error
    }

    ref.requestTermination(gracePeriod: 0.1)

    var childExited = false
    for _ in 0..<40 {
        if Darwin.kill(pid, 0) != 0 {
            childExited = true
            break
        }
        try await Task.sleep(nanoseconds: 50_000_000)
    }

    #expect(childExited)
}
