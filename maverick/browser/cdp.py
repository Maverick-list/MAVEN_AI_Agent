"""Maverick DevOS - Minimalist Synchronous Chrome DevTools Protocol (CDP) Client.

RFC 6455 Protocol Implementation Notes & Limitations:
-----------------------------------------------------
Supported Features:
- Synchronous RFC 6455 WebSocket client handshake (HTTP/1.1 Upgrade to WebSocket version 13).
- Mandatory client-to-server 4-byte frame masking (XOR with cryptographically secure random key).
- Standard payload length decoding: 7-bit (<=125 bytes), 16-bit (126 extended), and 64-bit (127 extended).
- Control Frame Handling:
  * Ping (opcode 0x9): Immediately responds with masked Pong (opcode 0xA) preserving payload.
  * Pong (opcode 0xA): Gracefully ignores unsolicited or solicited server Pong frames.
  * Close (opcode 0x8): Gracefully echoes Close frame and terminates socket connection.
- Message Fragmentation: Reassembles multi-frame fragmented text messages across continuation frames (opcode 0x0).
- Correlated JSON-RPC: Correlates command responses by message ID, gracefully skipping broadcast events.
- Strict Endpoint Validation: Validates loopback binding and DevTools target path before TCP connection.

Unsupported Features / Documented Limitations:
- Per-message compression extensions (RFC 7692 'permessage-deflate') are not negotiated or supported.
- Arbitrary binary streaming (opcode 0x2) is not decoded; payload is treated as UTF-8 text.
- Multiplexed multi-channel subprotocols are not supported.
"""

import base64
import json
import os
import socket
import struct
import time
import urllib.parse
from typing import Any, Dict, Optional
from maverick.browser.security import validate_cdp_ws_url, BrowserSecurityError


class CDPError(Exception):
    """Base error for CDP protocol communication."""
    pass


class CDPConnectionClosedError(CDPError):
    """Raised when the CDP connection is closed by remote host."""
    pass


class CDPTimeoutError(CDPError):
    """Raised when a CDP command exceeds timeout."""
    pass


class CDPClient:
    """Synchronous pure-Python RFC 6455 WebSocket client for CDP targets."""

    def __init__(self, ws_url: str, timeout: float = 5.0):
        # Enforce strict loopback and path validation
        self.ws_url = validate_cdp_ws_url(ws_url)
        self.timeout = timeout
        self.sock: Optional[socket.socket] = None
        self._msg_counter = 0
        self._is_closed = False
        self._connect()

    def _connect(self) -> None:
        """Establish TCP connection and perform WebSocket upgrade handshake."""
        parsed = urllib.parse.urlsplit(self.ws_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 9222
        path = parsed.path
        if parsed.query:
            path += "?" + parsed.query

        host_header = f"{host}:{port}"

        try:
            self.sock = socket.create_connection((host, port), timeout=self.timeout)
            key = base64.b64encode(os.urandom(16)).decode("utf-8")
            handshake = (
                f"GET {path} HTTP/1.1\r\n"
                f"Host: {host_header}\r\n"
                f"Upgrade: websocket\r\n"
                f"Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {key}\r\n"
                f"Sec-WebSocket-Version: 13\r\n\r\n"
            )
            self.sock.sendall(handshake.encode("utf-8"))

            # Read handshake response
            header_data = b""
            while b"\r\n\r\n" not in header_data:
                chunk = self.sock.recv(1024)
                if not chunk:
                    raise CDPConnectionClosedError("Connection closed during WebSocket handshake.")
                header_data += chunk

            resp_text = header_data.decode("utf-8", errors="ignore")
            if " 101 " not in resp_text:
                raise CDPError(
                    f"WebSocket upgrade rejected by browser: {resp_text.splitlines()[0] if resp_text else 'No response'}"
                )

        except Exception as exc:
            self.close()
            raise CDPError(f"Failed to connect to CDP target at {self.ws_url}: {str(exc)}")

    def _send_raw_frame(self, opcode: int, payload: bytes) -> None:
        """Construct and transmit an RFC 6455 masked frame to the server."""
        if not self.sock:
            raise CDPConnectionClosedError("Cannot send frame: socket is closed.")

        length = len(payload)
        header = bytearray([0x80 | (opcode & 0x0F)])  # FIN bit set + Opcode
        mask = os.urandom(4)

        if length <= 125:
            header.append(0x80 | length)
        elif length <= 65535:
            header.append(0x80 | 126)
            header.extend(struct.pack(">H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack(">Q", length))

        header.extend(mask)
        masked_payload = bytearray(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(header + masked_payload)

    def send_command(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Send a JSON-RPC command and await response matching message ID."""
        if not self.sock or self._is_closed:
            raise CDPConnectionClosedError("CDP socket is not connected.")

        self._msg_counter += 1
        msg_id = self._msg_counter
        payload = json.dumps({
            "id": msg_id,
            "method": method,
            "params": params or {}
        }).encode("utf-8")

        try:
            self._send_raw_frame(opcode=0x01, payload=payload)
        except Exception as exc:
            self.close()
            raise CDPConnectionClosedError(f"Socket write failed: {exc}")

        # Wait for matching response
        deadline = time.time() + (timeout or self.timeout)
        while time.time() < deadline:
            remaining = max(0.1, deadline - time.time())
            self.sock.settimeout(remaining)
            try:
                msg_text = self._recv_complete_message()
                if not msg_text:
                    continue
                parsed = json.loads(msg_text)
                if parsed.get("id") == msg_id:
                    if "error" in parsed:
                        err = parsed["error"]
                        raise CDPError(f"CDP command '{method}' failed: {err.get('message', str(err))}")
                    return parsed.get("result", {})
                # Non-matching message (e.g. CDP event notification); continue loop
            except socket.timeout:
                raise CDPTimeoutError(f"CDP command '{method}' timed out after {timeout or self.timeout}s")
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue

        raise CDPTimeoutError(f"CDP command '{method}' timed out waiting for response.")

    def _recv_complete_message(self) -> Optional[str]:
        """
        Read complete message from WebSocket, handling control frames (Ping, Pong, Close)
        and reassembling fragmented messages across continuation frames.
        """
        assembled_payload = bytearray()

        while True:
            header = self._recv_exact(2)
            if not header:
                return None

            b1, b2 = header[0], header[1]
            fin = (b1 & 0x80) != 0
            rsv = b1 & 0x70
            opcode = b1 & 0x0F

            if rsv != 0:
                self.close()
                raise CDPError("WebSocket RSV bits set without negotiated extension.")

            has_mask = (b2 & 0x80) != 0
            length = b2 & 0x7F

            if length == 126:
                ext = self._recv_exact(2)
                length = struct.unpack(">H", ext)[0]
            elif length == 127:
                ext = self._recv_exact(8)
                length = struct.unpack(">Q", ext)[0]

            mask = self._recv_exact(4) if has_mask else None
            raw_payload = self._recv_exact(length)

            if has_mask and mask:
                raw_payload = bytearray(b ^ mask[i % 4] for i, b in enumerate(raw_payload))

            # Handle RFC 6455 Opcodes
            if opcode == 0x09:  # Ping
                # Immediately send masked Pong with identical application data
                try:
                    self._send_raw_frame(opcode=0x0A, payload=raw_payload)
                except Exception:
                    pass
                continue

            elif opcode == 0x0A:  # Pong
                # Unsolicited Pong; discard and continue
                continue

            elif opcode == 0x08:  # Close
                # Echo close and terminate cleanly
                try:
                    self._send_raw_frame(opcode=0x08, payload=raw_payload[:2])
                except Exception:
                    pass
                self.close()
                raise CDPConnectionClosedError("Remote endpoint sent WebSocket Close frame.")

            elif opcode in (0x01, 0x02, 0x00):  # Text, Binary, or Continuation
                assembled_payload.extend(raw_payload)
                if fin:
                    return assembled_payload.decode("utf-8", errors="ignore")
                # More continuation frames expected; continue reading

            else:
                self.close()
                raise CDPError(f"Unsupported WebSocket opcode: 0x{opcode:x}")

    def _recv_exact(self, num_bytes: int) -> bytearray:
        """Read exactly num_bytes from the socket."""
        buf = bytearray()
        while len(buf) < num_bytes:
            chunk = self.sock.recv(num_bytes - len(buf))
            if not chunk:
                raise CDPConnectionClosedError("Connection terminated while reading frame.")
            buf.extend(chunk)
        return buf

    def close(self) -> None:
        """Close the socket connection cleanly."""
        if not self._is_closed:
            self._is_closed = True
            if self.sock:
                try:
                    # Send close frame (0x88) masked
                    mask = os.urandom(4)
                    header = bytearray([0x88, 0x80]) + mask
                    self.sock.sendall(header)
                    self.sock.close()
                except Exception:
                    pass
                finally:
                    self.sock = None
