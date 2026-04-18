Date: 2026-04-18
Project: OpenCodeViz
Status: Approved design

## Summary

OpenCodeViz currently extracts per-file entities and relationships with an LLM-first pipeline in `[src/codeviz/extractor.py](/Users/hmj/Desktop/project/show-your-code/src/codeviz/extractor.py)`. That approach is flexible but slow, expensive, and unstable across reruns. The new design makes AST-based extraction the default path and reduces the LLM to a narrow fallback used only for unresolved cases that deterministic analysis cannot bind safely.

The design keeps the current output model and snapshot format centered on `FileRecord`, `EntityRecord`, and `EdgeRecord`. The main change is inside the analysis pipeline: source files are parsed into a small language-agnostic intermediate representation, deterministic resolvers convert that representation into graph entities and edges, and only a small unresolved subset is optionally sent to the LLM for disambiguation.

## Goals

- Replace per-file LLM extraction with AST-first extraction.
- Keep one unified analysis pipeline across supported languages.
- Preserve the current storage model and downstream UI expectations.
- Reduce analysis latency and token cost significantly.
- Improve determinism for entities, imports, inheritance, and direct call edges.
- Keep unresolved relationships traceable instead of guessing.
- Continue to support repositories containing multiple languages.

## Non-Goals

- Building a complete compiler-grade semantic model for every supported language.
- Perfectly resolving dynamic dispatch, reflection, runtime patching, or framework lifecycle calls.
- Replacing the current graph schema or storage format.
- Removing the LLM completely in the first version.
- Achieving identical output to the current LLM pipeline.

## Current Problems

The current pipeline asks the LLM to extract:

- entities
- intra-file edges
- import entities
- unresolved cross-file links

This creates four problems:

1. Cost grows linearly with file count and file size.
2. Latency is dominated by network calls and model inference.
3. Results can vary across reruns because extraction is prompt-driven.
4. The LLM is used for work that is mostly syntax-driven and better handled deterministically.

The repository already contains deterministic pieces in `[src/codeviz/analysis.py](/Users/hmj/Desktop/project/show-your-code/src/codeviz/analysis.py)`, especially import URL resolution and post-processing of unresolved edges. This design builds on that direction instead of replacing the whole pipeline.

## User And Usage Model

Primary user: project developers exploring repository structure, module dependencies, and code flow.

Primary questions:

- What entities exist in this repository?
- Which files import which code?
- Which functions and methods directly call each other?
- What relationships are certain versus unresolved?
- Can analysis remain useful when LLM access is slow, expensive, or unavailable?

This implies:

- deterministic structure is more important than maximal recall
- false positive edges are worse than missing low-confidence edges
- unresolved relationships must be inspectable and, when possible, recoverable later

## Proposed Architecture

The new analysis pipeline is split into four layers.

### 1. Parser registry

A parser registry selects a parser by `language` and exposes a common entrypoint:

`parse_file(path, content, language) -> ParseResult`

The first version uses `tree-sitter` as the primary parser family so the project can support multiple languages through one AST infrastructure. Language-specific differences are isolated in adapter modules, not in the analysis pipeline.

### 2. Parse IR

Parsers do not emit final graph records directly. They emit a small intermediate representation containing only the structural evidence needed by the graph pipeline.

This IR is language-agnostic and intentionally narrow so:

- new languages can be added with small adapters
- the resolver layer stays stable
- downstream storage and UI do not need to know parser details

### 3. Deterministic resolver

The resolver converts IR into `EntityRecord` and `EdgeRecord` using deterministic rules. It is responsible for:

- assigning stable entity identifiers
- binding parents for methods and nested entities
- resolving import URLs to known files
- binding imported symbols to target entities
- converting direct call sites into `calls` edges when targets are known
- producing `extends` and `implements` edges
- leaving uncertain cases unresolved instead of inventing links

This layer reuses and extends the existing deterministic helpers in `[src/codeviz/analysis.py](/Users/hmj/Desktop/project/show-your-code/src/codeviz/analysis.py)`.

### 4. LLM fallback resolver

The LLM is retained only as a disambiguation layer for unresolved relationships. It no longer performs primary extraction from whole files.

Its responsibilities are limited to:

- choosing among existing candidate target entities
- resolving a small unresolved subset when context is sufficient
- returning no result when the relationship is ambiguous

It may not:

- invent new entities
- invent new edge types
- rewrite deterministic results
- analyze the whole repository as raw input

## Parse IR Model

The first version should keep the IR minimal.

### `ParseEntity`

- `local_id`
- `name`
- `kind`
- `file_path`
- `start_line`
- `end_line`
- `signature`
- `parent_local_id`
- `exported`
- `language`

`kind` should align with current graph entity types where possible:

- `class`
- `function`
- `method`
- `interface`
- `enum`
- `variable`

### `ParseImport`

- `module_path`
- `import_kind`
- `imported_name`
- `local_name`
- `source_entity_local_id`
- `line`

`import_kind` initially supports:

- `named`
- `default`
- `namespace`
- `side_effect`

### `ParseReference`

- `source_entity_local_id`
- `name`
- `qualifier`
- `reference_kind`
- `line`

`reference_kind` initially supports:

- `read`
- `write`
- `type`

### `ParseCallSite`

- `source_entity_local_id`
- `callee_name`
- `callee_qualifier`
- `line`

### `ParseInheritance`

- `source_entity_local_id`
- `target_name`
- `relation_type`
- `line`

`relation_type` supports:

- `extends`
- `implements`

### `ParseExport`

- `export_name`
- `local_name`
- `line`

### `ParseDiagnostic`

- `level`
- `message`
- `line`

### `ParseResult`

- `entities`
- `imports`
- `references`
- `call_sites`
- `inheritance`
- `exports`
- `diagnostics`

The IR is not a public storage format. It exists only for deterministic analysis inside one run.

## Relationship Scope

The first version should only emit high-confidence relationships.

### Supported relationships

1. `defines`
- class to method
- file-level entity ownership already implied by entity records

2. `imports`
- import statement parsing
- import URL to target file resolution
- imported symbol to target entity resolution

3. `extends`
- directly declared class inheritance targets

4. `implements`
- explicitly declared interface implementations in languages that support them

5. `calls`
- high-confidence direct calls only
- examples: `foo()`, `helper.run()`, `self.render()`
- only when the target can be bound without guesswork

6. `uses`
- limited to explicit non-call references with clear evidence
- examples: type names, base types, decorator targets, constant references

### Explicitly unsupported for version one

- dynamic dispatch requiring whole-program type inference
- reflection and string-based dispatch
- monkey patching
- framework lifecycle edges inferred without explicit syntax
- runtime dependency injection
- macro-expanded relationships
- generated code that is absent from scanned source files

These cases should remain unresolved instead of producing speculative edges.

## Analysis Pipeline

The file discovery, snapshot setup, and final storage flow in `[src/codeviz/analysis.py](/Users/hmj/Desktop/project/show-your-code/src/codeviz/analysis.py)` remain intact. The change is inside the extraction step.

### Current flow

`file -> LLMExtractor.extract_file -> entities/edges/import_entities -> post-processing`

### New flow

`file -> ASTExtractor.extract_file -> ParseResult -> DeterministicResolver -> entities/edges/unresolved -> optional LLM fallback`

### Detailed steps

1. Discover files exactly as today.
2. Detect language exactly as today.
3. Parse each file into `ParseResult`.
4. Convert parsed entities into `EntityRecord`.
5. Resolve imports using existing known-file logic.
6. Resolve local direct calls and inheritance edges deterministically.
7. Record unresolved relationships with enough context for later recovery.
8. After all files are parsed, run optional LLM fallback only on unresolved subsets that have viable candidates.
9. Reuse existing deduplication and post-processing before saving snapshot outputs.

## Deterministic Resolution Rules

### Entity generation

Entity identifiers should remain compatible with the current convention:

`{entity_type}:{file_path}:{name}:{start_line}`

Parent-child relationships should continue to use parent entity identifiers so the UI can keep its current drill-down behavior.

### Import resolution

The existing `_resolve_import_url(...)` logic in `[src/codeviz/analysis.py](/Users/hmj/Desktop/project/show-your-code/src/codeviz/analysis.py)` should remain the base import URL resolver.

The new design adds one layer before it:

- parser extracts import declarations into `ParseImport`
- resolver groups imports by local names and module paths
- URL resolution maps `module_path` to a target file
- symbol resolution maps imported names to known target entities in that file

When a target file is known but the exact imported symbol is not yet available, the relation stays pending and is later flushed through the existing cross-file import mechanism.

### Call resolution

Direct call resolution should follow conservative rules:

- local unqualified calls first try same-scope entities in the same file
- qualified calls such as `service.run()` first try imported aliases or locally assigned receivers when those are explicit
- `self.method()` and equivalent receiver forms may resolve to methods on the current class when the binding is syntactically obvious

If multiple targets are plausible, the resolver must not choose one arbitrarily. The result should remain unresolved.

### Inheritance resolution

`extends` and `implements` should bind only when the target name can be matched confidently against:

- same-file entities
- directly imported entities
- known entities in the resolved imported file

Otherwise the relation remains unresolved.

## Unresolved Model

The system already uses unresolved identifiers such as `unresolved:{file}:{name}`. That pattern should be preserved and extended to the AST-first pipeline.

Unresolved records should retain enough evidence for later resolution:

- source file
- source entity
- raw referenced name
- relation type
- line number
- optional qualifier
- candidate entity identifiers, if available

The resolver must prefer unresolved output over speculative linking.

## LLM Fallback Strategy

The fallback layer should be invoked only for unresolved relationships that meet all of these conditions:

- relation type is high value: `calls`, `imports`, `extends`, or `implements`
- there is at least one plausible candidate target entity
- the source snippet is small enough to send efficiently
- fallback mode allows invocation

### Fallback modes

- `off`
  - never invoke the LLM
- `auto`
  - invoke only for selected unresolved cases
- `always`
  - invoke for every eligible unresolved case

Default mode should be `auto`.

### Fallback input

Fallback prompts should include only:

- unresolved relation records
- the local code snippet around each unresolved site
- the current file import table
- candidate target entities

Whole-file extraction prompts must be removed from the main path.

### Fallback output contract

The LLM may only:

- choose one candidate target
- choose none

It may not:

- introduce a new entity
- alter a resolved deterministic edge
- change entity boundaries

## Module Boundaries In Code

The new code should be split by responsibility instead of continuing to grow `[src/codeviz/extractor.py](/Users/hmj/Desktop/project/show-your-code/src/codeviz/extractor.py)`.

Recommended modules:

- `src/codeviz/parsing/base.py`
  - parser interfaces
  - IR structures
- `src/codeviz/parsing/registry.py`
  - language-to-parser registration
- `src/codeviz/parsing/tree_sitter_parser.py`
  - shared `tree-sitter` integration
- `src/codeviz/parsing/languages/*.py`
  - language-specific adapters
- `src/codeviz/resolution/deterministic.py`
  - AST-to-graph resolution
- `src/codeviz/resolution/fallback.py`
  - LLM disambiguation for unresolved cases
- `src/codeviz/extractor.py`
  - compatibility facade and legacy wrapper during migration

This keeps the parser layer, resolution layer, and LLM layer isolated and easier to test.

## Configuration

The pipeline should expose an extractor mode setting:

- `llm`
- `ast`
- `hybrid`

Recommended behavior:

- first rollout default: `hybrid`
- later default: `ast`

Meaning:

- `llm`
  - current behavior, retained temporarily for rollback
- `ast`
  - AST extraction only, optional fallback controlled separately
- `hybrid`
  - AST-first with optional LLM fallback for unresolved cases

This lets the project ship incrementally and compare outputs safely.

## Testing Strategy

### Unit tests

Add parser adapter tests that feed small source snippets into language parsers and assert:

- entity extraction
- import extraction
- call site extraction
- inheritance extraction

Add resolver tests that feed fixed IR and assert:

- `EntityRecord` generation
- `EdgeRecord` generation
- unresolved output for ambiguous cases

### Fixture tests

Create small multi-file fixtures covering:

- Python `import` and `from ... import ...`
- TypeScript and JavaScript named, default, and namespace imports
- direct same-file calls
- direct cross-file calls
- class inheritance
- alias imports

Fixture tests should stay focused and deterministic. They should verify resolution rules, not broad repository behavior.

### Regression tests

Use this repository as one baseline. Compare:

- entity counts
- import edge counts
- direct call edge counts
- unresolved counts
- number of LLM invocations

The primary acceptance metric is not parity with prior LLM output. The primary acceptance metric is better determinism and lower cost without breaking core graph behavior.

### End-to-end verification

A complete `analyze` run should still produce snapshots that work with:

- graph exploration
- architecture aggregation
- flow entry indexing

## Migration Plan

### Phase 1: infrastructure

- add IR types
- add parser registry
- add AST extractor scaffold
- keep current LLM path intact

### Phase 2: entity and import replacement

- support Python and TypeScript/JavaScript first
- replace entity extraction with AST
- replace import extraction with AST
- keep existing deterministic import URL resolution

### Phase 3: direct call replacement

- add same-file direct call resolution
- add conservative cross-file call binding
- keep unresolved for ambiguous cases

### Phase 4: fallback reduction

- move LLM to unresolved-only fallback
- shrink prompt inputs to unresolved subsets
- add mode flags and rollout controls

### Phase 5: broaden language coverage

- add more `tree-sitter` adapters
- optionally add language-specific enhancers where AST alone is insufficient

## Risks And Trade-Offs

### Risk: AST results may contain fewer edges than the current LLM pipeline

This is acceptable if the remaining edges are more accurate and stable. The system should optimize for trustworthy structure, not raw edge volume.

### Risk: parser adapters become inconsistent across languages

This is why the IR must stay narrow and the resolver must only depend on that IR, not on raw parser node shapes.

### Risk: fallback usage slowly expands back into the main path

The fallback contract must stay strict: choose among candidates or abstain. It must not resume whole-file extraction responsibilities.

### Risk: dynamic languages still leave many unresolved edges

This is expected. The design treats unresolved as an explicit, inspectable outcome rather than a failure hidden behind guesses.

## Recommendation

Adopt an AST-first unified parsing layer with `tree-sitter` as the common parser foundation, deterministic resolution as the primary graph builder, and LLM fallback limited to unresolved disambiguation.

This approach best fits the current codebase because:

- analysis already has deterministic post-processing that can be extended
- storage and UI can remain largely unchanged
- cost and latency drop immediately once whole-file LLM extraction is removed
- language-specific complexity is isolated to parser adapters instead of leaking across the system

## Implementation Sequence

1. Introduce IR structures and parser registry.
2. Add `tree-sitter` parsers for Python and TypeScript/JavaScript.
3. Replace AST entity and import extraction in the main pipeline.
4. Add deterministic direct call and inheritance resolution.
5. Restrict the LLM to unresolved-only fallback.
6. Add extractor mode flags and compare outputs under `hybrid`.
7. Expand language coverage incrementally.
