from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from threading import Lock
from typing import Any

from codeviz.models import (
    AnalysisMeta,
    DocumentRecord,
    EdgeRecord,
    EntityRecord,
    FileRecord,
    ProjectInfo,
    ProjectStatus,
)

_write_lock = Lock()


def _atomic_write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, str(path))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


# -- Layout ------------------------------------------------------------------

def ensure_layout(status: ProjectStatus) -> None:
    for d in (status.versions_dir, status.chat_dir):
        d.mkdir(parents=True, exist_ok=True)
    _migrate_legacy_current(status)
    # Ensure current_dir exists (points into versions/ after migration)
    if status.current_dir.parent == status.versions_dir:
        status.current_dir.mkdir(parents=True, exist_ok=True)


# -- Version management -----------------------------------------------------

def _migrate_legacy_current(status: ProjectStatus) -> None:
    """Migrate old .codeviz/current/ directory into versions/."""
    legacy_dir = status.codeviz_dir / "current"
    pointer_path = status.codeviz_dir / "current.json"
    if not legacy_dir.is_dir() or pointer_path.exists():
        return
    # Read run_id from existing meta.json, fall back to directory mtime
    meta_data = _read_json(legacy_dir / "meta.json")
    if meta_data and meta_data.get("run_id"):
        run_id = meta_data["run_id"]
    else:
        import time
        run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    dest = status.versions_dir / run_id
    if dest.exists():
        return
    shutil.copytree(str(legacy_dir), str(dest))
    _atomic_write(pointer_path, {"run_id": run_id})
    shutil.rmtree(str(legacy_dir), ignore_errors=True)


def create_version_dir(status: ProjectStatus, run_id: str) -> Path:
    version_dir = status.versions_dir / run_id
    version_dir.mkdir(parents=True, exist_ok=True)
    return version_dir


def set_current_version(status: ProjectStatus, run_id: str) -> None:
    pointer_path = status.codeviz_dir / "current.json"
    _atomic_write(pointer_path, {"run_id": run_id})
    status.current_dir = status.versions_dir / run_id


def get_current_version_dir(status: ProjectStatus) -> Path | None:
    pointer_path = status.codeviz_dir / "current.json"
    data = _read_json(pointer_path)
    if data is None or not data.get("run_id"):
        return None
    version_dir = status.versions_dir / data["run_id"]
    if not version_dir.is_dir():
        return None
    return version_dir


def list_versions(status: ProjectStatus) -> list[dict]:
    if not status.versions_dir.is_dir():
        return []
    versions = []
    for entry in sorted(status.versions_dir.iterdir()):
        if not entry.is_dir():
            continue
        meta_data = _read_json(entry / "meta.json")
        if meta_data is None:
            continue
        versions.append(meta_data)
    return versions


def get_version_dir(status: ProjectStatus, run_id: str) -> Path | None:
    version_dir = status.versions_dir / run_id
    if not version_dir.is_dir():
        return None
    return version_dir
# -- Meta --------------------------------------------------------------------

def save_meta(status: ProjectStatus, meta: AnalysisMeta) -> None:
    _atomic_write(status.current_dir / "meta.json", meta.to_dict())


def load_meta(status: ProjectStatus) -> AnalysisMeta | None:
    data = _read_json(status.current_dir / "meta.json")
    if data is None:
        return None
    return AnalysisMeta.from_dict(data)


# -- Project info ------------------------------------------------------------

def save_project_info(status: ProjectStatus, info: ProjectInfo) -> None:
    _atomic_write(status.current_dir / "project_info.json", info.to_dict())


def load_project_info(status: ProjectStatus) -> ProjectInfo | None:
    data = _read_json(status.current_dir / "project_info.json")
    if data is None:
        return None
    return ProjectInfo.from_dict(data)


# -- Files -------------------------------------------------------------------

def save_files(status: ProjectStatus, files: list[FileRecord]) -> None:
    _atomic_write(
        status.current_dir / "files.json",
        [{"path": f.path, "language": f.language, "content_hash": f.content_hash, "size": f.size} for f in files],
    )


def load_files(status: ProjectStatus) -> list[FileRecord]:
    data = _read_json(status.current_dir / "files.json", [])
    return [FileRecord(path=d["path"], language=d["language"], content_hash=d["content_hash"], size=d.get("size", 0)) for d in data]


# -- Entities ----------------------------------------------------------------

def save_entities(status: ProjectStatus, entities: list[EntityRecord]) -> None:
    _atomic_write(status.current_dir / "entities.json", [e.to_dict() for e in entities])


def load_entities(status: ProjectStatus) -> list[EntityRecord]:
    data = _read_json(status.current_dir / "entities.json", [])
    return [EntityRecord.from_dict(d) for d in data]


def append_entities(status: ProjectStatus, entities: list[EntityRecord]) -> None:
    with _write_lock:
        existing = _read_json(status.current_dir / "entities.json", [])
        existing.extend(e.to_dict() for e in entities)
        _atomic_write(status.current_dir / "entities.json", existing)


# -- Edges -------------------------------------------------------------------

def save_edges(status: ProjectStatus, edges: list[EdgeRecord]) -> None:
    _atomic_write(status.current_dir / "edges.json", [e.to_dict() for e in edges])


def load_edges(status: ProjectStatus) -> list[EdgeRecord]:
    data = _read_json(status.current_dir / "edges.json", [])
    return [EdgeRecord.from_dict(d) for d in data]


def append_edges(status: ProjectStatus, edges: list[EdgeRecord]) -> None:
    with _write_lock:
        existing = _read_json(status.current_dir / "edges.json", [])
        existing.extend(e.to_dict() for e in edges)
        _atomic_write(status.current_dir / "edges.json", existing)


# -- Documents ---------------------------------------------------------------

def save_documents(status: ProjectStatus, docs: list[DocumentRecord]) -> None:
    _atomic_write(status.current_dir / "documents.json", [d.to_dict() for d in docs])


def load_documents(status: ProjectStatus) -> list[DocumentRecord]:
    data = _read_json(status.current_dir / "documents.json", [])
    return [DocumentRecord.from_dict(d) for d in data]


# -- Events ------------------------------------------------------------------

def append_event(status: ProjectStatus, event: dict) -> None:
    with _write_lock:
        events = _read_json(status.current_dir / "events.json", [])
        event["event_id"] = len(events) + 1
        events.append(event)
        _atomic_write(status.current_dir / "events.json", events)


def load_events(status: ProjectStatus, after: int = 0) -> list[dict]:
    events = _read_json(status.current_dir / "events.json", [])
    return [e for e in events if e.get("event_id", 0) > after]


def clear_events(status: ProjectStatus) -> None:
    _atomic_write(status.current_dir / "events.json", [])


# -- Graph payload (API) -----------------------------------------------------

def graph_payload(status: ProjectStatus) -> dict:
    entities = load_entities(status)
    edges = load_edges(status)
    docs = load_documents(status)
    return {
        "entities": [e.to_dict() for e in entities],
        "edges": [e.to_dict() for e in edges],
        "documents": [d.to_dict() for d in docs],
    }


def graph_summary(status: ProjectStatus) -> dict:
    meta = load_meta(status)
    if meta is None:
        return {"files": 0, "entities": 0, "edges": 0, "docs": 0}
    return {
        "files": meta.file_count,
        "entities": meta.entity_count,
        "edges": meta.edge_count,
        "docs": meta.doc_count,
    }


# -- Search ------------------------------------------------------------------

def search_entities(status: ProjectStatus, query: str, limit: int = 20) -> list[dict]:
    entities = load_entities(status)
    terms = _search_terms(query)
    if not terms:
        return [e.to_dict() for e in entities[:limit]]
    results = []
    for entity in entities:
        score = _match_score(entity.name, entity.file_path, entity.signature, entity.description, terms)
        if score > 0:
            d = entity.to_dict()
            d["_score"] = score
            results.append(d)
    results.sort(key=lambda x: x["_score"], reverse=True)
    return results[:limit]


def search_documents_by_query(status: ProjectStatus, query: str, limit: int = 10) -> list[dict]:
    docs = load_documents(status)
    terms = _search_terms(query)
    if not terms:
        return [d.to_dict() for d in docs[:limit]]
    results = []
    for doc in docs:
        score = _match_score(doc.title, doc.heading, doc.excerpt, " ".join(doc.keywords), terms)
        if score > 0:
            d = doc.to_dict()
            d["_score"] = score
            results.append(d)
    results.sort(key=lambda x: x["_score"], reverse=True)
    return results[:limit]


def get_entity_neighbors(status: ProjectStatus, entity_id: str) -> dict:
    edges = load_edges(status)
    entities = load_entities(status)
    entity_map = {e.entity_id: e.to_dict() for e in entities}
    outgoing = []
    incoming = []
    for edge in edges:
        if edge.source_id == entity_id:
            target = entity_map.get(edge.target_id)
            outgoing.append({"edge": edge.to_dict(), "target": target})
        elif edge.target_id == entity_id:
            source = entity_map.get(edge.source_id)
            incoming.append({"edge": edge.to_dict(), "source": source})
    entity = entity_map.get(entity_id)
    return {"entity": entity, "outgoing": outgoing, "incoming": incoming}


# -- Chat --------------------------------------------------------------------

def save_chat_turn(status: ProjectStatus, turn: dict) -> None:
    turns_dir = status.chat_dir / "turns"
    turns_dir.mkdir(parents=True, exist_ok=True)
    turn_id = turn["turn_id"]
    _atomic_write(turns_dir / f"{turn_id}.json", turn)

    sessions = _read_json(status.chat_dir / "sessions.json", {"sessions": {}})
    session_id = turn.get("session_id", "project-default")
    session = sessions["sessions"].setdefault(session_id, {"turn_ids": [], "created_at": turn.get("created_at", "")})
    if turn_id not in session["turn_ids"]:
        session["turn_ids"].append(turn_id)
    _atomic_write(status.chat_dir / "sessions.json", sessions)


def load_chat_turn(status: ProjectStatus, turn_id: str) -> dict | None:
    path = status.chat_dir / "turns" / f"{turn_id}.json"
    return _read_json(path)


def load_chat_session(status: ProjectStatus, session_id: str = "project-default") -> list[dict]:
    sessions = _read_json(status.chat_dir / "sessions.json", {"sessions": {}})
    session = sessions["sessions"].get(session_id)
    if not session:
        return []
    turns = []
    for tid in session.get("turn_ids", []):
        turn = load_chat_turn(status, tid)
        if turn:
            turns.append(turn)
    return turns


# -- Internal helpers --------------------------------------------------------

def _search_terms(query: str) -> list[str]:
    words = query.lower().split()
    return [w for w in words if len(w) >= 2]


def _match_score(
    name: str,
    file_path: str,
    sig_or_heading: str,
    extra: str,
    terms: list[str],
) -> float:
    text = f"{name} {file_path} {sig_or_heading} {extra}".lower()
    score = 0.0
    for term in terms:
        if term in name.lower():
            score += 3.0
        elif term in text:
            score += 1.0
    return score
