import test from "node:test";
import assert from "node:assert/strict";

let api = null;

try {
  await import("../../src/codeviz/web/code-legend-filter.js");
  api = globalThis.CodeLegendFilter;
} catch {}

test("toggleHiddenType adds and removes code legend types", () => {
  assert.ok(api, "CodeLegendFilter API should be available");

  const hidden = new Set();

  const nextHidden = api.toggleHiddenType(hidden, "function");
  assert.deepEqual([...nextHidden], ["function"]);

  const restored = api.toggleHiddenType(nextHidden, "function");
  assert.deepEqual([...restored], []);
});

test("SUPPORTED_CODE_LEGEND_TYPES matches the clickable code legend", () => {
  assert.ok(api, "CodeLegendFilter API should be available");

  assert.deepEqual(api.SUPPORTED_CODE_LEGEND_TYPES, [
    "class",
    "function",
    "method",
    "interface",
    "module",
  ]);
});

test("buildVisibleCodeGraph removes hidden-type nodes and connected edges", () => {
  assert.ok(api, "CodeLegendFilter API should be available");

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
  assert.ok(api, "CodeLegendFilter API should be available");

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

test("buildVisibleCodeGraph handles links whose endpoints were already expanded to objects", () => {
  assert.ok(api, "CodeLegendFilter API should be available");

  const nodes = [
    { id: "class:a", type: "class" },
    { id: "function:b", type: "function" },
  ];
  const links = [
    { id: "a:b", source: { id: "class:a" }, target: { id: "function:b" } },
  ];

  const visible = api.buildVisibleCodeGraph(nodes, links, new Set(["function"]));

  assert.deepEqual(visible.nodes.map((node) => node.id), ["class:a"]);
  assert.deepEqual(visible.links, []);
});
