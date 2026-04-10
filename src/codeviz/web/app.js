(function () {
  "use strict";

  // -- Config -----------------------------------------------------------
  const TYPE_COLORS = {
    class: "#58a6ff",
    function: "#3fb950",
    method: "#bc8cff",
    interface: "#d29922",
    module: "#f0883e",
    variable: "#484f58",
    type: "#d29922",
    enum: "#f0883e",
    constant: "#8b949e",
    decorator: "#f85149",
  };
  const EDGE_COLORS = {
    calls: "#484f58",
    imports: "#30363d",
    inherits: "#d29922",
    implements: "#bc8cff",
    uses: "#30363d",
    contains: "#21262d",
    decorates: "#f85149",
    overrides: "#f0883e",
    cross_file_call: "#58a6ff",
    cross_file_import: "#388bfd",
    cross_file_inherit: "#d29922",
  };
  const TYPE_RADIUS = {
    class: 10,
    module: 10,
    interface: 8,
    function: 7,
    method: 6,
    variable: 5,
    type: 6,
    enum: 7,
    constant: 5,
    decorator: 6,
  };
  const DEGREE_THRESHOLDS = {
    medium: 5,
    high: 10,
  };
  const DEGREE_SCALE = {
    base: 1,
    medium: 1.45,
    high: 2,
  };
  const LANG_COLORS = {
    javascript: "#f1e05a",
    typescript: "#3178c6",
    python: "#3572a5",
    jsx: "#f1e05a",
    tsx: "#3178c6",
    java: "#b07219",
    go: "#00add8",
    rust: "#dea584",
    ruby: "#701516",
    php: "#4f5d95",
    css: "#563d7c",
    html: "#e34c26",
    c: "#555555",
    cpp: "#f34b7d",
    csharp: "#178600",
    swift: "#f05138",
    kotlin: "#a97bff",
    shell: "#89e051",
  };

  // -- State ------------------------------------------------------------
  let nodes = [];
  let links = [];
  let entityMap = {};
  let simulation = null;
  let selectedNode = null;
  let searchTimeout = null;
  let showLabels = true;
  let leftSidebarWidth = 320;
  let rightSidebarWidth = 360;

  // -- DOM refs ---------------------------------------------------------
  const app = document.getElementById("app");
  const svg = d3.select("#graph-svg");
  const tooltip = document.getElementById("tooltip");
  const statusBadge = document.getElementById("status-badge");
  const statsLabel = document.getElementById("stats-label");
  const streamDot = document.getElementById("stream-dot");
  const streamLabel = document.getElementById("stream-label");
  const searchInput = document.getElementById("search-input");
  const searchResults = document.getElementById("search-results");
  const detailPanel = document.getElementById("detail-panel");
  const labelToggle = document.getElementById("label-toggle");
  const chatPanel = document.getElementById("chat-panel");
  const chatForm = document.getElementById("chat-form");
  const chatInput = document.getElementById("chat-input");
  const chatMessages = document.getElementById("chat-messages");
  const leftSidebarToggle = document.getElementById("left-sidebar-toggle");
  const leftSidebarExpand = document.getElementById("left-sidebar-expand");
  const rightSidebarToggle = document.getElementById("right-sidebar-toggle");
  const rightSidebarExpand = document.getElementById("right-sidebar-expand");
  const leftResizer = document.getElementById("left-resizer");
  const rightResizer = document.getElementById("right-resizer");

  // -- D3 setup ---------------------------------------------------------
  const width = () => document.getElementById("graph-area").clientWidth;
  const height = () => document.getElementById("graph-area").clientHeight;

  const g = svg.append("g");
  let linkGroup = g.append("g").attr("class", "links");
  let nodeGroup = g.append("g").attr("class", "nodes");

  const zoom = d3.zoom().scaleExtent([0.1, 8]).on("zoom", (e) => {
    g.attr("transform", e.transform);
  });
  svg.call(zoom);

  function getNodeTier(degree) {
    if (degree >= DEGREE_THRESHOLDS.high) return "high";
    if (degree >= DEGREE_THRESHOLDS.medium) return "medium";
    return "base";
  }

  function getNodeRadius(node) {
    const baseRadius = TYPE_RADIUS[node.type] || 6;
    return baseRadius * DEGREE_SCALE[node.degreeTier || "base"];
  }

  function updateNodeDegrees() {
    const degreeMap = new Map(nodes.map((node) => [node.id, 0]));
    links.forEach((link) => {
      const sourceId = typeof link.source === "object" ? link.source.id : link.source;
      const targetId = typeof link.target === "object" ? link.target.id : link.target;
      degreeMap.set(sourceId, (degreeMap.get(sourceId) || 0) + 1);
      degreeMap.set(targetId, (degreeMap.get(targetId) || 0) + 1);
    });
    nodes.forEach((node) => {
      node.degree = degreeMap.get(node.id) || 0;
      node.degreeTier = getNodeTier(node.degree);
    });
  }

  function initSimulation() {
    simulation = d3
      .forceSimulation(nodes)
      .force("link", d3.forceLink(links).id((d) => d.id).distance(60))
      .force("charge", d3.forceManyBody().strength(-120))
      .force("center", d3.forceCenter(width() / 2, height() / 2))
      .force("collision", d3.forceCollide().radius((d) => getNodeRadius(d) + 6))
      .on("tick", ticked);
  }

  function ticked() {
    linkGroup
      .selectAll("line")
      .attr("x1", (d) => d.source.x)
      .attr("y1", (d) => d.source.y)
      .attr("x2", (d) => d.target.x)
      .attr("y2", (d) => d.target.y);

    nodeGroup
      .selectAll("g.node")
      .attr("transform", (d) => `translate(${d.x},${d.y})`);
  }

  function renderGraph() {
    updateNodeDegrees();

    // links
    const linkSel = linkGroup.selectAll("line").data(links, (d) => d.id);
    linkSel.exit().remove();
    linkSel
      .enter()
      .append("line")
      .attr("stroke", (d) => EDGE_COLORS[d.type] || "#30363d")
      .attr("stroke-width", (d) => (d.type && d.type.startsWith("cross_file") ? 1.5 : 1))
      .attr("stroke-opacity", 0.5);

    // nodes
    const nodeSel = nodeGroup.selectAll("g.node").data(nodes, (d) => d.id);
    nodeSel.exit().remove();
    const enter = nodeSel
      .enter()
      .append("g")
      .attr("class", "node")
      .call(drag(simulation));

    enter
      .append("circle")
      .attr("fill", (d) => TYPE_COLORS[d.type] || "#484f58")
      .attr("stroke", (d) => LANG_COLORS[d.language] || "var(--bg)")
      .attr("stroke-width", (d) => d.language ? 2.5 : 1.5);

    enter
      .append("text")
      .attr("y", 4)
      .attr("font-size", (d) => `${d.degreeTier === "high" ? 12 : 10}px`)
      .attr("fill", "var(--fg2)")
      .attr("font-family", "var(--sans)");

    const mergedNodes = enter.merge(nodeSel);

    mergedNodes
      .select("circle")
      .attr("r", (d) => getNodeRadius(d));

    mergedNodes
      .select("text")
      .text((d) => d.name)
      .attr("x", (d) => getNodeRadius(d) + 4)
      .attr("display", showLabels ? null : "none")
      .attr("font-size", (d) => `${d.degreeTier === "high" ? 12 : 10}px`);

    mergedNodes
      .on("mouseover", (event, d) => showTooltip(event, d))
      .on("mouseout", () => hideTooltip())
      .on("click", (event, d) => selectNode(d));

    // update simulation
    if (simulation) {
      simulation.nodes(nodes);
      simulation.force("link").links(links);
      simulation.force("collision", d3.forceCollide().radius((d) => getNodeRadius(d) + 6));
      simulation.alpha(0.3).restart();
    }
  }

  function drag(sim) {
    return d3
      .drag()
      .on("start", (e, d) => {
        if (!e.active) sim.alphaTarget(0.3).restart();
        d.fx = d.x;
        d.fy = d.y;
      })
      .on("drag", (e, d) => {
        d.fx = e.x;
        d.fy = e.y;
      })
      .on("end", (e, d) => {
        if (!e.active) sim.alphaTarget(0);
        d.fx = null;
        d.fy = null;
      });
  }

  // -- Tooltip ----------------------------------------------------------
  function showTooltip(event, d) {
    const lang = d.language ? `[${d.language}] ` : "";
    const lines = [`${lang}${d.type}: ${d.name}`, `File: ${d.file_path || "-"}`];
    if (d.signature) lines.push(`Sig: ${d.signature}`);
    if (d.description) lines.push(d.description);
    tooltip.textContent = lines.join("\n");
    tooltip.style.display = "block";
    const padding = 16;
    const rect = tooltip.getBoundingClientRect();
    const maxLeft = window.innerWidth - rect.width - padding;
    const maxTop = window.innerHeight - rect.height - padding;
    const left = Math.min(Math.max(event.clientX + 12, padding), Math.max(padding, maxLeft));
    const top = Math.min(Math.max(event.clientY - 20, padding), Math.max(padding, maxTop));
    tooltip.style.left = left + "px";
    tooltip.style.top = top + "px";
  }
  function hideTooltip() {
    tooltip.style.display = "none";
  }

  function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
  }

  function setSidebarWidth(side, next) {
    const min = 220;
    const max = Math.max(min, Math.floor(window.innerWidth * 0.45));
    const nextWidth = clamp(Math.round(next), min, max);
    if (side === "left") {
      leftSidebarWidth = nextWidth;
      document.documentElement.style.setProperty("--left-sidebar-width", `${nextWidth}px`);
    } else {
      rightSidebarWidth = nextWidth;
      document.documentElement.style.setProperty("--right-sidebar-width", `${nextWidth}px`);
    }
    if (simulation) {
      simulation.force("center", d3.forceCenter(width() / 2, height() / 2));
      simulation.alpha(0.1).restart();
    }
  }

  function toggleSidebar(side, collapsed) {
    const className = side === "left" ? "sidebar-left-collapsed" : "sidebar-right-collapsed";
    app.classList.toggle(className, collapsed);
    if (simulation) {
      simulation.force("center", d3.forceCenter(width() / 2, height() / 2));
      simulation.alpha(0.1).restart();
    }
  }

  function initSidebarControls() {
    leftSidebarToggle.addEventListener("click", () => toggleSidebar("left", true));
    leftSidebarExpand.addEventListener("click", () => toggleSidebar("left", false));
    rightSidebarToggle.addEventListener("click", () => toggleSidebar("right", true));
    rightSidebarExpand.addEventListener("click", () => toggleSidebar("right", false));

    attachResize(leftResizer, "left");
    attachResize(rightResizer, "right");
  }

  function attachResize(handle, side) {
    handle.addEventListener("pointerdown", (event) => {
      const collapsed = app.classList.contains(side === "left" ? "sidebar-left-collapsed" : "sidebar-right-collapsed");
      if (collapsed || window.innerWidth <= 900) return;

      event.preventDefault();
      handle.classList.add("dragging");
      handle.setPointerCapture(event.pointerId);

      const onMove = (moveEvent) => {
        if (side === "left") {
          setSidebarWidth("left", moveEvent.clientX);
        } else {
          setSidebarWidth("right", window.innerWidth - moveEvent.clientX);
        }
      };

      const onEnd = () => {
        handle.classList.remove("dragging");
        handle.removeEventListener("pointermove", onMove);
        handle.removeEventListener("pointerup", onEnd);
        handle.removeEventListener("pointercancel", onEnd);
      };

      handle.addEventListener("pointermove", onMove);
      handle.addEventListener("pointerup", onEnd);
      handle.addEventListener("pointercancel", onEnd);
    });
  }

  // -- Node selection ---------------------------------------------------
  function selectNode(d) {
    selectedNode = d;
    highlightNode(d.id);
    renderDetail(d);
  }

  function highlightNode(nodeId) {
    const connectedIds = new Set([nodeId]);
    links.forEach((l) => {
      const sid = typeof l.source === "object" ? l.source.id : l.source;
      const tid = typeof l.target === "object" ? l.target.id : l.target;
      if (sid === nodeId) connectedIds.add(tid);
      if (tid === nodeId) connectedIds.add(sid);
    });
    nodeGroup
      .selectAll("g.node")
      .attr("opacity", (d) => (connectedIds.has(d.id) ? 1 : 0.15));
    linkGroup
      .selectAll("line")
      .attr("stroke-opacity", (d) => {
        const sid = typeof d.source === "object" ? d.source.id : d.source;
        const tid = typeof d.target === "object" ? d.target.id : d.target;
        return sid === nodeId || tid === nodeId ? 0.8 : 0.05;
      });
  }

  function clearHighlight() {
    nodeGroup.selectAll("g.node").attr("opacity", 1);
    linkGroup.selectAll("line").attr("stroke-opacity", 0.5);
  }

  svg.on("click", (e) => {
    if (e.target === svg.node()) {
      selectedNode = null;
      clearHighlight();
      detailPanel.innerHTML = '<p style="color:var(--fg2);font-size:12px">Click a node to see details</p>';
    }
  });

  function renderDetail(d) {
    const incoming = links.filter((l) => {
      const tid = typeof l.target === "object" ? l.target.id : l.target;
      return tid === d.id;
    });
    const outgoing = links.filter((l) => {
      const sid = typeof l.source === "object" ? l.source.id : l.source;
      return sid === d.id;
    });
    const html = [
      `<span class="type-badge ${d.type}">${d.type}</span>${d.language ? ` <span class="lang-badge" style="background:${LANG_COLORS[d.language] || '#484f58'};color:#fff;padding:1px 5px;border-radius:3px;font-size:10px">${d.language}</span>` : ""} <strong>${d.name}</strong>`,
      `<div class="file-path">${d.file_path || ""}${d.start_line ? ":" + d.start_line : ""}</div>`,
    ];
    if (d.signature) html.push(`<div style="margin-top:4px;font-family:var(--mono);font-size:11px;color:var(--fg2)">${escHtml(d.signature)}</div>`);
    if (d.description) html.push(`<div class="desc">${escHtml(d.description)}</div>`);
    if (incoming.length) {
      html.push('<div class="neighbors"><strong>Called by:</strong>');
      incoming.forEach((l) => {
        const sid = typeof l.source === "object" ? l.source.id : l.source;
        const src = entityMap[sid];
        if (src) html.push(`<div class="neighbor-item" data-id="${sid}">${src.name} (${l.type})</div>`);
      });
      html.push("</div>");
    }
    if (outgoing.length) {
      html.push('<div class="neighbors"><strong>Calls:</strong>');
      outgoing.forEach((l) => {
        const tid = typeof l.target === "object" ? l.target.id : l.target;
        const tgt = entityMap[tid];
        if (tgt) html.push(`<div class="neighbor-item" data-id="${tid}">${tgt.name} (${l.type})</div>`);
      });
      html.push("</div>");
    }
    detailPanel.innerHTML = html.join("");
    detailPanel.querySelectorAll(".neighbor-item").forEach((el) => {
      el.addEventListener("click", () => {
        const id = el.dataset.id;
        const n = entityMap[id];
        if (n) selectNode(n);
      });
    });
  }

  function escHtml(s) {
    const div = document.createElement("div");
    div.textContent = s;
    return div.innerHTML;
  }

  // -- Search -----------------------------------------------------------
  searchInput.addEventListener("input", () => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => doSearch(searchInput.value), 200);
  });

  function doSearch(query) {
    searchResults.innerHTML = "";
    if (!query.trim()) return;
    const q = query.toLowerCase();
    const hits = nodes
      .filter((n) => n.name.toLowerCase().includes(q) || (n.file_path && n.file_path.toLowerCase().includes(q)))
      .slice(0, 20);
    hits.forEach((n) => {
      const div = document.createElement("div");
      div.className = "search-item";
      div.innerHTML = `<span class="type-badge ${n.type}">${n.type}</span>${n.language ? ` <span style="color:${LANG_COLORS[n.language] || '#8b949e'};font-size:10px">${n.language}</span>` : ""} ${escHtml(n.name)}`;
      div.addEventListener("click", () => {
        selectNode(n);
        zoomToNode(n);
      });
      searchResults.appendChild(div);
    });
  }

  function zoomToNode(d) {
    const transform = d3.zoomTransform(svg.node());
    const x = d.x || 0;
    const y = d.y || 0;
    svg
      .transition()
      .duration(500)
      .call(zoom.transform, d3.zoomIdentity.translate(width() / 2 - x * 1.5, height() / 2 - y * 1.5).scale(1.5));
  }

  // -- Data loading -----------------------------------------------------
  function loadInitialGraph() {
    fetch("/api/graph")
      .then((r) => r.json())
      .then((data) => {
        if (!data.ok && !data.entities) return;
        mergeEntities(data.entities || []);
        mergeEdges(data.edges || []);
        initSimulation();
        renderGraph();
        updateStats();
      })
      .catch(() => { });
  }

  function mergeEntities(entities) {
    entities.forEach((e) => {
      if (!entityMap[e.entity_id]) {
        const node = {
          id: e.entity_id,
          name: e.name,
          type: e.entity_type,
          file_path: e.file_path,
          start_line: e.start_line,
          end_line: e.end_line,
          signature: e.signature || "",
          description: e.description || "",
          parent_id: e.parent_id || null,
          language: e.language || "",
          degree: 0,
          degreeTier: "base",
        };
        nodes.push(node);
        entityMap[e.entity_id] = node;
      }
    });
  }

  function mergeEdges(edges) {
    const existingIds = new Set(links.map((l) => l.id));
    edges.forEach((e) => {
      if (existingIds.has(e.edge_id)) return;
      // Only add if both endpoints exist
      if (!entityMap[e.source_id] || !entityMap[e.target_id]) return;
      links.push({
        id: e.edge_id,
        source: e.source_id,
        target: e.target_id,
        type: e.edge_type,
        file_path: e.file_path || "",
        line: e.line || 0,
        description: e.description || "",
      });
      existingIds.add(e.edge_id);
    });
  }

  // -- SSE stream -------------------------------------------------------
  function connectSSE() {
    const source = new EventSource("/api/stream?after=0");
    source.addEventListener("status", (e) => {
      const data = JSON.parse(e.data);
      updateStatusBadge(data);
    });
    source.addEventListener("event", (e) => {
      const data = JSON.parse(e.data);
      handleStreamEvent(data);
    });
    source.addEventListener("heartbeat", (e) => {
      const data = JSON.parse(e.data);
      updateStatusBadge(data);
      updateStats(data.summary);
    });
    source.addEventListener("open", () => {
      streamDot.classList.add("active");
      streamLabel.textContent = "connected";
    });
    source.addEventListener("error", () => {
      streamDot.classList.remove("active");
      streamLabel.textContent = "reconnecting...";
    });
  }

  function handleStreamEvent(event) {
    const type = event.type || event.event_type || "";
    const payload = event.payload || event.data || event;

    if (type === "file.extracted") {
      const entities = payload.entities || [];
      const edges = payload.edges || [];
      if (entities.length || edges.length) {
        mergeEntities(entities);
        mergeEdges(edges);
        renderGraph();
        updateStats();
      }
    } else if (type === "relations.resolved") {
      const edges = payload.edges || [];
      if (edges.length) {
        mergeEdges(edges);
        renderGraph();
        updateStats();
      }
    } else if (type === "analysis.completed") {
      loadInitialGraph();
    }
  }

  function updateStatusBadge(data) {
    const status = data.analysis_status || data.freshness || "unknown";
    statusBadge.textContent = status;
    statusBadge.className = "badge";
    if (status === "running" || status === "analyzing") {
      statusBadge.classList.add("analyzing");
    } else if (status === "completed" || status === "fresh") {
      statusBadge.classList.add("fresh");
    } else if (status === "stale") {
      statusBadge.classList.add("stale");
    }
  }

  function syncLabelToggle() {
    if (!labelToggle) return;
    labelToggle.checked = showLabels;
  }

  function updateStats(summary) {
    const s = summary || { entities: nodes.length, edges: links.length };
    statsLabel.textContent = `${s.entities || nodes.length} entities, ${s.edges || links.length} edges`;
  }

  if (labelToggle) {
    syncLabelToggle();
    labelToggle.addEventListener("change", () => {
      showLabels = labelToggle.checked;
      renderGraph();
    });
  }

  // -- Chat -------------------------------------------------------------
  let _thinkingTimer = null;

  chatForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const question = chatInput.value.trim();
    if (!question) return;
    chatInput.value = "";
    appendChatMsg("user", question);
    appendChatMsg("thinking", "Thinking...");

    fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    })
      .then((r) => r.json())
      .then((data) => {
        if (data.ok && data.turn_id) {
          pollChatTurn(data.turn_id);
        } else {
          removeThinking();
          appendChatMsg("assistant", data.error || "Error");
        }
      })
      .catch((err) => {
        removeThinking();
        appendChatMsg("assistant", "Network error: " + err.message);
      });
  });

  function pollChatTurn(turnId) {
    // Try SSE streaming first, fall back to polling
    if (typeof EventSource !== "undefined") {
      return streamChatTurn(turnId);
    }
    legacyPollChatTurn(turnId);
  }

  function streamChatTurn(turnId) {
    const source = new EventSource(`/api/chat/stream/${turnId}`);
    let stepCount = 0;

    source.addEventListener("step", (e) => {
      try {
        const step = JSON.parse(e.data);
        stepCount++;
        updateThinkingSteps(step, stepCount);
      } catch (_) { }
    });

    source.addEventListener("done", (e) => {
      source.close();
      try {
        const data = JSON.parse(e.data);
        removeThinking();
        appendChatMsg("assistant", data.answer || "No answer");
      } catch (_) {
        removeThinking();
        appendChatMsg("assistant", "Failed to parse response");
      }
    });

    source.addEventListener("error", (e) => {
      source.close();
      // Fall back to polling if SSE fails, passing already-received step count
      legacyPollChatTurn(turnId, stepCount);
    });
  }

  function updateThinkingSteps(step, count) {
    const thinkingEl = chatMessages.querySelector(".chat-msg.thinking");
    if (!thinkingEl) return;
    const bubble = thinkingEl.querySelector(".bubble");
    if (!bubble) return;

    // Update step counter
    const counterEl = bubble.querySelector(".thinking-step-count");
    if (counterEl) {
      counterEl.textContent = `Step ${count}`;
    }

    // Add step line
    let stepsContainer = bubble.querySelector(".thinking-steps");
    if (!stepsContainer) {
      stepsContainer = document.createElement("div");
      stepsContainer.className = "thinking-steps";
      bubble.appendChild(stepsContainer);
    }

    const stepEl = document.createElement("div");
    stepEl.className = `thinking-step ${step.type || "thinking"}`;

    const icon = step.type === "tool_call" ? "\u{1F50D}" : step.type === "tool_result" ? "\u2705" : "\u{1F4AD}";
    stepEl.textContent = `${icon} ${step.summary || "Processing..."}`;
    stepsContainer.appendChild(stepEl);

    // Keep only last 8 steps visible
    while (stepsContainer.children.length > 8) {
      stepsContainer.removeChild(stepsContainer.firstChild);
    }

    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  function legacyPollChatTurn(turnId, _stepsSeen) {
    const poll = () => {
      fetch(`/api/chat/turn/${turnId}`)
        .then((r) => r.json())
        .then((data) => {
          if (data.status === "completed" || data.status === "failed") {
            removeThinking();
            appendChatMsg("assistant", data.answer || "No answer");
          } else {
            setTimeout(poll, 1500);
          }
        })
        .catch(() => {
          removeThinking();
          appendChatMsg("assistant", "Failed to get response");
        });
    };
    poll();
  }

  function appendChatMsg(role, text) {
    const div = document.createElement("div");
    div.className = `chat-msg ${role}`;
    const bubble = document.createElement("div");
    bubble.className = "bubble";

    if (role === "thinking") {
      bubble.innerHTML =
        `<div class="thinking-header">` +
        `Thinking<span class="thinking-dots"><span>\u25CF</span><span>\u25CF</span><span>\u25CF</span></span>` +
        `<span class="thinking-step-count"></span>` +
        `<span class="thinking-timer">0s</span>` +
        `</div>`;
      const start = Date.now();
      _thinkingTimer = setInterval(() => {
        const el = chatMessages.querySelector(".thinking-timer");
        if (el) el.textContent = `${Math.floor((Date.now() - start) / 1000)}s`;
      }, 1000);
    } else if (role === "assistant") {
      if (typeof marked !== "undefined") {
        bubble.innerHTML = marked.parse(text);
      } else {
        bubble.textContent = text;
      }
    } else {
      bubble.textContent = text;
    }

    div.appendChild(bubble);
    chatMessages.appendChild(div);
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  function removeThinking() {
    if (_thinkingTimer) { clearInterval(_thinkingTimer); _thinkingTimer = null; }
    const el = chatMessages.querySelector(".chat-msg.thinking");
    if (el) el.remove();
  }

  // -- Init -------------------------------------------------------------
  window.addEventListener("resize", () => {
    setSidebarWidth("left", leftSidebarWidth);
    setSidebarWidth("right", rightSidebarWidth);
    if (simulation) {
      simulation.force("center", d3.forceCenter(width() / 2, height() / 2));
      simulation.alpha(0.1).restart();
    }
  });

  initSidebarControls();
  loadInitialGraph();
  connectSSE();
})();
