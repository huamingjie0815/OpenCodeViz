# Architecture And Flow Diagram Design

Date: 2026-04-17
Project: OpenCodeViz
Status: Approved design

## Summary

OpenCodeViz already produces versioned code analysis snapshots containing files, entities, edges, documents, events, and project info. The new capability adds a second derived layer on top of that snapshot: architecture and flow diagram assets for developers.

The goal is not to replace the existing code graph. The goal is to derive a higher-level, versioned, code-traceable view of the repository that can:

- show a module-level architecture diagram by default
- drill down from module level to file level to entity level
- generate flow diagrams for a user-specified entrypoint
- support both interactive UI rendering and static export from the same underlying data

The generation strategy is hybrid:

- rules produce the stable structural skeleton
- LLMs only assist with naming, merge suggestions, and readable step summaries

## Goals

- Produce a stable architecture snapshot as part of each analysis run.
- Default to a module-level architecture diagram for developers.
- Preserve traceability from every architecture node and edge back to source directories, files, and entities.
- Generate flow diagrams only for explicit user-selected entrypoints.
- Reuse the current page layout and visual style.
- Support both API/UI consumption and static export from the same generated data.
- Continue to provide a useful fallback when LLM enhancement is unavailable.

## Non-Goals

- Replacing the existing entity-level code graph.
- Auto-generating broad workflow diagrams for an entire repository without an entrypoint.
- Building a separate frontend application or separate page for architecture and flow views.
- Letting the LLM invent architecture not supported by analysis evidence.

## User And Usage Model

Primary user: project developers.

Primary questions:

- What are the main components of this codebase?
- How do modules depend on each other?
- What files and entities belong to a module?
- How does a specific command, request path, or function execute?
- What code evidence supports a shown architecture or flow step?

This implies:

- traceability is more important than presentation polish
- stable results are more important than purely narrative output
- every high-level result must remain connected to code evidence

## Proposed Architecture

Each `versions/<run_id>/` snapshot gains a derived architecture layer in addition to the existing files, entities, edges, and documents.

New per-run files:

- `architecture.json`
  - normalized module definitions
  - module-to-module dependencies
  - module-to-file and module-to-entity mappings
  - merge decisions and evidence
- `flow_index.json`
  - candidate entrypoints for flow generation
  - file, entity, and inferred entry aliases
- `diagrams.json`
  - generated diagram definitions
  - initial format should be Mermaid text plus structured references
- `architecture_meta.json`
  - generator version
  - rules version
  - LLM enhancement metadata
  - confidence and warning records

These files are generated after the existing base analysis completes. They are versioned with the same `run_id` and consumed by both API and UI.

## Analysis Pipeline

### 1. Base analysis

Reuse the current pipeline to produce:

- `files.json`
- `entities.json`
- `edges.json`
- `documents.json`
- `events.json`
- `project_info.json`

This layer remains the source of truth for low-level code relationships.

### 2. Rule-based architecture derivation

Produce a deterministic architecture skeleton from the existing snapshot.

Responsibilities:

- split repository content into initial modules based on directory structure
- identify module ownership for files and entities
- aggregate cross-module dependencies from file and entity edges
- identify likely entrypoints for flow generation
- build drill-down mappings from module to file to entity

This stage must be reproducible without LLM support.

### 3. LLM semantic enhancement

LLM input must be the structured result of the rule stage, not the entire raw repository.

Allowed LLM responsibilities:

- propose clearer component display names
- suggest safe directory merges into one logical component
- summarize flow steps in readable one-line labels

Disallowed LLM responsibilities:

- invent new modules without evidence
- alter dependency direction
- create unsupported flow transitions

Every LLM-derived field must retain evidence references.

### 4. Diagram definition generation

Generate stable diagram outputs from the architecture snapshot:

- module-level architecture diagram
- file-level subgraph for a selected module
- entrypoint-specific flow diagram
- optional entity-level focus views backed by existing graph data

Diagram definition generation must be independent from frontend rendering.

## Module Segmentation Model

### Initial segmentation

Default module boundaries come from directory structure.

Rules:

- prefer `src/` descendants when present
- use first-level or second-level directories as initial module candidates
- preserve obvious single-file top-level roles such as `cli.py`, `app.py`, `server.py`, `commands.py`

### Merge and normalization

After initial segmentation, normalize modules with deterministic rules and optional LLM assistance.

Allowed merge cases:

- thin directories with one or two files serving a neighboring directory
- directories that clearly form a single subsystem together
- naming patterns such as API surface plus handlers plus routes that act as one component

Each final module record should retain:

- `module_id`
- `display_name`
- `source_dirs`
- `file_paths`
- `entity_ids`
- `merge_reason`
- `confidence`

The final architecture view must show logical components while preserving raw directory provenance.

## Dependency Aggregation Model

Architecture dependencies are not raw entity edges rendered at a higher zoom level. They are aggregated edges with evidence.

Aggregation rules:

- map file and entity edges to owning modules
- ignore edges that stay within the same final module
- aggregate cross-module dependencies by edge type
- compute a strength score from edge volume and evidence diversity

Each module dependency should contain:

- `source_module_id`
- `target_module_id`
- `dominant_edge_type`
- `imports_count`
- `calls_count`
- `uses_count`
- `strength`
- `evidence`

`evidence` must contain enough detail to support drill-down, such as:

- file-to-file examples
- entity-to-entity examples
- sample lines or source entity ids where available

Default filtering:

- exclude test-to-production dependencies unless the user explicitly enables test scope
- collapse weak utility connections when they add noise
- hide low-strength edges by default while keeping them available for expansion

## Drill-Down Model

Three levels are required.

### 1. Module level

Default architecture overview.

Shows:

- logical components
- component dependencies
- module summary metadata

Answers:

- what the major parts are
- how they connect

### 2. File level

Activated by selecting a module.

Shows:

- files inside the selected module
- internal and external file relationships
- per-file role summaries

Answers:

- how the component is organized internally

### 3. Entity level

Activated from a file view.

Shows:

- existing entity graph constrained to the current scope

Answers:

- what concrete classes, methods, and functions implement the behavior

This is a scope-aware reuse of the existing graph layer, not a separate model.

## Flow Generation Model

Flow diagrams are generated only for user-specified entrypoints.

### Supported entrypoint forms

- file path
- entity id
- natural language request that resolves to a specific file or entity

If resolution is ambiguous, the system must return candidates instead of guessing.

### Generation steps

1. Resolve the user input to a unique entrypoint.
2. Expand outward across supported relationships.
3. Keep only the main path and relevant branch points.
4. Collapse repetitive or low-value utility detail.
5. Generate a structured flow and a diagram definition.

### Relationship use

Preferred relationships:

- `calls`
- `imports`
- `uses`
- `defines` when needed to connect a method or nested entity to its container

### Complexity controls

Default controls:

- maximum depth
- maximum node count
- repeated utility collapse
- loop detection with marked back-edges
- module-level stage collapsing for dense internal sequences

If a path is too large, the result should explicitly show collapsed subflows instead of silently dropping steps.

### Flow output structure

Each flow should include:

- `flow_id`
- `entry`
- `scope`
- `steps`
- `transitions`
- `collapsed_subflows`
- `evidence`
- `warnings`

Each step should include:

- display label
- source file or entity
- inferred action summary
- upstream and downstream references
- evidence references

The display label may be LLM-enhanced, but the ordering and transitions must remain rule-derived.

## UI Integration

The page layout stays as-is.

- left sidebar remains the search, filters, and controls area
- center remains the primary canvas area
- right sidebar remains the detail panel

The center canvas gains a tab switcher.

Tabs:

- `Code Graph`
- `Architecture`
- `Flow`

Rules:

- do not create a separate page
- do not introduce a second visual language
- keep theme, typography, spacing, border treatment, hover states, selection states, and detail behavior aligned with the current UI

### Architecture tab

- default view is module-level architecture
- selecting a module drills into file level
- selecting a file can continue into entity level
- node and edge styling should feel native to the existing graph while clearly representing architectural meaning

### Flow tab

- flow diagrams render in the same center canvas
- entry selection and parameter controls can live in the existing side areas
- generated flow results replace the center canvas content for the active tab only
- details panel shows flow step metadata and code evidence

### Shared interaction model

Across tabs, preserve:

- consistent search behavior
- hover feedback
- selected item state
- right-panel inspection
- evidence-driven navigation back to files and entities

## API Additions

Current graph APIs should remain intact. Add architecture-specific endpoints backed by the versioned derived assets.

Suggested endpoints:

- `/api/architecture`
  - module graph payload and metadata
- `/api/architecture/module`
  - selected module drill-down payload
- `/api/flow/index`
  - available entrypoints and candidates
- `/api/flow`
  - generated flow for a resolved entrypoint
- `/api/diagrams`
  - exportable diagram definitions

API payloads should use the same derived data consumed by the UI and export path.

## Export Strategy

Exports must come from structured derived assets, not from DOM capture.

Initial export outputs:

- structured JSON
- Mermaid text
- SVG

Recommended implementation order:

1. structured JSON
2. Mermaid
3. SVG

PNG is out of the initial implementation scope.

## Failure Handling

Do not force a perfect-looking result. Failures must remain explainable.

Fallback rules:

- if module normalization fails, fall back to directory-level modules
- if LLM naming fails, keep deterministic directory-based names
- if a flow entrypoint cannot be resolved uniquely, return candidates
- if a flow exceeds complexity limits, surface collapsed sections explicitly
- if evidence is weak, mark low confidence instead of over-asserting relationships

Warnings belong in `architecture_meta.json` and flow payload warnings so the UI can surface them.

## Testing Strategy

### Unit tests

Cover:

- module segmentation
- merge rules
- dependency aggregation
- entrypoint resolution
- flow expansion and collapse rules
- low-confidence and fallback paths

### Snapshot tests

For fixed repositories, verify stable outputs for:

- `architecture.json`
- `flow_index.json`
- `diagrams.json`
- generated Mermaid content

### Integration tests

Cover:

- analyze to derived-asset generation
- API payload correctness
- drill-down behavior from architecture to file to entity scope
- flow generation for explicit entrypoints

### Regression corpus

Test against at least:

- a small script-oriented repository
- a layered backend repository
- a mixed frontend/backend repository
- this repository itself

## Acceptance Criteria

- each successful analysis run writes a stable `architecture.json`
- the UI provides `Code Graph`, `Architecture`, and `Flow` tabs in the center canvas
- the `Architecture` tab defaults to a module-level diagram
- architecture nodes and edges can be traced back to directories, files, and entities
- the user can drill down from module level to file level to entity level
- the user can request a flow for a specific entrypoint
- the generated flow keeps evidence for every visible step
- UI, API, and exports all consume the same derived architecture data
- when LLM enhancement is unavailable, a deterministic base architecture view still works

## Implementation Notes

Recommended delivery order:

1. add derived architecture storage and models
2. implement deterministic module segmentation and dependency aggregation
3. expose architecture API payloads
4. add `Architecture` and `Flow` tabs to the current UI
5. implement flow entry resolution and flow generation
6. layer in LLM naming and summary enhancement
7. add Mermaid and SVG export support

This sequencing keeps the first shipped version usable without depending on the LLM-enhanced layer.
