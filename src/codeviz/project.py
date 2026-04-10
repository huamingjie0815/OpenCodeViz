from __future__ import annotations

import threading
import webbrowser
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from codeviz.analysis import analyze_project
from codeviz.fingerprint import compute_fingerprint
from codeviz.models import AnalysisMeta, ProjectStatus
from codeviz.qa_agent import ProjectQAAgent
from codeviz.runtime_config import load_runtime_config
from codeviz.server import CodeVizServer
from codeviz.storage import (
    ensure_layout,
    get_current_version_dir,
    graph_payload,
    graph_summary,
    list_versions,
    load_events,
    load_meta,
    load_project_info,
    save_chat_turn,
    load_chat_turn,
    load_chat_session,
)


class CodeVizProject:
    def __init__(self, root: Path):
        self.root = root
        codeviz_dir = root / ".codeviz"
        versions_dir = codeviz_dir / "versions"
        self.status = ProjectStatus(
            root=root,
            codeviz_dir=codeviz_dir,
            current_dir=versions_dir / "_empty",
            chat_dir=codeviz_dir / "chat",
            versions_dir=versions_dir,
        )
        self._resolve_current_dir()
        self._analysis_thread: threading.Thread | None = None
        self._analysis_lock = threading.Lock()
        self._chat_threads: dict[str, threading.Thread] = {}
        self._chat_lock = threading.Lock()
        self.config = load_runtime_config(root)
        self._server: CodeVizServer | None = None

    def _resolve_current_dir(self) -> None:
        resolved = get_current_version_dir(self.status)
        if resolved is not None:
            self.status.current_dir = resolved

    def ensure_dirs(self) -> None:
        ensure_layout(self.status)

    # -- Freshness -------------------------------------------------------

    def _freshness(self) -> dict:
        meta = load_meta(self.status)
        if meta is None:
            return {"state": "missing", "matches": False}
        current_fp = compute_fingerprint(self.root)
        matches = current_fp == meta.fingerprint
        return {
            "state": "fresh" if matches else "stale",
            "matches": matches,
            "fingerprint": meta.fingerprint,
            "current_fingerprint": current_fp,
            "status": meta.status,
        }

    # -- Analyze ---------------------------------------------------------

    def analyze(self, port: int | None = None, open_browser: bool = False) -> dict:
        self.ensure_dirs()
        freshness = self._freshness()
        if freshness["matches"] and freshness.get("status") == "completed":
            summary = graph_summary(self.status)
            payload = {
                "ok": True,
                "reuse_state": "fresh",
                "summary": summary,
                "freshness": freshness["state"],
            }
            if port is not None or open_browser:
                payload["open"] = self._start_server(port=port, open_browser=open_browser)
            return payload

        server_payload = None
        if port is not None or open_browser:
            server_payload = self._start_server(port=port, open_browser=open_browser)

        with self._analysis_lock:
            meta = analyze_project(self.root, self.status, self.config)
        self._resolve_current_dir()

        payload = {
            "ok": True,
            "reuse_state": "analyzed",
            "summary": {
                "files": meta.file_count,
                "entities": meta.entity_count,
                "edges": meta.edge_count,
                "docs": meta.doc_count,
            },
            "freshness": "fresh",
        }
        if server_payload:
            payload["open"] = server_payload
        return payload

    def run_live_analysis(
        self,
        port: int | None = None,
        open_browser: bool = True,
    ) -> dict:
        self.ensure_dirs()
        effective_port = port if port is not None else self.config.get("port")
        server_payload = self._start_server(port=effective_port, open_browser=open_browser)
        self._start_background_analysis()
        summary = graph_summary(self.status)
        return {
            "ok": True,
            "reuse_state": "analyzing",
            "summary": summary,
            "open": server_payload,
            "analysis_started": True,
            "freshness": "analyzing",
        }

    def _start_background_analysis(self) -> None:
        if self._analysis_thread and self._analysis_thread.is_alive():
            return

        def worker():
            try:
                with self._analysis_lock:
                    analyze_project(self.root, self.status, self.config)
                self._resolve_current_dir()
            except Exception:
                pass

        self._analysis_thread = threading.Thread(target=worker, daemon=True)
        self._analysis_thread.start()

    # -- Open ------------------------------------------------------------

    def open(self, port: int | None = None, open_browser: bool = True) -> dict:
        self.ensure_dirs()
        self._resolve_current_dir()
        meta = load_meta(self.status)
        if meta is None:
            return {
                "ok": False,
                "error": "No analysis data found. Run 'codeviz analyze <project>' first.",
            }

        effective_port = port if port is not None else self.config.get("port")
        server_payload = self._start_server(port=effective_port, open_browser=open_browser)
        return {
            "ok": True,
            "reuse_state": meta.status,
            "url": server_payload.get("url", ""),
        }

    # -- Ask -------------------------------------------------------------

    def ask(self, query: str) -> dict:
        if not query.strip():
            return {"ok": False, "error": "empty query"}
        self.ensure_dirs()

        # Auto-analyze if no data yet
        freshness = self._freshness()
        if freshness["state"] == "missing":
            with self._analysis_lock:
                analyze_project(self.root, self.status, self.config)

        agent = ProjectQAAgent(self.root, self.status, self.config)
        turn_id = str(uuid4())
        created_at = datetime.now(UTC).isoformat()
        meta = load_meta(self.status)
        turn = {
            "turn_id": turn_id,
            "session_id": "project-default",
            "question": query,
            "status": "thinking",
            "created_at": created_at,
            "version_id": meta.run_id if meta else "",
        }
        save_chat_turn(self.status, turn)

        try:
            result = agent.ask(query)
            turn["answer"] = result.get("answer", "")
            turn["citations"] = result.get("citations", [])
            turn["status"] = "completed"
        except Exception as exc:
            turn["answer"] = f"Error: {exc}"
            turn["status"] = "failed"

        save_chat_turn(self.status, turn)
        return {
            "ok": True,
            "answer": turn.get("answer", ""),
            "source_scope": "agent",
            "turn_id": turn_id,
        }

    def start_chat(self, question: str, session_id: str = "project-default") -> dict:
        if not question.strip():
            return {"ok": False, "error": "empty question"}
        self.ensure_dirs()

        turn_id = str(uuid4())
        created_at = datetime.now(UTC).isoformat()
        meta = load_meta(self.status)
        turn = {
            "turn_id": turn_id,
            "session_id": session_id,
            "question": question,
            "status": "thinking",
            "created_at": created_at,
            "version_id": meta.run_id if meta else "",
        }
        save_chat_turn(self.status, turn)

        _QA_TIMEOUT = 90  # seconds

        def worker():
            try:
                freshness = self._freshness()
                if freshness["state"] == "missing":
                    with self._analysis_lock:
                        analyze_project(self.root, self.status, self.config)

                agent = ProjectQAAgent(self.root, self.status, self.config)
                with ThreadPoolExecutor(max_workers=1) as _pool:
                    _future = _pool.submit(agent.ask, question, session_id)
                    try:
                        result = _future.result(timeout=_QA_TIMEOUT)
                    except FuturesTimeoutError:
                        result = {
                            "answer": f"Request timed out after {_QA_TIMEOUT} seconds. Try asking a more specific question.",
                            "citations": [],
                        }
                turn["answer"] = result.get("answer", "")
                turn["citations"] = result.get("citations", [])
                turn["status"] = "completed"
            except Exception as exc:
                turn["answer"] = f"Error: {exc}"
                turn["status"] = "failed"
            save_chat_turn(self.status, turn)

        thread = threading.Thread(target=worker, daemon=True)
        with self._chat_lock:
            self._chat_threads[turn_id] = thread
        thread.start()

        return {"ok": True, "turn_id": turn_id, "status": "thinking"}

    # -- API payloads ----------------------------------------------------

    def status_payload(self) -> dict:
        meta = load_meta(self.status)
        project_info = load_project_info(self.status)
        freshness = self._freshness()
        summary = graph_summary(self.status)
        return {
            "ok": True,
            "freshness": freshness.get("state", "missing"),
            "summary": summary,
            "project_info": project_info.to_dict() if project_info else None,
            "analysis_status": meta.status if meta else "none",
        }

    def graph_api_payload(self) -> dict:
        payload = graph_payload(self.status)
        payload["ok"] = True
        return payload

    def events_payload(self, after: int = 0) -> dict:
        events = load_events(self.status, after)
        return {"ok": True, "events": events}

    def chat_turn_payload(self, turn_id: str) -> dict | None:
        turn = load_chat_turn(self.status, turn_id)
        if turn is None:
            return None
        return {"ok": True, **turn}

    def chat_session_payload(self, session_id: str = "project-default") -> dict:
        turns = load_chat_session(self.status, session_id)
        return {"ok": True, "session_id": session_id, "turns": turns}

    def versions_payload(self) -> dict:
        versions = list_versions(self.status)
        return {"ok": True, "versions": versions}

    # -- Server ----------------------------------------------------------

    def _start_server(self, port: int | None = None, open_browser: bool = True) -> dict:
        if self._server is None:
            self._server = CodeVizServer(self.root, self.status, port, self)
        result = self._server.start()
        if result.get("ok") and open_browser:
            webbrowser.open(result["url"])
        return result
