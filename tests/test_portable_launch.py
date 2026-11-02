"""End-to-end local launcher checks for paths with Unicode and shell metacharacters."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
FILES = ["launcher.py", "memory_bridge.py", "ai_workspace.py", "graphiti_adapter.py", "graphiti_delivery.py"]

class PortableLaunchTests(unittest.TestCase):
    def test_unicode_parentheses_and_duplicate_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "Проект (тест) & ! 100%"
            folder.mkdir()
            for name in FILES:
                shutil.copy2(ROOT / name, folder / name)
            shutil.copytree(ROOT / "web", folder / "web")
            kwargs = {"cwd": str(folder), "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
            first = subprocess.Popen([sys.executable, "launcher.py", "--no-browser"], **kwargs)
            try:
                url = None
                for _ in range(80):
                    if first.poll() is not None:
                        self.fail(f"First launcher exited: {first.returncode}")
                    state = folder / ".runtime" / "dashboard.json"
                    if state.exists():
                        try:
                            port = json.loads(state.read_text(encoding="utf-8"))["port"]
                            candidate = f"http://127.0.0.1:{port}/health"
                            with urlopen(candidate, timeout=0.5) as response:
                                if json.load(response).get("status") == "ok":
                                    url = candidate
                                    break
                        except (OSError, ValueError, KeyError):
                            pass
                    time.sleep(0.1)
                self.assertIsNotNone(url, "First launcher never became healthy")
                second = subprocess.run([sys.executable, "launcher.py", "--no-browser"], cwd=folder,
                                        capture_output=True, text=True, timeout=8)
                self.assertEqual(second.returncode, 0, second.stderr)
                self.assertIn("Already running", second.stdout)
                with urlopen(url, timeout=2) as response:
                    self.assertEqual(json.load(response)["status"], "ok")
            finally:
                first.terminate()
                try:
                    first.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    first.kill()
                    first.wait(timeout=5)

if __name__ == "__main__":
    unittest.main()
