"""
IPC Server for Unix Domain Socket communication with SwiftUI frontend.

Provides an async server that:
- Listens on a Unix Domain Socket
- Handles multiple client connections
- Routes incoming requests to appropriate handlers
- Sends streaming responses back to clients
"""

import asyncio
import inspect
import json
import logging
import os
import stat
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional, Awaitable
from dataclasses import dataclass

from agent_host.ipc.protocol import (
    IncomingRequest,
    ErrorMessage,
    ResultMessage,
    PROTOCOL_VERSION,
)
from agent_host.ipc.streaming import StreamingHandler
from agent_host.observability import (
    generate_correlation_id,
    reset_request_context,
    set_request_context,
)
from agent_host.redaction import redact_value

logger = logging.getLogger(__name__)


def _safe_env_int(name: str, default: int) -> int:
    """Parse an integer environment variable, returning *default* on invalid input."""
    raw = os.environ.get(name, "")
    if not raw.strip():
        return default
    try:
        return int(raw)
    except (ValueError, TypeError):
        return default


def _format_exception_message(exc: BaseException, *, fallback: str = "Internal server error") -> str:
    """Return a non-empty exception message for client-facing IPC errors."""
    detail = str(exc).strip()
    if detail:
        return detail
    return f"{fallback} ({exc.__class__.__name__})"


@dataclass
class ClientConnection:
    """Represents a connected client."""
    
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    address: str
    connected_at: float
    trace_outbound: Optional[Callable[[bytes], None]] = None
    
    async def send(self, data: bytes) -> None:
        """Sends data to the client."""
        if self.trace_outbound is not None:
            try:
                self.trace_outbound(data)
            except Exception:
                logger.exception("Outbound trace hook failed for client %s", self.address)
        if self.writer.is_closing():
            return
        self.writer.write(data)
        try:
            await self.writer.drain()
        except (ConnectionError, BrokenPipeError):
            # Client disconnected during write; ignore
            pass
    
    async def close(self) -> None:
        """Closes the client connection."""
        try:
            if not self.writer.is_closing():
                self.writer.close()
            await self.writer.wait_closed()
        except (ConnectionError, BrokenPipeError, OSError):
            pass


# Type alias for request handlers
RequestHandler = Callable[[IncomingRequest, ClientConnection], Awaitable[None]]
DisconnectHandler = Callable[[ClientConnection], Awaitable[None] | None]


class IPCServer:
    """
    Unix Domain Socket server for SwiftUI frontend communication.
    
    Usage:
        server = IPCServer()
        server.register_handler("prompt", handle_prompt)
        await server.start()
        # ... run until shutdown
        await server.stop()
    """
    
    # Default socket path template
    DEFAULT_SOCKET_PATH = "/tmp/ai-agent-{pid}.sock"
    
    # Buffer size for reading
    BUFFER_SIZE = 4096
    # Hard cap for buffered request bytes awaiting newline delimiter.
    # Increased to 16MB to support large context pastes/file content in prompts.
    MAX_INCOMING_BUFFER = 16 * 1_048_576
    # Timeout for client handshake/first request to prevent resource exhaustion
    HANDSHAKE_TIMEOUT = 10.0
    
    def __init__(
        self,
        socket_path: Optional[str] = None,
        max_clients: int = 5,
        *,
        require_auth: bool = False,
        auth_token: str | None = None,
        required_protocol_version: str = PROTOCOL_VERSION,
    ):
        """
        Initializes the IPC server.
        
        Args:
            socket_path: Path to the Unix Domain Socket.
                         Defaults to /tmp/ai-agent-<pid>.sock
            max_clients: Maximum number of concurrent clients.
            require_auth: Whether to enforce auth.hello before any RPC method.
            auth_token: Shared auth token expected from the frontend.
            required_protocol_version: Required frontend protocol version.
        """
        self._socket_path = socket_path or self.DEFAULT_SOCKET_PATH.format(pid=os.getpid())
        self._max_clients = max_clients
        self._require_auth = require_auth
        self._auth_token = (auth_token or "").strip()
        self._required_protocol_version = required_protocol_version
        self._server: Optional[asyncio.Server] = None
        self._clients: dict[str, ClientConnection] = {}
        self._handlers: dict[str, RequestHandler] = {}
        self._disconnect_handler: Optional[DisconnectHandler] = None
        self._running = False
        self._shutdown_event = asyncio.Event()
        self._trace_enabled = os.environ.get("AI_AGENT_DEBUG_PROTOCOL_TRACE", "0").strip() == "1"
        self._trace_max_bytes = _safe_env_int("AI_AGENT_DEBUG_PROTOCOL_TRACE_MAX_BYTES", 4096)
        self._trace_path: Optional[Path] = None
        artifact_dir = os.environ.get("AI_AGENT_ARTIFACT_DIR")
        if self._trace_enabled and artifact_dir:
            artifact_path = Path(artifact_dir)
            artifact_path.mkdir(parents=True, exist_ok=True)
            self._trace_path = artifact_path / "protocol_trace.jsonl"
        if self._require_auth and not self._auth_token:
            raise ValueError(
                "IPC auth is required but no auth_token was configured."
            )
    
    @property
    def socket_path(self) -> str:
        """Returns the socket path."""
        return self._socket_path
    
    @property
    def is_running(self) -> bool:
        """Returns whether the server is running."""
        return self._running
    
    @property
    def client_count(self) -> int:
        """Returns the number of connected clients."""
        return len(self._clients)
    
    def register_handler(self, method: str, handler: RequestHandler) -> None:
        """
        Registers a handler for a specific method.
        
        Args:
            method: The method name (e.g., "prompt", "cancel").
            handler: Async function to handle the request.
        """
        self._handlers[method] = handler
        logger.debug(f"Registered handler for method: {method}")
    
    def unregister_handler(self, method: str) -> None:
        """Unregisters a handler for a method."""
        self._handlers.pop(method, None)

    def set_disconnect_handler(self, handler: Optional[DisconnectHandler]) -> None:
        """Register an optional callback invoked when a client disconnects."""
        self._disconnect_handler = handler

    def _auth_feature_list(self) -> list[str]:
        """Return feature names exposed for version/auth negotiation."""
        base_features = {
            "auth.hello",
            "ping",
            "version",
            "system.session_events",
            "system.notes_events",
            "system.memory_events",
        }
        base_features.update(self._handlers.keys())
        return sorted(base_features)

    def _build_auth_success_payload(self) -> str:
        payload = {
            "authenticated": True,
            "protocol_version": self._required_protocol_version,
            "features": self._auth_feature_list(),
        }
        return json.dumps(payload, ensure_ascii=False)

    def _remove_socket_path_if_safe(self, *, strict: bool) -> None:
        """
        Remove the configured socket path only when it is an actual socket node.

        When *strict* is True (startup path), encountering a non-socket existing
        path is treated as a hard error to avoid destructive unlink behavior.
        """
        socket_path = Path(self._socket_path)
        try:
            entry_stat = socket_path.lstat()
        except FileNotFoundError:
            return
        except OSError as exc:
            message = f"Unable to inspect socket path {socket_path}: {exc}"
            if strict:
                raise RuntimeError(message) from exc
            logger.warning(message)
            return

        if not stat.S_ISSOCK(entry_stat.st_mode):
            message = f"Refusing to remove non-socket path: {socket_path}"
            if strict:
                raise RuntimeError(message)
            logger.warning(message)
            return

        try:
            socket_path.unlink()
        except FileNotFoundError:
            return
        except OSError as exc:
            message = f"Failed to remove stale socket path {socket_path}: {exc}"
            if strict:
                raise RuntimeError(message) from exc
            logger.warning(message)
    
    async def start(self) -> None:
        """Starts the IPC server."""
        if self._running:
            logger.warning("Server is already running")
            return

        # Remove stale socket safely without unlinking arbitrary file types.
        self._remove_socket_path_if_safe(strict=True)
        
        # Create the server with a restrictive umask so socket permissions are
        # safe from the moment the path is created.
        original_umask = os.umask(0o177)
        try:
            self._server = await asyncio.start_unix_server(
                self._handle_client,
                path=self._socket_path,
            )
        finally:
            os.umask(original_umask)
        
        # Set socket permissions (owner read/write only)
        try:
            os.chmod(self._socket_path, 0o600)
        except OSError as e:
            logger.error(f"Failed to set socket permissions: {e}")
            raise
        
        self._running = True
        self._shutdown_event.clear()
        
        logger.info(f"IPC Server started on {self._socket_path}")
    
    async def stop(self) -> None:
        """Stops the IPC server and disconnects all clients."""
        if not self._running:
            return
        
        logger.info("Stopping IPC Server...")
        self._running = False
        
        # Close all client connections
        for client_id, client in list(self._clients.items()):
            try:
                await client.close()
            except Exception as e:
                logger.error(f"Error closing client {client_id}: {e}")
        
        self._clients.clear()
        
        # Close the server
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        
        # Remove socket file if and only if the path is still a socket node.
        self._remove_socket_path_if_safe(strict=False)
        
        self._shutdown_event.set()
        logger.info("IPC Server stopped")
    
    async def wait_for_shutdown(self) -> None:
        """Waits until the server is shut down."""
        await self._shutdown_event.wait()
    
    async def serve_forever(self) -> None:
        """Runs the server until stopped."""
        if not self._server:
            await self.start()
        
        # Wait on the shutdown event instead of server.serve_forever()
        # This allows stop() to unblock this method cleanly.
        try:
            await self._shutdown_event.wait()
        except asyncio.CancelledError:
            pass
        finally:
            if self._running:
                await self.stop()

    def _trace_message(self, direction: str, client_id: str, payload: bytes) -> None:
        """Write protocol in/out traces when debug tracing is enabled."""
        if not self._trace_enabled or self._trace_path is None:
            return

        decoded = payload.decode("utf-8", errors="replace")
        encoded = decoded.encode("utf-8", errors="replace")
        truncated = False
        if len(encoded) > self._trace_max_bytes:
            decoded = encoded[: self._trace_max_bytes].decode("utf-8", errors="replace")
            truncated = True

        request_id = None
        method = None
        correlation_id = None
        parsed: dict[str, Any] | None = None
        try:
            parsed_candidate = json.loads(decoded)
            if isinstance(parsed_candidate, dict):
                parsed = parsed_candidate
                request_id_value = parsed.get("id")
                if isinstance(request_id_value, str):
                    request_id = request_id_value
                method_value = parsed.get("method")
                if isinstance(method_value, str):
                    method = method_value
                params = parsed.get("params")
                if isinstance(params, dict):
                    corr = params.get("correlation_id")
                    if isinstance(corr, str) and corr.strip():
                        correlation_id = corr.strip()
        except Exception:
            parsed = None

        entry = redact_value(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "direction": direction,
                "client_id": client_id,
                "request_id": request_id,
                "method": method,
                "correlation_id": correlation_id,
                "truncated": truncated,
                "payload": parsed if parsed is not None else decoded,
            }
        )
        try:
            with self._trace_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.warning("Protocol trace write failed: %s", exc)
    
    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handles a new client connection."""
        # Generate client ID
        client_id = f"client-{len(self._clients) + 1}-{id(writer)}"
        
        # Check max clients
        if len(self._clients) >= self._max_clients:
            logger.warning(f"Max clients reached, rejecting {client_id}")
            writer.close()
            await writer.wait_closed()
            return
        
        # Create client connection
        client = ClientConnection(
            reader=reader,
            writer=writer,
            address=client_id,
            connected_at=asyncio.get_event_loop().time(),
            trace_outbound=lambda data: self._trace_message("out", client_id, data),
        )
        self._clients[client_id] = client
        
        logger.info(f"Client connected: {client_id}")
        
        try:
            # Enforce handshake timeout for first request
            await asyncio.wait_for(
                self._process_client(client_id, client),
                timeout=None  # _process_client handles its own timeouts, but we could add global session limit here
            )
        except asyncio.CancelledError:
            logger.debug(f"Client {client_id} cancelled")
        except Exception as e:
            logger.error(f"Error handling client {client_id}: {e}")
        finally:
            # Clean up
            self._clients.pop(client_id, None)
            if self._disconnect_handler is not None:
                try:
                    maybe_awaitable = self._disconnect_handler(client)
                    if inspect.isawaitable(maybe_awaitable):
                        await maybe_awaitable
                except Exception as e:
                    logger.error(f"Disconnect handler failed for {client_id}: {e}")
            try:
                await client.close()
            except Exception:
                pass
            logger.info(f"Client disconnected: {client_id}")
    
    async def _process_client(
        self,
        client_id: str,
        client: ClientConnection,
    ) -> None:
        """Processes messages from a client."""
        buffer = b""
        auth_complete = not self._require_auth
        
        while self._running:
            try:
                # Read data from client
                # Use stricter timeout for initial handshake
                timeout = self.HANDSHAKE_TIMEOUT if not auth_complete else 300.0
                
                data = await asyncio.wait_for(
                    client.reader.read(self.BUFFER_SIZE),
                    timeout=timeout,
                )
                
                if not data:
                    # Client disconnected
                    break
                
                # Add to buffer (bytes) and process newline-delimited messages
                buffer += data
                if len(buffer) > self.MAX_INCOMING_BUFFER:
                    logger.warning(
                        "Client %s exceeded max buffered request bytes (%s), closing connection",
                        client_id,
                        self.MAX_INCOMING_BUFFER,
                    )
                    error = ErrorMessage.parse_error(
                        "global",
                        "Request too large or missing newline delimiter",
                    )
                    try:
                        await client.send(error.to_bytes())
                    except Exception:
                        pass
                    break
                
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    line = line.strip()
                    
                    if not line:
                        continue

                    self._trace_message("in", client_id, line)
                    
                    try:
                        message = line.decode("utf-8")
                    except UnicodeDecodeError as e:
                        logger.error(f"Invalid UTF-8 from {client_id}: {e}")
                        error = ErrorMessage.parse_error("global", "Invalid UTF-8 in request")
                        try:
                            await client.send(error.to_bytes())
                        except (BrokenPipeError, ConnectionError, OSError):
                            logger.debug(f"Failed to send UTF-8 parse error to {client_id}")
                        continue

                    request_id = self._extract_request_id(message)
                    try:
                        request = IncomingRequest.from_json(message)
                    except json.JSONDecodeError as exc:
                        logger.error("Invalid JSON from %s during framing/auth: %s", client_id, exc)
                        error = ErrorMessage.parse_error(request_id, str(exc))
                        try:
                            await client.send(error.to_bytes())
                        except (BrokenPipeError, ConnectionError, OSError):
                            logger.debug(f"Failed to send parse error to {client_id}")
                        continue
                    except ValueError as exc:
                        logger.error("Invalid request payload from %s during framing/auth: %s", client_id, exc)
                        error = ErrorMessage.invalid_request(request_id, str(exc))
                        try:
                            await client.send(error.to_bytes())
                        except (BrokenPipeError, ConnectionError, OSError):
                            logger.debug(f"Failed to send invalid request error to {client_id}")
                        continue

                    if self._require_auth and not auth_complete:
                        if request.method != "auth.hello":
                            logger.warning(
                                "Rejecting unauthenticated method from %s: %s",
                                client_id,
                                request.method,
                            )
                            error = ErrorMessage.auth_required(
                                request.id,
                                "First request must be auth.hello",
                            )
                            try:
                                await client.send(error.to_bytes())
                            except (BrokenPipeError, ConnectionError, OSError):
                                logger.debug(f"Failed to send auth-required error to {client_id}")
                            break
                        auth_complete = await self._handle_auth_hello(client_id, client, request)
                        if not auth_complete:
                            break
                        continue

                    await self._handle_message(client_id, client, message)
                    
            except asyncio.TimeoutError:
                # Check connection liveness
                if client.writer.is_closing():
                    break
                if self._require_auth and not auth_complete:
                    logger.warning("Authentication timeout for %s; closing connection", client_id)
                    try:
                        await client.send(
                            ErrorMessage.auth_required(
                                "global",
                                "Authentication handshake timed out",
                            ).to_bytes()
                        )
                    except (BrokenPipeError, ConnectionError, OSError):
                        logger.debug("Failed to send auth-timeout error to %s", client_id)
                    break
                # Keepalive timeout after auth: continue and wait for next frame.
                continue
            except (ConnectionResetError, BrokenPipeError):
                break
            except Exception as e:
                logger.error(f"Error reading from client {client_id}: {e}")
                break

    async def _handle_auth_hello(
        self,
        client_id: str,
        client: ClientConnection,
        request: IncomingRequest,
    ) -> bool:
        """Validate auth.hello request and emit explicit auth negotiation result."""
        params = request.params
        client_name = params.get("client_name")
        client_pid = params.get("client_pid")
        protocol_version = params.get("protocol_version")
        auth_token = params.get("auth_token")

        if not isinstance(client_name, str) or not client_name.strip():
            await client.send(
                ErrorMessage.invalid_request(
                    request.id,
                    "auth.hello requires non-empty client_name",
                ).to_bytes()
            )
            return False
        if not isinstance(client_pid, int) or client_pid <= 0:
            await client.send(
                ErrorMessage.invalid_request(
                    request.id,
                    "auth.hello requires positive integer client_pid",
                ).to_bytes()
            )
            return False
        if not isinstance(protocol_version, str) or not protocol_version.strip():
            await client.send(
                ErrorMessage.invalid_request(
                    request.id,
                    "auth.hello requires protocol_version",
                ).to_bytes()
            )
            return False
        if protocol_version != self._required_protocol_version:
            await client.send(
                ErrorMessage.protocol_mismatch(
                    request.id,
                    (
                        f"Client protocol {protocol_version!r} is not supported; "
                        f"required {self._required_protocol_version!r}"
                    ),
                ).to_bytes()
            )
            return False
        if not isinstance(auth_token, str) or not auth_token:
            await client.send(
                ErrorMessage.auth_failed(
                    request.id,
                    "Missing auth token",
                ).to_bytes()
            )
            return False
        if auth_token != self._auth_token:
            await client.send(
                ErrorMessage.auth_failed(
                    request.id,
                    "Invalid auth token",
                ).to_bytes()
            )
            return False

        await client.send(
            ResultMessage.create(
                request.id,
                self._build_auth_success_payload(),
            ).to_bytes()
        )
        logger.info(
            "Client authenticated: %s (client_name=%s, client_pid=%s)",
            client_id,
            client_name,
            client_pid,
        )
        return True
    
    async def _handle_message(
        self,
        client_id: str,
        client: ClientConnection,
        message: str,
    ) -> None:
        """Handles a single message from a client."""
        request_id = self._extract_request_id(message)
        started = time.perf_counter()
        context_tokens = None
        method = None
        last_error_type: str | None = None
        last_error_message: str | None = None
        try:
            # Parse the message
            request = IncomingRequest.from_json(message)
            request_id = request.id
            method = request.method
            correlation_id = generate_correlation_id()
            correlation_value = request.params.get("correlation_id")
            if isinstance(correlation_value, str):
                trimmed = correlation_value.strip()
                if trimmed:
                    correlation_id = trimmed[:128]
            context_tokens = set_request_context(
                correlation_id=correlation_id,
                request_id=request_id,
                method=request.method,
            )
            logger.debug(f"Received request from {client_id}: method={request.method}")
            
            # Find handler
            handler = self._handlers.get(request.method)
            
            if handler is None:
                # Method not found
                error = ErrorMessage.method_not_found(request.id, request.method)
                await client.send(error.to_bytes())
                return
            
            # Execute handler
            await handler(request, client)
            
        except json.JSONDecodeError as e:
            last_error_type = type(e).__name__
            last_error_message = str(e)
            logger.error(f"Invalid JSON from {client_id}: {e}")
            error = ErrorMessage.parse_error(request_id, str(e))
            try:
                await client.send(error.to_bytes())
            except (BrokenPipeError, ConnectionError, OSError):
                logger.debug(f"Failed to send parse error to {client_id}")
        except ValueError as e:
            last_error_type = type(e).__name__
            last_error_message = str(e)
            logger.error(f"Invalid request from {client_id}: {e}")
            error = ErrorMessage.invalid_request(request_id, str(e))
            try:
                await client.send(error.to_bytes())
            except (BrokenPipeError, ConnectionError, OSError):
                logger.debug(f"Failed to send invalid-request error to {client_id}")
        except Exception as e:
            last_error_type = type(e).__name__
            last_error_message = str(e)
            logger.error(f"Error handling message from {client_id}: {e}")
            error = ErrorMessage.internal_error(
                request_id,
                _format_exception_message(e),
            )
            try:
                await client.send(error.to_bytes())
            except (BrokenPipeError, ConnectionError, OSError):
                logger.debug(f"Failed to send error response to {client_id}")
        finally:
            duration_ms = (time.perf_counter() - started) * 1000.0
            logger.info(
                "rpc_message_complete",
                extra={
                    "component": "ipc.server",
                    "request_id": request_id,
                    "method": method,
                    "duration_ms": round(duration_ms, 3),
                    "error_type": last_error_type,
                    "error_message": last_error_message,
                    "client_id": client_id,
                },
            )
            if context_tokens is not None:
                reset_request_context(context_tokens)

    def _extract_request_id(self, message: str) -> str:
        """Best-effort extraction of request id for correlation on parse failures."""
        try:
            parsed = json.loads(message)
            request_id = parsed.get("id")
            if isinstance(request_id, str) and request_id:
                return request_id
        except Exception:
            pass
        return "global"
    
    async def broadcast(self, message: bytes) -> None:
        """Broadcasts a message to all connected clients."""
        for client in self._clients.values():
            try:
                await client.send(message)
            except Exception as e:
                logger.error(f"Error broadcasting to {client.address}: {e}")
    
    def create_streaming_handler(
        self,
        client: ClientConnection,
        request_id: str,
    ) -> StreamingHandler:
        """Creates a streaming handler for a client."""
        return StreamingHandler(
            send_func=client.send,
            request_id=request_id,
        )


class IPCServerManager:
    """
    Manager for IPC server lifecycle.
    
    Provides context manager support and integration with the main application.
    """
    
    def __init__(self, server: Optional[IPCServer] = None):
        """Initializes the manager."""
        self._server = server or IPCServer()
        self._task: Optional[asyncio.Task] = None
    
    @property
    def server(self) -> IPCServer:
        """Returns the managed server."""
        return self._server
    
    async def __aenter__(self) -> "IPCServerManager":
        """Starts the server."""
        await self._server.start()
        self._task = asyncio.create_task(self._run_server())
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Stops the server."""
        await self._server.stop()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
    
    async def _run_server(self) -> None:
        """Background task running the server."""
        try:
            await self._server.serve_forever()
        except asyncio.CancelledError:
            pass
