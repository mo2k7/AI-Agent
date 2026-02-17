# gemini_client.py

**Purpose:** Gemini API client wrapper with retry logic and per-request model selection

**Path:** `agent_host/gemini_client.py`

**Last Updated:** 2026-01-18 (SESSION-0005) - Dependency version refresh

---

## Overview

Wraps the new Google Gen AI SDK (`google.genai`) to interact with the Gemini API. The new API enables **per-request model selection**, meaning the model can be changed on each call without restarting the client.

## Key Changes in v2.0 (SESSION-0003)

### Previous API (deprecated):
```python
# OLD WAY - model fixed at initialization
import google.generativeai as genai
genai.configure(api_key=api_key)
model = genai.GenerativeModel(model_name)
response = model.generate_content(prompt)
```

### New API (current):
```python
# NEW WAY - model specified per-request
from google import genai
from google.genai import types

client = genai.Client(api_key=api_key)
response = client.models.generate_content(
    model='gemini-3-flash-preview',  # Can change per request!
    contents=prompt,
    config=types.GenerateContentConfig(
        tools=[...],
        system_instruction='...',
        temperature=0.1,
    ),
)
```

## Public Interface

### GeminiClient

```python
class GeminiClient:
    def __init__(
        self,
        api_key: str,
        model_name: str = "gemini-2.0-flash-exp",
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ) -> None: ...
    
    def send_prompt_with_tools(
        self,
        prompt: str,
        tools: List[Dict[str, Any]],
        system_instruction: Optional[str] = None,
        model: Optional[str] = None,  # Override model for this request!
    ) -> Dict[str, Any]: ...
```

### Parameters

- **api_key**: Google API key
- **model_name**: Default model (can be overridden per request)
- **max_retries**: Retry attempts for rate limits/server errors
- **retry_delay**: Initial delay between retries (exponential backoff)

### Return Format

```python
{
    "text": Optional[str],       # Text response
    "function_call": Optional[{  # Tool call if any
        "name": str,
        "args": Dict[str, Any],
    }],
    "raw_response": Any,         # Raw Gemini response
}
```

## Tool Conversion

Uses `types.FunctionDeclaration` with `parameters_json_schema` (dict) instead of protobuf Schema:

```python
func_decl = types.FunctionDeclaration(
    name=tool["name"],
    description=tool["description"],
    parameters_json_schema=tool["parameters"],  # Just pass JSON Schema directly!
)
tools = [types.Tool(function_declarations=[func_decl])]
```

## Error Handling

Uses `google.genai.errors.APIError` with error codes:

| Code | Exception | Retry? |
|------|-----------|--------|
| 429 | GeminiRateLimitError | Yes |
| 500, 502, 503, 504 | GeminiServerError | Yes |
| Other | GeminiAPIError | No |

## Custom Exceptions

```python
class GeminiClientError(Exception): ...      # Base exception
class GeminiAPIError(GeminiClientError): ... # API errors with status_code
class GeminiRateLimitError(GeminiAPIError): ... # Rate limit (429)
class GeminiServerError(GeminiAPIError): ...    # Server errors (5xx)
```

## Usage Example

```python
from agent_host.gemini_client import GeminiClient

# Initialize with default model
client = GeminiClient(api_key="your-key")

tools = [
    {
        "name": "search_files",
        "description": "Search for files",
        "parameters": {"type": "object", "properties": {...}}
    }
]

# Use default model
response = client.send_prompt_with_tools(
    prompt="Find Python files",
    tools=tools,
    system_instruction="You are a helpful assistant",
)

# Override model for this specific request
response = client.send_prompt_with_tools(
    prompt="Complex analysis",
    tools=tools,
    model="gemini-3-pro-preview",  # Uses Pro model just for this call
)
```

## Dependencies

- `google-genai` ^1.59.0 (new package, NOT `google-generativeai`)
- Python 3.14+

## Related Files

- [`main.py`](main.md) - Uses GeminiClient with model from frontend
- [`system_prompt.py`](system_prompt.md) - System instruction for the model
- [`pyproject.toml`](../pyproject.toml.md) - Package dependencies

---

## Change Log

| Date | Session | Change |
|------|---------|--------|
| 2026-01-18 | SESSION-0005 | Updated google-genai dependency baseline to ^1.59.0 |
| 2026-01-18 | SESSION-0003 | Major rewrite: migrated from `google-generativeai` to `google.genai` Client API |
| 2026-01-18 | SESSION-0003 | Added per-request model selection via `model` parameter |
| 2026-01-18 | SESSION-0003 | Updated error handling to use `google.genai.errors.APIError` |
| 2026-01-18 | SESSION-0003 | Switched to `types.FunctionDeclaration` with `parameters_json_schema` |
