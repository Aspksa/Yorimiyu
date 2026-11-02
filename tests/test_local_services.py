import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
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
            with self.assertRaises(ValueError):
                s.save_cloud({"endpoint":"http://evil.test/v1","model":"model-1"})
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
    def test_neo4j_never_remote(self):
        with patch.dict(os.environ,{"YORIMIYU_NEO4J_URL":"http://example.org:7474"}):
            with self.assertRaises(ValueError):s.neo4j_config()

if __name__=="__main__": unittest.main()
