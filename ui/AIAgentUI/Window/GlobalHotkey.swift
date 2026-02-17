//
//  GlobalHotkey.swift
//  AIAgentUI
//
//  Created for Personal macOS AI Agent
//  Status: Active - Global Cmd+K hotkey registration
//

import Foundation
import AppKit
import Carbon.HIToolbox

/// Manages global hotkey registration using Carbon Event Manager
/// Default hotkey: Cmd+K to toggle the panel
@MainActor
final class GlobalHotkeyManager {
    
    // MARK: - Singleton
    
    static let shared = GlobalHotkeyManager()
    
    // MARK: - Properties
    
    /// Registered Carbon hotkeys keyed by EventHotKeyID.id
    private var hotkeyRefs: [UInt32: EventHotKeyRef] = [:]
    
    /// Event handler reference
    private var eventHandlerRef: EventHandlerRef?
    
    /// Unique IDs for registered hotkeys
    private let primaryHotkeyID = EventHotKeyID(signature: OSType(0x41474E54), id: 1) // "AGNT"
    private let secondaryHotkeyID = EventHotKeyID(signature: OSType(0x41474E54), id: 2) // "AGNT"
    private let tertiaryHotkeyID = EventHotKeyID(signature: OSType(0x41474E54), id: 3) // "AGNT"
    
    /// Hotkey callback handler
    var onHotkeyPressed: (() -> Void)?
    
    // MARK: - Initialization
    
    private init() {}
    
    // MARK: - Registration
    
    /// Registers the global Cmd+K hotkey
    /// - Returns: Whether registration was successful
    @discardableResult
    func registerHotkey() -> Bool {
        unregisterHotkey()
        
        // Register both the historical shortcut and a backup shortcut.
        // This reduces conflicts in apps that consume Cmd+K.
        let primaryRegistered = registerHotkey(
            keyCode: KeyCode.k.rawValue,
            modifiers: UInt32(cmdKey),
            hotkeyID: primaryHotkeyID,
            label: "Cmd+K"
        )
        let secondaryRegistered = registerHotkey(
            keyCode: KeyCode.k.rawValue,
            modifiers: UInt32(cmdKey | shiftKey),
            hotkeyID: secondaryHotkeyID,
            label: "Cmd+Shift+K"
        )
        let tertiaryRegistered = registerHotkey(
            keyCode: KeyCode.k.rawValue,
            modifiers: UInt32(cmdKey | optionKey),
            hotkeyID: tertiaryHotkeyID,
            label: "Cmd+Option+K"
        )

        guard primaryRegistered || secondaryRegistered || tertiaryRegistered else {
            return false
        }
        
        installEventHandler()
        let registeredLabels = [
            primaryRegistered ? "Cmd+K" : nil,
            secondaryRegistered ? "Cmd+Shift+K" : nil,
            tertiaryRegistered ? "Cmd+Option+K" : nil
        ].compactMap { $0 }.joined(separator: ", ")
        print("Registered global hotkey(s): \(registeredLabels)")
        return true
    }
    
    /// Registers a custom hotkey
    /// - Parameters:
    ///   - keyCode: The key code
    ///   - modifiers: Modifier keys (e.g., cmdKey, controlKey, optionKey, shiftKey)
    /// - Returns: Whether registration was successful
    @discardableResult
    func registerHotkey(keyCode: UInt32, modifiers: UInt32) -> Bool {
        unregisterHotkey()

        guard registerHotkey(
            keyCode: keyCode,
            modifiers: modifiers,
            hotkeyID: primaryHotkeyID,
            label: "Custom"
        ) else {
            return false
        }
        
        installEventHandler()
        return true
    }
    
    /// Unregisters the current hotkey
    func unregisterHotkey() {
        for (_, hotKeyRef) in hotkeyRefs {
            UnregisterEventHotKey(hotKeyRef)
        }
        hotkeyRefs.removeAll()
        
        if let handlerRef = eventHandlerRef {
            RemoveEventHandler(handlerRef)
            eventHandlerRef = nil
        }
    }
    
    // MARK: - Private Methods
    
    /// Installs the Carbon event handler
    private func installEventHandler() {
        var eventType = EventTypeSpec(
            eventClass: OSType(kEventClassKeyboard),
            eventKind: UInt32(kEventHotKeyPressed)
        )
        
        // Store self reference for the callback
        let selfPtr = Unmanaged.passUnretained(self).toOpaque()
        
        let status = InstallEventHandler(
            GetApplicationEventTarget(),
            { (_, event, userData) -> OSStatus in
                guard let userData = userData else { return OSStatus(eventNotHandledErr) }
                
                let manager = Unmanaged<GlobalHotkeyManager>.fromOpaque(userData).takeUnretainedValue()
                
                // Verify it's our hotkey
                var hotKeyID = EventHotKeyID()
                let status = GetEventParameter(
                    event,
                    EventParamName(kEventParamDirectObject),
                    EventParamType(typeEventHotKeyID),
                    nil,
                    MemoryLayout<EventHotKeyID>.size,
                    nil,
                    &hotKeyID
                )
                
                guard status == noErr else { return status }
                
                // Check if it matches one of our registered hotkeys
                if hotKeyID.signature == manager.primaryHotkeyID.signature &&
                    (hotKeyID.id == manager.primaryHotkeyID.id
                        || hotKeyID.id == manager.secondaryHotkeyID.id
                        || hotKeyID.id == manager.tertiaryHotkeyID.id) {
                    DispatchQueue.main.async {
                        manager.onHotkeyPressed?()
                    }
                }
                
                return noErr
            },
            1,
            &eventType,
            selfPtr,
            &eventHandlerRef
        )
        
        if status != noErr {
            print("Failed to install event handler: \(status)")
        }
    }

    @discardableResult
    private func registerHotkey(
        keyCode: UInt32,
        modifiers: UInt32,
        hotkeyID: EventHotKeyID,
        label: String
    ) -> Bool {
        var hotkeyRef: EventHotKeyRef?
        let status = RegisterEventHotKey(
            keyCode,
            modifiers,
            hotkeyID,
            GetApplicationEventTarget(),
            0,
            &hotkeyRef
        )

        guard status == noErr, let hotkeyRef else {
            print("Failed to register \(label) hotkey: \(status)")
            return false
        }

        hotkeyRefs[hotkeyID.id] = hotkeyRef
        return true
    }
}

// MARK: - Key Codes

/// Common key codes for hotkey registration
enum KeyCode: UInt32 {
    case a = 0x00
    case s = 0x01
    case d = 0x02
    case f = 0x03
    case h = 0x04
    case g = 0x05
    case z = 0x06
    case x = 0x07
    case c = 0x08
    case v = 0x09
    case b = 0x0B
    case q = 0x0C
    case w = 0x0D
    case e = 0x0E
    case r = 0x0F
    case y = 0x10
    case t = 0x11
    case one = 0x12
    case two = 0x13
    case three = 0x14
    case four = 0x15
    case six = 0x16
    case five = 0x17
    case equals = 0x18
    case nine = 0x19
    case seven = 0x1A
    case minus = 0x1B
    case eight = 0x1C
    case zero = 0x1D
    case rightBracket = 0x1E
    case o = 0x1F
    case u = 0x20
    case leftBracket = 0x21
    case i = 0x22
    case p = 0x23
    case returnKey = 0x24
    case l = 0x25
    case j = 0x26
    case apostrophe = 0x27
    case k = 0x28
    case semicolon = 0x29
    case backslash = 0x2A
    case comma = 0x2B
    case slash = 0x2C
    case n = 0x2D
    case m = 0x2E
    case period = 0x2F
    case tab = 0x30
    case space = 0x31
    case grave = 0x32
    case delete = 0x33
    case escape = 0x35
    case f5 = 0x60
    case f6 = 0x61
    case f7 = 0x62
    case f3 = 0x63
    case f8 = 0x64
    case f9 = 0x65
    case f11 = 0x67
    case f13 = 0x69
    case f14 = 0x6B
    case f10 = 0x6D
    case f12 = 0x6F
    case f15 = 0x71
    case f4 = 0x76
    case f2 = 0x78
    case f1 = 0x7A
}

// MARK: - Modifier Masks

/// Modifier key masks for Carbon
struct ModifierMask: OptionSet {
    let rawValue: UInt32
    
    static let command = ModifierMask(rawValue: UInt32(cmdKey))
    static let option = ModifierMask(rawValue: UInt32(optionKey))
    static let control = ModifierMask(rawValue: UInt32(controlKey))
    static let shift = ModifierMask(rawValue: UInt32(shiftKey))
    
    /// Combines multiple modifiers
    var carbonModifiers: UInt32 {
        return rawValue
    }
}

// MARK: - HotKey Wrapper (Alternative Implementation Using LocalMonitor)

/// A simpler hotkey implementation using NSEvent local/global monitors
/// Use this if Carbon events cause issues
@MainActor
final class HotKeyMonitor {
    
    // MARK: - Singleton
    
    static let shared = HotKeyMonitor()
    
    // MARK: - Properties
    
    private var globalMonitor: Any?
    private var localMonitor: Any?
    
    /// Handler for hotkey press
    var onHotkeyPressed: (() -> Void)?
    
    // MARK: - Initialization
    
    private init() {}
    
    // MARK: - Methods
    
    /// Starts monitoring for hotkeys
    /// - Parameter includeGlobalMonitor: Whether to monitor when app is unfocused
    func startMonitoring(includeGlobalMonitor: Bool = true) {
        stopMonitoring()

        if includeGlobalMonitor {
            // Global monitor (works when app is not focused; requires Accessibility permission)
            globalMonitor = NSEvent.addGlobalMonitorForEvents(matching: .keyDown) { [weak self] event in
                self?.handleKeyEvent(event)
            }
        }
        
        // Local monitor (works when app is focused)
        localMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] event in
            self?.handleKeyEvent(event)
            return event
        }
    }
    
    /// Stops monitoring
    func stopMonitoring() {
        if let monitor = globalMonitor {
            NSEvent.removeMonitor(monitor)
            globalMonitor = nil
        }
        
        if let monitor = localMonitor {
            NSEvent.removeMonitor(monitor)
            localMonitor = nil
        }
    }
    
    private func handleKeyEvent(_ event: NSEvent) {
        let modifiers = event.modifierFlags.intersection(.deviceIndependentFlagsMask)
        let isCmdK = modifiers == .command && event.keyCode == KeyCode.k.rawValue
        let isCmdShiftK = modifiers == [.command, .shift] && event.keyCode == KeyCode.k.rawValue
        let isCmdOptionK = modifiers == [.command, .option] && event.keyCode == KeyCode.k.rawValue

        if isCmdK || isCmdShiftK || isCmdOptionK {
            DispatchQueue.main.async { [weak self] in
                self?.onHotkeyPressed?()
            }
        }
    }
}
