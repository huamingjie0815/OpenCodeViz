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

  // -- DOM refs ---------------------------------------------------------
  const svg = d3.select("#graph-svg");
  const tooltip = document.getElementById("tooltip");
  const statusBadge = document.getElementById("status-badge");
  const statsLabel = document.getElementById("stats-label");
  const streamDot = document.getElementById("stream-dot");
  const streamLabel = document.getElementById("stream-label");
  const searchInput = document.getElementById("search-input");
  const searchResults = document.getElementById("search-results");
  const detailPanel = document.getElementById("detail-panel");
  const chatToggle = document.getElementById("chat-toggle");
  const chatPanel = document.getElementById("chat-panel");
  const chatClose = document.getElementById("chat-close");
  const chatForm = document.getElementById("chat-form");
  const chatInput = document.getElementById("chat-input");
  const chatMessages = document.getElementById("chat-messages");

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

  function initSimulation() {
    simulation = d3
      .forceSimulation(nodes)
      .force("link", d3.forceLink(links).id((d) => d.id).distance(60))
      .force("charge", d3.forceManyBody().strength(-120))
      .force("center", d3.forceCenter(width() / 2, height() / 2))
      .force("collision", d3.forceCollide().radius((d) => (TYPE_RADIUS[d.type] || 6) + 2))
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
      .attr("r", (d) => TYPE_RADIUS[d.type] || 6)
      .attr("fill", (d) => TYPE_COLORS[d.type] || "#484f58")
      .attr("stroke", (d) => LANG_COLORS[d.language] || "var(--bg)")
      .attr("stroke-width", (d) => d.language ? 2.5 : 1.5);

    enter
      .append("text")
      .text((d) => d.name)
      .attr("x", (d) => (TYPE_RADIUS[d.type] || 6) + 4)
      .attr("y", 4)
      .attr("font-size", "10px")
      .attr("fill", "var(--fg2)")
      .attr("font-family", "var(--sans)");

    enter
      .on("mouseover", (event, d) => showTooltip(event, d))
      .on("mouseout", () => hideTooltip())
      .on("click", (event, d) => selectNode(d));

    // update simulation
    if (simulation) {
      simulation.nodes(nodes);
      simulation.force("link").links(links);
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
    tooltip.style.left = event.pageX + 12 + "px";
    tooltip.style.top = event.pageY - 20 + "px";
  }
  function hideTooltip() {
    tooltip.style.display = "none";
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

  function updateStats(summary) {
    const s = summary || { entities: nodes.length, edges: links.length };
    statsLabel.textContent = `${s.entities || nodes.length} entities, ${s.edges || links.length} edges`;
  }

  // -- Chat -------------------------------------------------------------
  let _thinkingTimer = null;

  function updateTogglePosition() {
    chatToggle.style.bottom = chatPanel.classList.contains("open") ? "336px" : "16px";
  }

  chatToggle.addEventListener("click", () => {
    chatPanel.classList.toggle("open");
    updateTogglePosition();
    if (chatPanel.classList.contains("open")) chatInput.focus();
  });
  chatClose.addEventListener("click", () => {
    chatPanel.classList.remove("open");
    updateTogglePosition();
  });

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
        removeThinking();
        if (data.ok && data.turn_id) {
          pollChatTurn(data.turn_id);
        } else {
          appendChatMsg("assistant", data.error || "Error");
        }
      })
      .catch((err) => {
        removeThinking();
        appendChatMsg("assistant", "Network error: " + err.message);
      });
  });

  function pollChatTurn(turnId) {
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
        `Thinking<span class="thinking-dots"><span>●</span><span>●</span><span>●</span></span>` +
        `<span class="thinking-timer">0s</span>`;
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
    if (simulation) {
      simulation.force("center", d3.forceCenter(width() / 2, height() / 2));
      simulation.alpha(0.1).restart();
    }
  });

  loadInitialGraph();
  connectSSE();
})();
