import tempfile
import unittest
from pathlib import Path
from memory_bridge import connect, create_agent, add_memory, list_memories, list_agents, status

class MemoryBridgeTests(unittest.TestCase):
    def test_agent_memory_isolation_and_persistence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.db"
            db = connect(path)
            first = create_agent(db, "Первый")
            second = create_agent(db, "Второй")
            add_memory(db, first["id"], "Привет")
            self.assertEqual(len(list_memories(db, second["id"])), 0)
            self.assertEqual(status(db)["memories"], 1)
            db.close()
            db = connect(path)
            self.assertEqual(list_memories(db, first["id"])[0]["content"], "Привет")
            self.assertEqual(len(list_agents(db)), 2)
            db.close()

    def test_invalid_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            db = connect(Path(directory) / "test.db")
            with self.assertRaises(ValueError):
                create_agent(db, "")
            with self.assertRaises(ValueError):
                add_memory(db, "missing", "text")
            db.close()

if __name__ == "__main__":
    unittest.main()
