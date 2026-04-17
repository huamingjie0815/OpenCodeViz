# Flow Diagram Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the `Flow` tab into a bounded branching call-flow diagram rendered as a top-down layout instead of a force-directed subgraph.

**Architecture:** Extend the existing flow payload in `src/codeviz/architecture.py` from a linear chain to a bounded branching DAG with per-step depth and truncation metadata. Add a dedicated frontend flow layout helper and render path so `Flow` no longer goes through the generic force simulation used by `Code Graph`.

**Tech Stack:** Python 3.12, pytest, static HTML/CSS/JS, Node test runner, D3 SVG rendering

---

## File Map

- Modify: `src/codeviz/architecture.py`
  - build bounded branching flow payloads with deterministic ordering
- Modify: `tests/test_architecture.py`
  - cover branching, limits, and loop handling
- Create: `src/codeviz/web/flow-layout.js`
  - pure helpers for layered node and edge layout
- Create: `tests/web/flow-layout.test.mjs`
  - cover layered flow layout behavior
- Modify: `src/codeviz/web/app.js`
  - add dedicated flow render path and stop using force simulation for flow
- Modify: `src/codeviz/web/index.html`
  - add flow arrow marker and flow-card styles
- Modify: `tests/web/view-search.test.mjs`
  - keep left search behavior bound to visible flow nodes

### Task 1: Branching Flow Payload

**Files:**
- Modify: `tests/test_architecture.py`
- Modify: `src/codeviz/architecture.py`

- [ ] **Step 1: Write the failing branching and truncation tests**

```python
def test_build_flow_payload_branches_to_multiple_children() -> None:
    entities = [
        EntityRecord(entity_id="function:src/app.py:main:1", entity_type="function", name="main", file_path="src/app.py", start_line=1, end_line=10),
        EntityRecord(entity_id="function:src/a.py:alpha:1", entity_type="function", name="alpha", file_path="src/a.py", start_line=1, end_line=10),
        EntityRecord(entity_id="function:src/b.py:beta:1", entity_type="function", name="beta", file_path="src/b.py", start_line=1, end_line=10),
    ]
    edges = [
        EdgeRecord(edge_id="e1", source_id="function:src/app.py:main:1", target_id="function:src/a.py:alpha:1", edge_type="calls", file_path="src/app.py", line=2),
        EdgeRecord(edge_id="e2", source_id="function:src/app.py:main:1", target_id="function:src/b.py:beta:1", edge_type="calls", file_path="src/app.py", line=3),
    ]

    flow = build_flow_payload("function:src/app.py:main:1", entities, edges)

    assert [step.label for step in flow.steps] == ["main", "alpha", "beta"]
    assert [step.depth for step in flow.steps] == [0, 1, 1]
    assert {(item["source"], item["target"]) for item in flow.transitions} == {
        ("step-1", "step-2"),
        ("step-1", "step-3"),
    }


def test_build_flow_payload_marks_collapsed_children_when_branch_limit_hits() -> None:
    entities = [
        EntityRecord(entity_id="function:src/app.py:main:1", entity_type="function", name="main", file_path="src/app.py", start_line=1, end_line=10),
        EntityRecord(entity_id="function:src/a.py:alpha:1", entity_type="function", name="alpha", file_path="src/a.py", start_line=1, end_line=10),
        EntityRecord(entity_id="function:src/b.py:beta:1", entity_type="function", name="beta", file_path="src/b.py", start_line=1, end_line=10),
        EntityRecord(entity_id="function:src/c.py:gamma:1", entity_type="function", name="gamma", file_path="src/c.py", start_line=1, end_line=10),
    ]
    edges = [
        EdgeRecord(edge_id="e1", source_id="function:src/app.py:main:1", target_id="function:src/a.py:alpha:1", edge_type="calls", file_path="src/app.py", line=2),
        EdgeRecord(edge_id="e2", source_id="function:src/app.py:main:1", target_id="function:src/b.py:beta:1", edge_type="calls", file_path="src/app.py", line=3),
        EdgeRecord(edge_id="e3", source_id="function:src/app.py:main:1", target_id="function:src/c.py:gamma:1", edge_type="calls", file_path="src/app.py", line=4),
    ]

    flow = build_flow_payload("function:src/app.py:main:1", entities, edges, max_branch_per_node=2)

    assert [step.label for step in flow.steps] == ["main", "alpha", "beta"]
    assert flow.steps[0].child_count == 3
    assert flow.steps[0].visible_child_count == 2
    assert flow.steps[0].collapsed_child_count == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_architecture.py -k "branches_to_multiple_children or collapsed_children" -v`
Expected: FAIL because `ArchitectureFlowStep` has no `depth` metadata and `build_flow_payload()` still emits a single path.

- [ ] **Step 3: Write the minimal branching flow implementation**

```python
def build_flow_payload(
    entry_ref: str,
    entities: list[EntityRecord],
    edges: list[EdgeRecord],
    max_depth: int = 4,
    max_branch_per_node: int = 4,
    max_nodes: int = 24,
) -> ArchitectureFlow:
    entity_by_id = {entity.entity_id: entity for entity in entities}
    outgoing = _build_flow_outgoing(edges)
    root = _resolve_flow_entry(entry_ref, entities, entity_by_id)
    if root is None:
        return ArchitectureFlow(flow_id=f"flow:{entry_ref}", entry={"kind": "file", "value": entry_ref}, scope="entity", steps=[], transitions=[], collapsed_subflows=[], evidence=[], warnings=[])

    queue = [(root.entity_id, 0)]
    seen = set()
    step_ids = {}
    steps = []
    transitions = []
    warnings = []

    while queue and len(steps) < max_nodes:
        entity_id, depth = queue.pop(0)
        if entity_id in seen:
            continue
        seen.add(entity_id)
        entity = entity_by_id[entity_id]
        step_id = f"step-{len(steps) + 1}"
        step_ids[entity_id] = step_id

        candidates = [
            edge for edge in _sorted_flow_edges(outgoing.get(entity_id, []))
            if edge.target_id in entity_by_id and edge.target_id not in seen
        ]
        visible = candidates[:max_branch_per_node]
        collapsed = max(0, len(candidates) - len(visible))

        steps.append(
            ArchitectureFlowStep(
                step_id=step_id,
                label=entity.name,
                node_kind="entity",
                ref=entity.entity_id,
                file_path=entity.file_path,
                depth=depth,
                child_count=len(candidates),
                visible_child_count=len(visible),
                collapsed_child_count=collapsed,
                evidence=[{"entity_id": entity.entity_id}],
            )
        )

        if depth >= max_depth:
            if candidates:
                warnings.append("max_depth_reached")
            continue

        for edge in visible:
            if len(steps) + len(queue) >= max_nodes:
                warnings.append("max_nodes_reached")
                break
            queue.append((edge.target_id, depth + 1))
            transitions.append({"source_entity_id": entity_id, "target_entity_id": edge.target_id, "edge_type": edge.edge_type, "evidence": [{"edge_id": edge.edge_id}]})
```

- [ ] **Step 4: Run the architecture tests**

Run: `pytest tests/test_architecture.py -v`
Expected: PASS for the new branching tests and existing architecture tests.

- [ ] **Step 5: Commit**

```bash
git add tests/test_architecture.py src/codeviz/architecture.py
git commit -m "feat: build branching flow payloads"
```

### Task 2: Layered Flow Layout Helper

**Files:**
- Create: `src/codeviz/web/flow-layout.js`
- Create: `tests/web/flow-layout.test.mjs`

- [ ] **Step 1: Write the failing frontend layout tests**

```javascript
test("buildFlowLayout places nodes by depth and separates siblings", () => {
  const layout = api.buildFlowLayout(
    [
      { id: "step-1", depth: 0, name: "main", file_path: "src/app.py" },
      { id: "step-2", depth: 1, name: "alpha", file_path: "src/a.py" },
      { id: "step-3", depth: 1, name: "beta", file_path: "src/b.py" },
    ],
    [
      { source: "step-1", target: "step-2", type: "calls" },
      { source: "step-1", target: "step-3", type: "calls" },
    ],
    1200,
    700,
  );

  assert.equal(layout.nodesById["step-1"].y < layout.nodesById["step-2"].y, true);
  assert.notEqual(layout.nodesById["step-2"].x, layout.nodesById["step-3"].x);
  assert.equal(layout.edges.length, 2);
});


test("buildFlowLayout keeps shared depth rows stable", () => {
  const layout = api.buildFlowLayout(
    [
      { id: "step-1", depth: 0, name: "main", file_path: "src/app.py" },
      { id: "step-2", depth: 1, name: "alpha", file_path: "src/a.py" },
      { id: "step-3", depth: 2, name: "gamma", file_path: "src/c.py" },
    ],
    [
      { source: "step-1", target: "step-2", type: "calls" },
      { source: "step-2", target: "step-3", type: "calls" },
    ],
    1200,
    700,
  );

  assert.equal(layout.nodesById["step-1"].depth, 0);
  assert.equal(layout.nodesById["step-3"].depth, 2);
  assert.match(layout.edges[0].path, /^M /);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test tests/web/flow-layout.test.mjs`
Expected: FAIL because `src/codeviz/web/flow-layout.js` does not exist yet.

- [ ] **Step 3: Write the minimal layout helper**

```javascript
function buildFlowLayout(nodes, links, canvasWidth, canvasHeight) {
  const width = Math.max(canvasWidth, 960);
  const layers = new Map();
  (nodes || []).forEach((node) => {
    const depth = Number.isFinite(node.depth) ? node.depth : 0;
    if (!layers.has(depth)) layers.set(depth, []);
    layers.get(depth).push(node);
  });

  const orderedDepths = [...layers.keys()].sort((a, b) => a - b);
  const layerGap = 150;
  const top = 96;
  const positions = {};

  orderedDepths.forEach((depth) => {
    const layerNodes = (layers.get(depth) || []).slice().sort((a, b) => String(a.name || "").localeCompare(String(b.name || "")));
    const gap = width / (layerNodes.length + 1);
    layerNodes.forEach((node, index) => {
      positions[node.id] = {
        ...node,
        depth,
        x: gap * (index + 1),
        y: top + depth * layerGap,
        width: 220,
        height: 64,
      };
    });
  });

  return {
    nodes: Object.values(positions),
    nodesById: positions,
    edges: (links || []).map((link) => {
      const source = positions[link.source];
      const target = positions[link.target];
      return {
        ...link,
        path: `M ${source.x} ${source.y + 32} C ${source.x} ${source.y + 96}, ${target.x} ${target.y - 96}, ${target.x} ${target.y - 32}`,
      };
    }),
  };
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `node --test tests/web/flow-layout.test.mjs`
Expected: PASS with 2 passing tests.

- [ ] **Step 5: Commit**

```bash
git add src/codeviz/web/flow-layout.js tests/web/flow-layout.test.mjs
git commit -m "feat: add layered flow layout"
```

### Task 3: Flow Renderer Integration

**Files:**
- Modify: `src/codeviz/web/app.js`
- Modify: `src/codeviz/web/index.html`
- Modify: `tests/web/view-search.test.mjs`

- [ ] **Step 1: Write the failing search and renderer tests**

```javascript
test("getSearchPlaceholder keeps flow search scoped to visible steps", () => {
  assert.equal(api.getSearchPlaceholder("flow"), "Search flow steps...");
});

test("filterVisibleNodes matches flow node labels and file paths", () => {
  const matches = api.filterVisibleNodes(
    [
      { id: "step-1", name: "main", file_path: "src/app.py" },
      { id: "step-2", name: "alpha", file_path: "src/a.py" },
    ],
    "alpha",
  );

  assert.deepEqual(matches.map((item) => item.id), ["step-2"]);
});
```

- [ ] **Step 2: Run tests to verify current frontend behavior**

Run: `node --test tests/web/view-search.test.mjs tests/web/flow-layout.test.mjs tests/web/flow-search.test.mjs`
Expected: PASS for search tests, PASS for layout tests, then manual review will still show `Flow` using the generic graph renderer.

- [ ] **Step 3: Wire `Flow` into a dedicated render path**

```javascript
function renderFlowGraph() {
  stopSimulation();
  ensureGraphDefs();
  const layout = flowLayoutApi
    ? flowLayoutApi.buildFlowLayout(states.flow.nodes, states.flow.links, width(), height())
    : { nodes: [], nodesById: {}, edges: [] };

  linkGroup.selectAll("*").remove();
  nodeGroup.selectAll("*").remove();
  g.selectAll(".arch-layer-label").remove();
  g.selectAll(".arch-lanes").remove();

  linkGroup
    .selectAll("path.flow-edge")
    .data(layout.edges, (item) => item.id)
    .enter()
    .append("path")
    .attr("class", "edge flow-edge")
    .attr("d", (item) => item.path)
    .attr("marker-end", "url(#flow-arrow)");

  const nodeEnter = nodeGroup
    .selectAll("g.flow-node")
    .data(layout.nodes, (item) => item.id)
    .enter()
    .append("g")
    .attr("class", "node flow-node")
    .attr("transform", (item) => `translate(${item.x},${item.y})`);

  nodeEnter.append("rect").attr("x", -110).attr("y", -32).attr("width", 220).attr("height", 64).attr("rx", 12);
  nodeEnter.append("text").attr("class", "flow-node-title").attr("x", -94).attr("y", -4).text((item) => item.name);
  nodeEnter.append("text").attr("class", "flow-node-meta").attr("x", -94).attr("y", 16).text((item) => item.file_path || "");
}

if (nextView === "flow") {
  bindState("flow");
  renderFlowGraph();
  renderDetailMessage(defaultDetailMessage());
  updateStats({ entities: nodes.length, edges: links.length });
  return;
}
```

- [ ] **Step 4: Run frontend tests and build**

Run: `node --test tests/web/view-search.test.mjs tests/web/flow-layout.test.mjs tests/web/flow-search.test.mjs tests/web/architecture-interactions.test.mjs tests/web/architecture-layout.test.mjs`
Expected: PASS

Run: `npm run build:web`
Expected: PASS with `copied .../src/codeviz/web -> .../dist/web`

- [ ] **Step 5: Commit**

```bash
git add src/codeviz/web/app.js src/codeviz/web/index.html tests/web/view-search.test.mjs
git add src/codeviz/web/flow-layout.js tests/web/flow-layout.test.mjs
git commit -m "feat: render flow as layered diagram"
```
