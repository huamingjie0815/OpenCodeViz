from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)

from codeviz.models import EdgeRecord, EntityRecord, FileRecord
from codeviz.runtime_config import init_llm

EXTRACTION_SYSTEM_PROMPT = """\
You are a code analysis engine. Given a source file, extract all code entities and their relationships.

Output ONLY valid JSON with this exact structure:
{
  "entities": [
    {
      "name": "entity name",
      "type": "class|function|method|interface|enum|variable",
      "start_line": 1,
      "end_line": 10,
      "signature": "full signature line",
      "description": "one-line purpose description",
      "parent": "parent entity name if this is a method inside a class, else empty string"
    }
  ],
  "edges": [
    {
      "source": "calling entity name",
      "target": "called entity name",
      "type": "calls|imports|extends|implements|uses|defines",
      "line": 5,
      "description": "brief description of the relationship"
    }
  ],
  "import_entities": [
    {
      "url": "the exact import path string as written in the source (e.g. \"./service\", \"@/utils/helper\", \"../models\")",
      "names": ["EntityName1", "EntityName2"]
    }
  ]
}

Rules:
- Extract ALL classes, functions, methods, interfaces, enums, and significant variables/constants
- For methods, set parent to the class name they belong to
- Edge types (do NOT use "imports" — imports are handled exclusively in import_entities):
  - "defines": class defines a method
  - "calls": one function/method calls another
  - "extends": class extends another class
  - "implements": class implements an interface
  - "uses": entity references/uses another entity
- Do NOT include import statements in edges at all — use import_entities exclusively
- For EVERY import statement in the file, populate import_entities:
  - url: the exact module path string as written in the source (e.g. "./service", "@/utils/helper")
  - names: list of entity names imported from that path
- Only include in import_entities imports that reference other source files — skip stdlib and
  bare package names like "os", "fs", "react", "lodash" (packages without relative path separators)
- Be thorough but precise - only report what is actually in the code
- Do NOT invent entities or relationships not present in the source
- Output valid JSON only, no markdown fencing, no explanation
"""

EXTRACTION_SCHEMA = {
    "title": "ExtractionResult",
    "type": "object",
    "properties": {
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "type": {"type": "string", "enum": ["class", "function", "method", "interface", "enum", "variable"]},
                    "start_line": {"type": "integer"},
                    "end_line": {"type": "integer"},
                    "signature": {"type": "string"},
                    "description": {"type": "string"},
                    "parent": {"type": "string"},
                },
                "required": ["name", "type", "start_line", "end_line"],
            },
        },
        "edges": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "target": {"type": "string"},
                    "type": {"type": "string", "enum": ["calls", "imports", "extends", "implements", "uses", "defines"]},
                    "line": {"type": "integer"},
                    "description": {"type": "string"},
                },
                "required": ["source", "target", "type"],
            },
        },
        "import_entities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "names": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["url", "names"],
            },
        },
    },
    "required": ["entities", "edges"],
}

CROSS_FILE_SYSTEM_PROMPT = """\
You are a code analysis engine. Given a manifest of all entities across multiple files, \
resolve cross-file relationships.

For each import that references an entity from another file, and for each function call \
that targets an entity in a different file, output an edge connecting them.

Rules:
- Only connect entities that actually exist in the manifest
- Use exact entity_id values from the manifest
- Be conservative - only create edges where the connection is clear
"""

CROSS_FILE_SCHEMA = {
    "title": "CrossFileResult",
    "type": "object",
    "properties": {
        "edges": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source_id": {"type": "string"},
                    "target_id": {"type": "string"},
                    "type": {"type": "string", "enum": ["calls", "imports", "extends", "implements", "uses"]},
                    "description": {"type": "string"},
                },
                "required": ["source_id", "target_id", "type"],
            },
        },
    },
    "required": ["edges"],
}


def _parse_llm_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```\w*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
    start = cleaned.find("{")
    if start == -1:
        return {"entities": [], "edges": []}
    try:
        result, _ = json.JSONDecoder().raw_decode(cleaned, start)
        return result
    except json.JSONDecodeError:
        return {"entities": [], "edges": []}


class LLMExtractor:
    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self._llm = None
        # Pre-disable structured output if explicitly configured off,
        # or if a custom baseUrl is set (non-standard endpoints rarely support it).
        cfg_flag = self.config.get("structuredOutput")
        has_custom_base = bool(self.config.get("baseUrl", "").strip())
        if cfg_flag is False or (cfg_flag is None and has_custom_base):
            self._structured_output_supported: bool | None = False
        else:
            self._structured_output_supported = None  # None = untested

    @property
    def llm(self):
        if self._llm is None:
            self._llm = init_llm(self.config)
        return self._llm

    def _invoke_structured(self, schema: dict, messages: list, fallback_default: dict) -> dict:
        """Invoke with structured output, falling back to text parsing if unsupported."""
        if self._structured_output_supported is not False:
            try:
                structured_llm = self.llm.with_structured_output(schema)
                result = structured_llm.invoke(messages)
                self._structured_output_supported = True
                if isinstance(result, dict):
                    return result
                if hasattr(result, "model_dump"):
                    return result.model_dump()
                if hasattr(result, "dict"):
                    return result.dict()
            except Exception as exc:
                self._structured_output_supported = False
                logger.warning("with_structured_output failed (%s); falling back to text parsing for all files", exc)
        # Fallback: plain invocation — system prompt already contains the JSON format
        response = self.llm.invoke(messages)
        text = response.content if hasattr(response, "content") else str(response)
        parsed = _parse_llm_json(text)
        # Ensure all expected top-level keys are present
        for key, default in fallback_default.items():
            parsed.setdefault(key, default)
        return parsed

    def invoke_json(self, system_prompt: str, user_prompt: str, schema: dict, default: dict) -> dict:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return self._invoke_structured(schema, messages, default)

    def extract_file(
        self,
        file_path: str,
        content: str,
        language: str,
    ) -> dict[str, list]:
        prompt = (
            f"Analyze this {language} file: {file_path}\n\n"
            f"```{language}\n{content}\n```"
        )
        messages = [
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        parsed = self._invoke_structured(
            EXTRACTION_SCHEMA, messages, {"entities": [], "edges": [], "import_entities": []}
        )

        entities: list[EntityRecord] = []
        edges: list[EdgeRecord] = []

        for raw in parsed.get("entities", []):
            name = raw.get("name", "")
            etype = raw.get("type", "function")
            parent = raw.get("parent", "")
            parent_id = ""
            if parent:
                parent_id = f"{parent}:{file_path}"
            entity_id = f"{etype}:{file_path}:{name}:{raw.get('start_line', 0)}"
            entities.append(EntityRecord(
                entity_id=entity_id,
                entity_type=etype,
                name=name,
                file_path=file_path,
                start_line=raw.get("start_line", 0),
                end_line=raw.get("end_line", 0),
                signature=raw.get("signature", ""),
                description=raw.get("description", ""),
                parent_id=parent_id,
                language=language,
            ))

        entity_names = {e.name: e.entity_id for e in entities}

        for raw in parsed.get("edges", []):
            # Skip import-type edges from the LLM — all imports are handled via import_entities
            if raw.get("type") == "imports":
                continue
            src_name = raw.get("source", "")
            tgt_name = raw.get("target", "")
            etype = raw.get("type", "calls")
            line = raw.get("line", 0)

            src_id = entity_names.get(src_name, f"unresolved:{file_path}:{src_name}")
            tgt_id = entity_names.get(tgt_name, f"unresolved:{file_path}:{tgt_name}")
            edge_id = f"{etype}:{src_id}->{tgt_id}:{line}"

            edges.append(EdgeRecord(
                edge_id=edge_id,
                source_id=src_id,
                target_id=tgt_id,
                edge_type=etype,
                file_path=file_path,
                line=line,
                description=raw.get("description", ""),
            ))

        import_entities: list[dict] = []
        for raw in parsed.get("import_entities", []):
            url = raw.get("url", "").strip()
            names = [n for n in raw.get("names", []) if isinstance(n, str) and n]
            if url and names:
                import_entities.append({"url": url, "names": names})

        return {"entities": entities, "edges": edges, "import_entities": import_entities}

    def resolve_cross_file_relations(
        self,
        all_entities: list[EntityRecord],
        all_edges: list[EdgeRecord],
    ) -> list[EdgeRecord]:
        manifest_lines = []
        for e in all_entities:
            manifest_lines.append(f"  {e.entity_id} | {e.entity_type} | {e.name} | {e.file_path}")
        manifest = "\n".join(manifest_lines)

        unresolved = [e for e in all_edges if "unresolved:" in e.source_id or "unresolved:" in e.target_id]
        if not unresolved:
            return []

        unresolved_lines = []
        for edge in unresolved[:100]:
            unresolved_lines.append(f"  {edge.source_id} --{edge.edge_type}--> {edge.target_id}")
        unresolved_text = "\n".join(unresolved_lines)

        prompt = (
            f"Entity manifest:\n{manifest}\n\n"
            f"Unresolved edges to resolve:\n{unresolved_text}\n\n"
            f"Resolve the 'unresolved:' references to actual entity_ids from the manifest."
        )
        messages = [
            {"role": "system", "content": CROSS_FILE_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        parsed = self._invoke_structured(
            CROSS_FILE_SCHEMA, messages, {"edges": []}
        )

        entity_set = {e.entity_id for e in all_entities}
        new_edges: list[EdgeRecord] = []
        for raw in parsed.get("edges", []):
            src = raw.get("source_id", "")
            tgt = raw.get("target_id", "")
            if src in entity_set and tgt in entity_set:
                edge_id = f"xref:{src}->{tgt}"
                new_edges.append(EdgeRecord(
                    edge_id=edge_id,
                    source_id=src,
                    target_id=tgt,
                    edge_type=raw.get("type", "calls"),
                    description=raw.get("description", ""),
                ))

        return new_edges
