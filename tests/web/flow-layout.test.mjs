import test from "node:test";
import assert from "node:assert/strict";

await import("../../src/codeviz/web/flow-layout.js");

const api = globalThis.FlowLayout;

test("buildFlowLayout places nodes by depth and separates siblings", () => {
  const layout = api.buildFlowLayout(
    [
      { id: "step-1", depth: 0, name: "main", file_path: "src/app.py" },
      { id: "step-2", depth: 1, name: "alpha", file_path: "src/a.py" },
      { id: "step-3", depth: 1, name: "beta", file_path: "src/b.py" },
    ],
    [
      { id: "edge-1", source: "step-1", target: "step-2", type: "calls" },
      { id: "edge-2", source: "step-1", target: "step-3", type: "calls" },
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
      { id: "edge-1", source: "step-1", target: "step-2", type: "calls" },
      { id: "edge-2", source: "step-2", target: "step-3", type: "calls" },
    ],
    1200,
    700,
  );

  assert.equal(layout.nodesById["step-1"].depth, 0);
  assert.equal(layout.nodesById["step-3"].depth, 2);
  assert.match(layout.edges[0].path, /^M /);
});

test("buildFlowLayout preserves manually moved node positions", () => {
  const layout = api.buildFlowLayout(
    [
      { id: "step-1", depth: 0, name: "main", file_path: "src/app.py", x: 420, y: 160 },
      { id: "step-2", depth: 1, name: "alpha", file_path: "src/a.py" },
    ],
    [
      { id: "edge-1", source: "step-1", target: "step-2", type: "calls" },
    ],
    1200,
    700,
  );

  assert.equal(layout.nodesById["step-1"].x, 420);
  assert.equal(layout.nodesById["step-1"].y, 160);
});
