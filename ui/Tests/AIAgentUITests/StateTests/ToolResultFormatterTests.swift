import Testing
@testable import AIAgentApp

@Test
func toolResultFormatterLeavesPlainTextUntouched() {
    let content = "No files found. Try refining your query."
    #expect(ToolResultFormatter.normalizeContent(content) == content)
}

@Test
func toolResultFormatterRendersSearchFilesPayloadAsMarkdownList() {
    let content = """
    {"tool":"search_files","ok":true,"timestamp":1770446741.1303859,"output":{"ok":true,"query":"gemini","limit":10,"scanned_entries":20001,"truncated":true,"truncated_reason":"Reached walk scan limit (20001 entries)","matches":[{"path":"/Users/test/Downloads/generated-image.png","name":"generated-image.png","display_path":"~/Downloads/generated-image.png","uri":"file:///Users/test/Downloads/generated-image.png"}]}}
    """

    let normalized = ToolResultFormatter.normalizeContent(content)

    #expect(normalized.contains("Found 1 matching file(s)."))
    #expect(normalized.contains("[generated-image.png](file:///Users/test/Downloads/generated-image.png)"))
    #expect(normalized.contains("(`~/Downloads/generated-image.png`)"))
    #expect(normalized.contains("Scanned entries: 20001."))
}

@Test
func toolResultFormatterRendersSearchFilesNoMatchPayloadClearly() {
    let content = """
    {"tool":"search_files","ok":true,"timestamp":1770446741.1303859,"output":{"ok":true,"query":"gemini","limit":10,"scanned_entries":20001,"truncated":true,"matches":[]}}
    """

    let normalized = ToolResultFormatter.normalizeContent(content)

    #expect(normalized.contains("No files found."))
    #expect(normalized.contains("Query: gemini."))
    #expect(normalized.contains("Try a more specific"))
}

@Test
func toolResultFormatterRendersGenerateImagePayload() {
    let content = """
    {"tool":"generate_image","ok":true,"output":{"summary":"Generated 1 image(s) with model 'imagen-4.0-fast-generate-001'.","model":"imagen-4.0-fast-generate-001","images":[{"path":"/Users/test/Downloads/cat.png","mime_type":"image/png","width":1024,"height":1024,"note_embedded":false}]}}
    """

    let normalized = ToolResultFormatter.normalizeContent(content)

    #expect(normalized.contains("**Image Generation**"))
    #expect(normalized.contains("Generated 1 image(s):"))
    #expect(normalized.contains("[cat.png](file:///Users/test/Downloads/cat.png)"))
    #expect(normalized.contains("1024x1024"))
}

@Test
func toolResultFormatterRendersGenerateImageEmptyPayloadClearly() {
    let content = """
    {"tool":"generate_image","ok":true,"output":{"model":"imagen-4.0-generate-001","images":[]}}
    """

    let normalized = ToolResultFormatter.normalizeContent(content)

    #expect(normalized.contains("**Image Generation**"))
    #expect(normalized.contains("No saved images were returned."))
}

@Test
func toolResultFormatterRendersBrowseWebWarningsCompactly() {
    let content = """
    {"tool":"browse_web","ok":true,"output":{"final_url":"https://example.com/article","title":"Example Article","effective_browse_profile":"flexible","policy_warnings":["Access restriction warning: URL appears to require login.","Security attestation warning: stale"],"content":"Article body text."}}
    """

    let normalized = ToolResultFormatter.normalizeContent(content)

    #expect(normalized.contains("**Web Browse**"))
    #expect(normalized.contains("Source: [Example Article](https://example.com/article)"))
    #expect(normalized.contains("Browse profile: `flexible`"))
    #expect(normalized.contains("Policy notice: `flexible` browsing allowed this result with policy warnings."))
    #expect(normalized.contains("Policy notice: `flexible` browsing allowed this result with policy warnings.\n\nCaution:"))
    #expect(normalized.contains("Caution: Access restriction warning: URL appears to require login. (+1 more)"))
    #expect(normalized.contains("Article body text."))
}
