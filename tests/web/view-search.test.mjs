import test from "node:test";
import assert from "node:assert/strict";

await import("../../src/codeviz/web/view-search.js");

const api = globalThis.ViewSearch;

test("getSearchPlaceholder returns flow-specific copy for the left sidebar", () => {
  assert.equal(api.getSearchPlaceholder("flow"), "Search flow steps...");
});

test("filterVisibleNodes matches the nodes rendered in the current flow view", () => {
  const matches = api.filterVisibleNodes([
    { id: "step-1", name: "main", file_path: "bin/codeviz.js" },
    { id: "step-2", name: "loadGraph", file_path: "src/codeviz/project.py" },
  ], "project.py");

  assert.deepEqual(matches.map((node) => node.id), ["step-2"]);
});
