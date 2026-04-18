from codeviz.parsing import ASTExtractor, ParseResult, get_parser


def test_ast_extractor_returns_empty_result_for_unknown_language() -> None:
    extractor = ASTExtractor()
    result = extractor.extract_file("README.md", "# hello\n", "unknown")

    assert isinstance(result, ParseResult)
    assert result.entities == []
    assert result.imports == []
    assert result.call_sites == []


def test_registry_is_empty_for_unregistered_language() -> None:
    assert get_parser("unknown") is None


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
        ("method:src/app.py:boot:4", "render", "self"),
        ("function:src/app.py:helper:8", "run", ""),
    ]
    assert [(item.source_entity_local_id, item.target_name, item.relation_type) for item in result.inheritance] == [
        ("class:src/app.py:App:3", "BaseApp", "extends"),
    ]


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
