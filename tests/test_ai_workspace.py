import tempfile
import unittest
from pathlib import Path
from memory_bridge import connect,create_agent,add_memory
from ai_workspace import initialize,messages,search,graph,propose,suggestions,review,bind_letta

class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=connect(Path(self.tmp.name)/"memory.sqlite")
        initialize(self.db)
        self.agent=create_agent(self.db,"Агент")["id"]
        self.other=create_agent(self.db,"Другой")["id"]
    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()
    def test_search_and_isolation(self):
        add_memory(self.db,self.agent,"Золотая лисица читает книгу")
        add_memory(self.db,self.agent,"Золотая лисица читает сказку")
        add_memory(self.db,self.other,"Золотая лисица читает книгу")
        self.assertEqual(len(search(self.db,self.agent,"Золотая")),2)
        g=graph(self.db,self.agent)
        self.assertEqual(len(g["nodes"]),2)
        self.assertEqual(len(g["edges"]),1)
        self.assertFalse(g["graphiti_indexed"])
    def test_review_requires_approval(self):
        self.db.execute("INSERT INTO chat_messages(agent_id,role,content,created_at) VALUES(?,?,?,?)",(self.agent,"user","Запомни: люблю книги","2026-01-01"))
        self.db.commit()
        self.assertEqual(propose(self.db,self.agent)["created"],1)
        self.assertEqual(propose(self.db,self.agent)["created"],0)
        s=suggestions(self.db,self.agent)[0]
        self.assertEqual(len(search(self.db,self.agent,"книги")),0)
        self.assertEqual(review(self.db,self.agent,s["id"],True)["state"],"approved")
        self.assertEqual(len(search(self.db,self.agent,"книги")),1)
        with self.assertRaises(ValueError): review(self.db,self.agent,s["id"],True)
    def test_letta_binding_validation(self):
        with self.assertRaises(ValueError): bind_letta(self.db,self.agent,"--unsafe")
        self.assertTrue(bind_letta(self.db,self.agent,"agent_123")["bound"])
    def test_messages_are_per_agent(self):
        self.db.execute("INSERT INTO chat_messages(agent_id,role,content,created_at) VALUES(?,?,?,?)",(self.agent,"user","hello","2026-01-01"))
        self.db.commit()
        self.assertEqual(len(messages(self.db,self.agent)),1)
        self.assertEqual(messages(self.db,self.other),[])

if __name__=="__main__":
    unittest.main()
