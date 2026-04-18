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
