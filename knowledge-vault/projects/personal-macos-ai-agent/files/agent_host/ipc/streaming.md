# File Doc: `agent_host/ipc/streaming.py`

## File Metadata
| Field | Value |
|---|---|
| Project | Personal macOS AI Agent |
| Code File Path | `agent_host/ipc/streaming.py` |
| Doc Path | `projects/personal-macos-ai-agent/files/agent_host/ipc/streaming.md` |
| Language | Python |
| File Role | Streaming Response Handler |
| Ownership | Core Team |
| Status | Active |
| Last Edited (YYYY-MM-DD) | 2026-01-18 |
| Last Major Edit (YYYY-MM-DD) | 2026-01-18 |
| Modified By | AI Agent (Codex) |
| WHY (Reason for last change) | Preserve whitespace during word streaming |
| Lines of Code (LOC) | 212 |
| Cyclomatic Complexity | Low |
| Test Coverage | 0% |

---

## Purpose & Responsibilities

### What this file does
**Single-sentence summary:**
Provides streaming utilities for sending LLM responses to the SwiftUI frontend with configurable typewriter effects.

**Detailed responsibilities:**
- Implements `StreamingHandler` class for various streaming modes (character, word, chunk)
- Provides configurable delays for different streaming effects
- Manages streaming state (active, cancelled, paused)
- Creates `StreamChunk` protocol messages
- Implements `ResponseAccumulator` for collecting streamed chunks on the client side
- Handles cancellation and reset for long-running streams

### What this file must NOT do (boundaries)
**Out of scope:**
- Network I/O (handled by `server.py`)
- Protocol message definitions (use `protocol.py`)
- LLM interaction or response generation
- UI rendering or animations

### Who/what calls it
| Caller | Purpose | Frequency | Error Handling |
|---|---|---|---|
| `agent_host/ipc/server.py` | `create_streaming_handler()` factory | Per streaming response | N/A |
| Request handlers | Stream text to client | During LLM response | Cancellation supported |

### What it calls
| Callee | Purpose | Error Handling | Fallback Strategy |
|---|---|---|---|
| `.protocol.StreamChunk` | Create stream chunks | N/A | N/A |
| `asyncio.sleep` | Timing delays | CancelledError | Stream cancelled |

---

## Imports / Dependencies

### Internal Dependencies
| Import Path | What's Used | Why Needed | Coupling Level | Risk/Notes |
|---|---|---|---|---|
| `.protocol` | `StreamChunk`, `StatusUpdate`, `AgentStatus` | Message creation | High | Core protocol |

### External Dependencies
| Package | Version | License | What's Used | Why Needed | Security Risk | Alternatives |
|---|---|---|---|---|---|---|
| asyncio | stdlib | PSF | `sleep` | Timing delays | None | trio |
| typing | stdlib | PSF | Type hints | Code clarity | None | N/A |
| re | stdlib | PSF | `split` | Word splitting | None | N/A |

---

## Public Surface (Document EVERYTHING Exposed)

### Exports / Public Symbols
| Symbol | Type (func/class/const/type) | Visibility | Status | Brief Description |
|---|---|---|---|---|
| `StreamingHandler` | class | public | Stable | Main streaming utility |
| `ResponseAccumulator` | class | public | Stable | Client-side chunk collector |
| `StreamingConfig` | dataclass | public | Stable | Configuration for delays |

### API Stability
| Symbol | Introduced Version | Deprecated Version | Breaking Changes History |
|---|---|---|---|
| All symbols | 0.2.0 (Phase 2) | N/A | None |

---

## Types (Classes / Structs / Enums / Interfaces)

### `StreamingConfig`
| Metadata | Value |
|---|---|
| Kind | dataclass |
| Purpose | Configuration for streaming delays and behavior |
| Thread-Safe | Yes (immutable) |
| Immutable | Yes (frozen=True) |
| Serializable | Yes |
| Related Types | `StreamingHandler` |

#### Fields / Properties
| Name | Type | Visibility | Default | Required | Mutable | Purpose | Validation | Notes |
|---|---|---|---|---|---|---|---|---|
| `char_delay` | float | public | `0.02` | No | No | Delay between characters (seconds) | N/A | 20ms for typewriter |
| `word_delay` | float | public | `0.05` | No | No | Delay between words (seconds) | N/A | 50ms for word-by-word |
| `chunk_delay` | float | public | `0.1` | No | No | Delay between chunks (seconds) | N/A | 100ms for larger chunks |
| `chunk_size` | int | public | `50` | No | No | Characters per chunk | N/A | For chunk streaming |

#### Example Usage
```python
# Default config for smooth typewriter effect
config = StreamingConfig()

# Faster streaming for short responses
fast_config = StreamingConfig(char_delay=0.01, word_delay=0.03)

# Slower streaming for dramatic effect
slow_config = StreamingConfig(char_delay=0.05, word_delay=0.1)
```

---

### `StreamingHandler`
| Metadata | Value |
|---|---|
| Kind | class |
| Purpose | Handles streaming text to a client with various effects |
| Thread-Safe | No (async single-threaded) |
| Immutable | No |
| Serializable | No |
| Related Types | `StreamingConfig`, `StreamChunk`, `ClientConnection` |

#### Fields / Properties
| Name | Type | Visibility | Default | Required | Mutable | Purpose | Validation | Notes |
|---|---|---|---|---|---|---|---|---|
| `_client` | ClientConnection | private | Required | Yes | No | Target client | N/A | Injected |
| `_request_id` | str | private | Required | Yes | No | Request ID | N/A | For message correlation |
| `_config` | StreamingConfig | private | `StreamingConfig()` | No | No | Delay configuration | N/A | |
| `_cancelled` | bool | private | `False` | No | Yes | Cancellation flag | N/A | |
| `_active` | bool | private | `False` | No | Yes | Streaming in progress | N/A | |
| `_total_sent` | int | private | `0` | No | Yes | Characters sent counter | N/A | |

#### Methods
| Method | Signature | Visibility | Parameters | Returns | Throws/Errors | Side Effects | Thread-Safe | Complexity | Notes |
|---|---|---|---|---|---|---|---|---|---|
| `stream_text` | `async (text: str) -> int` | public | Full text | Characters sent | Never | Sends chunks to client | N/A | O(n) | Character-by-character |
| `stream_words` | `async (text: str) -> int` | public | Full text | Characters sent | Never | Sends chunks to client | N/A | O(n) | Word-by-word |
| `stream_chunks` | `async (text: str, chunk_size: int = None) -> int` | public | Text, optional size | Characters sent | Never | Sends chunks to client | N/A | O(n) | Fixed-size chunks |
| `send_chunk` | `async (delta: str, done: bool = False) -> bool` | public | Chunk text, done flag | Success bool | Never | Sends single chunk | N/A | O(1) | Low-level send |
| `send_done` | `async () -> bool` | public | None | Success bool | Never | Sends final chunk | N/A | O(1) | Sets done=True |
| `cancel` | `() -> None` | public | None | None | Never | Sets cancelled flag | N/A | O(1) | Safe to call anytime |
| `reset` | `() -> None` | public | None | None | Never | Clears state | N/A | O(1) | For reuse |
| `is_active` | `() -> bool` | public | None | Active status | Never | None | N/A | O(1) | Property-like |
| `is_cancelled` | `() -> bool` | public | None | Cancelled status | Never | None | N/A | O(1) | Property-like |
| `total_sent` | `() -> int` | public | None | Total characters | Never | None | N/A | O(1) | Property-like |

#### Example Usage
```python
# Create handler for a client
handler = StreamingHandler(client, "req-123")

# Stream character by character (typewriter effect)
total = await handler.stream_text("Hello, how can I help you today?")
print(f"Sent {total} characters")

# Stream word by word (faster for longer text)
total = await handler.stream_words("This is a longer response that streams word by word.")

# Stream in larger chunks (fastest)
total = await handler.stream_chunks(long_response, chunk_size=100)

# Manual streaming
await handler.send_chunk("Hello", done=False)
await handler.send_chunk(" world", done=False)
await handler.send_done()

# Cancel streaming
handler.cancel()
```

---

### `ResponseAccumulator`
| Metadata | Value |
|---|---|
| Kind | class |
| Purpose | Collects streaming chunks into a complete response (client-side utility) |
| Thread-Safe | No |
| Immutable | No |
| Serializable | No |
| Related Types | `StreamChunk` |

#### Fields / Properties
| Name | Type | Visibility | Default | Required | Mutable | Purpose | Validation | Notes |
|---|---|---|---|---|---|---|---|---|
| `_chunks` | list[str] | private | `[]` | No | Yes | Collected chunks | N/A | |
| `_complete` | bool | private | `False` | No | Yes | Done flag received | N/A | |
| `_request_id` | str | private | Required | Yes | No | Request correlation | N/A | |

#### Methods
| Method | Signature | Visibility | Parameters | Returns | Throws/Errors | Side Effects | Thread-Safe | Complexity | Notes |
|---|---|---|---|---|---|---|---|---|---|
| `add_chunk` | `(chunk: StreamChunk) -> None` | public | Stream chunk | None | Never | Appends to `_chunks` | N/A | O(1) | Ignores if complete |
| `get_text` | `() -> str` | public | None | Accumulated text | Never | None | N/A | O(n) | Joins all chunks |
| `is_complete` | `() -> bool` | public | None | Complete status | Never | None | N/A | O(1) | |
| `clear` | `() -> None` | public | None | None | Never | Clears state | N/A | O(1) | For reuse |

#### Example Usage
```python
# On client side
accumulator = ResponseAccumulator("req-123")

# Process incoming stream chunks
for message in incoming_messages:
    if isinstance(message, StreamChunk):
        accumulator.add_chunk(message)
        print(f"Partial: {accumulator.get_text()}")
        
        if accumulator.is_complete():
            print(f"Final: {accumulator.get_text()}")
```

---

## Algorithms & Logic

### Character-by-Character Streaming
```python
async def stream_text(self, text: str) -> int:
    for char in text:
        if self._cancelled:
            break
        await self.send_chunk(char)
        await asyncio.sleep(self._config.char_delay)
    await self.send_done()
    return self._total_sent
```

### Word-by-Word Streaming
```python
async def stream_words(self, text: str) -> int:
    # Split by whitespace, preserving separators
    words = re.split(r'(\s+)', text)
    for word in words:
        if self._cancelled:
            break
        await self.send_chunk(word)
        if word.strip():  # Only delay after actual words
            await asyncio.sleep(self._config.word_delay)
    await self.send_done()
    return self._total_sent
```

### Chunk Streaming
```python
async def stream_chunks(self, text: str, chunk_size: int = None) -> int:
    size = chunk_size or self._config.chunk_size
    for i in range(0, len(text), size):
        if self._cancelled:
            break
        chunk = text[i:i + size]
        await self.send_chunk(chunk)
        await asyncio.sleep(self._config.chunk_delay)
    await self.send_done()
    return self._total_sent
```

---

## State Management

### Instance State
| Variable | Type | Scope | Mutability | Thread-Safe | Purpose | Risk |
|---|---|---|---|---|---|---|
| `_cancelled` | bool | Instance | Mutable | No | Cancellation flag | Must check before each send |
| `_active` | bool | Instance | Mutable | No | Active streaming flag | |
| `_total_sent` | int | Instance | Mutable | No | Progress tracking | |

### State Transitions
```
[Idle] --stream_*()--> [Active] --done--> [Complete]
                           |
                        cancel()
                           |
                       [Cancelled]
                           |
                        reset()
                           |
                        [Idle]
```

---

## Error Handling Strategy

### Error Categories
| Category | Examples | Default Behavior | User Action |
|---|---|---|---|
| Cancellation | User cancelled | Stop streaming, send done | None |
| Connection Lost | Broken pipe | Log, stop streaming | Reconnect |

### Error Propagation
```
send_chunk() -> client.send() failure -> returns False -> streaming stops
asyncio.CancelledError -> caught in stream loop -> send_done()
```

---

## Performance Profile

### Performance Characteristics
| Metric | Value | Target | Acceptable Range |
|---|---|---|---|
| Char Delay | 20ms | 15-30ms | 10-50ms |
| Word Delay | 50ms | 40-60ms | 30-100ms |
| Chunk Delay | 100ms | 80-120ms | 50-200ms |
| Memory | ~10 bytes/char | <100 bytes/char | <1KB/char |

### Optimization Notes
- Character streaming is CPU-intensive for large texts
- Word streaming is recommended for responses >100 chars
- Chunk streaming for responses >1000 chars
- Cancellation is checked before each send for responsiveness

---

## Testing Documentation

### Unit Test Coverage
| Function/Class | Coverage | Test Location | Edge Cases Covered |
|---|---|---|---|
| All | 0% | `tests/unit/test_streaming.py` | None yet |

### Testing Gaps
| Untested Area | Risk | Reason | Plan to Address |
|---|---|---|---|
| Streaming modes | Medium | New implementation | Add unit tests |
| Cancellation | Medium | New implementation | Add unit tests |
| Edge cases | Low | Empty text, single char | Add unit tests |

---

## Related Documentation

### Related Files
| File Path | Relationship | Why Related |
|---|---|---|
| `agent_host/ipc/protocol.py` | Uses | StreamChunk messages |
| `agent_host/ipc/server.py` | Used by | Factory method |
| `ui/AIAgentUI/Views/Components/ResponseBubble.swift` | Client | Displays streamed text |

---

## Maintainer Notes

### When to Update This Doc
- [ ] When adding new streaming modes
- [ ] When changing default delays
- [ ] When adding new configuration options
- [ ] When modifying cancellation behavior

### Configuration Tuning
- `char_delay` of 20ms gives ~50 chars/second (typewriter feel)
- `word_delay` of 50ms gives ~20 words/second (readable pace)
- Reduce delays for faster streaming, increase for dramatic effect

---

## Major Edits Log (Append-Only)
| Date | Modified By | WHY | Summary | Impact |
|---|---|---|---|---|
| 2026-01-18 | AI Assistant | Initial implementation | Created streaming handler | New file |
| 2026-01-18 | AI Agent (Codex) | Whitespace fidelity | Stream word tokens without collapsing spaces or newlines | Medium |
