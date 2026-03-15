import Testing
@testable import AIAgentApp

@Test
func responsePresentationStyleDisplayNamesAreStable() {
    #expect(ResponsePresentationStyle.readablePro.displayName == "Readable Pro")
    #expect(ResponsePresentationStyle.glassEditorial.displayName == "Glass Editorial")
    #expect(ResponsePresentationStyle.denseTechnical.displayName == "Dense Technical")
}

@Test
func streamingAnimationStyleDisplayNamesAreStable() {
    #expect(StreamingAnimationStyle.waveReveal.displayName == "Wave Reveal")
    #expect(StreamingAnimationStyle.typewriterLuxe.displayName == "Typewriter Luxe")
    #expect(StreamingAnimationStyle.minimalMotion.displayName == "Minimal Motion")
}

@Test
func browseRestrictionProfileDisplayNamesAreStable() {
    #expect(BrowseRestrictionProfile.strict.displayName == "Strict")
    #expect(BrowseRestrictionProfile.standard.displayName == "Standard")
    #expect(BrowseRestrictionProfile.flexible.displayName == "Flexible")
    #expect(BrowseRestrictionProfile.standard.quickMenuDescription == "Recommended balanced browsing with fewer false blocks.")
    #expect(BrowseRestrictionProfile.flexible.quickMenuDescription == "Broader access while still blocking SSRF, prompt-injection, and PII.")
}
