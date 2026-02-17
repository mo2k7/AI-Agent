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
