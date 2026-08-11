import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import Connections from "./pages/Connections";
import CustomDiagram from "./pages/CustomDiagram";
import DatabaseDiagram from "./pages/DatabaseDiagram";
import DatabaseExplorer from "./pages/DatabaseExplorer";
import DiagramViewer from "./pages/DiagramViewer";
import ScanJobs from "./pages/ScanJobs";

export default function App() {
  return (
    <div className="app-shell">
      <nav className="app-nav">
        <span className="brand">Impala Lineage</span>
        <NavLink to="/connections" className={({ isActive }) => (isActive ? "active" : "")}>
          Connections
        </NavLink>
        <NavLink to="/scans" className={({ isActive }) => (isActive ? "active" : "")}>
          Scan Jobs
        </NavLink>
      </nav>
      <main className="app-main">
        <Routes>
          <Route path="/" element={<Navigate to="/connections" replace />} />
          <Route path="/connections" element={<Connections />} />
          <Route path="/connections/:connectionId/explorer" element={<DatabaseExplorer />} />
          <Route path="/connections/:connectionId/custom-diagram" element={<CustomDiagram />} />
          <Route path="/connections/:connectionId/databases/:databaseName/diagram" element={<DatabaseDiagram />} />
          <Route path="/diagram/:objectId" element={<DiagramViewer />} />
          <Route path="/scans" element={<ScanJobs />} />
          <Route path="*" element={<Navigate to="/connections" replace />} />
        </Routes>
      </main>
    </div>
  );
}
