(function () {
  "use strict";

  function normalizeFlowCandidates(entries) {
    return [
      ...((entries && entries.entity) || []).map((item) => ({ ...item, kind: "entity" })),
      ...((entries && entries.file) || []).map((item) => ({ ...item, kind: "file" })),
    ];
  }

  function filterFlowCandidates(candidates, query, limit = 12) {
    const q = String(query || "").trim().toLowerCase();
    if (!q) return [];

    return [...(candidates || [])]
      .map((candidate) => {
        const label = String(candidate.label || "").toLowerCase();
        const value = String(candidate.value || "").toLowerCase();
        let score = -1;
        if (value === q) score = 0;
        else if (label === q) score = 1;
        else if (value.startsWith(q)) score = 2;
        else if (label.startsWith(q)) score = 3;
        else if (value.includes(q)) score = 4;
        else if (label.includes(q)) score = 5;
        return { candidate, score };
      })
      .filter((item) => item.score >= 0)
      .sort((a, b) => {
        if (a.score !== b.score) return a.score - b.score;
        return String(a.candidate.label || "").localeCompare(String(b.candidate.label || ""));
      })
      .slice(0, limit)
      .map((item) => item.candidate);
  }

  globalThis.FlowSearch = {
    normalizeFlowCandidates,
    filterFlowCandidates,
  };
})();
