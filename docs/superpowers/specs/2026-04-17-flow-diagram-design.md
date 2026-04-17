# Flow Diagram Design

Date: 2026-04-17
Project: OpenCodeViz
Status: Approved design

## Summary

The current `Flow` view is not a true flow diagram.

Backend flow generation currently follows one linear path by picking a single next edge from the selected entrypoint. Frontend flow rendering then reuses the same force-directed graph renderer used by the code graph. That combination produces a small subgraph, not a readable call flow.

This change turns `Flow` into a dedicated call flow diagram for function and module execution paths:

- start from one selected entrypoint
- expand into multiple downstream branches
- render as a top-down layered diagram
- keep traceability to source files and entity ids
- stay bounded so large repositories do not explode into unreadable diagrams

The target shape is a branching call-flow view, not a control-flow graph and not a full repository call graph.

## Goals

- Make `Flow` visually distinct from `Code Graph`.
- Support one entrypoint with multiple downstream branches.
- Render `Flow` as a top-down diagram with directional arrows.
- Keep results deterministic for the same snapshot and entrypoint.
- Bound expansion with depth, branch, and node limits.
- Preserve code traceability for every node and edge.
- Keep the current single-page application and current left/right sidebars.

## Non-Goals

- Building a control-flow graph for one function body with `if`, `else`, loops, or returns.
- Rendering the entire repository call graph in the `Flow` tab.
- Adding LLM-generated business stages such as "validate request" or "load config".
- Replacing the existing `Code Graph` view.
- Adding browser routing, deep-link state, or multi-entry comparison.

## User And Usage Model

Primary user: project developers exploring how one command or entry function fans out into lower-level calls.

Primary questions:

- What does this entrypoint call next?
- Where does execution branch?
- Which downstream calls belong to the same file or subsystem?
- Which part of the flow was omitted because of complexity limits?

This implies:

- directional readability matters more than preserving every raw edge
- branch structure matters more than physical force balance
- stable layout matters more than free-form graph exploration

## Current Problem

### Backend

`build_flow_payload()` in `src/codeviz/architecture.py` only follows one next edge at each step. It sorts candidate edges and selects the first valid target. That means the current payload is a single chain even when the source entity calls multiple children.

### Frontend

`loadFlow()` in `src/codeviz/web/app.js` converts the flow payload into `states.flow.nodes` and `states.flow.links`, then sends that state through `bindState("flow")`, `initSimulation()`, and `renderGraph()`.

That renderer is force-directed. It is appropriate for graph exploration, but not for flow reading. Even correct flow data will still look like a graph cloud if rendered this way.

## Proposed Architecture

`Flow` becomes a dedicated pipeline with its own data shape expectations and its own renderer:

1. backend derives a bounded branching call DAG from one entrypoint
2. project and server APIs expose that DAG as the flow payload
3. frontend renders the DAG with a dedicated layered flow layout
4. the shared sidebars remain, but the center canvas uses flow-specific drawing rules

The existing code graph and architecture pipelines remain separate.

## Backend Design

### Flow traversal model

Replace the current single-path walk with a bounded breadth-first or depth-aware traversal from the selected entrypoint.

Traversal rules:

- start from one selected entity
- only follow edges of type `calls`, `imports`, or `uses`
- allow one source node to connect to multiple child nodes
- stop revisiting already expanded entities
- keep traversal deterministic by sorting candidates

Recommended sort order for child expansion:

1. edge type priority
2. source line
3. target file path
4. target entity id

This preserves stable output while still showing real branches.

### Flow limits

The traversal must be bounded with explicit limits:

- `max_depth`
  - maximum layer depth from the selected entrypoint
- `max_branch_per_node`
  - maximum number of children drawn from one node
- `max_nodes`
  - global cap for the full rendered flow

Recommended starting defaults:

- `max_depth = 4`
- `max_branch_per_node = 4`
- `max_nodes = 24`

These values are small enough to stay readable and large enough to show useful fan-out in typical CLI and service entrypoints.

### Truncation model

When limits suppress children, the payload should preserve that fact explicitly.

Each flow step may include:

- `depth`
- `child_count`
- `visible_child_count`
- `collapsed_child_count`

This allows the UI to show that a node has additional downstream calls not currently displayed.

### Flow data shape

The existing `steps` and `transitions` model can stay, but each step needs enough layout and status metadata for branching flow rendering.

Each step should include:

- `step_id`
- `label`
- `node_kind`
- `ref`
- `file_path`
- `depth`
- `child_count`
- `visible_child_count`
- `collapsed_child_count`
- `evidence`

Each transition should include:

- `source`
- `target`
- `edge_type`
- `evidence`

The payload remains evidence-backed and deterministic.

### Entry resolution

The current entry selection behavior is acceptable:

- entity id input resolves directly
- file path input resolves to the first supported entity in that file

This change does not need a new entry selection model.

## Frontend Design

### Dedicated renderer

`Flow` must stop using the generic force simulation renderer.

Instead, add a dedicated render path in `src/codeviz/web/app.js` or a small companion module such as `src/codeviz/web/flow-layout.js` that:

- groups nodes by `depth`
- places layers vertically from top to bottom
- spreads sibling branches horizontally
- draws directional edges with arrow markers
- renders each step as a rectangular card, not a circle

The visual contract should be:

- parent above
- children below
- branches fan out horizontally
- arrows read top to bottom

### Node design

Each flow node should render as a compact card containing:

- primary label: function or class name
- secondary line: file path
- collapsed badge when `collapsed_child_count > 0`

The current circular node treatment should not be reused in `Flow`.

### Edge design

Flow edges should be drawn as directional paths with arrowheads.

Rules:

- vertical-first or smooth curved connector between layers
- edge labels do not need to be always visible, but `calls`, `imports`, and `uses` must remain inspectable in tooltip or detail panel
- no force-based overlap movement after initial layout

### Interaction model

Keep the interaction model simple:

- hover shows tooltip
- click selects a step and updates the detail panel
- left search filters visible flow steps only
- the top flow entry input remains the place to generate or regenerate a flow

Optional follow-up, not required in the first pass:

- click a node to regenerate the flow with that node as the new root

### Empty and limited states

The UI should distinguish between:

- no flow found for selected entry
- flow generated with no outgoing transitions
- flow truncated because limits were reached

If truncation happened, the detail panel should say so clearly instead of pretending the shown flow is complete.

## File Changes

Expected implementation scope:

- Modify: `src/codeviz/architecture.py`
  - change flow traversal from single path to bounded branching DAG
- Modify: `src/codeviz/project.py`
  - keep the current endpoint shape and pass through the new flow metadata fields
- Modify: `src/codeviz/web/app.js`
  - stop routing `Flow` through force-graph rendering
  - add dedicated flow render path
- Create: `src/codeviz/web/flow-layout.js`
  - pure layout helpers for layered flow placement
- Modify: `src/codeviz/web/index.html`
  - add flow-specific SVG marker or styling hooks if needed
- Modify: `tests/test_architecture.py`
  - cover branching flow payload generation
- Create: `tests/web/flow-layout.test.mjs`
  - cover layered layout behavior
- Modify: `tests/web/view-search.test.mjs`
  - keep left search bound to visible flow nodes

## Testing

Required backend verification:

- one entrypoint with two downstream calls produces one parent and two child steps
- child ordering is deterministic
- repeated reachable nodes do not recurse forever
- depth and node limits produce `collapsed_child_count`

Required frontend verification:

- layered flow layout places deeper nodes below shallower nodes
- siblings occupy different horizontal slots
- flow rendering does not call the force simulation path
- visible flow steps are still searchable from the left sidebar

Manual verification:

- a branching entrypoint renders as a readable top-down diagram
- the `Flow` tab is visually distinct from `Code Graph`
- truncated nodes clearly indicate hidden downstream calls

## Risks And Constraints

- Some entrypoints will still produce noisy flows if the extracted graph contains low-signal utility edges. The traversal may need minor filtering to stay useful.
- DAG layout is simpler than full graph layout, but repeated nodes and shared downstream calls still need careful handling to avoid crossing clutter.
- The current frontend file already contains three rendering modes. Flow-specific logic should stay isolated so this change does not make `app.js` harder to maintain.
- The repository currently has unrelated in-progress changes. Implementation should stay scoped to the flow-specific files above.

## Recommendation

Implement this as a dedicated branching flow diagram, not as a visual tweak on top of the current graph renderer.

If the backend remains single-path, the result will still be too narrow. If the frontend remains force-directed, the result will still look like a graph. Both changes are required for the `Flow` tab to become a real flow diagram.
