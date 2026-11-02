"""Local-only memory and agent registry; optional external services are not implied."""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / ".runtime" / "memory.sqlite3"
MAX_TEXT = 16000

def connect(path=DB_PATH):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path), timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS memories (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      agent_id TEXT NOT NULL,
      content TEXT NOT NULL,
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS agents (
      id TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      created_at TEXT NOT NULL
    );
    """)
    db.execute("""CREATE TABLE IF NOT EXISTS graphiti_outbox (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      memory_id INTEGER NOT NULL UNIQUE,
      agent_id TEXT NOT NULL,
      content TEXT NOT NULL,
      state TEXT NOT NULL DEFAULT 'pending'
    )""")
    db.commit()
    return db

def now():
    return datetime.now(timezone.utc).isoformat()

def list_agents(db):
    return [dict(row) for row in db.execute("SELECT * FROM agents ORDER BY created_at DESC LIMIT 100")]

def create_agent(db, name):
    import uuid
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
        raise ValueError("Имя агента: от 1 до 80 символов")
    agent = {"id": uuid.uuid4().hex, "name": name.strip(), "created_at": now()}
    db.execute("INSERT INTO agents VALUES (:id,:name,:created_at)", agent)
    db.commit()
    return agent

def add_memory(db, agent_id, content):
    if not isinstance(agent_id, str) or not db.execute("SELECT 1 FROM agents WHERE id=?", (agent_id,)).fetchone():
        raise ValueError("Агент не найден")
    if not isinstance(content, str) or not 1 <= len(content.strip()) <= MAX_TEXT:
        raise ValueError("Текст памяти должен содержать от 1 до 16000 символов")
    cursor = db.execute("INSERT INTO memories(agent_id,content,created_at) VALUES(?,?,?)", (agent_id,content.strip(),now()))
    from graphiti_adapter import queue_memory
    queue_memory(db, cursor.lastrowid, agent_id, content.strip())
    return {"id": cursor.lastrowid}

def list_memories(db, agent_id):
    if not isinstance(agent_id, str):
        raise ValueError("Некорректный идентификатор")
    return [dict(row) for row in db.execute("SELECT * FROM memories WHERE agent_id=? ORDER BY id DESC LIMIT 200", (agent_id,))]

def status(db):
    return {"agents": db.execute("SELECT count(*) FROM agents").fetchone()[0],
            "memories": db.execute("SELECT count(*) FROM memories").fetchone()[0],
            "graphiti": "not_configured", "letta": "not_configured",
            "storage": "local_sqlite"}
