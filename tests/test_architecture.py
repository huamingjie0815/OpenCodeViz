from __future__ import annotations

from codeviz.architecture import build_architecture_snapshot, build_flow_payload
from codeviz.models import EdgeRecord, EntityRecord, FileRecord


def test_build_architecture_snapshot_groups_entities_into_modules() -> None:
    files = [
        FileRecord(path="src/codeviz/project.py", language="python", content_hash="a"),
        FileRecord(path="src/codeviz/server.py", language="python", content_hash="b"),
        FileRecord(path="src/codeviz/web/app.js", language="javascript", content_hash="c"),
    ]
    entities = [
        EntityRecord(
            entity_id="function:src/codeviz/project.py:analyze:1",
            entity_type="function",
            name="analyze",
            file_path="src/codeviz/project.py",
            start_line=1,
            end_line=10,
        ),
        EntityRecord(
            entity_id="function:src/codeviz/server.py:start:1",
            entity_type="function",
            name="start",
            file_path="src/codeviz/server.py",
            start_line=1,
            end_line=10,
        ),
        EntityRecord(
            entity_id="function:src/codeviz/web/app.js:loadInitialGraph:1",
            entity_type="function",
            name="loadInitialGraph",
            file_path="src/codeviz/web/app.js",
            start_line=1,
            end_line=10,
        ),
    ]
    edges = [
        EdgeRecord(
            edge_id="e1",
            source_id="function:src/codeviz/project.py:analyze:1",
            target_id="function:src/codeviz/server.py:start:1",
            edge_type="calls",
            file_path="src/codeviz/project.py",
            line=4,
        ),
        EdgeRecord(
            edge_id="e2",
            source_id="function:src/codeviz/project.py:analyze:1",
            target_id="function:src/codeviz/web/app.js:loadInitialGraph:1",
            edge_type="imports",
            file_path="src/codeviz/project.py",
            line=5,
        ),
    ]

    snapshot = build_architecture_snapshot(files, entities, edges)

    assert [module.display_name for module in snapshot.modules] == ["project", "server", "web"]
    assert len(snapshot.dependencies) == 2
    assert snapshot.dependencies[0].source_module_id == "src/codeviz/project"
    assert snapshot.dependencies[0].target_module_id == "src/codeviz/server"
    assert snapshot.dependencies[0].calls_count == 1
    assert snapshot.dependencies[1].source_module_id == "src/codeviz/project"
    assert snapshot.dependencies[1].target_module_id == "src/codeviz/web"
    assert snapshot.dependencies[1].imports_count == 1


def test_build_flow_payload_follows_entity_calls() -> None:
    entities = [
        EntityRecord(
            entity_id="function:src/codeviz/project.py:analyze:1",
            entity_type="function",
            name="analyze",
            file_path="src/codeviz/project.py",
            start_line=1,
            end_line=10,
        ),
        EntityRecord(
            entity_id="function:src/codeviz/server.py:start:1",
            entity_type="function",
            name="start",
            file_path="src/codeviz/server.py",
            start_line=1,
            end_line=10,
        ),
    ]
    edges = [
        EdgeRecord(
            edge_id="e1",
            source_id="function:src/codeviz/project.py:analyze:1",
            target_id="function:src/codeviz/server.py:start:1",
            edge_type="calls",
            file_path="src/codeviz/project.py",
            line=4,
        ),
    ]

    flow = build_flow_payload("function:src/codeviz/project.py:analyze:1", entities, edges)

    assert [step.label for step in flow.steps] == ["analyze", "start"]
    assert flow.transitions[0]["source"] == "step-1"
    assert flow.transitions[0]["target"] == "step-2"


def test_build_flow_payload_skips_self_loop_transition() -> None:
    entities = [
        EntityRecord(
            entity_id="function:bin/codeviz.js:main:2",
            entity_type="function",
            name="main",
            file_path="bin/codeviz.js",
            start_line=2,
            end_line=8,
        ),
    ]
    edges = [
        EdgeRecord(
            edge_id="e1",
            source_id="function:bin/codeviz.js:main:2",
            target_id="function:bin/codeviz.js:main:2",
            edge_type="calls",
            file_path="bin/codeviz.js",
            line=4,
        ),
    ]

    flow = build_flow_payload("function:bin/codeviz.js:main:2", entities, edges)

    assert [step.label for step in flow.steps] == ["main"]
    assert flow.transitions == []
    assert "loop_detected" in flow.warnings


def test_build_flow_payload_branches_to_multiple_children() -> None:
    entities = [
        EntityRecord(
            entity_id="function:src/app.py:main:1",
            entity_type="function",
            name="main",
            file_path="src/app.py",
            start_line=1,
            end_line=10,
        ),
        EntityRecord(
            entity_id="function:src/a.py:alpha:1",
            entity_type="function",
            name="alpha",
            file_path="src/a.py",
            start_line=1,
            end_line=10,
        ),
        EntityRecord(
            entity_id="function:src/b.py:beta:1",
            entity_type="function",
            name="beta",
            file_path="src/b.py",
            start_line=1,
            end_line=10,
        ),
    ]
    edges = [
        EdgeRecord(
            edge_id="e1",
            source_id="function:src/app.py:main:1",
            target_id="function:src/a.py:alpha:1",
            edge_type="calls",
            file_path="src/app.py",
            line=2,
        ),
        EdgeRecord(
            edge_id="e2",
            source_id="function:src/app.py:main:1",
            target_id="function:src/b.py:beta:1",
            edge_type="calls",
            file_path="src/app.py",
            line=3,
        ),
    ]

    flow = build_flow_payload("function:src/app.py:main:1", entities, edges)

    assert [step.label for step in flow.steps] == ["main", "alpha", "beta"]
    assert [step.depth for step in flow.steps] == [0, 1, 1]
    assert {(item["source"], item["target"]) for item in flow.transitions} == {
        ("step-1", "step-2"),
        ("step-1", "step-3"),
    }


def test_build_flow_payload_marks_collapsed_children_when_branch_limit_hits() -> None:
    entities = [
        EntityRecord(
            entity_id="function:src/app.py:main:1",
            entity_type="function",
            name="main",
            file_path="src/app.py",
            start_line=1,
            end_line=10,
        ),
        EntityRecord(
            entity_id="function:src/a.py:alpha:1",
            entity_type="function",
            name="alpha",
            file_path="src/a.py",
            start_line=1,
            end_line=10,
        ),
        EntityRecord(
            entity_id="function:src/b.py:beta:1",
            entity_type="function",
            name="beta",
            file_path="src/b.py",
            start_line=1,
            end_line=10,
        ),
        EntityRecord(
            entity_id="function:src/c.py:gamma:1",
            entity_type="function",
            name="gamma",
            file_path="src/c.py",
            start_line=1,
            end_line=10,
        ),
    ]
    edges = [
        EdgeRecord(
            edge_id="e1",
            source_id="function:src/app.py:main:1",
            target_id="function:src/a.py:alpha:1",
            edge_type="calls",
            file_path="src/app.py",
            line=2,
        ),
        EdgeRecord(
            edge_id="e2",
            source_id="function:src/app.py:main:1",
            target_id="function:src/b.py:beta:1",
            edge_type="calls",
            file_path="src/app.py",
            line=3,
        ),
        EdgeRecord(
            edge_id="e3",
            source_id="function:src/app.py:main:1",
            target_id="function:src/c.py:gamma:1",
            edge_type="calls",
            file_path="src/app.py",
            line=4,
        ),
    ]

    flow = build_flow_payload(
        "function:src/app.py:main:1",
        entities,
        edges,
        max_branch_per_node=2,
    )

    assert [step.label for step in flow.steps] == ["main", "alpha", "beta"]
    assert flow.steps[0].child_count == 3
    assert flow.steps[0].visible_child_count == 2
    assert flow.steps[0].collapsed_child_count == 1


def test_build_architecture_snapshot_excludes_tests_by_default() -> None:
    files = [
        FileRecord(path="src/codeviz/project.py", language="python", content_hash="a"),
        FileRecord(path="tests/test_project.py", language="python", content_hash="b"),
    ]
    entities = [
        EntityRecord(
            entity_id="function:src/codeviz/project.py:analyze:1",
            entity_type="function",
            name="analyze",
            file_path="src/codeviz/project.py",
            start_line=1,
            end_line=10,
        ),
        EntityRecord(
            entity_id="function:tests/test_project.py:test_analyze:1",
            entity_type="function",
            name="test_analyze",
            file_path="tests/test_project.py",
            start_line=1,
            end_line=10,
        ),
    ]
    edges = [
        EdgeRecord(
            edge_id="e1",
            source_id="function:tests/test_project.py:test_analyze:1",
            target_id="function:src/codeviz/project.py:analyze:1",
            edge_type="calls",
            file_path="tests/test_project.py",
            line=4,
        ),
    ]

    snapshot = build_architecture_snapshot(files, entities, edges)

    assert [module.display_name for module in snapshot.modules] == ["project"]
    assert snapshot.dependencies == []
