"""Local dashboard with safe single-instance reuse and diagnostic logs."""
import argparse
import json
from urllib.parse import urlsplit, parse_qs
from memory_bridge import connect, list_agents, create_agent, add_memory, list_memories, status
from graphiti_adapter import health as graphiti_health, list_pending
from graphiti_delivery import deliver_one
from ai_workspace import initialize, messages, search, graph, runtime, send_chat, propose, suggestions, review, bind_letta, letta_message
import logging
from logging.handlers import RotatingFileHandler
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import secrets
import threading
import time
import os
import webbrowser
from local_services import settings_public, save_cloud, graph_status, graph_view, index_memory, backup, list_backups, restore_backup
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
STATE = ROOT / ".runtime" / "dashboard.json"
LOG = ROOT / "logs" / "launch.log"
LOCK = ROOT / ".runtime" / "dashboard.lock"
TOKEN = secrets.token_urlsafe(24)

def setup_logging():
    LOG.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(LOG, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, handlers=[handler, logging.StreamHandler()], format="%(asctime)s %(levelname)s %(message)s")

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB), **kwargs)

    def _json(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _allowed(self):
        port = self.server.server_port
        return self.headers.get("Host") == "127.0.0.1:" + str(port) and self.headers.get("Origin", "http://127.0.0.1:" + str(port)) == "http://127.0.0.1:" + str(port)

    def do_POST(self):
        if not self.path.startswith("/api/"):
            self._json(404, {"error": "Не найдено"})
            return
        if not self._allowed():
            self._json(403, {"error": "Только локальный доступ"})
            return
        if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
            self._json(415, {"error": "Ожидается JSON"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 20000:
                raise ValueError("Некорректный размер запроса")
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError("Ожидается объект JSON")
            with connect() as db:
                initialize(db)
                if self.path == "/api/chat":
                    result = send_chat(db, data.get("agent_id"), data.get("content"))
                elif self.path == "/api/letta/bind":
                    result = bind_letta(db, data.get("agent_id"), data.get("letta_agent_id"))
                elif self.path == "/api/letta/chat":
                    if data.get("confirm") is not True:
                        raise ValueError("Подтвердите выполнение Letta")
                    result = letta_message(db, data.get("agent_id"), data.get("content"))
                elif self.path == "/api/learning/propose":
                    result = propose(db, data.get("agent_id"))
                elif self.path == "/api/learning/review":
                    result = review(db, data.get("agent_id"), data.get("id"), data.get("approve") is True)
                elif self.path == "/api/graphiti/deliver":
                    if data.get("confirm") is not True:
                        raise ValueError("Для передачи данных требуется явное подтверждение")
                    result = {"delivery": deliver_one(db)}
                elif self.path == "/api/agents":
                    result = {"agent": create_agent(db, data.get("name"))}
                elif self.path == "/api/memories":
                    result = {"memory": add_memory(db, data.get("agent_id"), data.get("content"))}
                    try:
                        result["graph_index"] = index_memory(data.get("agent_id"), result["memory"]["id"], data.get("content"))
                    except Exception:
                        logging.warning("Neo4j unavailable; memory preserved in SQLite")
                        result["graph_index"] = {"state":"pending"}
                elif self.path == "/api/cloud/settings":
                    result = save_cloud(data)
                elif self.path in ("/api/neo4j/index","/api/sqlite-graph/index"):
                    agent = data.get("agent_id")
                    if not isinstance(agent,str) or not db.execute("SELECT 1 FROM agents WHERE id=?",(agent,)).fetchone():
                        raise ValueError("Agent not found")
                    rows = db.execute("SELECT id,content FROM memories WHERE agent_id=? ORDER BY id LIMIT 500",(agent,)).fetchall()
                    indexed = 0
                    for row in rows:
                        index_memory(agent,row["id"],row["content"])
                        indexed += 1
                    result = {"indexed":indexed}
                elif self.path == "/api/backup":
                    result = backup(db)
                elif self.path == "/api/backup/restore":
                    if data.get("confirm") is not True:
                        raise ValueError("Explicit restore confirmation required")
                    backup(db)
                    result = restore_backup(db,data.get("name"))
                else:
                    self._json(404, {"error": "Не найдено"})
                    return
            self._json(201, result)
        except (ValueError, TypeError) as exc:
            self._json(400, {"error": str(exc)})
        except Exception:
            logging.exception("API write failure")
            self._json(500, {"error": "Внутренняя ошибка"})

    def do_GET(self):
        if self.path.split("?", 1)[0] == "/health":
            data = json.dumps({"status": "ok", "service": "yorimiyu-static-ui", "instanceId": TOKEN}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        path = urlsplit(self.path)
        if path.path.startswith("/api/"):
            if not self._allowed():
                self._json(403, {"error": "Только локальный доступ"})
                return
            try:
                with connect() as db:
                    initialize(db)
                    agent_id = parse_qs(path.query).get("agent_id", [""])[0]
                    if path.path == "/api/chat":
                        result = {"messages": messages(db, agent_id)}
                    elif path.path == "/api/search":
                        result = {"matches": search(db, agent_id, parse_qs(path.query).get("q", [""])[0])}
                    elif path.path == "/api/graph":
                        result = graph(db, agent_id)
                    elif path.path in ("/api/neo4j/graph","/api/sqlite-graph/graph"):
                        if not db.execute("SELECT 1 FROM agents WHERE id=?",(agent_id,)).fetchone():
                            raise ValueError("Agent not found")
                        result = graph_view(agent_id,parse_qs(path.query).get("q",[""])[0])
                    elif path.path in ("/api/neo4j/status","/api/sqlite-graph/status"):
                        result = graph_status()
                    elif path.path == "/api/cloud/settings":
                        result = settings_public()
                    elif path.path == "/api/backups":
                        result = {"backups":list_backups()}
                    elif path.path == "/api/runtime":
                        result = runtime()
                    elif path.path == "/api/learning":
                        result = {"suggestions": suggestions(db, agent_id)}
                    elif path.path == "/api/graphiti/status":
                        result = graphiti_health()
                        result["queued"] = db.execute("SELECT count(*) FROM graphiti_outbox WHERE state='pending'").fetchone()[0]
                    elif path.path == "/api/graphiti/outbox":
                        result = {"events": list_pending(db)}
                    elif path.path == "/api/status":
                        result = status(db)
                    elif path.path == "/api/agents":
                        result = {"agents": list_agents(db)}
                    elif path.path == "/api/memories":
                        result = {"memories": list_memories(db, parse_qs(path.query).get("agent_id", [""])[0])}
                    else:
                        self._json(404, {"error": "Не найдено"})
                        return
                self._json(200, result)
            except (ValueError, TypeError) as exc:
                self._json(400, {"error": str(exc)})
            except Exception:
                logging.exception("API read failure")
                self._json(500, {"error": "Внутренняя ошибка"})
            return
        super().do_GET()

    def log_message(self, fmt, *args):
        logging.info("%s %s", self.address_string(), fmt % args)

def existing_url():
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
        port = state["port"]
        if not isinstance(port, int) or not 1 <= port <= 65535:
            return None
        with urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as response:
            health = json.load(response)
        if health.get("service") == "yorimiyu-static-ui" and secrets.compare_digest(health.get("instanceId", ""), state["instanceId"]):
            return f"http://127.0.0.1:{port}/"
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None

def acquire_instance_lock(timeout=20):
    """Hold an OS file lock for the entire server lifetime; crash releases it."""
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    handle = open(LOCK, "a+b")
    handle.seek(0, os.SEEK_END)
    if handle.tell() == 0:
        handle.write(b"0")
        handle.flush()
    deadline = time.monotonic() + timeout
    while True:
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return handle
        except (OSError, BlockingIOError):
            if existing_url() is not None:
                handle.close()
                return None
            if time.monotonic() >= deadline:
                handle.close()
                return None
            time.sleep(0.2)

def release_instance_lock(handle):
    if handle is None:
        return
    try:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    setup_logging()
    if not (WEB / "index.html").is_file():
        raise SystemExit("Missing web/index.html")
    lock = acquire_instance_lock()
    if lock is None:
        url = existing_url()
        if url:
            print(f"[Yorimiyu] Already running: {url}", flush=True)
            if not args.no_browser:
                webbrowser.open(url)
            return
        raise SystemExit("Another startup is in progress. Try again in 20 seconds.")
    try:
        run_dashboard(args)
    finally:
        release_instance_lock(lock)

def run_dashboard(args):
    url = existing_url()
    if url:
        logging.info("Reusing dashboard at %s", url)
        print(f"[Yorimiyu] Already running: {url}", flush=True)
        if not args.no_browser and not webbrowser.open(url):
            logging.warning("Browser did not open automatically; open %s manually", url)
        return
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    url = f"http://127.0.0.1:{server.server_port}/"
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"port": server.server_port, "instanceId": TOKEN}), encoding="utf-8")
    logging.info("Yorimiyu dashboard: %s", url)
    print(f"[Yorimiyu] Open in browser: {url}", flush=True)
    logging.info("Local SQLite memory API enabled; Graphiti and Letta runtimes are not running.")
    if not args.no_browser:
        def open_dashboard():
            try:
                if not webbrowser.open(url):
                    logging.warning("Browser did not open automatically; open %s manually", url)
            except Exception:
                logging.exception("Failed to open browser; dashboard remains available at %s", url)
        threading.Timer(0.5, open_dashboard).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logging.info("Dashboard stopped")
    finally:
        server.server_close()
        try:
            state = json.loads(STATE.read_text(encoding="utf-8"))
            if state.get("instanceId") == TOKEN:
                STATE.unlink(missing_ok=True)
        except (OSError, ValueError):
            pass

if __name__ == "__main__":
    main()
