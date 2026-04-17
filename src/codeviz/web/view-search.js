(function () {
  "use strict";

  function getSearchPlaceholder(view) {
    if (view === "architecture") return "Search modules...";
    if (view === "flow") return "Search flow steps...";
    return "Search entities...";
  }

  function filterVisibleNodes(nodes, query, limit = 20) {
    const q = String(query || "").trim().toLowerCase();
    if (!q) return [];

    return [...(nodes || [])]
      .filter((node) => {
        const name = String(node.name || "").toLowerCase();
        const filePath = String(node.file_path || "").toLowerCase();
        return name.includes(q) || filePath.includes(q);
      })
      .slice(0, limit);
  }

  globalThis.ViewSearch = {
    getSearchPlaceholder,
    filterVisibleNodes,
  };
})();
