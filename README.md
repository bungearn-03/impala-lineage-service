# Impala Lineage Service

A service for scanning Impala / Hive Metastore metadata and reconstructing
SQL lineage (table-level and column-level) from view/query definitions, with
a web UI for browsing scanned databases and visualizing lineage as a graph.

It connects to Impala and/or the Hive Metastore, discovers databases, tables
and views, parses the SQL behind views to derive lineage edges (falling back
to an AI-assisted pass when static parsing can't confidently resolve a
column), and stores the result in Postgres for the frontend to query and
render as an interactive diagram.

## Architecture

The FastAPI backend (`backend/app/`) is organized into layers, each with a
narrow, single-purpose responsibility:

- **`connectors/`** - `BaseConnector` defines the interface (`list_databases`,
  `list_objects`, `get_columns`, `get_ddl`, `get_view_definition`, ...)
  implemented by `ImpalaConnector` and `HiveMetastoreConnector`, so the rest
  of the app can talk to either backend interchangeably without caring which
  one is configured on a given `Connection`.
- **`metadata/`** - loaders that drive a connector to discover objects,
  columns, and view definitions and persist them as `DataObject`/`Column`
  rows (`object_scanner.py`, `schema_loader.py`, `view_definition_loader.py`).
- **`parsers/`** - static SQL analysis built on `sqlglot`: normalizes
  dialect quirks (`sql_normalizer.py`), resolves table-level
  (`table_lineage.py`) and column-level (`column_lineage.py`) lineage,
  extracts join graphs (`join_extractor.py`), and recursively expands
  lineage through nested views (`recursive_resolver.py`).
- **`ai/`** - a thin, isolated wrapper around the Anthropic SDK
  (`ai_client.py`, `prompts.py`, `response_schema.py`, `result_validator.py`)
  used only as a fallback when the sqlglot-based parser can't confidently
  resolve column lineage. Disabled entirely unless `ANTHROPIC_API_KEY` is set.
- **`graph/`** - turns persisted lineage edges into `networkx` graphs and
  formats them for the frontend's Cytoscape.js viewer (`graph_builder.py`,
  `graph_filter.py`, `cytoscape_formatter.py`); deliberately decoupled from
  the ORM and Pydantic schemas so it can be unit tested with plain dicts.
- **`repositories/`** - the only layer that talks to SQLAlchemy directly:
  `object_repository.py` (DataObject/Column upserts), `lineage_repository.py`
  (LineageEdge persistence + raw-dict shaping for `graph/`), `job_repository.py`
  (ScanJob lifecycle).
- **`workers/`** - background execution of scan jobs, invoked via FastAPI's
  `BackgroundTasks` so long-running Impala/Metastore scans don't block API
  requests: `scan_worker.py` (metadata scans) and `lineage_worker.py`
  (lineage scans, including the AI fallback decision per view).
- **`api/`** - the FastAPI routers exposing connections, metadata, scan
  jobs, and lineage/diagram endpoints under `/api/v1`, wired together in
  `app/main.py`.

The Vite/React frontend (`frontend/`) is a separate, already-built
single-page app that talks to the backend over its `/api/v1` HTTP API and
renders the lineage graph with Cytoscape.js.

## Directory layout

```
impala-lineage-service/
├── backend/
│   ├── app/
│   │   ├── ai/             # Anthropic-backed lineage fallback
│   │   ├── api/             # FastAPI routers (/api/v1/...)
│   │   ├── connectors/     # Impala / Hive Metastore clients
│   │   ├── core/           # config, database session, security, logging
│   │   ├── graph/          # lineage graph construction & formatting
│   │   ├── metadata/       # metadata scanning/loading
│   │   ├── models/         # SQLAlchemy models (mirrored by the Alembic migration)
│   │   ├── parsers/        # sqlglot-based SQL lineage parsing
│   │   ├── repositories/    # SQLAlchemy query layer
│   │   ├── schemas/        # Pydantic request/response schemas
│   │   ├── workers/         # background scan/lineage jobs
│   │   └── main.py          # FastAPI app assembly
│   ├── scripts/
│   │   └── seed_connections.py  # register a Connection from IMPALA_* env vars
│   ├── tests/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── .env.example        # copy to .env
├── database/
│   └── migrations/         # Alembic environment (sibling of backend/, not inside it)
│       ├── alembic.ini
│       ├── env.py
│       ├── script.py.mako
│       └── versions/
│           └── 0001_initial_schema.py
├── frontend/                # Vite/React SPA (own Dockerfile, not covered here)
├── docker-compose.yml
└── README.md
```

## Local setup

### 1. Configure the backend environment

```bash
# from the repo root
cp backend/.env.example backend/.env
```

```powershell
# PowerShell equivalent
Copy-Item backend\.env.example backend\.env
```

Edit `backend/.env` and fill in real values, at minimum `SECRET_KEY`. Set
`ANTHROPIC_API_KEY` if you want the AI-assisted lineage fallback available
(see note below).

### 2. Start Postgres only

```bash
docker compose up -d postgres
```

```powershell
docker compose up -d postgres
```

Wait for it to report healthy (`docker compose ps`).

### 3. Run the initial migration

The Alembic environment lives in `database/migrations/`, a sibling of
`backend/`, so `env.py` puts `backend/` on `sys.path` itself - you don't need
to install the `app` package. You do need the same Python dependencies
installed (at least `alembic` and everything `app.core.config`/`app.models`
import), and `DATABASE_URL` reachable from wherever you run this command
(`localhost:5432` if you're running it directly on the host against the
`postgres` container's published port, which is what `backend/.env.example`
defaults to).

From the `backend/` directory, with a virtualenv containing
`backend/requirements.txt` installed:

```bash
# from backend/
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic -c ../database/migrations/alembic.ini upgrade head
```

```powershell
# from backend/
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic -c ..\database\migrations\alembic.ini upgrade head
```

`env.py` reads `DATABASE_URL` via `app.core.config.get_settings()` (i.e. from
`backend/.env` or your real process environment) - `alembic.ini`'s own
`sqlalchemy.url` is intentionally left blank.

> This project does not run migrations automatically from the backend
> container's entrypoint. `database/migrations` is mounted read-only into the
> `backend` container at `/migrations` for convenience, so you can also run
> the same command inside the running container instead of a local venv:
> `docker compose exec backend alembic -c /migrations/alembic.ini upgrade head`
> (either way works; a manual step was chosen over baking it into `CMD` so
> that container restarts never silently re-run migrations, and so a
> migration failure doesn't crash the API process).

### 4. Bring everything up

```bash
docker compose up --build
```

```powershell
docker compose up --build
```

- Backend: http://localhost:9000
- Frontend: http://localhost:5173

> **Frontend API URL is baked in at build time.** `VITE_API_BASE_URL` is a
> Vite build-time variable, not a runtime one - the `frontend` service's
> Dockerfile compiles it into the static JS bundle. `docker-compose.yml`
> passes it as a build arg (`http://localhost:9000/api/v1`, matching the
> backend's host port mapping above) so `docker compose up --build` picks it
> up automatically. If you change the backend's host port again, update that
> build arg too and rebuild with `docker compose build --build-arg
> VITE_API_BASE_URL=... frontend` - setting it as a container environment
> variable at `docker compose up` time has no effect on an already-built
> bundle.

### 5. (Optional) Seed a real Impala connection

Rather than adding your first `Connection` by hand through the API/UI, you
can set `IMPALA_HOST`/`IMPALA_PORT`/`IMPALA_USER`/`IMPALA_PASS` (and
optionally `IMPALA_CONNECTION_NAME`/`IMPALA_DEFAULT_DATABASE`/
`IMPALA_AUTH_MECHANISM`/`IMPALA_USE_SSL`) in `backend/.env` and run:

```bash
# from backend/, with the venv from step 3 active
python scripts/seed_connections.py
```

```powershell
python scripts\seed_connections.py
```

This is idempotent (re-running it updates the existing row by
`IMPALA_CONNECTION_NAME` instead of duplicating it) and encrypts the
password the same way the API does before storing it. It only reads
`IMPALA_*` variables - it never appears in git history or `.env.example`
with real values, since `backend/.env` is git-ignored.

## Key environment variables

All of these are read by `backend/app/core/config.py::Settings` from
`backend/.env` (see `backend/.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg2://lineage:lineage@localhost:5432/lineage` | SQLAlchemy connection string. Overridden in `docker-compose.yml` to target the `postgres` service hostname. |
| `SECRET_KEY` | *(dev placeholder, change in prod)* | Derives the Fernet key used to encrypt stored connection credentials. |
| `API_KEY` | *(none)* | If set, all API requests must send it in the `X-API-Key` header. |
| `CORS_ORIGINS` | `["http://localhost:5173"]` | JSON array of allowed frontend origins. |
| `ANTHROPIC_API_KEY` | *(none)* | Enables the AI-assisted lineage fallback. See note below. |
| `ANTHROPIC_MODEL` | `claude-sonnet-5` | Model used for the AI lineage fallback. |
| `AI_LINEAGE_FALLBACK_ENABLED` | `true` | Master switch for the fallback; still requires `ANTHROPIC_API_KEY`. |
| `DEFAULT_QUERY_TIMEOUT_SECONDS` | `120` | Timeout applied to Impala/Metastore queries during scans. |
| `SCAN_MAX_CONCURRENT_OBJECTS` | `8` | Max objects scanned concurrently per scan job. |
| `APP_NAME`, `ENVIRONMENT`, `LOG_LEVEL` | | General app metadata / logging. |

### AI-assisted lineage fallback

When the static `sqlglot`-based parser can't confidently resolve
column-level lineage for a view, the service can optionally make a single
tool-use call to Claude to fill in the gap. This is **entirely optional**:
if `ANTHROPIC_API_KEY` is not set, the fallback is silently skipped (not an
error) regardless of `AI_LINEAGE_FALLBACK_ENABLED` - lineage resolution just
stops at whatever the static parser could determine.

## Notes / deviations from a literal reading of the spec

- The Alembic migration hand-encodes the exact runtime behavior of
  SQLAlchemy's `Enum(SomePyEnum)` column type: by default it persists the
  Python enum member's **name**, not its `.value`. This only matters for
  `ConnectionType` (`IMPALA`/`HIVE_METASTORE` are the persisted values, not
  the lowercase `impala`/`hive_metastore` `.value`s) - every other enum's
  name and value happen to be identical strings. All seven Postgres enum
  types are created with explicit `create_type=False` and are
  created/dropped explicitly in `upgrade()`/`downgrade()` to avoid
  duplicate-type errors.
- `backend`'s `docker-compose.yml` service does not have a `healthcheck`, so
  `frontend`'s `depends_on: backend` only waits for the container to start,
  not for the API to be ready to serve requests.
