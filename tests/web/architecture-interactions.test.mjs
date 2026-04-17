import test from "node:test";
import assert from "node:assert/strict";

await import("../../src/codeviz/web/architecture-interactions.js");

const api = globalThis.ArchitectureInteractions;

test("buildHighlightState includes directly connected nodes and edges", () => {
  const links = [
    { id: "a:b", source: "module:a", target: "module:b" },
    { id: "b:c", source: { id: "module:b" }, target: { id: "module:c" } },
    { id: "d:e", source: "module:d", target: "module:e" },
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
