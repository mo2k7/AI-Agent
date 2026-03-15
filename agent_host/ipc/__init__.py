"""
IPC module for WebSocket communication with the SwiftUI frontend.

This module provides:
- IPCServer: Async server handling client connections
- Protocol: Message type definitions
- Streaming: Streaming response handling
"""

from agent_host.ipc.server import IPCServer
from agent_host.ipc.protocol import (
    IPCMessage,
    StatusUpdate,
    StreamChunk,
    ToolCallNotification,
    ResultMessage,
    ErrorMessage,
)
from agent_host.ipc.streaming import StreamingHandler

__all__ = [
    "IPCServer",
    "IPCMessage",
    "StatusUpdate",
    "StreamChunk",
    "ToolCallNotification",
    "ResultMessage",
    "ErrorMessage",
    "StreamingHandler",
]
