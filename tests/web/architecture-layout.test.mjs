import test from "node:test";
import assert from "node:assert/strict";
await import("../../src/codeviz/web/architecture-layout.js");
const layoutApi = globalThis.ArchitectureLayout;

test("buildArchitectureLayout places modules into multiple layers and routes edges", () => {
  const modules = [
    { module_id: "bin/codeviz", display_name: "codeviz", file_paths: ["bin/codeviz.js"], entity_ids: ["e1"] },
    { module_id: "src/codeviz/project", display_name: "project", file_paths: ["src/codeviz/project.py"], entity_ids: ["e2", "e3"] },
    { module_id: "src/codeviz/storage", display_name: "storage", file_paths: ["src/codeviz/storage.py"], entity_ids: ["e4", "e5"] },
    { module_id: "src/codeviz/web", display_name: "web", file_paths: ["src/codeviz/web/app.js"], entity_ids: ["e6"] },
  ];
  const dependencies = [
    {
      source_module_id: "src/codeviz/project",
      target_module_id: "src/codeviz/storage",
      dominant_edge_type: "calls",
      imports_count: 2,
      calls_count: 4,
      uses_count: 0,
    },
    {
      source_module_id: "bin/codeviz",
      target_module_id: "src/codeviz/project",
      dominant_edge_type: "imports",
      imports_count: 1,
      calls_count: 0,
      uses_count: 0,
    },
  ];

  const layout = layoutApi.buildArchitectureLayout(modules, dependencies, 1200, 700);

  assert.equal(layout.nodes.length, 4);
  assert.equal(layout.lanes.length, layout.layers.length);
  assert.ok(layout.layers.includes("entry"));
  assert.ok(layout.layers.includes("application"));
  assert.ok(layout.layers.includes("data"));
  assert.equal(layout.edges.length, 2);
  assert.ok(layout.edges[0].path.startsWith("M "));
  assert.notEqual(layout.nodes[0].x, layout.nodes[1].x);
  assert.ok(layout.lanes[0].width > 100);
});

test("normalizeArchitectureModules collapses low-signal tooling modules", () => {
  const modules = [
    { module_id: "src/codeviz/project", display_name: "project", file_paths: ["src/codeviz/project.py"], entity_ids: ["e1", "e2"] },
    { module_id: "src/codeviz/storage", display_name: "storage", file_paths: ["src/codeviz/storage.py"], entity_ids: ["e3", "e4"] },
    { module_id: "src/codeviz/runtime_config", display_name: "runtime_config", file_paths: ["src/codeviz/runtime_config.py"], entity_ids: ["e5"] },
    { module_id: "src/codeviz/__init__", display_name: "__init__", file_paths: ["src/codeviz/__init__.py"], entity_ids: [] },
    { module_id: "src/codeviz/__main__", display_name: "__main__", file_paths: ["src/codeviz/__main__.py"], entity_ids: ["e6"] },
    { module_id: "lib/setup", display_name: "setup", file_paths: ["lib/setup.js"], entity_ids: ["e7"] },
  ];
  const dependencies = [
    { source_module_id: "src/codeviz/project", target_module_id: "src/codeviz/storage", imports_count: 4, calls_count: 6, uses_count: 0 },
    { source_module_id: "src/codeviz/project", target_module_id: "src/codeviz/runtime_config", imports_count: 1, calls_count: 0, uses_count: 0 },
    { source_module_id: "src/codeviz/__main__", target_module_id: "src/codeviz/project", imports_count: 1, calls_count: 0, uses_count: 0 },
  ];

  const normalized = layoutApi.normalizeArchitectureModules(modules, dependencies);

  assert.ok(normalized.modules.some((module) => module.module_id === "layer/tooling-bundle"));
  assert.ok(normalized.modules.every((module) => module.module_id !== "src/codeviz/__init__"));
  assert.ok(normalized.dependencies.some((edge) => edge.source_module_id === "layer/tooling-bundle" || edge.target_module_id === "layer/tooling-bundle"));
});
