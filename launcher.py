"""Local dashboard with safe single-instance reuse and diagnostic logs."""
import argparse
import json
import logging
from logging.handlers import RotatingFileHandler
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import secrets
import threading
import webbrowser
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
STATE = ROOT / ".runtime" / "dashboard.json"
LOG = ROOT / "logs" / "launch.log"
TOKEN = secrets.token_urlsafe(24)

def setup_logging():
    LOG.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(LOG, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, handlers=[handler, logging.StreamHandler()], format="%(asctime)s %(levelname)s %(message)s")

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB), **kwargs)

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

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    setup_logging()
    if not (WEB / "index.html").is_file():
        raise SystemExit("Missing web/index.html")
    url = existing_url()
    if url:
        logging.info("Reusing dashboard at %s", url)
        if not args.no_browser:
            webbrowser.open(url)
        return
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    url = f"http://127.0.0.1:{server.server_port}/"
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"port": server.server_port, "instanceId": TOKEN}), encoding="utf-8")
    logging.info("Yorimiyu dashboard: %s", url)
    logging.info("Static UI only; Graphiti services are not running.")
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
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
