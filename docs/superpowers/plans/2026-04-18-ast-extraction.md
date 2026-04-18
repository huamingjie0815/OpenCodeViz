# AST Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace per-file LLM extraction with AST-first parsing and deterministic resolution, keeping the LLM only for unresolved fallback and project summary generation.

**Architecture:** Add a `parsing` package that turns source files into a small language-agnostic IR using `tree-sitter`, then convert that IR into the existing `EntityRecord` and `EdgeRecord` models in a deterministic resolver. Keep the current snapshot, storage, architecture, and flow layers intact by changing only the extraction stage in `src/codeviz/analysis.py`, and gate rollout with `extractorMode` and `fallbackMode`.

**Tech Stack:** Python 3.12, `tree-sitter` Python bindings, pytest, existing CodeViz analysis/storage/runtime config modules

---

## File Map

- Modify: `pyproject.toml`
  - add `tree-sitter` runtime dependencies for Python, JavaScript, and TypeScript grammars
- Create: `src/codeviz/parsing/__init__.py`
  - export AST extractor and parse IR types
- Create: `src/codeviz/parsing/base.py`
  - define parse IR dataclasses and parser protocol
- Create: `src/codeviz/parsing/registry.py`
  - map `detect_language()` results to parser instances
- Create: `src/codeviz/parsing/extractor.py`
  - AST-first extractor facade used by `analysis.py`
- Create: `src/codeviz/parsing/tree_sitter_parser.py`
  - shared `tree-sitter` parser helpers and node-text utilities
- Create: `src/codeviz/parsing/languages/python.py`
  - Python AST adapter
- Create: `src/codeviz/parsing/languages/javascript.py`
  - JavaScript and JSX AST adapter
- Create: `src/codeviz/parsing/languages/typescript.py`
  - TypeScript and TSX AST adapter
- Create: `src/codeviz/resolution/__init__.py`
  - export deterministic and fallback resolution helpers
- Create: `src/codeviz/resolution/deterministic.py`
  - convert parse IR into `EntityRecord`, `EdgeRecord`, pending imports, and unresolved relations
- Create: `src/codeviz/resolution/fallback.py`
  - unresolved-only LLM disambiguation
- Modify: `src/codeviz/analysis.py`
  - switch extraction pipeline from per-file LLM to AST-first/hybrid/legacy modes
- Modify: `src/codeviz/extractor.py`
  - keep project-summary and JSON invocation utilities, but stop treating it as the primary per-file extractor in AST/hybrid mode
- Modify: `src/codeviz/runtime_config.py`
  - add helpers for `extractorMode` and `fallbackMode`
- Modify: `README.md`
  - document new extraction modes and config keys
- Create: `tests/test_ast_parsing.py`
  - cover parser registry, AST extractor facade, and Python/JS/TS adapters
- Create: `tests/test_runtime_config.py`
  - cover extraction mode precedence and normalization
- Create: `tests/test_ast_resolution.py`
  - cover deterministic resolution and unresolved fallback eligibility
- Modify: `tests/test_import_resolution.py`
  - move helper imports to the new deterministic resolver module
- Modify: `tests/test_project_integration.py`
  - verify AST mode writes usable graph data without per-file LLM extraction

### Task 1: Parsing Scaffold And Runtime Flags

**Files:**
- Modify: `pyproject.toml`
- Create: `src/codeviz/parsing/__init__.py`
- Create: `src/codeviz/parsing/base.py`
- Create: `src/codeviz/parsing/registry.py`
- Create: `src/codeviz/parsing/extractor.py`
- Modify: `src/codeviz/runtime_config.py`
- Create: `tests/test_ast_parsing.py`
- Create: `tests/test_runtime_config.py`

- [ ] **Step 1: Write the failing scaffold tests**

```python
from codeviz.parsing import ASTExtractor, ParseResult, get_parser
from codeviz.runtime_config import extractor_mode, fallback_mode


def test_ast_extractor_returns_empty_result_for_unknown_language() -> None:
    extractor = ASTExtractor()
    result = extractor.extract_file("README.md", "# hello\n", "unknown")

    assert isinstance(result, ParseResult)
    assert result.entities == []
    assert result.imports == []
    assert result.call_sites == []


def test_registry_is_empty_for_unregistered_language() -> None:
    assert get_parser("unknown") is None


def test_runtime_modes_prefer_env_over_config(monkeypatch) -> None:
    monkeypatch.setenv("CODEVIZ_EXTRACTOR_MODE", "ast")
    monkeypatch.setenv("CODEVIZ_FALLBACK_MODE", "off")

    assert extractor_mode({"extractorMode": "llm"}) == "ast"
    assert fallback_mode({"fallbackMode": "always"}) == "off"


def test_runtime_modes_default_to_hybrid_and_auto(monkeypatch) -> None:
    monkeypatch.delenv("CODEVIZ_EXTRACTOR_MODE", raising=False)
    monkeypatch.delenv("CODEVIZ_FALLBACK_MODE", raising=False)

    assert extractor_mode({}) == "hybrid"
    assert fallback_mode({}) == "auto"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ast_parsing.py tests/test_runtime_config.py -v`

Expected: FAIL with import errors because the `codeviz.parsing` package and runtime mode helpers do not exist yet.

- [ ] **Step 3: Write the minimal parsing scaffold and mode helpers**

```toml
[project]
dependencies = [
  "pydantic>=2.11,<3",
  "langchain>=0.3,<1",
  "langchain-core>=0.3,<1",
  "langchain-openai>=0.3,<1",
  "langchain-anthropic>=0.3,<1",
  "langchain-google-genai>=2,<3",
  "tree-sitter>=0.24,<0.25",
  "tree-sitter-python>=0.23,<0.24",
  "tree-sitter-javascript>=0.23,<0.24",
  "tree-sitter-typescript>=0.23,<0.24",
]
```

```python
# src/codeviz/parsing/base.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(slots=True)
class ParseEntity:
    local_id: str
    name: str
    kind: str
    file_path: str
    start_line: int
    end_line: int
    signature: str = ""
    parent_local_id: str = ""
    exported: bool = False
    language: str = ""


@dataclass(slots=True)
class ParseImport:
    module_path: str
    import_kind: str
    imported_name: str
    local_name: str
    source_entity_local_id: str = ""
    line: int = 0


@dataclass(slots=True)
class ParseReference:
    source_entity_local_id: str
    name: str
    qualifier: str = ""
    reference_kind: str = "read"
    line: int = 0


@dataclass(slots=True)
class ParseCallSite:
    source_entity_local_id: str
    callee_name: str
    callee_qualifier: str = ""
    line: int = 0


@dataclass(slots=True)
class ParseInheritance:
    source_entity_local_id: str
    target_name: str
    relation_type: str
    line: int = 0


@dataclass(slots=True)
class ParseExport:
    export_name: str
    local_name: str
    line: int = 0


@dataclass(slots=True)
class ParseDiagnostic:
    level: str
    message: str
    line: int = 0


@dataclass(slots=True)
class ParseResult:
    entities: list[ParseEntity] = field(default_factory=list)
    imports: list[ParseImport] = field(default_factory=list)
    references: list[ParseReference] = field(default_factory=list)
    call_sites: list[ParseCallSite] = field(default_factory=list)
    inheritance: list[ParseInheritance] = field(default_factory=list)
    exports: list[ParseExport] = field(default_factory=list)
    diagnostics: list[ParseDiagnostic] = field(default_factory=list)


class SourceParser(Protocol):
    def parse_file(self, file_path: str, content: str, language: str) -> ParseResult: ...
```

```python
# src/codeviz/parsing/registry.py
from __future__ import annotations

from codeviz.parsing.base import SourceParser


_PARSERS: dict[str, SourceParser] = {}


def register_parser(language: str, parser: SourceParser) -> None:
    _PARSERS[language] = parser


def get_parser(language: str) -> SourceParser | None:
    return _PARSERS.get(language)
```

```python
# src/codeviz/parsing/extractor.py
from __future__ import annotations

from codeviz.parsing.base import ParseResult
from codeviz.parsing.registry import get_parser


class ASTExtractor:
    def extract_file(self, file_path: str, content: str, language: str) -> ParseResult:
        parser = get_parser(language)
        if parser is None:
            return ParseResult()
        return parser.parse_file(file_path, content, language)
```

```python
# src/codeviz/runtime_config.py
def _normalized_mode(value: str, allowed: set[str], default: str) -> str:
    lowered = (value or "").strip().lower()
    return lowered if lowered in allowed else default


def extractor_mode(config: dict) -> str:
    raw = os.environ.get("CODEVIZ_EXTRACTOR_MODE", config.get("extractorMode", "hybrid"))
    return _normalized_mode(raw, {"llm", "ast", "hybrid"}, "hybrid")


def fallback_mode(config: dict) -> str:
    raw = os.environ.get("CODEVIZ_FALLBACK_MODE", config.get("fallbackMode", "auto"))
    return _normalized_mode(raw, {"off", "auto", "always"}, "auto")
```

```python
# src/codeviz/parsing/__init__.py
from codeviz.parsing.base import ParseCallSite, ParseEntity, ParseImport, ParseInheritance, ParseResult
from codeviz.parsing.extractor import ASTExtractor
from codeviz.parsing.registry import get_parser, register_parser

__all__ = [
    "ASTExtractor",
    "ParseCallSite",
    "ParseEntity",
    "ParseImport",
    "ParseInheritance",
    "ParseResult",
    "get_parser",
    "register_parser",
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ast_parsing.py tests/test_runtime_config.py -v`

Expected: PASS for the new scaffold and runtime mode tests.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/codeviz/parsing/__init__.py src/codeviz/parsing/base.py src/codeviz/parsing/registry.py src/codeviz/parsing/extractor.py src/codeviz/runtime_config.py tests/test_ast_parsing.py tests/test_runtime_config.py
git commit -m "feat: add ast parsing scaffold"
```

### Task 2: Python Tree-Sitter Adapter

**Files:**
- Create: `src/codeviz/parsing/tree_sitter_parser.py`
- Create: `src/codeviz/parsing/languages/python.py`
- Modify: `src/codeviz/parsing/registry.py`
- Modify: `tests/test_ast_parsing.py`

- [ ] **Step 1: Write the failing Python parser tests**

```python
from codeviz.parsing import get_parser


def test_python_parser_extracts_entities_imports_calls_and_inheritance() -> None:
    parser = get_parser("python")
    assert parser is not None

    source = """
from pkg.service import run_service as run

class App(BaseApp):
    def boot(self):
        helper()
        self.render()

def helper():
    return run()
""".strip()

    result = parser.parse_file("src/app.py", source, "python")

    assert [entity.name for entity in result.entities] == ["App", "boot", "helper"]
    assert [entity.kind for entity in result.entities] == ["class", "method", "function"]
    assert [(item.module_path, item.imported_name, item.local_name) for item in result.imports] == [
        ("pkg.service", "run_service", "run"),
    ]
    assert [(item.source_entity_local_id, item.callee_name, item.callee_qualifier) for item in result.call_sites] == [
        ("method:src/app.py:boot:4", "helper", ""),
        ("method:src/app.py:boot:5", "render", "self"),
        ("function:src/app.py:helper:7", "run", ""),
    ]
    assert [(item.source_entity_local_id, item.target_name, item.relation_type) for item in result.inheritance] == [
        ("class:src/app.py:App:3", "BaseApp", "extends"),
    ]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ast_parsing.py -k python_parser -v`

Expected: FAIL because no Python parser is registered and no `tree-sitter` helper exists.

- [ ] **Step 3: Write the minimal shared parser helper and Python adapter**

```python
# src/codeviz/parsing/tree_sitter_parser.py
from __future__ import annotations

from tree_sitter import Node, Parser


class TreeSitterSourceParser:
    def __init__(self, language) -> None:
        self._parser = Parser()
        self._parser.language = language

    def parse_bytes(self, content: str):
        return self._parser.parse(content.encode("utf-8"))

    def node_text(self, node: Node, content: str) -> str:
        return content.encode("utf-8")[node.start_byte:node.end_byte].decode("utf-8")

    def line_number(self, node: Node) -> int:
        return node.start_point[0] + 1
```

```python
# src/codeviz/parsing/languages/python.py
from __future__ import annotations

from tree_sitter_python import language as python_language

from codeviz.parsing.base import ParseCallSite, ParseEntity, ParseImport, ParseInheritance, ParseResult
from codeviz.parsing.tree_sitter_parser import TreeSitterSourceParser


class PythonParser(TreeSitterSourceParser):
    def __init__(self) -> None:
        super().__init__(python_language())

    def parse_file(self, file_path: str, content: str, language: str) -> ParseResult:
        tree = self.parse_bytes(content)
        result = ParseResult()
        self._walk(tree.root_node, file_path, content, result, [])
        return result

    def _walk(self, node, file_path: str, content: str, result: ParseResult, parents: list[str]) -> None:
        if node.type == "class_definition":
            name_node = node.child_by_field_name("name")
            local_id = f"class:{file_path}:{self.node_text(name_node, content)}:{self.line_number(node)}"
            result.entities.append(ParseEntity(
                local_id=local_id,
                name=self.node_text(name_node, content),
                kind="class",
                file_path=file_path,
                start_line=self.line_number(node),
                end_line=node.end_point[0] + 1,
                signature=self.node_text(node, content).splitlines()[0],
                language="python",
            ))
            for child in node.named_children:
                if child.type == "argument_list":
                    for base in child.named_children:
                        result.inheritance.append(ParseInheritance(
                            source_entity_local_id=local_id,
                            target_name=self.node_text(base, content),
                            relation_type="extends",
                            line=self.line_number(base),
                        ))
            for child in node.named_children:
                self._walk(child, file_path, content, result, parents + [local_id])
            return

        if node.type == "function_definition":
            name_node = node.child_by_field_name("name")
            kind = "method" if parents else "function"
            local_id = f"{kind}:{file_path}:{self.node_text(name_node, content)}:{self.line_number(node)}"
            result.entities.append(ParseEntity(
                local_id=local_id,
                name=self.node_text(name_node, content),
                kind=kind,
                file_path=file_path,
                start_line=self.line_number(node),
                end_line=node.end_point[0] + 1,
                signature=self.node_text(node, content).splitlines()[0],
                parent_local_id=parents[-1] if parents else "",
                language="python",
            ))
            for child in node.named_children:
                self._walk(child, file_path, content, result, parents + [local_id])
            return

        if node.type == "import_from_statement":
            module_node = node.child_by_field_name("module_name")
            module_path = self.node_text(module_node, content) if module_node else ""
            for child in node.named_children:
                if child.type != "aliased_import":
                    continue
                name_node = child.child_by_field_name("name")
                alias_node = child.child_by_field_name("alias")
                imported_name = self.node_text(name_node, content)
                local_name = self.node_text(alias_node, content) if alias_node else imported_name
                result.imports.append(ParseImport(
                    module_path=module_path,
                    import_kind="named",
                    imported_name=imported_name,
                    local_name=local_name,
                    line=self.line_number(node),
                ))

        if node.type == "call" and parents:
            function_node = node.child_by_field_name("function")
            if function_node is not None:
                text = self.node_text(function_node, content)
                if "." in text:
                    qualifier, callee_name = text.rsplit(".", 1)
                else:
                    qualifier, callee_name = "", text
                result.call_sites.append(ParseCallSite(
                    source_entity_local_id=parents[-1],
                    callee_name=callee_name,
                    callee_qualifier=qualifier,
                    line=self.line_number(node),
                ))

        if node.type == "argument_list":
            return

        for child in node.named_children:
            self._walk(child, file_path, content, result, parents)
```

```python
# src/codeviz/parsing/registry.py
from codeviz.parsing.languages.python import PythonParser

register_parser("python", PythonParser())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ast_parsing.py -k python_parser -v`

Expected: PASS for the Python parser coverage.

- [ ] **Step 5: Commit**

```bash
git add src/codeviz/parsing/tree_sitter_parser.py src/codeviz/parsing/languages/python.py src/codeviz/parsing/registry.py tests/test_ast_parsing.py
git commit -m "feat: add python ast parser"
```

### Task 3: JavaScript And TypeScript Tree-Sitter Adapters

**Files:**
- Create: `src/codeviz/parsing/languages/javascript.py`
- Create: `src/codeviz/parsing/languages/typescript.py`
- Modify: `src/codeviz/parsing/registry.py`
- Modify: `tests/test_ast_parsing.py`

- [ ] **Step 1: Write the failing JavaScript and TypeScript parser tests**

```python
from codeviz.parsing import get_parser


def test_typescript_parser_extracts_named_imports_and_method_calls() -> None:
    parser = get_parser("typescript")
    assert parser is not None

    source = """
import { helper as runHelper } from "./helper";

class App extends BaseApp {
  boot() {
    runHelper();
    this.render();
  }
}
""".strip()

    result = parser.parse_file("src/app.ts", source, "typescript")

    assert [entity.name for entity in result.entities] == ["App", "boot"]
    assert [(item.module_path, item.imported_name, item.local_name) for item in result.imports] == [
        ("./helper", "helper", "runHelper"),
    ]
    assert [(item.callee_name, item.callee_qualifier) for item in result.call_sites] == [
        ("runHelper", ""),
        ("render", "this"),
    ]
    assert result.inheritance[0].target_name == "BaseApp"


def test_javascript_parser_extracts_default_and_namespace_imports() -> None:
    parser = get_parser("javascript")
    assert parser is not None

    source = """
import service from "./service";
import * as metrics from "./metrics";

export function boot() {
  service();
  metrics.record();
}
""".strip()

    result = parser.parse_file("src/app.js", source, "javascript")

    assert [entity.name for entity in result.entities] == ["boot"]
    assert [(item.import_kind, item.imported_name, item.local_name) for item in result.imports] == [
        ("default", "default", "service"),
        ("namespace", "*", "metrics"),
    ]
    assert [(item.callee_name, item.callee_qualifier) for item in result.call_sites] == [
        ("service", ""),
        ("record", "metrics"),
    ]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ast_parsing.py -k "typescript_parser or javascript_parser" -v`

Expected: FAIL because no JavaScript or TypeScript parser is registered.

- [ ] **Step 3: Write the minimal JavaScript/TypeScript adapters**

```python
# src/codeviz/parsing/languages/javascript.py
from __future__ import annotations

from tree_sitter_javascript import language as javascript_language

from codeviz.parsing.base import ParseCallSite, ParseEntity, ParseImport, ParseInheritance, ParseResult
from codeviz.parsing.tree_sitter_parser import TreeSitterSourceParser


class JavaScriptParser(TreeSitterSourceParser):
    def __init__(self) -> None:
        super().__init__(javascript_language())

    def parse_file(self, file_path: str, content: str, language: str) -> ParseResult:
        tree = self.parse_bytes(content)
        result = ParseResult()
        self._walk(tree.root_node, file_path, content, result, [])
        return result

    def _walk(self, node, file_path: str, content: str, result: ParseResult, parents: list[str]) -> None:
        if node.type == "function_declaration":
            name_node = node.child_by_field_name("name")
            local_id = f"function:{file_path}:{self.node_text(name_node, content)}:{self.line_number(node)}"
            result.entities.append(ParseEntity(
                local_id=local_id,
                name=self.node_text(name_node, content),
                kind="function",
                file_path=file_path,
                start_line=self.line_number(node),
                end_line=node.end_point[0] + 1,
                signature=self.node_text(node, content).splitlines()[0],
                exported=node.parent is not None and node.parent.type == "export_statement",
                language=language,
            ))
            for child in node.named_children:
                self._walk(child, file_path, content, result, parents + [local_id])
            return

        if node.type == "class_declaration":
            name_node = node.child_by_field_name("name")
            local_id = f"class:{file_path}:{self.node_text(name_node, content)}:{self.line_number(node)}"
            result.entities.append(ParseEntity(
                local_id=local_id,
                name=self.node_text(name_node, content),
                kind="class",
                file_path=file_path,
                start_line=self.line_number(node),
                end_line=node.end_point[0] + 1,
                signature=self.node_text(node, content).splitlines()[0],
                language=language,
            ))
            heritage = node.child_by_field_name("superclass")
            if heritage is not None:
                result.inheritance.append(ParseInheritance(
                    source_entity_local_id=local_id,
                    target_name=self.node_text(heritage, content),
                    relation_type="extends",
                    line=self.line_number(heritage),
                ))
            for child in node.named_children:
                self._walk(child, file_path, content, result, parents + [local_id])
            return

        if node.type == "method_definition" and parents:
            name_node = node.child_by_field_name("name")
            local_id = f"method:{file_path}:{self.node_text(name_node, content)}:{self.line_number(node)}"
            result.entities.append(ParseEntity(
                local_id=local_id,
                name=self.node_text(name_node, content),
                kind="method",
                file_path=file_path,
                start_line=self.line_number(node),
                end_line=node.end_point[0] + 1,
                signature=self.node_text(node, content).splitlines()[0],
                parent_local_id=parents[-1],
                language=language,
            ))
            for child in node.named_children:
                self._walk(child, file_path, content, result, parents + [local_id])
            return

        if node.type == "import_statement":
            clause = self.node_text(node, content)
            module_node = node.child_by_field_name("source")
            module_path = self.node_text(module_node, content).strip("\"'")
            if " as " in clause and "* as " in clause:
                local_name = clause.split("* as ", 1)[1].split(" from ", 1)[0].strip()
                result.imports.append(ParseImport(module_path=module_path, import_kind="namespace", imported_name="*", local_name=local_name, line=self.line_number(node)))
            elif "{" in clause:
                binding_text = clause.split("{", 1)[1].split("}", 1)[0]
                for part in binding_text.split(","):
                    raw = part.strip()
                    if not raw:
                        continue
                    if " as " in raw:
                        imported_name, local_name = [item.strip() for item in raw.split(" as ", 1)]
                    else:
                        imported_name, local_name = raw, raw
                    result.imports.append(ParseImport(module_path=module_path, import_kind="named", imported_name=imported_name, local_name=local_name, line=self.line_number(node)))
            else:
                local_name = clause.replace("import", "", 1).split("from", 1)[0].strip()
                result.imports.append(ParseImport(module_path=module_path, import_kind="default", imported_name="default", local_name=local_name, line=self.line_number(node)))

        if node.type == "call_expression" and parents:
            function_node = node.child_by_field_name("function")
            if function_node is not None:
                text = self.node_text(function_node, content)
                if "." in text:
                    qualifier, callee_name = text.rsplit(".", 1)
                else:
                    qualifier, callee_name = "", text
                result.call_sites.append(ParseCallSite(
                    source_entity_local_id=parents[-1],
                    callee_name=callee_name,
                    callee_qualifier=qualifier,
                    line=self.line_number(node),
                ))

        for child in node.named_children:
            self._walk(child, file_path, content, result, parents)
```

```python
# src/codeviz/parsing/languages/typescript.py
from __future__ import annotations

from tree_sitter import Parser
from tree_sitter_typescript import language_tsx, language_typescript

from codeviz.parsing.languages.javascript import JavaScriptParser


class TypeScriptParser(JavaScriptParser):
    def __init__(self) -> None:
        super().__init__()
        self._parser = Parser()
        self._parser.language = language_typescript()


class TsxParser(JavaScriptParser):
    def __init__(self) -> None:
        super().__init__()
        self._parser = Parser()
        self._parser.language = language_tsx()
```

```python
# src/codeviz/parsing/registry.py
from codeviz.parsing.languages.javascript import JavaScriptParser
from codeviz.parsing.languages.typescript import TsxParser, TypeScriptParser

register_parser("javascript", JavaScriptParser())
register_parser("javascriptreact", JavaScriptParser())
register_parser("typescript", TypeScriptParser())
register_parser("typescriptreact", TsxParser())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ast_parsing.py -k "typescript_parser or javascript_parser" -v`

Expected: PASS for the JavaScript and TypeScript parser coverage.

- [ ] **Step 5: Commit**

```bash
git add src/codeviz/parsing/languages/javascript.py src/codeviz/parsing/languages/typescript.py src/codeviz/parsing/registry.py tests/test_ast_parsing.py
git commit -m "feat: add javascript and typescript ast parsers"
```

### Task 4: Deterministic AST Resolution

**Files:**
- Create: `src/codeviz/resolution/__init__.py`
- Create: `src/codeviz/resolution/deterministic.py`
- Create: `tests/test_ast_resolution.py`
- Modify: `tests/test_import_resolution.py`

- [ ] **Step 1: Write the failing deterministic resolution tests**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ast_resolution.py tests/test_import_resolution.py -v`

Expected: FAIL because the deterministic resolver module does not exist and the import resolution tests still import helpers from `analysis.py`.

- [ ] **Step 3: Write the minimal deterministic resolver**

```python
# src/codeviz/resolution/deterministic.py
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from codeviz.models import EdgeRecord, EntityRecord


@dataclass(slots=True)
class UnresolvedRelation:
    source_id: str
    edge_type: str
    target_name: str
    file_path: str
    line: int
    qualifier: str = ""
    candidate_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ResolvedFileResult:
    entities: list[EntityRecord]
    edges: list[EdgeRecord]
    unresolved: list[UnresolvedRelation]
    import_entities: list[dict]


_ALIAS_PREFIXES = ("@/", "~/", "~", "src/", "lib/", "app/", "components/", "utils/", "pages/")
_SOURCE_EXTENSIONS = (".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")


def _resolve_import_url(url: str, importing_file: str, known_files: set[str]) -> str | None:
    if not url:
        return None
    if "." in url and "/" not in url and not url.startswith("."):
        dotted_path = url.replace(".", "/")
        for ext in _SOURCE_EXTENSIONS:
            candidate = dotted_path + ext
            if candidate in known_files:
                return candidate
    if url.startswith("."):
        base = Path(importing_file).parent / url
        base_str = base.as_posix().lstrip("/")
        for candidate in [base_str] + [base_str + ext for ext in _SOURCE_EXTENSIONS]:
            if candidate in known_files:
                return candidate
    stem = Path(url.split("/")[-1]).stem
    if not stem:
        return None
    matches = [item for item in known_files if Path(item).stem == stem]
    return matches[0] if len(matches) == 1 else None


def _build_cross_file_edges(
    pending_imports: dict[str, list[tuple[str, str, str]]],
    file_entity_index: dict[str, dict[str, str]],
    resolved_files: set[str],
) -> list[EdgeRecord]:
    new_edges: list[EdgeRecord] = []
    for target_file in [item for item in list(pending_imports.keys()) if item in resolved_files]:
        target_index = file_entity_index.get(target_file, {})
        remaining: list[tuple[str, str, str]] = []
        for source_id, name, importing_file in pending_imports[target_file]:
            target_id = target_index.get(name)
            if target_id:
                new_edges.append(EdgeRecord(
                    edge_id=f"imports:{source_id}->{target_id}",
                    source_id=source_id,
                    target_id=target_id,
                    edge_type="imports",
                    file_path=importing_file,
                    line=0,
                    description=f"imported from {target_file}",
                ))
            else:
                remaining.append((source_id, name, importing_file))
        if remaining:
            pending_imports[target_file] = remaining
        else:
            del pending_imports[target_file]
    return new_edges


def resolve_file(
    file_path: str,
    language: str,
    parse_result,
    known_files: set[str],
    file_entity_index: dict[str, dict[str, str]],
    pending_imports: dict[str, list[tuple[str, str, str]]],
) -> ResolvedFileResult:
    entities: list[EntityRecord] = []
    edges: list[EdgeRecord] = []
    unresolved: list[UnresolvedRelation] = []
    entity_ids_by_local: dict[str, str] = {}
    entity_ids_by_name: dict[str, list[str]] = {}

    for parsed in parse_result.entities:
        entity = EntityRecord(
            entity_id=f"{parsed.kind}:{file_path}:{parsed.name}:{parsed.start_line}",
            entity_type=parsed.kind,
            name=parsed.name,
            file_path=file_path,
            start_line=parsed.start_line,
            end_line=parsed.end_line,
            signature=parsed.signature,
            parent_id="",
            language=language,
        )
        entities.append(entity)
        entity_ids_by_local[parsed.local_id] = entity.entity_id
        entity_ids_by_name.setdefault(parsed.name, []).append(entity.entity_id)

    for parsed in parse_result.entities:
        if not parsed.parent_local_id:
            continue
        parent_id = entity_ids_by_local.get(parsed.parent_local_id)
        child_id = entity_ids_by_local.get(parsed.local_id)
        if parent_id and child_id:
            edges.append(EdgeRecord(
                edge_id=f"defines:{parent_id}->{child_id}:{parsed.start_line}",
                source_id=parent_id,
                target_id=child_id,
                edge_type="defines",
                file_path=file_path,
                line=parsed.start_line,
                description="parent defines child entity",
            ))

    for call in parse_result.call_sites:
        source_id = entity_ids_by_local.get(call.source_entity_local_id, f"unresolved:{file_path}:{call.source_entity_local_id}")
        candidates = entity_ids_by_name.get(call.callee_name, [])
        if len(candidates) == 1:
            target_id = candidates[0]
            edges.append(EdgeRecord(
                edge_id=f"calls:{source_id}->{target_id}:{call.line}",
                source_id=source_id,
                target_id=target_id,
                edge_type="calls",
                file_path=file_path,
                line=call.line,
                description="direct call",
            ))
        else:
            unresolved.append(UnresolvedRelation(
                source_id=source_id,
                edge_type="calls",
                target_name=call.callee_name,
                file_path=file_path,
                line=call.line,
                qualifier=call.callee_qualifier,
                candidate_ids=candidates,
            ))

    for reference in parse_result.references:
        source_id = entity_ids_by_local.get(reference.source_entity_local_id, f"unresolved:{file_path}:{reference.source_entity_local_id}")
        candidates = entity_ids_by_name.get(reference.name, [])
        if len(candidates) == 1:
            target_id = candidates[0]
            edges.append(EdgeRecord(
                edge_id=f"uses:{source_id}->{target_id}:{reference.line}",
                source_id=source_id,
                target_id=target_id,
                edge_type="uses",
                file_path=file_path,
                line=reference.line,
                description=f"{reference.reference_kind} reference",
            ))

    import_entities: list[dict] = []
    for item in parse_result.imports:
        import_entities.append({"url": item.module_path, "names": [item.local_name]})
        target_file = _resolve_import_url(item.module_path, file_path, known_files)
        if not target_file:
            continue
        source_id = entities[0].entity_id if entities else f"unresolved:{file_path}:{item.local_name}"
        if target_file in file_entity_index and item.imported_name in file_entity_index[target_file]:
            target_id = file_entity_index[target_file][item.imported_name]
            edges.append(EdgeRecord(
                edge_id=f"imports:{source_id}->{target_id}",
                source_id=source_id,
                target_id=target_id,
                edge_type="imports",
                file_path=file_path,
                line=item.line,
                description=f"imported from {target_file}",
            ))
        else:
            pending_imports.setdefault(target_file, []).append((source_id, item.imported_name, file_path))

    return ResolvedFileResult(entities=entities, edges=edges, unresolved=unresolved, import_entities=import_entities)
```

```python
# src/codeviz/resolution/__init__.py
from codeviz.resolution.deterministic import ResolvedFileResult, UnresolvedRelation, resolve_file

__all__ = ["ResolvedFileResult", "UnresolvedRelation", "resolve_file"]
```

```python
# tests/test_import_resolution.py
from codeviz.resolution.deterministic import _build_cross_file_edges, _resolve_import_url
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ast_resolution.py tests/test_import_resolution.py -v`

Expected: PASS for the deterministic resolver and moved import resolution helpers.

- [ ] **Step 5: Commit**

```bash
git add src/codeviz/resolution/__init__.py src/codeviz/resolution/deterministic.py tests/test_ast_resolution.py tests/test_import_resolution.py
git commit -m "feat: add deterministic ast resolution"
```

### Task 5: AST-First Analysis Integration And Unresolved Fallback

**Files:**
- Create: `src/codeviz/resolution/fallback.py`
- Modify: `src/codeviz/analysis.py`
- Modify: `src/codeviz/extractor.py`
- Modify: `README.md`
- Modify: `tests/test_ast_resolution.py`
- Modify: `tests/test_project_integration.py`

- [ ] **Step 1: Write the failing integration and fallback tests**

```python
from codeviz.models import ProjectInfo
from codeviz.project import CodeVizProject


def test_analyze_ast_mode_writes_entities_without_llm_file_extraction(fixture_project, monkeypatch) -> None:
    monkeypatch.setattr(
        "codeviz.analysis.extract_project_info",
        lambda root, documents, extractor: ProjectInfo(name=root.name, root=str(root)),
    )
    monkeypatch.setattr(
        "codeviz.extractor.LLMExtractor.extract_file",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("llm file extraction should not run")),
    )

    project = CodeVizProject(fixture_project)
    project.config = {"extractorMode": "ast", "fallbackMode": "off"}

    result = project.analyze()
    payload = project.graph_api_payload()

    assert result["ok"] is True
    assert len(payload["entities"]) >= 1
    assert any(entity["name"] == "runService" for entity in payload["entities"])


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ast_resolution.py tests/test_project_integration.py -k "ast_mode or unresolved_relations" -v`

Expected: FAIL because `analysis.py` still calls the per-file LLM extractor and no unresolved fallback module exists.

- [ ] **Step 3: Wire AST extraction into the analysis pipeline and add unresolved fallback**

```python
# src/codeviz/extractor.py
class LLMExtractor:
    ...

    def invoke_json(self, system_prompt: str, user_prompt: str, schema: dict, default: dict) -> dict:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return self._invoke_structured(schema, messages, default)
```

```python
# src/codeviz/resolution/fallback.py
from __future__ import annotations

from codeviz.models import EdgeRecord


FALLBACK_SCHEMA = {
    "title": "FallbackResolution",
    "type": "object",
    "properties": {
        "edges": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source_id": {"type": "string"},
                    "target_id": {"type": "string"},
                    "type": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["source_id", "target_id", "type"],
            },
        },
    },
    "required": ["edges"],
}


def resolve_unresolved_relations(unresolved: list, all_entities: list, extractor, mode: str) -> list[EdgeRecord]:
    if mode == "off":
        return []

    eligible = [
        item for item in unresolved
        if item.edge_type in {"calls", "imports", "extends", "implements"} and item.candidate_ids
    ]
    if not eligible:
        return []

    candidate_lines = []
    for item in eligible:
        candidate_lines.append(
            f"{item.source_id} --{item.edge_type}--> {item.target_name} | candidates={','.join(item.candidate_ids)}"
        )
    manifest = "\n".join(f"{entity.entity_id} | {entity.name} | {entity.file_path}" for entity in all_entities)
    prompt = (
        "Resolve each unresolved relation to one candidate target or return no edge.\n\n"
        f"Entities:\n{manifest}\n\n"
        f"Unresolved:\n{'\n'.join(candidate_lines)}"
    )
    parsed = extractor.invoke_json(
        "You resolve uncertain code relationships. Choose only from the provided candidate ids.",
        prompt,
        FALLBACK_SCHEMA,
        {"edges": []},
    )
    entity_ids = {entity.entity_id for entity in all_entities}
    resolved: list[EdgeRecord] = []
    for raw in parsed.get("edges", []):
        if raw["source_id"] in entity_ids or raw["source_id"].startswith("function:") or raw["source_id"].startswith("method:"):
            if raw["target_id"] in entity_ids:
                resolved.append(EdgeRecord(
                    edge_id=f"xref:{raw['source_id']}->{raw['target_id']}",
                    source_id=raw["source_id"],
                    target_id=raw["target_id"],
                    edge_type=raw["type"],
                    description=raw.get("description", ""),
                ))
    return resolved
```

```python
# src/codeviz/analysis.py
from codeviz.parsing import ASTExtractor
from codeviz.resolution.deterministic import _build_cross_file_edges, resolve_file
from codeviz.resolution.fallback import resolve_unresolved_relations
from codeviz.runtime_config import extractor_mode, fallback_mode


def analyze_project(root: Path, status: ProjectStatus, config: dict | None = None, emit: Callable[[str, dict], None] | None = None) -> AnalysisMeta:
    ...
    mode = extractor_mode(config or {})
    fallback = fallback_mode(config or {})
    ast_extractor = ASTExtractor()
    llm_extractor = LLMExtractor(config)
    all_unresolved = []

    for file_rec in file_records:
        ...
        if mode == "llm":
            result = llm_extractor.extract_file(file_path, content, file_rec.language)
            new_entities = result["entities"]
            new_edges = result["edges"]
            import_entities = result.get("import_entities", [])
        else:
            parse_result = ast_extractor.extract_file(file_path, content, file_rec.language)
            resolved = resolve_file(
                file_path=file_path,
                language=file_rec.language,
                parse_result=parse_result,
                known_files=known_files,
                file_entity_index=file_entity_index,
                pending_imports=pending_imports,
            )
            new_entities = resolved.entities
            new_edges = resolved.edges
            import_entities = resolved.import_entities
            all_unresolved.extend(resolved.unresolved)
        ...

    if mode != "llm":
        xref_edges = resolve_unresolved_relations(all_unresolved, all_entities, llm_extractor, fallback)
        if xref_edges:
            all_edges.extend(xref_edges)
            append_edges(vs, xref_edges)
```

````markdown
<!-- README.md -->
Common config fields:

- `provider`
- `model`
- `apiKey`
- `apiKeyEnv`
- `baseUrl`
- `port`
- `extractorMode`
- `fallbackMode`

Example project config:

```json
{
  "provider": "openai",
  "model": "gpt-4o-mini",
  "extractorMode": "hybrid",
  "fallbackMode": "auto"
}
```

Extraction modes:

- `llm`: keep the legacy per-file LLM extractor
- `ast`: use AST-only extraction, no per-file LLM extraction
- `hybrid`: AST-first plus unresolved-only LLM fallback
````

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ast_parsing.py tests/test_ast_resolution.py tests/test_import_resolution.py tests/test_runtime_config.py tests/test_project_integration.py -v`

Expected: PASS for AST parsing, deterministic resolution, import resolution, runtime config, and project integration coverage. The project integration run should confirm `extractorMode=ast` produces graph entities without calling `LLMExtractor.extract_file()`.

- [ ] **Step 5: Commit**

```bash
git add src/codeviz/resolution/fallback.py src/codeviz/analysis.py src/codeviz/extractor.py README.md tests/test_ast_resolution.py tests/test_project_integration.py
git commit -m "feat: switch analysis to ast-first extraction"
```
