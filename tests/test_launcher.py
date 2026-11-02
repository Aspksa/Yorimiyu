import json
import threading
import unittest
from urllib.request import urlopen
from launcher import Handler, ThreadingHTTPServer

class LauncherTests(unittest.TestCase):
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
