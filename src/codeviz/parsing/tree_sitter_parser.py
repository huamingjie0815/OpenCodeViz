from __future__ import annotations

from tree_sitter import Language, Node, Parser


class TreeSitterSourceParser:
    def __init__(self, language) -> None:
        self._parser = Parser()
        self._parser.language = Language(language)

    def parse_bytes(self, content: str):
        return self._parser.parse(content.encode("utf-8"))

    def node_text(self, node: Node, content: str) -> str:
        return content.encode("utf-8")[node.start_byte:node.end_byte].decode("utf-8")

    def line_number(self, node: Node) -> int:
        return node.start_point[0] + 1
