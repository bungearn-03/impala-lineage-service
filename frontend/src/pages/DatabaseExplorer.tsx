import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import ObjectPanel from "../components/ObjectPanel";
import {
  createScan,
  getConnection,
  getObject,
  listDatabases,
  listObjects,
  type ConnectionRead,
  type DatabaseSummary,
  type DataObjectDetail,
  type DataObjectSummary,
} from "../services/api";

export default function DatabaseExplorer() {
  const { connectionId } = useParams<{ connectionId: string }>();

  const [connection, setConnection] = useState<ConnectionRead | null>(null);

  const [databases, setDatabases] = useState<DatabaseSummary[]>([]);
  const [databasesLoading, setDatabasesLoading] = useState(true);
  const [databasesError, setDatabasesError] = useState<string | null>(null);
  const [selectedDb, setSelectedDb] = useState<string | null>(null);

  const [scanState, setScanState] = useState<"idle" | "loading" | "started" | "error">("idle");

  const [objects, setObjects] = useState<DataObjectSummary[]>([]);
  const [objectsLoading, setObjectsLoading] = useState(false);
  const [objectsError, setObjectsError] = useState<string | null>(null);

  const [selectedObjectId, setSelectedObjectId] = useState<string | null>(null);
  const [objectDetail, setObjectDetail] = useState<DataObjectDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  useEffect(() => {
    if (!connectionId) return;
    getConnection(connectionId).catch(() => setConnection(null)).then((c) => c && setConnection(c));
  }, [connectionId]);

  function loadDatabases() {
    if (!connectionId) return;
    setDatabasesLoading(true);
    setDatabasesError(null);
    listDatabases(connectionId)
      .then(setDatabases)
      .catch((err) => setDatabasesError(describeError(err)))
      .finally(() => setDatabasesLoading(false));
  }

  useEffect(loadDatabases, [connectionId]);

  async function handleScanNow() {
    if (!connectionId) return;
    setScanState("loading");
    try {
      await createScan({ connection_id: connectionId, job_type: "METADATA_SCAN" });
      setScanState("started");
    } catch {
      setScanState("error");
    }
  }

  useEffect(() => {
    if (!connectionId || !selectedDb) return;
    setObjectsLoading(true);
    setObjectsError(null);
    setSelectedObjectId(null);
    setObjectDetail(null);
    listObjects(connectionId, selectedDb)
      .then(setObjects)
      .catch((err) => setObjectsError(describeError(err)))
      .finally(() => setObjectsLoading(false));
  }, [connectionId, selectedDb]);

  useEffect(() => {
    if (!selectedObjectId) return;
    setDetailLoading(true);
    setDetailError(null);
    getObject(selectedObjectId)
      .then(setObjectDetail)
      .catch((err) => setDetailError(describeError(err)))
      .finally(() => setDetailLoading(false));
  }, [selectedObjectId]);

  return (
    <div className="stack">
      <h1>Database Explorer</h1>
      <p className="muted">
        Connection <strong>{connection?.name ?? connectionId}</strong> &middot;{" "}
        <Link to="/connections">back to connections</Link>
      </p>

      <div className="three-col-layout">
        <div className="panel">
          <h3>Databases</h3>
          {databasesLoading && <p className="muted">Loading...</p>}
          {databasesError && <p className="error-text">{databasesError}</p>}
          {!databasesLoading && !databasesError && (
            <ul className="list-reset stack" style={{ gap: "0.5rem" }}>
              {databases.map((db) => (
                <li
                  key={db.database_name}
                  className={`db-card ${selectedDb === db.database_name ? "selected" : ""}`}
                >
                  <button className="db-card-main" onClick={() => setSelectedDb(db.database_name)}>
                    <span>{db.database_name}</span>
                    <span className="db-card-counts">
                      {db.table_count}t / {db.view_count}v
                    </span>
                  </button>
                  <Link
                    className="db-card-diagram-link"
                    to={`/connections/${connectionId}/databases/${encodeURIComponent(db.database_name)}/diagram`}
                    title="View this database as a whole ER-style diagram"
                  >
                    DR Diagram
                  </Link>
                </li>
              ))}
              {databases.length === 0 && (
                <li className="stack" style={{ gap: "0.5rem" }}>
                  <span className="muted">
                    No databases found yet. This connection hasn't been scanned, or the last scan hasn't
                    finished.
                  </span>
                  <div className="row" style={{ gap: "0.5rem", alignItems: "center" }}>
                    <button
                      className="btn btn-sm btn-primary"
                      onClick={handleScanNow}
                      disabled={scanState === "loading"}
                    >
                      {scanState === "loading" ? "Starting..." : "Run Metadata Scan"}
                    </button>
                    {scanState === "started" && (
                      <span className="muted" style={{ fontSize: "0.75rem" }}>
                        Started &middot; <Link to="/scans">watch progress &rarr;</Link>
                      </span>
                    )}
                    {scanState === "error" && <span className="error-text">Failed to start scan</span>}
                  </div>
                </li>
              )}
            </ul>
          )}
        </div>

        <div className="panel">
          <h3>Objects {selectedDb ? `in ${selectedDb}` : ""}</h3>
          {!selectedDb && <p className="muted">Select a database.</p>}
          {objectsLoading && <p className="muted">Loading objects...</p>}
          {objectsError && <p className="error-text">{objectsError}</p>}
          {selectedDb && !objectsLoading && !objectsError && (
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Type</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {objects.map((obj) => (
                  <tr
                    key={obj.id}
                    className={`clickable-row ${selectedObjectId === obj.id ? "selected" : ""}`}
                    onClick={() => setSelectedObjectId(obj.id)}
                  >
                    <td>{obj.object_name}</td>
                    <td>
                      <span
                        className={
                          obj.object_type === "TABLE" ? "badge badge-object-table" : "badge badge-object-view"
                        }
                      >
                        {obj.object_type}
                      </span>
                    </td>
                    <td>
                      <Link
                        className="btn btn-sm"
                        to={`/diagram/${obj.id}`}
                        onClick={(e) => e.stopPropagation()}
                      >
                        View Diagram
                      </Link>
                    </td>
                  </tr>
                ))}
                {objects.length === 0 && (
                  <tr>
                    <td colSpan={3} className="muted">
                      No objects in this database.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
        </div>

        <div>
          {detailLoading && <p className="muted">Loading object...</p>}
          {detailError && <p className="error-text">{detailError}</p>}
          {!detailLoading && !detailError && objectDetail && <ObjectPanel object={objectDetail} />}
          {!detailLoading && !detailError && !objectDetail && (
            <div className="panel">
              <p className="muted">Select an object to view its details.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function describeError(err: unknown): string {
  if (err && typeof err === "object" && "message" in err) {
    return String((err as { message: unknown }).message);
  }
  return "Something went wrong.";
}
