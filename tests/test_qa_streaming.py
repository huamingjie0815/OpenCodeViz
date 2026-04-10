from __future__ import annotations

import io
import json
from pathlib import Path
from types import SimpleNamespace

from codeviz.project import CodeVizProject
from codeviz.qa_agent import ProjectQAAgent
from codeviz.server import CodeVizRequestHandler


def test_collect_stream_messages_handles_nested_payloads(fixture_project: Path) -> None:
    project = CodeVizProject(fixture_project)
    agent = ProjectQAAgent(fixture_project, project.status, project.config)

    payload = {
        "agent": {
            "state": {
                "messages": [
                    SimpleNamespace(type="ai", content=[SimpleNamespace(text="Nested final answer")], tool_calls=[]),
                ]
            }
        }
    }

    messages = agent._collect_stream_messages(payload)
    assert len(messages) == 1
    assert agent._extract_answer(messages) == "Nested final answer"


def test_start_chat_marks_turn_failed_when_agent_execution_raises(fixture_project: Path, monkeypatch) -> None:
    project = CodeVizProject(fixture_project)
    project.ensure_dirs()

    monkeypatch.setattr(CodeVizProject, "_freshness", lambda self: {"state": "fresh"})

    def _raise(*args, **kwargs):
        raise RuntimeError("stream parse failed")

    monkeypatch.setattr(ProjectQAAgent, "ask", _raise)

    payload = project.start_chat("what does the service do?")
    thread = project._chat_threads[payload["turn_id"]]
    thread.join(timeout=5)
    assert not thread.is_alive(), "worker thread did not complete in time"

    turn = project.chat_turn_payload(payload["turn_id"])
    assert turn is not None
    assert turn["status"] == "failed"
    assert "stream parse failed" in turn["answer"]


def test_stream_chat_turn_flushes_final_done_event() -> None:
    flush_calls: list[int] = []

    class DummyWFile(io.BytesIO):
        def flush(self) -> None:
            flush_calls.append(1)

    handler = object.__new__(CodeVizRequestHandler)
    handler.project = SimpleNamespace(
        chat_turn_payload=lambda turn_id: {
            "ok": True,
            "status": "completed",
            "answer": "done",
            "steps": [{"type": "thinking", "summary": "Analyzing question..."}],
        }
    )
    handler.wfile = DummyWFile()
    handler.send_response = lambda code: None
    handler.send_header = lambda key, value: None
    handler.end_headers = lambda: None

    handler._stream_chat_turn("turn-1")

    body = handler.wfile.getvalue().decode("utf-8")
    assert "event: step" in body
    assert "event: done" in body
    assert len(flush_calls) >= 2


def test_search_tool_blocks_duplicate_calls_and_compacts_results(fixture_project: Path, monkeypatch) -> None:
    project = CodeVizProject(fixture_project)
    agent = ProjectQAAgent(fixture_project, project.status, {"qaSearchLimit": 3, "qaToolBudget": 6})

    monkeypatch.setattr(
        "codeviz.qa_agent.search_entities",
        lambda status, query, limit=20: [
            {
                "entity_id": "e1",
                "entity_type": "function",
                "name": "alpha",
                "file_path": "src/service.ts",
                "start_line": 10,
                "end_line": 20,
                "signature": "function alpha()",
                "description": "A" * 300,
                "parent_id": "p1",
                "language": "ts",
            },
            {
                "entity_id": "e2",
                "entity_type": "function",
                "name": "beta",
                "file_path": "src/helper.ts",
                "start_line": 30,
                "end_line": 40,
                "signature": "function beta()",
                "description": "B" * 300,
                "parent_id": "p2",
                "language": "ts",
            },
            {
                "entity_id": "e3",
                "entity_type": "function",
                "name": "gamma",
                "file_path": "src/view.ts",
                "start_line": 50,
                "end_line": 60,
                "signature": "function gamma()",
                "description": "C" * 300,
                "parent_id": "p3",
                "language": "ts",
            },
        ],
    )

    search_tool = agent._build_tools()[0]

    first = json.loads(search_tool.invoke({"query": "service"}))
    second = json.loads(search_tool.invoke({"query": "service"}))

    assert first["count"] == 3
    assert len(first["results"]) == 3
    assert "parent_id" not in first["results"][0]
    assert len(first["results"][0]["description"]) <= 160
    assert "Duplicate tool call blocked" in second["warning"]


def test_tool_budget_stops_additional_unique_calls(fixture_project: Path, monkeypatch) -> None:
    project = CodeVizProject(fixture_project)
    agent = ProjectQAAgent(fixture_project, project.status, {"qaToolBudget": 3})

    monkeypatch.setattr(
        "codeviz.qa_agent.search_entities",
        lambda status, query, limit=20: [],
    )
    monkeypatch.setattr(
        "codeviz.qa_agent.search_documents_by_query",
        lambda status, query, limit=10: [],
    )

    search_tool, entity_tool, docs_tool, read_tool, *_ = agent._build_tools()

    first = json.loads(search_tool.invoke({"query": "service"}))
    second = json.loads(entity_tool.invoke({"entity_id": "entity-1"}))
    third = json.loads(docs_tool.invoke({"query": "service"}))
    fourth = json.loads(read_tool.invoke({"file_path": "src/service.ts", "start_line": 1, "end_line": 10}))

    assert first["count"] == 0
    assert second["entity"] is None
    assert third["count"] == 0
    assert "Tool budget reached" in fourth["warning"]