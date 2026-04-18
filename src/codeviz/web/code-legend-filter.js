(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.CodeLegendFilter = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const SUPPORTED_CODE_LEGEND_TYPES = ["class", "function", "method", "interface", "module"];

  function nodeIdOf(endpoint) {
    return typeof endpoint === "object" ? endpoint.id : endpoint;
  }

  function toggleHiddenType(hiddenTypes, type) {
    const next = new Set(hiddenTypes || []);
    if (next.has(type)) {
      next.delete(type);
    } else {
      next.add(type);
    }
    return next;
  }

  function buildVisibleCodeGraph(nodes, links, hiddenTypes) {
    const hidden = new Set(hiddenTypes || []);
    const visibleNodes = (nodes || []).filter((node) => !hidden.has(node.type));
    const visibleNodeIds = new Set(visibleNodes.map((node) => node.id));
    const visibleLinks = (links || []).filter((link) => (
      visibleNodeIds.has(nodeIdOf(link.source)) &&
      visibleNodeIds.has(nodeIdOf(link.target))
    ));

    return {
      nodes: visibleNodes,
      links: visibleLinks,
      nodeIds: visibleNodeIds,
    };
  }

  return {
    SUPPORTED_CODE_LEGEND_TYPES,
    toggleHiddenType,
    buildVisibleCodeGraph,
  };
});
