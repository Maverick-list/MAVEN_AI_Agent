import json
import os
import unittest
import urllib.request
import urllib.error
from maverick.dashboard.server import ControlCenterServer, TelemetryHub

class TestDashboardEndpointsV2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hub = TelemetryHub()
        cls.server = ControlCenterServer(host="127.0.0.1", port=18765, hub=cls.hub)
        import threading
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = "http://127.0.0.1:18765"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def _get(self, path):
        req = urllib.request.Request(f"{self.base_url}{path}")
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            data = resp.read()
            return resp.status, resp.headers.get_content_type(), data

    def _post(self, path, payload):
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers={"Content-Type": "application/json", "Origin": "http://127.0.0.1:18765"},
        )
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            data = resp.read()
            return resp.status, resp.headers.get_content_type(), json.loads(data.decode("utf-8"))

    def test_status_endpoint(self):
        status, ctype, data = self._get("/api/status")
        self.assertEqual(status, 200)
        self.assertEqual(ctype, "application/json")
        obj = json.loads(data.decode("utf-8"))
        self.assertEqual(obj.get("status"), "success")
        self.assertIn("assistant", obj)
        self.assertIn("system", obj)

    def test_diagnostics_endpoint(self):
        status, ctype, data = self._get("/api/system/diagnostics")
        self.assertEqual(status, 200)
        obj = json.loads(data.decode("utf-8"))
        self.assertEqual(obj.get("status"), "success")
        self.assertIn("diagnostics", obj)
        diag = obj["diagnostics"]
        self.assertIn("services", diag)
        self.assertIn("top_processes", diag)

    def test_voices_endpoint(self):
        status, ctype, data = self._get("/api/voice/voices")
        self.assertEqual(status, 200)
        obj = json.loads(data.decode("utf-8"))
        self.assertEqual(obj.get("status"), "success")
        ln = obj.get("local_neural", {})
        voice_ids = [v["id"] for v in ln.get("voices", [])]
        self.assertIn("george", voice_ids)
        self.assertIn("jean", voice_ids)

    def test_emergency_stop_all(self):
        status, _, res = self._post("/api/emergency-stop", {})
        self.assertEqual(status, 200)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("action"), "emergency_stop_all_engaged")

    def test_toolkit_document(self):
        payload = {
            "type": "markdown",
            "title": "Test Doc",
            "content": "# Test\nSample content for test.",
            "output_dir": "/tmp",
        }
        status, _, res = self._post("/api/toolkit/document", payload)
        self.assertEqual(status, 200)
        self.assertEqual(res.get("status"), "success")
        self.assertTrue(os.path.isfile(res.get("path")))
        if os.path.exists(res.get("path")):
            os.remove(res.get("path"))

    def test_toolkit_code_symbols(self):
        payload = {"action": "find_symbols", "path": "/home/firza-ilmi/Maverick-DevOS-evolution/maverick/system"}
        status, _, res = self._post("/api/toolkit/code", payload)
        self.assertEqual(status, 200)
        self.assertEqual(res.get("status"), "success")
        self.assertIn("symbols", res)

    def test_operating_mode_switch(self):
        status, _, res = self._post("/api/system/mode", {"mode": "low_memory"})
        self.assertEqual(status, 200)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("current_mode"), "low_memory")

        status, _, res = self._post("/api/system/mode", {"mode": "normal"})
        self.assertEqual(status, 200)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("current_mode"), "normal")

    def test_memory_profile_and_cleanup(self):
        status, ctype, data = self._get("/api/system/memory-profile")
        self.assertEqual(status, 200)
        obj = json.loads(data.decode("utf-8"))
        self.assertEqual(obj.get("status"), "success")
        self.assertIn("subsystems", obj)

        status, _, res = self._post("/api/system/memory-cleanup", {})
        self.assertEqual(status, 200)
        self.assertEqual(res.get("status"), "success")
        self.assertIn("pressure", res)

if __name__ == "__main__":
    unittest.main()
