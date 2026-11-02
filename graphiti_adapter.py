"""Explicit opt-in Graphiti HTTP bridge with SSRF-resistant loopback target."""
import json
import os
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

def endpoint():
    value = os.environ.get("YORIMIYU_GRAPHITI_URL", "").rstrip("/")
    if not value:
        return None
    parsed = urlsplit(value)
    if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost") or parsed.username or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError("Graphiti URL должен быть локальным http://127.0.0.1:PORT")
    return value

def health():
    base = endpoint()
    if base is None:
        return {"state": "not_configured"}
    try:
        request = Request(base + "/openapi.json", headers={"Accept": "application/json"})
        with urlopen(request, timeout=2) as response:
            document = json.load(response)
        return {"state": "reachable" if "paths" in document else "incompatible", "url": base}
    except Exception:
        return {"state": "unreachable", "url": base}

def queued_count(db):
    return db.execute("SELECT count(*) FROM graphiti_outbox WHERE state='pending'").fetchone()[0]

def queue_memory(db, memory_id, agent_id, content):
    db.execute("INSERT OR IGNORE INTO graphiti_outbox(memory_id,agent_id,content,state) VALUES(?,?,?,'pending')", (memory_id,agent_id,content))
    db.commit()

def list_pending(db, limit=100):
    return [dict(row) for row in db.execute("SELECT id,memory_id,agent_id,content,state FROM graphiti_outbox WHERE state='pending' ORDER BY id LIMIT ?", (min(max(int(limit),1),100),))]
