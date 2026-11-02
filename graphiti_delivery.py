"""Opt-in Graphiti message delivery. HTTP 202 is queued, not indexed."""
import json
import uuid
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from graphiti_adapter import endpoint

def payload(event):
    return {
        "group_id": "yorimiyu-" + event["agent_id"],
        "messages": [{
            "uuid": str(uuid.uuid5(uuid.NAMESPACE_URL, "yorimiyu:memory:" + str(event["memory_id"]))),
            "name": "Yorimiyu memory " + str(event["memory_id"]),
            "role": "user",
            "role_type": "user",
            "content": event["content"],
            "timestamp": event["created_at"],
            "source_description": "Yorimiyu local memory"
        }]
    }

def deliver_one(db):
    base = endpoint()
    if not base:
        raise ValueError("Укажите YORIMIYU_GRAPHITI_URL для локального сервера Graphiti")
    row = db.execute("""SELECT o.id,o.memory_id,o.agent_id,o.content,m.created_at
        FROM graphiti_outbox o JOIN memories m ON m.id=o.memory_id
        WHERE o.state='pending' ORDER BY o.id LIMIT 1""").fetchone()
    if row is None:
        return {"state": "empty"}
    event = dict(row)
    data = json.dumps(payload(event)).encode("utf-8")
    request = Request(base + "/messages", data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"}, method="POST")
    # The reference Graphiti server returns 202 before asynchronous indexing.
    with urlopen(request, timeout=20) as response:
        if response.status != 202:
            raise RuntimeError("Graphiti did not accept the message")
        answer = json.load(response)
    if not isinstance(answer, dict) or answer.get("success") is not True:
        raise RuntimeError("Graphiti response did not confirm queue acceptance")
    db.execute("UPDATE graphiti_outbox SET state='accepted' WHERE id=? AND state='pending'", (event["id"],))
    db.commit()
    return {"state": "accepted_not_indexed", "memory_id": event["memory_id"]}
