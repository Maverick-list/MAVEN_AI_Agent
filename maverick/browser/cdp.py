"""Maverick DevOS - Minimalist Synchronous Chrome DevTools Protocol (CDP) Client."""

import base64
import json
import os
import socket
import struct
import time
from typing import Any, Dict, Optional


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
        self.ws_url = ws_url
        self.timeout = timeout
        self.sock: Optional[socket.socket] = None
        self._msg_counter = 0
        self._connect()

    def _connect(self) -> None:
        """Establish TCP connection and perform WebSocket upgrade handshake."""
        clean_url = self.ws_url.replace("ws://", "")
        if "/" not in clean_url:
            raise CDPError(f"Malformed WebSocket URL: '{self.ws_url}'")

        host_port, path = clean_url.split("/", 1)
        path = "/" + path
        if ":" in host_port:
            host, port_str = host_port.split(":")
            port = int(port_str)
        else:
            host, port = host_port, 80

        try:
            self.sock = socket.create_connection((host, port), timeout=self.timeout)
            key = base64.b64encode(os.urandom(16)).decode("utf-8")
            handshake = (
                f"GET {path} HTTP/1.1\r\n"
                f"Host: {host_port}\r\n"
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
                raise CDPError(f"WebSocket upgrade rejected by browser: {resp_text.splitlines()[0] if resp_text else 'No response'}")

        except Exception as exc:
            self.close()
            raise CDPError(f"Failed to connect to CDP target at {self.ws_url}: {str(exc)}")

    def send_command(self, method: str, params: Optional[Dict[str, Any]] = None, timeout: Optional[float] = None) -> Dict[str, Any]:
        """Send a JSON-RPC command and await response matching message ID."""
        if not self.sock:
            raise CDPConnectionClosedError("CDP socket is not connected.")

        self._msg_counter += 1
        msg_id = self._msg_counter
        payload = json.dumps({
            "id": msg_id,
            "method": method,
            "params": params or {}
        }).encode("utf-8")

        # Encode RFC 6455 masked text frame
        length = len(payload)
        header = bytearray([0x81])  # FIN + Text frame (opcode 0x1)
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

        try:
            self.sock.sendall(header + masked_payload)
        except Exception as exc:
            self.close()
            raise CDPConnectionClosedError(f"Socket write failed: {exc}")

        # Wait for matching response
        deadline = time.time() + (timeout or self.timeout)
        while time.time() < deadline:
            remaining = max(0.1, deadline - time.time())
            self.sock.settimeout(remaining)
            try:
                frame_text = self._recv_frame()
                if not frame_text:
                    continue
                parsed = json.loads(frame_text)
                if parsed.get("id") == msg_id:
                    if "error" in parsed:
                        err = parsed["error"]
                        raise CDPError(f"CDP command '{method}' failed: {err.get('message', str(err))}")
                    return parsed.get("result", {})
            except socket.timeout:
                raise CDPTimeoutError(f"CDP command '{method}' timed out after {timeout or self.timeout}s")
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue

        raise CDPTimeoutError(f"CDP command '{method}' timed out waiting for response.")

    def _recv_frame(self) -> Optional[str]:
        """Read and decode a single RFC 6455 frame from the socket."""
        header = self._recv_exact(2)
        if not header:
            return None

        b1, b2 = header[0], header[1]
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

        return raw_payload.decode("utf-8", errors="ignore")

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
        if self.sock:
            try:
                # Send close frame (0x88)
                self.sock.sendall(bytearray([0x88, 0x80]) + os.urandom(4))
                self.sock.close()
            except Exception:
                pass
            finally:
                self.sock = None
