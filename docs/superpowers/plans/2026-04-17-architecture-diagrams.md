# Architecture Diagrams Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add derived architecture and flow diagram data, API access, and center-canvas tabs for `Code Graph`, `Architecture`, and `Flow` without placeholder functions or mock data.

**Architecture:** Extend the existing snapshot pipeline with deterministic derived assets for modules and flows, then expose them through project/server payloads consumed by the current single-page UI. Reuse the current graph canvas and sidebars, switching data sources by active tab instead of adding a new page or second design system.

**Tech Stack:** Python 3.12, pytest, static HTML/CSS/JS, D3, Mermaid text export

---

## File Map

- Modify: `src/codeviz/models.py`
  - add architecture and flow dataclasses
- Modify: `src/codeviz/storage.py`
  - save/load helpers for derived assets
- Modify: `src/codeviz/analysis.py`
  - generate derived assets after base extraction completes
- Create: `src/codeviz/architecture.py`
  - deterministic module segmentation, dependency aggregation, flow generation
- Modify: `src/codeviz/project.py`
  - expose architecture and flow payloads
- Modify: `src/codeviz/server.py`
  - add architecture and flow endpoints
- Modify: `src/codeviz/web/index.html`
  - add center-canvas tab UI and flow controls
- Modify: `src/codeviz/web/app.js`
  - switch between code graph, architecture graph, and flow graph
- Modify: `tests/test_storage.py`
  - cover derived asset persistence
- Create: `tests/test_architecture.py`
  - cover module segmentation, dependency aggregation, flow generation
- Modify: `tests/test_project_integration.py`
  - cover new project payloads

### Task 1: Derived Asset Models And Storage

**Files:**
- Create: `src/codeviz/architecture.py`
- Modify: `src/codeviz/models.py`
- Modify: `src/codeviz/storage.py`
- Test: `tests/test_storage.py`
- Test: `tests/test_architecture.py`

- [ ] **Step 1: Write the failing storage tests**

```python
from codeviz.models import (
    ArchitectureDependency,
    ArchitectureFlow,
    ArchitectureFlowStep,
    ArchitectureModule,
)
from codeviz.storage import (
    load_architecture,
    load_flow_index,
    save_architecture,
    save_flow_index,
)


def test_save_and_load_architecture_assets(tmp_path: Path) -> None:
    status = _make_status(tmp_path)
    ensure_layout(status)
    module = ArchitectureModule(
        module_id="src/codeviz",
        display_name="codeviz core",
        source_dirs=["src/codeviz"],
        file_paths=["src/codeviz/project.py"],
        entity_ids=["function:src/codeviz/project.py:analyze:1"],
        merge_reason="directory",
        confidence="high",
    )
    dependency = ArchitectureDependency(
        source_module_id="src/codeviz",
        target_module_id="src/codeviz/web",
        dominant_edge_type="imports",
        imports_count=1,
        calls_count=0,
        uses_count=0,
        strength=1,
        evidence=[{"source_file": "src/codeviz/project.py", "target_file": "src/codeviz/web/app.js"}],
    )
    save_architecture(status, [module], [dependency], {"root_modules": 1})
    payload = load_architecture(status)
    assert payload["modules"][0]["display_name"] == "codeviz core"
    assert payload["dependencies"][0]["dominant_edge_type"] == "imports"


def test_save_and_load_flow_index(tmp_path: Path) -> None:
    status = _make_status(tmp_path)
    ensure_layout(status)
    flow = ArchitectureFlow(
        flow_id="flow:analyze",
        entry={"kind": "entity", "value": "function:src/codeviz/project.py:analyze:1"},
        scope="entity",
        steps=[
            ArchitectureFlowStep(
                step_id="step-1",
                label="Analyze project",
                node_kind="entity",
                ref="function:src/codeviz/project.py:analyze:1",
                file_path="src/codeviz/project.py",
                evidence=[{"entity_id": "function:src/codeviz/project.py:analyze:1"}],
            )
        ],
        transitions=[],
        collapsed_subflows=[],
        evidence=[],
        warnings=[],
    )
    save_flow_index(status, {"entity": [{"label": "Analyze project", "value": "function:src/codeviz/project.py:analyze:1"}]}, [flow])
    payload = load_flow_index(status)
    assert payload["entries"]["entity"][0]["label"] == "Analyze project"
    assert payload["flows"][0]["flow_id"] == "flow:analyze"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_storage.py -k "architecture or flow" -v`

Expected: FAIL with import or attribute errors for missing architecture model and storage helpers.

- [ ] **Step 3: Write minimal models and storage implementation**

```python
@dataclass(slots=True)
class ArchitectureModule:
    module_id: str
    display_name: str
    source_dirs: list[str]
    file_paths: list[str]
    entity_ids: list[str]
    merge_reason: str
    confidence: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "module_id": self.module_id,
            "display_name": self.display_name,
            "source_dirs": self.source_dirs,
            "file_paths": self.file_paths,
            "entity_ids": self.entity_ids,
            "merge_reason": self.merge_reason,
            "confidence": self.confidence,
        }


def save_architecture(status: ProjectStatus, modules: list[ArchitectureModule], dependencies: list[ArchitectureDependency], meta: dict) -> None:
    _atomic_write(
        status.current_dir / "architecture.json",
        {
            "modules": [item.to_dict() for item in modules],
            "dependencies": [item.to_dict() for item in dependencies],
            "meta": meta,
        },
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_storage.py -k "architecture or flow" -v`

Expected: PASS for the new persistence tests.

- [ ] **Step 5: Commit**

```bash
git add src/codeviz/models.py src/codeviz/storage.py tests/test_storage.py
git commit -m "feat: add architecture asset storage"
```

### Task 2: Deterministic Architecture And Flow Derivation

**Files:**
- Create: `src/codeviz/architecture.py`
- Modify: `src/codeviz/analysis.py`
- Test: `tests/test_architecture.py`

- [ ] **Step 1: Write the failing derivation tests**

```python
from codeviz.architecture import build_architecture_snapshot, build_flow_payload
from codeviz.models import EdgeRecord, EntityRecord, FileRecord


def test_build_architecture_snapshot_groups_entities_into_modules() -> None:
    files = [
        FileRecord(path="src/codeviz/project.py", language="python", content_hash="a"),
        FileRecord(path="src/codeviz/server.py", language="python", content_hash="b"),
        FileRecord(path="src/codeviz/web/app.js", language="javascript", content_hash="c"),
    ]
    entities = [
        EntityRecord(entity_id="function:src/codeviz/project.py:analyze:1", entity_type="function", name="analyze", file_path="src/codeviz/project.py", start_line=1, end_line=10),
        EntityRecord(entity_id="function:src/codeviz/server.py:start:1", entity_type="function", name="start", file_path="src/codeviz/server.py", start_line=1, end_line=10),
    ]
    edges = [
        EdgeRecord(edge_id="e1", source_id="function:src/codeviz/project.py:analyze:1", target_id="function:src/codeviz/server.py:start:1", edge_type="calls", file_path="src/codeviz/project.py", line=4),
    ]
    snapshot = build_architecture_snapshot(files, entities, edges)
    assert [module.display_name for module in snapshot.modules] == ["codeviz", "web"]
    assert snapshot.dependencies[0].calls_count == 1


def test_build_flow_payload_follows_entity_calls() -> None:
    entities = [
        EntityRecord(entity_id="function:src/codeviz/project.py:analyze:1", entity_type="function", name="analyze", file_path="src/codeviz/project.py", start_line=1, end_line=10),
        EntityRecord(entity_id="function:src/codeviz/server.py:start:1", entity_type="function", name="start", file_path="src/codeviz/server.py", start_line=1, end_line=10),
    ]
    edges = [
        EdgeRecord(edge_id="e1", source_id="function:src/codeviz/project.py:analyze:1", target_id="function:src/codeviz/server.py:start:1", edge_type="calls", file_path="src/codeviz/project.py", line=4),
    ]
    flow = build_flow_payload("function:src/codeviz/project.py:analyze:1", entities, edges)
    assert [step.label for step in flow.steps] == ["analyze", "start"]
    assert flow.transitions[0]["source"] == "step-1"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_architecture.py -v`

Expected: FAIL because `build_architecture_snapshot` and `build_flow_payload` do not exist yet.

- [ ] **Step 3: Write minimal deterministic derivation code**

```python
def build_architecture_snapshot(files: list[FileRecord], entities: list[EntityRecord], edges: list[EdgeRecord]) -> ArchitectureSnapshot:
    modules = _build_modules(files, entities)
    dependencies = _build_dependencies(modules, entities, edges)
    return ArchitectureSnapshot(modules=modules, dependencies=dependencies, meta={"root_modules": len(modules)})


def build_flow_payload(entry_ref: str, entities: list[EntityRecord], edges: list[EdgeRecord], max_steps: int = 12) -> ArchitectureFlow:
    entity_by_id = {entity.entity_id: entity for entity in entities}
    outgoing = {}
    for edge in edges:
        if edge.edge_type not in {"calls", "imports", "uses"}:
            continue
        outgoing.setdefault(edge.source_id, []).append(edge)
    current = entry_ref
    steps = []
    transitions = []
    seen = set()
    while current in entity_by_id and current not in seen and len(steps) < max_steps:
        seen.add(current)
        entity = entity_by_id[current]
        step_id = f"step-{len(steps) + 1}"
        steps.append(ArchitectureFlowStep(step_id=step_id, label=entity.name, node_kind="entity", ref=entity.entity_id, file_path=entity.file_path, evidence=[{"entity_id": entity.entity_id}]))
        candidates = outgoing.get(current, [])
        if not candidates:
            break
        next_edge = candidates[0]
        next_step_id = f"step-{len(steps) + 1}"
        transitions.append({"source": step_id, "target": next_step_id, "edge_type": next_edge.edge_type, "evidence": [{"edge_id": next_edge.edge_id}]})
        current = next_edge.target_id
    return ArchitectureFlow(
        flow_id=f"flow:{entry_ref}",
        entry={"kind": "entity", "value": entry_ref},
        scope="entity",
        steps=steps,
        transitions=transitions,
        collapsed_subflows=[],
        evidence=[],
        warnings=[],
    )
```

- [ ] **Step 4: Persist derived assets during analysis**

```python
snapshot = build_architecture_snapshot(files, deduped_entities, deduped_edges)
save_architecture(status, snapshot.modules, snapshot.dependencies, snapshot.meta)
save_flow_index(status, snapshot.flow_index, [])
save_diagrams(status, snapshot.diagrams)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_architecture.py tests/test_storage.py -v`

Expected: PASS for new derivation and storage coverage.

- [ ] **Step 6: Commit**

```bash
git add src/codeviz/architecture.py src/codeviz/analysis.py tests/test_architecture.py tests/test_storage.py
git commit -m "feat: derive architecture and flow assets"
```

### Task 3: Project And Server API Support

**Files:**
- Modify: `src/codeviz/project.py`
- Modify: `src/codeviz/server.py`
- Modify: `tests/test_project_integration.py`

- [ ] **Step 1: Write the failing project payload tests**

```python
def test_architecture_payload_returns_modules_and_dependencies(fixture_project: Path, monkeypatch) -> None:
    monkeypatch.setattr(CodeVizServer, "start", fake_server_start)
    project = CodeVizProject(fixture_project)
    project.analyze()
    payload = project.architecture_payload()
    assert payload["ok"] is True
    assert "modules" in payload
    assert "dependencies" in payload


def test_flow_payload_returns_candidates_for_unknown_entry(fixture_project: Path, monkeypatch) -> None:
    monkeypatch.setattr(CodeVizServer, "start", fake_server_start)
    project = CodeVizProject(fixture_project)
    project.analyze()
    payload = project.flow_payload("missing-entry")
    assert payload["ok"] is False
    assert payload["error"] == "entry_not_found"
    assert isinstance(payload["candidates"], list)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_project_integration.py -k "architecture_payload or flow_payload" -v`

Expected: FAIL because the new project methods do not exist.

- [ ] **Step 3: Add project payload methods and server routes**

```python
def architecture_payload(self) -> dict:
    payload = load_architecture(self.status)
    return {"ok": True, **payload}


def flow_payload(self, entry: str) -> dict:
    payload = load_flow_index(self.status)
    flow = next((item for item in payload["flows"] if item["entry"]["value"] == entry), None)
    if flow is None:
        candidates = []
        for entries in payload["entries"].values():
            candidates.extend(entries)
        return {"ok": False, "error": "entry_not_found", "candidates": candidates[:10]}
    return {"ok": True, **flow}
```

- [ ] **Step 4: Wire HTTP endpoints**

```python
if parsed.path == "/api/architecture":
    return self._send_json(self.project.architecture_payload())

if parsed.path == "/api/flow/index":
    return self._send_json(self.project.flow_index_payload())

if parsed.path == "/api/flow":
    params = parse_qs(parsed.query)
    entry = params.get("entry", [""])[0]
    return self._send_json(self.project.flow_payload(entry))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_project_integration.py -v`

Expected: PASS with the new architecture and flow payload coverage included.

- [ ] **Step 6: Commit**

```bash
git add src/codeviz/project.py src/codeviz/server.py tests/test_project_integration.py
git commit -m "feat: expose architecture and flow APIs"
```

### Task 4: Center-Canvas Tabs And Derived Views

**Files:**
- Modify: `src/codeviz/web/index.html`
- Modify: `src/codeviz/web/app.js`

- [ ] **Step 1: Add the tab shell and flow controls**

```html
<div id="view-tabs" class="view-tabs">
  <button class="view-tab active" data-view="code">Code Graph</button>
  <button class="view-tab" data-view="architecture">Architecture</button>
  <button class="view-tab" data-view="flow">Flow</button>
</div>
<div id="flow-controls" class="flow-controls" hidden>
  <input id="flow-entry-input" type="text" placeholder="Enter file path or entity id">
  <button id="flow-run-button" type="button">Generate</button>
</div>
```

- [ ] **Step 2: Render each tab from its own data source**

```javascript
let activeView = "code";
let architecturePayload = { modules: [], dependencies: [] };
let flowPayload = { steps: [], transitions: [] };

function setActiveView(nextView) {
  activeView = nextView;
  document.querySelectorAll(".view-tab").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === nextView);
  });
  document.getElementById("flow-controls").hidden = nextView !== "flow";
  if (nextView === "code") renderCodeGraph();
  if (nextView === "architecture") renderArchitectureGraph();
  if (nextView === "flow") renderFlowGraph();
}
```

- [ ] **Step 3: Implement architecture and flow fetch/render paths**

```javascript
function loadArchitecture() {
  return fetch("/api/architecture")
    .then((response) => response.json())
    .then((payload) => {
      architecturePayload = payload;
      if (activeView === "architecture") renderArchitectureGraph();
    });
}

function loadFlow(entry) {
  return fetch(`/api/flow?entry=${encodeURIComponent(entry)}`)
    .then((response) => response.json())
    .then((payload) => {
      flowPayload = payload.ok ? payload : { steps: [], transitions: [], error: payload.error, candidates: payload.candidates || [] };
      renderFlowGraph();
    });
}
```

- [ ] **Step 4: Preserve visual consistency**

```css
.view-tabs {
  position: absolute;
  top: 12px;
  left: 12px;
  display: flex;
  gap: 8px;
  z-index: 3;
}

.view-tab {
  background: rgba(22, 27, 34, .92);
  color: var(--fg2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 6px 10px;
}

.view-tab.active {
  color: var(--fg);
  border-color: var(--accent);
}
```

- [ ] **Step 5: Verify the UI manually**

Run:

```bash
python -m codeviz analyze /Users/hmj/Desktop/project/show-your-code --no-browser
python -m codeviz open /Users/hmj/Desktop/project/show-your-code --no-browser
```

Expected:

- the center canvas shows `Code Graph`, `Architecture`, and `Flow` tabs
- the current theme is preserved
- `Architecture` shows aggregated module nodes
- `Flow` accepts a real entry id and renders a real flow path

- [ ] **Step 6: Commit**

```bash
git add src/codeviz/web/index.html src/codeviz/web/app.js
git commit -m "feat: add architecture and flow tabs"
```

### Task 5: Full Verification

**Files:**
- Modify: none
- Test: `tests/test_storage.py`
- Test: `tests/test_architecture.py`
- Test: `tests/test_project_integration.py`

- [ ] **Step 1: Run focused test suite**

Run: `pytest tests/test_storage.py tests/test_architecture.py tests/test_project_integration.py -v`

Expected: PASS with zero failures.

- [ ] **Step 2: Run broader regression suite**

Run: `pytest -v`

Expected: PASS with zero failures.

- [ ] **Step 3: Smoke the CLI and UI**

Run:

```bash
python -m codeviz analyze /Users/hmj/Desktop/project/show-your-code --no-browser --json
python -m codeviz open /Users/hmj/Desktop/project/show-your-code --no-browser --json
```

Expected:

- analyze JSON includes graph summary
- open JSON includes a localhost URL
- `/api/architecture` and `/api/flow/index` return non-empty payloads for this repository
```
