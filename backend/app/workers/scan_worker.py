"""Background job that scans a connection's Impala/Hive metadata and persists it.

Runs outside the FastAPI request/response cycle (invoked via BackgroundTasks
from app.api.scans), so it manages its own short-lived DB sessions via
``session_scope`` rather than relying on the request-scoped ``get_db``
dependency.

Cancellation: checked (via app.workers.cancellation) between each database
and, within ``scan_database``, between each object -- so a cancel request
lands within one object's metadata fetch rather than only after the whole
current database finishes. Results are persisted incrementally per-database
rather than all at once at the end, so a cancelled/crashed scan keeps
whatever it already finished instead of losing all progress.
"""

from app.connectors import get_connector
from app.core.database import session_scope
from app.core.logging import get_logger
from app.metadata.object_scanner import scan_database
from app.models.connection import Connection
from app.repositories.job_repository import JobRepository
from app.repositories.object_repository import ObjectRepository
from app.workers import cancellation

logger = get_logger(__name__)

# When no target_database is given, a scan job covers every database on the
# connection by default - restrict that "scan everything" mode to the ll_
# databases this service actually cares about instead of the whole cluster.
DATABASE_NAME_PREFIX = "ll_"


def run_metadata_scan(job_id: str) -> None:
    with session_scope() as db:
        job = JobRepository(db).get(job_id)
        if job is None:
            logger.error("Metadata scan job %s not found", job_id)
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
        connector = get_connector(connection)

    stats = {
        "databases_scanned": 0,
        "objects_scanned": 0,
        "objects_skipped": 0,
        "skipped_details": [],
    }
    was_cancelled = False

    try:
        database_names = (
            [target_database]
            if target_database
            else [name for name in connector.list_databases() if name.startswith(DATABASE_NAME_PREFIX)]
        )

        for database_name in database_names:
            if cancellation.is_cancelled(job_id):
                was_cancelled = True
                break

            scan_result = scan_database(
                connector, database_name, cancel_check=lambda: cancellation.is_cancelled(job_id)
            )

            with session_scope() as db:
                repo = ObjectRepository(db)
                for obj_metadata in scan_result.objects:
                    repo.upsert_object(connection_id, obj_metadata)
                    stats["objects_scanned"] += 1
                for object_name, error_message in scan_result.skipped:
                    stats["objects_skipped"] += 1
                    stats["skipped_details"].append(
                        {"database": database_name, "object": object_name, "error": error_message}
                    )
            stats["databases_scanned"] += 1

        with session_scope() as db:
            job = JobRepository(db).get(job_id)
            if was_cancelled:
                JobRepository(db).mark_cancelled(job, stats)
            else:
                JobRepository(db).mark_success(job, stats)

    except Exception as exc:  # noqa: BLE001 - surface any failure on the job row
        logger.exception("Metadata scan failed for job %s", job_id)
        with session_scope() as db:
            job = JobRepository(db).get(job_id)
            if job is not None:
                JobRepository(db).mark_failed(job, str(exc), stats)
    finally:
        connector.close()
        cancellation.clear(job_id)
