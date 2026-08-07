import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  cancelScan,
  createScan,
  getScan,
  listConnections,
  listScans,
  type ConnectionRead,
  type ScanJobRead,
  type ScanJobType,
} from "../services/api";

const POLL_INTERVAL_MS = 4000;

export default function ScanJobs() {
  const [connections, setConnections] = useState<ConnectionRead[]>([]);
  const [filterConnectionId, setFilterConnectionId] = useState<string>("");

  const [jobs, setJobs] = useState<ScanJobRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [form, setForm] = useState<{ connection_id: string; job_type: ScanJobType; target_database: string }>({
    connection_id: "",
    job_type: "METADATA_SCAN",
    target_database: "",
  });
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const jobsRef = useRef<ScanJobRead[]>([]);
  jobsRef.current = jobs;

  useEffect(() => {
    listConnections().then(setConnections).catch(() => setConnections([]));
  }, []);

  async function refresh() {
    setLoading(true);
    setLoadError(null);
    try {
      const data = await listScans(filterConnectionId || undefined);
      setJobs(data);
    } catch (err) {
      setLoadError(describeError(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterConnectionId]);

  // Poll any job still PENDING/RUNNING so status updates without a full
  // page reload. A simple setInterval is sufficient at this scale; a
  // websocket/SSE push would be preferable for a busier production system.
  useEffect(() => {
    const interval = setInterval(async () => {
      const inFlight = jobsRef.current.filter((j) => j.status === "PENDING" || j.status === "RUNNING");
      if (inFlight.length === 0) return;
      try {
        const updates = await Promise.all(inFlight.map((j) => getScan(j.id)));
        setJobs((prev) => {
          const byId = new Map(updates.map((u) => [u.id, u]));
          return prev.map((j) => byId.get(j.id) ?? j);
        });
      } catch {
        // Ignore transient polling errors; next tick will retry.
      }
    }, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, []);

  const [cancellingIds, setCancellingIds] = useState<Set<string>>(new Set());

  async function handleCancel(jobId: string) {
    setCancellingIds((prev) => new Set(prev).add(jobId));
    try {
      const updated = await cancelScan(jobId);
      setJobs((prev) => prev.map((j) => (j.id === updated.id ? updated : j)));
    } catch {
      // Ignore -- the next poll tick will reflect whatever the real state is.
    } finally {
      setCancellingIds((prev) => {
        const next = new Set(prev);
        next.delete(jobId);
        return next;
      });
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!form.connection_id) {
      setSubmitError("Select a connection.");
      return;
    }
    setSubmitting(true);
    setSubmitError(null);
    try {
      await createScan({
        connection_id: form.connection_id,
        job_type: form.job_type,
        target_database: form.target_database || undefined,
      });
      setForm((prev) => ({ ...prev, target_database: "" }));
      await refresh();
    } catch (err) {
      setSubmitError(describeError(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="stack">
      <h1>Scan Jobs</h1>

      <div className="panel row" style={{ alignItems: "flex-end" }}>
        <label>
          Filter by connection
          <select value={filterConnectionId} onChange={(e) => setFilterConnectionId(e.target.value)}>
            <option value="">All connections</option>
            {connections.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <button className="btn" onClick={refresh}>
          Refresh
        </button>
      </div>

      <div className="panel">
        {loading && <p className="muted">Loading scan jobs...</p>}
        {loadError && <p className="error-text">{loadError}</p>}
        {!loading && !loadError && (
          <table>
            <thead>
              <tr>
                <th>Connection</th>
                <th>Type</th>
                <th>Status</th>
                <th>Target DB</th>
                <th>Created</th>
                <th>Finished</th>
                <th>Error</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => {
                const cancellable = job.status === "PENDING" || job.status === "RUNNING";
                const cancelling = cancellingIds.has(job.id);
                return (
                  <tr key={job.id}>
                    <td>{connectionName(connections, job.connection_id)}</td>
                    <td>{job.job_type}</td>
                    <td>
                      <span className={statusBadgeClass(job.status)}>{job.status}</span>
                    </td>
                    <td>{job.target_database ?? "*"}</td>
                    <td>{new Date(job.created_at).toLocaleString()}</td>
                    <td>{job.finished_at ? new Date(job.finished_at).toLocaleString() : "-"}</td>
                    <td className="error-text">{job.error_message ?? ""}</td>
                    <td>
                      {cancellable && (
                        <button
                          className="btn btn-sm btn-danger"
                          onClick={() => handleCancel(job.id)}
                          disabled={cancelling}
                        >
                          {cancelling ? "Cancelling..." : "Cancel"}
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
              {jobs.length === 0 && (
                <tr>
                  <td colSpan={8} className="muted">
                    No scan jobs found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>

      <div className="panel stack">
        <h2>Trigger New Scan</h2>
        <form className="stack" onSubmit={handleSubmit}>
          <div className="form-grid">
            <label>
              Connection
              <select
                required
                value={form.connection_id}
                onChange={(e) => setForm((prev) => ({ ...prev, connection_id: e.target.value }))}
              >
                <option value="">Select a connection...</option>
                {connections.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Job Type
              <select
                value={form.job_type}
                onChange={(e) => setForm((prev) => ({ ...prev, job_type: e.target.value as ScanJobType }))}
              >
                <option value="METADATA_SCAN">METADATA_SCAN</option>
                <option value="LINEAGE_SCAN">LINEAGE_SCAN</option>
              </select>
            </label>
            <label>
              Target Database (optional)
              <input
                value={form.target_database}
                onChange={(e) => setForm((prev) => ({ ...prev, target_database: e.target.value }))}
                placeholder="all databases if empty"
              />
            </label>
          </div>
          {submitError && <p className="error-text">{submitError}</p>}
          <div>
            <button className="btn btn-primary" type="submit" disabled={submitting}>
              {submitting ? "Submitting..." : "Start Scan"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function connectionName(connections: ConnectionRead[], id: string): string {
  return connections.find((c) => c.id === id)?.name ?? id;
}

function statusBadgeClass(status: ScanJobRead["status"]): string {
  switch (status) {
    case "PENDING":
      return "badge badge-status-pending";
    case "RUNNING":
      return "badge badge-status-running";
    case "SUCCESS":
      return "badge badge-status-success";
    case "FAILED":
      return "badge badge-status-failed";
    case "CANCELLED":
      return "badge badge-status-cancelled";
    default:
      return "badge";
  }
}

function describeError(err: unknown): string {
  if (err && typeof err === "object" && "message" in err) {
    return String((err as { message: unknown }).message);
  }
  return "Something went wrong.";
}
