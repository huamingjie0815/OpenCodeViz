from __future__ import annotations

import json
import socket
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlparse

from codeviz.models import ProjectStatus


DEFAULT_PORT = 39127
COMMON_PORTS = {3000, 5173, 8000, 8080}


class CodeVizRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, directory: str, project, **kwargs):
        self.project = project
        super().__init__(*args, directory=directory, **kwargs)

    def handle_one_request(self) -> None:
        try:
            super().handle_one_request()
        except (ConnectionResetError, BrokenPipeError):
            self.close_connection = True

    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/api/status":
            return self._send_json(self.project.status_payload())

        if parsed.path == "/api/graph":
            return self._send_json(self.project.graph_api_payload())

        if parsed.path == "/api/architecture":
            return self._send_json(self.project.architecture_payload())

        if parsed.path == "/api/flow/index":
            return self._send_json(self.project.flow_index_payload())

        if parsed.path == "/api/flow":
            params = parse_qs(parsed.query)
            entry = params.get("entry", [""])[0]
            return self._send_json(self.project.flow_payload(entry))

        if parsed.path == "/api/project-info":
            return self._send_json(self.project.status_payload())

        if parsed.path == "/api/versions":
            return self._send_json(self.project.versions_payload())

        if parsed.path == "/api/stream":
            params = parse_qs(parsed.query)
            after = int(params.get("after", ["0"])[0])
            return self._stream_events(after)

        if parsed.path == "/api/events":
            params = parse_qs(parsed.query)
            after = int(params.get("after", ["0"])[0])
            return self._send_json(self.project.events_payload(after))

        if parsed.path == "/api/chat/session":
            params = parse_qs(parsed.query)
            session_id = params.get("session_id", ["project-default"])[0]
            return self._send_json(self.project.chat_session_payload(session_id))

        if parsed.path.startswith("/api/chat/turn/"):
            turn_id = parsed.path.split("/")[-1]
            payload = self.project.chat_turn_payload(turn_id)
            if payload is None:
                payload = {"ok": False, "error": "turn not found"}
            return self._send_json(payload)

        if parsed.path.startswith("/api/chat/stream/"):
            turn_id = parsed.path.split("/")[-1]
            return self._stream_chat_turn(turn_id)

        return super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/api/chat":
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length) if length > 0 else b"{}"
            payload = json.loads(body.decode("utf-8") or "{}")
            question = str(payload.get("question", "")).strip()
            session_id = str(payload.get("session_id", "project-default")).strip() or "project-default"
            return self._send_json(self.project.start_chat(question, session_id=session_id))

        self.send_error(404, "Not Found")

    def log_message(self, format: str, *args) -> None:
        return

    def _send_json(self, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _stream_events(self, after_event_id: int) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.flush()
        cursor = after_event_id
        try:
            self._write_sse("status", self.project.status_payload())
            while True:
                events = self.project.events_payload(cursor)["events"]
                for event in events:
                    eid = event.get("event_id", 0)
                    cursor = max(cursor, eid)
                    self._write_sse("event", event)
                status = self.project.status_payload()
                self._write_sse("heartbeat", {
                    "after": cursor,
                    "freshness": status.get("freshness", "unknown"),
                    "summary": status.get("summary", {}),
                    "analysis_status": status.get("analysis_status", "none"),
                })
                self.wfile.flush()
                time.sleep(1.0)
        except (BrokenPipeError, ConnectionResetError):
            return

    def _write_sse(self, event_name: str, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False)
        self.wfile.write(f"event: {event_name}\n".encode("utf-8"))
        self.wfile.write(f"data: {body}\n\n".encode("utf-8"))

    def _stream_chat_turn(self, turn_id: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.flush()

        steps_sent = 0
        max_polls = 240  # 2 minutes at 0.5 s per poll
        polls = 0
        try:
            while polls < max_polls:
                polls += 1
                payload = self.project.chat_turn_payload(turn_id)
                if payload is None:
                    self._write_sse("error", {"error": "turn not found"})
                    self.wfile.flush()
                    break

                steps = payload.get("steps", [])
                for step in steps[steps_sent:]:
                    self._write_sse("step", step)
                steps_sent = len(steps)

                status = payload.get("status", "thinking")
                if status == "completed":
                    self._write_sse("done", {"answer": payload.get("answer", ""), "status": "completed"})
                    self.wfile.flush()
                    break
                elif status == "failed":
                    self._write_sse("done", {"answer": payload.get("answer", ""), "status": "failed"})
                    self.wfile.flush()
                    break

                self.wfile.flush()
                time.sleep(0.5)
            # Timed out waiting for worker to finish
            self._write_sse("error", {"error": "chat turn timed out"})
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return


class CodeVizServer:
    def __init__(self, root: Path, status: ProjectStatus, requested_port: int | None, project):
        self.root = root
        self.status = status
        self.requested_port = requested_port
        self.project = project
        self.httpd: ThreadingHTTPServer | None = None
        self._thread: Thread | None = None

    def start(self) -> dict:
        if self.httpd is not None:
            host, port = self.httpd.server_address
            return {"ok": True, "url": f"http://{host}:{port}/", "port": port}
        port = choose_port(self.requested_port)
        package_root = Path(__file__).resolve().parents[2]
        dist_web = package_root / "dist" / "web"
        web_dir = dist_web if dist_web.exists() else Path(__file__).with_name("web")
        handler = partial(CodeVizRequestHandler, directory=str(web_dir), project=self.project)

        class _QuietServer(ThreadingHTTPServer):
            def handle_error(self, request, client_address):
                import sys
                exc = sys.exc_info()[1]
                if isinstance(exc, (ConnectionResetError, BrokenPipeError)):
                    return
                super().handle_error(request, client_address)

        try:
            self.httpd = _QuietServer(("127.0.0.1", port), handler)
        except OSError as exc:
            return {"ok": False, "url": None, "port": port, "error": str(exc)}
        self._thread = Thread(target=self.httpd.serve_forever, daemon=True)
        self._thread.start()
        return {"ok": True, "url": f"http://127.0.0.1:{port}/", "port": port}

    def close(self) -> None:
        if self.httpd is None:
            return
        self.httpd.shutdown()
        self.httpd.server_close()
        self.httpd = None


def choose_port(requested_port: int | None = None) -> int:
    if requested_port is not None:
        return requested_port
    for port in range(DEFAULT_PORT, DEFAULT_PORT + 50):
        if port in COMMON_PORTS:
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if sock.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError("no free port available")
