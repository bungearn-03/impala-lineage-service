import { useMemo } from "react";
import CytoscapeComponent from "react-cytoscapejs";
import type { Core, ElementDefinition, LayoutOptions, StylesheetStyle } from "cytoscape";
import type { CytoscapeElement } from "../services/api";

interface GraphCanvasProps {
  elements: CytoscapeElement[];
  onNodeClick?: (nodeId: string) => void;
}

// Layout choice: we use cytoscape's built-in `breadthfirst` layout rather than
// pulling in `cytoscape-dagre` (an extra dependency + peer-dependency wiring)
// for what is, for lineage graphs of this depth, a fairly similar visual
// result: a directed layer-by-layer tree. `breadthfirst` lays nodes out
// top-to-bottom by default, so we rotate the computed positions 90 degrees
// via the `transform` hook to get a left-to-right upstream -> downstream
// flow, which reads more naturally for lineage diagrams.
// Built as a loose record and cast at the end: `@types/cytoscape`'s
// BreadthFirstLayoutOptions typing does not declare `transform`, even though
// cytoscape's breadthfirst layout supports it at runtime.
const rawLayout: Record<string, unknown> = {
  name: "breadthfirst",
  directed: true,
  spacingFactor: 1.2,
  padding: 30,
  transform: (_node: unknown, position: { x: number; y: number }) => ({
    x: position.y,
    y: position.x,
  }),
};
const layout = rawLayout as unknown as LayoutOptions;

const stylesheet: StylesheetStyle[] = [
  {
    selector: 'node[type = "object"]',
    style: {
      shape: "round-rectangle",
      "background-color": "#2563eb",
      label: "data(label)",
      color: "#ffffff",
      "text-valign": "center",
      "text-halign": "center",
      "font-size": 11,
      "text-wrap": "wrap",
      "text-max-width": "110px",
      width: 130,
      height: 44,
      "border-width": 1,
      "border-color": "#1d4ed8",
    },
  },
  {
    selector: 'node[type = "column"]',
    style: {
      shape: "ellipse",
      "background-color": "#a78bfa",
      label: "data(label)",
      color: "#1e1b3a",
      "text-valign": "center",
      "text-halign": "center",
      "font-size": 9,
      width: 70,
      height: 28,
      "border-width": 1,
      "border-color": "#7c3aed",
    },
  },
  {
    selector: "edge",
    style: {
      width: 2,
      "line-color": "#9ca3af",
      "target-arrow-color": "#9ca3af",
      "target-arrow-shape": "triangle",
      "curve-style": "bezier",
      label: "data(label)",
      "font-size": 8,
      color: "#4b5563",
      "text-background-color": "#ffffff",
      "text-background-opacity": 0.85,
      "text-background-padding": "1px",
    },
  },
  {
    selector: "edge[transformation_type = 'DIRECT']",
    style: { "line-color": "#16a34a", "target-arrow-color": "#16a34a" },
  },
  {
    selector: "edge[transformation_type = 'DERIVED']",
    style: { "line-color": "#d97706", "target-arrow-color": "#d97706" },
  },
  {
    selector: "edge[transformation_type = 'AGGREGATED']",
    style: { "line-color": "#7c3aed", "target-arrow-color": "#7c3aed" },
  },
  {
    selector: "edge[transformation_type = 'JOIN']",
    style: { "line-color": "#2563eb", "target-arrow-color": "#2563eb" },
  },
];

export default function GraphCanvas({ elements, onNodeClick }: GraphCanvasProps) {
  // react-cytoscapejs wants `label` set on edges for our stylesheet's
  // `label: "data(label)"` selector; fall back to transformation_type when no
  // explicit label was provided by the API.
  const normalized: ElementDefinition[] = useMemo(
    () =>
      elements.map((el) => {
        if (el.group === "edges") {
          const data = el.data as { label?: string; transformation_type?: string };
          return {
            group: el.group,
            data: { ...el.data, label: data.label ?? data.transformation_type ?? "" },
          };
        }
        return { group: el.group, data: el.data };
      }),
    [elements]
  );

  return (
    <div className="panel" style={{ padding: 0, overflow: "hidden" }}>
      <CytoscapeComponent
        elements={normalized}
        style={{ width: "100%", height: "600px" }}
        layout={layout}
        stylesheet={stylesheet}
        cy={(cy: Core) => {
          cy.off("tap", "node");
          cy.on("tap", "node", (evt) => {
            const id = evt.target.id();
            onNodeClick?.(id);
          });
        }}
      />
    </div>
  );
}
