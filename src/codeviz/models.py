from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class FileRecord:
    path: str
    language: str
    content_hash: str
    size: int = 0


@dataclass(slots=True)
class EntityRecord:
    entity_id: str
    entity_type: str  # class | function | method | interface | enum | variable | module
    name: str
    file_path: str
    start_line: int
    end_line: int
    signature: str = ""
    description: str = ""
    parent_id: str = ""
    language: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "name": self.name,
            "file_path": self.file_path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "signature": self.signature,
            "description": self.description,
            "parent_id": self.parent_id,
            "language": self.language,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EntityRecord:
        return cls(
            entity_id=data["entity_id"],
            entity_type=data["entity_type"],
            name=data["name"],
            file_path=data["file_path"],
            start_line=data.get("start_line", 0),
            end_line=data.get("end_line", 0),
            signature=data.get("signature", ""),
            description=data.get("description", ""),
            parent_id=data.get("parent_id", ""),
            language=data.get("language", ""),
        )


@dataclass(slots=True)
class EdgeRecord:
    edge_id: str
    source_id: str
    target_id: str
    edge_type: str  # calls | imports | extends | implements | uses | defines
    file_path: str = ""
    line: int = 0
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "edge_type": self.edge_type,
            "file_path": self.file_path,
            "line": self.line,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EdgeRecord:
        return cls(
            edge_id=data["edge_id"],
            source_id=data.get("source_id", data.get("src_entity_id", "")),
            target_id=data.get("target_id", data.get("dst_entity_id", "")),
            edge_type=data["edge_type"],
            file_path=data.get("file_path", ""),
            line=data.get("line", 0),
            description=data.get("description", ""),
        )


@dataclass(slots=True)
class DocumentRecord:
    doc_id: str
    file_path: str
    title: str
    heading: str
    excerpt: str
    content_hash: str
    start_line: int = 1
    end_line: int = 1
    kind: str = "markdown"
    keywords: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "file_path": self.file_path,
            "title": self.title,
            "heading": self.heading,
            "excerpt": self.excerpt,
            "content_hash": self.content_hash,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "kind": self.kind,
            "keywords": self.keywords,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DocumentRecord:
        return cls(
            doc_id=data["doc_id"],
            file_path=data["file_path"],
            title=data.get("title", ""),
            heading=data.get("heading", ""),
            excerpt=data.get("excerpt", ""),
            content_hash=data.get("content_hash", ""),
            start_line=data.get("start_line", 1),
            end_line=data.get("end_line", 1),
            kind=data.get("kind", "markdown"),
            keywords=data.get("keywords", []),
        )


@dataclass(slots=True)
class ProjectInfo:
    name: str
    root: str
    description: str = ""
    languages: list[str] = field(default_factory=list)
    readme_summary: str = ""
    spec_summary: str = ""
    key_files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "root": self.root,
            "description": self.description,
            "languages": self.languages,
            "readme_summary": self.readme_summary,
            "spec_summary": self.spec_summary,
            "key_files": self.key_files,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProjectInfo:
        return cls(
            name=data.get("name", ""),
            root=data.get("root", ""),
            description=data.get("description", ""),
            languages=data.get("languages", []),
            readme_summary=data.get("readme_summary", ""),
            spec_summary=data.get("spec_summary", ""),
            key_files=data.get("key_files", []),
        )


@dataclass(slots=True)
class AnalysisMeta:
    run_id: str
    fingerprint: str
    status: str = "analyzing"  # analyzing | completed | failed
    file_count: int = 0
    entity_count: int = 0
    edge_count: int = 0
    doc_count: int = 0
    started_at: str = ""
    finished_at: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "fingerprint": self.fingerprint,
            "status": self.status,
            "file_count": self.file_count,
            "entity_count": self.entity_count,
            "edge_count": self.edge_count,
            "doc_count": self.doc_count,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AnalysisMeta:
        return cls(
            run_id=data.get("run_id", ""),
            fingerprint=data.get("fingerprint", ""),
            status=data.get("status", "analyzing"),
            file_count=data.get("file_count", 0),
            entity_count=data.get("entity_count", 0),
            edge_count=data.get("edge_count", 0),
            doc_count=data.get("doc_count", 0),
            started_at=data.get("started_at", ""),
            finished_at=data.get("finished_at", ""),
            error=data.get("error", ""),
        )


@dataclass(slots=True)
class ProjectStatus:
    root: Path
    codeviz_dir: Path
    current_dir: Path
    chat_dir: Path
    versions_dir: Path = field(default=Path())

    def __post_init__(self) -> None:
        if self.versions_dir == Path():
            self.versions_dir = self.codeviz_dir / "versions"

    def as_json(self) -> dict[str, str]:
        return {
            "root": str(self.root),
            "codeviz_dir": str(self.codeviz_dir),
            "current_dir": str(self.current_dir),
            "chat_dir": str(self.chat_dir),
            "versions_dir": str(self.versions_dir),
        }
