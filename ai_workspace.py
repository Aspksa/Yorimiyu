"""Unified local AI workspace: history, retrieval, graph and reviewable learning."""
import os
import re
import shutil
import sqlite3
import subprocess
from datetime import datetime, timezone
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import json
from local_services import cloud_connection, graph_status

def initialize(db):
    db.executescript("""
    CREATE TABLE IF NOT EXISTS chat_messages (
      id INTEGER PRIMARY KEY AUTOINCREMENT, agent_id TEXT NOT NULL,
      role TEXT NOT NULL CHECK(role IN ('user','assistant')),
      content TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS idx_chat_agent ON chat_messages(agent_id,id);
    CREATE TABLE IF NOT EXISTS learning_suggestions (
      id INTEGER PRIMARY KEY AUTOINCREMENT, agent_id TEXT NOT NULL,
      content TEXT NOT NULL, source_message_id INTEGER NOT NULL,
      state TEXT NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','approved','rejected')),
      UNIQUE(agent_id,source_message_id));
    """)
    db.execute("""CREATE TABLE IF NOT EXISTS letta_bindings (
        agent_id TEXT PRIMARY KEY, letta_agent_id TEXT NOT NULL)""")
    db.commit()

def bind_letta(db,agent_id,letta_id):
    valid_agent(db,agent_id)
    if not isinstance(letta_id,str) or not re.fullmatch(r"[a-zA-Z0-9_][a-zA-Z0-9_-]{0,127}",letta_id):
        raise ValueError("Некорректный ID агента Letta")
    db.execute("INSERT OR REPLACE INTO letta_bindings VALUES (?,?)",(agent_id,letta_id))
    db.commit()
    return {"bound":True}

def letta_message(db,agent_id,prompt):
    valid_agent(db,agent_id)
    row=db.execute("SELECT letta_agent_id FROM letta_bindings WHERE agent_id=?",(agent_id,)).fetchone()
    command=os.environ.get("YORIMIYU_LETTA_COMMAND","").strip()
    if not row or not command or not shutil.which(command):
        raise ValueError("Укажите исполняемый Letta и привяжите ID агента")
    if not isinstance(prompt,str) or not 1<=len(prompt.strip())<=4000:
        raise ValueError("Сообщение должно содержать 1–4000 символов")
    if os.environ.get("YORIMIYU_ENABLE_LETTA_EXEC")!="1":
        raise ValueError("Запуск Letta отключён: YORIMIYU_ENABLE_LETTA_EXEC=1")
    # Letta may execute tools: only allow explicitly opted-in users.
    proc=subprocess.run([command,"-p","--agent",row["letta_agent_id"],prompt],
        capture_output=True,text=True,timeout=120,check=False,stdin=subprocess.DEVNULL)
    if proc.returncode!=0:
        raise RuntimeError("Letta завершился с ошибкой; подробности смотрите в его собственном журнале")
    return {"answer":proc.stdout[-16000:]}

def valid_agent(db, agent_id):
    if not isinstance(agent_id,str) or not db.execute("SELECT 1 FROM agents WHERE id=?",(agent_id,)).fetchone():
        raise ValueError("Агент не найден")

def messages(db,agent_id,limit=80):
    valid_agent(db,agent_id)
    rows=db.execute("SELECT * FROM (SELECT * FROM chat_messages WHERE agent_id=? ORDER BY id DESC LIMIT ?) ORDER BY id",(agent_id,min(max(int(limit),1),200))).fetchall()
    return [dict(x) for x in rows]

def search(db,agent_id,query,limit=30):
    valid_agent(db,agent_id)
    if not isinstance(query,str) or not 1<=len(query.strip())<=200:
        raise ValueError("Запрос должен содержать 1–200 символов")
    # Escape LIKE metacharacters; query is always parameterized.
    term="%"+query.strip().replace("\\","\\\\").replace("%","\\%").replace("_","\\_")+"%"
    rows=db.execute("SELECT id,content,created_at FROM memories WHERE agent_id=? AND content LIKE ? ESCAPE '\\' ORDER BY id DESC LIMIT ?",(agent_id,term,min(max(int(limit),1),100))).fetchall()
    return [dict(x) for x in rows]

def graph(db,agent_id):
    valid_agent(db,agent_id)
    memories=db.execute("SELECT id,content FROM memories WHERE agent_id=? ORDER BY id DESC LIMIT 150",(agent_id,)).fetchall()
    nodes=[{"id":"m"+str(r["id"]),"label":r["content"][:70],"kind":"memory"} for r in memories]
    # Local graph is a lexical co-occurrence visualization, NOT Graphiti facts.
    edges=[]
    tokens={}
    for r in memories:
        tokens[r["id"]]=set(w.lower() for w in re.findall(r"[^\W\d_]{4,}",r["content"],re.UNICODE))
    for i,a in enumerate(memories):
        for b in memories[i+1:]:
            common=tokens[a["id"]] & tokens[b["id"]]
            if len(common)>=2:
                edges.append({"source":"m"+str(a["id"]),"target":"m"+str(b["id"]),"weight":len(common)})
                if len(edges)>=400:
                    break
        if len(edges)>=400:
            break
    return {"nodes":nodes,"edges":edges,"kind":"local_lexical","graphiti_indexed":False}

def runtime():
    command=os.environ.get("YORIMIYU_LETTA_COMMAND","").strip()
    return {"letta":{"state":"configured" if command and shutil.which(command) else ("missing_executable" if command else "not_configured")},
            "llm":{"state":"configured" if all(cloud_connection()[:2]) else "not_configured"}, "neo4j":graph_status()}

def llm_reply(db,agent_id,prompt):
    base,model,cloud_key=cloud_connection()
    base=base.rstrip("/")
    parsed=urlsplit(base)
    if not model or not base or parsed.scheme!="https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("","/v1"):
        raise ValueError("Настройте HTTPS YORIMIYU_LLM_URL (корень или /v1) и YORIMIYU_LLM_MODEL")
    context=search(db,agent_id,prompt[:120]) if len(prompt)<=200 else []
    history=messages(db,agent_id,20)
    system="Ты помощник Yorimiyu. Не придумывай воспоминания. Используй только достоверные данные. Контекст памяти: "+json.dumps(context,ensure_ascii=False)[:5000]
    body={"model":model,"messages":[{"role":"system","content":system}]+[{"role":x["role"],"content":x["content"]} for x in history[-18:]],"stream":False}
    headers={"Content-Type":"application/json"}
    key=cloud_key
    if key: headers["Authorization"]="Bearer "+key
    req=Request(base+("/chat/completions" if parsed.path=="/v1" else "/v1/chat/completions"),data=json.dumps(body).encode(),headers=headers,method="POST")
    with urlopen(req,timeout=60) as response:
        result=json.load(response)
    answer=result["choices"][0]["message"]["content"]
    if not isinstance(answer,str) or not answer.strip():
        raise RuntimeError("Модель вернула пустой ответ")
    return answer[:16000]

def send_chat(db,agent_id,content):
    valid_agent(db,agent_id)
    if not isinstance(content,str) or not 1<=len(content.strip())<=8000:
        raise ValueError("Сообщение должно содержать 1–8000 символов")
    if not os.environ.get("YORIMIYU_LLM_URL"):
        raise ValueError("Модель не настроена. Укажите YORIMIYU_LLM_URL и YORIMIYU_LLM_MODEL")
    db.execute("INSERT INTO chat_messages(agent_id,role,content,created_at) VALUES(?,?,?,?)",(agent_id,"user",content.strip(),datetime.now(timezone.utc).isoformat()))
    db.commit()
    # Failed model calls remain visible as unanswered user messages.
    answer=llm_reply(db,agent_id,content.strip())
    db.execute("INSERT INTO chat_messages(agent_id,role,content,created_at) VALUES(?,?,?,?)",(agent_id,"assistant",answer,datetime.now(timezone.utc).isoformat()))
    db.commit()
    return {"answer":answer}

def propose(db,agent_id):
    valid_agent(db,agent_id)
    # Explicit user-marked memory candidates; never autonomously rewrite knowledge.
    rows=db.execute("""SELECT id,content FROM chat_messages WHERE agent_id=? AND role='user'
      AND (content LIKE 'Запомни:%' OR content LIKE 'Remember:%') ORDER BY id DESC LIMIT 30""",(agent_id,)).fetchall()
    count=0
    for row in rows:
        content=row["content"].split(":",1)[1].strip()
        if content and len(content)<=16000:
            cur=db.execute("INSERT OR IGNORE INTO learning_suggestions(agent_id,content,source_message_id) VALUES(?,?,?)",(agent_id,content,row["id"]))
            count+=cur.rowcount
    db.commit()
    return {"created":count}

def suggestions(db,agent_id):
    valid_agent(db,agent_id)
    return [dict(r) for r in db.execute("SELECT * FROM learning_suggestions WHERE agent_id=? ORDER BY id DESC LIMIT 100",(agent_id,))]

def review(db,agent_id,suggestion_id,approve):
    valid_agent(db,agent_id)
    row=db.execute("SELECT * FROM learning_suggestions WHERE id=? AND agent_id=? AND state='pending'",(suggestion_id,agent_id)).fetchone()
    if not row: raise ValueError("Предложение не найдено или уже обработано")
    if approve:
        from memory_bridge import add_memory
        add_memory(db,agent_id,row["content"])
    db.execute("UPDATE learning_suggestions SET state=? WHERE id=?",("approved" if approve else "rejected",suggestion_id))
    db.commit()
    return {"state":"approved" if approve else "rejected"}
