"""Local-only Neo4j graph, Cloud.ru settings and safe SQLite backups."""
import base64
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
CONFIG = DATA / "cloudru-settings.json"
BACKUPS = DATA / "backups"

def _config():
    if not CONFIG.exists():
        return {}
    value = json.loads(CONFIG.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}

def settings_public():
    cfg = _config()
    return {"endpoint": cfg.get("endpoint",""), "model":cfg.get("model",""),
            "has_key": bool(cfg.get("api_key")), "key": "stored_locally_only"}

def save_cloud(data):
    if not isinstance(data,dict):
        raise ValueError("Invalid settings")
    old = _config()
    endpoint = data.get("endpoint",old.get("endpoint",""))
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
    return cfg.get("endpoint") or os.environ.get("YORIMIYU_LLM_URL",""), cfg.get("model") or os.environ.get("YORIMIYU_LLM_MODEL",""), cfg.get("api_key") or os.environ.get("YORIMIYU_LLM_API_KEY","")

def neo4j_config():
    url=os.environ.get("YORIMIYU_NEO4J_URL","http://127.0.0.1:7474").rstrip("/")
    p=urlsplit(url)
    if p.scheme!="http" or p.hostname not in ("127.0.0.1","localhost") or p.port!=7474 or p.username or p.password or p.query or p.fragment or p.path:
        raise ValueError("Neo4j HTTP must be on local port 7474")
    return url,os.environ.get("YORIMIYU_NEO4J_USER","neo4j"),os.environ.get("YORIMIYU_NEO4J_PASSWORD","")

def cypher(statement,parameters=None):
    url,user,password=neo4j_config()
    if not password:
        raise ValueError("Set YORIMIYU_NEO4J_PASSWORD locally; no default password")
    token=base64.b64encode((user+":"+password).encode()).decode()
    body=json.dumps({"statements":[{"statement":statement,"parameters":parameters or {}}]}).encode()
    req=Request(url+"/db/neo4j/tx/commit",data=body,headers={"Authorization":"Basic "+token,"Content-Type":"application/json"},method="POST")
    with urlopen(req,timeout=8) as response:
        payload=json.load(response)
    if payload.get("errors"):
        raise ValueError("Neo4j query failed: "+str(payload["errors"][0].get("code","unknown")))
    return payload.get("results",[{}])[0].get("data",[])

def graph_status():
    try:
        cypher("RETURN 1 AS ready")
        return {"state":"connected","backend":"neo4j_local"}
    except Exception:
        return {"state":"offline","backend":"neo4j_local"}

def extract_entities(text):
    """Conservative offline extraction: explicit capitalized multiword names only."""
    if not isinstance(text,str): return []
    matches=re.findall(r"(?<!\w)[A-ZА-ЯЁ][\wА-Яа-яЁё-]+(?:\s+[A-ZА-ЯЁ][\wА-Яа-яЁё-]+){1,2}",text)
    return list(dict.fromkeys(matches))[:15]

def index_memory(agent_id,memory_id,content):
    if not isinstance(agent_id,str) or not isinstance(memory_id,int):
        raise ValueError("Invalid memory identifier")
    entities=extract_entities(content)
    cypher("MERGE (m:YorimiyuMemory {agent:$agent,id:$id}) SET m.text=$text,m.updated=$updated",
           {"agent":agent_id,"id":memory_id,"text":content[:16000],"updated":datetime.now(timezone.utc).isoformat()})
    for name in entities:
        cypher("MERGE (e:YorimiyuEntity {agent:$agent,name:$name}) WITH e MATCH (m:YorimiyuMemory {agent:$agent,id:$id}) MERGE (m)-[:MENTIONS]->(e)",
               {"agent":agent_id,"id":memory_id,"name":name})
    return {"entities":len(entities)}

def graph_view(agent_id,query="",limit=150):
    if not isinstance(agent_id,str) or len(agent_id)>128 or not isinstance(query,str) or len(query)>150:
        raise ValueError("Invalid graph query")
    limit=min(max(int(limit),1),300)
    rows=cypher("MATCH (m:YorimiyuMemory {agent:$agent}) OPTIONAL MATCH (m)-[:MENTIONS]->(e:YorimiyuEntity) WHERE $q='' OR toLower(m.text) CONTAINS toLower($q) OR toLower(e.name) CONTAINS toLower($q) RETURN m.id,m.text,collect(DISTINCT e.name) LIMIT $limit",
                {"agent":agent_id,"q":query,"limit":limit})
    nodes=[];edges=[];seen=set()
    for row in rows:
        values=row.get("row",[])
        if len(values)<3: continue
        mid="m"+str(values[0]);nodes.append({"id":mid,"label":str(values[1])[:80],"kind":"memory"})
        for name in values[2] or []:
            if not name:continue
            eid="e:"+name
            if eid not in seen:
                nodes.append({"id":eid,"label":name,"kind":"entity"});seen.add(eid)
            edges.append({"source":mid,"target":eid,"weight":1})
    return {"nodes":nodes,"edges":edges,"kind":"neo4j_local","graphiti_indexed":False}

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
