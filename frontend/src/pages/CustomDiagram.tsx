import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import ERDiagram from "../components/ERDiagram";
import {
  createCustomDiagramPreset,
  deleteCustomDiagramPreset,
  getConnection,
  getCustomDrDiagram,
  listAllObjects,
  listCustomDiagramPresets,
  type ConnectionRead,
  type CustomDiagramPresetRead,
  type DataObjectSummary,
  type DrDiagramResponse,
} from "../services/api";

export default function CustomDiagram() {
  const { connectionId } = useParams<{ connectionId: string }>();

  const [connection, setConnection] = useState<ConnectionRead | null>(null);

  const [allObjects, setAllObjects] = useState<DataObjectSummary[]>([]);
  const [objectsLoading, setObjectsLoading] = useState(true);
  const [objectsError, setObjectsError] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [activePresetId, setActivePresetId] = useState<string | null>(null);

  const [presets, setPresets] = useState<CustomDiagramPresetRead[]>([]);
  const [presetsLoading, setPresetsLoading] = useState(true);
  const [presetsError, setPresetsError] = useState<string | null>(null);
  const [newPresetName, setNewPresetName] = useState("");
  const [savingPreset, setSavingPreset] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const [diagramData, setDiagramData] = useState<DrDiagramResponse | null>(null);
  const [diagramLoading, setDiagramLoading] = useState(false);
  const [diagramError, setDiagramError] = useState<string | null>(null);

  useEffect(() => {
    if (!connectionId) return;
    getConnection(connectionId).catch(() => setConnection(null)).then((c) => c && setConnection(c));
  }, [connectionId]);

  useEffect(() => {
    if (!connectionId) return;
    setObjectsLoading(true);
    setObjectsError(null);
    listAllObjects(connectionId)
      .then(setAllObjects)
      .catch((err) => setObjectsError(describeError(err)))
      .finally(() => setObjectsLoading(false));
  }, [connectionId]);

  function reloadPresets() {
    if (!connectionId) return;
    setPresetsLoading(true);
    setPresetsError(null);
    listCustomDiagramPresets(connectionId)
      .then(setPresets)
      .catch((err) => setPresetsError(describeError(err)))
      .finally(() => setPresetsLoading(false));
  }

  useEffect(reloadPresets, [connectionId]);

  const objectById = useMemo(() => {
    const map = new Map<string, DataObjectSummary>();
    allObjects.forEach((o) => map.set(o.id, o));
    return map;
  }, [allObjects]);

  const groupedObjects = useMemo(() => {
    const q = search.trim().toLowerCase();
    const filtered = q
      ? allObjects.filter(
          (o) => o.object_name.toLowerCase().includes(q) || o.database_name.toLowerCase().includes(q)
        )
      : allObjects;
    const byDb = new Map<string, DataObjectSummary[]>();
    for (const obj of filtered) {
      const bucket = byDb.get(obj.database_name);
      if (bucket) bucket.push(obj);
      else byDb.set(obj.database_name, [obj]);
    }
    return [...byDb.entries()]
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([dbName, objs]) => [dbName, objs.sort((a, b) => a.object_name.localeCompare(b.object_name))] as const);
  }, [allObjects, search]);

  function toggle(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
    setActivePresetId(null);
  }

  function clearSelection() {
    setSelectedIds(new Set());
    setActivePresetId(null);
    setNewPresetName("");
  }

  function loadPreset(preset: CustomDiagramPresetRead) {
    setSelectedIds(new Set(preset.object_ids));
    setActivePresetId(preset.id);
    setNewPresetName(preset.name);
    generateDiagram(preset.object_ids);
  }

  async function handleDeletePreset(preset: CustomDiagramPresetRead) {
    if (!connectionId) return;
    if (!window.confirm(`Delete preset "${preset.name}"?`)) return;
    await deleteCustomDiagramPreset(connectionId, preset.id);
    if (activePresetId === preset.id) setActivePresetId(null);
    reloadPresets();
  }

  async function handleSavePreset() {
    if (!connectionId || selectedIds.size === 0 || !newPresetName.trim()) return;
    setSavingPreset(true);
    setSaveError(null);
    try {
      const preset = await createCustomDiagramPreset(connectionId, newPresetName.trim(), [...selectedIds]);
      setActivePresetId(preset.id);
      reloadPresets();
    } catch (err) {
      setSaveError(describeError(err));
    } finally {
      setSavingPreset(false);
    }
  }

  function generateDiagram(ids: string[] = [...selectedIds]) {
    if (ids.length === 0) return;
    setDiagramLoading(true);
    setDiagramError(null);
    getCustomDrDiagram(ids)
      .then(setDiagramData)
      .catch((err) => setDiagramError(describeError(err)))
      .finally(() => setDiagramLoading(false));
  }

  const selectedObjects = [...selectedIds].map((id) => objectById.get(id)).filter(Boolean) as DataObjectSummary[];
  const selectedDbCount = new Set(selectedObjects.map((o) => o.database_name)).size;

  return (
    <div className="stack">
      <h1>Custom Diagram</h1>
      <p className="muted">
        Connection <strong>{connection?.name ?? connectionId}</strong> &middot; pick any tables/views from
        any database on this connection and view them together as one ER diagram &middot;{" "}
        {connectionId ? (
          <Link to={`/connections/${connectionId}/explorer`}>back to explorer</Link>
        ) : (
          <Link to="/connections">back to connections</Link>
        )}
      </p>

      <div className="sidebar-layout">
        <div className="panel">
          <h3>Saved presets</h3>
          {presetsLoading && <p className="muted">Loading...</p>}
          {presetsError && <p className="error-text">{presetsError}</p>}
          {!presetsLoading && !presetsError && presets.length === 0 && (
            <p className="muted" style={{ fontSize: "0.85rem" }}>
              No saved presets yet. Pick some tables, then save the selection below.
            </p>
          )}
          {!presetsLoading && !presetsError && presets.length > 0 && (
            <ul className="list-reset stack" style={{ gap: "0.4rem" }}>
              {presets.map((preset) => (
                <li
                  key={preset.id}
                  className={`db-card ${activePresetId === preset.id ? "selected" : ""}`}
                >
                  <button className="db-card-main" onClick={() => loadPreset(preset)}>
                    <span>{preset.name}</span>
                    <span className="db-card-counts">{preset.object_ids.length} objects</span>
                  </button>
                  <button
                    className="db-card-diagram-link danger"
                    style={{ color: "var(--color-danger)" }}
                    onClick={() => handleDeletePreset(preset)}
                  >
                    Delete
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="stack">
          <div className="panel">
            <h3>Pick tables/views</h3>
            {objectsLoading && <p className="muted">Loading objects...</p>}
            {objectsError && <p className="error-text">{objectsError}</p>}
            {!objectsLoading && !objectsError && (
              <>
                <div className="panel-toolbar">
                  <input
                    className="search-input"
                    type="text"
                    placeholder="Search by table/view or database name..."
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                  />
                  <span className="panel-count">{selectedIds.size} selected</span>
                </div>

                <div className="db-list-scroll" style={{ maxHeight: "calc(100vh - 560px)" }}>
                  {groupedObjects.map(([dbName, objs]) => (
                    <div key={dbName} style={{ marginBottom: "0.75rem" }}>
                      <div
                        className="muted"
                        style={{ fontWeight: 700, fontSize: "0.78rem", margin: "0.4rem 0" }}
                      >
                        {dbName}
                      </div>
                      <div className="stack" style={{ gap: "0.3rem" }}>
                        {objs.map((obj) => (
                          <label key={obj.id} className="er-toggle">
                            <input
                              type="checkbox"
                              checked={selectedIds.has(obj.id)}
                              onChange={() => toggle(obj.id)}
                            />
                            <span>{obj.object_name}</span>
                            <span
                              className={
                                obj.object_type === "TABLE" ? "badge badge-object-table" : "badge badge-object-view"
                              }
                            >
                              {obj.object_type}
                            </span>
                          </label>
                        ))}
                      </div>
                    </div>
                  ))}
                  {groupedObjects.length === 0 && (
                    <p className="muted">No tables or views match &ldquo;{search}&rdquo;.</p>
                  )}
                </div>

                <div className="row" style={{ gap: "0.5rem", alignItems: "center", marginTop: "0.85rem" }}>
                  <button
                    className="btn btn-sm btn-primary"
                    disabled={selectedIds.size === 0}
                    onClick={() => generateDiagram()}
                  >
                    Generate Diagram
                  </button>
                  <button className="btn btn-sm" disabled={selectedIds.size === 0} onClick={clearSelection}>
                    Clear selection
                  </button>
                  {selectedIds.size > 0 && (
                    <span className="muted" style={{ fontSize: "0.8rem" }}>
                      {selectedIds.size} objects across {selectedDbCount} database
                      {selectedDbCount === 1 ? "" : "s"}
                    </span>
                  )}
                </div>

                <div className="row" style={{ gap: "0.5rem", alignItems: "center", marginTop: "0.6rem" }}>
                  <input
                    type="text"
                    placeholder="Preset name..."
                    value={newPresetName}
                    onChange={(e) => setNewPresetName(e.target.value)}
                    style={{ flex: 1, minWidth: 0 }}
                  />
                  <button
                    className="btn btn-sm"
                    disabled={selectedIds.size === 0 || !newPresetName.trim() || savingPreset}
                    onClick={handleSavePreset}
                  >
                    {savingPreset ? "Saving..." : "Save as preset"}
                  </button>
                </div>
                {saveError && <p className="error-text">{saveError}</p>}
              </>
            )}
          </div>

          {diagramLoading && (
            <div className="panel">
              <p className="muted">Building diagram...</p>
            </div>
          )}
          {diagramError && (
            <div className="panel">
              <p className="error-text">{diagramError}</p>
            </div>
          )}
          {!diagramLoading && !diagramError && diagramData && <ERDiagram data={diagramData} />}
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
