# Architecture Interaction Adjustments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add hover-based relationship highlighting and one-level back navigation in the `Architecture` view while keeping existing click-to-drill-down behavior.

**Architecture:** Keep the current `module -> file -> entity` rendering flow in `src/codeviz/web/app.js`, and add a small pure helper surface for architecture-specific highlight and back-navigation state so behavior can be tested without a browser harness. Update the single-page UI in place by adding one in-canvas back button that only appears on drilled-down architecture levels.

**Tech Stack:** static HTML/CSS/JS, D3, Node `node:test`

---

## File Map

- Create: `src/codeviz/web/architecture-interactions.js`
  - pure helpers for direct-neighbor highlight state and back-target resolution
- Modify: `src/codeviz/web/app.js`
  - wire hover highlight, drill-down context, and back behavior into the Architecture view
- Modify: `src/codeviz/web/index.html`
  - add the back button and minimal styles
- Create: `tests/web/architecture-interactions.test.mjs`
  - cover highlight adjacency and previous-level resolution

### Task 1: Pure Architecture Interaction Helpers

**Files:**
- Create: `src/codeviz/web/architecture-interactions.js`
- Create: `tests/web/architecture-interactions.test.mjs`

- [ ] **Step 1: Write the failing tests**

```javascript
import test from "node:test";
import assert from "node:assert/strict";

await import("../../src/codeviz/web/architecture-interactions.js");

const api = globalThis.ArchitectureInteractions;

test("buildHighlightState includes directly connected nodes and edges", () => {
  const links = [
    { id: "a:b", source: "module:a", target: "module:b" },
    { id: "b:c", source: "module:b", target: "module:c" },
  ];

  const state = api.buildHighlightState("module:b", links);

  assert.deepEqual([...state.nodeIds].sort(), ["module:a", "module:b", "module:c"]);
  assert.deepEqual([...state.edgeIds].sort(), ["a:b", "b:c"]);
});

test("getBackTarget returns module level from file level", () => {
  const target = api.getBackTarget("file", {
    moduleId: "src/codeviz",
    filePath: "src/codeviz/web/app.js",
  });

  assert.deepEqual(target, {
    viewMode: "module",
    moduleId: null,
    filePath: null,
  });
});

test("getBackTarget returns file level from entity level", () => {
  const target = api.getBackTarget("entity", {
    moduleId: "src/codeviz/web",
    filePath: "src/codeviz/web/app.js",
  });

  assert.deepEqual(target, {
    viewMode: "file",
    moduleId: "src/codeviz/web",
    filePath: null,
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `node --test tests/web/architecture-interactions.test.mjs`

Expected: FAIL because `ArchitectureInteractions` is not defined yet.

- [ ] **Step 3: Write the minimal helper implementation**

```javascript
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.ArchitectureInteractions = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  function nodeIdOf(endpoint) {
    return typeof endpoint === "object" ? endpoint.id : endpoint;
  }

  function buildHighlightState(nodeId, links) {
    const nodeIds = new Set([nodeId]);
    const edgeIds = new Set();
    links.forEach((link) => {
      const sourceId = nodeIdOf(link.source);
      const targetId = nodeIdOf(link.target);
      if (sourceId !== nodeId && targetId !== nodeId) return;
      nodeIds.add(sourceId);
      nodeIds.add(targetId);
      edgeIds.add(link.id);
    });
    return { nodeIds, edgeIds };
  }

  function getBackTarget(viewMode, context) {
    if (viewMode === "entity") {
      return {
        viewMode: "file",
        moduleId: context.moduleId || null,
        filePath: null,
      };
    }
    return {
      viewMode: "module",
      moduleId: null,
      filePath: null,
    };
  }

  return {
    buildHighlightState,
    getBackTarget,
  };
});
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `node --test tests/web/architecture-interactions.test.mjs`

Expected: PASS for all helper tests.

### Task 2: Wire Hover Highlight And Back Navigation Into The App

**Files:**
- Modify: `src/codeviz/web/app.js`
- Modify: `src/codeviz/web/index.html`
- Test: `tests/web/architecture-interactions.test.mjs`

- [ ] **Step 1: Add one failing test for file-level back resolution**

```javascript
test("getBackTarget preserves module id when returning from entity level", () => {
  const target = api.getBackTarget("entity", {
    moduleId: "src/codeviz/web",
    filePath: "src/codeviz/web/app.js",
  });

  assert.equal(target.viewMode, "file");
  assert.equal(target.moduleId, "src/codeviz/web");
});
```

- [ ] **Step 2: Run the tests to verify the red state if needed**

Run: `node --test tests/web/architecture-interactions.test.mjs`

Expected: FAIL only if the helper contract is still incomplete. If already covered by Task 1, keep the existing passing suite and continue.

- [ ] **Step 3: Update the UI markup and styles**

```html
<div id="graph-area">
  <div id="view-tabs" class="view-tabs">
    ...
  </div>
  <button id="architecture-back-button" class="graph-action" type="button" hidden>Back</button>
  <div id="flow-controls" class="flow-controls" hidden>
```

```css
.graph-action {
  position: absolute;
  top: 56px;
  left: 12px;
  z-index: 6;
  border: 1px solid var(--border);
  background: rgba(22, 27, 34, .92);
  color: var(--fg);
  border-radius: var(--radius);
  padding: 6px 10px;
  font-size: 12px;
  cursor: pointer;
}

.graph-action:hover {
  border-color: var(--accent);
}
```

- [ ] **Step 4: Update the app logic with minimal state and handlers**

```javascript
const architectureInteractionsApi = globalThis.ArchitectureInteractions || null;
const architectureBackButton = document.getElementById("architecture-back-button");
let architectureContext = { moduleId: null, filePath: null };

function setArchitectureContext(next) {
  architectureContext = {
    moduleId: next.moduleId || null,
    filePath: next.filePath || null,
  };
}

function syncArchitectureBackButton() {
  const show = activeView === "architecture" && architectureViewMode !== "module";
  architectureBackButton.hidden = !show;
}

function applyArchitectureHighlight(nodeId) {
  const state = architectureInteractionsApi
    ? architectureInteractionsApi.buildHighlightState(nodeId, states.architecture.links)
    : { nodeIds: new Set([nodeId]), edgeIds: new Set() };

  nodeGroup
    .selectAll("g.node")
    .attr("opacity", (d) => (state.nodeIds.has(d.id) ? 1 : 0.18));

  linkGroup
    .selectAll(activeView === "architecture" && architectureViewMode === "module" ? "path.arch-edge" : "line")
    .attr("stroke-opacity", (d) => (state.edgeIds.has(d.id) ? 0.92 : 0.08));
}

function clearArchitectureHighlight() {
  nodeGroup.selectAll("g.node").attr("opacity", 1);
  linkGroup.selectAll("path.arch-edge, line").attr("stroke-opacity", null);
}
```

- [ ] **Step 5: Use the new handlers in architecture rendering**

```javascript
nodeGroup
  .selectAll("g.arch-node")
  .on("mouseover", (event, d) => {
    showTooltip(event, d);
    applyArchitectureHighlight(d.id);
  })
  .on("mouseout", () => {
    hideTooltip();
    clearArchitectureHighlight();
  })
  .on("click", (event, d) => selectNode(d));
```

```javascript
mergedNodes
  .on("mouseover", (event, d) => {
    showTooltip(event, d);
    if (activeView === "architecture") {
      applyArchitectureHighlight(d.id);
      return;
    }
  })
  .on("mouseout", () => {
    hideTooltip();
    if (activeView === "architecture") {
      clearArchitectureHighlight();
      return;
    }
  });
```

- [ ] **Step 6: Preserve parent context during drill-down and support back**

```javascript
function renderArchitectureModuleView() {
  architectureViewMode = "module";
  selectedNode = null;
  setArchitectureContext({ moduleId: null, filePath: null });
  renderArchitectureDiagram();
  syncArchitectureBackButton();
}

function renderArchitectureFileView(moduleId) {
  architectureViewMode = "file";
  selectedNode = null;
  setArchitectureContext({ moduleId, filePath: null });
  ...
  syncArchitectureBackButton();
}

function renderArchitectureEntityView(filePath) {
  architectureViewMode = "entity";
  selectedNode = null;
  setArchitectureContext({ moduleId: architectureContext.moduleId, filePath });
  ...
  syncArchitectureBackButton();
}

function goBackArchitectureLevel() {
  const target = architectureInteractionsApi
    ? architectureInteractionsApi.getBackTarget(architectureViewMode, architectureContext)
    : { viewMode: "module", moduleId: null, filePath: null };

  if (target.viewMode === "file" && target.moduleId) {
    renderArchitectureFileView(target.moduleId);
    return;
  }
  renderArchitectureModuleView();
}

architectureBackButton.addEventListener("click", () => {
  goBackArchitectureLevel();
});
```

- [ ] **Step 7: Run the focused tests and the existing layout tests**

Run: `node --test tests/web/architecture-interactions.test.mjs tests/web/architecture-layout.test.mjs`

Expected: PASS for the new interaction helpers and the existing architecture layout suite.

- [ ] **Step 8: Run the web bundle build**

Run: `npm run build:web`

Expected: PASS with no build errors.
