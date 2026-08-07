// `react-cytoscapejs` ships as plain JS with no bundled type declarations and
// there is no reliably-published @types package for it, so we declare a
// minimal ambient module covering the props this app actually uses.
declare module "react-cytoscapejs" {
  import type { Core, ElementDefinition, LayoutOptions, StylesheetStyle } from "cytoscape";
  import type { Component } from "react";

  export interface CytoscapeComponentProps {
    elements: ElementDefinition[];
    style?: React.CSSProperties;
    className?: string;
    layout?: LayoutOptions;
    stylesheet?: StylesheetStyle[];
    cy?: (cy: Core) => void;
    zoom?: number;
    pan?: { x: number; y: number };
    minZoom?: number;
    maxZoom?: number;
    boxSelectionEnabled?: boolean;
    autoungrabify?: boolean;
    autolock?: boolean;
    autounselectify?: boolean;
    wheelSensitivity?: number;
  }

  export default class CytoscapeComponent extends Component<CytoscapeComponentProps> {
    static normalizeElements(elements: unknown): ElementDefinition[];
  }
}
