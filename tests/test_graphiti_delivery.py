import unittest
from graphiti_delivery import payload

class GraphitiDeliveryTests(unittest.TestCase):
    def test_stable_episode_uuid(self):
        event = {"memory_id": 9, "agent_id": "abc", "content": "Тест", "created_at": "2026-11-02T00:00:00+00:00"}
        first = payload(event)
        self.assertEqual(first, payload(event))
        self.assertEqual(first["group_id"], "yorimiyu-abc")
        self.assertEqual(first["messages"][0]["content"], "Тест")

if __name__ == "__main__":
    unittest.main()
