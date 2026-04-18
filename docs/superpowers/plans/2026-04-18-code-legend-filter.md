# Code Legend Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add clickable legend filters in the `Code` view so users can hide one or more node types and automatically remove edges attached to hidden nodes.

**Architecture:** Keep `states.code.nodes` and `states.code.links` as the raw graph source in `src/codeviz/web/app.js`, and add one small pure helper that derives the visible code subset from the legend state. Wire the legend UI directly in the existing single-page frontend so the canvas filters only the `Code` view while search and detail panels keep using the full raw data.

**Tech Stack:** static HTML/CSS/JS, D3, Node `node:test`

---

## File Map

- Create: `src/codeviz/web/code-legend-filter.js`
  - pure helpers for supported legend types, hidden-type toggling, and visible node/link derivation
- Modify: `src/codeviz/web/app.js`
  - track `hiddenCodeTypes`, render clickable legend state, derive visible code graph for the `Code` view, and keep search bound to raw data
- Modify: `src/codeviz/web/index.html`
  - turn static code legend items into buttons and add active/inactive styles
- Create: `tests/web/code-legend-filter.test.mjs`
  - cover visible subset derivation and hidden-type toggle behavior

### Task 1: Pure Code Legend Filter Helper

**Files:**
- Create: `src/codeviz/web/code-legend-filter.js`
- Create: `tests/web/code-legend-filter.test.mjs`

- [ ] **Step 1: Write the failing tests**

```javascript
import test from "node:test";
import assert from "node:assert/strict";

await import("../../src/codeviz/web/code-legend-filter.js");

const api = globalThis.CodeLegendFilter;

test("toggleHiddenType adds and removes code legend types", () => {
  const hidden = new Set();

  const nextHidden = api.toggleHiddenType(hidden, "function");
  assert.deepEqual([...nextHidden], ["function"]);

  const restored = api.toggleHiddenType(nextHidden, "function");
  assert.deepEqual([...restored], []);
});

test("buildVisibleCodeGraph removes hidden-type nodes and connected edges", () => {
  const nodes = [
    { id: "class:a", type: "class" },
    { id: "function:b", type: "function" },
    { id: "method:c", type: "method" },
  ];
  const links = [
    { id: "a:b", source: "class:a", target: "function:b" },
    { id: "a:c", source: "class:a", target: "method:c" },
  ];

  const visible = api.buildVisibleCodeGraph(nodes, links, new Set(["function"]));

  assert.deepEqual(visible.nodes.map((node) => node.id), ["class:a", "method:c"]);
  assert.deepEqual(visible.links.map((link) => link.id), ["a:c"]);
});

test("buildVisibleCodeGraph keeps non-filtered types untouched", () => {
  const nodes = [
    { id: "enum:a", type: "enum" },
    { id: "class:b", type: "class" },
  ];
  const links = [
    { id: "enum:class", source: "enum:a", target: "class:b" },
  ];

  const visible = api.buildVisibleCodeGraph(nodes, links, new Set(["function"]));

  assert.deepEqual(visible.nodes.map((node) => node.id), ["enum:a", "class:b"]);
  assert.deepEqual(visible.links.map((link) => link.id), ["enum:class"]);
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `node --test tests/web/code-legend-filter.test.mjs`

Expected: FAIL because `CodeLegendFilter` is not defined yet.

- [ ] **Step 3: Write the minimal helper implementation**

```javascript
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.CodeLegendFilter = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const SUPPORTED_CODE_LEGEND_TYPES = ["class", "function", "method", "interface", "module"];

  function nodeIdOf(endpoint) {
    return typeof endpoint === "object" ? endpoint.id : endpoint;
  }

  function toggleHiddenType(hiddenTypes, type) {
    const next = new Set(hiddenTypes || []);
    if (next.has(type)) {
      next.delete(type);
    } else {
      next.add(type);
    }
    return next;
  }

  function buildVisibleCodeGraph(nodes, links, hiddenTypes) {
    const hidden = new Set(hiddenTypes || []);
    const visibleNodes = (nodes || []).filter((node) => !hidden.has(node.type));
    const visibleNodeIds = new Set(visibleNodes.map((node) => node.id));
    const visibleLinks = (links || []).filter((link) => (
      visibleNodeIds.has(nodeIdOf(link.source)) &&
      visibleNodeIds.has(nodeIdOf(link.target))
    ));
    return {
      nodes: visibleNodes,
      links: visibleLinks,
      nodeIds: visibleNodeIds,
    };
  }

  return {
    SUPPORTED_CODE_LEGEND_TYPES,
    toggleHiddenType,
    buildVisibleCodeGraph,
  };
});
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `node --test tests/web/code-legend-filter.test.mjs`

Expected: PASS for all legend filter helper tests.

### Task 2: Wire Code Legend Buttons Into The Frontend

**Files:**
- Modify: `src/codeviz/web/app.js`
- Modify: `src/codeviz/web/index.html`
- Test: `tests/web/code-legend-filter.test.mjs`

- [ ] **Step 1: Add one failing helper test for supported legend types**

```javascript
test("SUPPORTED_CODE_LEGEND_TYPES matches the clickable code legend", () => {
  assert.deepEqual(api.SUPPORTED_CODE_LEGEND_TYPES, [
    "class",
    "function",
    "method",
    "interface",
    "module",
  ]);
});
```

- [ ] **Step 2: Run the tests to verify the red state if needed**

Run: `node --test tests/web/code-legend-filter.test.mjs`

Expected: FAIL only if the exported legend type list is missing or incorrect. If the list already passes, keep the suite green and continue.

- [ ] **Step 3: Update the legend markup and styles**

```html
<div id="legend">
  <label class="legend-item legend-toggle" style="cursor:pointer;gap:6px;align-items:center;display:flex;">
    <input id="label-toggle" type="checkbox" checked>
    <span>label</span>
  </label>
  <button class="legend-item legend-filter active" type="button" data-code-type="class">
    <span class="legend-dot" style="background:var(--accent)"></span>class
  </button>
  <button class="legend-item legend-filter active" type="button" data-code-type="function">
    <span class="legend-dot" style="background:var(--green)"></span>function
  </button>
  <button class="legend-item legend-filter active" type="button" data-code-type="method">
    <span class="legend-dot" style="background:var(--purple)"></span>method
  </button>
  <button class="legend-item legend-filter active" type="button" data-code-type="interface">
    <span class="legend-dot" style="background:var(--yellow)"></span>interface
  </button>
  <button class="legend-item legend-filter active" type="button" data-code-type="module">
    <span class="legend-dot" style="background:var(--orange)"></span>module
  </button>
</div>
```

```css
.legend-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.legend-filter {
  border: 1px solid transparent;
  background: transparent;
  color: var(--fg);
  border-radius: 999px;
  padding: 4px 8px;
  cursor: pointer;
}

.legend-filter.active {
  background: rgba(255, 255, 255, .04);
}

.legend-filter:not(.active) {
  color: var(--fg2);
  opacity: .62;
}
```

- [ ] **Step 4: Update app state, legend syncing, and visible code graph rendering**

```javascript
const codeLegendFilterApi = globalThis.CodeLegendFilter || null;
const codeLegendButtons = Array.from(document.querySelectorAll("[data-code-type]"));
let hiddenCodeTypes = new Set();

function visibleCodeGraph() {
  if (activeView !== "code") {
    return { nodes, links, nodeIds: new Set(nodes.map((node) => node.id)) };
  }
  if (!codeLegendFilterApi) {
    return { nodes, links, nodeIds: new Set(nodes.map((node) => node.id)) };
  }
  return codeLegendFilterApi.buildVisibleCodeGraph(states.code.nodes, states.code.links, hiddenCodeTypes);
}

function syncCodeLegend() {
  codeLegendButtons.forEach((button) => {
    const type = button.dataset.codeType;
    const active = !hiddenCodeTypes.has(type);
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  });
}

codeLegendButtons.forEach((button) => {
  button.addEventListener("click", () => {
    const type = button.dataset.codeType;
    hiddenCodeTypes = codeLegendFilterApi.toggleHiddenType(hiddenCodeTypes, type);
    syncCodeLegend();
    if (activeView !== "code") return;
    initSimulation();
    renderGraph();
    updateStats({ entities: states.code.nodes.length, edges: states.code.links.length });
  });
});
```

```javascript
function renderGraph() {
  const graph = activeView === "code" && codeLegendFilterApi
    ? codeLegendFilterApi.buildVisibleCodeGraph(states.code.nodes, states.code.links, hiddenCodeTypes)
    : { nodes, links };

  nodes = graph.nodes;
  links = graph.links;
  entityMap = activeView === "code"
    ? Object.fromEntries(graph.nodes.map((node) => [node.id, states.code.entityMap[node.id] || node]))
    : states[activeView].entityMap;
  updateNodeDegrees();
  ...
}
```

- [ ] **Step 5: Run the focused tests and build**

Run: `node --test tests/web/code-legend-filter.test.mjs tests/web/code-layout.test.mjs tests/web/view-search.test.mjs`

Expected: PASS, proving legend filtering works and search helpers remain raw-data based.

Run: `npm run build:web`

Expected: PASS with `copied ...src/codeviz/web -> ...dist/web`.

### Task 3: Full Web Verification

**Files:**
- Modify: `src/codeviz/web/app.js`
- Modify: `src/codeviz/web/index.html`
- Create: `src/codeviz/web/code-legend-filter.js`
- Create: `tests/web/code-legend-filter.test.mjs`

- [ ] **Step 1: Run the full web test suite**

Run: `node --test tests/web/*.test.mjs`

Expected: PASS for all web tests, including the new legend filter suite.

- [ ] **Step 2: Rebuild the shipped frontend assets**

Run: `npm run build:web`

Expected: PASS with the updated `dist/web` copy step.

- [ ] **Step 3: Commit the implementation**

```bash
git add src/codeviz/web/app.js src/codeviz/web/index.html src/codeviz/web/code-legend-filter.js tests/web/code-legend-filter.test.mjs docs/superpowers/plans/2026-04-18-code-legend-filter.md
git commit -m "feat: add code legend filters"
```
