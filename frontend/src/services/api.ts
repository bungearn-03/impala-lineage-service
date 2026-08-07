import axios, { type InternalAxiosRequestConfig } from "axios";

// ---------------------------------------------------------------------------
// Axios client
// ---------------------------------------------------------------------------

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";
const API_KEY = import.meta.env.VITE_API_KEY;

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
});

apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  if (API_KEY) {
    config.headers.set("X-API-Key", API_KEY);
  }
  return config;
});

// ---------------------------------------------------------------------------
// Shared enum-ish types (mirrors backend enums exactly)
// ---------------------------------------------------------------------------

export type ConnectionType = "impala" | "hive_metastore";
export type AuthMechanism = "NOSASL" | "PLAIN" | "LDAP" | "KERBEROS";
export type ObjectType = "TABLE" | "VIEW";
export type ScanJobType = "METADATA_SCAN" | "LINEAGE_SCAN";
export type ScanJobStatus = "PENDING" | "RUNNING" | "SUCCESS" | "FAILED" | "CANCELLED";
export type TransformationType = "DIRECT" | "DERIVED" | "AGGREGATED" | "JOIN" | "UNKNOWN";
export type LineageSource = "PARSER" | "AI" | "MANUAL";
export type LineageDirection = "upstream" | "downstream" | "both";
export type DiagramGranularity = "table" | "column";

// ---------------------------------------------------------------------------
// Connections
// ---------------------------------------------------------------------------

export interface ConnectionRead {
  id: string;
  name: string;
  conn_type: ConnectionType;
  host: string;
  port: number;
  default_database: string;
  auth_mechanism: AuthMechanism;
  username: string | null;
  use_ssl: boolean;
  extra_params: Record<string, unknown>;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ConnectionCreate {
  name: string;
  conn_type: ConnectionType;
  host: string;
  port: number;
  default_database?: string;
  auth_mechanism?: AuthMechanism;
  username?: string | null;
  password?: string | null;
  use_ssl?: boolean;
  extra_params?: Record<string, unknown>;
}

export interface ConnectionUpdate {
  name?: string;
  host?: string;
  port?: number;
  default_database?: string;
  auth_mechanism?: AuthMechanism;
  username?: string | null;
  password?: string | null;
  use_ssl?: boolean;
  extra_params?: Record<string, unknown>;
  is_active?: boolean;
}

export interface ConnectionTestResult {
  success: boolean;
  message: string;
  databases_visible?: number;
}

// ---------------------------------------------------------------------------
// Metadata (databases / objects / columns)
// ---------------------------------------------------------------------------

export interface DatabaseSummary {
  database_name: string;
  table_count: number;
  view_count: number;
}

export interface DataObjectSummary {
  id: string;
  connection_id: string;
  database_name: string;
  object_name: string;
  object_type: ObjectType;
  last_scanned_at: string | null;
}

export interface ColumnRead {
  id: string;
  name: string;
  data_type: string;
  ordinal_position: number;
  is_nullable: boolean;
}

export interface DataObjectDetail extends DataObjectSummary {
  ddl: string | null;
  view_definition: string | null;
  columns: ColumnRead[];
}

// ---------------------------------------------------------------------------
// Scans
// ---------------------------------------------------------------------------

export interface ScanJobCreate {
  connection_id: string;
  job_type: ScanJobType;
  target_database?: string;
}

export interface ScanJobRead {
  id: string;
  connection_id: string;
  job_type: ScanJobType;
  status: ScanJobStatus;
  target_database: string | null;
  error_message: string | null;
  stats: Record<string, unknown>;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

// ---------------------------------------------------------------------------
// Lineage
// ---------------------------------------------------------------------------

export interface LineageEndpoint {
  object_id: string;
  object_full_name: string;
  column_id?: string | null;
  column_name?: string | null;
}

export interface LineageEdgeRead {
  id: string;
  source: LineageEndpoint;
  target: LineageEndpoint;
  transformation_type: TransformationType;
  transformation_expr: string | null;
  confidence: number;
  source_sql: string | null;
  created_by: LineageSource;
  created_at: string;
}

export interface LineageQueryParams {
  direction?: LineageDirection;
  depth?: number;
  column_name?: string;
}

// ---------------------------------------------------------------------------
// Diagrams (cytoscape.js-shaped)
// ---------------------------------------------------------------------------

export interface CytoscapeNodeData {
  id: string;
  label: string;
  type: "object" | "column";
  object_type?: ObjectType;
  database_name?: string;
  parent?: string;
}

export interface CytoscapeEdgeData {
  id: string;
  source: string;
  target: string;
  label?: string;
  transformation_type?: TransformationType;
  confidence?: number;
}

export interface CytoscapeElement {
  group: "nodes" | "edges";
  data: CytoscapeNodeData | CytoscapeEdgeData;
}

export interface DiagramResponse {
  elements: CytoscapeElement[];
  node_count: number;
  edge_count: number;
  truncated: boolean;
}

export interface DiagramQueryParams {
  direction?: LineageDirection;
  depth?: number;
  granularity?: DiagramGranularity;
}

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------

export interface HealthResponse {
  status: string;
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

export async function listConnections(): Promise<ConnectionRead[]> {
  const res = await apiClient.get<ConnectionRead[]>("/connections");
  return res.data;
}

export async function createConnection(data: ConnectionCreate): Promise<ConnectionRead> {
  const res = await apiClient.post<ConnectionRead>("/connections", data);
  return res.data;
}

export async function getConnection(id: string): Promise<ConnectionRead> {
  const res = await apiClient.get<ConnectionRead>(`/connections/${id}`);
  return res.data;
}

export async function updateConnection(id: string, data: ConnectionUpdate): Promise<ConnectionRead> {
  const res = await apiClient.put<ConnectionRead>(`/connections/${id}`, data);
  return res.data;
}

export async function deleteConnection(id: string): Promise<void> {
  await apiClient.delete(`/connections/${id}`);
}

export async function testConnection(id: string): Promise<ConnectionTestResult> {
  const res = await apiClient.post<ConnectionTestResult>(`/connections/${id}/test`);
  return res.data;
}

export async function listDatabases(connectionId: string): Promise<DatabaseSummary[]> {
  const res = await apiClient.get<DatabaseSummary[]>(`/connections/${connectionId}/databases`);
  return res.data;
}

export async function listObjects(connectionId: string, db: string): Promise<DataObjectSummary[]> {
  const res = await apiClient.get<DataObjectSummary[]>(
    `/connections/${connectionId}/databases/${encodeURIComponent(db)}/objects`
  );
  return res.data;
}

export async function getObject(objectId: string): Promise<DataObjectDetail> {
  const res = await apiClient.get<DataObjectDetail>(`/objects/${objectId}`);
  return res.data;
}

export async function createScan(data: ScanJobCreate): Promise<ScanJobRead> {
  const res = await apiClient.post<ScanJobRead>("/scans", data);
  return res.data;
}

export async function listScans(connectionId?: string): Promise<ScanJobRead[]> {
  const res = await apiClient.get<ScanJobRead[]>("/scans", {
    params: connectionId ? { connection_id: connectionId } : undefined,
  });
  return res.data;
}

export async function getScan(id: string): Promise<ScanJobRead> {
  const res = await apiClient.get<ScanJobRead>(`/scans/${id}`);
  return res.data;
}

export async function cancelScan(id: string): Promise<ScanJobRead> {
  const res = await apiClient.post<ScanJobRead>(`/scans/${id}/cancel`);
  return res.data;
}

export async function getLineage(
  objectId: string,
  params: LineageQueryParams = {}
): Promise<LineageEdgeRead[]> {
  const res = await apiClient.get<LineageEdgeRead[]>(`/lineage/objects/${objectId}`, {
    params: {
      direction: params.direction ?? "both",
      depth: params.depth ?? 3,
      column_name: params.column_name,
    },
  });
  return res.data;
}

export async function getDiagram(
  objectId: string,
  params: DiagramQueryParams = {}
): Promise<DiagramResponse> {
  const res = await apiClient.get<DiagramResponse>(`/diagrams/objects/${objectId}`, {
    params: {
      direction: params.direction ?? "both",
      depth: params.depth ?? 3,
      granularity: params.granularity ?? "table",
    },
  });
  return res.data;
}

export async function getDatabaseDiagram(connectionId: string, databaseName: string): Promise<DiagramResponse> {
  const res = await apiClient.get<DiagramResponse>(
    `/diagrams/databases/${connectionId}/${encodeURIComponent(databaseName)}`
  );
  return res.data;
}

// ---------------------------------------------------------------------------
// DR (Data Relationship) diagram -- DBeaver-style ER diagram data: real
// table/column metadata plus foreign-key-style relationships inferred from
// parsing views' JOIN conditions (distinct from the lineage-based diagrams
// above, which show data *provenance* rather than schema relationships).
// ---------------------------------------------------------------------------

export interface DrColumn {
  name: string;
  type: string;
  is_key: boolean;
  description: string;
}

export interface DrTable {
  name: string;
  object_type: "TABLE" | "VIEW";
  columns: DrColumn[];
}

export interface DrRelationship {
  from_table: string;
  from_col: string;
  to_table: string;
  to_col: string;
  via_view: string;
  relationship_type: "JOIN" | "VIEW_SOURCE";
}

export interface DrDiagramResponse {
  database: string;
  tables: Record<string, DrTable>;
  relationships: DrRelationship[];
  table_count: number;
  view_count: number;
  relationship_count: number;
}

export async function getDrDiagram(connectionId: string, databaseName: string): Promise<DrDiagramResponse> {
  const res = await apiClient.get<DrDiagramResponse>(
    `/diagrams/dr/${connectionId}/${encodeURIComponent(databaseName)}`
  );
  return res.data;
}

export async function getHealth(): Promise<HealthResponse> {
  const res = await apiClient.get<HealthResponse>("/health");
  return res.data;
}
