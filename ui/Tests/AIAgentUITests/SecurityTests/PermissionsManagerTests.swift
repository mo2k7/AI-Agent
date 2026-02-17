import Foundation
import Testing
@testable import AIAgentApp

@Test
func fullDiskAccessStatusIsAuthorizedOnlyWhenProtectedReadSucceeds() {
    let status = PermissionsManager.evaluateFullDiskAccessStatus(
        from: [
            .init(exists: true, readable: false, permissionDenied: true),
            .init(exists: true, readable: true, permissionDenied: false),
        ]
    )
    #expect(status == .authorized)
}

@Test
func fullDiskAccessStatusReportsDeniedWhenPermissionErrorsObserved() {
    let status = PermissionsManager.evaluateFullDiskAccessStatus(
        from: [
            .init(exists: true, readable: false, permissionDenied: true),
            .init(exists: true, readable: false, permissionDenied: false),
        ]
    )
    #expect(status == .denied)
}

@Test
func fullDiskAccessStatusAvoidsFalseAuthorizedForUnreadableTargets() {
    let status = PermissionsManager.evaluateFullDiskAccessStatus(
        from: [
            .init(exists: true, readable: false, permissionDenied: false),
            .init(exists: true, readable: false, permissionDenied: false),
        ]
    )
    #expect(status == .notDetermined)
}

@Test
func fullDiskAccessStatusIsNotDeterminedWhenNoProtectedTargetsExist() {
    let status = PermissionsManager.evaluateFullDiskAccessStatus(from: [])
    #expect(status == .notDetermined)
}

