from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from codeviz.models import (
    ArchitectureDependency,
    ArchitectureFlow,
    ArchitectureFlowStep,
    ArchitectureModule,
    EdgeRecord,
    EntityRecord,
    FileRecord,
)

_FLOW_EDGE_PRIORITY = {"calls": 0, "imports": 1, "uses": 2}
ARCHITECTURE_SCHEMA_VERSION = 3


@dataclass(slots=True)
class ArchitectureSnapshot:
    modules: list[ArchitectureModule]
    dependencies: list[ArchitectureDependency]
    flow_index: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    meta: dict[str, int] = field(default_factory=dict)


def _module_id_for_file(file_path: str) -> str:
    path = Path(file_path)
    parts = path.parts
    if len(parts) >= 3 and parts[0] == "src":
        package_root = Path(*parts[:2]).as_posix()
        if len(parts) == 3:
            return f"{package_root}/{path.stem}"
        return f"{package_root}/{parts[2]}"
    if len(parts) == 2 and parts[0] in {"lib", "bin", "scripts"}:
        return f"{parts[0]}/{path.stem}"
    parent = path.parent.as_posix()
    if parent and parent != ".":
        return parent
    return path.as_posix()


def _module_display_name(module_id: str) -> str:
    parts = Path(module_id).parts
    return parts[-1] if parts else module_id


def _is_test_path(file_path: str) -> bool:
    parts = Path(file_path).parts
    return bool(parts) and parts[0] == "tests"


def build_architecture_snapshot(
    files: list[FileRecord],
    entities: list[EntityRecord],
    edges: list[EdgeRecord],
) -> ArchitectureSnapshot:
    module_files: dict[str, list[str]] = {}
    module_dirs: dict[str, set[str]] = {}
    module_entities: dict[str, list[str]] = {}

    for file_record in files:
        if _is_test_path(file_record.path):
            continue
        module_id = _module_id_for_file(file_record.path)
        module_files.setdefault(module_id, []).append(file_record.path)
        parent = Path(file_record.path).parent.as_posix()
        if parent and parent != ".":
            module_dirs.setdefault(module_id, set()).add(parent)

    entity_by_id = {entity.entity_id: entity for entity in entities}
    entity_module: dict[str, str] = {}
    for entity in entities:
        if _is_test_path(entity.file_path):
            continue
        module_id = _module_id_for_file(entity.file_path)
        entity_module[entity.entity_id] = module_id
        module_entities.setdefault(module_id, []).append(entity.entity_id)
        module_files.setdefault(module_id, [])
        if entity.file_path not in module_files[module_id]:
            module_files[module_id].append(entity.file_path)
        parent = Path(entity.file_path).parent.as_posix()
        if parent and parent != ".":
            module_dirs.setdefault(module_id, set()).add(parent)

    modules = [
        ArchitectureModule(
            module_id=module_id,
            display_name=_module_display_name(module_id),
            source_dirs=sorted(module_dirs.get(module_id, {module_id})),
            file_paths=sorted(module_files.get(module_id, [])),
            entity_ids=sorted(module_entities.get(module_id, [])),
            merge_reason="directory",
            confidence="high",
        )
        for module_id in sorted(module_files.keys())
    ]

    dependency_counts: dict[tuple[str, str], dict[str, object]] = {}
    for edge in edges:
        source_module_id = entity_module.get(edge.source_id)
        target_entity = entity_by_id.get(edge.target_id)
        target_module_id = entity_module.get(edge.target_id)
        if not source_module_id or not target_module_id or source_module_id == target_module_id:
            continue
        bucket = dependency_counts.setdefault(
            (source_module_id, target_module_id),
            {"imports": 0, "calls": 0, "uses": 0, "evidence": []},
        )
        if edge.edge_type in {"imports", "calls", "uses"}:
            bucket[edge.edge_type] = int(bucket[edge.edge_type]) + 1
        else:
            bucket["uses"] = int(bucket["uses"]) + 1
        evidence = bucket["evidence"]
        if isinstance(evidence, list) and len(evidence) < 5:
            evidence.append(
                {
                    "edge_id": edge.edge_id,
                    "edge_type": edge.edge_type,
                    "source_entity_id": edge.source_id,
                    "target_entity_id": edge.target_id,
                    "source_file": entity_by_id[edge.source_id].file_path,
                    "target_file": target_entity.file_path if target_entity else "",
                }
            )

    dependencies: list[ArchitectureDependency] = []
    for (source_module_id, target_module_id), counts in sorted(dependency_counts.items()):
        type_counts = {
            "imports": int(counts["imports"]),
            "calls": int(counts["calls"]),
            "uses": int(counts["uses"]),
        }
        dominant_edge_type = max(type_counts.items(), key=lambda item: (item[1], -_FLOW_EDGE_PRIORITY.get(item[0], 99)))[0]
        dependencies.append(
            ArchitectureDependency(
                source_module_id=source_module_id,
                target_module_id=target_module_id,
                dominant_edge_type=dominant_edge_type,
                imports_count=type_counts["imports"],
                calls_count=type_counts["calls"],
                uses_count=type_counts["uses"],
                strength=sum(type_counts.values()),
                evidence=list(counts["evidence"]),
            )
        )

    return ArchitectureSnapshot(
        modules=modules,
        dependencies=dependencies,
        flow_index=build_flow_index(files, entities),
        meta={
            "schema_version": ARCHITECTURE_SCHEMA_VERSION,
            "module_count": len(modules),
            "dependency_count": len(dependencies),
        },
    )


def build_flow_index(files: list[FileRecord], entities: list[EntityRecord]) -> dict[str, list[dict[str, str]]]:
    file_entries = [
        {"label": file_record.path, "value": file_record.path}
        for file_record in sorted(files, key=lambda item: item.path)
        if not _is_test_path(file_record.path)
    ]
    entity_entries = [
        {"label": f"{entity.name} ({entity.file_path})", "value": entity.entity_id}
        for entity in sorted(entities, key=lambda item: (item.file_path, item.start_line, item.name))
        if entity.entity_type in {"function", "method", "class"}
        and not _is_test_path(entity.file_path)
    ]
    return {"file": file_entries, "entity": entity_entries}


def _build_flow_outgoing(edges: list[EdgeRecord]) -> dict[str, list[EdgeRecord]]:
    outgoing: dict[str, list[EdgeRecord]] = {}
    for edge in edges:
        if edge.edge_type not in {"calls", "imports", "uses"}:
            continue
        outgoing.setdefault(edge.source_id, []).append(edge)
    return outgoing


def _sorted_flow_edges(edges: list[EdgeRecord]) -> list[EdgeRecord]:
    return sorted(
        edges,
        key=lambda edge: (
            _FLOW_EDGE_PRIORITY.get(edge.edge_type, 99),
            edge.line,
            edge.file_path,
            edge.target_id,
        ),
    )


DEFAULT_FLOW_MAX_DEPTH = 4
DEFAULT_FLOW_MAX_BRANCH = 4
DEFAULT_FLOW_MAX_NODES = 24


def build_flow_payload(
    entry_ref: str,
    entities: list[EntityRecord],
    edges: list[EdgeRecord],
    max_depth: int = DEFAULT_FLOW_MAX_DEPTH,
    max_branch_per_node: int = DEFAULT_FLOW_MAX_BRANCH,
    max_nodes: int = DEFAULT_FLOW_MAX_NODES,
) -> ArchitectureFlow:
    entity_by_id = {entity.entity_id: entity for entity in entities}
    outgoing = _build_flow_outgoing(edges)

    current_entity = _resolve_flow_entry(entry_ref, entities, entity_by_id)
    steps: list[ArchitectureFlowStep] = []
    transitions: list[dict[str, object]] = []
    warnings: list[str] = []
    if current_entity is None:
        return ArchitectureFlow(
            flow_id=f"flow:{entry_ref}",
            entry={"kind": "entity" if entry_ref in entity_by_id else "file", "value": entry_ref},
            scope="entity",
            steps=[],
            transitions=[],
            collapsed_subflows=[],
            evidence=[],
            warnings=[],
        )

    step_meta = {
        current_entity.entity_id: {
            "step_id": "step-1",
            "depth": 0,
        }
    }
    queued_entities = [current_entity.entity_id]
    seen_entities: set[str] = set()

    while queued_entities:
        entity_id = queued_entities.pop(0)
        if entity_id in seen_entities:
            continue

        seen_entities.add(entity_id)
        entity = entity_by_id[entity_id]
        meta = step_meta[entity_id]
        step_id = str(meta["step_id"])
        depth = int(meta["depth"])

        unique_children: dict[str, EdgeRecord] = {}
        for edge in _sorted_flow_edges(outgoing.get(entity_id, [])):
            if edge.target_id not in entity_by_id:
                continue
            if edge.target_id == entity_id:
                warnings.append("loop_detected")
                continue
            if edge.target_id not in unique_children:
                unique_children[edge.target_id] = edge

        child_edges = list(unique_children.values())

        visible_edges: list[EdgeRecord] = []
        collapsed_child_count = 0
        if depth >= max_depth:
            collapsed_child_count = len(child_edges)
            if collapsed_child_count:
                warnings.append("max_depth_reached")
        else:
            for edge in child_edges:
                if len(visible_edges) >= max_branch_per_node:
                    collapsed_child_count += 1
                    continue
                existing = step_meta.get(edge.target_id)
                if existing and int(existing["depth"]) <= depth:
                    warnings.append("loop_detected")
                    collapsed_child_count += 1
                    continue
                if existing is None:
                    if len(step_meta) >= max_nodes:
                        warnings.append("max_nodes_reached")
                        collapsed_child_count += 1
                        continue
                    step_meta[edge.target_id] = {
                        "step_id": f"step-{len(step_meta) + 1}",
                        "depth": depth + 1,
                    }
                    queued_entities.append(edge.target_id)
                visible_edges.append(edge)

        steps.append(
            ArchitectureFlowStep(
                step_id=step_id,
                label=entity.name,
                node_kind="entity",
                ref=entity.entity_id,
                file_path=entity.file_path,
                depth=depth,
                child_count=len(child_edges),
                visible_child_count=len(visible_edges),
                collapsed_child_count=collapsed_child_count,
                evidence=[{"entity_id": entity.entity_id}],
            )
        )

        for edge in visible_edges:
            target_meta = step_meta.get(edge.target_id)
            if not target_meta:
                continue
            transitions.append(
                {
                    "source": step_id,
                    "target": str(target_meta["step_id"]),
                    "edge_type": edge.edge_type,
                    "evidence": [{"edge_id": edge.edge_id}],
                }
            )

    warnings = list(dict.fromkeys(warnings))

    return ArchitectureFlow(
        flow_id=f"flow:{entry_ref}",
        entry={"kind": "entity" if entry_ref in entity_by_id else "file", "value": entry_ref},
        scope="entity",
        steps=steps,
        transitions=transitions,
        collapsed_subflows=[],
        evidence=[],
        warnings=warnings,
    )


def _resolve_flow_entry(
    entry_ref: str,
    entities: list[EntityRecord],
    entity_by_id: dict[str, EntityRecord],
) -> EntityRecord | None:
    if entry_ref in entity_by_id:
        return entity_by_id[entry_ref]
    file_matches = [
        entity for entity in entities if entity.file_path == entry_ref and entity.entity_type in {"function", "method", "class"}
    ]
    if file_matches:
        file_matches.sort(key=lambda entity: (entity.start_line, entity.name))
        return file_matches[0]
    return None
