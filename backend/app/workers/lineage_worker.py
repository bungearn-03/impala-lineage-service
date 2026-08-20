"""Background job that computes SQL lineage for a connection's scanned views.

For every VIEW with a known ``view_definition``, this:
  1. Runs the deterministic sqlglot-based parser (app.parsers) to get
     table-level lineage and, where possible, column-level lineage.
  2. For any of the view's own output columns that the parser could not
     resolve at all, optionally falls back to the AI-assisted client
     (app.ai) when ``Settings.ai_lineage_fallback_enabled`` and an
     Anthropic API key are configured.
  3. Persists the resulting edges via LineageRepository, replacing any
     previously computed (non-manual) edges into that view.

Only lineage between objects that have already been scanned (i.e. exist as
DataObject rows for this connection) can be persisted, since LineageEdge rows
are foreign-keyed to DataObject/Column -- sources that resolve to identifiers
outside the known schema are skipped and do not fail the job.
"""

from app.ai.ai_client import AnthropicLineageClient
from app.ai.result_validator import validate_ai_edges
from app.core.config import get_settings
from app.core.database import session_scope
from app.core.logging import get_logger
from app.models.connection import Connection
from app.models.data_object import DataObject, ObjectType
from app.parsers.column_lineage import extract_column_lineage
from app.parsers.table_lineage import extract_table_lineage
from app.repositories.job_repository import JobRepository
from app.repositories.lineage_repository import LineageRepository
from app.repositories.object_repository import ObjectRepository
from app.workers import cancellation

logger = get_logger(__name__)


def run_lineage_scan(job_id: str) -> None:
    with session_scope() as db:
        job = JobRepository(db).get(job_id)
        if job is None:
            logger.error("Lineage scan job %s not found", job_id)
            return

        if cancellation.is_cancelled(job_id):
            JobRepository(db).mark_cancelled(job)
            cancellation.clear(job_id)
            return

        connection = db.get(Connection, job.connection_id)
        if connection is None:
            JobRepository(db).mark_failed(job, f"Connection {job.connection_id} not found")
            return

        connection_id = connection.id
        target_database = job.target_database
        JobRepository(db).mark_running(job)

    settings = get_settings()
    ai_client = None
    if settings.ai_lineage_fallback_enabled and settings.anthropic_api_key:
        ai_client = AnthropicLineageClient()

    stats = {
        "views_processed": 0,
        "views_skipped_no_definition": 0,
        "edges_created": 0,
        "ai_fallback_used": 0,
        "ai_fallback_failed": 0,
        "errors": [],
    }
    was_cancelled = False

    try:
        with session_scope() as db:
            obj_repo = ObjectRepository(db)
            objects = obj_repo.list_by_connection(connection_id)
            if target_database:
                objects = [obj for obj in objects if obj.database_name == target_database]

            # Maps to the plain id string, not the DataObject itself: this dict
            # is read later (in `_compute_edges_for_view`) from a different,
            # later-opened session, once this one has committed and closed.
            # session_scope() commits with SQLAlchemy's default
            # expire_on_commit=True, which expires every attribute on these
            # instances -- holding onto the ORM objects themselves would make
            # any later attribute access (e.g. `.id`) try to refresh from a
            # session that's already closed and raise a detached-instance
            # error. A plain str has no such lifecycle.
            by_full_name = {obj.full_name: obj.id for obj in objects}
            schema = {obj.full_name: obj_repo.get_columns_schema(obj) for obj in objects}
            view_ids = [obj.id for obj in objects if obj.object_type == ObjectType.VIEW]

        # Each view is computed and persisted in its own short session so that
        # a cancellation checked between views keeps whatever was already
        # written, instead of holding one long transaction for the whole scan.
        for view_id in view_ids:
            if cancellation.is_cancelled(job_id):
                was_cancelled = True
                break

            with session_scope() as db:
                obj_repo = ObjectRepository(db)
                lineage_repo = LineageRepository(db)
                view = obj_repo.get_by_id(view_id)

                if view is None or not view.view_definition:
                    stats["views_skipped_no_definition"] += 1
                    continue

                try:
                    edges = _compute_edges_for_view(
                        view, by_full_name, schema, obj_repo, ai_client, stats
                    )
                except Exception as exc:  # noqa: BLE001 - one bad view must not abort the scan
                    logger.exception("Lineage computation failed for view %s", view.full_name)
                    stats["errors"].append({"view": view.full_name, "error": str(exc)})
                    continue

                lineage_repo.replace_edges_for_target(view.id, edges)
                stats["edges_created"] += len(edges)
                stats["views_processed"] += 1

        with session_scope() as db:
            job = JobRepository(db).get(job_id)
            if was_cancelled:
                JobRepository(db).mark_cancelled(job, stats)
            else:
                JobRepository(db).mark_success(job, stats)

    except Exception as exc:  # noqa: BLE001 - surface any failure on the job row
        logger.exception("Lineage scan failed for job %s", job_id)
        with session_scope() as db:
            job = JobRepository(db).get(job_id)
            if job is not None:
                JobRepository(db).mark_failed(job, str(exc), stats)
    finally:
        cancellation.clear(job_id)


def _compute_edges_for_view(
    view: DataObject,
    by_full_name: dict[str, str],  # full_name -> DataObject.id
    schema: dict[str, dict],
    obj_repo: ObjectRepository,
    ai_client: AnthropicLineageClient | None,
    stats: dict,
) -> list[dict]:
    sql = view.view_definition
    edges: list[dict] = []

    table_lineage = extract_table_lineage(sql)
    source_full_names = table_lineage["sources"]

    resolved_source_names = [name for name in source_full_names if name in by_full_name]
    for source_name in resolved_source_names:
        source_object_id = by_full_name[source_name]
        edges.append(
            {
                "source_object_id": source_object_id,
                "target_object_id": view.id,
                "source_column_id": None,
                "target_column_id": None,
                "transformation_type": "UNKNOWN",
                "transformation_expr": None,
                "confidence": 1.0,
                "source_sql": sql,
                "created_by": "PARSER",
            }
        )

    target_column_names = [col.name for col in view.columns]
    if not resolved_source_names or not target_column_names:
        return edges

    lineage_schema = {name: schema[name] for name in resolved_source_names}

    try:
        column_edges = extract_column_lineage(sql, target_column_names, lineage_schema)
    except Exception:  # noqa: BLE001 - column lineage is best-effort
        column_edges = []

    columns_with_attempts: set[str] = set()
    for col_edge in column_edges:
        columns_with_attempts.add(col_edge["target_column"])
        source_object_id = by_full_name.get(col_edge["source_table"])
        if source_object_id is None:
            continue
        source_col = obj_repo.get_column_by_name(source_object_id, col_edge["source_column"])
        target_col = obj_repo.get_column_by_name(view.id, col_edge["target_column"])
        if source_col is None or target_col is None:
            continue
        edges.append(
            {
                "source_object_id": source_object_id,
                "target_object_id": view.id,
                "source_column_id": source_col.id,
                "target_column_id": target_col.id,
                "transformation_type": col_edge["transformation_type"],
                "transformation_expr": col_edge.get("transformation_expr"),
                "confidence": 1.0,
                "source_sql": sql,
                "created_by": "PARSER",
            }
        )

    unresolved_targets = [name for name in target_column_names if name not in columns_with_attempts]

    if unresolved_targets and ai_client is not None:
        try:
            ai_response = ai_client.infer_column_lineage(sql, unresolved_targets, lineage_schema)
            validated = validate_ai_edges(ai_response, lineage_schema, unresolved_targets)
            for val_edge in validated:
                source_object_id = by_full_name.get(val_edge["source_table"])
                if source_object_id is None:
                    continue
                source_col = obj_repo.get_column_by_name(source_object_id, val_edge["source_column"])
                target_col = obj_repo.get_column_by_name(view.id, val_edge["target_column"])
                if source_col is None or target_col is None:
                    continue
                edges.append(
                    {
                        "source_object_id": source_object_id,
                        "target_object_id": view.id,
                        "source_column_id": source_col.id,
                        "target_column_id": target_col.id,
                        "transformation_type": val_edge["transformation_type"],
                        "transformation_expr": val_edge.get("transformation_expr"),
                        "confidence": val_edge["confidence"],
                        "source_sql": sql,
                        "created_by": "AI",
                    }
                )
            stats["ai_fallback_used"] += 1
        except Exception as exc:  # noqa: BLE001 - AI fallback failure must not fail the whole scan
            stats["ai_fallback_failed"] += 1
            logger.warning("AI lineage fallback failed for view %s: %s", view.full_name, exc)

    return edges
