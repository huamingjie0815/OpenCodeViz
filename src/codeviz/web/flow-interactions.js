(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.FlowInteractions = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  function nodeIdOf(endpoint) {
    return typeof endpoint === "object" ? endpoint.id : endpoint;
  }

  function buildHighlightState(nodeId, links) {
    const nodeIds = new Set([nodeId]);
    const edgeIds = new Set();

    (links || []).forEach((link) => {
      const sourceId = nodeIdOf(link.source);
      const targetId = nodeIdOf(link.target);
      if (sourceId !== nodeId && targetId !== nodeId) return;
      nodeIds.add(sourceId);
      nodeIds.add(targetId);
      edgeIds.add(link.id);
    });

    return { nodeIds, edgeIds };
  }

  function buildEdgePath(source, target) {
    const startX = source.x;
    const startY = source.y + (source.height || 64) / 2;
    const endX = target.x;
    const endY = target.y - (target.height || 64) / 2;
    const controlY = startY + Math.max(48, (endY - startY) * 0.45);
    return `M ${startX} ${startY} C ${startX} ${controlY}, ${endX} ${endY - Math.max(24, (endY - startY) * 0.2)}, ${endX} ${endY}`;
  }

  return {
    buildHighlightState,
    buildEdgePath,
  };
});
