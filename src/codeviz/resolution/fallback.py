from __future__ import annotations

from codeviz.models import EdgeRecord


FALLBACK_SCHEMA = {
    "title": "FallbackResolution",
    "type": "object",
    "properties": {
        "edges": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source_id": {"type": "string"},
                    "target_id": {"type": "string"},
                    "type": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["source_id", "target_id", "type"],
            },
        },
    },
    "required": ["edges"],
}


def resolve_unresolved_relations(unresolved: list, all_entities: list, extractor, mode: str) -> list[EdgeRecord]:
    if mode == "off":
        return []

    eligible = [
        item for item in unresolved
        if item.edge_type in {"calls", "imports", "extends", "implements"} and item.candidate_ids
    ]
    if not eligible:
        return []

    candidate_lines = [
        f"{item.source_id} --{item.edge_type}--> {item.target_name} | candidates={','.join(item.candidate_ids)}"
        for item in eligible
    ]
    manifest = "\n".join(f"{entity.entity_id} | {entity.name} | {entity.file_path}" for entity in all_entities)
    prompt = (
        "Resolve each unresolved relation to one candidate target or return no edge.\n\n"
        f"Entities:\n{manifest}\n\n"
        f"Unresolved:\n{'\n'.join(candidate_lines)}"
    )
    parsed = extractor.invoke_json(
        "You resolve uncertain code relationships. Choose only from the provided candidate ids.",
        prompt,
        FALLBACK_SCHEMA,
        {"edges": []},
    )
    entity_ids = {entity.entity_id for entity in all_entities}
    resolved: list[EdgeRecord] = []
    for raw in parsed.get("edges", []):
        source_id = raw.get("source_id", "")
        target_id = raw.get("target_id", "")
        if target_id not in entity_ids:
            continue
        if not source_id:
            continue
        resolved.append(
            EdgeRecord(
                edge_id=f"xref:{source_id}->{target_id}",
                source_id=source_id,
                target_id=target_id,
                edge_type=raw.get("type", "calls"),
                description=raw.get("description", ""),
            )
        )
    return resolved
