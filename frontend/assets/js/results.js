/* RESULTS.JS - Dynamic Card Rendering and Detail Diagrams */

const NS = 'http://www.w3.org/2000/svg';
const M1_PREVIEW_LIMIT = 5;
const M2_PREVIEW_LIMIT = 3;

const LAYER_COLORS = {
  entry: { fill: 'rgba(59,130,246,0.12)', stroke: '#3B82F6', strokeOpacity: '0.55' },
  route: { fill: 'rgba(59,130,246,0.12)', stroke: '#3B82F6', strokeOpacity: '0.55' },
  plugin: { fill: 'rgba(168,85,247,0.10)', stroke: '#A855F7', strokeOpacity: '0.45' },
  store: { fill: 'rgba(0,230,120,0.10)', stroke: '#00E678', strokeOpacity: '0.55' },
  controller: { fill: 'rgba(59,130,246,0.10)', stroke: '#3B82F6', strokeOpacity: '0.40' },
  service: { fill: 'rgba(168,85,247,0.12)', stroke: '#A855F7', strokeOpacity: '0.55' },
  model: { fill: 'rgba(239,68,68,0.10)', stroke: '#EF4444', strokeOpacity: '0.45' },
  util: { fill: 'rgba(255,255,255,0.04)', stroke: 'rgba(255,255,255,0.18)', strokeOpacity: '1' },
  config: { fill: 'rgba(234,179,8,0.08)', stroke: '#EAB308', strokeOpacity: '0.40' },
  script: { fill: 'rgba(234,179,8,0.10)', stroke: '#EAB308', strokeOpacity: '0.45' },
  leaf: { fill: 'rgba(255,255,255,0.03)', stroke: 'rgba(255,255,255,0.10)', strokeOpacity: '1' },
  unknown: { fill: 'rgba(255,255,255,0.04)', stroke: 'rgba(255,255,255,0.15)', strokeOpacity: '1' }
};

const LAYER_COLUMNS = {
  entry: 0,
  route: 0,
  config: 0,
  plugin: 1,
  store: 1,
  controller: 2,
  service: 2,
  model: 3,
  util: 3,
  leaf: 4,
  script: 4,
  unknown: 2
};

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = String(str ?? '');
  return div.innerHTML;
}

function truncate(text, maxLen) {
  const value = String(text ?? '');
  return value.length > maxLen ? value.slice(0, maxLen - 3) + '...' : value;
}

function truncateLabel(label, max) {
  if (!label) return '';
  if (label.length <= max) return label;
  const dotIdx = label.lastIndexOf('.');
  const ext = dotIdx > 0 ? label.slice(dotIdx) : '';
  const allowed = max - ext.length - 1;
  if (allowed <= 0) return label.slice(0, Math.max(0, max - 1)) + '\u2026';
  return label.slice(0, allowed) + '\u2026' + ext;
}

function baseName(pathOrName) {
  const raw = String(pathOrName ?? '');
  const parts = raw.split('/').filter(Boolean);
  return parts.length ? parts[parts.length - 1] : raw;
}

function stripStepPrefix(stepText) {
  return String(stepText ?? '').replace(/^Step\s*\d+:\s*/i, '').trim();
}

function assignLayer(node, edges) {
  if (node.layer && node.layer !== 'unknown') return node.layer;

  const id = node.id;
  const isSource = edges.some((e) => e.source === id);
  const isTarget = edges.some((e) => e.target === id);

  const label = (node.label || '').toLowerCase();
  if (label.includes('route') || label.includes('router')) return 'route';
  if (label.includes('store') || label.includes('state')) return 'store';
  if (label.includes('service') || label.includes('api')) return 'service';
  if (label.includes('controller')) return 'controller';
  if (label.includes('model') || label.includes('schema')) return 'model';
  if (label.includes('config') || label.includes('vite') || label.includes('eslint') || label.includes('cypress')) return 'config';
  if (label.includes('util') || label.includes('helper')) return 'util';
  if (label.includes('main') || label.includes('app') || (label.includes('index') && !isTarget)) return 'entry';
  if (label.includes('plugin') || label.includes('vuetify')) return 'plugin';
  if (label.endsWith('.py')) return 'script';

  if (isSource && !isTarget) return 'entry';
  if (!isSource && isTarget) return 'leaf';
  return 'util';
}

function getLayerColors(layer) {
  return LAYER_COLORS[layer] || LAYER_COLORS.unknown;
}

function showCardError(cardId, message) {
  const el = document.getElementById(cardId);
  if (!el) return;
  el.innerHTML = '<div class="card-error">? ' + escapeHtml(message) + '</div>';
}

function showSkeletons() {
  const ids = ['card-folder-structure', 'card-entry-point', 'card-dependency-map'];
  const widths = ['80%', '60%', '90%', '50%'];

  ids.forEach((id) => {
    const el = document.getElementById(id);
    if (!el) return;
    let html = '';
    widths.forEach((w) => {
      html += '<div class="skeleton-line" style="width:' + w + '"></div>';
    });
    el.innerHTML = html;
  });
}

function hideSkeletons() {
  const ids = ['card-folder-structure', 'card-entry-point', 'card-dependency-map'];
  ids.forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = '';
  });
}

function normalizeGraphData(data) {
  const nodes = Array.isArray(data?.m3_nodes) ? data.m3_nodes : [];
  const edges = Array.isArray(data?.m3_edges) ? data.m3_edges : [];

  if (nodes.length || edges.length) {
    return { nodes, edges };
  }

  const fallbackEdges = [];
  if (Array.isArray(data?.m3_dependency_graph)) {
    data.m3_dependency_graph.forEach((e) => {
      if (e && e.source && e.target) fallbackEdges.push({ source: e.source, target: e.target });
    });
  }

  const ids = new Set();
  fallbackEdges.forEach((e) => {
    ids.add(e.source);
    ids.add(e.target);
  });

  const fallbackNodes = [...ids].map((id) => ({ id, label: baseName(id), layer: 'unknown' }));
  return { nodes: fallbackNodes, edges: fallbackEdges };
}

function renderM1(m1Data) {
  const container = document.getElementById('card-folder-structure');
  if (!container) return;

  try {
    if (!m1Data || !m1Data.folders || typeof m1Data.folders !== 'object') {
      throw new Error('Missing folder data');
    }

    const rows = Object.entries(m1Data.folders);
    const limited = rows.slice(0, M1_PREVIEW_LIMIT);
    const remaining = Math.max(0, rows.length - limited.length);

    let html = '';
    if (m1Data.architecture_style) {
      html += '<p class="arch-style">// ' + escapeHtml(m1Data.architecture_style) + '</p>';
    }

    limited.forEach(([name, desc], i) => {
      html +=
        '<div class="folder-row" style="animation-delay:' + i * 80 + 'ms">' +
        '<span class="folder-name">' + escapeHtml(name) + '</span>' +
        '<span class="folder-sep">-&gt;</span>' +
        '<span class="folder-desc">' + escapeHtml(desc) + '</span>' +
        '</div>';
    });

    if (remaining > 0) {
      html += '<p class="entry-dim">... and ' + remaining + ' more</p>';
    }

    container.innerHTML = html;
  } catch (err) {
    showCardError('card-folder-structure', 'Failed to render folder structure');
  }
}

function createText(svg, x, y, fill, size, family, value, anchor = 'start', weight = '400') {
  const t = document.createElementNS(NS, 'text');
  t.setAttribute('x', String(x));
  t.setAttribute('y', String(y));
  t.setAttribute('fill', fill);
  t.setAttribute('font-size', String(size));
  t.setAttribute('font-family', family);
  t.setAttribute('text-anchor', anchor);
  t.setAttribute('font-weight', weight);
  t.textContent = value;
  svg.appendChild(t);
  return t;
}

function renderM2Preview(m2Data) {
  const container = document.getElementById('card-entry-point');
  if (!container) return;

  try {
    if (!m2Data || !m2Data.entry_file) throw new Error('Missing entry point data');

    const steps = Array.isArray(m2Data.execution_flow) ? m2Data.execution_flow : [];
    const previewSteps = steps.slice(0, M2_PREVIEW_LIMIT);
    const remaining = Math.max(0, steps.length - previewSteps.length);

    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('viewBox', '0 0 560 220');
    svg.setAttribute('width', '100%');

    const defs = document.createElementNS(NS, 'defs');
    defs.innerHTML =
      '<marker id="m2-preview-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto">' +
      '<path d="M2 1L8 5L2 9" fill="none" stroke="rgba(59,130,246,0.8)" stroke-width="1.5"/></marker>';
    svg.appendChild(defs);

    const entryRect = document.createElementNS(NS, 'rect');
    entryRect.setAttribute('x', '20');
    entryRect.setAttribute('y', '12');
    entryRect.setAttribute('width', '520');
    entryRect.setAttribute('height', '30');
    entryRect.setAttribute('rx', '8');
    entryRect.setAttribute('fill', 'rgba(0,230,120,0.08)');
    entryRect.setAttribute('stroke', '#00E678');
    svg.appendChild(entryRect);

    createText(svg, 32, 31, '#E2E8F0', 12, 'JetBrains Mono, monospace', 'Entry: ' + truncate(m2Data.entry_file, 55), 'start', '600');

    const baseY = 58;
    previewSteps.forEach((step, i) => {
      const y = baseY + i * 48;

      const rect = document.createElementNS(NS, 'rect');
      rect.setAttribute('x', '20');
      rect.setAttribute('y', String(y));
      rect.setAttribute('width', '520');
      rect.setAttribute('height', '34');
      rect.setAttribute('rx', '10');
      rect.setAttribute('fill', 'rgba(255,255,255,0.04)');
      rect.setAttribute('stroke', 'rgba(59,130,246,0.4)');
      svg.appendChild(rect);

      createText(svg, 34, y + 21, '#E2E8F0', 12, 'JetBrains Mono, monospace', truncate(stripStepPrefix(step), 55));

      if (i < previewSteps.length - 1) {
        const arrow = document.createElementNS(NS, 'line');
        arrow.setAttribute('x1', '280');
        arrow.setAttribute('y1', String(y + 34));
        arrow.setAttribute('x2', '280');
        arrow.setAttribute('y2', String(y + 48));
        arrow.setAttribute('stroke', 'rgba(59,130,246,0.6)');
        arrow.setAttribute('stroke-width', '1.5');
        arrow.setAttribute('marker-end', 'url(#m2-preview-arrow)');
        svg.appendChild(arrow);
      }
    });

    if (remaining > 0) {
      createText(svg, 30, 214, '#64748B', 12, 'JetBrains Mono, monospace', '? ' + remaining + ' more steps');
    }

    container.innerHTML = '';
    container.appendChild(svg);
  } catch (err) {
    showCardError('card-entry-point', 'Failed to render entry point');
  }
}

function renderM3Preview(nodes, edges) {
  const container = document.getElementById('card-dependency-map');
  if (!container) return;

  try {
    if (!Array.isArray(nodes) || !Array.isArray(edges) || nodes.length === 0) {
      throw new Error('Missing dependency data');
    }

    const normalizedNodes = nodes
      .filter((n) => n && n.id)
      .map((n) => ({
        ...n,
        label: n.label || baseName(n.id)
      }));

    normalizedNodes.forEach((node) => {
      node._layer = assignLayer(node, edges);
    });

    const outDegree = new Map();
    const inDegree = new Map();
    normalizedNodes.forEach((n) => {
      outDegree.set(n.id, 0);
      inDegree.set(n.id, 0);
    });
    edges.forEach((e) => {
      if (outDegree.has(e.source)) outDegree.set(e.source, (outDegree.get(e.source) || 0) + 1);
      if (inDegree.has(e.target)) inDegree.set(e.target, (inDegree.get(e.target) || 0) + 1);
    });

    const topIds = [...normalizedNodes]
      .sort((a, b) => ((outDegree.get(b.id) || 0) * 2 + (inDegree.get(b.id) || 0)) - ((outDegree.get(a.id) || 0) * 2 + (inDegree.get(a.id) || 0)))
      .slice(0, 8)
      .map((n) => n.id);

    const topSet = new Set(topIds);
    const selectedNodes = normalizedNodes.filter((n) => topSet.has(n.id));
    const selectedEdges = edges.filter((e) => topSet.has(e.source) && topSet.has(e.target));

    const pos = new Map();
    selectedNodes.forEach((n, i) => {
      const col = i < 4 ? 0 : 1;
      const row = i % 4;
      const x = col === 0 ? 60 : 340;
      const y = 20 + row * 44;
      pos.set(n.id, { x, y });
    });

    const nodeMap = new Map(selectedNodes.map((n) => [n.id, n]));

    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('viewBox', '0 0 560 200');
    svg.setAttribute('width', '100%');

    selectedEdges.forEach((e) => {
      const s = pos.get(e.source);
      const t = pos.get(e.target);
      if (!s || !t) return;
      const sx = s.x + 180;
      const sy = s.y + 16;
      const tx = t.x;
      const ty = t.y + 16;
      const cx = (sx + tx) / 2;

      const path = document.createElementNS(NS, 'path');
      path.setAttribute('d', 'M ' + sx + ' ' + sy + ' Q ' + cx + ' ' + sy + ' ' + tx + ' ' + ty);
      path.setAttribute('stroke', 'rgba(255,255,255,0.12)');
      path.setAttribute('stroke-width', '1');
      path.setAttribute('fill', 'none');
      svg.appendChild(path);
    });

    selectedNodes.forEach((n) => {
      const p = pos.get(n.id);
      if (!p) return;

      const colors = getLayerColors(n._layer);

      const rect = document.createElementNS(NS, 'rect');
      rect.setAttribute('x', String(p.x));
      rect.setAttribute('y', String(p.y));
      rect.setAttribute('width', '180');
      rect.setAttribute('height', '32');
      rect.setAttribute('rx', '6');
      rect.setAttribute('fill', colors.fill);
      rect.setAttribute('stroke', colors.stroke);
      rect.setAttribute('stroke-opacity', colors.strokeOpacity || '1');
      svg.appendChild(rect);

      createText(
        svg,
        p.x + 90,
        p.y + 20,
        '#E2E8F0',
        11,
        'JetBrains Mono, monospace',
        truncateLabel(n.label || baseName(n.id), 20),
        'middle',
        '500'
      );
    });

    container.innerHTML = '';
    container.appendChild(svg);
  } catch (err) {
    showCardError('card-dependency-map', 'Failed to render dependency map');
  }
}

function renderM1Full(m1Data) {
  const container = document.getElementById('m1-diagram');
  if (!container) return;

  try {
    if (!m1Data || !m1Data.folders || typeof m1Data.folders !== 'object') {
      throw new Error('No folder data');
    }

    function wrapText(text, maxCharsPerLine) {
      const words = String(text ?? '').split(' ');
      const lines = [];
      let current = '';
      for (const word of words) {
        if ((current + ' ' + word).trim().length <= maxCharsPerLine) {
          current = (current + ' ' + word).trim();
        } else {
          if (current) lines.push(current);
          current = word;
        }
      }
      if (current) lines.push(current);
      return lines;
    }

    const folders = Object.entries(m1Data.folders);
    const LINE_HEIGHT = 18;
    const ROW_PADDING_V = 14;
    const DESC_X = 220;
    const NAME_X = 50;
    const SVG_WIDTH = 860;
    const startY = 64;

    let rowsSvg = '';
    let currentY = startY;

    folders.forEach(([name, desc]) => {
      const curatedDesc = typeof curateDescription === 'function' ? curateDescription(desc, 999) : String(desc ?? '');
      const descLines = wrapText(curatedDesc, 55);
      const rowHeight = Math.max(
        ROW_PADDING_V * 2 + LINE_HEIGHT,
        ROW_PADDING_V * 2 + descLines.length * LINE_HEIGHT
      );

      const rowY = currentY;
      const nameCY = rowY + rowHeight / 2;
      const firstLineY = rowY + ROW_PADDING_V + LINE_HEIGHT / 2;

      rowsSvg +=
        '<rect x="30" y="' + rowY + '" width="' + (SVG_WIDTH - 60) + '" height="' + rowHeight + '" rx="4" ' +
        'fill="rgba(255,255,255,0.02)" stroke="rgba(255,255,255,0.04)" stroke-width="0.5"/>';

      rowsSvg +=
        '<text x="' + NAME_X + '" y="' + nameCY + '" dominant-baseline="central" ' +
        'font-family="JetBrains Mono, monospace" font-size="13" font-weight="600" fill="#00E678">' +
        escapeHtml(truncate(name, 28)) +
        '</text>';

      descLines.forEach((line, i) => {
        const lineY = firstLineY + i * LINE_HEIGHT;
        rowsSvg +=
          '<text x="' + DESC_X + '" y="' + lineY + '" dominant-baseline="central" ' +
          'font-family="JetBrains Mono, monospace" font-size="12" fill="#64748B">' +
          escapeHtml(line) +
          '</text>';
      });

      currentY += rowHeight + 8;
    });

    const totalHeight = currentY + 40;
    const badgeText = 'Architecture: ' + truncate(m1Data.architecture_style || 'unknown', 96);
    const svgMarkup =
      '<svg viewBox="0 0 ' + SVG_WIDTH + ' ' + totalHeight + '" width="100%">' +
      '<rect x="24" y="16" width="712" height="28" rx="14" fill="rgba(0,230,120,0.12)" stroke="rgba(0,230,120,0.3)"/>' +
      '<text x="36" y="34" fill="#00E678" font-size="12" font-family="JetBrains Mono, monospace" text-anchor="start" font-weight="500">' +
      escapeHtml(badgeText) +
      '</text>' +
      rowsSvg +
      '</svg>';

    container.innerHTML = svgMarkup;
  } catch (err) {
    container.innerHTML = '<p class="diagram-fallback">No folder data available</p>';
  }
}

function wrapTwoLines(text, maxChars) {
  const words = String(text || '').split(/\s+/).filter(Boolean);
  if (!words.length) return ['', ''];

  let line1 = '';
  let line2 = '';

  words.forEach((w) => {
    const candidate1 = (line1 ? line1 + ' ' : '') + w;
    if (candidate1.length <= maxChars || !line1) {
      line1 = candidate1;
      return;
    }
    if (!line2) {
      line2 = w;
      return;
    }
    const candidate2 = line2 + ' ' + w;
    if (candidate2.length <= maxChars) {
      line2 = candidate2;
    }
  });

  return [line1, line2 ? truncate(line2, maxChars) : ''];
}

function renderM2Full(m2Data) {
  const container = document.getElementById('m2-diagram');
  if (!container) return;

  try {
    if (!m2Data || !m2Data.entry_file) throw new Error('Missing entry data');
    const steps = Array.isArray(m2Data.execution_flow) ? m2Data.execution_flow : [];

    const height = 120 + steps.length * 96;
    const boxX = 120;
    const boxW = 520;

    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('viewBox', '0 0 760 ' + height);
    svg.setAttribute('width', '100%');

    const defs = document.createElementNS(NS, 'defs');
    defs.innerHTML =
      '<marker id="m2-full-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto">' +
      '<path d="M2 1L8 5L2 9" fill="none" stroke="#3B82F6" stroke-width="1.5"/></marker>';
    svg.appendChild(defs);

    const entryRect = document.createElementNS(NS, 'rect');
    entryRect.setAttribute('x', String(boxX));
    entryRect.setAttribute('y', '24');
    entryRect.setAttribute('width', String(boxW));
    entryRect.setAttribute('height', '56');
    entryRect.setAttribute('rx', '10');
    entryRect.setAttribute('fill', 'rgba(0,230,120,0.08)');
    entryRect.setAttribute('stroke', '#00E678');
    svg.appendChild(entryRect);

    createText(svg, boxX + 20, 57, '#E2E8F0', 13, 'JetBrains Mono, monospace', 'ENTRY: ' + truncate(m2Data.entry_file, 70), 'start', '600');

    steps.forEach((step, i) => {
      const y = 120 + i * 96;

      if (i === 0) {
        const arrowFromEntry = document.createElementNS(NS, 'line');
        arrowFromEntry.setAttribute('x1', String(boxX + boxW / 2));
        arrowFromEntry.setAttribute('y1', '80');
        arrowFromEntry.setAttribute('x2', String(boxX + boxW / 2));
        arrowFromEntry.setAttribute('y2', String(y));
        arrowFromEntry.setAttribute('stroke', 'rgba(59,130,246,0.5)');
        arrowFromEntry.setAttribute('stroke-width', '2');
        arrowFromEntry.setAttribute('marker-end', 'url(#m2-full-arrow)');
        svg.appendChild(arrowFromEntry);
      }

      const rect = document.createElementNS(NS, 'rect');
      rect.setAttribute('x', String(boxX));
      rect.setAttribute('y', String(y));
      rect.setAttribute('width', String(boxW));
      rect.setAttribute('height', '56');
      rect.setAttribute('rx', '10');
      rect.setAttribute('fill', 'rgba(14,20,28,0.8)');
      rect.setAttribute('stroke', 'rgba(59,130,246,0.35)');
      svg.appendChild(rect);

      const badge = document.createElementNS(NS, 'circle');
      badge.setAttribute('cx', String(boxX - 28));
      badge.setAttribute('cy', String(y + 28));
      badge.setAttribute('r', '12');
      badge.setAttribute('fill', 'rgba(59,130,246,0.2)');
      badge.setAttribute('stroke', '#3B82F6');
      svg.appendChild(badge);

      createText(svg, boxX - 28, y + 32, '#3B82F6', 11, 'JetBrains Mono, monospace', String(i + 1), 'middle', '700');

      const clean = stripStepPrefix(step);
      const [line1, line2] = wrapTwoLines(clean, 60);

      const text = document.createElementNS(NS, 'text');
      text.setAttribute('x', String(boxX + 20));
      text.setAttribute('y', String(y + 24));
      text.setAttribute('fill', '#E2E8F0');
      text.setAttribute('font-size', '13');
      text.setAttribute('font-family', 'JetBrains Mono, monospace');

      const t1 = document.createElementNS(NS, 'tspan');
      t1.setAttribute('x', String(boxX + 20));
      t1.setAttribute('dy', '0');
      t1.textContent = line1;
      text.appendChild(t1);

      if (line2) {
        const t2 = document.createElementNS(NS, 'tspan');
        t2.setAttribute('x', String(boxX + 20));
        t2.setAttribute('dy', '18');
        t2.textContent = line2;
        text.appendChild(t2);
      }

      svg.appendChild(text);

      if (i < steps.length - 1) {
        const arrow = document.createElementNS(NS, 'line');
        arrow.setAttribute('x1', String(boxX + boxW / 2));
        arrow.setAttribute('y1', String(y + 56));
        arrow.setAttribute('x2', String(boxX + boxW / 2));
        arrow.setAttribute('y2', String(y + 96));
        arrow.setAttribute('stroke', 'rgba(59,130,246,0.5)');
        arrow.setAttribute('stroke-width', '2');
        arrow.setAttribute('marker-end', 'url(#m2-full-arrow)');
        svg.appendChild(arrow);
      }
    });

    container.innerHTML = '';
    container.appendChild(svg);
  } catch (err) {
    container.innerHTML = '<p class="diagram-fallback">No execution flow data available</p>';
  }
}

function renderDependencyGraph(nodes, edges) {
  const container = document.getElementById('dep-diagram');
  if (!container) return;

  try {
    if (!Array.isArray(nodes) || !Array.isArray(edges) || nodes.length === 0) {
      throw new Error('No graph data');
    }

    const nodeMap = new Map();
    nodes.forEach((n) => {
      if (!n || !n.id) return;
      nodeMap.set(n.id, {
        id: n.id,
        label: n.label || baseName(n.id),
        layer: n.layer || 'unknown'
      });
    });

    const cleanEdges = [];
    edges.forEach((e) => {
      if (!e || !nodeMap.has(e.source) || !nodeMap.has(e.target)) return;
      cleanEdges.push({ source: e.source, target: e.target });
    });

    const normalizedNodes = [...nodeMap.values()];
    normalizedNodes.forEach((node) => {
      node._layer = assignLayer(node, cleanEdges);
    });

    const columns = [[], [], [], [], []];
    normalizedNodes.forEach((node) => {
      const col = LAYER_COLUMNS[node._layer] ?? LAYER_COLUMNS.unknown;
      columns[col].push(node);
    });

    columns.forEach((col) => {
      col.sort((a, b) => a.label.localeCompare(b.label));
    });

    const colX = [40, 220, 400, 580, 760];
    const nodeW = 150;
    const nodeH = 38;
    const colHeights = columns.map((col) => Math.max(col.length * 72, 300));
    const height = Math.max(...colHeights, 300) + 100;

    const pos = new Map();
    columns.forEach((col, colIndex) => {
      col.forEach((node, rowIndex) => {
        const x = colX[colIndex];
        const y = 70 + rowIndex * 72;
        pos.set(node.id, { x, y, col: colIndex });
      });
    });

    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('viewBox', '0 0 960 ' + height);
    svg.setAttribute('width', '100%');

    const defs = document.createElementNS(NS, 'defs');
    defs.innerHTML =
      '<marker id="dep-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="5" markerHeight="5" orient="auto-start-reverse">' +
      '<path d="M1 1L7 4L1 7" fill="none" stroke="rgba(255,255,255,0.25)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></marker>';
    svg.appendChild(defs);

    const headers = [
      'ENTRY / ROUTES',
      'PLUGINS / STATE',
      'CONTROLLERS / SERVICES',
      'MODELS / UTILS',
      'SCRIPTS / LEAVES'
    ];
    headers.forEach((name, i) => {
      createText(svg, colX[i] + nodeW / 2, 28, '#64748B', 9, 'JetBrains Mono, monospace', name, 'middle', '600')
        .setAttribute('letter-spacing', '1.8px');
    });

    cleanEdges.forEach((e) => {
      const s = pos.get(e.source);
      const t = pos.get(e.target);
      if (!s || !t) return;

      const sx = s.x + nodeW;
      const sy = s.y + 19;
      const tx = t.x;
      const ty = t.y + 19;

      let d = '';
      if (s.col === t.col) {
        d = 'M ' + sx + ' ' + sy + ' C ' + (sx + 60) + ' ' + sy + ' ' + (tx + 60) + ' ' + ty + ' ' + tx + ' ' + ty;
      } else {
        const midX = (sx + tx) / 2;
        d = 'M ' + sx + ' ' + sy + ' C ' + midX + ' ' + sy + ' ' + midX + ' ' + ty + ' ' + tx + ' ' + ty;
      }

      const path = document.createElementNS(NS, 'path');
      path.setAttribute('d', d);
      path.setAttribute('stroke', 'rgba(255,255,255,0.10)');
      path.setAttribute('stroke-width', '1.2');
      path.setAttribute('fill', 'none');
      path.setAttribute('marker-end', 'url(#dep-arrow)');
      svg.appendChild(path);
    });

    normalizedNodes.forEach((node) => {
      const p = pos.get(node.id);
      if (!p) return;

      const colors = getLayerColors(node._layer);

      const group = document.createElementNS(NS, 'g');
      group.setAttribute('class', 'dep-node-group');

      const title = document.createElementNS(NS, 'title');
      title.textContent = node.id;
      group.appendChild(title);

      const rect = document.createElementNS(NS, 'rect');
      rect.setAttribute('x', String(p.x));
      rect.setAttribute('y', String(p.y));
      rect.setAttribute('width', String(nodeW));
      rect.setAttribute('height', String(nodeH));
      rect.setAttribute('rx', '7');
      rect.setAttribute('fill', colors.fill);
      rect.setAttribute('stroke', colors.stroke);
      rect.setAttribute('stroke-opacity', colors.strokeOpacity || '1');
      rect.setAttribute('stroke-width', '0.8');
      group.appendChild(rect);

      const text = document.createElementNS(NS, 'text');
      text.setAttribute('x', String(p.x + nodeW / 2));
      text.setAttribute('y', String(p.y + nodeH / 2));
      text.setAttribute('fill', '#E2E8F0');
      text.setAttribute('font-size', '11');
      text.setAttribute('font-family', 'JetBrains Mono, monospace');
      text.setAttribute('text-anchor', 'middle');
      text.setAttribute('dominant-baseline', 'central');
      text.textContent = truncateLabel(node.label, 18);
      group.appendChild(text);

      svg.appendChild(group);
    });

    const legendY = height - 40;
    const legend = [
      { name: 'Routes/Entry', color: 'rgba(59,130,246,0.6)' },
      { name: 'State/Plugins', color: 'rgba(168,85,247,0.5)' },
      { name: 'Services', color: 'rgba(168,85,247,0.7)' },
      { name: 'Models', color: 'rgba(239,68,68,0.5)' },
      { name: 'Utils/Config', color: 'rgba(234,179,8,0.5)' }
    ];

    const legendStartX = 80;
    const legendItemWidth = 110;
    legend.forEach((item, i) => {
      const x = legendStartX + i * legendItemWidth;
      const sq = document.createElementNS(NS, 'rect');
      sq.setAttribute('x', String(x));
      sq.setAttribute('y', String(legendY - 10));
      sq.setAttribute('width', '10');
      sq.setAttribute('height', '10');
      sq.setAttribute('rx', '2');
      sq.setAttribute('fill', item.color);
      svg.appendChild(sq);

      createText(svg, x + 14, legendY - 1, '#64748B', 10, 'JetBrains Mono, monospace', item.name);
    });

    container.innerHTML = '';
    container.appendChild(svg);
  } catch (err) {
    container.innerHTML = '<p class="diagram-fallback">No dependency data available</p>';
  }
}

function renderAll(data) {
  hideSkeletons();
  window._lastApiResponse = data;

  const graph = normalizeGraphData(data || {});
  if (!window._lastApiResponse.m3_nodes) window._lastApiResponse.m3_nodes = graph.nodes;
  if (!window._lastApiResponse.m3_edges) window._lastApiResponse.m3_edges = graph.edges;

  renderM1(data?.m1_folder_explanation || {});
  renderM2Preview(data?.m2_entry_analysis || {});
  renderM3Preview(graph.nodes, graph.edges);
}

function renderAllCards() {
  const mockData = {
    m1_folder_explanation: {
      architecture_style: 'Component-Based (Single Page Application)',
      folders: {
        '<root>': 'Contains project-level configs and docs',
        'src/': 'Main application source code',
        'src/components/': 'Reusable UI components',
        'src/services/': 'External API and integration handlers',
        'src/store/': 'Global state management',
        'src/routes/': 'Route definitions and guards'
      }
    },
    m2_entry_analysis: {
      entry_file: 'src/main.js',
      execution_flow: [
        'Step 1: Load runtime environment and polyfills',
        'Step 2: Initialize router and global store',
        'Step 3: Mount root app into DOM',
        'Step 4: Register async services'
      ]
    },
    m3_nodes: [
      { id: 'src/main.js', label: 'main.js', layer: 'route' },
      { id: 'src/store.js', label: 'store.js', layer: 'store' },
      { id: 'src/router.js', label: 'router.js', layer: 'route' },
      { id: 'src/services/openPricesApi.js', label: 'openPricesApi.js', layer: 'service' }
    ],
    m3_edges: [
      { source: 'src/main.js', target: 'src/router.js' },
      { source: 'src/main.js', target: 'src/store.js' },
      { source: 'src/router.js', target: 'src/services/openPricesApi.js' }
    ]
  };

  renderAll(mockData);
}

window.renderAll = renderAll;
window.renderAllCards = renderAllCards;
window.renderM1Full = renderM1Full;
window.renderM2Full = renderM2Full;
window.renderDependencyGraph = renderDependencyGraph;
window.showSkeletons = showSkeletons;
window.hideSkeletons = hideSkeletons;
window.showCardError = showCardError;
