"""Unit tests for pure-Python WebSocket CDP client and RFC 6455 protocol handling."""

import json
import os
import socket
import sys
import threading
import time
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from maverick.browser.cdp import (
    CDPClient,
    CDPError,
    CDPConnectionClosedError,
    CDPTimeoutError,
)


class MockCDPServer:
    """Mock WebSocket server capable of testing various RFC 6455 behaviors."""

    def __init__(self, handler_mode: str = "echo"):
        self.handler_mode = handler_mode
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_sock.bind(("127.0.0.1", 0))
        self.port = self.server_sock.getsockname()[1]
        self.server_sock.listen(1)
        self.running = True
        self.conn = None
        self.last_client_masked = None
        self.received_pong_payload = None
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _send_server_frame(self, opcode: int, payload: bytes, fin: bool = True, rsv: int = 0) -> None:
        """Helper to send unmasked server frame."""
        if not self.conn:
            return
        b1 = (0x80 if fin else 0x00) | (rsv & 0x70) | (opcode & 0x0F)
        frame = bytearray([b1])
        length = len(payload)
        if length < 126:
            frame.append(length)
        elif length < 65536:
            frame.append(126)
            frame.extend(length.to_bytes(2, "big"))
        else:
            frame.append(127)
            frame.extend(length.to_bytes(8, "big"))
        frame.extend(payload)
        self.conn.sendall(frame)

    def _run(self):
        try:
            self.conn, _ = self.server_sock.accept()
            # Perform HTTP Upgrade Handshake
            request = b""
            while b"\r\n\r\n" not in request:
                chunk = self.conn.recv(1024)
                if not chunk:
                    break
                request += chunk

            handshake_resp = (
                b"HTTP/1.1 101 Switching Protocols\r\n"
                b"Upgrade: websocket\r\n"
                b"Connection: Upgrade\r\n"
                b"Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZ9/K+xOo=\r\n\r\n"
            )
            self.conn.sendall(handshake_resp)

            while self.running:
                header = self.conn.recv(2)
                if not header or len(header) < 2:
                    break
                b1, b2 = header[0], header[1]
                opcode = b1 & 0x0F
                has_mask = (b2 & 0x80) != 0
                self.last_client_masked = has_mask
                payload_len = b2 & 0x7F
                if payload_len == 126:
                    ext = self.conn.recv(2)
                    payload_len = int.from_bytes(ext, "big")
                elif payload_len == 127:
                    ext = self.conn.recv(8)
                    payload_len = int.from_bytes(ext, "big")

                mask_key = self.conn.recv(4) if has_mask else None
                masked_data = self.conn.recv(payload_len)
                unmasked = bytes(b ^ mask_key[i % 4] for i, b in enumerate(masked_data)) if has_mask else masked_data

                # If Pong frame received from client
                if opcode == 0x0A:
                    self.received_pong_payload = unmasked
                    continue

                # If Close frame received
                if opcode == 0x08:
                    break

                # If text frame
                if opcode == 0x01:
                    msg = json.loads(unmasked.decode("utf-8"))
                    cmd_id = msg.get("id")
                    method = msg.get("method")

                    if self.handler_mode == "echo":
                        resp_payload = {"id": cmd_id, "result": {"echo_method": method, "status": "ok"}}
                        self._send_server_frame(0x01, json.dumps(resp_payload).encode("utf-8"))

                    elif self.handler_mode == "with_broadcast_events":
                        # Send async event first
                        event = {"method": "Page.loadEventFired", "params": {"timestamp": 12345}}
                        self._send_server_frame(0x01, json.dumps(event).encode("utf-8"))
                        # Then send command reply
                        resp_payload = {"id": cmd_id, "result": {"echo_method": method, "event_skipped": True}}
                        self._send_server_frame(0x01, json.dumps(resp_payload).encode("utf-8"))

                    elif self.handler_mode == "fragmented":
                        # Send text in two fragments
                        full_msg = json.dumps({"id": cmd_id, "result": {"fragmented": True}}).encode("utf-8")
                        mid = len(full_msg) // 2
                        self._send_server_frame(0x01, full_msg[:mid], fin=False)  # Opcode 1, fin=False
                        self._send_server_frame(0x00, full_msg[mid:], fin=True)   # Opcode 0, fin=True

                    elif self.handler_mode == "ping":
                        # Send a Ping frame to the client
                        self._send_server_frame(0x09, b"heartbeat-payload")
                        time.sleep(0.1)
                        # Then reply to command
                        resp_payload = {"id": cmd_id, "result": {"pong_verified": True}}
                        self._send_server_frame(0x01, json.dumps(resp_payload).encode("utf-8"))

                    elif self.handler_mode == "rsv_error":
                        # Send frame with RSV1 bit set
                        self._send_server_frame(0x01, b'{"id":1}', fin=True, rsv=0x40)

                    elif self.handler_mode == "server_close":
                        # Server sends close frame
                        self._send_server_frame(0x08, b"\x03\xe8Normal Closure")

                    elif self.handler_mode == "timeout":
                        # Never reply
                        time.sleep(2.0)

        except Exception:
            pass
        finally:
            if self.conn:
                try:
                    self.conn.close()
                except Exception:
                    pass
            self.server_sock.close()

    def close(self):
        self.running = False
        if self.conn:
            try:
                self.conn.close()
            except Exception:
                pass
        try:
            self.server_sock.close()
        except Exception:
            pass


class TestCDPClient(unittest.TestCase):
    """Test pure-Python WebSocket client and RFC 6455 protocol conformance."""

    def test_cdp_send_and_receive_with_masking(self):
        """Test sending CDP command, ensuring client frame is masked and reply correlated."""
        server = MockCDPServer(handler_mode="echo")
        try:
            client = CDPClient(f"ws://127.0.0.1:{server.port}/devtools/page/test-tab", timeout=3.0)
            res = client.send_command("Page.navigate", {"url": "about:blank"})
            self.assertEqual(res.get("echo_method"), "Page.navigate")
            self.assertEqual(res.get("status"), "ok")
            self.assertTrue(server.last_client_masked)
            client.close()
        finally:
            server.close()

    def test_cdp_skips_broadcast_events(self):
        """Test that asynchronous CDP broadcast events are gracefully skipped to find correlated ID."""
        server = MockCDPServer(handler_mode="with_broadcast_events")
        try:
            client = CDPClient(f"ws://127.0.0.1:{server.port}/devtools/page/test-tab", timeout=3.0)
            res = client.send_command("Page.reload")
            self.assertEqual(res.get("echo_method"), "Page.reload")
            self.assertTrue(res.get("event_skipped"))
            client.close()
        finally:
            server.close()

    def test_cdp_handles_message_fragmentation(self):
        """Test reassembly of fragmented multi-frame messages."""
        server = MockCDPServer(handler_mode="fragmented")
        try:
            client = CDPClient(f"ws://127.0.0.1:{server.port}/devtools/page/test-tab", timeout=3.0)
            res = client.send_command("Page.inspect")
            self.assertTrue(res.get("fragmented"))
            client.close()
        finally:
            server.close()

    def test_cdp_auto_pong_on_ping(self):
        """Test that client responds with Pong frame preserving payload when server sends Ping."""
        server = MockCDPServer(handler_mode="ping")
        try:
            client = CDPClient(f"ws://127.0.0.1:{server.port}/devtools/page/test-tab", timeout=3.0)
            res = client.send_command("Page.ping")
            self.assertTrue(res.get("pong_verified"))
            # Brief wait for mock server thread to process Pong packet
            time.sleep(0.2)
            self.assertEqual(server.received_pong_payload, b"heartbeat-payload")
            client.close()
        finally:
            server.close()

    def test_cdp_rejects_rsv_bits(self):
        """Test that non-zero RSV bits without negotiated extension raise CDPError."""
        server = MockCDPServer(handler_mode="rsv_error")
        try:
            client = CDPClient(f"ws://127.0.0.1:{server.port}/devtools/page/test-tab", timeout=3.0)
            with self.assertRaises(CDPError) as ctx:
                client.send_command("Page.test")
            self.assertIn("RSV bits set", str(ctx.exception))
            client.close()
        finally:
            server.close()

    def test_cdp_handles_server_close(self):
        """Test handling of incoming WebSocket Close frame."""
        server = MockCDPServer(handler_mode="server_close")
        try:
            client = CDPClient(f"ws://127.0.0.1:{server.port}/devtools/page/test-tab", timeout=3.0)
            with self.assertRaises(CDPConnectionClosedError):
                client.send_command("Page.test")
            client.close()
        finally:
            server.close()

    def test_cdp_timeout(self):
        """Test timeout raised when server fails to respond within deadline."""
        server = MockCDPServer(handler_mode="timeout")
        try:
            client = CDPClient(f"ws://127.0.0.1:{server.port}/devtools/page/test-tab", timeout=0.5)
            with self.assertRaises(CDPTimeoutError):
                client.send_command("Page.test")
            client.close()
        finally:
            server.close()

    def test_cdp_connection_failure(self):
        """Test connecting to closed port raises CDPError."""
        with self.assertRaises(CDPError):
            CDPClient("ws://127.0.0.1:1/devtools/page/test-tab", timeout=0.5)


if __name__ == "__main__":
    unittest.main()
