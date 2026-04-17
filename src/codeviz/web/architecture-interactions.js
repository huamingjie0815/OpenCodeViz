(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.ArchitectureInteractions = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  function nodeIdOf(endpoint) {
    return typeof endpoint === "object" ? endpoint.id : endpoint;
  }

  function buildHighlightState(nodeId, links) {
    const nodeIds = new Set([nodeId]);
    const edgeIds = new Set();

    links.forEach((link) => {
      const sourceId = nodeIdOf(link.source);
      const targetId = nodeIdOf(link.target);
      if (sourceId !== nodeId && targetId !== nodeId) return;
      nodeIds.add(sourceId);
      nodeIds.add(targetId);
      edgeIds.add(link.id);
    });

    return { nodeIds, edgeIds };
  }

  function getBackTarget(viewMode, context) {
    if (viewMode === "entity") {
      return {
        viewMode: "file",
        moduleId: context && context.moduleId ? context.moduleId : null,
        filePath: null,
      };
    }

    return {
      viewMode: "module",
      moduleId: null,
      filePath: null,
    };
  }

  return {
    buildHighlightState,
    getBackTarget,
  };
});
