import test from "node:test";
import assert from "node:assert/strict";

let api = null;

try {
  await import("../../src/codeviz/web/code-layout.js");
  api = globalThis.CodeLayout;
} catch {}

test("buildForceLayoutConfig increases code graph spacing for dense graphs", () => {
  assert.ok(api, "CodeLayout API should be available");

  const compact = api.buildForceLayoutConfig("code", 40);
  const dense = api.buildForceLayoutConfig("code", 320);

  assert.equal(dense.linkDistance > compact.linkDistance, true);
  assert.equal(dense.chargeStrength < compact.chargeStrength, true);
  assert.equal(dense.chargeDistanceMax > compact.chargeDistanceMax, true);
  assert.equal(dense.collisionPadding > compact.collisionPadding, true);
});

test("buildForceLayoutConfig keeps architecture settings stable", () => {
  assert.ok(api, "CodeLayout API should be available");

  const config = api.buildForceLayoutConfig("architecture", 320);

  assert.deepEqual(config, {
    linkDistance: 60,
    chargeStrength: -120,
    chargeDistanceMax: 250,
    collisionPadding: 4,
  });
});
