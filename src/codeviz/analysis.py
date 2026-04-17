from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

from codeviz.extractor import LLMExtractor
from codeviz.fingerprint import compute_fingerprint, detect_language, iter_source_files
from codeviz.models import (
    AnalysisMeta,
    DocumentRecord,
    EdgeRecord,
    EntityRecord,
    FileRecord,
    ProjectInfo,
    ProjectStatus,
)
from codeviz.storage import (
    append_edges,
    append_entities,
    append_event,
    clear_events,
    create_version_dir,
    load_entities,
    load_edges,
    save_documents,
    save_edges,
    save_entities,
    save_files,
    save_meta,
    save_project_info,
    set_current_version,
)


def _build_file_entity_index(
    entities: list[EntityRecord],
) -> dict[str, dict[str, str]]:
    """Build {file_path: {entity_name: entity_id}} index.

    When multiple entities share a name in the same file, the first one wins.
    """
    index: dict[str, dict[str, str]] = {}
    for e in entities:
        file_map = index.setdefault(e.file_path, {})
        if e.name not in file_map:
            file_map[e.name] = e.entity_id
    return index




_ALIAS_PREFIXES = ("@/", "~/", "~", "src/", "lib/", "app/", "components/", "utils/", "pages/")
_SOURCE_EXTENSIONS = (".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")


def _resolve_import_url(
    url: str,
    importing_file: str,
    known_files: set[str],
) -> str | None:
    """Resolve an import url to a known file path using multi-tier fuzzy matching.

    Strategy 0: Python dotted module path (codeviz.models -> codeviz/models.py)
    Strategy 1: relative path exact resolution (./foo, ../bar)
    Strategy 2: filename stem fuzzy match (aliases, bare names)
    Strategy 3: longest common suffix disambiguation (multiple stem matches)
    """
    if not url:
        return None

    # Strategy 0: Python dotted module path
    # Detect: contains dots, no slashes, and not a relative path
    if "." in url and "/" not in url and not url.startswith("."):
        # Convert dots to path separators: codeviz.models -> codeviz/models
        dotted_path = url.replace(".", "/")
        # Try with each source extension
        for ext in _SOURCE_EXTENSIONS:
            candidate = dotted_path + ext
            if candidate in known_files:
                return candidate
        # Try matching as a suffix of known file paths (handles src/codeviz/models.py)
        dotted_parts = dotted_path.split("/")
        suffix_matches: list[str] = []
        for f in known_files:
            f_no_ext = Path(f).with_suffix("").as_posix()
            f_parts = f_no_ext.split("/")
            if len(f_parts) >= len(dotted_parts) and f_parts[-len(dotted_parts):] == dotted_parts:
                suffix_matches.append(f)
        if len(suffix_matches) == 1:
            return suffix_matches[0]
        # If multiple matches, prefer shortest path (closest to direct module)
        if suffix_matches:
            suffix_matches.sort(key=len)
            return suffix_matches[0]
        # Also try matching just the last segment as a stem (foo.bar.baz -> baz)
        last_segment = dotted_parts[-1]
        stem_hits = [f for f in known_files if Path(f).stem == last_segment]
        if len(stem_hits) == 1:
            return stem_hits[0]
        # Multiple stem hits: disambiguate with suffix matching
        if len(stem_hits) > 1:
            best: list[tuple[str, int]] = []
            for f in stem_hits:
                f_parts = Path(f).with_suffix("").parts
                count = 0
                for fp, dp in zip(reversed(f_parts), reversed(dotted_parts)):
                    if fp == dp:
                        count += 1
                    else:
                        break
                best.append((f, count))
            best.sort(key=lambda x: -x[1])
            if best[0][1] > 0 and (len(best) == 1 or best[0][1] > best[1][1]):
                return best[0][0]

    # Strategy 1: relative path
    if url.startswith("."):
        base = Path(importing_file).parent / url
        # Normalise to posix without leading slash
        base_str = base.as_posix().lstrip("/")
        candidates = [base_str] + [base_str + ext for ext in _SOURCE_EXTENSIONS]
        for c in candidates:
            if c in known_files:
                return c
        # Also try stripping an existing extension then re-adding (handles ./foo.js -> foo.ts)
        base_no_ext = Path(base_str).with_suffix("").as_posix()
        if base_no_ext != base_str:
            for ext in _SOURCE_EXTENSIONS:
                c = base_no_ext + ext
                if c in known_files:
                    return c

    # Strategy 2: stem match
    # For dotted urls without slashes, use the last dot-segment as the stem
    # (avoids Path treating dots as file extensions: Path("codeviz.models").stem = "codeviz")
    last_segment = url.split("/")[-1]
    if "." in last_segment and "/" not in url:
        stem = last_segment.rsplit(".", 1)[-1]
    else:
        stem = Path(last_segment).stem
    # Skip bare package names: no "/" in url and no "." in stem  -> stdlib/npm package
    if "/" not in url and "." not in stem and "." not in url:
        return None
    if not stem:
        return None

    stem_matches = [f for f in known_files if Path(f).stem == stem]
    if not stem_matches:
        return None
    if len(stem_matches) == 1:
        return stem_matches[0]

    # Strategy 3: longest common suffix disambiguation
    # Strip common alias prefixes from url to get a bare relative path
    bare = url
    for prefix in _ALIAS_PREFIXES:
        if bare.startswith(prefix):
            bare = bare[len(prefix):]
            break
    # Remove leading ./ or ../
    bare = bare.lstrip("./")
    # For dotted module paths, convert dots to path separators for suffix matching
    if "." in bare and "/" not in bare:
        bare = bare.replace(".", "/")
    bare_parts = [p for p in bare.replace("\\", "/").split("/") if p]

    def _common_suffix_len(file_path: str) -> int:
        file_parts = Path(file_path).with_suffix("").parts
        count = 0
        for fp, bp in zip(reversed(file_parts), reversed(bare_parts)):
            if fp == bp:
                count += 1
            else:
                break
        return count

    scored = [(f, _common_suffix_len(f)) for f in stem_matches]
    max_score = max(s for _, s in scored)
    if max_score == 0:
        return None
    best_matches = [f for f, s in scored if s == max_score]
    return best_matches[0] if len(best_matches) == 1 else None


def _build_cross_file_edges(
    pending_imports: dict[str, list[tuple[str, str, str]]],
    file_entity_index: dict[str, dict[str, str]],
    resolved_files: set[str],
) -> list[EdgeRecord]:
    """Build cross-file EdgeRecords from pending_imports where target file is now known.

    pending_imports: {target_file: [(source_entity_id, entity_name, importing_file)]}
    Returns new EdgeRecords and removes resolved items from pending_imports in-place.
    """
    new_edges: list[EdgeRecord] = []
    resolved_targets = [t for t in list(pending_imports.keys()) if t in resolved_files]

    for target_file in resolved_targets:
        target_index = file_entity_index.get(target_file, {})
        remaining: list[tuple[str, str, str]] = []
        for source_id, name, importing_file in pending_imports[target_file]:
            target_id = target_index.get(name)
            if target_id:
                edge_id = f"imports:{source_id}->{target_id}"
                new_edges.append(EdgeRecord(
                    edge_id=edge_id,
                    source_id=source_id,
                    target_id=target_id,
                    edge_type="imports",
                    file_path=importing_file,
                    line=0,
                    description=f"imported from {target_file}",
                ))
            else:
                remaining.append((source_id, name, importing_file))
        if remaining:
            pending_imports[target_file] = remaining
        else:
            del pending_imports[target_file]

    return new_edges


def _dedup_and_resolve(
    entities: list[EntityRecord],
    edges: list[EdgeRecord],
) -> tuple[list[EntityRecord], list[EdgeRecord], dict]:
    """Deduplicate entities and deterministically resolve cross-file edges."""

    # 1. Dedup entities: same (entity_type, file_path, name, start_line) -> keep first
    seen: dict[tuple, EntityRecord] = {}
    id_remap: dict[str, str] = {}  # old_id -> canonical_id

    for e in entities:
        key = (e.entity_type, e.file_path, e.name, e.start_line)
        if key in seen:
            id_remap[e.entity_id] = seen[key].entity_id
        else:
            seen[key] = e

    deduped_entities = list(seen.values())
    removed_count = len(entities) - len(deduped_entities)

    # 2. Build indices for cross-file resolution
    name_index: dict[str, list[str]] = {}
    for e in deduped_entities:
        name_index.setdefault(e.name, []).append(e.entity_id)

    file_entity_index = _build_file_entity_index(deduped_entities)

    # 3. Remap edge references and resolve unresolved targets
    resolved_count = 0
    unresolved_count = 0
    deduped_edges: list[EdgeRecord] = []
    newly_resolved: list[EdgeRecord] = []  # edges that went from unresolved -> resolved
    seen_edge_keys: set[str] = set()

    for edge in edges:
        src = id_remap.get(edge.source_id, edge.source_id)
        tgt = id_remap.get(edge.target_id, edge.target_id)
        src_was_unresolved = src.startswith("unresolved:")
        tgt_was_unresolved = tgt.startswith("unresolved:")

        if src_was_unresolved:
            resolved_src = _resolve_unresolved(
                src, edge.file_path, edge.edge_type, name_index,
                file_entity_index,
            )
            if resolved_src:
                src = resolved_src
                resolved_count += 1

        if tgt_was_unresolved:
            resolved_tgt = _resolve_unresolved(
                tgt, edge.file_path, edge.edge_type, name_index,
                file_entity_index,
            )
            if resolved_tgt:
                tgt = resolved_tgt
                resolved_count += 1

        # Drop edges where either endpoint is still unresolved — they reference
        # stdlib/runtime symbols that are not user-defined entities.
        if src.startswith("unresolved:") or tgt.startswith("unresolved:"):
            unresolved_count += 1
            continue

        # Deduplicate edges by (source, target, type)
        edge_key = (src, tgt, edge.edge_type)
        if edge_key in seen_edge_keys:
            continue
        seen_edge_keys.add(edge_key)

        new_edge_id = f"{edge.edge_type}:{src}->{tgt}"
        resolved_edge = EdgeRecord(
            edge_id=new_edge_id,
            source_id=src,
            target_id=tgt,
            edge_type=edge.edge_type,
            file_path=edge.file_path,
            line=edge.line,
            description=edge.description,
        )
        deduped_edges.append(resolved_edge)
        if src_was_unresolved or tgt_was_unresolved:
            newly_resolved.append(resolved_edge)

    stats = {
        "entities_before": len(entities),
        "entities_after": len(deduped_entities),
        "entities_removed": removed_count,
        "edges_before": len(edges),
        "edges_after": len(deduped_edges),
        "resolved_deterministic": resolved_count,
        "remaining_unresolved": unresolved_count,
        "edges": [e.to_dict() for e in newly_resolved],
    }
    return deduped_entities, deduped_edges, stats


def _resolve_unresolved(
    unresolved_id: str,
    source_file: str,
    edge_type: str,
    name_index: dict[str, list[str]],
    file_entity_index: dict[str, dict[str, str]],
) -> str | None:
    """Resolve an 'unresolved:file:name' id to an actual entity_id.

    Resolution strategies (in order):
    1. Same-file lookup: entity with this name in the same file
    2. Global unique lookup: if only one entity with this name exists across all files
    3. Cross-file preference: among multiple candidates, prefer those not in the same file
    """
    parts = unresolved_id.split(":", 2)
    if len(parts) < 3:
        return None
    name = parts[2]

    # Skip built-in / runtime names that are never real entities
    if "." in name:
        # e.g. console.log, process.exit, path.dirname - not user entities
        return None

    # Strategy 1: same-file lookup
    same_file_entities = file_entity_index.get(source_file, {})
    if name in same_file_entities:
        return same_file_entities[name]

    # Strategy 2: global unique name
    candidates = name_index.get(name, [])
    if len(candidates) == 1:
        return candidates[0]

    # Strategy 3: for multiple candidates, prefer cross-file (not same file)
    if len(candidates) > 1:
        cross_file = [c for c in candidates if source_file not in c]
        if len(cross_file) == 1:
            return cross_file[0]

    return None


def analyze_project(
    root: Path,
    status: ProjectStatus,
    config: dict,
    event_cb: Callable[[dict], None] | None = None,
) -> AnalysisMeta:
    started_at = datetime.now(UTC)
    run_id = started_at.strftime("%Y%m%dT%H%M%SZ")
    fingerprint = compute_fingerprint(root)

    # Create a versioned directory and a scoped status for this run
    version_dir = create_version_dir(status, run_id)
    vs = ProjectStatus(
        root=status.root,
        codeviz_dir=status.codeviz_dir,
        current_dir=version_dir,
        chat_dir=status.chat_dir,
        versions_dir=status.versions_dir,
    )

    meta = AnalysisMeta(
        run_id=run_id,
        fingerprint=fingerprint,
        status="analyzing",
        started_at=started_at.isoformat(),
    )
    save_meta(vs, meta)
    clear_events(vs)
    save_entities(vs, [])
    save_edges(vs, [])

    # Also update the caller's status so the server can stream partial data
    set_current_version(status, run_id)

    def emit(event_type: str, payload: dict | None = None) -> None:
        event = {"event_type": event_type, "payload": payload or {}}
        append_event(vs, event)
        if event_cb:
            event_cb(event)

    emit("analysis.started", {"run_id": run_id, "root": str(root)})

    # 1. Discover files
    source_files = iter_source_files(root)
    file_records: list[FileRecord] = []
    for path in source_files:
        rel = path.relative_to(root).as_posix()
        lang = detect_language(path)
        try:
            content = path.read_bytes()
            chash = hashlib.sha256(content).hexdigest()
            size = len(content)
        except OSError:
            chash = ""
            size = 0
        file_records.append(FileRecord(path=rel, language=lang, content_hash=chash, size=size))

    save_files(vs, file_records)
    emit("files.discovered", {"count": len(file_records), "files": [f.path for f in file_records]})
    meta.file_count = len(file_records)
    save_meta(vs, meta)

    # 2. Collect markdown documents
    documents = collect_documents(root)
    save_documents(vs, documents)
    meta.doc_count = len(documents)
    emit("docs.collected", {"count": len(documents)})

    # 3. Per-file LLM extraction
    extractor = LLMExtractor(config)
    all_entities: list[EntityRecord] = []
    all_edges: list[EdgeRecord] = []

    # Incremental cross-file import resolution state
    # {file_path: {entity_name: entity_id}} — grows as each file is parsed
    file_entity_index: dict[str, dict[str, str]] = {}
    # {target_file: [(source_entity_id, entity_name, importing_file)]} — pending matches
    pending_imports: dict[str, list[tuple[str, str, str]]] = {}
    known_files: set[str] = {fr.path for fr in file_records}

    for file_rec in file_records:
        file_path = file_rec.path
        emit("file.extracting", {"file": file_path, "language": file_rec.language})

        try:
            full_path = root / file_path
            content = full_path.read_text(encoding="utf-8", errors="replace")
            # Skip very large files (>50KB) to avoid token limits
            if len(content) > 50_000:
                emit("file.skipped", {"file": file_path, "reason": "too large"})
                continue

            result = extractor.extract_file(file_path, content, file_rec.language)
            new_entities = result["entities"]
            new_edges = result["edges"]
            import_entities = result.get("import_entities", [])

            all_entities.extend(new_entities)
            all_edges.extend(new_edges)

            # Update entity index with this file's entities (first definition wins)
            file_index = file_entity_index.setdefault(file_path, {})
            for e in new_entities:
                if e.name not in file_index:
                    file_index[e.name] = e.entity_id

            # Pick a representative source entity for file-level import edges:
            # prefer the first non-method entity, fall back to any entity
            source_entity_id = ""
            for e in new_entities:
                if e.entity_type != "method":
                    source_entity_id = e.entity_id
                    break
            if not source_entity_id and new_entities:
                source_entity_id = new_entities[0].entity_id

            # Build a lookup: imported name -> set of entity_ids that reference it
            # (entities in this file that call/use the imported name)
            callers_of: dict[str, list[str]] = {}
            for e in new_edges:
                # target_id for unresolved cross-file refs looks like "unresolved:file:name"
                tgt = e.target_id
                if tgt.startswith(f"unresolved:{file_path}:"):
                    ref_name = tgt.split(":", 2)[2]
                    # Ignore dotted built-in names (e.g. console.error)
                    if "." not in ref_name:
                        callers_of.setdefault(ref_name, []).append(e.source_id)

            # Process import_entities: resolve url -> target file and match names
            import_cross_edges: list[EdgeRecord] = []
            for imp in import_entities:
                url = imp.get("url", "")
                names = imp.get("names", [])
                if not url or not names:
                    continue

                target_file = _resolve_import_url(url, file_path, known_files)
                if not target_file:
                    continue

                for name in names:
                    if not name:
                        continue
                    # Prefer callers of this name as source; fall back to file representative
                    callers = callers_of.get(name, [])
                    src_ids = callers if callers else (
                        [source_entity_id] if source_entity_id else [f"unresolved:{file_path}:{name}"]
                    )
                    if target_file in file_entity_index:
                        # Target already parsed — resolve immediately
                        target_id = file_entity_index[target_file].get(name)
                        if target_id:
                            for src_id in src_ids:
                                edge_id = f"imports:{src_id}->{target_id}"
                                import_cross_edges.append(EdgeRecord(
                                    edge_id=edge_id,
                                    source_id=src_id,
                                    target_id=target_id,
                                    edge_type="imports",
                                    file_path=file_path,
                                    line=0,
                                    description=f"imported from {target_file}",
                                ))
                    else:
                        # Target not yet parsed — queue for later
                        for src_id in src_ids:
                            pending_imports.setdefault(target_file, []).append(
                                (src_id, name, file_path)
                            )

            # Reverse check: flush any pending imports waiting for THIS file
            resolved_now = _build_cross_file_edges(
                pending_imports, file_entity_index, {file_path}
            )
            import_cross_edges.extend(resolved_now)

            all_edges.extend(import_cross_edges)

            all_edges_for_file = new_edges + import_cross_edges
            append_entities(vs, new_entities)
            append_edges(vs, all_edges_for_file)

            emit("file.extracted", {
                "file": file_path,
                "entities": [e.to_dict() for e in new_entities],
                "edges": [e.to_dict() for e in all_edges_for_file],
                "import_entities": import_entities,
                "entity_count": len(new_entities),
                "edge_count": len(all_edges_for_file),
                "import_edge_count": len(import_cross_edges),
            })
        except Exception as exc:
            emit("file.error", {"file": file_path, "error": str(exc)})

    # Flush any remaining pending imports (target files were skipped or not found)
    if pending_imports:
        leftover_edges = _build_cross_file_edges(
            pending_imports, file_entity_index, set(file_entity_index.keys())
        )
        if leftover_edges:
            all_edges.extend(leftover_edges)
            append_edges(vs, leftover_edges)
            emit("relations.import_flush", {
                "resolved": len(leftover_edges),
                "still_pending": sum(len(v) for v in pending_imports.values()),
            })

    meta.entity_count = len(all_entities)
    meta.edge_count = len(all_edges)
    save_meta(vs, meta)

    # 3b. Deduplicate entities and resolve deterministic cross-file edges
    all_entities, all_edges, dedup_stats = _dedup_and_resolve(all_entities, all_edges)
    save_entities(vs, all_entities)
    save_edges(vs, all_edges)
    meta.entity_count = len(all_entities)
    meta.edge_count = len(all_edges)
    save_meta(vs, meta)
    emit("entities.deduped", dedup_stats)

    # 4. Cross-file relation resolution (LLM fallback for remaining unresolved)
    # Note: after _dedup_and_resolve, all_edges no longer contains unresolved edges.
    # The LLM fallback is now a no-op for clean runs but kept for future extensibility.
    xref_edges: list[EdgeRecord] = []
    try:
        xref_edges = extractor.resolve_cross_file_relations(all_entities, all_edges)
        if xref_edges:
            all_edges.extend(xref_edges)
            append_edges(vs, xref_edges)
            meta.edge_count = len(all_edges)
            save_meta(vs, meta)
    except Exception as exc:
        emit("relations.error", {"error": str(exc)})
    emit("relations.resolved", {
        "new_edges": len(xref_edges),
        "edges": [e.to_dict() for e in xref_edges],
    })

    # 5. Generate project summary
    emit("project.summarizing", {})
    try:
        project_info = extract_project_info(root, documents, extractor)
        save_project_info(vs, project_info)
        emit("project.summarized", {"name": project_info.name})
    except Exception as exc:
        emit("project.summary_error", {"error": str(exc)})
        save_project_info(vs, ProjectInfo(name=root.name, root=str(root)))

    # 6. Finalize
    finished_at = datetime.now(UTC)
    meta.status = "completed"
    meta.finished_at = finished_at.isoformat()
    meta.entity_count = len(all_entities)
    meta.edge_count = len(all_edges)
    save_meta(vs, meta)
    emit("analysis.completed", {
        "files": meta.file_count,
        "entities": meta.entity_count,
        "edges": meta.edge_count,
        "docs": meta.doc_count,
    })

    return meta


def extract_project_info(
    root: Path,
    documents: list[DocumentRecord],
    extractor: LLMExtractor,
) -> ProjectInfo:
    readme_content = ""
    spec_content = ""
    for doc in documents:
        lower = doc.file_path.lower()
        if "readme" in lower and not readme_content:
            path = root / doc.file_path
            if path.exists():
                readme_content = path.read_text(encoding="utf-8", errors="replace")[:4000]
        elif any(k in lower for k in ("spec", "architecture", "design")) and not spec_content:
            path = root / doc.file_path
            if path.exists():
                spec_content = path.read_text(encoding="utf-8", errors="replace")[:4000]

    prompt = (
        f"Project directory: {root.name}\n\n"
        f"README content:\n{readme_content[:3000] if readme_content else '(no README found)'}\n\n"
        f"Spec/Architecture content:\n{spec_content[:2000] if spec_content else '(none found)'}\n\n"
        "Output JSON:\n"
        '{\n'
        '  "name": "project name",\n'
        '  "description": "one paragraph project description",\n'
        '  "languages": ["primary languages used"],\n'
        '  "readme_summary": "key points from README",\n'
        '  "spec_summary": "key points from specs/architecture docs",\n'
        '  "key_files": ["important file paths"]\n'
        '}\n'
        "Output valid JSON only."
    )
    messages = [
        {"role": "system", "content": "You are a project analyst. Summarize the project based on its documentation. Output ONLY valid JSON."},
        {"role": "user", "content": prompt},
    ]
    from codeviz.extractor import _parse_llm_json
    response = extractor.llm.invoke(messages)
    text = response.content if hasattr(response, "content") else str(response)
    data = _parse_llm_json(text)

    return ProjectInfo(
        name=data.get("name", root.name),
        root=str(root),
        description=data.get("description", ""),
        languages=data.get("languages", []),
        readme_summary=data.get("readme_summary", ""),
        spec_summary=data.get("spec_summary", ""),
        key_files=data.get("key_files", []),
    )


# -- Document collection (kept from original) --------------------------------

DOC_PRIORITY = (
    ("readme", "readme"),
    ("spec", "spec"),
    ("architecture", "architecture"),
    ("design", "design"),
    ("adr", "adr"),
)


def collect_documents(root: Path) -> list[DocumentRecord]:
    documents: list[DocumentRecord] = []
    skip_dirs = {".git", ".codeviz", "node_modules", "dist", "build", "vendor", "__pycache__"}
    for path in root.rglob("*.md"):
        rel = path.relative_to(root).as_posix()
        if any(part in skip_dirs for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if not text.strip():
            continue
        title, heading, excerpt, start_line, end_line, keywords = _doc_summary(path.name, text)
        documents.append(DocumentRecord(
            doc_id=f"doc:{rel}",
            file_path=rel,
            title=title,
            heading=heading,
            excerpt=excerpt,
            content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            start_line=start_line,
            end_line=end_line,
            kind=_doc_kind(rel),
            keywords=keywords,
        ))
    documents.sort(key=lambda item: (_doc_rank(item.file_path), item.file_path))
    return documents


def _doc_summary(name: str, text: str) -> tuple[str, str, str, int, int, list[str]]:
    lines = text.splitlines()
    heading = next((line.lstrip("# ").strip() for line in lines if line.strip().startswith("#")), name)
    best_start = 0
    best_end = min(len(lines), 6)
    for index, line in enumerate(lines):
        if line.strip():
            best_start = index
            best_end = min(len(lines), index + 6)
            break
    excerpt_lines = [line for line in lines[best_start:best_end] if line.strip()]
    excerpt = "\n".join(excerpt_lines)[:800]
    keywords = re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", " ".join(excerpt_lines[:4]))
    return name, heading, excerpt, best_start + 1, max(best_start + 1, best_end), keywords[:16]


def _doc_rank(file_path: str) -> int:
    lowered = file_path.lower()
    if lowered.startswith("docs/"):
        return 0
    for index, (needle, _) in enumerate(DOC_PRIORITY, start=1):
        if needle in lowered:
            return index
    return len(DOC_PRIORITY) + 1


def _doc_kind(file_path: str) -> str:
    lowered = file_path.lower()
    for needle, kind in DOC_PRIORITY:
        if needle in lowered:
            return kind
    if lowered.startswith("docs/"):
        return "docs"
    return "markdown"
