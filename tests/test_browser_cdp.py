"""Unit tests for pure-Python WebSocket CDP client."""

import json
import os
import socket
import sys
import threading
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from maverick.browser.cdp import CDPClient, CDPError


class MockCDPServer:
    """Mock WebSocket server to test CDPClient protocol interaction."""

    def __init__(self):
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_sock.bind(("127.0.0.1", 0))
        self.port = self.server_sock.getsockname()[1]
        self.server_sock.listen(1)
        self.running = True
        self.conn = None
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

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

            # Read client frames and respond with CDP responses
            while self.running:
                header = self.conn.recv(2)
                if not header or len(header) < 2:
                    break
                b1, b2 = header[0], header[1]
                payload_len = b2 & 0x7F
                if payload_len == 126:
                    ext = self.conn.recv(2)
                    payload_len = int.from_bytes(ext, "big")
                elif payload_len == 127:
                    ext = self.conn.recv(8)
                    payload_len = int.from_bytes(ext, "big")

                mask_key = self.conn.recv(4)
                masked_data = self.conn.recv(payload_len)
                unmasked = bytes(b ^ mask_key[i % 4] for i, b in enumerate(masked_data))
                msg = json.loads(unmasked.decode("utf-8"))

                # Reply with matching ID
                cmd_id = msg.get("id")
                method = msg.get("method")
                resp_payload = {
                    "id": cmd_id,
                    "result": {"echo_method": method, "status": "ok"}
                }
                resp_bytes = json.dumps(resp_payload).encode("utf-8")
                # Send unmasked server frame
                frame = bytearray([0x81])
                rlen = len(resp_bytes)
                if rlen < 126:
                    frame.append(rlen)
                elif rlen < 65536:
                    frame.append(126)
                    frame.extend(rlen.to_bytes(2, "big"))
                else:
                    frame.append(127)
                    frame.extend(rlen.to_bytes(8, "big"))
                frame.extend(resp_bytes)
                self.conn.sendall(frame)
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
    """Test pure-Python WebSocket client and CDP JSON-RPC protocol handling."""

    def setUp(self):
        self.server = MockCDPServer()
        self.ws_url = f"ws://127.0.0.1:{self.server.port}/devtools/page/test-tab"

    def tearDown(self):
        self.server.close()

    def test_cdp_send_and_receive(self):
        """Test sending CDP command and parsing correlated response."""
        client = CDPClient(self.ws_url, timeout=3.0)
        res = client.send_command("Page.navigate", {"url": "about:blank"})
        self.assertEqual(res.get("echo_method"), "Page.navigate")
        self.assertEqual(res.get("status"), "ok")
        client.close()

    def test_cdp_connection_failure(self):
        """Test connecting to closed port raises CDPError."""
        with self.assertRaises(CDPError):
            CDPClient("ws://127.0.0.1:1/nonexistent", timeout=0.5)


if __name__ == "__main__":
    unittest.main()
