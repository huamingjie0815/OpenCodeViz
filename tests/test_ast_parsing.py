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
