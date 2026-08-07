// `dagre` ships as plain JS with no bundled type declarations. This covers
// only the small API surface this app actually uses (graph construction +
// layout for the DR/ER diagram's automatic table positioning).
declare module "dagre" {
  export interface GraphLabel {
    width?: number;
    height?: number;
    rankdir?: string;
    nodesep?: number;
    ranksep?: number;
    marginx?: number;
    marginy?: number;
    acyclicer?: string;
    ranker?: string;
  }

  export interface NodeLayout {
    x: number;
    y: number;
    width: number;
    height: number;
  }

  export namespace graphlib {
    class Graph {
      setGraph(label: GraphLabel): void;
      graph(): GraphLabel;
      setDefaultEdgeLabel(fn: () => Record<string, unknown>): void;
      setNode(name: string, label: { width: number; height: number }): void;
      setEdge(source: string, target: string): void;
      node(name: string): NodeLayout | undefined;
    }
  }

  export function layout(graph: graphlib.Graph): void;
}
