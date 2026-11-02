import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from io import BytesIO
from urllib.error import HTTPError
import local_services as s

class LocalServicesTests(unittest.TestCase):
    def test_entity_extraction(self):
        self.assertIn("Новая Москва",s.extract_entities("Мы обсуждали Новая Москва и Новая Москва"))
        self.assertEqual(len(s.extract_entities("Новая Москва; Новая Москва")),1)
    def test_cloud_secret_not_exposed(self):
        with tempfile.TemporaryDirectory() as d, patch.object(s,"DATA",Path(d)),patch.object(s,"CONFIG",Path(d)/"settings.json"):
            s.save_cloud({"endpoint":"https://example.org/v1","model":"model-1","api_key":"very-secret"})
            self.assertTrue(s.settings_public()["has_key"])
            self.assertNotIn("very-secret",str(s.settings_public()))
            self.assertEqual(s.settings_public()["endpoint"],s.CLOUD_BASE_URL)
            s.save_cloud({"endpoint":"http://evil.test/v1","model":"model-1"})
            self.assertEqual(s.settings_public()["endpoint"],s.CLOUD_BASE_URL)
    def test_cloud_models_connection_and_secret_handling(self):
        with tempfile.TemporaryDirectory() as d, patch.object(s,"DATA",Path(d)), patch.object(s,"CONFIG",Path(d)/"settings.json"):
            s.save_cloud({"endpoint":"https://example.org/v1","model":"model-a","api_key":"private-token"})
            class Response:
                def __enter__(self): return BytesIO(b'{"data":[{"id":"model-b"},{"id":"model-a"}]}')
                def __exit__(self,*args): return False
            def fake_open(request,timeout):
                self.assertEqual(request.full_url,s.CLOUD_BASE_URL+"/models")
                self.assertEqual(request.get_header("Authorization"),"Bearer private-token")
                self.assertLessEqual(timeout,15)
                return Response()
            with patch.object(s,"urlopen",side_effect=fake_open):
                result=s.cloud_models()
            self.assertEqual(result["models"],["model-a","model-b"])
            self.assertNotIn("private-token",str(result))
            with patch.object(s,"urlopen",side_effect=HTTPError("https://example.org/v1/models",429,"limit",{},None)):
                with self.assertRaisesRegex(ValueError,"429"):s.cloud_models()
    def test_sqlite_backup(self):
        with tempfile.TemporaryDirectory() as d,patch.object(s,"BACKUPS",Path(d)):
            db=sqlite3.connect(":memory:")
            db.execute("CREATE TABLE t (v TEXT)")
            db.execute("INSERT INTO t VALUES ('hello')")
            result=s.backup(db)
            self.assertTrue((Path(d)/result["name"]).exists())
            db.execute("DELETE FROM t")
            s.restore_backup(db,result["name"])
            self.assertEqual(db.execute("SELECT v FROM t").fetchone()[0],"hello")
            with self.assertRaises(ValueError):s.restore_backup(db,"../bad")
            db.close()
    def test_sqlite_graph_is_local_and_agent_isolated(self):
        with tempfile.TemporaryDirectory() as d,patch.object(s,"DATA",Path(d)),patch.object(s,"GRAPH_DB",Path(d)/"graph.sqlite3"):
            self.assertEqual(s.graph_status()["backend"],"sqlite_local")
            self.assertEqual(s.index_memory("agent-1",1,"Новая Москва — Новая Москва")["entities"],1)
            graph=s.graph_view("agent-1")
            self.assertEqual(graph["kind"],"sqlite_local")
            self.assertTrue(any(n["kind"]=="entity" for n in graph["nodes"]))
            self.assertTrue(any(e["source"]=="m1" for e in graph["edges"]))
            self.assertEqual(s.graph_view("agent-2")["nodes"],[])
            s.index_memory("agent-1",1,"Текст без сущностей")
            self.assertEqual(s.graph_view("agent-1")["edges"],[])
            with self.assertRaises(ValueError): s.graph_view("agent-1",query="x"*151)

if __name__=="__main__": unittest.main()
