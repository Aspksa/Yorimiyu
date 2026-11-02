"""Docker-free SQLite knowledge graph, Cloud.ru settings and safe backups."""
import json
import os
from pathlib import Path
import re
import sqlite3
from datetime import datetime, timezone
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import socket

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
CONFIG = DATA / "cloudru-settings.json"
BACKUPS = DATA / "backups"
CLOUD_BASE_URL = "https://foundation-models.api.cloud.ru/v1"

def _config():
    if not CONFIG.exists():
        return {}
    value = json.loads(CONFIG.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}

def settings_public():
    cfg = _config()
    return {"endpoint": CLOUD_BASE_URL, "model":cfg.get("model",""),
            "has_key": bool(cfg.get("api_key")), "key": "stored_locally_only"}

def save_cloud(data):
    if not isinstance(data,dict):
        raise ValueError("Invalid settings")
    old = _config()
    endpoint = CLOUD_BASE_URL
    model = data.get("model",old.get("model",""))
    key = data.get("api_key",None)
    if not isinstance(endpoint,str) or not isinstance(model,str) or len(endpoint)>300 or len(model)>150:
        raise ValueError("Invalid endpoint/model")
    if endpoint:
        p=urlsplit(endpoint)
        if p.scheme!="https" or not p.hostname or p.username or p.password or p.query or p.fragment or p.path.rstrip("/") not in ("","/v1"):
            raise ValueError("Only HTTPS OpenAI-compatible root or /v1 endpoints are allowed")
    if not re.fullmatch(r"[\w./:-]{0,150}",model):
        raise ValueError("Invalid model name")
    if key is None or key=="":
        key=old.get("api_key","")
    if not isinstance(key,str) or len(key)>2048:
        raise ValueError("Invalid API key")
    DATA.mkdir(parents=True,exist_ok=True)
    tmp=CONFIG.with_suffix(".tmp")
    tmp.write_text(json.dumps({"endpoint":endpoint,"model":model,"api_key":key},ensure_ascii=False),encoding="utf-8")
    os.replace(tmp,CONFIG)
    try: os.chmod(CONFIG,0o600)
    except OSError: pass
    return settings_public()

def cloud_connection():
    cfg=_config()
    return os.environ.get("YORIMIYU_LLM_URL") or CLOUD_BASE_URL, cfg.get("model") or os.environ.get("YORIMIYU_LLM_MODEL",""), cfg.get("api_key") or os.environ.get("YORIMIYU_LLM_API_KEY","")


def _cloud_models_url(endpoint):
    parsed=urlsplit(endpoint.rstrip("/"))
    if parsed.scheme!="https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("","/v1"):
        raise ValueError("Укажите корректный HTTPS endpoint (/v1)")
    return endpoint.rstrip("/") + ("/models" if parsed.path=="/v1" else "/v1/models")

def cloud_models():
    endpoint,model,key=cloud_connection()
    if not endpoint:
        raise ValueError("Не настроен адрес Cloud.ru")
    if not key:
        raise ValueError("Сначала сохраните API-ключ Cloud.ru")
    request=Request(_cloud_models_url(endpoint),headers={"Authorization":"Bearer "+key,"Accept":"application/json"},method="GET")
    try:
        with urlopen(request,timeout=12) as response:
            payload=json.load(response)
    except HTTPError as error:
        codes={401:"Неверный или истёкший API-ключ (401)",403:"Нет доступа к моделям (403)",404:"Endpoint не поддерживает /models (404)",429:"Лимит запросов или квота Cloud.ru (429)"}
        raise ValueError(codes.get(error.code,"Ошибка Cloud.ru HTTP "+str(error.code))) from None
    except (URLError,TimeoutError,socket.timeout):
        raise ValueError("Cloud.ru недоступен: проверьте сеть и endpoint") from None
    except (ValueError,TypeError):
        raise ValueError("Cloud.ru вернул некорректный список моделей") from None
    if not isinstance(payload,dict) or not isinstance(payload.get("data"),list):
        raise ValueError("Endpoint не вернул список моделей в формате OpenAI")
    models=sorted({item["id"] for item in payload["data"] if isinstance(item,dict) and isinstance(item.get("id"),str) and item["id"] and len(item["id"])<=150})
    return {"connected":True,"models":models[:300],"selected_model":model,"total":len(models)}

# Built-in SQLite graph. No Docker, Neo4j, Java, or third-party packages.
GRAPH_DB = DATA / "knowledge-graph.sqlite3"

def _graph_db():
    DATA.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(GRAPH_DB), timeout=10)
    db.execute("PRAGMA busy_timeout=10000")
    db.execute("""CREATE TABLE IF NOT EXISTS graph_memories (
        agent TEXT NOT NULL, id INTEGER NOT NULL, content TEXT NOT NULL,
        updated TEXT NOT NULL, PRIMARY KEY(agent,id))""")
    db.execute("""CREATE TABLE IF NOT EXISTS graph_entities (
        agent TEXT NOT NULL, name TEXT NOT NULL, PRIMARY KEY(agent,name))""")
    db.execute("""CREATE TABLE IF NOT EXISTS graph_mentions (
        agent TEXT NOT NULL, memory_id INTEGER NOT NULL, entity_name TEXT NOT NULL,
        PRIMARY KEY(agent,memory_id,entity_name))""")
    db.execute("CREATE INDEX IF NOT EXISTS graph_mentions_entity ON graph_mentions(agent,entity_name)")
    return db

def graph_status():
    try:
        with _graph_db() as db:
            db.execute("SELECT 1").fetchone()
        return {"state":"connected","backend":"sqlite_local"}
    except sqlite3.Error:
        return {"state":"offline","backend":"sqlite_local"}

def extract_entities(text):
    """Conservative offline extraction: explicit capitalized multiword names only."""
    if not isinstance(text,str): return []
    matches=re.findall(r"(?<!\\w)[A-ZА-ЯЁ][\\wА-Яа-яЁё-]+(?:\\s+[A-ZА-ЯЁ][\\wА-Яа-яЁё-]+){1,2}",text)
    return list(dict.fromkeys(matches))[:15]

def index_memory(agent_id,memory_id,content):
    if not isinstance(agent_id,str) or not 1<=len(agent_id)<=128 or not isinstance(memory_id,int) or memory_id<1 or not isinstance(content,str):
        raise ValueError("Invalid memory identifier or content")
    entities=extract_entities(content)
    with _graph_db() as db:
        db.execute("INSERT INTO graph_memories(agent,id,content,updated) VALUES(?,?,?,?) ON CONFLICT(agent,id) DO UPDATE SET content=excluded.content,updated=excluded.updated",
                   (agent_id,memory_id,content[:16000],datetime.now(timezone.utc).isoformat()))
        db.execute("DELETE FROM graph_mentions WHERE agent=? AND memory_id=?",(agent_id,memory_id))
        for name in entities:
            db.execute("INSERT OR IGNORE INTO graph_entities(agent,name) VALUES(?,?)",(agent_id,name))
            db.execute("INSERT OR IGNORE INTO graph_mentions(agent,memory_id,entity_name) VALUES(?,?,?)",(agent_id,memory_id,name))
    return {"entities":len(entities)}

def graph_view(agent_id,query="",limit=150):
    if not isinstance(agent_id,str) or not 1<=len(agent_id)<=128 or not isinstance(query,str) or len(query)>150:
        raise ValueError("Invalid graph query")
    limit=min(max(int(limit),1),300)
    with _graph_db() as db:
        rows=db.execute("""SELECT id,content FROM graph_memories WHERE agent=?
            AND (?='' OR instr(lower(content),lower(?))>0 OR EXISTS(
                SELECT 1 FROM graph_mentions WHERE agent=graph_memories.agent
                AND memory_id=graph_memories.id AND instr(lower(entity_name),lower(?))>0))
            ORDER BY id DESC LIMIT ?""",(agent_id,query,query,query,limit)).fetchall()
        nodes=[];edges=[];seen=set()
        for memory_id,content in rows:
            mid="m"+str(memory_id)
            nodes.append({"id":mid,"label":content[:80],"kind":"memory"})
            mentions=db.execute("SELECT entity_name FROM graph_mentions WHERE agent=? AND memory_id=? ORDER BY entity_name",(agent_id,memory_id)).fetchall()
            for (name,) in mentions:
                eid="e:"+name
                if eid not in seen:
                    nodes.append({"id":eid,"label":name,"kind":"entity"});seen.add(eid)
                edges.append({"source":mid,"target":eid,"weight":1})
    return {"nodes":nodes,"edges":edges,"kind":"sqlite_local","graphiti_indexed":False}

def backup(db):
    db.commit()  # Avoid an open write transaction blocking SQLite online backup.
    BACKUPS.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path=BACKUPS/("yorimiyu-"+stamp+".sqlite3")
    target=sqlite3.connect(str(path))
    try: db.backup(target)
    finally: target.close()
    return {"name":path.name,"bytes":path.stat().st_size,"scope":"sqlite_only"}

def list_backups():
    if not BACKUPS.exists():return []
    return [{"name":p.name,"bytes":p.stat().st_size} for p in sorted(BACKUPS.glob("yorimiyu-*.sqlite3"),reverse=True)[:50] if p.is_file()]

def restore_backup(db,name):
    if not isinstance(name,str) or not re.fullmatch(r"yorimiyu-\d{8}T\d{12}Z\.sqlite3",name):
        raise ValueError("Invalid backup name")
    path=BACKUPS/name
    if not path.is_file():raise ValueError("Backup not found")
    db.commit()
    check=sqlite3.connect(str(path))
    try:
        if check.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
            raise ValueError("Corrupt backup")
        check.backup(db)
    finally: check.close()
    return {"restored":True,"scope":"sqlite_only"}
