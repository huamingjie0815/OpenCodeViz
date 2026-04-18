from __future__ import annotations

from codeviz.parsing.base import ParseResult
from codeviz.parsing.registry import get_parser


class ASTExtractor:
    def extract_file(self, file_path: str, content: str, language: str) -> ParseResult:
        parser = get_parser(language)
        if parser is None:
            return ParseResult()
        return parser.parse_file(file_path, content, language)
