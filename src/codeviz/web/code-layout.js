(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.CodeLayout = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  function buildForceLayoutConfig(view, nodeCount) {
    if (view === "architecture") {
      return {
        linkDistance: 60,
        chargeStrength: -120,
        chargeDistanceMax: 250,
        collisionPadding: 4,
      };
    }

    if (view === "code") {
      if (nodeCount >= 300) {
        return {
          linkDistance: 108,
          chargeStrength: -150,
          chargeDistanceMax: 440,
          collisionPadding: 12,
        };
      }
      if (nodeCount >= 140) {
        return {
          linkDistance: 90,
          chargeStrength: -120,
          chargeDistanceMax: 360,
          collisionPadding: 8,
        };
      }
      return {
        linkDistance: 72,
        chargeStrength: -80,
        chargeDistanceMax: 300,
        collisionPadding: 6,
      };
    }

    return {
      linkDistance: 90,
      chargeStrength: -50,
      chargeDistanceMax: 250,
      collisionPadding: 4,
    };
  }

  return {
    buildForceLayoutConfig,
  };
});
