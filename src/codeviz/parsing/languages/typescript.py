from __future__ import annotations

from tree_sitter import Language, Parser
from tree_sitter_typescript import language_tsx, language_typescript

from codeviz.parsing.languages.javascript import JavaScriptParser


class TypeScriptParser(JavaScriptParser):
    def __init__(self) -> None:
        self._parser = Parser()
        self._parser.language = Language(language_typescript())


class TsxParser(JavaScriptParser):
    def __init__(self) -> None:
        self._parser = Parser()
        self._parser.language = Language(language_tsx())
