import { useEffect, useMemo, useRef, useState } from "react";
import * as dagre from "dagre";
import type { DrDiagramResponse, DrRelationship, DrTable } from "../services/api";

// ═══════════════════════════════════════════════════════════════════════
// This is a fairly direct port of the DBeaver-style SVG ER/Schema-Overview
// renderer from gen_drdiagram/templates/index.html, adapted to consume
// DrDiagramResponse (real scanned columns + JOIN-derived relationships)
// instead of a Google Sheet, and wrapped as a React component instead of
// vanilla DOM script. The rendering itself stays imperative (building raw
// SVG DOM nodes) since that's what the original does and it's the simplest
// way to get pixel-level control over a DBeaver-style diagram.
// ═══════════════════════════════════════════════════════════════════════

const NS = "http://www.w3.org/2000/svg";
const TW = 262;
const HDR_H = 30;
const COL_H = 22;
const COL_PB = 8;
const OV = { GW: 270, GHDR: 28, CROW: 17, GPAD: 6, GGAPH: 18, GGAPV: 14 };
const TITLE_H = 50;
const LEGEND_H = 40;

const C = {
  diagBg: "#e8ecf4",
  diagGrid: "#d4d9e8",
  titleBg: "#0e1630",
  titleText: "#fff",
  titleSub: "#8098c8",
  accent: "#2b5fa8",
  tblBg: "#fff",
  tblBorder: "#9aaac0",
  hdrBg: "#1e3060",
  viewHdrBg: "#5b3a8f",
  viewAccent: "#8a5fc0",
  rowAlt: "#f3f6ff",
  rowSep: "#e2e8f5",
  colName: "#0a1a38",
  colType: "#6878a0",
  pkClr: "#c87800",
  fkClr: "#2b5fa8",
  relClr: "#2b5fa8",
  relClr2: "#3a78c8",
  relLblBg: "#edf2ff",
  grpBg: "#f0f5ff",
  grpHdr: "#1e3060",
  grpBorder: "#9ab0d0",
  grpRelHdr: "#0e2048",
  rowRel: "#dce9ff",
  rowRelBar: "#2b5fa8",
  legendBg: "#fff",
  legendBorder: "#cdd3e2",
};

type Attrs = Record<string, string | number>;

function el(tag: string, attrs: Attrs = {}): SVGElement {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, String(v));
  return e as unknown as SVGElement;
}
function txt(parent: SVGElement, x: number, y: number, s: string, attrs: Attrs = {}): SVGElement {
  const t = el("text", { x, y, ...attrs });
  t.textContent = s;
  parent.appendChild(t);
  return t;
}
function rct(parent: SVGElement, x: number, y: number, w: number, h: number, attrs: Attrs = {}): SVGElement {
  const r = el("rect", { x, y, width: w, height: h, ...attrs });
  parent.appendChild(r);
  return r;
}
function trunc(s: string, maxPx: number, cw = 7): string {
  const m = Math.max(1, Math.floor(maxPx / cw));
  return s.length > m ? s.slice(0, m - 1) + "…" : s;
}
// Native browser tooltip (hover) with the untruncated text, for labels that
// `trunc()` may have shortened to fit a card's width.
function addTooltip(target: SVGElement, fullText: string): void {
  const title = document.createElementNS(NS, "title");
  title.textContent = fullText;
  target.appendChild(title);
}
// Pick a column count for a shortest-column grid. Simulates the same
// shortest-column bin-packing the caller will actually use, for every
// candidate column count, and keeps whichever scores best on a mix of two
// things: how close the canvas shape lands to `targetRatio` (width:height),
// and how much of that canvas is actually filled with content.
//
// The fill term matters because of one-outlier schemas: if a single table
// is dramatically taller than everything else (e.g. one view with 100+
// columns), that outlier sets a height floor no matter which column it
// lands in, so adding more columns can keep "improving" the ratio (wider,
// same height) long after every other column has run out of real content
// to add -- chasing the ratio alone would keep picking more columns and
// produce a canvas that's mostly dead space beside one tall outlier.
// Penalizing low fill keeps that from winning purely on ratio closeness.
//
// Deliberately does NOT pre-filter to "whichever cols get closest to the
// minimum possible height" first (an earlier version did this, and always
// picked the max column count for many-similar-height boxes regardless of
// target ratio). Searching the full range directly lets a squarer,
// taller-but-narrower packing win when it actually looks more balanced.
function pickLandscapeCols(
  heightsInPackOrder: number[],
  boxW: number,
  gapX: number,
  gapY: number,
  margin: number,
  targetRatio: number
): number {
  const n = heightsInPackOrder.length;
  if (n <= 1) return 1;
  const maxCols = Math.min(40, n);
  const totalContentArea = heightsInPackOrder.reduce((sum, h) => sum + h, 0) * boxW;
  const FILL_PENALTY_WEIGHT = 1.5;

  let best = 1;
  let bestScore = Infinity;
  for (let cols = 1; cols <= maxCols; cols++) {
    const colH = new Array(cols).fill(margin);
    for (const h of heightsInPackOrder) {
      const ci = colH.indexOf(Math.min(...colH));
      colH[ci] += h + gapY;
    }
    const w = cols * boxW + (cols - 1) * gapX + margin * 2;
    const hgt = Math.max(...colH) + margin;
    const ratioDiff = Math.abs(w / hgt - targetRatio) / targetRatio;
    const fillRatio = Math.min(1, totalContentArea / (w * hgt));
    const score = ratioDiff + (1 - fillRatio) * FILL_PENALTY_WEIGHT;
    if (score < bestScore) {
      bestScore = score;
      best = cols;
    }
  }
  return best;
}
function fontA(fam = "Segoe UI,Arial,sans-serif", sz = 11, wt = "400", fill = "#333"): Attrs {
  return { "font-family": fam, "font-size": sz, "font-weight": wt, fill, "dominant-baseline": "middle" };
}
function monoA(sz = 9.5, fill = "#666"): Attrs {
  return {
    "font-family": "Consolas,Courier New,monospace",
    "font-size": sz,
    fill,
    "dominant-baseline": "middle",
  };
}

function buildDefs(svg: SVGElement, n: number): void {
  const d = el("defs");
  const f = el("filter", { id: "ds", x: "-15%", y: "-15%", width: "130%", height: "130%" });
  f.appendChild(el("feDropShadow", { dx: "0", dy: "2", stdDeviation: "3.5", "flood-color": "rgba(0,0,0,.16)" }));
  d.appendChild(f);
  const pat = el("pattern", { id: "grid", width: "28", height: "28", patternUnits: "userSpaceOnUse" });
  pat.appendChild(el("path", { d: "M28 0 L0 0 0 28", fill: "none", stroke: C.diagGrid, "stroke-width": ".6" }));
  d.appendChild(pat);
  const cols = [C.relClr, C.relClr2];
  for (let i = 0; i < Math.max(n, 1); i++) {
    const clr = cols[i % 2];
    // Kept small and tight to the line's exact endpoint -- a marker much
    // taller than a table row makes it ambiguous which row a line actually
    // terminates at.
    const crow = el("marker", {
      id: `crow-${i}`,
      markerWidth: "9",
      markerHeight: "9",
      refX: "0",
      refY: "4.5",
      orient: "auto-start-reverse",
    });
    crow.appendChild(el("line", { x1: "0", y1: "4.5", x2: "8", y2: "0.5", stroke: clr, "stroke-width": "1.2" }));
    crow.appendChild(el("line", { x1: "0", y1: "4.5", x2: "8", y2: "8.5", stroke: clr, "stroke-width": "1.2" }));
    crow.appendChild(el("line", { x1: "8", y1: "0.5", x2: "8", y2: "8.5", stroke: clr, "stroke-width": "1.2" }));
    d.appendChild(crow);
    const one = el("marker", { id: `one-${i}`, markerWidth: "7", markerHeight: "9", refX: "6", refY: "4.5", orient: "auto" });
    one.appendChild(el("line", { x1: "3.5", y1: "0.5", x2: "3.5", y2: "8.5", stroke: clr, "stroke-width": "1.4" }));
    one.appendChild(el("line", { x1: "5.5", y1: "0.5", x2: "5.5", y2: "8.5", stroke: clr, "stroke-width": "1.4" }));
    d.appendChild(one);
    const arr = el("marker", { id: `arr-${i}`, markerWidth: "7", markerHeight: "6", refX: "6", refY: "3", orient: "auto" });
    arr.appendChild(el("path", { d: "M0,0 L0,6 L7,3 z", fill: clr }));
    d.appendChild(arr);
  }
  svg.appendChild(d);
}

function keyIcon(parent: SVGElement, cx: number, cy: number, color: string): void {
  const g = el("g", { transform: `translate(${cx - 7},${cy - 6})` });
  g.appendChild(el("circle", { cx: 4, cy: 4, r: 3.6, fill: color }));
  g.appendChild(el("circle", { cx: 4, cy: 4, r: 1.7, fill: "rgba(255,255,255,.5)" }));
  g.appendChild(el("rect", { x: 7, y: 3.2, width: 7, height: 1.6, rx: 0.8, fill: color }));
  g.appendChild(el("rect", { x: 10.5, y: 4.8, width: 1.4, height: 2.2, rx: 0.4, fill: color }));
  g.appendChild(el("rect", { x: 12.8, y: 4.8, width: 1.4, height: 1.7, rx: 0.4, fill: color }));
  parent.appendChild(g);
}
function miniKey(parent: SVGElement, x: number, y: number, color: string): void {
  const g = el("g", { transform: `translate(${x},${y})` });
  g.appendChild(el("circle", { cx: 2.8, cy: 2.8, r: 2.5, fill: color }));
  g.appendChild(el("circle", { cx: 2.8, cy: 2.8, r: 1.0, fill: "rgba(255,255,255,.4)" }));
  g.appendChild(el("rect", { x: 5.2, y: 2.1, width: 4.8, height: 1.3, rx: 0.6, fill: color }));
  g.appendChild(el("rect", { x: 7.8, y: 3.4, width: 1.1, height: 1.8, rx: 0.3, fill: color }));
  g.appendChild(el("rect", { x: 9.5, y: 3.4, width: 1.1, height: 1.4, rx: 0.3, fill: color }));
  parent.appendChild(g);
}

function drawTitle(svg: SVGElement, data: DrDiagramResponse, W: number, subtitle?: string): void {
  const g = el("g");
  rct(g, 0, 0, W, TITLE_H, { fill: C.titleBg });
  rct(g, 0, TITLE_H - 3, W, 3, { fill: C.accent });
  txt(g, 18, 26, `DR Diagram : ${data.database}`, { ...fontA("Segoe UI,Arial", 17, "700", C.titleText) });
  txt(
    g,
    18,
    41,
    subtitle || `${data.table_count} tables · ${data.view_count} views · ${data.relationship_count} relationships`,
    { ...fontA("Segoe UI,Arial", 10.5, "400", C.titleSub) }
  );
  const d = new Date().toLocaleDateString("th-TH", { year: "numeric", month: "long", day: "numeric" });
  txt(g, W - 16, 33, d, { ...fontA("Segoe UI,Arial", 10, "400", C.titleSub), "text-anchor": "end" });
  svg.appendChild(g);
}

function drawLegend(svg: SVGElement, W: number, svgH: number, mode: "er" | "ov"): SVGElement {
  const g = el("g", { transform: `translate(0,${svgH - LEGEND_H})` });
  rct(g, 0, 0, W, LEGEND_H, { fill: C.legendBg, stroke: C.legendBorder, "stroke-width": "1" });
  let lx = 18;
  if (mode === "er") {
    keyIcon(g, lx + 7, LEGEND_H / 2, C.pkClr);
    txt(g, lx + 20, LEGEND_H / 2, "Primary Key (PK)", { ...fontA("Segoe UI,Arial", 10.5, "400", "#2d3c5a") });
    lx += 130;
    keyIcon(g, lx + 7, LEGEND_H / 2, C.fkClr);
    txt(g, lx + 20, LEGEND_H / 2, "Foreign Key / Join", { ...fontA("Segoe UI,Arial", 10.5, "400", "#2d3c5a") });
    lx += 145;
    g.appendChild(
      el("line", {
        x1: lx,
        y1: LEGEND_H / 2,
        x2: lx + 46,
        y2: LEGEND_H / 2,
        stroke: C.relClr,
        "stroke-width": "1.5",
        "marker-start": "url(#crow-0)",
        "marker-end": "url(#one-0)",
      })
    );
    txt(g, lx + 56, LEGEND_H / 2, "JOIN relationship (many → one)", {
      ...fontA("Segoe UI,Arial", 10.5, "400", "#2d3c5a"),
    });
    lx += 260;
    g.appendChild(
      el("line", {
        x1: lx,
        y1: LEGEND_H / 2,
        x2: lx + 36,
        y2: LEGEND_H / 2,
        stroke: C.relClr,
        "stroke-width": "1.5",
        "stroke-dasharray": "6,4",
        "marker-end": "url(#arr-0)",
      })
    );
    txt(g, lx + 46, LEGEND_H / 2, "View reads from (source)", { ...fontA("Segoe UI,Arial", 10.5, "400", "#2d3c5a") });
  } else {
    rct(g, lx, LEGEND_H / 2 - 9, 16, 18, { rx: 3, fill: C.grpHdr });
    txt(g, lx + 22, LEGEND_H / 2, "Table", { ...fontA("Segoe UI,Arial", 10.5, "400", "#2d3c5a") });
    lx += 90;
    rct(g, lx, LEGEND_H / 2 - 9, 16, 18, { rx: 3, fill: C.viewHdrBg });
    txt(g, lx + 22, LEGEND_H / 2, "View", { ...fontA("Segoe UI,Arial", 10.5, "400", "#2d3c5a") });
    lx += 90;
    keyIcon(g, lx + 7, LEGEND_H / 2, C.pkClr);
    txt(g, lx + 20, LEGEND_H / 2, "PK", { ...fontA("Segoe UI,Arial", 10.5, "400", "#2d3c5a") });
    lx += 42;
    keyIcon(g, lx + 7, LEGEND_H / 2, C.fkClr);
    txt(g, lx + 20, LEGEND_H / 2, "FK/Join", { ...fontA("Segoe UI,Arial", 10.5, "400", "#2d3c5a") });
    lx += 85;
    rct(g, lx, LEGEND_H / 2 - 9, 60, 18, { rx: 4, fill: "#e8effd", stroke: "#7a9fd8", "stroke-width": 1.2 });
    txt(g, lx + 72, LEGEND_H / 2, "Table with JOIN", { ...fontA("Segoe UI,Arial", 10.5, "400", "#2d3c5a") });
    lx += 200;
    g.appendChild(
      el("line", {
        x1: lx,
        y1: LEGEND_H / 2,
        x2: lx + 36,
        y2: LEGEND_H / 2,
        stroke: C.relClr,
        "stroke-width": "1.5",
        "marker-end": "url(#arr-0)",
      })
    );
    txt(g, lx + 46, LEGEND_H / 2, "JOIN relationship", { ...fontA("Segoe UI,Arial", 10.5, "400", "#2d3c5a") });
    lx += 190;
    g.appendChild(
      el("line", {
        x1: lx,
        y1: LEGEND_H / 2,
        x2: lx + 36,
        y2: LEGEND_H / 2,
        stroke: C.relClr,
        "stroke-width": "1.5",
        "stroke-dasharray": "6,4",
        "marker-end": "url(#arr-0)",
      })
    );
    txt(g, lx + 46, LEGEND_H / 2, "View reads from (source)", { ...fontA("Segoe UI,Arial", 10.5, "400", "#2d3c5a") });
  }
  svg.appendChild(g);
  return g;
}

// ─── ER diagram mode ───────────────────────────────────────────────────

type ColMode = "all" | "key" | "none";

function getVisibleCols(ti: DrTable, fkSet: Set<string>, colMode: ColMode) {
  if (colMode === "none") return [];
  if (colMode === "key") return ti.columns.filter((c) => c.is_key || fkSet.has(c.name.toLowerCase()));
  return ti.columns;
}

interface NodeInfo {
  x: number;
  y: number;
  w: number;
  h: number;
  cols: DrTable["columns"];
  el?: SVGElement;
}

function drawERTable(
  parent: SVGElement,
  tn: string,
  ti: DrTable,
  tx: number,
  ty: number,
  fkSet: Set<string>,
  joinColSet: Set<string>,
  colMode: ColMode,
  showType: boolean
): NodeInfo {
  const cols = getVisibleCols(ti, fkSet, colMode);
  const isView = ti.object_type === "VIEW";
  const w = TW;
  const h = HDR_H + cols.length * COL_H + (cols.length > 0 ? COL_PB : 4);
  const g = el("g", { transform: `translate(${tx},${ty})` });
  rct(g, 3, 4, w, h, { rx: 5, fill: "rgba(0,0,0,.13)" });
  rct(g, 0, 0, w, h, { rx: 5, fill: C.tblBg, stroke: C.tblBorder, "stroke-width": 1.4 });
  g.appendChild(
    el("path", { d: `M5,0 H${w - 5} Q${w},0 ${w},5 V${HDR_H} H0 V5 Q0,0 5,0`, fill: isView ? C.viewHdrBg : C.hdrBg })
  );
  rct(g, 0, HDR_H - 2.5, w, 2.5, { fill: isView ? C.viewAccent : C.accent });
  const gi = el("g", { transform: `translate(9,${HDR_H / 2 - 5})`, opacity: 0.65 });
  rct(gi, 0, 0, 13, 10, { rx: 2, fill: "rgba(255,255,255,.18)", stroke: "rgba(255,255,255,.5)", "stroke-width": 1 });
  gi.appendChild(el("line", { x1: 0, y1: 3.5, x2: 13, y2: 3.5, stroke: "rgba(255,255,255,.4)", "stroke-width": 0.8 }));
  gi.appendChild(el("line", { x1: 4.5, y1: 0, x2: 4.5, y2: 10, stroke: "rgba(255,255,255,.3)", "stroke-width": 0.8 }));
  g.appendChild(gi);

  const badge = String(ti.columns.length);
  const bw = badge.length * 7 + 10;
  let badgeLeft = w - bw - 6;
  rct(g, badgeLeft, HDR_H / 2 - 9, bw, 18, { rx: 9, fill: "rgba(255,255,255,.15)" });
  txt(g, badgeLeft + bw / 2, HDR_H / 2 + 1, badge, { ...fontA("Arial", 9, "700", "#fff"), "text-anchor": "middle" });

  if (isView) {
    const vb = "VIEW";
    const vbw = vb.length * 7 + 10;
    badgeLeft -= vbw + 5;
    rct(g, badgeLeft, HDR_H / 2 - 9, vbw, 18, { rx: 9, fill: "rgba(255,255,255,.28)" });
    txt(g, badgeLeft + vbw / 2, HDR_H / 2 + 1, vb, { ...fontA("Arial", 8, "700", "#fff"), "text-anchor": "middle" });
  }

  const nameEl = txt(g, 27, HDR_H / 2 + 1, trunc(tn, badgeLeft - 27 - 6, 7), { ...fontA("Segoe UI,Arial", 12, "700", "#fff") });
  addTooltip(nameEl, tn);

  cols.forEach((col, i) => {
    const ry = HDR_H + i * COL_H;
    const mid = ry + COL_H / 2;
    const isPK = col.is_key;
    const isFK = fkSet.has(col.name.toLowerCase());
    const isJ = joinColSet.has(`${tn}.${col.name.toLowerCase()}`);
    if (isJ) rct(g, 1.4, ry, 4, i === cols.length - 1 ? COL_H - 3 : COL_H, { fill: C.accent });
    if (i % 2 === 1) {
      if (i === cols.length - 1) {
        g.appendChild(
          el("path", {
            d: `M1.4,${ry} H${w - 1.4} V${ry + COL_H - 4} Q${w - 1.4},${ry + COL_H - 1.4} ${w - 5},${ry + COL_H - 1.4} H5 Q1.4,${ry + COL_H - 1.4} 1.4,${ry + COL_H - 4} Z`,
            fill: C.rowAlt,
          })
        );
      } else {
        rct(g, 1.4, ry, w - 2.8, COL_H, { fill: C.rowAlt });
      }
    }
    if (i > 0) g.appendChild(el("line", { x1: 8, y1: ry, x2: w - 8, y2: ry, stroke: C.rowSep, "stroke-width": 0.8 }));
    let nx = isJ ? 14 : 9;
    if (isPK) {
      keyIcon(g, nx + 8, mid, C.pkClr);
      nx += 20;
    } else if (isFK) {
      keyIcon(g, nx + 8, mid, C.fkClr);
      nx += 20;
    }
    const colNameEl = txt(g, nx, mid + 1, trunc(col.name, w - nx - (showType ? 65 : 14), 6.8), {
      ...fontA("Segoe UI,Arial", 10.5, isPK ? "700" : "400", C.colName),
    });
    addTooltip(colNameEl, col.name);
    if (showType) {
      const bt = (col.type || "").split(/[\s(<]/)[0].toUpperCase().slice(0, 12);
      txt(g, w - 8, mid + 1, bt, { ...monoA(9, C.colType), "text-anchor": "end" });
    }
  });
  parent.appendChild(g);
  return { x: tx, y: ty, w, h, cols, el: g };
}

function colAbsY(ni: NodeInfo, colName: string): number {
  const idx = ni.cols.findIndex((c) => c.name.toLowerCase() === colName.toLowerCase());
  return ni.y + HDR_H + (idx < 0 ? Math.floor(ni.cols.length / 2) : idx) * COL_H + COL_H / 2;
}

function drawERLine(parent: SVGElement, fi: NodeInfo, ti2: NodeInfo, rel: DrRelationship, idx: number): void {
  const isViewSrc = rel.relationship_type === "VIEW_SOURCE";
  const fy = colAbsY(fi, rel.from_col);
  const ty2 = colAbsY(ti2, rel.to_col);
  let fx: number, tx: number;
  if (fi.x + fi.w / 2 < ti2.x + ti2.w / 2) {
    fx = fi.x + fi.w;
    tx = ti2.x;
  } else {
    fx = fi.x;
    tx = ti2.x + ti2.w;
  }
  const gap = Math.min(Math.abs(tx - fx) * 0.45 + 30, 120);
  const dx = fx < tx ? gap : -gap;
  const d = `M${fx},${fy} C${fx + dx},${fy} ${tx - dx},${ty2} ${tx},${ty2}`;
  const clr = idx % 2 === 0 ? C.relClr : C.relClr2;
  parent.appendChild(
    el("path", {
      d,
      stroke: clr,
      "stroke-width": "2.2",
      fill: "none",
      opacity: ".88",
      ...(isViewSrc
        ? { "stroke-dasharray": "6,4", "marker-end": `url(#arr-${idx})` }
        : { "marker-start": `url(#crow-${idx})`, "marker-end": `url(#one-${idx})` }),
    })
  );
  if (isViewSrc) return;
  const mx = (fx + tx) / 2;
  const my = (fy + ty2) / 2;
  const ls = `${rel.from_col} = ${rel.to_col}`.slice(0, 24);
  const lw = ls.length * 5.4 + 14;
  rct(parent, mx - lw / 2, my - 9, lw, 18, { rx: 4, fill: C.relLblBg, stroke: clr, "stroke-width": ".9", opacity: ".94" });
  txt(parent, mx, my + 1, ls, { ...monoA(8.5, clr), "text-anchor": "middle" });
}

interface ERViewOptions {
  colMode: ColMode;
  showType: boolean;
  relOnly: boolean;
  rankdir: "LR" | "TB";
  // Manual per-table position overrides (keyed by table name), mutated live
  // as the user drags a table card, and re-applied on every re-render so
  // dragged positions survive toggling unrelated options (colMode, showType,
  // ...). Reset by the caller when `data` itself changes.
  overrides?: Record<string, { x: number; y: number }>;
  // Current pan/zoom scale of the enclosing viewport, used to convert screen
  // pixel drag deltas into SVG user-space deltas.
  getScale?: () => number;
  bgColor?: string;
  // Target width:height ratio for the auto-packed (no-relationship) layout
  // and for padding a too-tall canvas back out to a reasonable shape.
  // Defaults to 1.5 (3:2) when omitted.
  aspectRatio?: number;
}

function renderER(data: DrDiagramResponse, opts: ERViewOptions): SVGElement {
  const relatedSet = new Set<string>();
  const fkPerTable: Record<string, Set<string>> = {};
  const joinColSet = new Set<string>();
  data.relationships.forEach((r) => {
    relatedSet.add(r.from_table);
    relatedSet.add(r.to_table);
    [r.from_table, r.to_table].forEach((t) => {
      if (!fkPerTable[t]) fkPerTable[t] = new Set();
    });
    fkPerTable[r.from_table].add(r.from_col.toLowerCase());
    fkPerTable[r.to_table].add(r.to_col.toLowerCase());
    joinColSet.add(`${r.from_table}.${r.from_col.toLowerCase()}`);
    joinColSet.add(`${r.to_table}.${r.to_col.toLowerCase()}`);
  });

  let tables = data.tables;
  if (opts.relOnly) {
    tables = Object.fromEntries(Object.entries(data.tables).filter(([k]) => relatedSet.has(k)));
  }
  const rels = data.relationships.filter((r) => r.from_table in tables && r.to_table in tables);
  const tableEntries = Object.entries(tables);

  const nodeMeta: Record<string, { w: number; h: number; cols: DrTable["columns"] }> = {};
  for (const [tn, ti] of tableEntries) {
    const fk = fkPerTable[tn] || new Set<string>();
    const cols = getVisibleCols(ti, fk, opts.colMode);
    nodeMeta[tn] = { w: TW, h: HDR_H + cols.length * COL_H + (cols.length > 0 ? COL_PB : 4), cols };
  }

  const layoutPos: Record<string, { x: number; y: number }> = {};
  let diagW: number;
  let diagH: number;

  if (rels.length > 0) {
    const G = new dagre.graphlib.Graph();
    G.setGraph({ rankdir: opts.rankdir, nodesep: 65, ranksep: 110, marginx: 90, marginy: 90, acyclicer: "greedy", ranker: "network-simplex" });
    G.setDefaultEdgeLabel(() => ({}));
    for (const [tn, meta] of Object.entries(nodeMeta)) {
      G.setNode(tn, { width: meta.w, height: meta.h });
    }
    const se = new Set<string>();
    rels.forEach((r) => {
      const k = `${r.from_table}→${r.to_table}`;
      if (!se.has(k)) {
        se.add(k);
        G.setEdge(r.from_table, r.to_table);
      }
    });
    dagre.layout(G);
    const gi = G.graph();
    diagW = (gi.width || 400) + 60;
    diagH = (gi.height || 300) + 60;
    for (const tn of Object.keys(tables)) {
      const nd = G.node(tn);
      if (!nd) continue;
      layoutPos[tn] = { x: nd.x - nd.width / 2, y: nd.y - nd.height / 2 };
    }
  } else {
    // dagre degenerates when there are no edges at all: every node lands in
    // the same rank (same x for rankdir LR), stacking all tables on top of
    // one another. Pack them into a simple shortest-column grid instead.
    const GAP_X = 40;
    const GAP_Y = 40;
    const MARGIN = 70;
    // Largest-first packing order gives a far more even column balance than
    // insertion order -- one huge outlier table packed early into whichever
    // column happens to be shortest at that moment can otherwise dominate
    // and tower over every other column regardless of how many columns exist.
    const orderedEntries = [...tableEntries].sort(([a], [b]) => nodeMeta[b].h - nodeMeta[a].h);
    const perRow = Math.max(
      1,
      Math.min(
        24,
        pickLandscapeCols(orderedEntries.map(([tn]) => nodeMeta[tn].h), TW, GAP_X, GAP_Y, MARGIN, opts.aspectRatio ?? 1.5)
      )
    );
    const colX = Array.from({ length: perRow }, (_, c) => MARGIN + c * (TW + GAP_X));
    const colH = new Array(perRow).fill(MARGIN);
    orderedEntries.forEach(([tn]) => {
      const ci = colH.indexOf(Math.min(...colH));
      layoutPos[tn] = { x: colX[ci], y: colH[ci] };
      colH[ci] += nodeMeta[tn].h + GAP_Y;
    });
    diagW = perRow * TW + (perRow - 1) * GAP_X + MARGIN * 2;
    diagH = Math.max(...colH) + MARGIN;
  }

  const nodeInfo: Record<string, NodeInfo> = {};
  for (const tn of Object.keys(tables)) {
    const pos = layoutPos[tn];
    if (!pos) continue;
    const meta = nodeMeta[tn];
    const override = opts.overrides?.[tn];
    nodeInfo[tn] = { x: override?.x ?? pos.x, y: override?.y ?? pos.y, w: meta.w, h: meta.h, cols: meta.cols };
  }

  // Manually-dragged tables can land outside the auto-computed bounds -
  // grow the canvas (never shrink it) to keep them fully visible.
  for (const ni of Object.values(nodeInfo)) {
    diagW = Math.max(diagW, ni.x + ni.w + 60);
    diagH = Math.max(diagH, ni.y + ni.h + 60);
  }

  // The exported/rendered canvas should read as a landscape image even when
  // the tables themselves pack into a shape that's taller than it is wide
  // (e.g. one very tall table next to a short one, with no room to balance
  // that out across more columns) - pad extra background on the sides and
  // center the content instead of shipping a portrait-cropped export.
  const LANDSCAPE_RATIO = opts.aspectRatio ?? 1.5;
  let canvasW = diagW;
  if (diagW < diagH) canvasW = Math.ceil(diagH * LANDSCAPE_RATIO);
  let xOffset = (canvasW - diagW) / 2;

  const svgW = canvasW;
  const svgH = TITLE_H + diagH + LEGEND_H;
  const svg = el("svg", { xmlns: NS, width: svgW, height: svgH, viewBox: `0 0 ${svgW} ${svgH}`, style: "background:white" });
  buildDefs(svg, rels.length);
  drawTitle(svg, data, svgW);
  const dg = el("g", { transform: `translate(${xOffset},${TITLE_H})` });
  const bgRect = rct(dg, -xOffset, 0, canvasW, diagH, { fill: opts.bgColor || C.diagBg });

  // Dragging a table past the current canvas edge would otherwise clip it
  // out of view (content outside an <svg>'s viewBox isn't rendered) - grow
  // the SVG, backdrop, and legend position live so the background always
  // extends to cover wherever a table gets dragged.
  let legendG: SVGElement | null = null;
  function growCanvasTo(neededW: number, neededH: number) {
    if (neededW <= diagW && neededH <= diagH) return;
    diagW = Math.max(diagW, neededW);
    diagH = Math.max(diagH, neededH);
    canvasW = diagW < diagH ? Math.ceil(diagH * LANDSCAPE_RATIO) : diagW;
    xOffset = (canvasW - diagW) / 2;
    const newSvgH = TITLE_H + diagH + LEGEND_H;
    svg.setAttribute("width", String(canvasW));
    svg.setAttribute("height", String(newSvgH));
    svg.setAttribute("viewBox", `0 0 ${canvasW} ${newSvgH}`);
    dg.setAttribute("transform", `translate(${xOffset},${TITLE_H})`);
    bgRect.setAttribute("x", String(-xOffset));
    bgRect.setAttribute("width", String(canvasW));
    bgRect.setAttribute("height", String(diagH));
    legendG?.setAttribute("transform", `translate(0,${newSvgH - LEGEND_H})`);
    legendG?.firstElementChild?.setAttribute("width", String(canvasW));
  }

  const relG = el("g", { id: "rels" });
  const dr: (DrRelationship & { idx: number })[] = [];
  const sp = new Set<string>();
  rels.forEach((r, i) => {
    const pk = [r.from_table, r.from_col, r.to_table, r.to_col].join("|");
    if (!sp.has(pk)) {
      sp.add(pk);
      dr.push({ ...r, idx: i });
    }
  });
  function redrawRelationships() {
    while (relG.firstChild) relG.removeChild(relG.firstChild);
    dr.forEach((r) => {
      const fi = nodeInfo[r.from_table];
      const ti2 = nodeInfo[r.to_table];
      if (!fi || !ti2) return;
      // Dimmed by default and wrapped per-relationship so hovering a table
      // can highlight just its own lines -- with 100+ tables, every line
      // drawn at full opacity all the time turns into unreadable spaghetti.
      const wrap = el("g", { "data-from": r.from_table, "data-to": r.to_table, opacity: "0.7" });
      drawERLine(wrap, fi, ti2, r, r.idx);
      relG.appendChild(wrap);
    });
  }
  redrawRelationships();
  dg.appendChild(relG);

  function setRelHighlight(activeTn: string | null) {
    Array.from(relG.children).forEach((g) => {
      const from = g.getAttribute("data-from");
      const to = g.getAttribute("data-to");
      if (!activeTn) (g as SVGElement).setAttribute("opacity", "0.7");
      else if (from === activeTn || to === activeTn) (g as SVGElement).setAttribute("opacity", "1");
      else (g as SVGElement).setAttribute("opacity", "0.06");
    });
  }

  function attachDrag(tn: string, ni: NodeInfo) {
    const handle = ni.el;
    if (!handle) return;
    handle.style.cursor = "grab";
    handle.addEventListener("mouseenter", () => setRelHighlight(tn));
    handle.addEventListener("mouseleave", () => setRelHighlight(null));
    handle.addEventListener("pointerdown", (e: PointerEvent) => {
      if (e.button !== 0) return;
      e.stopPropagation();
      e.preventDefault();
      handle.setPointerCapture(e.pointerId);
      handle.style.cursor = "grabbing";
      const startX = e.clientX;
      const startY = e.clientY;
      const origX = ni.x;
      const origY = ni.y;
      const scale = opts.getScale ? opts.getScale() || 1 : 1;

      const onMove = (ev: PointerEvent) => {
        const nx = Math.max(0, origX + (ev.clientX - startX) / scale);
        const ny = Math.max(0, origY + (ev.clientY - startY) / scale);
        ni.x = nx;
        ni.y = ny;
        growCanvasTo(nx + ni.w + 60, ny + ni.h + 60);
        handle.setAttribute("transform", `translate(${nx},${ny})`);
        if (opts.overrides) opts.overrides[tn] = { x: nx, y: ny };
        redrawRelationships();
      };
      const onUp = (ev: PointerEvent) => {
        handle.releasePointerCapture(ev.pointerId);
        handle.style.cursor = "grab";
        handle.removeEventListener("pointermove", onMove);
        handle.removeEventListener("pointerup", onUp);
      };
      handle.addEventListener("pointermove", onMove);
      handle.addEventListener("pointerup", onUp, { once: true });
    });
  }

  const tg = el("g", { filter: "url(#ds)" });
  for (const [tn, ti] of Object.entries(tables)) {
    const ni = nodeInfo[tn];
    if (!ni) continue;
    const info = drawERTable(tg, tn, ti, ni.x, ni.y, fkPerTable[tn] || new Set<string>(), joinColSet, opts.colMode, opts.showType);
    ni.el = info.el;
    attachDrag(tn, ni);
  }
  dg.appendChild(tg);
  svg.appendChild(dg);
  legendG = drawLegend(svg, svgW, svgH, "er");
  return svg;
}

// ─── Schema overview mode ──────────────────────────────────────────────

function getOvCols(ti: DrTable, fkSet: Set<string>, colMode: ColMode) {
  if (colMode === "none") return [];
  if (colMode === "key") return ti.columns.filter((c) => c.is_key || fkSet.has(c.name.toLowerCase()));
  return ti.columns;
}

function computeGroupH(
  tableNames: string[],
  data: DrDiagramResponse,
  fkPerTable: Record<string, Set<string>>,
  colMode: ColMode
): number {
  // One table per box (no more prefix-based grouping) - the box header IS
  // the table's own name, so there's no separate "table name row" to add
  // height for the way a multi-table group used to need.
  const { GHDR, CROW, GPAD } = OV;
  let h = GHDR + GPAD * 2;
  tableNames.forEach((tn) => {
    const ti = data.tables[tn];
    if (!ti) return;
    const fkSet = fkPerTable[tn] || new Set<string>();
    h += getOvCols(ti, fkSet, colMode).length * CROW;
  });
  return h;
}

interface OverviewOptions {
  colMode: ColMode;
  showType: boolean;
  // Number of grid columns, or -1 to auto-pick a column count that makes
  // the overall canvas landscape (wider than tall) rather than a single
  // very tall column of boxes.
  ovCols: number;
  // Manual per-group drag offsets (keyed by group prefix), as a delta from
  // the group's auto-computed position -- mirrors ERViewOptions.overrides
  // but at group granularity, since Schema Overview positions whole
  // prefix-groups rather than individual tables.
  overrides?: Record<string, { dx: number; dy: number }>;
  getScale?: () => number;
  bgColor?: string;
  // Target width:height ratio for the auto column-count pick ("Auto"
  // Columns per row) and for padding a too-tall canvas back out to a
  // reasonable shape. Defaults to 1.5 (3:2) when omitted.
  aspectRatio?: number;
}

function renderOverview(data: DrDiagramResponse, opts: OverviewOptions): SVGElement {
  const { GW, GHDR, CROW, GPAD, GGAPH, GGAPV } = OV;
  const MARGIN = 90;

  const relatedSet = new Set<string>();
  const fkPerTable: Record<string, Set<string>> = {};
  data.relationships.forEach((r) => {
    relatedSet.add(r.from_table);
    relatedSet.add(r.to_table);
    if (!fkPerTable[r.from_table]) fkPerTable[r.from_table] = new Set();
    if (!fkPerTable[r.to_table]) fkPerTable[r.to_table] = new Set();
    fkPerTable[r.from_table].add(r.from_col.toLowerCase());
    fkPerTable[r.to_table].add(r.to_col.toLowerCase());
  });

  // One box per table - tables are no longer bucketed by name prefix. That
  // grouping read as an arbitrary/confusing categorization (and its header
  // was easy to mistake for a truncated table name); every table now gets
  // its own independently positioned box within the database, full stop.
  const groups: Record<string, string[]> = {};
  for (const tn of Object.keys(data.tables).sort()) {
    groups[tn] = [tn];
  }

  const heightByPre: Record<string, number> = {};
  for (const [pre, tableNames] of Object.entries(groups)) {
    heightByPre[pre] = computeGroupH(tableNames, data, fkPerTable, opts.colMode);
  }

  // Cluster tables connected by a relationship (JOIN or VIEW_SOURCE) into the
  // same column, stacked one after another, instead of packing every table
  // independently by height alone - otherwise two related tables can land
  // in far-apart columns purely because of how the bin-packing happened to
  // balance heights, forcing long lines across the whole canvas.
  const adjacency: Record<string, Set<string>> = {};
  for (const tn of Object.keys(groups)) adjacency[tn] = new Set();
  data.relationships.forEach((r) => {
    if (adjacency[r.from_table] && adjacency[r.to_table]) {
      adjacency[r.from_table].add(r.to_table);
      adjacency[r.to_table].add(r.from_table);
    }
  });
  const visited = new Set<string>();
  const components: string[][] = [];
  for (const tn of Object.keys(groups)) {
    if (visited.has(tn)) continue;
    const comp: string[] = [];
    const queue = [tn];
    visited.add(tn);
    while (queue.length) {
      const cur = queue.shift()!;
      comp.push(cur);
      for (const nb of adjacency[cur]) {
        if (!visited.has(nb)) {
          visited.add(nb);
          queue.push(nb);
        }
      }
    }
    comp.sort((a, b) => heightByPre[b] - heightByPre[a]);
    components.push(comp);
  }

  // Related components sort first (visual priority), but within that,
  // tallest-total first -- largest-first packing gives a far more even
  // column balance than alphabetical order, where one huge outlier can
  // otherwise dominate and tower over every other column regardless of
  // column count.
  const compHeight = (comp: string[]) => comp.reduce((s, tn) => s + heightByPre[tn] + GGAPV, 0);
  const sortedComps = [...components].sort((a, b) => {
    const aR = a.some((t) => relatedSet.has(t));
    const bR = b.some((t) => relatedSet.has(t));
    if (aR && !bR) return -1;
    if (!aR && bR) return 1;
    return compHeight(b) - compHeight(a);
  });

  // NCOLS is estimated (and the columns below are packed) per individual
  // table, not per whole connected component -- a schema-wide web of
  // relationships can pull nearly every table into one giant component, and
  // sizing/packing by component would then dump that entire component into
  // a single column regardless of column count, towering over everything
  // else while the rest of the grid sits mostly empty.
  let orderedTables = sortedComps.flat();

  // A table dramatically taller than the rest (e.g. one view with 100+
  // columns) sets a height floor for whichever column it lands in no
  // matter what -- but shortest-column packing has no say over WHICH
  // column that ends up being, so it can land in the middle of the grid,
  // sandwiched between shorter columns on both sides and reading as an
  // arbitrary spike. Packing it first guarantees it seeds column 0 (ties in
  // the shortest-column pick favor the lowest index), so it always ends up
  // flush against the left edge instead of stranded in the middle.
  {
    const heights = Object.values(heightByPre);
    const sortedHeights = [...heights].sort((a, b) => a - b);
    const medianHeight = sortedHeights[Math.floor(sortedHeights.length / 2)] || 0;
    const isOutlier = (tn: string) => medianHeight > 0 && heightByPre[tn] > medianHeight * 2.2;
    const outliers = orderedTables.filter(isOutlier);
    if (outliers.length > 0) {
      orderedTables = [...outliers, ...orderedTables.filter((tn) => !isOutlier(tn))];
    }
  }

  const NCOLS =
    opts.ovCols === -1
      ? Math.max(1, pickLandscapeCols(orderedTables.map((tn) => heightByPre[tn]), GW, GGAPH, GGAPV, MARGIN, opts.aspectRatio ?? 1.5))
      : opts.ovCols || 4;

  // Masonry columns: each component goes into whichever column is currently
  // shortest, and every column packs continuously (no forced row alignment
  // across columns) -- a row-flow grid forces every box in a row to start
  // at the same y, which leaves a large dead gap under any short box that
  // shares a row with a much taller one. Masonry can end up with columns of
  // different final heights, but never a gap in the *middle* of the canvas,
  // only trailing empty space at the bottom of whichever columns run out of
  // content first.
  interface GroupBox {
    pre: string;
    tableNames: string[];
    gx: number;
    gy: number;
    gh: number;
    ci: number;
  }
  const groupBoxes: GroupBox[] = [];
  const colX = Array.from({ length: NCOLS }, (_, c) => MARGIN + c * (GW + GGAPH));
  const colH = new Array(NCOLS).fill(0);
  for (const tn of orderedTables) {
    const ci = colH.indexOf(Math.min(...colH));
    groupBoxes.push({ pre: tn, tableNames: [tn], gx: colX[ci], gy: MARGIN + colH[ci], gh: heightByPre[tn], ci });
    colH[ci] += heightByPre[tn] + GGAPV;
  }
  const maxH = Math.max(...colH);

  let diagW = NCOLS * GW + (NCOLS - 1) * GGAPH + MARGIN * 2;
  let diagH = maxH + MARGIN * 2;
  // Manually-dragged groups can land outside the auto-computed bounds - grow
  // the canvas (never shrink it) to keep them fully visible.
  for (const gb of groupBoxes) {
    const d = opts.overrides?.[gb.pre];
    if (!d) continue;
    diagW = Math.max(diagW, gb.gx + d.dx + GW + 60);
    diagH = Math.max(diagH, gb.gy + d.dy + gb.gh + 60);
  }
  // The exported/rendered canvas should read as a landscape image even when
  // the groups themselves pack into a shape that's taller than it is wide -
  // pad extra background on the sides and center the content instead of
  // shipping a portrait-cropped export.
  const LANDSCAPE_RATIO = opts.aspectRatio ?? 1.5;
  let canvasW = diagW;
  if (diagW < diagH) canvasW = Math.ceil(diagH * LANDSCAPE_RATIO);
  let xOffset = (canvasW - diagW) / 2;

  const svgW = canvasW;
  const svgH = TITLE_H + diagH + LEGEND_H;

  const svg = el("svg", { xmlns: NS, width: svgW, height: svgH, viewBox: `0 0 ${svgW} ${svgH}`, style: "background:white" });
  buildDefs(svg, data.relationships.length);
  drawTitle(svg, data, svgW, `Schema Overview · ${data.table_count} tables · ${data.relationship_count} JOIN relationships`);

  const dg = el("g", { transform: `translate(${xOffset},${TITLE_H})` });
  const bgRect = rct(dg, -xOffset, 0, canvasW, diagH, { fill: opts.bgColor || "#f0f3fa" });

  // Dragging a group past the current canvas edge would otherwise clip it
  // out of view (content outside an <svg>'s viewBox isn't rendered) - grow
  // the SVG, backdrop, and legend position live so the background always
  // extends to cover wherever a group gets dragged.
  let legendG: SVGElement | null = null;
  function growCanvasTo(neededW: number, neededH: number) {
    if (neededW <= diagW && neededH <= diagH) return;
    diagW = Math.max(diagW, neededW);
    diagH = Math.max(diagH, neededH);
    canvasW = diagW < diagH ? Math.ceil(diagH * LANDSCAPE_RATIO) : diagW;
    xOffset = (canvasW - diagW) / 2;
    const newSvgH = TITLE_H + diagH + LEGEND_H;
    svg.setAttribute("width", String(canvasW));
    svg.setAttribute("height", String(newSvgH));
    svg.setAttribute("viewBox", `0 0 ${canvasW} ${newSvgH}`);
    dg.setAttribute("transform", `translate(${xOffset},${TITLE_H})`);
    bgRect.setAttribute("x", String(-xOffset));
    bgRect.setAttribute("width", String(canvasW));
    bgRect.setAttribute("height", String(diagH));
    legendG?.setAttribute("transform", `translate(0,${newSvgH - LEGEND_H})`);
    legendG?.firstElementChild?.setAttribute("width", String(canvasW));
  }

  const tablePos: Record<
    string,
    { ax: number; ay: number; right: number; left: number; top: number; bottom: number; ci: number; pre: string }
  > = {};
  // The columns actually drawn in each table's box (post colMode filtering),
  // in row order -- used so a relationship line can point at the exact row
  // of its real from_col/to_col instead of always the box's vertical
  // center, which made it impossible to tell which column a line meant.
  const colListByTn: Record<string, DrTable["columns"]> = {};
  const grpG = el("g", { id: "groups", filter: "url(#ds)" });
  const groupDelta: Record<string, { dx: number; dy: number }> = {};
  for (const pre of Object.keys(opts.overrides || {})) {
    groupDelta[pre] = { ...opts.overrides![pre] };
  }

  for (const { pre, tableNames, gx, gy, gh, ci } of groupBoxes) {
    // Each box is exactly one table (see the `groups` comment above) - the
    // header IS that table's own name, so there's no separate group/table
    // name row below it the way a multi-table prefix-group used to need.
    const tn = tableNames[0];
    const tdata = data.tables[tn];
    const isRel = relatedSet.has(tn);
    const isView = tdata?.object_type === "VIEW";

    // Everything below is still drawn at the group's absolute (gx,gy)
    // position, exactly as before dragging existed -- the wrapper's own
    // translate(dx,dy) is what actually moves the whole group when dragged,
    // so none of that math needs to change.
    const gGroup = el("g", {});
    const initD = groupDelta[pre] || { dx: 0, dy: 0 };
    gGroup.setAttribute("transform", `translate(${initD.dx},${initD.dy})`);

    rct(gGroup, gx, gy, GW, gh, {
      rx: 6,
      fill: isRel ? "#e8effd" : "#f4f6fc",
      stroke: isRel ? "#7a9fd8" : C.grpBorder,
      "stroke-width": isRel ? 1.5 : 1,
    });

    gGroup.appendChild(
      el("path", {
        d: `M${gx + 5},${gy} H${gx + GW - 5} Q${gx + GW},${gy} ${gx + GW},${gy + 5} V${gy + GHDR} H${gx} V${gy + 5} Q${gx},${gy} ${gx + 5},${gy}`,
        fill: isView ? C.viewHdrBg : isRel ? C.grpRelHdr : C.grpHdr,
      })
    );

    const nameEl = txt(gGroup, gx + 9, gy + GHDR / 2 + 1, trunc(tn, GW - 18 - (isView ? 44 : 34), 7), {
      ...fontA("Segoe UI,Arial", 11, "700", "#fff"),
    });
    addTooltip(nameEl, tn);

    let badgeLeft = gx + GW - 6;
    if (tdata) {
      const b2 = String(tdata.columns.length);
      const bw2 = b2.length * 7 + 10;
      badgeLeft -= bw2;
      rct(gGroup, badgeLeft, gy + GHDR / 2 - 9, bw2, 18, { rx: 9, fill: "rgba(255,255,255,.18)" });
      txt(gGroup, badgeLeft + bw2 / 2, gy + GHDR / 2 + 1, b2, {
        ...fontA("Arial", 9, "700", "#fff"),
        "text-anchor": "middle",
      });
    }
    if (isView) {
      const vb = "VIEW";
      const vbw = vb.length * 7 + 10;
      badgeLeft -= vbw + 5;
      rct(gGroup, badgeLeft, gy + GHDR / 2 - 9, vbw, 18, { rx: 9, fill: "rgba(255,255,255,.28)" });
      txt(gGroup, badgeLeft + vbw / 2, gy + GHDR / 2 + 1, vb, { ...fontA("Arial", 8, "700", "#fff"), "text-anchor": "middle" });
    }

    tablePos[tn] = { ax: gx, ay: gy + gh / 2, right: gx + GW, left: gx, top: gy, bottom: gy + gh, ci, pre };

    if (tdata) {
      const fkSet = fkPerTable[tn] || new Set<string>();
      const ovCols = getOvCols(tdata, fkSet, opts.colMode);
      colListByTn[tn] = ovCols;
      let ry = gy + GHDR + GPAD;

      ovCols.forEach((col, ci2) => {
        const cry = ry + ci2 * CROW;
        const isPK = col.is_key;
        const isFK = fkSet.has(col.name.toLowerCase());

        if (isRel) {
          rct(gGroup, gx + 5, cry, GW - 6.5, CROW, { fill: ci2 % 2 === 0 ? "#e4edff" : "#dae8fc" });
        } else {
          rct(gGroup, gx + 1.5, cry, GW - 3, CROW, { fill: ci2 % 2 === 0 ? "rgba(255,255,255,.55)" : "rgba(242,246,255,.55)" });
        }
        // A colored left-edge bar on top of the row background, same idea as
        // ER Diagram mode's join-column accent bar - the small key icon alone
        // is easy to miss, this makes "this column participates in a
        // relationship" visible at a glance even when scanning quickly.
        if (isPK || isFK) {
          rct(gGroup, gx + 1.5, cry, 3, CROW, { fill: isPK ? C.pkClr : C.fkClr });
        }
        gGroup.appendChild(el("line", { x1: gx + 8, y1: cry, x2: gx + GW - 8, y2: cry, stroke: "rgba(0,0,0,.05)", "stroke-width": 0.5 }));

        let nx = gx + 8;
        if (isPK || isFK) {
          miniKey(gGroup, nx, cry + CROW / 2 - 4.5, isPK ? C.pkClr : C.fkClr);
          nx += 14;
        }

        const typeW = opts.showType ? 54 : 0;
        const colEl = txt(gGroup, nx, cry + CROW / 2 + 1, trunc(col.name, GW - (nx - gx) - typeW - 6, 6.0), {
          ...fontA("Segoe UI,Arial", 9.5, isPK ? "600" : "400", isPK ? "#5a2800" : isFK ? "#0a1e60" : "#4a5a7a"),
        });
        addTooltip(colEl, col.name);

        if (opts.showType) {
          const bt = (col.type || "").split(/[\s(<]/)[0].toUpperCase().slice(0, 10);
          txt(gGroup, gx + GW - 6, cry + CROW / 2 + 1, bt, { ...monoA(8.5, C.colType), "text-anchor": "end" });
        }
      });
    }

    gGroup.style.cursor = "grab";
    gGroup.addEventListener("mouseenter", () => setRelHighlight(tn));
    gGroup.addEventListener("mouseleave", () => setRelHighlight(null));
    gGroup.addEventListener("pointerdown", (e: PointerEvent) => {
      if (e.button !== 0) return;
      e.stopPropagation();
      e.preventDefault();
      gGroup.setPointerCapture(e.pointerId);
      gGroup.style.cursor = "grabbing";
      const startX = e.clientX;
      const startY = e.clientY;
      const origD = groupDelta[pre] || { dx: 0, dy: 0 };
      const scale = opts.getScale ? opts.getScale() || 1 : 1;

      const onMove = (ev: PointerEvent) => {
        const dx = origD.dx + (ev.clientX - startX) / scale;
        const dy = origD.dy + (ev.clientY - startY) / scale;
        groupDelta[pre] = { dx, dy };
        growCanvasTo(gx + dx + GW + 60, gy + dy + gh + 60);
        gGroup.setAttribute("transform", `translate(${dx},${dy})`);
        if (opts.overrides) opts.overrides[pre] = { dx, dy };
        redrawRelLines();
      };
      const onUp = (ev: PointerEvent) => {
        gGroup.releasePointerCapture(ev.pointerId);
        gGroup.style.cursor = "grab";
        gGroup.removeEventListener("pointermove", onMove);
        gGroup.removeEventListener("pointerup", onUp);
      };
      gGroup.addEventListener("pointermove", onMove);
      gGroup.addEventListener("pointerup", onUp, { once: true });
    });

    grpG.appendChild(gGroup);
  }

  const relG2 = el("g", { id: "rel-lines" });

  // Anchors a relationship endpoint at the exact row of `colName` (when
  // known -- JOIN relationships carry real column names) instead of always
  // the box's vertical center, so it's actually clear which column a line
  // connects to. Falls back to the header (VIEW_SOURCE relationships have
  // no specific column -- a view can depend on a whole table, not one field).
  function effPos(tn: string, colName?: string) {
    const tp = tablePos[tn];
    if (!tp) return null;
    const d = groupDelta[tp.pre] || { dx: 0, dy: 0 };
    const top = tp.top + d.dy;
    const cols = colListByTn[tn] || [];
    const idx = colName ? cols.findIndex((c) => c.name.toLowerCase() === colName.toLowerCase()) : -1;
    const ay = idx < 0 ? top + GHDR / 2 : top + GHDR + GPAD + idx * CROW + CROW / 2;
    return {
      ax: tp.ax + d.dx,
      ay,
      right: tp.right + d.dx,
      left: tp.left + d.dx,
      top,
      bottom: tp.bottom + d.dy,
      ci: tp.ci,
    };
  }

  function redrawRelLines() {
    while (relG2.firstChild) relG2.removeChild(relG2.firstChild);
    const drawnRels = new Set<string>();
    data.relationships.forEach((r, i) => {
      const key = [r.from_table, r.to_table].sort().join("|");
      if (drawnRels.has(key)) return;
      drawnRels.add(key);
      const fp = effPos(r.from_table, r.from_col);
      const tp = effPos(r.to_table, r.to_col);
      if (!fp || !tp) return;
      const clr = i % 2 === 0 ? C.relClr : C.relClr2;
      // Related tables get clustered into the same column (stacked one under
      // another) whenever possible, so most relationships connect vertically
      // now, not across columns - the old always-horizontal connector drawn
      // between left/right box edges made no visual sense for two boxes
      // sharing the same x-range, and rendered entirely hidden behind them.
      let fx: number, fy: number, tx2: number, ty2: number, d: string;
      if (fp.ci === tp.ci) {
        // Same column (stacked boxes): exit and re-enter on the right edge,
        // each at its OWN relationship's specific row, and bulge sideways
        // into the visible gap next to the column - anchoring at a fixed
        // box edge (like top/bottom) would ignore which row the from_col/
        // to_col actually is.
        fx = fp.right + 2;
        tx2 = tp.right + 2;
        fy = fp.ay;
        ty2 = tp.ay;
        const rail = Math.min(36, Math.max(18, Math.abs(ty2 - fy) * 0.25));
        d = `M${fx},${fy} C${fx + rail},${fy} ${tx2 + rail},${ty2} ${tx2},${ty2}`;
      } else {
        if (fp.ci <= tp.ci) {
          fx = fp.right + 2;
          tx2 = tp.left - 2;
        } else {
          fx = fp.left - 2;
          tx2 = tp.right + 2;
        }
        fy = fp.ay;
        ty2 = tp.ay;
        const gap = Math.max(Math.abs(tx2 - fx) * 0.38 + 20, 40);
        const dxC = fx < tx2 ? gap : -gap;
        d = `M${fx},${fy} C${fx + dxC},${fy} ${tx2 - dxC},${ty2} ${tx2},${ty2}`;
      }
      const isViewSrc = r.relationship_type === "VIEW_SOURCE";
      // Dimmed by default and wrapped per-relationship so hovering a table
      // can highlight just its own lines -- with 100+ tables, every line
      // drawn at full opacity all the time turns into unreadable spaghetti.
      const wrap = el("g", { "data-from": r.from_table, "data-to": r.to_table, opacity: "0.7" });
      wrap.appendChild(
        el("path", {
          d,
          stroke: clr,
          "stroke-width": "2.2",
          fill: "none",
          "marker-end": `url(#arr-${i})`,
          ...(isViewSrc ? { "stroke-dasharray": "6,4" } : {}),
        })
      );
      if (!isViewSrc) {
        const mx = (fx + tx2) / 2;
        const my = (fy + ty2) / 2;
        const ls = `${r.from_col} = ${r.to_col}`.slice(0, 22);
        const lw = ls.length * 5.3 + 14;
        rct(wrap, mx - lw / 2, my - 9, lw, 18, { rx: 4, fill: C.relLblBg, stroke: clr, "stroke-width": ".9", opacity: ".93" });
        txt(wrap, mx, my + 1, ls, { ...monoA(8.5, clr), "text-anchor": "middle" });
      }
      relG2.appendChild(wrap);
    });
  }
  redrawRelLines();

  function setRelHighlight(activeTn: string | null) {
    Array.from(relG2.children).forEach((g) => {
      const from = g.getAttribute("data-from");
      const to = g.getAttribute("data-to");
      if (!activeTn) (g as SVGElement).setAttribute("opacity", "0.7");
      else if (from === activeTn || to === activeTn) (g as SVGElement).setAttribute("opacity", "1");
      else (g as SVGElement).setAttribute("opacity", "0.06");
    });
  }

  dg.appendChild(relG2);
  dg.appendChild(grpG);
  svg.appendChild(dg);
  legendG = drawLegend(svg, svgW, svgH, "ov");
  return svg;
}

// ─── Export helpers ────────────────────────────────────────────────────

// Downloaded filenames use `data.database` verbatim, which for the custom
// cross-database diagram is a free-text label like "3 databases (a, b, c)"
// rather than a single identifier -- strip anything that isn't safe/plain
// across OSes instead of passing it straight through.
function sanitizeFilename(name: string): string {
  return name.replace(/[^a-zA-Z0-9_-]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 80) || "diagram";
}

function serSVG(s: SVGElement): string {
  const c = s.cloneNode(true) as SVGElement;
  c.setAttribute("xmlns", NS);
  c.setAttribute("xmlns:xlink", "http://www.w3.org/1999/xlink");
  return '<?xml version="1.0" encoding="UTF-8"?>\n' + new XMLSerializer().serializeToString(c);
}

// ─── React component ───────────────────────────────────────────────────

interface ERDiagramProps {
  data: DrDiagramResponse;
}

export default function ERDiagram({ data }: ERDiagramProps) {
  const [mode, setMode] = useState<"er" | "ov">("er");
  const [colMode, setColMode] = useState<ColMode>(data.table_count > 50 ? "key" : "all");
  const [showType, setShowType] = useState(true);
  const [relOnly, setRelOnly] = useState(false);
  const [rankdir, setRankdir] = useState<"LR" | "TB">("LR");
  const [ovCols, setOvCols] = useState(-1);
  const [aspectRatio, setAspectRatio] = useState(1.5);
  const [layoutVersion, setLayoutVersion] = useState(0);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [bgColor, setBgColor] = useState("#e8ecf4");

  const shellRef = useRef<HTMLDivElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const innerRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGElement | null>(null);
  const view = useRef({ scale: 1, panX: 0, panY: 0 });
  const dragState = useRef<{ dragging: boolean; ox: number; oy: number; opx: number; opy: number }>({
    dragging: false,
    ox: 0,
    oy: 0,
    opx: 0,
    opy: 0,
  });
  // Manual per-table drag positions (ER Diagram mode) and per-group drag
  // offsets (Schema Overview mode). Persist across re-renders triggered by
  // unrelated option changes; cleared whenever a different database's data
  // loads or the user resets the layout.
  const posOverrides = useRef<Record<string, { x: number; y: number }>>({});
  const ovOverrides = useRef<Record<string, { dx: number; dy: number }>>({});

  useEffect(() => {
    posOverrides.current = {};
    ovOverrides.current = {};
  }, [data]);

  function resetLayout() {
    posOverrides.current = {};
    ovOverrides.current = {};
    setLayoutVersion((v) => v + 1);
  }

  const svg = useMemo(() => {
    return mode === "er"
      ? renderER(data, { colMode, showType, relOnly, rankdir, overrides: posOverrides.current, getScale: () => view.current.scale, bgColor, aspectRatio })
      : renderOverview(data, { colMode, showType, ovCols, overrides: ovOverrides.current, getScale: () => view.current.scale, bgColor, aspectRatio });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, mode, colMode, showType, relOnly, rankdir, ovCols, layoutVersion, bgColor, aspectRatio]);

  function applyTransform() {
    if (innerRef.current) {
      const { scale, panX, panY } = view.current;
      innerRef.current.style.transform = `translate(${panX}px,${panY}px) scale(${scale})`;
    }
  }

  function fitToWindow() {
    const wrap = wrapRef.current;
    const s = svgRef.current;
    if (!wrap || !s) return;
    const aw = wrap.clientWidth - 40;
    const ah = wrap.clientHeight - 40;
    const sw = Number(s.getAttribute("width"));
    const sh = Number(s.getAttribute("height"));
    if (!sw || !sh) return;
    const scale = Math.min(aw / sw, ah / sh, 1.4);
    view.current = { scale, panX: (aw - sw * scale) / 2 + 20, panY: (ah - sh * scale) / 2 + 20 };
    applyTransform();
  }

  useEffect(() => {
    svgRef.current = svg;
    if (innerRef.current) {
      innerRef.current.innerHTML = "";
      innerRef.current.appendChild(svg);
    }
    const t = setTimeout(fitToWindow, 60);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [svg]);

  // Large schemas (dozens+ of tables) don't fit readably in the normal
  // in-page panel height -- let the panel take over the whole screen via the
  // Fullscreen API so fitToWindow has much more room to work with.
  function toggleFullscreen() {
    if (document.fullscreenElement) {
      document.exitFullscreen();
    } else {
      shellRef.current?.requestFullscreen();
    }
  }

  useEffect(() => {
    function onFullscreenChange() {
      setIsFullscreen(document.fullscreenElement === shellRef.current);
      setTimeout(fitToWindow, 80);
    }
    document.addEventListener("fullscreenchange", onFullscreenChange);
    return () => document.removeEventListener("fullscreenchange", onFullscreenChange);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const wrap = wrapRef.current;
    if (!wrap) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      view.current.scale = Math.max(0.06, Math.min(8, view.current.scale + (e.deltaY < 0 ? 0.1 : -0.1)));
      applyTransform();
    };
    wrap.addEventListener("wheel", onWheel, { passive: false });
    return () => wrap.removeEventListener("wheel", onWheel);
  }, []);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "f" || e.key === "F") fitToWindow();
      if (e.key === "=" || e.key === "+") {
        view.current.scale = Math.min(8, view.current.scale + 0.2);
        applyTransform();
      }
      if (e.key === "-") {
        view.current.scale = Math.max(0.06, view.current.scale - 0.2);
        applyTransform();
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  });

  function handleMouseDown(e: React.MouseEvent) {
    dragState.current = { dragging: true, ox: e.clientX, oy: e.clientY, opx: view.current.panX, opy: view.current.panY };
  }
  function handleMouseMove(e: React.MouseEvent) {
    if (!dragState.current.dragging) return;
    view.current.panX = dragState.current.opx + e.clientX - dragState.current.ox;
    view.current.panY = dragState.current.opy + e.clientY - dragState.current.oy;
    applyTransform();
  }
  function handleMouseUp() {
    dragState.current.dragging = false;
  }

  function downloadSVG() {
    const s = svgRef.current;
    if (!s) return;
    try {
      const blob = new Blob([serSVG(s)], { type: "image/svg+xml" });
      const a = Object.assign(document.createElement("a"), {
        href: URL.createObjectURL(blob),
        download: `drdiagram_${sanitizeFilename(data.database)}_${mode}.svg`,
      });
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (err) {
      console.error("Export SVG failed:", err);
      window.alert("Export SVG failed. See the browser console for details.");
    }
  }
  function downloadPNG() {
    const s = svgRef.current;
    if (!s) return;
    const rawW = Number(s.getAttribute("width"));
    const rawH = Number(s.getAttribute("height"));
    if (!rawW || !rawH) return;

    // A very large schema (many tables, "All columns" mode) can produce an
    // SVG far too big to rasterize at a fixed 2.5x scale -- canvases have a
    // hard per-dimension AND total-pixel-area limit (varies by browser, but
    // commonly ~16384px/side or ~270 million total pixels), past which
    // `getContext("2d")`/`toBlob` fail silently rather than throwing, which
    // otherwise looks exactly like "the export button does nothing" with no
    // error at all. Scale down first so it always stays within a safe
    // budget -- generous enough that most diagrams still export at the full
    // 2.5x (sharp when zoomed into afterwards), only kicking in for
    // genuinely huge schemas.
    const MAX_PIXELS = 180_000_000;
    const MAX_DIM = 14_000;
    const scale = Math.max(
      0.1,
      Math.min(2.5, Math.sqrt(MAX_PIXELS / (rawW * rawH)) || 2.5, MAX_DIM / rawW, MAX_DIM / rawH)
    );

    const blob = new Blob([serSVG(s)], { type: "image/svg+xml" });
    const url = URL.createObjectURL(blob);
    const img = new Image();
    img.onerror = () => {
      URL.revokeObjectURL(url);
      window.alert("Export PNG failed while rendering the diagram. Try Export SVG instead.");
    };
    img.onload = () => {
      const cw = rawW * scale;
      const ch = rawH * scale;
      const cv = document.createElement("canvas");
      cv.width = cw;
      cv.height = ch;
      const ctx = cv.getContext("2d");
      URL.revokeObjectURL(url);
      if (!ctx) {
        window.alert("Export PNG failed: this browser wouldn't allocate a canvas for the diagram.");
        return;
      }
      ctx.fillStyle = "#fff";
      ctx.fillRect(0, 0, cw, ch);
      ctx.scale(scale, scale);
      ctx.drawImage(img, 0, 0);
      cv.toBlob((b2) => {
        if (!b2) {
          window.alert("Export PNG failed: the diagram may be too large to export as an image. Try Export SVG instead.");
          return;
        }
        const a = Object.assign(document.createElement("a"), {
          href: URL.createObjectURL(b2),
          download: `drdiagram_${sanitizeFilename(data.database)}_${mode}.png`,
        });
        a.click();
        URL.revokeObjectURL(a.href);
      }, "image/png");
    };
    img.src = url;
  }

  return (
    <div className={`er-diagram-shell${isFullscreen ? " is-fullscreen" : ""}`} ref={shellRef}>
      <div className="panel er-controls">
        <div className="er-control-group">
          <label className="sl">View Mode</label>
          <div className="row" style={{ gap: "0.4rem" }}>
            <button className={`mode-btn ${mode === "er" ? "active" : ""}`} onClick={() => setMode("er")}>
              ER Diagram
            </button>
            <button className={`mode-btn ${mode === "ov" ? "active" : ""}`} onClick={() => setMode("ov")}>
              Schema Overview
            </button>
          </div>
        </div>

        <div className="er-control-group">
          <label className="sl">Columns</label>
          <select value={colMode} onChange={(e) => setColMode(e.target.value as ColMode)}>
            <option value="all">All columns</option>
            <option value="key">PK + FK columns</option>
            <option value="none">Name only</option>
          </select>
          <label className="er-toggle">
            <input type="checkbox" checked={showType} onChange={(e) => setShowType(e.target.checked)} />
            Show data type
          </label>
        </div>

        <div className="er-control-group">
          <label className="sl">Background</label>
          <div className="row" style={{ gap: "0.4rem" }}>
            <input
              type="color"
              value={/^#[0-9a-fA-F]{6}$/.test(bgColor) ? bgColor : "#ffffff"}
              onChange={(e) => setBgColor(e.target.value)}
              title="Diagram background color"
              style={{ width: 40, height: 30, padding: 0, border: "1.5px solid var(--color-border-strong)", borderRadius: 7, cursor: "pointer" }}
            />
            <input
              type="text"
              value={bgColor}
              onChange={(e) => setBgColor(e.target.value)}
              title="Diagram background color (hex code)"
              placeholder="#e8ecf4"
              spellCheck={false}
              style={{ width: 90, height: 30, padding: "0 0.5rem", border: "1.5px solid var(--color-border-strong)", borderRadius: 7, fontFamily: "monospace", fontSize: "0.85rem" }}
            />
          </div>
        </div>

        <div className="er-control-group">
          <label className="sl">Aspect Ratio</label>
          <div className="row" style={{ gap: "0.4rem" }}>
            <select value={aspectRatio} onChange={(e) => setAspectRatio(Number(e.target.value))} title="Overall canvas width:height ratio">
              <option value={1}>1:1 Square</option>
              <option value={1.33}>4:3</option>
              <option value={1.5}>3:2 Balanced</option>
              <option value={1.78}>16:9 Widescreen</option>
              <option value={2}>2:1 Wide</option>
            </select>
            <input
              type="number"
              min={0.5}
              max={4}
              step={0.05}
              value={aspectRatio}
              onChange={(e) => {
                const v = Number(e.target.value);
                if (v > 0) setAspectRatio(v);
              }}
              title="Custom width:height ratio (e.g. 1.5 for 3:2)"
              style={{ width: 64, height: 30, padding: "0 0.5rem", border: "1.5px solid var(--color-border-strong)", borderRadius: 7 }}
            />
          </div>
        </div>

        {mode === "er" ? (
          <div className="er-control-group">
            <label className="er-toggle">
              <input type="checkbox" checked={relOnly} onChange={(e) => setRelOnly(e.target.checked)} />
              Related tables only
            </label>
            <label className="sl">Layout</label>
            <select value={rankdir} onChange={(e) => setRankdir(e.target.value as "LR" | "TB")}>
              <option value="LR">Left &rarr; Right</option>
              <option value="TB">Top &rarr; Bottom</option>
            </select>
            <button className="btn" type="button" title="Discard manually dragged table positions" onClick={resetLayout}>
              Reset Layout
            </button>
          </div>
        ) : (
          <div className="er-control-group">
            <label className="sl">Columns per row</label>
            <select value={ovCols} onChange={(e) => setOvCols(Number(e.target.value))}>
              <option value={-1}>Auto (landscape)</option>
              <option value={3}>3 columns</option>
              <option value={4}>4 columns</option>
              <option value={5}>5 columns</option>
              <option value={6}>6 columns</option>
              <option value={8}>8 columns</option>
              <option value={10}>10 columns</option>
              <option value={12}>12 columns</option>
            </select>
            <button className="btn" type="button" title="Discard manually dragged table positions" onClick={resetLayout}>
              Reset Layout
            </button>
          </div>
        )}

        <div className="er-control-group er-stats">
          <span>{data.table_count} tables</span>
          <span>{data.view_count} views</span>
          <span>{data.relationship_count} relationships</span>
        </div>
      </div>

      <div
        className="er-diagram-area"
        ref={wrapRef}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        style={{ background: bgColor }}
      >
        <div
          ref={innerRef}
          className="er-diagram-inner"
          onMouseDown={handleMouseDown}
          style={{ cursor: dragState.current.dragging ? "grabbing" : "grab" }}
        />
        <div className="er-tools">
          <button
            className="btn btn-sm"
            onClick={toggleFullscreen}
            title={isFullscreen ? "Exit full screen (Esc)" : "Full screen"}
          >
            {isFullscreen ? "⤡" : "⛶"}
          </button>
          <button className="btn btn-sm" onClick={fitToWindow} title="Fit (F)">
            &#x2922;
          </button>
          <button
            className="btn btn-sm"
            onClick={() => {
              view.current.scale = Math.min(8, view.current.scale + 0.2);
              applyTransform();
            }}
          >
            +
          </button>
          <button
            className="btn btn-sm"
            onClick={() => {
              view.current.scale = Math.max(0.06, view.current.scale - 0.2);
              applyTransform();
            }}
          >
            &minus;
          </button>
        </div>
        <div className="er-export-bar">
          <button className="btn btn-sm" onClick={downloadPNG}>
            Export PNG
          </button>
          <button className="btn btn-sm" onClick={downloadSVG}>
            Export SVG
          </button>
        </div>
      </div>
    </div>
  );
}
