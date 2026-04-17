(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.FlowLayout = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  function buildFlowLayout(nodes, links, canvasWidth, canvasHeight) {
    const width = Math.max(canvasWidth || 0, 960);
    const height = Math.max(canvasHeight || 0, 560);
    const cardWidth = 220;
    const cardHeight = 64;
    const topPadding = 96;
    const bottomPadding = 72;
    const layerGap = Math.max(140, Math.floor((height - topPadding - bottomPadding) / Math.max(1, _maxDepth(nodes))));
    const layers = new Map();

    (nodes || []).forEach((node) => {
      const depth = Number.isFinite(node.depth) ? node.depth : 0;
      if (!layers.has(depth)) layers.set(depth, []);
      layers.get(depth).push(node);
    });

    const orderedDepths = [...layers.keys()].sort((a, b) => a - b);
    const nodesById = {};

    orderedDepths.forEach((depth) => {
      const layerNodes = (layers.get(depth) || [])
        .slice()
        .sort((left, right) => {
          const leftPath = String(left.file_path || "");
          const rightPath = String(right.file_path || "");
          if (leftPath !== rightPath) return leftPath.localeCompare(rightPath);
          return String(left.name || "").localeCompare(String(right.name || ""));
        });
      const gap = width / (layerNodes.length + 1);
      layerNodes.forEach((node, index) => {
        nodesById[node.id] = {
          ...node,
          depth,
          x: Number.isFinite(node.x) ? node.x : Math.round(gap * (index + 1)),
          y: Number.isFinite(node.y) ? node.y : (topPadding + depth * layerGap),
          width: cardWidth,
          height: cardHeight,
        };
      });
    });

    return {
      nodes: Object.values(nodesById),
      nodesById,
      edges: (links || [])
        .map((link) => {
          const source = nodesById[typeof link.source === "object" ? link.source.id : link.source];
          const target = nodesById[typeof link.target === "object" ? link.target.id : link.target];
          if (!source || !target) return null;
          return {
            ...link,
            path: _buildEdgePath(source, target),
          };
        })
        .filter(Boolean),
    };
  }

  function _maxDepth(nodes) {
    return (nodes || []).reduce((max, node) => {
      const depth = Number.isFinite(node.depth) ? node.depth : 0;
      return Math.max(max, depth || 0);
    }, 0) + 1;
  }

  function _buildEdgePath(source, target) {
    const startX = source.x;
    const startY = source.y + source.height / 2;
    const endX = target.x;
    const endY = target.y - target.height / 2;
    const controlY = startY + Math.max(48, (endY - startY) * 0.45);
    return `M ${startX} ${startY} C ${startX} ${controlY}, ${endX} ${endY - Math.max(24, (endY - startY) * 0.2)}, ${endX} ${endY}`;
  }

  return {
    buildFlowLayout,
  };
});
