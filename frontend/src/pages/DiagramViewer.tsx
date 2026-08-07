import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import GraphCanvas from "../components/GraphCanvas";
import LineageDetail from "../components/LineageDetail";
import {
  getDiagram,
  getLineage,
  getObject,
  type CytoscapeElement,
  type DataObjectDetail,
  type DiagramGranularity,
  type LineageDirection,
  type LineageEdgeRead,
} from "../services/api";

export default function DiagramViewer() {
  const { objectId } = useParams<{ objectId: string }>();

  const [object, setObject] = useState<DataObjectDetail | null>(null);

  const [direction, setDirection] = useState<LineageDirection>("both");
  const [depth, setDepth] = useState(3);
  const [granularity, setGranularity] = useState<DiagramGranularity>("table");

  const [elements, setElements] = useState<CytoscapeElement[]>([]);
  const [diagramLoading, setDiagramLoading] = useState(true);
  const [diagramError, setDiagramError] = useState<string | null>(null);
  const [truncated, setTruncated] = useState(false);
  const [counts, setCounts] = useState<{ nodes: number; edges: number }>({ nodes: 0, edges: 0 });

  const [edges, setEdges] = useState<LineageEdgeRead[]>([]);
  const [lineageLoading, setLineageLoading] = useState(true);
  const [focusedObjectId, setFocusedObjectId] = useState<string | null>(null);

  useEffect(() => {
    if (!objectId) return;
    getObject(objectId)
      .then(setObject)
      .catch(() => setObject(null));
  }, [objectId]);

  useEffect(() => {
    if (!objectId) return;
    setDiagramLoading(true);
    setDiagramError(null);
    getDiagram(objectId, { direction, depth, granularity })
      .then((res) => {
        setElements(res.elements);
        setTruncated(res.truncated);
        setCounts({ nodes: res.node_count, edges: res.edge_count });
      })
      .catch((err) => setDiagramError(describeError(err)))
      .finally(() => setDiagramLoading(false));
  }, [objectId, direction, depth, granularity]);

  useEffect(() => {
    if (!objectId) return;
    setLineageLoading(true);
    setFocusedObjectId(objectId);
    getLineage(objectId, { direction, depth })
      .then(setEdges)
      .catch(() => setEdges([]))
      .finally(() => setLineageLoading(false));
  }, [objectId, direction, depth]);

  function handleNodeClick(nodeId: string) {
    // Node ids for table/object-granularity nodes are the object_id itself;
    // for column-granularity nodes they are typically `${objectId}:${columnId}`
    // style composite ids from the backend. Either way, re-fetch lineage
    // centered on the object portion of the clicked node so the side panel
    // reflects what was clicked.
    const objectPortion = nodeId.split(":")[0];
    setFocusedObjectId(objectPortion);
    setLineageLoading(true);
    getLineage(objectPortion, { direction, depth })
      .then(setEdges)
      .catch(() => setEdges([]))
      .finally(() => setLineageLoading(false));
  }

  return (
    <div className="stack">
      <h1>Lineage Diagram</h1>
      <p className="muted">
        {object ? (
          <>
            <strong>
              {object.database_name}.{object.object_name}
            </strong>{" "}
            <span className={object.object_type === "TABLE" ? "badge badge-object-table" : "badge badge-object-view"}>
              {object.object_type}
            </span>
          </>
        ) : (
          <>Object {objectId}</>
        )}
        {object ? (
          <>
            {" "}
            &middot;{" "}
            <Link to={`/connections/${object.connection_id}/explorer`}>back to explorer</Link>
          </>
        ) : (
          <>
            {" "}
            &middot; <Link to="/connections">back to connections</Link>
          </>
        )}
      </p>

      <div className="panel row" style={{ alignItems: "flex-end", flexWrap: "wrap" }}>
        <label>
          Direction
          <select value={direction} onChange={(e) => setDirection(e.target.value as LineageDirection)}>
            <option value="upstream">upstream</option>
            <option value="downstream">downstream</option>
            <option value="both">both</option>
          </select>
        </label>
        <label>
          Depth
          <input
            type="number"
            min={1}
            max={10}
            value={depth}
            onChange={(e) => setDepth(Number(e.target.value) || 1)}
          />
        </label>
        <label>
          Granularity
          <select
            value={granularity}
            onChange={(e) => setGranularity(e.target.value as DiagramGranularity)}
          >
            <option value="table">table</option>
            <option value="column">column</option>
          </select>
        </label>
        {!diagramLoading && !diagramError && (
          <span className="muted">
            {counts.nodes} nodes / {counts.edges} edges{truncated ? " (truncated)" : ""}
          </span>
        )}
      </div>

      <div className="sidebar-layout" style={{ gridTemplateColumns: "1fr 380px" }}>
        <div>
          {diagramLoading && (
            <div className="panel">
              <p className="muted">Loading diagram...</p>
            </div>
          )}
          {diagramError && (
            <div className="panel">
              <p className="error-text">{diagramError}</p>
            </div>
          )}
          {!diagramLoading && !diagramError && counts.nodes === 0 && (
            <div className="panel">
              <p className="muted">
                No lineage found for this object yet. Either no <strong>LINEAGE_SCAN</strong> has run for
                its connection, or the SQL behind it couldn't be resolved. Trigger a lineage scan from the{" "}
                <Link to="/scans">Scan Jobs</Link> page, then come back here.
              </p>
            </div>
          )}
          {!diagramLoading && !diagramError && counts.nodes > 0 && (
            <GraphCanvas elements={elements} onNodeClick={handleNodeClick} />
          )}
        </div>
        <LineageDetail edges={edges} loading={lineageLoading} focusedObjectId={focusedObjectId} />
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
