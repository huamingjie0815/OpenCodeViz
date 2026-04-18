from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from codeviz.models import EdgeRecord, EntityRecord


@dataclass(slots=True)
class UnresolvedRelation:
    source_id: str
    edge_type: str
    target_name: str
    file_path: str
    line: int
    qualifier: str = ""
    candidate_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PendingRelation:
    source_id: str
    edge_type: str
    target_name: str
    file_path: str
    line: int


@dataclass(slots=True)
class ResolvedFileResult:
    entities: list[EntityRecord]
    edges: list[EdgeRecord]
    unresolved: list[UnresolvedRelation]
    import_entities: list[dict]


_ALIAS_PREFIXES = ("@/", "~/", "~", "src/", "lib/", "app/", "components/", "utils/", "pages/")
_SOURCE_EXTENSIONS = (".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")


def _resolve_import_url(
    url: str,
    importing_file: str,
    known_files: set[str],
) -> str | None:
    if not url:
        return None

    if "." in url and "/" not in url and not url.startswith("."):
        dotted_path = url.replace(".", "/")
        for ext in _SOURCE_EXTENSIONS:
            candidate = dotted_path + ext
            if candidate in known_files:
                return candidate
        dotted_parts = dotted_path.split("/")
        suffix_matches: list[str] = []
        for file_path in known_files:
            no_ext = Path(file_path).with_suffix("").as_posix()
            parts = no_ext.split("/")
            if len(parts) >= len(dotted_parts) and parts[-len(dotted_parts):] == dotted_parts:
                suffix_matches.append(file_path)
        if len(suffix_matches) == 1:
            return suffix_matches[0]
        if suffix_matches:
            suffix_matches.sort(key=len)
            return suffix_matches[0]
        last_segment = dotted_parts[-1]
        stem_hits = [file_path for file_path in known_files if Path(file_path).stem == last_segment]
        if len(stem_hits) == 1:
            return stem_hits[0]
        if len(stem_hits) > 1:
            best: list[tuple[str, int]] = []
            for file_path in stem_hits:
                parts = Path(file_path).with_suffix("").parts
                count = 0
                for file_part, dotted_part in zip(reversed(parts), reversed(dotted_parts)):
                    if file_part == dotted_part:
                        count += 1
                    else:
                        break
                best.append((file_path, count))
            best.sort(key=lambda item: -item[1])
            if best[0][1] > 0 and (len(best) == 1 or best[0][1] > best[1][1]):
                return best[0][0]

    if "/" not in url and "." not in url and Path(importing_file).suffix in {".py", ".pyi"}:
        sibling_base = (Path(importing_file).parent / url).as_posix().lstrip("/")
        for ext in (".py", ".pyi"):
            candidate = sibling_base + ext
            if candidate in known_files:
                return candidate

    if url.startswith("."):
        base = Path(importing_file).parent / url
        base_str = base.as_posix().lstrip("/")
        candidates = [base_str] + [base_str + ext for ext in _SOURCE_EXTENSIONS]
        for candidate in candidates:
            if candidate in known_files:
                return candidate
        base_no_ext = Path(base_str).with_suffix("").as_posix()
        if base_no_ext != base_str:
            for ext in _SOURCE_EXTENSIONS:
                candidate = base_no_ext + ext
                if candidate in known_files:
                    return candidate

    last_segment = url.split("/")[-1]
    if "." in last_segment and "/" not in url:
        stem = last_segment.rsplit(".", 1)[-1]
    else:
        stem = Path(last_segment).stem
    if "/" not in url and "." not in stem:
        return None
    if not stem:
        return None

    stem_matches = [file_path for file_path in known_files if Path(file_path).stem == stem]
    if not stem_matches:
        return None
    if len(stem_matches) == 1:
        return stem_matches[0]

    bare = url
    for prefix in _ALIAS_PREFIXES:
        if bare.startswith(prefix):
            bare = bare[len(prefix):]
            break
    bare = bare.lstrip("./")
    if "." in bare and "/" not in bare:
        bare = bare.replace(".", "/")
    bare_parts = [part for part in bare.replace("\\", "/").split("/") if part]

    def _common_suffix_len(file_path: str) -> int:
        file_parts = Path(file_path).with_suffix("").parts
        count = 0
        for file_part, bare_part in zip(reversed(file_parts), reversed(bare_parts)):
            if file_part == bare_part:
                count += 1
            else:
                break
        return count

    scored = [(file_path, _common_suffix_len(file_path)) for file_path in stem_matches]
    max_score = max(score for _, score in scored)
    if max_score == 0:
        return None
    best_matches = [file_path for file_path, score in scored if score == max_score]
    return best_matches[0] if len(best_matches) == 1 else None


def _build_cross_file_edges(
    pending_imports: dict[str, list[tuple[str, str, str]]],
    file_entity_index: dict[str, dict[str, str]],
    resolved_files: set[str],
) -> list[EdgeRecord]:
    new_edges: list[EdgeRecord] = []
    resolved_targets = [target for target in list(pending_imports.keys()) if target in resolved_files]

    for target_file in resolved_targets:
        target_index = file_entity_index.get(target_file, {})
        remaining: list[tuple[str, str, str]] = []
        for source_id, name, importing_file in pending_imports[target_file]:
            target_id = target_index.get(name)
            if target_id:
                new_edges.append(
                    EdgeRecord(
                        edge_id=f"imports:{source_id}->{target_id}",
                        source_id=source_id,
                        target_id=target_id,
                        edge_type="imports",
                        file_path=importing_file,
                        line=0,
                        description=f"imported from {target_file}",
                    )
                )
            else:
                remaining.append((source_id, name, importing_file))
        if remaining:
            pending_imports[target_file] = remaining
        else:
            del pending_imports[target_file]

    return new_edges


def _build_cross_file_relation_edges(
    pending_relations: dict[str, list[PendingRelation]],
    file_entity_index: dict[str, dict[str, str]],
    resolved_files: set[str],
) -> list[EdgeRecord]:
    new_edges: list[EdgeRecord] = []
    resolved_targets = [target for target in list(pending_relations.keys()) if target in resolved_files]

    for target_file in resolved_targets:
        target_index = file_entity_index.get(target_file, {})
        remaining: list[PendingRelation] = []
        for relation in pending_relations[target_file]:
            target_id = target_index.get(relation.target_name)
            if target_id:
                new_edges.append(
                    EdgeRecord(
                        edge_id=f"{relation.edge_type}:{relation.source_id}->{target_id}:{relation.line}",
                        source_id=relation.source_id,
                        target_id=target_id,
                        edge_type=relation.edge_type,
                        file_path=relation.file_path,
                        line=relation.line,
                        description=f"{relation.edge_type} relation",
                    )
                )
            else:
                remaining.append(relation)
        if remaining:
            pending_relations[target_file] = remaining
        else:
            del pending_relations[target_file]

    return new_edges


def _collect_import_sources(parse_result, entity_ids_by_local: dict[str, str]) -> dict[str, list[str]]:
    source_ids_by_name: dict[str, set[str]] = {}

    def add_source(name: str, source_entity_local_id: str) -> None:
        if not name or not source_entity_local_id:
            return
        source_id = entity_ids_by_local.get(source_entity_local_id)
        if not source_id:
            return
        source_ids_by_name.setdefault(name, set()).add(source_id)

    for item in parse_result.imports:
        add_source(item.local_name, item.source_entity_local_id)

    for call in parse_result.call_sites:
        add_source(call.callee_name, call.source_entity_local_id)
        add_source(call.callee_qualifier, call.source_entity_local_id)

    for reference in parse_result.references:
        add_source(reference.name, reference.source_entity_local_id)
        add_source(reference.qualifier, reference.source_entity_local_id)

    for relation in parse_result.inheritance:
        add_source(relation.target_name, relation.source_entity_local_id)

    return {
        name: sorted(source_ids)
        for name, source_ids in source_ids_by_name.items()
    }


def _resolve_imported_call_target(call, imports_by_local: dict[str, tuple[object, str]]) -> tuple[str, str] | None:
    if call.callee_qualifier:
        imported = imports_by_local.get(call.callee_qualifier)
        if imported is None:
            return None
        item, target_file = imported
        if not target_file:
            return None
        if item.import_kind == "namespace" or item.imported_name == item.module_path:
            return target_file, call.callee_name
        return None

    imported = imports_by_local.get(call.callee_name)
    if imported is None:
        return None
    item, target_file = imported
    if not target_file:
        return None
    if item.import_kind == "default":
        return target_file, "default"
    if item.import_kind == "named" and item.imported_name != item.module_path:
        return target_file, item.imported_name
    return None


def resolve_file(
    file_path: str,
    language: str,
    parse_result,
    known_files: set[str],
    file_entity_index: dict[str, dict[str, str]],
    pending_imports: dict[str, list[tuple[str, str, str]]],
    pending_relations: dict[str, list[PendingRelation]] | None = None,
) -> ResolvedFileResult:
    entities: list[EntityRecord] = []
    edges: list[EdgeRecord] = []
    unresolved: list[UnresolvedRelation] = []
    entity_ids_by_local: dict[str, str] = {}
    entity_ids_by_name: dict[str, list[str]] = {}
    pending_relations = pending_relations if pending_relations is not None else {}

    for parsed in parse_result.entities:
        entity = EntityRecord(
            entity_id=f"{parsed.kind}:{file_path}:{parsed.name}:{parsed.start_line}",
            entity_type=parsed.kind,
            name=parsed.name,
            file_path=file_path,
            start_line=parsed.start_line,
            end_line=parsed.end_line,
            signature=parsed.signature,
            parent_id="",
            language=language,
        )
        entities.append(entity)
        entity_ids_by_local[parsed.local_id] = entity.entity_id
        entity_ids_by_name.setdefault(parsed.name, []).append(entity.entity_id)

    current_file_index = file_entity_index.setdefault(file_path, {})
    for parsed in parse_result.entities:
        entity_id = entity_ids_by_local.get(parsed.local_id)
        if entity_id and parsed.name not in current_file_index:
            current_file_index[parsed.name] = entity_id
    for export in parse_result.exports:
        candidates = entity_ids_by_name.get(export.local_name, [])
        if len(candidates) == 1 and export.export_name not in current_file_index:
            current_file_index[export.export_name] = candidates[0]

    for parsed in parse_result.entities:
        if not parsed.parent_local_id:
            continue
        parent_id = entity_ids_by_local.get(parsed.parent_local_id)
        child_id = entity_ids_by_local.get(parsed.local_id)
        if parent_id and child_id:
            edges.append(
                EdgeRecord(
                    edge_id=f"defines:{parent_id}->{child_id}:{parsed.start_line}",
                    source_id=parent_id,
                    target_id=child_id,
                    edge_type="defines",
                    file_path=file_path,
                    line=parsed.start_line,
                    description="parent defines child entity",
                )
            )

    resolved_imports = [
        (item, _resolve_import_url(item.module_path, file_path, known_files))
        for item in parse_result.imports
    ]
    import_sources = _collect_import_sources(parse_result, entity_ids_by_local)
    imports_by_local = {
        item.local_name: (item, target_file)
        for item, target_file in resolved_imports
        if item.local_name
    }
    imported_targets = {
        item.local_name: (target_file, item.imported_name)
        for item, target_file in resolved_imports
        if target_file
    }

    for call in parse_result.call_sites:
        source_id = entity_ids_by_local.get(call.source_entity_local_id, f"unresolved:{file_path}:{call.source_entity_local_id}")
        candidates = entity_ids_by_name.get(call.callee_name, [])
        if len(candidates) == 1:
            edges.append(
                EdgeRecord(
                    edge_id=f"calls:{source_id}->{candidates[0]}:{call.line}",
                    source_id=source_id,
                    target_id=candidates[0],
                    edge_type="calls",
                    file_path=file_path,
                    line=call.line,
                    description="direct call",
                )
            )
            continue

        imported_target = _resolve_imported_call_target(call, imports_by_local)
        if imported_target is not None:
            target_file, target_name = imported_target
            target_id = file_entity_index.get(target_file, {}).get(target_name, "")
            if target_id:
                edges.append(
                    EdgeRecord(
                        edge_id=f"calls:{source_id}->{target_id}:{call.line}",
                        source_id=source_id,
                        target_id=target_id,
                        edge_type="calls",
                        file_path=file_path,
                        line=call.line,
                        description="direct call",
                    )
                )
            else:
                pending_relations.setdefault(target_file, []).append(
                    PendingRelation(
                        source_id=source_id,
                        edge_type="calls",
                        target_name=target_name,
                        file_path=file_path,
                        line=call.line,
                    )
                )
        else:
            unresolved.append(
                UnresolvedRelation(
                    source_id=source_id,
                    edge_type="calls",
                    target_name=call.callee_name,
                    file_path=file_path,
                    line=call.line,
                    qualifier=call.callee_qualifier,
                    candidate_ids=candidates,
                )
            )

    for reference in parse_result.references:
        source_id = entity_ids_by_local.get(reference.source_entity_local_id, f"unresolved:{file_path}:{reference.source_entity_local_id}")
        candidates = entity_ids_by_name.get(reference.name, [])
        if len(candidates) == 1:
            edges.append(
                EdgeRecord(
                    edge_id=f"uses:{source_id}->{candidates[0]}:{reference.line}",
                    source_id=source_id,
                    target_id=candidates[0],
                    edge_type="uses",
                    file_path=file_path,
                    line=reference.line,
                    description=f"{reference.reference_kind} reference",
                )
            )

    for relation in parse_result.inheritance:
        source_id = entity_ids_by_local.get(relation.source_entity_local_id, "")
        candidates = entity_ids_by_name.get(relation.target_name, [])
        if source_id and len(candidates) == 1:
            edges.append(
                EdgeRecord(
                    edge_id=f"{relation.relation_type}:{source_id}->{candidates[0]}:{relation.line}",
                    source_id=source_id,
                    target_id=candidates[0],
                    edge_type=relation.relation_type,
                    file_path=file_path,
                    line=relation.line,
                    description=f"{relation.relation_type} relation",
                )
            )
        elif source_id and relation.target_name in imported_targets:
            target_file, imported_name = imported_targets[relation.target_name]
            target_id = file_entity_index.get(target_file, {}).get(imported_name, "")
            if target_id:
                edges.append(
                    EdgeRecord(
                        edge_id=f"{relation.relation_type}:{source_id}->{target_id}:{relation.line}",
                        source_id=source_id,
                        target_id=target_id,
                        edge_type=relation.relation_type,
                        file_path=file_path,
                        line=relation.line,
                        description=f"{relation.relation_type} relation",
                    )
                )
            else:
                pending_relations.setdefault(target_file, []).append(
                    PendingRelation(
                        source_id=source_id,
                        edge_type=relation.relation_type,
                        target_name=imported_name,
                        file_path=file_path,
                        line=relation.line,
                    )
                )
        elif source_id:
            unresolved.append(
                UnresolvedRelation(
                    source_id=source_id,
                    edge_type=relation.relation_type,
                    target_name=relation.target_name,
                    file_path=file_path,
                    line=relation.line,
                    candidate_ids=candidates,
                )
            )

    import_entities: list[dict] = []
    for item, target_file in resolved_imports:
        import_entities.append({"url": item.module_path, "names": [item.local_name]})
        if not target_file:
            continue
        source_ids = import_sources.get(item.local_name)
        if not source_ids:
            source_ids = [entities[0].entity_id] if entities else [f"unresolved:{file_path}:{item.local_name}"]
        if target_file in file_entity_index and item.imported_name in file_entity_index[target_file]:
            target_id = file_entity_index[target_file][item.imported_name]
            for source_id in source_ids:
                edges.append(
                    EdgeRecord(
                        edge_id=f"imports:{source_id}->{target_id}",
                        source_id=source_id,
                        target_id=target_id,
                        edge_type="imports",
                        file_path=file_path,
                        line=item.line,
                        description=f"imported from {target_file}",
                    )
                )
        else:
            for source_id in source_ids:
                pending_imports.setdefault(target_file, []).append((source_id, item.imported_name, file_path))

    return ResolvedFileResult(
        entities=entities,
        edges=edges,
        unresolved=unresolved,
        import_entities=import_entities,
    )
