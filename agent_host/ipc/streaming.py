"""
Streaming handler for sending streaming responses to SwiftUI frontend.

Manages chunking text responses and sending them over the IPC connection
with appropriate delays for typewriter effect.
"""

import asyncio
import re
from typing import Callable, Awaitable
from agent_host.ipc.protocol import StreamChunk, StatusUpdate


class StreamingHandler:
    """
    Handles streaming responses to the SwiftUI frontend.
    
    Supports:
    - Character-by-character streaming with configurable delay
    - Word-by-word streaming
    - Chunk streaming with size control
    """
    
    # Default delays in seconds
    DEFAULT_CHAR_DELAY = 0.02  # 20ms per character for typewriter effect
    DEFAULT_WORD_DELAY = 0.05  # 50ms per word
    DEFAULT_CHUNK_DELAY = 0.1  # 100ms per chunk
    
    def __init__(
        self,
        send_func: Callable[[bytes], Awaitable[None]],
        request_id: str,
        char_delay: float = DEFAULT_CHAR_DELAY,
        word_delay: float = DEFAULT_WORD_DELAY,
        chunk_delay: float = DEFAULT_CHUNK_DELAY,
    ):
        """
        Initializes the streaming handler.
        
        Args:
            send_func: Async function to send bytes to the client.
            request_id: The request ID to include in messages.
            char_delay: Delay between characters in character streaming mode.
            word_delay: Delay between words in word streaming mode.
            chunk_delay: Delay between chunks in chunk streaming mode.
        """
        self._send = send_func
        self._request_id = request_id
        self._char_delay = char_delay
        self._word_delay = word_delay
        self._chunk_delay = chunk_delay
        self._cancelled = False
    
    def cancel(self) -> None:
        """Cancels any ongoing streaming operation."""
        self._cancelled = True
    
    def reset(self) -> None:
        """Resets the cancelled state for reuse."""
        self._cancelled = False
    
    async def send_status_streaming(self) -> None:
        """Sends a streaming status update."""
        status = StatusUpdate.streaming(self._request_id)
        await self._send(status.to_bytes())
    
    async def stream_text(self, text: str, done: bool = True) -> None:
        """
        Streams text character by character with typewriter effect.
        
        Args:
            text: The text to stream.
            done: Whether this is the final text.
        """
        self.reset()
        
        # Send streaming status first
        await self.send_status_streaming()
        
        for i, char in enumerate(text):
            if self._cancelled:
                break
            
            is_last = (i == len(text) - 1) and done
            chunk = StreamChunk.chunk(self._request_id, char, done=is_last)
            await self._send(chunk.to_bytes())
            
            if not is_last:
                await asyncio.sleep(self._char_delay)
    
    async def stream_words(self, text: str, done: bool = True) -> None:
        """
        Streams text word by word.
        
        Args:
            text: The text to stream.
            done: Whether this is the final text.
        """
        self.reset()
        
        # Send streaming status first
        await self.send_status_streaming()
        
        tokens = re.findall(r"\s+|[^\s]+", text)
        for i, token in enumerate(tokens):
            if self._cancelled:
                break
            
            is_last = (i == len(tokens) - 1) and done
            
            chunk = StreamChunk.chunk(self._request_id, token, done=is_last)
            await self._send(chunk.to_bytes())
            
            if not is_last and not token.isspace():
                await asyncio.sleep(self._word_delay)
    
    async def stream_chunks(
        self,
        text: str,
        chunk_size: int = 20,
        done: bool = True,
    ) -> None:
        """
        Streams text in fixed-size chunks.
        
        Args:
            text: The text to stream.
            chunk_size: Number of characters per chunk.
            done: Whether this is the final text.
        """
        self.reset()
        
        # Send streaming status first
        await self.send_status_streaming()
        
        # Split text into chunks
        chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]
        
        for i, chunk_text in enumerate(chunks):
            if self._cancelled:
                break
            
            is_last = (i == len(chunks) - 1) and done
            chunk = StreamChunk.chunk(self._request_id, chunk_text, done=is_last)
            await self._send(chunk.to_bytes())
            
            if not is_last:
                await asyncio.sleep(self._chunk_delay)
    
    async def send_chunk(self, text: str, done: bool = False) -> None:
        """
        Sends a single chunk immediately without delay.
        
        Args:
            text: The text chunk to send.
            done: Whether this is the final chunk.
        """
        chunk = StreamChunk.chunk(self._request_id, text, done=done)
        await self._send(chunk.to_bytes())
    
    async def send_done(self, final_text: str = "") -> None:
        """
        Sends the final done chunk.
        
        Args:
            final_text: Optional final text to include.
        """
        chunk = StreamChunk.final(self._request_id, final_text)
        await self._send(chunk.to_bytes())


class ResponseAccumulator:
    """
    Accumulates streaming response chunks for building the final response.
    
    Used when the backend receives streaming from the LLM and needs to
    both forward to UI and build the final response.
    """
    
    def __init__(self):
        """Initializes the accumulator."""
        self._chunks: list[str] = []
        self._complete = False
    
    def add_chunk(self, text: str) -> None:
        """Adds a chunk to the accumulator."""
        self._chunks.append(text)
    
    def mark_complete(self) -> None:
        """Marks the response as complete."""
        self._complete = True
    
    @property
    def is_complete(self) -> bool:
        """Returns whether the response is complete."""
        return self._complete
    
    @property
    def text(self) -> str:
        """Returns the accumulated text."""
        return "".join(self._chunks)
    
    @property
    def chunk_count(self) -> int:
        """Returns the number of chunks accumulated."""
        return len(self._chunks)
    
    def clear(self) -> None:
        """Clears the accumulator for reuse."""
        self._chunks.clear()
        self._complete = False
