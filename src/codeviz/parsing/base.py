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
