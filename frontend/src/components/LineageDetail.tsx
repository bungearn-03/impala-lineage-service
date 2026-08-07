import type { LineageEdgeRead, LineageSource } from "../services/api";

interface LineageDetailProps {
  edges: LineageEdgeRead[];
  loading?: boolean;
  focusedObjectId?: string | null;
}

function sourceBadgeClass(source: LineageSource): string {
  switch (source) {
    case "PARSER":
      return "badge badge-source-parser";
    case "AI":
      return "badge badge-source-ai";
    case "MANUAL":
      return "badge badge-source-manual";
    default:
      return "badge";
  }
}

function endpointLabel(endpoint: LineageEdgeRead["source"]): string {
  return endpoint.column_name ? `${endpoint.object_full_name}.${endpoint.column_name}` : endpoint.object_full_name;
}

export default function LineageDetail({ edges, loading, focusedObjectId }: LineageDetailProps) {
  return (
    <div className="panel stack">
      <h3>Lineage Edges {focusedObjectId ? <span className="muted">(around selected node)</span> : null}</h3>
      {loading && <p className="muted">Loading lineage...</p>}
      {!loading && edges.length === 0 && <p className="muted">No lineage edges found.</p>}
      {!loading && edges.length > 0 && (
        <ul className="list-reset stack" style={{ gap: "0.6rem" }}>
          {edges.map((edge) => (
            <li key={edge.id} className="panel" style={{ padding: "0.6rem 0.75rem" }}>
              <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
                <div style={{ fontSize: "0.85rem" }}>
                  <strong>{endpointLabel(edge.source)}</strong>
                  <span className="muted"> {"->"} </span>
                  <strong>{endpointLabel(edge.target)}</strong>
                </div>
                <span className={sourceBadgeClass(edge.created_by)}>{edge.created_by}</span>
              </div>
              <div className="row" style={{ marginTop: "0.35rem", gap: "0.75rem", fontSize: "0.8rem" }}>
                <span className="muted">
                  Type: <strong>{edge.transformation_type}</strong>
                </span>
                <span className="muted">Confidence: {edge.confidence.toFixed(2)}</span>
              </div>
              {edge.transformation_expr && (
                <pre
                  style={{
                    marginTop: "0.4rem",
                    marginBottom: 0,
                    fontSize: "0.78rem",
                    background: "#f3f4f6",
                    padding: "0.4rem 0.55rem",
                    borderRadius: 4,
                    overflowX: "auto",
                  }}
                >
                  <code>{edge.transformation_expr}</code>
                </pre>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
