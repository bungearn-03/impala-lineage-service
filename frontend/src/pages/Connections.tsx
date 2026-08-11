import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import {
  createConnection,
  createScan,
  deleteConnection,
  listConnections,
  testConnection,
  type AuthMechanism,
  type ConnectionCreate,
  type ConnectionRead,
  type ConnectionTestResult,
  type ConnectionType,
  type ScanJobRead,
} from "../services/api";

const emptyForm: ConnectionCreate = {
  name: "",
  conn_type: "impala",
  host: "",
  port: 21050,
  default_database: "default",
  auth_mechanism: "NOSASL",
  username: "",
  password: "",
};

export default function Connections() {
  const [connections, setConnections] = useState<ConnectionRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [form, setForm] = useState<ConnectionCreate>(emptyForm);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, ConnectionTestResult | "loading" | "error">>({});
  const [scanResults, setScanResults] = useState<Record<string, ScanJobRead | "loading" | "error">>({});

  async function refresh() {
    setLoading(true);
    setLoadError(null);
    try {
      const data = await listConnections();
      setConnections(data);
    } catch (err) {
      setLoadError(describeError(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  function updateField<K extends keyof ConnectionCreate>(key: K, value: ConnectionCreate[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setSubmitError(null);
    try {
      await createConnection({
        ...form,
        port: Number(form.port),
        username: form.username || undefined,
        password: form.password || undefined,
      });
      setForm(emptyForm);
      await refresh();
    } catch (err) {
      setSubmitError(describeError(err));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleTest(id: string) {
    setTestResults((prev) => ({ ...prev, [id]: "loading" }));
    try {
      const result = await testConnection(id);
      setTestResults((prev) => ({ ...prev, [id]: result }));
    } catch {
      setTestResults((prev) => ({ ...prev, [id]: "error" }));
    }
  }

  async function handleScan(id: string) {
    setScanResults((prev) => ({ ...prev, [id]: "loading" }));
    try {
      const job = await createScan({ connection_id: id, job_type: "METADATA_SCAN" });
      setScanResults((prev) => ({ ...prev, [id]: job }));
    } catch {
      setScanResults((prev) => ({ ...prev, [id]: "error" }));
    }
  }

  async function handleDelete(id: string) {
    if (!confirm("Delete this connection? This cannot be undone.")) {
      return;
    }
    try {
      await deleteConnection(id);
      await refresh();
    } catch (err) {
      alert(describeError(err));
    }
  }

  return (
    <div className="stack">
      <h1>Connections</h1>

      <div className="panel">
        {loading && <p className="muted">Loading connections...</p>}
        {loadError && <p className="error-text">{loadError}</p>}
        {!loading && !loadError && (
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Type</th>
                <th>Host</th>
                <th>Default DB</th>
                <th>Auth</th>
                <th>Active</th>
                <th>Test</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {connections.map((conn) => {
                const testState = testResults[conn.id];
                return (
                  <tr key={conn.id}>
                    <td>{conn.name}</td>
                    <td>{conn.conn_type}</td>
                    <td>
                      {conn.host}:{conn.port}
                    </td>
                    <td>{conn.default_database}</td>
                    <td>{conn.auth_mechanism}</td>
                    <td>
                      <span className={conn.is_active ? "badge badge-ok" : "badge badge-error"}>
                        {conn.is_active ? "active" : "inactive"}
                      </span>
                    </td>
                    <td>
                      <div className="stack" style={{ gap: "0.25rem" }}>
                        <button className="btn btn-sm" onClick={() => handleTest(conn.id)} disabled={testState === "loading"}>
                          {testState === "loading" ? "Testing..." : "Test"}
                        </button>
                        {testState && testState !== "loading" && (
                          <span
                            className={
                              testState === "error"
                                ? "error-text"
                                : testState.success
                                ? "badge badge-ok"
                                : "badge badge-error"
                            }
                            style={{ fontSize: "0.75rem" }}
                          >
                            {testState === "error"
                              ? "Request failed"
                              : `${testState.message}${
                                  testState.databases_visible != null ? ` (${testState.databases_visible} dbs)` : ""
                                }`}
                          </span>
                        )}
                      </div>
                    </td>
                    <td>
                      <div className="stack" style={{ gap: "0.25rem" }}>
                        <div className="row" style={{ gap: "0.4rem" }}>
                          <button
                            className="btn btn-sm btn-primary"
                            onClick={() => handleScan(conn.id)}
                            disabled={scanResults[conn.id] === "loading"}
                            title="Scan this connection's databases/tables/views right now"
                          >
                            {scanResults[conn.id] === "loading" ? "Starting..." : "Scan"}
                          </button>
                          <Link className="btn btn-sm" to={`/connections/${conn.id}/explorer`}>
                            Explore
                          </Link>
                          <Link className="btn btn-sm" to={`/connections/${conn.id}/custom-diagram`}>
                            Custom Diagram
                          </Link>
                          <button className="btn btn-sm btn-danger" onClick={() => handleDelete(conn.id)}>
                            Delete
                          </button>
                        </div>
                        {scanResults[conn.id] && scanResults[conn.id] !== "loading" && (
                          <span className="muted" style={{ fontSize: "0.75rem" }}>
                            {scanResults[conn.id] === "error" ? (
                              <span className="error-text">Failed to start scan</span>
                            ) : (
                              <>
                                Scan started &middot;{" "}
                                <Link to="/scans">watch progress &rarr;</Link>
                              </>
                            )}
                          </span>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
              {connections.length === 0 && (
                <tr>
                  <td colSpan={8} className="muted">
                    No connections yet. Create one below.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>

      <div className="panel stack">
        <h2>New Connection</h2>
        <form className="stack" onSubmit={handleSubmit}>
          <div className="form-grid">
            <label>
              Name
              <input required value={form.name} onChange={(e) => updateField("name", e.target.value)} />
            </label>
            <label>
              Type
              <select
                value={form.conn_type}
                onChange={(e) => updateField("conn_type", e.target.value as ConnectionType)}
              >
                <option value="impala">impala</option>
                <option value="hive_metastore">hive_metastore</option>
              </select>
            </label>
            <label>
              Host
              <input required value={form.host} onChange={(e) => updateField("host", e.target.value)} />
            </label>
            <label>
              Port
              <input
                required
                type="number"
                value={form.port}
                onChange={(e) => updateField("port", Number(e.target.value))}
              />
            </label>
            <label>
              Default Database
              <input
                value={form.default_database}
                onChange={(e) => updateField("default_database", e.target.value)}
              />
            </label>
            <label>
              Auth Mechanism
              <select
                value={form.auth_mechanism}
                onChange={(e) => updateField("auth_mechanism", e.target.value as AuthMechanism)}
              >
                <option value="NOSASL">NOSASL</option>
                <option value="PLAIN">PLAIN</option>
                <option value="LDAP">LDAP</option>
                <option value="KERBEROS">KERBEROS</option>
              </select>
            </label>
            <label>
              Username
              <input value={form.username ?? ""} onChange={(e) => updateField("username", e.target.value)} />
            </label>
            <label>
              Password
              <input
                type="password"
                value={form.password ?? ""}
                onChange={(e) => updateField("password", e.target.value)}
              />
            </label>
          </div>
          {submitError && <p className="error-text">{submitError}</p>}
          <div>
            <button className="btn btn-primary" type="submit" disabled={submitting}>
              {submitting ? "Creating..." : "Create Connection"}
            </button>
          </div>
        </form>
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
