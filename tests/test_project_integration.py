from __future__ import annotations

import json
from pathlib import Path

import pytest

from codeviz.project import CodeVizProject
from codeviz.server import CodeVizServer


def fake_server_start(self):
    return {"ok": True, "url": "http://127.0.0.1:39127/", "port": 39127}


def test_analyze_writes_current_meta(fixture_project: Path, monkeypatch) -> None:
    monkeypatch.setattr(CodeVizServer, "start", fake_server_start)
    project = CodeVizProject(fixture_project)
    result = project.analyze()

    # Data now lives under versions/{run_id}/, pointer in current.json
    pointer_path = fixture_project / ".codeviz" / "current.json"
    assert pointer_path.exists()
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    meta_path = fixture_project / ".codeviz" / "versions" / pointer["run_id"] / "meta.json"
    assert meta_path.exists()
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["fingerprint"]
    assert result["ok"] is True


def test_open_reuses_fresh_graph(fixture_project: Path, monkeypatch) -> None:
    monkeypatch.setattr(CodeVizServer, "start", fake_server_start)
    project = CodeVizProject(fixture_project)
    project.analyze()

    payload = project.open(port=None, open_browser=False)
    assert payload["ok"] is True
    assert payload["reuse_state"] == "completed"


def test_open_returns_error_when_no_data(fixture_project: Path, monkeypatch) -> None:
    monkeypatch.setattr(CodeVizServer, "start", fake_server_start)
    project = CodeVizProject(fixture_project)
    payload = project.open(port=None, open_browser=False)

    assert payload["ok"] is False
    assert "No analysis data" in payload["error"]


def test_ask_auto_analyzes_and_returns_answer(fixture_project: Path) -> None:
    project = CodeVizProject(fixture_project)
    payload = project.ask("what does the service do?")

    assert payload["ok"] is True
    assert payload["source_scope"] == "agent"
    # Data now lives under versions/
    versions_dir = fixture_project / ".codeviz" / "versions"
    assert any((versions_dir / d).is_dir() for d in versions_dir.iterdir()) if versions_dir.exists() else False


def test_status_payload_exposes_freshness(fixture_project: Path) -> None:
    project = CodeVizProject(fixture_project)
    project.ensure_dirs()
    payload = project.status_payload()

    assert payload["ok"] is True
    assert payload["freshness"] in {"missing", "fresh", "stale"}


def test_graph_api_payload_returns_entities_and_edges(fixture_project: Path, monkeypatch) -> None:
    monkeypatch.setattr(CodeVizServer, "start", fake_server_start)
    project = CodeVizProject(fixture_project)
    project.analyze()

    payload = project.graph_api_payload()
    assert payload["ok"] is True
    assert "entities" in payload
    assert "edges" in payload


def test_events_payload_returns_events_list(fixture_project: Path, monkeypatch) -> None:
    monkeypatch.setattr(CodeVizServer, "start", fake_server_start)
    project = CodeVizProject(fixture_project)
    project.analyze()

    payload = project.events_payload()
    assert payload["ok"] is True
    assert isinstance(payload["events"], list)


def test_open_detects_stale_after_file_change(fixture_project: Path, monkeypatch) -> None:
    monkeypatch.setattr(CodeVizServer, "start", fake_server_start)
    project = CodeVizProject(fixture_project)
    project.analyze()

    (fixture_project / "src" / "service.ts").write_text("export function changed() { return 1; }\n", encoding="utf-8")
    payload = project.open(port=None, open_browser=False)

    # open() now serves existing data without re-analyzing, even if stale
    assert payload["ok"] is True
    assert payload["reuse_state"] == "completed"


def test_chat_session_payload_returns_turns(fixture_project: Path) -> None:
    project = CodeVizProject(fixture_project)
    project.ensure_dirs()

    payload = project.chat_session_payload()
    assert payload["ok"] is True
    assert isinstance(payload["turns"], list)
