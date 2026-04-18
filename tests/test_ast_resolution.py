from codeviz.parsing.base import ParseCallSite, ParseEntity, ParseImport, ParseReference, ParseResult
from codeviz.resolution.deterministic import resolve_file


def test_resolve_file_builds_define_import_and_call_edges() -> None:
    parse_result = ParseResult(
        entities=[
            ParseEntity(local_id="class:src/app.py:App:1", name="App", kind="class", file_path="src/app.py", start_line=1, end_line=5, language="python"),
            ParseEntity(local_id="method:src/app.py:boot:2", name="boot", kind="method", file_path="src/app.py", start_line=2, end_line=4, parent_local_id="class:src/app.py:App:1", language="python"),
            ParseEntity(local_id="function:src/app.py:helper:6", name="helper", kind="function", file_path="src/app.py", start_line=6, end_line=7, language="python"),
        ],
        imports=[
            ParseImport(module_path="./helper", import_kind="named", imported_name="helper", local_name="helper", line=1),
        ],
        call_sites=[
            ParseCallSite(source_entity_local_id="method:src/app.py:boot:2", callee_name="helper", line=3),
        ],
    )

    resolved = resolve_file(
        file_path="src/app.py",
        language="python",
        parse_result=parse_result,
        known_files={"src/app.py", "src/helper.py"},
        file_entity_index={"src/helper.py": {"helper": "function:src/helper.py:helper:1"}},
        pending_imports={},
    )

    assert [entity.entity_id for entity in resolved.entities] == [
        "class:src/app.py:App:1",
        "method:src/app.py:boot:2",
        "function:src/app.py:helper:6",
    ]
    assert any(edge.edge_type == "defines" and edge.source_id == "class:src/app.py:App:1" for edge in resolved.edges)
    assert any(edge.edge_type == "calls" and edge.target_id == "function:src/app.py:helper:6" for edge in resolved.edges)
    assert any(edge.edge_type == "imports" and edge.target_id == "function:src/helper.py:helper:1" for edge in resolved.edges)
    assert resolved.unresolved == []


def test_resolve_file_builds_use_edges_for_type_references() -> None:
    parse_result = ParseResult(
        entities=[
            ParseEntity(local_id="class:src/app.py:Config:1", name="Config", kind="class", file_path="src/app.py", start_line=1, end_line=3, language="python"),
            ParseEntity(local_id="function:src/app.py:boot:5", name="boot", kind="function", file_path="src/app.py", start_line=5, end_line=7, language="python"),
        ],
        references=[
            ParseReference(source_entity_local_id="function:src/app.py:boot:5", name="Config", reference_kind="type", line=5),
        ],
    )

    resolved = resolve_file(
        file_path="src/app.py",
        language="python",
        parse_result=parse_result,
        known_files={"src/app.py"},
        file_entity_index={},
        pending_imports={},
    )

    assert any(edge.edge_type == "uses" and edge.target_id == "class:src/app.py:Config:1" for edge in resolved.edges)


def test_resolve_file_keeps_ambiguous_call_unresolved() -> None:
    parse_result = ParseResult(
        entities=[
            ParseEntity(local_id="function:src/app.py:boot:1", name="boot", kind="function", file_path="src/app.py", start_line=1, end_line=3, language="python"),
        ],
        call_sites=[
            ParseCallSite(source_entity_local_id="function:src/app.py:boot:1", callee_name="render", line=2),
        ],
    )

    resolved = resolve_file(
        file_path="src/app.py",
        language="python",
        parse_result=parse_result,
        known_files={"src/app.py"},
        file_entity_index={},
        pending_imports={},
    )

    assert resolved.edges == []
    assert [(item.edge_type, item.target_name, item.line) for item in resolved.unresolved] == [
        ("calls", "render", 2),
    ]


def test_resolve_unresolved_relations_skips_items_without_candidates() -> None:
    from codeviz.extractor import LLMExtractor
    from codeviz.resolution.deterministic import UnresolvedRelation
    from codeviz.resolution.fallback import resolve_unresolved_relations

    extractor = LLMExtractor(config={"provider": "openai", "model": "gpt-4o-mini"})
    unresolved = [
        UnresolvedRelation(
            source_id="function:src/app.ts:boot:1",
            edge_type="calls",
            target_name="render",
            file_path="src/app.ts",
            line=2,
            candidate_ids=[],
        )
    ]

    assert resolve_unresolved_relations(unresolved, [], extractor, "auto") == []
