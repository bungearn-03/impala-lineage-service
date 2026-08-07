import { Link } from "react-router-dom";
import type { DataObjectDetail } from "../services/api";
import SqlViewer from "./SqlViewer";

interface ObjectPanelProps {
  object: DataObjectDetail;
}

export default function ObjectPanel({ object }: ObjectPanelProps) {
  return (
    <div className="panel stack">
      <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h2 style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem" }}>
            {object.database_name}.{object.object_name}
            <span
              className={
                object.object_type === "TABLE" ? "badge badge-object-table" : "badge badge-object-view"
              }
            >
              {object.object_type}
            </span>
          </h2>
          <p className="muted">
            {object.last_scanned_at
              ? `Last scanned ${new Date(object.last_scanned_at).toLocaleString()}`
              : "Never scanned"}
          </p>
        </div>
        <Link className="btn btn-primary" to={`/diagram/${object.id}`}>
          View Diagram
        </Link>
      </div>

      <div>
        <h3>Columns ({object.columns.length})</h3>
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>Name</th>
              <th>Type</th>
              <th>Nullable</th>
            </tr>
          </thead>
          <tbody>
            {object.columns.map((col) => (
              <tr key={col.id}>
                <td>{col.ordinal_position}</td>
                <td>{col.name}</td>
                <td>
                  <code>{col.data_type}</code>
                </td>
                <td>{col.is_nullable ? "yes" : "no"}</td>
              </tr>
            ))}
            {object.columns.length === 0 && (
              <tr>
                <td colSpan={4} className="muted">
                  No column metadata available.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <SqlViewer title="DDL" sql={object.ddl} />
      <SqlViewer title="View Definition" sql={object.view_definition} />
    </div>
  );
}
