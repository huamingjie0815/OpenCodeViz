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


def test_architecture_payload_returns_modules_and_dependencies(fixture_project: Path, monkeypatch) -> None:
    monkeypatch.setattr(CodeVizServer, "start", fake_server_start)
    project = CodeVizProject(fixture_project)
    project.analyze()

    payload = project.architecture_payload()

    assert payload["ok"] is True
    assert "modules" in payload
    assert "dependencies" in payload
    assert len(payload["modules"]) >= 1


def test_flow_index_payload_returns_entry_candidates(fixture_project: Path, monkeypatch) -> None:
    monkeypatch.setattr(CodeVizServer, "start", fake_server_start)
    project = CodeVizProject(fixture_project)
    project.analyze()

    payload = project.flow_index_payload()

    assert payload["ok"] is True
    assert "entries" in payload
    assert "entity" in payload["entries"]


def test_flow_payload_returns_candidates_for_unknown_entry(fixture_project: Path, monkeypatch) -> None:
    monkeypatch.setattr(CodeVizServer, "start", fake_server_start)
    project = CodeVizProject(fixture_project)
    project.analyze()

    payload = project.flow_payload("missing-entry")

    assert payload["ok"] is False
    assert payload["error"] == "entry_not_found"
    assert isinstance(payload["candidates"], list)


def test_architecture_payload_rebuilds_missing_assets(fixture_project: Path, monkeypatch) -> None:
    monkeypatch.setattr(CodeVizServer, "start", fake_server_start)
    project = CodeVizProject(fixture_project)
    project.analyze()

    architecture_path = project.status.current_dir / "architecture.json"
    flow_index_path = project.status.current_dir / "flow_index.json"
    architecture_path.unlink()
    flow_index_path.unlink()

    architecture_payload = project.architecture_payload()
    flow_index_payload = project.flow_index_payload()

    assert architecture_payload["ok"] is True
    assert len(architecture_payload["modules"]) >= 1
    assert flow_index_payload["ok"] is True
    assert "entity" in flow_index_payload["entries"]


def test_architecture_payload_rebuilds_legacy_assets(fixture_project: Path, monkeypatch) -> None:
    monkeypatch.setattr(CodeVizServer, "start", fake_server_start)
    project = CodeVizProject(fixture_project)
    project.analyze()

    architecture_path = project.status.current_dir / "architecture.json"
    architecture = json.loads(architecture_path.read_text(encoding="utf-8"))
    architecture["meta"].pop("schema_version", None)
    architecture["modules"].append({
        "module_id": "tests",
        "display_name": "tests",
        "source_dirs": ["tests"],
        "file_paths": ["tests/test_project.py"],
        "entity_ids": [],
        "merge_reason": "directory",
        "confidence": "high",
    })
    architecture_path.write_text(json.dumps(architecture, ensure_ascii=False), encoding="utf-8")

    payload = project.architecture_payload()

    assert payload["ok"] is True
    assert all(module["display_name"] != "tests" for module in payload["modules"])


def test_open_prefers_latest_completed_snapshot_when_current_is_incomplete(fixture_project: Path, monkeypatch) -> None:
    monkeypatch.setattr(CodeVizServer, "start", fake_server_start)
    project = CodeVizProject(fixture_project)
    project.analyze()

    completed_dir = project.status.current_dir
    incomplete_dir = project.status.versions_dir / "20990101T000000Z"
    incomplete_dir.mkdir(parents=True, exist_ok=True)
    (project.status.codeviz_dir / "current.json").write_text(json.dumps({"run_id": "20990101T000000Z"}), encoding="utf-8")
    (incomplete_dir / "meta.json").write_text(
        json.dumps(
            {
                "run_id": "20990101T000000Z",
                "fingerprint": "x",
                "status": "analyzing",
                "file_count": 0,
                "entity_count": 0,
                "edge_count": 0,
                "doc_count": 0,
                "started_at": "",
                "finished_at": "",
                "error": "",
            }
        ),
        encoding="utf-8",
    )

    reopened = CodeVizProject(fixture_project)

    assert reopened.status.current_dir == completed_dir
