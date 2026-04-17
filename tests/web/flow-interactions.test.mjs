import test from "node:test";
import assert from "node:assert/strict";

await import("../../src/codeviz/web/flow-interactions.js");

const api = globalThis.FlowInteractions;

test("buildHighlightState includes directly connected flow nodes and edges", () => {
  const links = [
    { id: "flow:1:2", source: "step-1", target: "step-2" },
    { id: "flow:1:3", source: { id: "step-1" }, target: { id: "step-3" } },
    { id: "flow:4:5", source: "step-4", target: "step-5" },
  ];

  const state = api.buildHighlightState("step-1", links);

  assert.deepEqual([...state.nodeIds].sort(), ["step-1", "step-2", "step-3"]);
  assert.deepEqual([...state.edgeIds].sort(), ["flow:1:2", "flow:1:3"]);
});

test("buildEdgePath follows updated node positions during drag", () => {
  const path = api.buildEdgePath(
    { x: 320, y: 180, width: 220, height: 64 },
    { x: 540, y: 340, width: 220, height: 64 },
  );

  assert.match(path, /^M 320 212 C /);
  assert.match(path, / 540 308$/);
});
