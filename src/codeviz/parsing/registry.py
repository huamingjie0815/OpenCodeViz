from __future__ import annotations

from codeviz.parsing.base import SourceParser


_PARSERS: dict[str, SourceParser] = {}


def register_parser(language: str, parser: SourceParser) -> None:
    _PARSERS[language] = parser


def get_parser(language: str) -> SourceParser | None:
    return _PARSERS.get(language)
