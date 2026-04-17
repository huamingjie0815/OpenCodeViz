import test from "node:test";
import assert from "node:assert/strict";

await import("../../src/codeviz/web/flow-search.js");

const api = globalThis.FlowSearch;

test("normalizeFlowCandidates tags entity and file entries", () => {
  const candidates = api.normalizeFlowCandidates({
    entity: [{ label: "main (bin/codeviz.js)", value: "function:bin/codeviz.js:main:2" }],
    file: [{ label: "bin/codeviz.js", value: "bin/codeviz.js" }],
  });

  assert.deepEqual(candidates, [
    { label: "main (bin/codeviz.js)", value: "function:bin/codeviz.js:main:2", kind: "entity" },
    { label: "bin/codeviz.js", value: "bin/codeviz.js", kind: "file" },
  ]);
});

test("filterFlowCandidates matches label and value with exact hits first", () => {
  const candidates = [
    { label: "main (bin/codeviz.js)", value: "function:bin/codeviz.js:main:2", kind: "entity" },
    { label: "main (lib/cli.js)", value: "function:lib/cli.js:main:69", kind: "entity" },
    { label: "bin/codeviz.js", value: "bin/codeviz.js", kind: "file" },
  ];

  const matches = api.filterFlowCandidates(candidates, "bin/codeviz.js");

  assert.equal(matches[0].value, "bin/codeviz.js");
  assert.equal(matches[1].value, "function:bin/codeviz.js:main:2");
});

test("filterFlowCandidates returns empty list for blank query", () => {
  const matches = api.filterFlowCandidates(
    [{ label: "bin/codeviz.js", value: "bin/codeviz.js", kind: "file" }],
    "   ",
  );

  assert.deepEqual(matches, []);
});
