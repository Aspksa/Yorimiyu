import json
import threading
import unittest
from urllib.request import urlopen
from launcher import Handler, ThreadingHTTPServer, existing_url, STATE, TOKEN

class LauncherTests(unittest.TestCase):
    def test_stale_state_is_ignored(self):
        old = STATE.read_bytes() if STATE.exists() else None
        try:
            STATE.parent.mkdir(parents=True, exist_ok=True)
            STATE.write_text(json.dumps({"port": 1, "instanceId": TOKEN}), encoding="utf-8")
            self.assertIsNone(existing_url())
        finally:
            if old is None:
                STATE.unlink(missing_ok=True)
            else:
                STATE.write_bytes(old)

    def test_health_and_home(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            with urlopen(base + "/health", timeout=3) as response:
                self.assertEqual(json.load(response)["service"], "yorimiyu-static-ui")
            with urlopen(base + "/", timeout=3) as response:
                self.assertIn(b"Yorimiyu", response.read())
        finally:
            server.shutdown()
            server.server_close()

if __name__ == "__main__":
    unittest.main()
