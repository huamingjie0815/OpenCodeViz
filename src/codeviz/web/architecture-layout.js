(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.ArchitectureLayout = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const LAYER_ORDER = ["entry", "interface", "application", "analysis", "data", "tooling"];

  function classifyArchitectureLayer(module) {
    const text = `${module.module_id || ""} ${module.display_name || ""}`.toLowerCase();
    if (/(^|\/)(bin|__main__|cli)(\/|$)/.test(text) || /\b(entry|main)\b/.test(text)) return "entry";
    if (/\b(web|ui|server|api|route|handler|controller)\b/.test(text)) return "interface";
    if (/\b(project|app|command|commands|service)\b/.test(text)) return "application";
    if (/\b(analysis|extract|fingerprint|parser|scan|index|qa|agent)\b/.test(text)) return "analysis";
    if (/\b(storage|model|config|runtime|state|cache|db|data)\b/.test(text)) return "data";
    return "tooling";
  }

  function buildNeighborMaps(dependencies) {
    const incoming = new Map();
    const outgoing = new Map();
    dependencies.forEach((dependency) => {
      const weight = (dependency.imports_count || 0) + (dependency.calls_count || 0) + (dependency.uses_count || 0) || 1;
      if (!outgoing.has(dependency.source_module_id)) outgoing.set(dependency.source_module_id, []);
      if (!incoming.has(dependency.target_module_id)) incoming.set(dependency.target_module_id, []);
      outgoing.get(dependency.source_module_id).push({ id: dependency.target_module_id, weight });
      incoming.get(dependency.target_module_id).push({ id: dependency.source_module_id, weight });
    });
    return { incoming, outgoing };
  }

  function buildModuleWeightMap(modules, dependencies) {
    const weights = new Map(modules.map((module) => [module.module_id, 0]));
    dependencies.forEach((dependency) => {
      const weight = (dependency.imports_count || 0) + (dependency.calls_count || 0) + (dependency.uses_count || 0) || 1;
      weights.set(dependency.source_module_id, (weights.get(dependency.source_module_id) || 0) + weight);
      weights.set(dependency.target_module_id, (weights.get(dependency.target_module_id) || 0) + weight);
    });
    return weights;
  }

  function weightedAverage(values) {
    if (!values.length) return null;
    let total = 0;
    let weightTotal = 0;
    values.forEach((item) => {
      total += item.value * item.weight;
      weightTotal += item.weight;
    });
    return weightTotal ? total / weightTotal : null;
  }

  function orderLaneNodes(layerModules, rowIndexMap, neighbors) {
    const scored = layerModules.map((module, index) => {
      const incomingRows = (neighbors.incoming.get(module.module_id) || [])
        .map((item) => rowIndexMap.get(item.id))
        .filter((value) => Number.isFinite(value))
        .map((value, i) => ({ value, weight: (neighbors.incoming.get(module.module_id) || [])[i].weight }));
      const outgoingRows = (neighbors.outgoing.get(module.module_id) || [])
        .map((item) => rowIndexMap.get(item.id))
        .filter((value) => Number.isFinite(value))
        .map((value, i) => ({ value, weight: (neighbors.outgoing.get(module.module_id) || [])[i].weight }));
      const barycenter = weightedAverage([...incomingRows, ...outgoingRows]);
      const weight =
        (incomingRows.reduce((sum, item) => sum + item.weight, 0)) +
        (outgoingRows.reduce((sum, item) => sum + item.weight, 0));
      const sizeScore = (module.file_paths || []).length + (module.entity_ids || []).length;
      return {
        module,
        barycenter,
        weight,
        sizeScore,
        index,
      };
    });
    scored.sort((left, right) => {
      const leftHasBarycenter = Number.isFinite(left.barycenter);
      const rightHasBarycenter = Number.isFinite(right.barycenter);
      if (leftHasBarycenter !== rightHasBarycenter) return leftHasBarycenter ? -1 : 1;
      if (leftHasBarycenter && rightHasBarycenter && left.barycenter !== right.barycenter) {
        return left.barycenter - right.barycenter;
      }
      if (left.weight !== right.weight) return right.weight - left.weight;
      if (left.sizeScore !== right.sizeScore) return right.sizeScore - left.sizeScore;
      return (left.module.display_name || left.module.module_id).localeCompare(right.module.display_name || right.module.module_id);
    });
    return scored.map((item) => item.module);
  }

  function normalizeArchitectureModules(modules, dependencies) {
    const weightMap = buildModuleWeightMap(modules, dependencies);
    const toolingModules = modules.filter((module) => classifyArchitectureLayer(module) === "tooling");
    const collapsedTooling = toolingModules.filter((module) =>
      (weightMap.get(module.module_id) || 0) <= 6 && ((module.entity_ids || []).length <= 8)
    );
    if (collapsedTooling.length < 3) {
      return { modules, dependencies };
    }

    const collapsedIds = new Set(collapsedTooling.map((module) => module.module_id));
    const aggregateId = "layer/tooling-bundle";
    const aggregateModule = {
      module_id: aggregateId,
      display_name: `tooling bundle (${collapsedTooling.length})`,
      source_dirs: collapsedTooling.flatMap((module) => module.source_dirs || []),
      file_paths: collapsedTooling.flatMap((module) => module.file_paths || []),
      entity_ids: collapsedTooling.flatMap((module) => module.entity_ids || []),
      grouped_modules: collapsedTooling.map((module) => ({
        module_id: module.module_id,
        display_name: module.display_name || module.module_id,
      })),
    };

    const nextModules = modules.filter((module) => !collapsedIds.has(module.module_id));
    nextModules.push(aggregateModule);

    const dependencyBuckets = new Map();
    dependencies.forEach((dependency) => {
      const source = collapsedIds.has(dependency.source_module_id) ? aggregateId : dependency.source_module_id;
      const target = collapsedIds.has(dependency.target_module_id) ? aggregateId : dependency.target_module_id;
      if (source === target) return;
      const key = `${source}:${target}`;
      if (!dependencyBuckets.has(key)) {
        dependencyBuckets.set(key, {
          source_module_id: source,
          target_module_id: target,
          imports_count: 0,
          calls_count: 0,
          uses_count: 0,
        });
      }
      const bucket = dependencyBuckets.get(key);
      bucket.imports_count += dependency.imports_count || 0;
      bucket.calls_count += dependency.calls_count || 0;
      bucket.uses_count += dependency.uses_count || 0;
    });

    const nextDependencies = Array.from(dependencyBuckets.values()).map((dependency) => {
      const entries = [
        ["imports", dependency.imports_count],
        ["calls", dependency.calls_count],
        ["uses", dependency.uses_count],
      ];
      entries.sort((left, right) => right[1] - left[1]);
      return {
        ...dependency,
        dominant_edge_type: entries[0][1] > 0 ? entries[0][0] : "uses",
      };
    });

    return { modules: nextModules, dependencies: nextDependencies };
  }

  function buildArchitectureLayout(modules, dependencies, canvasWidth, canvasHeight) {
    const normalized = normalizeArchitectureModules(modules, dependencies);
    modules = normalized.modules;
    dependencies = normalized.dependencies;
    const visibleLayers = LAYER_ORDER.filter((layer) =>
      modules.some((module) => classifyArchitectureLayer(module) === layer)
    );
    const width = Math.max(canvasWidth, 960);
    const height = Math.max(canvasHeight, 560);
    const topPadding = 64;
    const bottomPadding = 36;
    const leftPadding = 56;
    const rightPadding = 56;
    const laneGap = 18;
    const laneWidth = visibleLayers.length > 0
      ? Math.max(136, Math.floor((width - leftPadding - rightPadding - laneGap * Math.max(visibleLayers.length - 1, 0)) / Math.max(visibleLayers.length, 1)))
      : width - leftPadding - rightPadding;
    const nodeWidth = Math.min(200, Math.max(132, laneWidth - 18));
    const nodeHeight = 68;

    const dependencyScore = new Map();
    dependencies.forEach((dependency) => {
      dependencyScore.set(
        `${dependency.source_module_id}:${dependency.target_module_id}`,
        (dependency.imports_count || 0) + (dependency.calls_count || 0) + (dependency.uses_count || 0)
      );
    });

    const neighbors = buildNeighborMaps(dependencies);
    const layerModulesMap = new Map();
    visibleLayers.forEach((layer) => {
      const layerModules = modules
        .filter((module) => classifyArchitectureLayer(module) === layer)
        .sort((left, right) => {
          const leftScore = (left.file_paths || []).length + (left.entity_ids || []).length;
          const rightScore = (right.file_paths || []).length + (right.entity_ids || []).length;
          return rightScore - leftScore || (left.display_name || left.module_id).localeCompare(right.display_name || right.module_id);
        });
      layerModulesMap.set(layer, layerModules);
    });

    const rowIndexMap = new Map();
    for (let pass = 0; pass < 3; pass += 1) {
      visibleLayers.forEach((layer) => {
        const ordered = orderLaneNodes(layerModulesMap.get(layer) || [], rowIndexMap, neighbors);
        layerModulesMap.set(layer, ordered);
        ordered.forEach((module, index) => rowIndexMap.set(module.module_id, index));
      });
      [...visibleLayers].reverse().forEach((layer) => {
        const ordered = orderLaneNodes(layerModulesMap.get(layer) || [], rowIndexMap, neighbors);
        layerModulesMap.set(layer, ordered);
        ordered.forEach((module, index) => rowIndexMap.set(module.module_id, index));
      });
    }

    const lanes = visibleLayers.map((layer, index) => ({
      layer,
      x: leftPadding + index * (laneWidth + laneGap),
      y: topPadding - 26,
      width: laneWidth,
      height: height - topPadding - bottomPadding + 18,
    }));

    const positionedNodes = [];
    visibleLayers.forEach((layer, columnIndex) => {
      const lane = lanes[columnIndex];
      const layerModules = layerModulesMap.get(layer) || [];
      const usableHeight = height - topPadding - bottomPadding;
      const rowGap = layerModules.length > 0
        ? Math.max(nodeHeight + 18, Math.floor(usableHeight / Math.max(layerModules.length, 1)))
        : usableHeight;
      const totalHeight = (layerModules.length - 1) * rowGap + nodeHeight;
      const startY = topPadding + Math.max(0, (usableHeight - totalHeight) / 2) + nodeHeight / 2;
      layerModules.forEach((module, rowIndex) => {
        positionedNodes.push({
          id: module.module_id,
          name: module.display_name || module.module_id,
          layer,
          x: lane.x + lane.width / 2,
          y: startY + rowIndex * rowGap,
          width: nodeWidth,
          height: nodeHeight,
          fileCount: (module.file_paths || []).length,
          entityCount: (module.entity_ids || []).length,
          module,
        });
      });
    });

    const nodeById = Object.fromEntries(positionedNodes.map((node) => [node.id, node]));
    const routedEdges = dependencies
      .map((dependency) => {
        const source = nodeById[dependency.source_module_id];
        const target = nodeById[dependency.target_module_id];
        if (!source || !target) return null;
        const sourceX = source.x + source.width / 2;
        const targetX = target.x - target.width / 2;
        const sourceY = source.y;
        const targetY = target.y;
        const delta = Math.max(40, Math.abs(targetX - sourceX) * 0.45);
        return {
          id: `${dependency.source_module_id}:${dependency.target_module_id}`,
          source: dependency.source_module_id,
          target: dependency.target_module_id,
          edgeType: dependency.dominant_edge_type || "uses",
          strength: dependencyScore.get(`${dependency.source_module_id}:${dependency.target_module_id}`) || 1,
          path: `M ${sourceX} ${sourceY} C ${sourceX + delta} ${sourceY}, ${targetX - delta} ${targetY}, ${targetX} ${targetY}`,
          description: `imports=${dependency.imports_count || 0}, calls=${dependency.calls_count || 0}, uses=${dependency.uses_count || 0}`,
        };
      })
      .filter(Boolean);

    return { nodes: positionedNodes, edges: routedEdges, layers: visibleLayers, lanes };
  }

  return {
    LAYER_ORDER,
    classifyArchitectureLayer,
    normalizeArchitectureModules,
    buildArchitectureLayout,
  };
});
