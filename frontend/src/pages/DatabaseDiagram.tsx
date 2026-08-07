import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import ERDiagram from "../components/ERDiagram";
import { getConnection, getDrDiagram, type ConnectionRead, type DrDiagramResponse } from "../services/api";

export default function DatabaseDiagram() {
  const { connectionId, databaseName } = useParams<{ connectionId: string; databaseName: string }>();

  const [connection, setConnection] = useState<ConnectionRead | null>(null);
  const [data, setData] = useState<DrDiagramResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!connectionId) return;
    getConnection(connectionId).catch(() => setConnection(null)).then((c) => c && setConnection(c));
  }, [connectionId]);

  useEffect(() => {
    if (!connectionId || !databaseName) return;
    setLoading(true);
    setError(null);
    getDrDiagram(connectionId, databaseName)
      .then(setData)
      .catch((err) => setError(describeError(err)))
      .finally(() => setLoading(false));
  }, [connectionId, databaseName]);

  return (
    <div className="stack">
      <h1>DR Diagram</h1>
      <p className="muted">
        <strong>{connection?.name ?? connectionId}</strong> &middot; <strong>{databaseName}</strong>{" "}
        &middot;{" "}
        {connectionId ? (
          <Link to={`/connections/${connectionId}/explorer`}>back to explorer</Link>
        ) : (
          <Link to="/connections">back to connections</Link>
        )}
      </p>

      {loading && (
        <div className="panel">
          <p className="muted">Loading diagram...</p>
        </div>
      )}
      {error && (
        <div className="panel">
          <p className="error-text">{error}</p>
        </div>
      )}
      {!loading && !error && data && data.table_count === 0 && (
        <div className="panel">
          <p className="muted">
            No tables scanned yet for this database. Trigger a <strong>METADATA_SCAN</strong> from the{" "}
            <Link to="/scans">Scan Jobs</Link> page, then come back here.
          </p>
        </div>
      )}
      {!loading && !error && data && data.table_count > 0 && data.relationship_count === 0 && (
        <div className="panel">
          <p className="muted">
            {data.table_count} tables found ({data.view_count} views), but no JOIN relationships detected
            between them. This is computed live from each view's SQL every time you open this page (no
            separate scan needed) -- it means either this database has no views, its views' JOINs couldn't
            be parsed, or the views simply don't join tables together. Showing tables with no connecting
            lines below.
          </p>
        </div>
      )}
      {!loading && !error && data && data.table_count > 0 && <ERDiagram data={data} />}
    </div>
  );
}

function describeError(err: unknown): string {
  if (err && typeof err === "object" && "message" in err) {
    return String((err as { message: unknown }).message);
  }
  return "Something went wrong.";
}
