"""Tests for the import_entities cross-file edge resolution mechanism."""
from __future__ import annotations

from pathlib import Path

import pytest

from codeviz.analysis import _resolve_import_url, _build_cross_file_edges
from codeviz.models import EdgeRecord


# ---------------------------------------------------------------------------
# _resolve_import_url
# ---------------------------------------------------------------------------

KNOWN_FILES = {
    "src/service.ts",
    "src/helper.ts",
    "src/view.jsx",
    "src/components/Button.tsx",
    "lib/utils/format.ts",
    "lib/utils/parse.ts",
}


class TestResolveImportUrlRelative:
    def test_relative_same_dir_no_ext(self):
        result = _resolve_import_url("./helper", "src/service.ts", KNOWN_FILES)
        assert result == "src/helper.ts"

    def test_relative_same_dir_with_ext(self):
        result = _resolve_import_url("./helper.ts", "src/service.ts", KNOWN_FILES)
        assert result == "src/helper.ts"

    def test_relative_up_one_dir(self):
        result = _resolve_import_url("../helper", "src/components/Button.tsx", KNOWN_FILES)
        assert result == "src/helper.ts"

    def test_relative_nested_path(self):
        result = _resolve_import_url("./utils/format", "lib/index.ts", KNOWN_FILES)
        assert result == "lib/utils/format.ts"

    def test_relative_not_found_returns_none(self):
        result = _resolve_import_url("./nonexistent", "src/service.ts", KNOWN_FILES)
        assert result is None

    def test_relative_wrong_extension_falls_back(self):
        # ./helper.js doesn't exist but ./helper.ts does
        result = _resolve_import_url("./helper.js", "src/service.ts", KNOWN_FILES)
        assert result == "src/helper.ts"


class TestResolveImportUrlAlias:
    def test_at_alias(self):
        result = _resolve_import_url("@/service", "src/view.jsx", KNOWN_FILES)
        assert result == "src/service.ts"

    def test_tilde_slash_alias(self):
        result = _resolve_import_url("~/helper", "src/view.jsx", KNOWN_FILES)
        assert result == "src/helper.ts"

    def test_src_prefix(self):
        result = _resolve_import_url("src/helper", "app/main.ts", KNOWN_FILES)
        assert result == "src/helper.ts"

    def test_disambiguation_by_suffix(self):
        # Both format.ts and parse.ts have unique names — should match correctly
        result = _resolve_import_url("@/utils/format", "src/service.ts", KNOWN_FILES)
        assert result == "lib/utils/format.ts"

    def test_ambiguous_returns_none(self):
        # Two files with same stem 'format' would be ambiguous; simulate with custom set
        ambiguous_files = {
            "src/format.ts",
            "lib/format.ts",
        }
        result = _resolve_import_url("@/format", "src/service.ts", ambiguous_files)
        # Both have stem 'format' and no path suffix helps disambiguate → None
        assert result is None


class TestResolveImportUrlSkipped:
    def test_bare_package_name_skipped(self):
        assert _resolve_import_url("react", "src/view.jsx", KNOWN_FILES) is None

    def test_bare_stdlib_name_skipped(self):
        assert _resolve_import_url("os", "src/service.ts", KNOWN_FILES) is None

    def test_empty_url_returns_none(self):
        assert _resolve_import_url("", "src/service.ts", KNOWN_FILES) is None

    def test_scoped_npm_package_skipped(self):
        # "@org/package" has a "/" but no stem match in known files
        result = _resolve_import_url("@org/package", "src/view.jsx", KNOWN_FILES)
        assert result is None


# ---------------------------------------------------------------------------
# _build_cross_file_edges
# ---------------------------------------------------------------------------

def _make_entity_id(etype: str, file: str, name: str, line: int = 1) -> str:
    return f"{etype}:{file}:{name}:{line}"


class TestBuildCrossFileEdges:
    def test_resolves_pending_when_target_available(self):
        src_id = _make_entity_id("function", "src/service.ts", "runService")
        pending: dict[str, list[tuple[str, str, str]]] = {
            "src/helper.ts": [(src_id, "helper", "src/service.ts")],
        }
        tgt_id = _make_entity_id("function", "src/helper.ts", "helper")
        file_entity_index = {
            "src/helper.ts": {"helper": tgt_id},
        }
        edges = _build_cross_file_edges(pending, file_entity_index, {"src/helper.ts"})

        assert len(edges) == 1
        assert edges[0].source_id == src_id
        assert edges[0].target_id == tgt_id
        assert edges[0].edge_type == "imports"
        # Resolved target is removed from pending
        assert "src/helper.ts" not in pending

    def test_unmatched_name_stays_in_pending(self):
        src_id = _make_entity_id("function", "src/service.ts", "runService")
        pending: dict[str, list[tuple[str, str, str]]] = {
            "src/helper.ts": [(src_id, "nonexistent", "src/service.ts")],
        }
        file_entity_index = {
            "src/helper.ts": {"helper": _make_entity_id("function", "src/helper.ts", "helper")},
        }
        edges = _build_cross_file_edges(pending, file_entity_index, {"src/helper.ts"})

        assert edges == []
        # Still in pending because name didn't match
        assert "src/helper.ts" in pending
        assert len(pending["src/helper.ts"]) == 1

    def test_target_not_in_resolved_files_is_skipped(self):
        src_id = _make_entity_id("function", "src/service.ts", "runService")
        pending: dict[str, list[tuple[str, str, str]]] = {
            "src/helper.ts": [(src_id, "helper", "src/service.ts")],
        }
        file_entity_index: dict[str, dict[str, str]] = {}
        # Pass empty resolved_files — target not ready yet
        edges = _build_cross_file_edges(pending, file_entity_index, set())

        assert edges == []
        assert "src/helper.ts" in pending

    def test_multiple_names_partial_resolve(self):
        src_id = _make_entity_id("function", "src/view.jsx", "View")
        pending: dict[str, list[tuple[str, str, str]]] = {
            "src/service.ts": [
                (src_id, "runService", "src/view.jsx"),
                (src_id, "unknownFn", "src/view.jsx"),
            ],
        }
        run_id = _make_entity_id("function", "src/service.ts", "runService")
        file_entity_index = {
            "src/service.ts": {"runService": run_id},
        }
        edges = _build_cross_file_edges(pending, file_entity_index, {"src/service.ts"})

        assert len(edges) == 1
        assert edges[0].target_id == run_id
        # unknownFn still pending
        assert "src/service.ts" in pending
        assert pending["src/service.ts"][0][1] == "unknownFn"


# ---------------------------------------------------------------------------
# extract_file returns import_entities
# ---------------------------------------------------------------------------

class TestExtractFileImportEntities:
    """Unit test that extract_file parses and returns import_entities from LLM output."""

    def test_import_entities_returned_from_parsed_output(self, monkeypatch):
        from codeviz.extractor import LLMExtractor

        fake_parsed = {
            "entities": [
                {"name": "runService", "type": "function", "start_line": 3, "end_line": 6},
            ],
            "edges": [],
            "import_entities": [
                {"url": "./helper", "names": ["helper"]},
            ],
        }

        extractor = LLMExtractor()
        monkeypatch.setattr(extractor, "_invoke_structured", lambda *a, **kw: fake_parsed)

        result = extractor.extract_file("src/service.ts", "dummy content", "typescript")

        assert "import_entities" in result
        assert result["import_entities"] == [{"url": "./helper", "names": ["helper"]}]

    def test_missing_import_entities_returns_empty_list(self, monkeypatch):
        from codeviz.extractor import LLMExtractor

        fake_parsed = {
            "entities": [],
            "edges": [],
            # No import_entities key
        }

        extractor = LLMExtractor()
        monkeypatch.setattr(extractor, "_invoke_structured", lambda *a, **kw: fake_parsed)

        result = extractor.extract_file("src/view.jsx", "dummy", "javascript")

        assert result["import_entities"] == []

    def test_invalid_entries_filtered_out(self, monkeypatch):
        from codeviz.extractor import LLMExtractor

        fake_parsed = {
            "entities": [],
            "edges": [],
            "import_entities": [
                {"url": "", "names": ["foo"]},           # empty url — filtered
                {"url": "./bar", "names": []},            # empty names — filtered
                {"url": "./valid", "names": ["Baz"]},     # valid
            ],
        }

        extractor = LLMExtractor()
        monkeypatch.setattr(extractor, "_invoke_structured", lambda *a, **kw: fake_parsed)

        result = extractor.extract_file("src/main.ts", "dummy", "typescript")

        assert result["import_entities"] == [{"url": "./valid", "names": ["Baz"]}]
