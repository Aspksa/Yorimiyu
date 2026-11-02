import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from memory_bridge import connect, create_agent, add_memory
from graphiti_adapter import endpoint, list_pending

class GraphitiAdapterTests(unittest.TestCase):
    def test_endpoint_rejects_remote(self):
        for url in ("https://example.com", "http://127.0.0.1.evil.com:8000", "file:///etc/passwd", "http://user:pass@localhost:8000"):
            with patch.dict(os.environ, {"YORIMIYU_GRAPHITI_URL":url}):
                with self.assertRaises(ValueError):
                    endpoint()

    def test_outbox_idempotence(self):
        with tempfile.TemporaryDirectory() as folder:
            with connect(Path(folder)/"test.sqlite") as db:
                agent = create_agent(db, "Тест")
                add_memory(db, agent["id"], "Проверка")
                self.assertEqual(len(list_pending(db)), 1)
                db.execute("INSERT OR IGNORE INTO graphiti_outbox(memory_id,agent_id,content,state) VALUES(1,?,?,'pending')", (agent["id"],"Проверка"))
                self.assertEqual(len(list_pending(db)), 1)

if __name__ == "__main__":
    unittest.main()
