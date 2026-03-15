"""
IPC Server for WebSocket communication with SwiftUI frontend.

Provides an async server that:
- Listens on a WebSocket endpoint
- Handles multiple client connections
- Routes incoming requests to appropriate handlers
- Sends streaming responses back to clients
"""

import asyncio
import inspect
import json
import logging
import os
import secrets
import ssl
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional, Awaitable
from dataclasses import dataclass
from websockets.asyncio.server import Server, ServerConnection, serve
from websockets.exceptions import ConnectionClosed

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


class _SlidingWindowRateLimiter:
    """Per-client sliding-window rate limiter."""

    _EXEMPT_METHODS = frozenset({"auth.hello", "ping"})

    def __init__(self, max_requests: int, window_seconds: float):
        if max_requests <= 0 or window_seconds <= 0:
            raise ValueError("max_requests and window_seconds must be positive")
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._windows: dict[str, list[float]] = {}

    def check(self, client_id: str, method: str) -> bool:
        """Return True if the request is allowed, False if rate-limited."""
        if method in self._EXEMPT_METHODS:
            return True
        now = time.monotonic()
        window = self._windows.get(client_id)
        if window is None:
            window = []
            self._windows[client_id] = window
        cutoff = now - self._window_seconds
        # Prune expired entries
        while window and window[0] < cutoff:
            window.pop(0)
        if len(window) >= self._max_requests:
            return False
        window.append(now)
        return True

    def remove_client(self, client_id: str) -> None:
        """Remove tracking state for a disconnected client."""
        self._windows.pop(client_id, None)


@dataclass
class ClientConnection:
    """Represents a connected client."""

    websocket: ServerConnection
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
        try:
            await self.websocket.send(data)
        except ConnectionClosed:
            # Client disconnected during write; ignore
            pass

    async def close(self) -> None:
        """Closes the client connection."""
        try:
            await self.websocket.close()
        except (ConnectionClosed, OSError):
            pass


# Type alias for request handlers
RequestHandler = Callable[[IncomingRequest, ClientConnection], Awaitable[None]]
DisconnectHandler = Callable[[ClientConnection], Awaitable[None] | None]


class IPCServer:
    """
    WebSocket server for SwiftUI frontend communication.
    
    Usage:
        server = IPCServer()
        server.register_handler("prompt", handle_prompt)
        await server.start()
        # ... run until shutdown
        await server.stop()
    """
    
    DEFAULT_HOST = os.environ.get("AI_AGENT_IPC_HOST", "127.0.0.1").strip() or "127.0.0.1"
    DEFAULT_PORT = 8765
    MAX_INCOMING_BUFFER = 16 * 1_048_576
    # Timeout for client handshake/first request to prevent resource exhaustion
    HANDSHAKE_TIMEOUT = 10.0
    
    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        max_clients: int = 5,
        *,
        require_auth: bool = False,
        auth_token: str | None = None,
        required_protocol_version: str = PROTOCOL_VERSION,
    ):
        """
        Initializes the IPC server.
        
        Args:
            host: Interface to bind the WebSocket server to.
            port: TCP port to bind the WebSocket server to.
            max_clients: Maximum number of concurrent clients.
            require_auth: Whether to enforce auth.hello before any RPC method.
            auth_token: Shared auth token expected from the frontend.
            required_protocol_version: Required frontend protocol version.
        """
        self._host = (host or self.DEFAULT_HOST).strip() or self.DEFAULT_HOST
        resolved_port = self.DEFAULT_PORT if port is None else int(port)
        if resolved_port < 0 or resolved_port > 65535:
            raise ValueError("WebSocket port must be between 0 and 65535")
        self._port = resolved_port
        self._max_clients = max_clients
        self._require_auth = require_auth
        self._auth_token = (auth_token or "").strip()
        self._required_protocol_version = required_protocol_version
        self._server: Optional[Server] = None
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
        self._rate_limiter = _SlidingWindowRateLimiter(
            max_requests=max(1, _safe_env_int("AI_AGENT_IPC_RATE_LIMIT", 30)),
            window_seconds=max(1, _safe_env_int("AI_AGENT_IPC_RATE_WINDOW", 10)),
        )
        # Auth rotation: one-time tokens issued per auth.hello success.
        self._active_rotation_tokens: dict[str, dict[str, object]] = {}
        self._rotation_token_ttl_seconds = 3600.0
        self._tls_enabled = False
    
    @property
    def endpoint_url(self) -> str:
        """Returns the bound WebSocket endpoint URL."""
        scheme = "wss" if self._tls_enabled else "ws"
        return f"{scheme}://{self._host}:{self._port}"
    
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

    def _generate_rotation_token(self, client_id: str) -> str:
        """Generate a one-time rotation token for a client."""
        token = secrets.token_urlsafe(32)
        self._active_rotation_tokens[token] = {
            "client_id": client_id,
            "created_at": time.monotonic(),
        }
        return token

    def _consume_rotation_token(self, token: str) -> str | None:
        """Consume a rotation token if valid and not expired.

        Returns the associated client_id on success, None otherwise.
        """
        entry = self._active_rotation_tokens.pop(token, None)
        if entry is None:
            return None
        created_at = entry["created_at"]
        if not isinstance(created_at, (int, float)):
            return None
        elapsed = time.monotonic() - created_at
        if elapsed > self._rotation_token_ttl_seconds:
            logger.debug("Rotation token expired (%.1fs old)", elapsed)
            return None
        client_id = entry["client_id"]
        return client_id if isinstance(client_id, str) else None

    def _purge_rotation_tokens_for_client(self, client_id: str) -> None:
        """Remove all rotation tokens associated with a client."""
        to_remove = [
            tok for tok, entry in self._active_rotation_tokens.items()
            if entry.get("client_id") == client_id
        ]
        for tok in to_remove:
            self._active_rotation_tokens.pop(tok, None)

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

    def _build_auth_success_payload(
        self, *, rotation_token: str | None = None
    ) -> str:
        payload: dict[str, object] = {
            "authenticated": True,
            "protocol_version": self._required_protocol_version,
            "features": self._auth_feature_list(),
        }
        if rotation_token is not None:
            payload["rotation_token"] = rotation_token
        return json.dumps(payload, ensure_ascii=False)

    @staticmethod
    def _is_allowed_ip(ip: str) -> bool:
        """Check if an IP is from a trusted subnet (Tailscale, localhost, or private)."""
        import ipaddress
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False

        # Localhost
        if addr.is_loopback:
            return True

        # Tailscale CGNAT range: 100.64.0.0/10
        tailscale_net = ipaddress.ip_network("100.64.0.0/10")
        if addr in tailscale_net:
            return True

        # RFC 1918 private ranges (LAN)
        if addr.is_private:
            return True

        return False

    def _build_ssl_context(self) -> ssl.SSLContext | None:
        """Build an SSL context from env-configured cert/key files.

        Returns None (plain ws://) when certs are not configured.
        Sets ``self._tls_enabled`` when TLS is active.
        """
        require_tls = os.environ.get("AI_AGENT_REQUIRE_TLS", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        cert_path = os.environ.get("AI_AGENT_TLS_CERT", "").strip()
        key_path = os.environ.get("AI_AGENT_TLS_KEY", "").strip()
        if not cert_path or not key_path:
            if require_tls:
                raise RuntimeError("AI_AGENT_REQUIRE_TLS is set but TLS cert/key env vars are missing.")
            return None
        cert_file = Path(cert_path).expanduser().resolve(strict=False)
        key_file = Path(key_path).expanduser().resolve(strict=False)
        if not cert_file.is_file():
            if require_tls:
                raise RuntimeError(f"Required TLS cert file not found: {cert_file}")
            logger.warning("TLS cert file not found: %s — falling back to plain ws://", cert_file)
            return None
        if not key_file.is_file():
            if require_tls:
                raise RuntimeError(f"Required TLS key file not found: {key_file}")
            logger.warning("TLS key file not found: %s — falling back to plain ws://", key_file)
            return None
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        # ATS-compatible Forward Secrecy cipher suites
        ctx.set_ciphers(
            "ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20"
        )
        ctx.load_cert_chain(str(cert_file), str(key_file))
        self._tls_enabled = True
        logger.info("TLS enabled with cert=%s", cert_file)
        return ctx

    async def start(self) -> None:
        """Starts the IPC server."""
        if self._running:
            logger.warning("Server is already running")
            return

        # Optional TLS for iOS ATS compliance; plain ws:// for local connections.
        ssl_context = self._build_ssl_context()

        self._server = await serve(
            self._handle_client,
            self._host,
            self._port,
            max_size=self.MAX_INCOMING_BUFFER,
            open_timeout=self.HANDSHAKE_TIMEOUT,
            ssl=ssl_context,
        )
        bound = self._server.sockets[0].getsockname()
        self._host = str(bound[0])
        self._port = int(bound[1])
        self._running = True
        self._shutdown_event.clear()

        logger.info("IPC Server started on %s", self.endpoint_url)
    
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
        self._active_rotation_tokens.clear()

        # Close the server
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        
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
        websocket: ServerConnection,
    ) -> None:
        """Handles a new client connection."""
        # Generate client ID
        client_id = f"client-{len(self._clients) + 1}-{id(websocket)}"

        # Security: when bound to 0.0.0.0, restrict to Tailscale/local/private subnets
        if self._host == "0.0.0.0":
            remote_addr = websocket.remote_address
            client_ip = remote_addr[0] if remote_addr else ""
            if not self._is_allowed_ip(client_ip):
                logger.warning(
                    "Rejected connection from non-Tailscale IP: %s (client %s)",
                    client_ip, client_id,
                )
                await websocket.close(code=1008, reason="Connection not allowed from this IP")
                return
        
        # Check max clients
        if len(self._clients) >= self._max_clients:
            logger.warning(f"Max clients reached, rejecting {client_id}")
            await websocket.close(code=1013, reason="Max clients reached")
            return
        
        # Create client connection
        client = ClientConnection(
            websocket=websocket,
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
            self._rate_limiter.remove_client(client_id)
            self._purge_rotation_tokens_for_client(client_id)
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
        auth_complete = not self._require_auth

        while self._running:
            try:
                timeout = self.HANDSHAKE_TIMEOUT if not auth_complete else 300.0
                incoming = await asyncio.wait_for(client.websocket.recv(), timeout=timeout)
                if incoming is None:
                    break

                if isinstance(incoming, bytes):
                    payload = incoming
                    try:
                        message = incoming.decode("utf-8")
                    except UnicodeDecodeError as exc:
                        logger.error("Invalid UTF-8 from %s: %s", client_id, exc)
                        await client.send(ErrorMessage.parse_error("global", "Invalid UTF-8 in request").to_bytes())
                        continue
                else:
                    message = incoming
                    payload = incoming.encode("utf-8")

                self._trace_message("in", client_id, payload)
                request_id = self._extract_request_id(message)
                try:
                    request = IncomingRequest.from_json(message)
                except json.JSONDecodeError as exc:
                    logger.error("Invalid JSON from %s during framing/auth: %s", client_id, exc)
                    await client.send(ErrorMessage.parse_error(request_id, str(exc)).to_bytes())
                    continue
                except ValueError as exc:
                    logger.error("Invalid request payload from %s during framing/auth: %s", client_id, exc)
                    await client.send(ErrorMessage.invalid_request(request_id, str(exc)).to_bytes())
                    continue

                if self._require_auth and not auth_complete:
                    if request.method != "auth.hello":
                        logger.warning("Rejecting unauthenticated method from %s: %s", client_id, request.method)
                        await client.send(
                            ErrorMessage.auth_required(request.id, "First request must be auth.hello").to_bytes()
                        )
                        break
                    auth_complete = await self._handle_auth_hello(client_id, client, request)
                    if not auth_complete:
                        break
                    continue

                if not self._rate_limiter.check(client_id, request.method):
                    logger.warning("Rate limiting client %s for method %s", client_id, request.method)
                    await client.send(
                        ErrorMessage.rate_limited(
                            request.id,
                            f"Exceeded {self._rate_limiter._max_requests} requests "
                            f"per {self._rate_limiter._window_seconds}s window",
                        ).to_bytes()
                    )
                    continue

                await self._handle_message(client_id, client, message)
            except asyncio.TimeoutError:
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
            except ConnectionClosed:
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
        # Dual-token validation: check rotation token first, then bootstrap.
        rotation_token_param = params.get("rotation_token")
        token_valid = False
        auth_method = "bootstrap"

        if isinstance(rotation_token_param, str) and rotation_token_param:
            consumed_client = self._consume_rotation_token(rotation_token_param)
            if consumed_client is not None:
                token_valid = True
                auth_method = "rotation"

        if not token_valid:
            if not isinstance(auth_token, str) or not auth_token:
                await client.send(
                    ErrorMessage.auth_failed(
                        request.id,
                        "Missing auth token",
                    ).to_bytes()
                )
                return False
            if auth_token == self._auth_token:
                token_valid = True

        if not token_valid:
            await client.send(
                ErrorMessage.auth_failed(
                    request.id,
                    "Invalid auth token",
                ).to_bytes()
            )
            return False

        # Auth succeeded — issue a fresh rotation token for reconnect.
        new_rotation_token = self._generate_rotation_token(client_id)

        await client.send(
            ResultMessage.create(
                request.id,
                self._build_auth_success_payload(
                    rotation_token=new_rotation_token
                ),
            ).to_bytes()
        )
        logger.info(
            "Client authenticated: %s (client_name=%s, client_pid=%s, method=%s)",
            client_id,
            client_name,
            client_pid,
            auth_method,
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
