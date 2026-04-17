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
  const FLOW_EDGE_PRIORITY = { calls: 0, imports: 1, uses: 2 };
  const architectureLayoutApi = globalThis.ArchitectureLayout || null;
  const architectureInteractionsApi = globalThis.ArchitectureInteractions || null;

  // -- State ------------------------------------------------------------
  const states = {
    code: { nodes: [], links: [], entityMap: {} },
    architecture: { nodes: [], links: [], entityMap: {} },
    flow: { nodes: [], links: [], entityMap: {} },
  };
  let activeView = "code";
  let nodes = states.code.nodes;
  let links = states.code.links;
  let entityMap = states.code.entityMap;
  let simulation = null;
  let selectedNode = null;
  let searchTimeout = null;
  let showLabels = true;
  let leftSidebarWidth = 320;
  let rightSidebarWidth = 360;
  let flowCandidates = [];
  let architecturePayload = { modules: [], dependencies: [] };
  let architectureViewMode = "module";
  let architectureContext = { moduleId: null, filePath: null };

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
  const legend = document.getElementById("legend");
  const chatForm = document.getElementById("chat-form");
  const chatInput = document.getElementById("chat-input");
  const chatMessages = document.getElementById("chat-messages");
  const viewTabs = Array.from(document.querySelectorAll(".view-tab"));
  const flowControls = document.getElementById("flow-controls");
  const architectureBackButton = document.getElementById("architecture-back-button");
  const flowEntryInput = document.getElementById("flow-entry-input");
  const flowRunButton = document.getElementById("flow-run-button");
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

  function bindState(view) {
    activeView = view;
    nodes = states[view].nodes;
    links = states[view].links;
    entityMap = states[view].entityMap;
  }

  function resetViewTransform() {
    svg.call(zoom.transform, d3.zoomIdentity);
  }

  function clearState(view) {
    states[view].nodes.length = 0;
    states[view].links.length = 0;
    states[view].entityMap = {};
    if (activeView === view) {
      bindState(view);
    }
  }

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
    if (simulation) {
      simulation.stop();
    }
    simulation = d3
      .forceSimulation(nodes)
      .force("link", d3.forceLink(links).id((d) => d.id).distance(activeView === "flow" ? 90 : 60))
      .force("charge", d3.forceManyBody().strength(activeView === "architecture" ? -120 : -50).distanceMax(250))
      .force("center", d3.forceCenter(width() / 2, height() / 2))
      .force("x", d3.forceX(width() / 2).strength(0.05))
      .force("y", d3.forceY(height() / 2).strength(0.05))
      .force("collision", d3.forceCollide().radius((d) => getNodeRadius(d) + 4))
      .on("tick", ticked);
  }

  function ticked() {
    linkGroup
      .selectAll("line")
      .attr("x1", (d) => (Number.isFinite(d.source.x) ? d.source.x : 0))
      .attr("y1", (d) => (Number.isFinite(d.source.y) ? d.source.y : 0))
      .attr("x2", (d) => (Number.isFinite(d.target.x) ? d.target.x : 0))
      .attr("y2", (d) => (Number.isFinite(d.target.y) ? d.target.y : 0));

    nodeGroup
      .selectAll("g.node")
      .attr("transform", (d) => `translate(${Number.isFinite(d.x) ? d.x : 0},${Number.isFinite(d.y) ? d.y : 0})`);
  }

  function renderGraph() {
    linkGroup.selectAll("*").remove();
    nodeGroup.selectAll("*").remove();
    g.selectAll(".arch-layer-label").remove();
    g.selectAll(".arch-lanes").remove();
    updateNodeDegrees();

    const linkSel = linkGroup.selectAll("line").data(links, (d) => d.id);
    linkSel.exit().remove();
    linkSel
      .enter()
      .append("line")
      .attr("stroke", (d) => EDGE_COLORS[d.type] || "#30363d")
      .attr("stroke-width", (d) => (activeView === "architecture" ? 1.5 : 1))
      .attr("stroke-opacity", 0.5);

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
      .on("mouseover", (event, d) => {
        showTooltip(event, d);
        if (activeView === "architecture") {
          applyArchitectureHighlight(d.id);
        }
      })
      .on("mouseout", () => {
        hideTooltip();
        if (activeView === "architecture") {
          clearArchitectureHighlight();
        }
      })
      .on("click", (event, d) => selectNode(d));

    if (simulation) {
      simulation.nodes(nodes);
      simulation.force("link").links(links);
      simulation.force("collision", d3.forceCollide().radius((d) => getNodeRadius(d) + 4));
      simulation.alpha(0.3).restart();
    }

    if (!selectedNode || !entityMap[selectedNode.id]) {
      selectedNode = null;
      if (activeView === "architecture") {
        clearArchitectureHighlight();
      } else {
        clearHighlight();
      }
    } else {
      highlightNode(selectedNode.id);
    }
  }

  function stopSimulation() {
    if (simulation) {
      simulation.stop();
      simulation = null;
    }
  }

  function setArchitectureContext(next) {
    architectureContext = {
      moduleId: next && next.moduleId ? next.moduleId : null,
      filePath: next && next.filePath ? next.filePath : null,
    };
  }

  function syncArchitectureBackButton() {
    if (!architectureBackButton) return;
    const show = activeView === "architecture" && architectureViewMode !== "module";
    architectureBackButton.hidden = !show;
    architectureBackButton.textContent = architectureViewMode === "entity" ? "Back to Files" : "Back to Modules";
  }

  function architectureLinkSelection() {
    return architectureViewMode === "module"
      ? linkGroup.selectAll("path.arch-edge")
      : linkGroup.selectAll("line");
  }

  function applyArchitectureHighlight(nodeId) {
    const state = architectureInteractionsApi
      ? architectureInteractionsApi.buildHighlightState(nodeId, states.architecture.links)
      : { nodeIds: new Set([nodeId]), edgeIds: new Set() };

    nodeGroup
      .selectAll("g.node")
      .attr("opacity", (d) => (state.nodeIds.has(d.id) ? 1 : 0.18));

    nodeGroup
      .selectAll("g.arch-node")
      .classed("active", (d) => state.nodeIds.has(d.id));

    architectureLinkSelection()
      .attr("stroke-opacity", (d) => (state.edgeIds.has(d.id) ? 0.92 : 0.08));
  }

  function clearArchitectureHighlight() {
    nodeGroup.selectAll("g.node").attr("opacity", 1);
    nodeGroup.selectAll("g.arch-node").classed("active", false);
    if (architectureViewMode === "module") {
      linkGroup.selectAll("path.arch-edge").attr("stroke-opacity", null);
      return;
    }
    linkGroup.selectAll("line").attr("stroke-opacity", 0.5);
  }

  function ensureGraphDefs() {
    let defs = svg.select("defs");
    if (defs.empty()) {
      defs = svg.append("defs");
    }
    let marker = defs.select("#arch-arrow");
    if (marker.empty()) {
      marker = defs
        .append("marker")
        .attr("id", "arch-arrow")
        .attr("viewBox", "0 0 10 10")
        .attr("refX", 9)
        .attr("refY", 5)
        .attr("markerWidth", 8)
        .attr("markerHeight", 8)
        .attr("orient", "auto-start-reverse");
      marker
        .append("path")
        .attr("d", "M 0 0 L 10 5 L 0 10 z")
        .attr("fill", "#58a6ff");
    }
  }

  function architectureEdgePath(edge) {
    const source = states.architecture.entityMap[edge.source];
    const target = states.architecture.entityMap[edge.target];
    if (!source || !target) return "";
    const sourceX = source.x + (source.boxWidth || 0) / 2;
    const targetX = target.x - (target.boxWidth || 0) / 2;
    const sourceY = source.y;
    const targetY = target.y;
    const delta = Math.max(40, Math.abs(targetX - sourceX) * 0.45);
    return `M ${sourceX} ${sourceY} C ${sourceX + delta} ${sourceY}, ${targetX - delta} ${targetY}, ${targetX} ${targetY}`;
  }

  function updateArchitectureEdges() {
    linkGroup
      .selectAll("path.arch-edge")
      .attr("d", (d) => architectureEdgePath(d));
  }

  function architectureNodeDrag() {
    return d3
      .drag()
      .on("start", () => {
        selectedNode = null;
        clearArchitectureHighlight();
      })
      .on("drag", function (event, d) {
        d.x = event.x;
        d.y = event.y;
        states.architecture.entityMap[d.id] = d;
        d3.select(this).attr("transform", `translate(${d.x},${d.y})`);
        updateArchitectureEdges();
      });
  }

  function renderArchitectureDiagram() {
    stopSimulation();
    ensureGraphDefs();
    const layout = architectureLayoutApi
      ? architectureLayoutApi.buildArchitectureLayout(architecturePayload.modules || [], architecturePayload.dependencies || [], width(), height())
      : { nodes: [], edges: [], layers: [] };

    states.architecture.nodes = layout.nodes.map((node) => ({
      id: node.id,
      name: node.name,
      type: "module",
      file_path: (node.module.source_dirs || []).join(", "),
      description: node.module.grouped_modules
        ? `${node.module.grouped_modules.length} grouped modules, ${node.fileCount} files, ${node.entityCount} entities`
        : `${node.fileCount} files, ${node.entityCount} entities`,
      signature: node.id,
      language: "",
      degree: 0,
      degreeTier: "base",
      architectureLevel: "module",
      moduleId: node.id,
      rawFiles: node.module.file_paths || [],
      groupedModules: node.module.grouped_modules || [],
      x: node.x,
      y: node.y,
      boxWidth: node.width,
      boxHeight: node.height,
      layer: node.layer,
    }));
    states.architecture.entityMap = Object.fromEntries(states.architecture.nodes.map((node) => [node.id, node]));
    states.architecture.links = layout.edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      type: edge.edgeType,
      description: edge.description,
      path: edge.path,
      strength: edge.strength,
    }));

    bindState("architecture");
    resetViewTransform();

    linkGroup.selectAll("*").remove();
    nodeGroup.selectAll("*").remove();

    g.selectAll(".arch-layer-label").remove();
    g.selectAll(".arch-lane").remove();
    const laneGroup = g.insert("g", ":first-child").attr("class", "arch-lanes");
    laneGroup
      .selectAll("g.arch-lane")
      .data(layout.lanes || [])
      .enter()
      .append("g")
      .attr("class", "arch-lane")
      .each(function (lane) {
        const group = d3.select(this);
        group
          .append("rect")
          .attr("x", lane.x)
          .attr("y", lane.y)
          .attr("width", lane.width)
          .attr("height", lane.height)
          .attr("rx", 16);
      });
    g.selectAll(".arch-layer-label")
      .data(layout.layers)
      .enter()
      .append("text")
      .attr("class", "arch-layer-label")
      .attr("x", (_, index) => {
        const lane = (layout.lanes || [])[index];
        return lane ? lane.x + lane.width / 2 : width() / 2;
      })
      .attr("y", 28)
      .attr("text-anchor", "middle")
      .text((layer) => layer);

    linkGroup
      .selectAll("path.arch-edge")
      .data(states.architecture.links, (d) => d.id)
      .enter()
      .append("path")
      .attr("class", "edge arch-edge")
      .attr("d", (d) => d.path)
      .attr("stroke", (d) => EDGE_COLORS[d.type] || "#58a6ff")
      .classed("medium", (d) => (d.strength || 0) >= 4 && (d.strength || 0) < 8)
      .classed("strong", (d) => (d.strength || 0) >= 8)
      .attr("stroke-width", (d) => {
        const strength = d.strength || 1;
        if (strength >= 12) return 3.8;
        if (strength >= 8) return 3.2;
        if (strength >= 4) return 2.4;
        return 1.8;
      })
      .attr("marker-end", "url(#arch-arrow)");

    const nodeEnter = nodeGroup
      .selectAll("g.arch-node")
      .data(states.architecture.nodes, (d) => d.id)
      .enter()
      .append("g")
      .attr("class", "node arch-node")
      .attr("transform", (d) => `translate(${d.x},${d.y})`)
      .call(architectureNodeDrag());

    nodeEnter
      .append("rect")
      .attr("x", (d) => -d.boxWidth / 2)
      .attr("y", (d) => -d.boxHeight / 2)
      .attr("width", (d) => d.boxWidth)
      .attr("height", (d) => d.boxHeight)
      .attr("fill", "rgba(33, 38, 45, .96)")
      .attr("stroke", "var(--border)")
      .attr("stroke-width", 1.2)
      .attr("rx", 10);

    nodeEnter
      .append("text")
      .attr("class", "arch-node-title")
      .attr("x", (d) => -d.boxWidth / 2 + 14)
      .attr("y", -4)
      .text((d) => d.name);

    nodeEnter
      .append("text")
      .attr("class", "arch-node-meta")
      .attr("x", (d) => -d.boxWidth / 2 + 14)
      .attr("y", 16)
      .text((d) => `${d.layer} • ${d.description}`);

    nodeGroup
      .selectAll("g.arch-node")
      .on("mouseover", (event, d) => {
        showTooltip(event, d);
        applyArchitectureHighlight(d.id);
      })
      .on("mouseout", () => {
        hideTooltip();
        clearArchitectureHighlight();
      })
      .on("click", (event, d) => selectNode(d));

    clearArchitectureHighlight();
    syncArchitectureBackButton();
    renderDetailMessage(defaultDetailMessage());
    updateStats({ entities: states.architecture.nodes.length, edges: states.architecture.links.length });
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
    const lines = [`${lang}${d.type}: ${d.name}`, `Path: ${d.file_path || "-"}`];
    if (d.signature) lines.push(`Ref: ${d.signature}`);
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
      if (simulation.force("x")) simulation.force("x", d3.forceX(width() / 2).strength(0.05));
      if (simulation.force("y")) simulation.force("y", d3.forceY(height() / 2).strength(0.05));
      simulation.alpha(0.1).restart();
    }
  }

  function toggleSidebar(side, collapsed) {
    const className = side === "left" ? "sidebar-left-collapsed" : "sidebar-right-collapsed";
    app.classList.toggle(className, collapsed);
    if (simulation) {
      simulation.force("center", d3.forceCenter(width() / 2, height() / 2));
      if (simulation.force("x")) simulation.force("x", d3.forceX(width() / 2).strength(0.05));
      if (simulation.force("y")) simulation.force("y", d3.forceY(height() / 2).strength(0.05));
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
    if (activeView === "architecture") {
      handleArchitectureSelect(d);
      return;
    }
    selectedNode = d;
    highlightNode(d.id);
    renderDetail(d);
  }

  function handleArchitectureSelect(d) {
    if (d.architectureLevel === "module" && Array.isArray(d.rawFiles) && d.rawFiles.length) {
      renderArchitectureFileView(d.moduleId);
      renderDetailMessage(`Showing files for ${d.name}. Hover to inspect dependencies. Click a file to drill into entities.`);
      return;
    }
    if (d.architectureLevel === "file" && d.file_path) {
      renderArchitectureEntityView(d.file_path);
      renderDetailMessage(`Showing entities for ${d.file_path}. Hover to inspect dependencies. Use Back to return to files.`);
      return;
    }
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
      if (activeView === "architecture") {
        clearArchitectureHighlight();
      } else {
        clearHighlight();
      }
      renderDetailMessage(defaultDetailMessage());
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
      `<span class="type-badge ${d.type}">${d.type}</span>${d.language ? ` <span class="lang-badge" style="background:${LANG_COLORS[d.language] || "#484f58"};color:#fff;padding:1px 5px;border-radius:3px;font-size:10px">${d.language}</span>` : ""} <strong>${d.name}</strong>`,
      `<div class="file-path">${d.file_path || ""}${d.start_line ? ":" + d.start_line : ""}</div>`,
    ];
    if (d.signature) html.push(`<div style="margin-top:4px;font-family:var(--mono);font-size:11px;color:var(--fg2)">${escHtml(d.signature)}</div>`);
    if (d.description) html.push(`<div class="desc">${escHtml(d.description)}</div>`);
    if (Array.isArray(d.groupedModules) && d.groupedModules.length) {
      html.push('<div class="neighbors"><strong>Grouped Modules:</strong>');
      d.groupedModules.forEach((item) => {
        html.push(`<div style="font-size:12px;padding:2px 0;color:var(--fg2)">${escHtml(item.display_name || item.module_id)}</div>`);
      });
      html.push("</div>");
    }
    if (incoming.length) {
      html.push('<div class="neighbors"><strong>Incoming:</strong>');
      incoming.forEach((l) => {
        const sid = typeof l.source === "object" ? l.source.id : l.source;
        const src = entityMap[sid];
        if (src) html.push(`<div class="neighbor-item" data-id="${sid}">${src.name} (${l.type})</div>`);
      });
      html.push("</div>");
    }
    if (outgoing.length) {
      html.push('<div class="neighbors"><strong>Outgoing:</strong>');
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

  function renderDetailMessage(message) {
    detailPanel.innerHTML = `<p style="color:var(--fg2);font-size:12px">${escHtml(message)}</p>`;
  }

  function defaultDetailMessage() {
    if (activeView === "architecture") {
      if (architectureViewMode === "file") return "Hover a file to highlight its linked files. Click to drill into entities.";
      if (architectureViewMode === "entity") return "Hover an entity to highlight its linked entities. Click a node to see details.";
      return "Hover a module to highlight its linked modules. Click to drill into files.";
    }
    if (activeView === "flow") return "Enter a file path or entity id to generate a flow";
    return "Click a node to see details";
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
      div.innerHTML = `<span class="type-badge ${n.type}">${n.type}</span>${n.language ? ` <span style="color:${LANG_COLORS[n.language] || "#8b949e"};font-size:10px">${n.language}</span>` : ""} ${escHtml(n.name)}`;
      div.addEventListener("click", () => {
        selectNode(n);
        zoomToNode(n);
      });
      searchResults.appendChild(div);
    });
  }

  function zoomToNode(d) {
    const x = d.x || 0;
    const y = d.y || 0;
    svg
      .transition()
      .duration(500)
      .call(zoom.transform, d3.zoomIdentity.translate(width() / 2 - x * 1.5, height() / 2 - y * 1.5).scale(1.5));
  }

  // -- Data loading -----------------------------------------------------
  function mergeEntities(state, entities) {
    entities.forEach((e) => {
      if (!state.entityMap[e.entity_id]) {
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
        state.nodes.push(node);
        state.entityMap[e.entity_id] = node;
      }
    });
  }

  function mergeEdges(state, edges) {
    const existingIds = new Set(state.links.map((l) => l.id));
    edges.forEach((e) => {
      if (existingIds.has(e.edge_id)) return;
      if (!state.entityMap[e.source_id] || !state.entityMap[e.target_id]) return;
      state.links.push({
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

  function loadCodeGraph() {
    fetch("/api/graph")
      .then((r) => r.json())
      .then((data) => {
        if (!data.ok && !data.entities) return;
        clearState("code");
        mergeEntities(states.code, data.entities || []);
        mergeEdges(states.code, data.edges || []);
        if (activeView === "code") {
          bindState("code");
          resetViewTransform();
          initSimulation();
          renderGraph();
          renderDetailMessage(defaultDetailMessage());
          updateStats({ entities: states.code.nodes.length, edges: states.code.links.length });
        }
      })
      .catch(() => { });
  }

  function loadArchitecture() {
    fetch("/api/architecture")
      .then((r) => r.json())
      .then((data) => {
        architecturePayload = {
          modules: data.modules || [],
          dependencies: data.dependencies || [],
        };
        if (activeView === "architecture") {
          renderArchitectureModuleView();
        }
      })
      .catch(() => { });
  }

  function renderArchitectureModuleView() {
    architectureViewMode = "module";
    selectedNode = null;
    setArchitectureContext({ moduleId: null, filePath: null });
    renderArchitectureDiagram();
  }

  function renderArchitectureFileView(moduleId) {
    architectureViewMode = "file";
    selectedNode = null;
    setArchitectureContext({ moduleId, filePath: null });
    const module = architecturePayload.modules.find((item) => item.module_id === moduleId);
    if (!module) return;

    clearState("architecture");
    linkGroup.selectAll("*").remove();
    nodeGroup.selectAll("*").remove();
    g.selectAll(".arch-layer-label").remove();
    g.selectAll(".arch-lanes").remove();
    const fileSet = new Set(module.file_paths || []);
    const fileNodes = {};
    Array.from(fileSet).sort().forEach((filePath) => {
      const node = {
        id: `file:${filePath}`,
        name: filePath.split("/").pop() || filePath,
        type: "module",
        file_path: filePath,
        description: "File view",
        signature: filePath,
        language: "",
        degree: 0,
        degreeTier: "base",
        architectureLevel: "file",
        moduleId,
      };
      fileNodes[filePath] = node;
      states.architecture.nodes.push(node);
      states.architecture.entityMap[node.id] = node;
    });

    const aggregated = {};
    states.code.links.forEach((link) => {
      const sourceId = typeof link.source === "object" ? link.source.id : link.source;
      const targetId = typeof link.target === "object" ? link.target.id : link.target;
      const sourceNode = states.code.entityMap[sourceId];
      const targetNode = states.code.entityMap[targetId];
      if (!sourceNode || !targetNode) return;
      if (!fileSet.has(sourceNode.file_path) || !fileSet.has(targetNode.file_path)) return;
      if (sourceNode.file_path === targetNode.file_path) return;
      const key = `${sourceNode.file_path}:${targetNode.file_path}:${link.type}`;
      if (!aggregated[key]) {
        aggregated[key] = {
          id: `file-edge:${key}`,
          source: `file:${sourceNode.file_path}`,
          target: `file:${targetNode.file_path}`,
          type: link.type,
          description: `${link.type} between files`,
          count: 0,
        };
      }
      aggregated[key].count += 1;
      aggregated[key].description = `${link.type}: ${aggregated[key].count}`;
    });
    Object.values(aggregated).forEach((link) => states.architecture.links.push(link));

    bindState("architecture");
    resetViewTransform();
    initSimulation();
    renderGraph();
    syncArchitectureBackButton();
    renderDetailMessage(`Showing files for ${module.display_name || module.module_id}. Hover to inspect dependencies. Click a file to drill into entities.`);
    updateStats({ entities: states.architecture.nodes.length, edges: states.architecture.links.length });
  }

  function renderArchitectureEntityView(filePath) {
    architectureViewMode = "entity";
    selectedNode = null;
    setArchitectureContext({ moduleId: architectureContext.moduleId, filePath });
    clearState("architecture");
    linkGroup.selectAll("*").remove();
    nodeGroup.selectAll("*").remove();
    g.selectAll(".arch-layer-label").remove();
    g.selectAll(".arch-lanes").remove();
    states.code.nodes
      .filter((node) => node.file_path === filePath)
      .forEach((node) => {
        const copy = {
          ...node,
          architectureLevel: "entity",
        };
        states.architecture.nodes.push(copy);
        states.architecture.entityMap[copy.id] = copy;
      });

    states.code.links.forEach((link) => {
      const sourceId = typeof link.source === "object" ? link.source.id : link.source;
      const targetId = typeof link.target === "object" ? link.target.id : link.target;
      if (!states.architecture.entityMap[sourceId] || !states.architecture.entityMap[targetId]) return;
      states.architecture.links.push({
        id: link.id,
        source: sourceId,
        target: targetId,
        type: link.type,
        file_path: link.file_path || "",
        line: link.line || 0,
        description: link.description || "",
      });
    });

    bindState("architecture");
    resetViewTransform();
    initSimulation();
    renderGraph();
    syncArchitectureBackButton();
    renderDetailMessage(`Showing entities for ${filePath}. Hover to inspect dependencies. Use Back to return to files.`);
    updateStats({ entities: states.architecture.nodes.length, edges: states.architecture.links.length });
  }

  function goBackArchitectureLevel() {
    const target = architectureInteractionsApi
      ? architectureInteractionsApi.getBackTarget(architectureViewMode, architectureContext)
      : { viewMode: "module", moduleId: null, filePath: null };

    if (target.viewMode === "file" && target.moduleId) {
      renderArchitectureFileView(target.moduleId);
      return;
    }
    renderArchitectureModuleView();
  }

  function loadFlowIndex() {
    fetch("/api/flow/index")
      .then((r) => r.json())
      .then((data) => {
        const entries = data.entries || {};
        flowCandidates = [...(entries.entity || []), ...(entries.file || [])];
        if (!flowEntryInput.value && flowCandidates[0]) {
          flowEntryInput.value = flowCandidates[0].value;
        }
      })
      .catch(() => { });
  }

  function loadFlow(entry) {
    if (!entry) {
      clearState("flow");
      if (activeView === "flow") {
        bindState("flow");
        renderGraph();
        renderDetailMessage(defaultDetailMessage());
        updateStats({ entities: 0, edges: 0 });
      }
      return;
    }

    fetch(`/api/flow?entry=${encodeURIComponent(entry)}`)
      .then((r) => r.json())
      .then((data) => {
        clearState("flow");
        if (data.ok) {
          (data.steps || []).forEach((step) => {
            const node = {
              id: step.step_id,
              name: step.label,
              type: "function",
              file_path: step.file_path || "",
              description: step.ref || "",
              signature: step.ref || "",
              language: "",
              degree: 0,
              degreeTier: "base",
            };
            states.flow.nodes.push(node);
            states.flow.entityMap[node.id] = node;
          });
          (data.transitions || []).forEach((transition, index) => {
            states.flow.links.push({
              id: `flow:${transition.source}:${transition.target}:${index}`,
              source: transition.source,
              target: transition.target,
              type: transition.edge_type || "calls",
              file_path: "",
              line: 0,
              description: transition.edge_type || "",
            });
          });
          renderDetailMessage(`Flow generated for ${data.entry ? data.entry.value : entry}`);
        } else {
          const suggestion = (data.candidates || []).slice(0, 5).map((item) => item.value).join("\n");
          renderDetailMessage(suggestion ? `Flow entry not found. Try:\n${suggestion}` : "Flow entry not found.");
        }
        if (activeView === "flow") {
          bindState("flow");
          resetViewTransform();
          initSimulation();
          renderGraph();
          updateStats({ entities: states.flow.nodes.length, edges: states.flow.links.length });
        }
      })
      .catch((error) => {
        renderDetailMessage(`Failed to load flow: ${error.message}`);
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
      if (activeView === "code") {
        updateStats(data.summary);
      }
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
        mergeEntities(states.code, entities);
        mergeEdges(states.code, edges);
        if (activeView === "code") {
          bindState("code");
          renderGraph();
          updateStats({ entities: states.code.nodes.length, edges: states.code.links.length });
        }
      }
    } else if (type === "entities.deduped" || type === "relations.resolved") {
      const edges = payload.edges || [];
      if (edges.length) {
        mergeEdges(states.code, edges);
        if (activeView === "code") {
          bindState("code");
          renderGraph();
          updateStats({ entities: states.code.nodes.length, edges: states.code.links.length });
        }
      }
    } else if (type === "analysis.completed") {
      loadCodeGraph();
      loadArchitecture();
      loadFlowIndex();
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

  function updateSearchPlaceholder(viewName) {
    const view = viewName || activeView;
    searchInput.placeholder =
      view === "architecture" ? "Search modules..." :
      view === "flow" ? "Search flow steps..." :
      "Search entities...";
  }

  function setActiveView(nextView) {
    viewTabs.forEach((button) => {
      button.classList.toggle("active", button.dataset.view === nextView);
    });
    flowControls.hidden = nextView !== "flow";
    legend.style.display = nextView === "flow" ? "none" : "flex";
    updateSearchPlaceholder(nextView);
    if (nextView === "architecture") {
      renderArchitectureModuleView();
      return;
    }
    selectedNode = null;
    bindState(nextView);
    resetViewTransform();
    initSimulation();
    renderGraph();
    syncArchitectureBackButton();
    renderDetailMessage(defaultDetailMessage());
    updateStats({ entities: nodes.length, edges: links.length });
  }

  viewTabs.forEach((button) => {
    button.addEventListener("click", () => {
      setActiveView(button.dataset.view);
    });
  });

  if (labelToggle) {
    syncLabelToggle();
    labelToggle.addEventListener("change", () => {
      showLabels = labelToggle.checked;
      renderGraph();
    });
  }

  if (flowRunButton) {
    flowRunButton.addEventListener("click", () => {
      setActiveView("flow");
      loadFlow(flowEntryInput.value.trim());
    });
  }

  if (flowEntryInput) {
    flowEntryInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        setActiveView("flow");
        loadFlow(flowEntryInput.value.trim());
      }
    });
  }

  if (architectureBackButton) {
    architectureBackButton.addEventListener("click", () => {
      goBackArchitectureLevel();
    });
  }

  // -- Chat -------------------------------------------------------------
  let thinkingTimer = null;

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

    source.addEventListener("error", () => {
      source.close();
      legacyPollChatTurn(turnId, stepCount);
    });
  }

  function updateThinkingSteps(step, count) {
    const thinkingEl = chatMessages.querySelector(".chat-msg.thinking");
    if (!thinkingEl) return;
    const bubble = thinkingEl.querySelector(".bubble");
    if (!bubble) return;

    const counterEl = bubble.querySelector(".thinking-step-count");
    if (counterEl) {
      counterEl.textContent = `Step ${count}`;
    }

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
      thinkingTimer = setInterval(() => {
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
    if (thinkingTimer) {
      clearInterval(thinkingTimer);
      thinkingTimer = null;
    }
    const el = chatMessages.querySelector(".chat-msg.thinking");
    if (el) el.remove();
  }

  // -- Init -------------------------------------------------------------
  window.addEventListener("resize", () => {
    setSidebarWidth("left", leftSidebarWidth);
    setSidebarWidth("right", rightSidebarWidth);
    if (activeView === "architecture" && architectureViewMode === "module") {
      renderArchitectureModuleView();
      return;
    }
    if (simulation) {
      simulation.force("center", d3.forceCenter(width() / 2, height() / 2));
      if (simulation.force("x")) simulation.force("x", d3.forceX(width() / 2).strength(0.05));
      if (simulation.force("y")) simulation.force("y", d3.forceY(height() / 2).strength(0.05));
      simulation.alpha(0.1).restart();
    }
  });

  initSidebarControls();
  updateSearchPlaceholder();
  bindState("code");
  initSimulation();
  renderGraph();
  renderDetailMessage(defaultDetailMessage());
  loadCodeGraph();
  loadArchitecture();
  loadFlowIndex();
  connectSSE();
})();
