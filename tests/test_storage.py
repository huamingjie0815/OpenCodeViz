from __future__ import annotations

import json
from pathlib import Path

from codeviz.models import (
    AnalysisMeta,
    EntityRecord,
    EdgeRecord,
    FileRecord,
    ProjectInfo,
    ProjectStatus,
)
from codeviz.storage import (
    append_entities,
    append_edges,
    append_event,
    clear_events,
    ensure_layout,
    graph_payload,
    graph_summary,
    load_entities,
    load_edges,
    load_events,
    load_meta,
    save_chat_turn,
    load_chat_turn,
    load_chat_session,
    save_meta,
    save_project_info,
    load_project_info,
    search_entities,
)


def _make_status(tmp_path: Path) -> ProjectStatus:
    codeviz_dir = tmp_path / ".codeviz"
    versions_dir = codeviz_dir / "versions"
    return ProjectStatus(
        root=tmp_path,
        codeviz_dir=codeviz_dir,
        current_dir=versions_dir / "test-run",
        chat_dir=codeviz_dir / "chat",
        versions_dir=versions_dir,
    )


def test_ensure_layout_creates_directories(tmp_path: Path) -> None:
    status = _make_status(tmp_path)
    ensure_layout(status)
    assert status.versions_dir.exists()
    assert status.chat_dir.exists()


def test_save_and_load_meta(tmp_path: Path) -> None:
    status = _make_status(tmp_path)
    ensure_layout(status)
    meta = AnalysisMeta(
        run_id="run-1",
        fingerprint="abc123",
        status="completed",
        file_count=5,
        entity_count=10,
        edge_count=8,
        doc_count=2,
    )
    save_meta(status, meta)
    loaded = load_meta(status)
    assert loaded is not None
    assert loaded.run_id == "run-1"
    assert loaded.fingerprint == "abc123"
    assert loaded.entity_count == 10


def test_append_and_load_entities(tmp_path: Path) -> None:
    status = _make_status(tmp_path)
    ensure_layout(status)
    entities = [
        EntityRecord(entity_id="func:main.py:foo:1", entity_type="function", name="foo", file_path="main.py", start_line=1, end_line=5),
        EntityRecord(entity_id="class:main.py:Bar:10", entity_type="class", name="Bar", file_path="main.py", start_line=10, end_line=20),
    ]
    append_entities(status, entities)
    loaded = load_entities(status)
    assert len(loaded) == 2
    assert loaded[0].name == "foo"
    assert loaded[1].entity_type == "class"


def test_append_and_load_edges(tmp_path: Path) -> None:
    status = _make_status(tmp_path)
    ensure_layout(status)
    edges = [
        EdgeRecord(edge_id="e1", source_id="func:a", target_id="func:b", edge_type="calls", file_path="main.py", line=3),
    ]
    append_edges(status, edges)
    loaded = load_edges(status)
    assert len(loaded) == 1
    assert loaded[0].edge_type == "calls"


def test_events_lifecycle(tmp_path: Path) -> None:
    status = _make_status(tmp_path)
    ensure_layout(status)
    append_event(status, {"type": "analysis.started", "data": {}})
    append_event(status, {"type": "file.extracted", "data": {"file": "a.py"}})
    events = load_events(status)
    assert len(events) == 2
    assert events[0]["type"] == "analysis.started"

    after_events = load_events(status, after=1)
    assert len(after_events) == 1

    clear_events(status)
    assert len(load_events(status)) == 0


def test_graph_payload_and_summary(tmp_path: Path) -> None:
    status = _make_status(tmp_path)
    ensure_layout(status)
    entities = [EntityRecord(entity_id="f:a:foo:1", entity_type="function", name="foo", file_path="a.py", start_line=1, end_line=5)]
    edges = [EdgeRecord(edge_id="e1", source_id="f:a:foo:1", target_id="f:b:bar:1", edge_type="calls", file_path="a.py", line=3)]
    append_entities(status, entities)
    append_edges(status, edges)

    payload = graph_payload(status)
    assert len(payload["entities"]) == 1
    assert len(payload["edges"]) == 1

    # graph_summary reads from meta, so save it first
    meta = AnalysisMeta(run_id="r1", fingerprint="x", status="completed", file_count=1, entity_count=1, edge_count=1, doc_count=0)
    save_meta(status, meta)
    summary = graph_summary(status)
    assert summary["entities"] == 1
    assert summary["edges"] == 1


def test_search_entities_by_name(tmp_path: Path) -> None:
    status = _make_status(tmp_path)
    ensure_layout(status)
    entities = [
        EntityRecord(entity_id="f:a:calculate:1", entity_type="function", name="calculate_total", file_path="math.py", start_line=1, end_line=5),
        EntityRecord(entity_id="f:a:render:10", entity_type="function", name="render_page", file_path="view.py", start_line=10, end_line=20),
    ]
    append_entities(status, entities)

    results = search_entities(status, "calculate")
    assert len(results) >= 1
    assert results[0]["name"] == "calculate_total"


def test_save_and_load_project_info(tmp_path: Path) -> None:
    status = _make_status(tmp_path)
    ensure_layout(status)
    info = ProjectInfo(name="test", root=str(tmp_path), description="A test project", languages=["python"], readme_summary="Test readme")
    save_project_info(status, info)
    loaded = load_project_info(status)
    assert loaded is not None
    assert loaded.name == "test"
    assert loaded.languages == ["python"]


def test_chat_turn_lifecycle(tmp_path: Path) -> None:
    status = _make_status(tmp_path)
    ensure_layout(status)
    turn = {
        "turn_id": "t1",
        "session_id": "default",
        "question": "What is foo?",
        "answer": "A function",
        "status": "completed",
    }
    save_chat_turn(status, turn)
    loaded = load_chat_turn(status, "t1")
    assert loaded is not None
    assert loaded["question"] == "What is foo?"

    session = load_chat_session(status, "default")
    assert len(session) == 1
    assert session[0]["turn_id"] == "t1"
