"""Entry points for scanning Impala/Hive metadata via a ``BaseConnector``.

These are the two functions the (future) scan worker calls. Everything here
runs sequentially against a single connector instance -- impyla connections
backing ``BaseConnector`` implementations are not thread-safe, so no
concurrency is introduced in this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.connectors.base import BaseConnector, ObjectMetadata
from app.core.logging import get_logger
from app.metadata.view_definition_loader import ensure_view_definitions

logger = get_logger(__name__)


@dataclass
class ScanResult:
    """Result of scanning a single database.

    - objects: successfully fetched ObjectMetadata for the database.
    - skipped: (object_name, error_message) pairs for objects whose metadata
      could not be fetched and were therefore excluded from ``objects``.
    """

    objects: list[ObjectMetadata]
    skipped: list[tuple[str, str]]


def scan_database(
    connector: BaseConnector,
    database: str,
    cancel_check: Callable[[], bool] | None = None,
) -> ScanResult:
    """Scan a single database and return its objects' metadata.

    Calls ``connector.list_objects(database)`` to enumerate (name, object_type)
    pairs, then fetches full metadata (columns, ddl, view_definition) for each
    via ``connector.get_object_metadata``. Any view still missing a
    view_definition after that is retried through ``ensure_view_definitions``.

    A failure fetching one object's metadata (e.g. a corrupted or unsupported
    table) is logged and that object is skipped -- it does not abort the scan
    of the rest of the database.

    ``cancel_check``, if given, is polled between objects (each of which is
    its own network round-trip to Impala/Hive) so a cancellation request
    lands within one object fetch instead of only after the entire database
    finishes -- important for databases with many tables, where that could
    otherwise be minutes. On cancellation, whatever was already fetched is
    returned rather than discarded.

    Caller contract (for the future scan worker): this function performs no
    persistence and has no side effects beyond logging. The worker is expected
    to take the returned ``ScanResult.objects`` and upsert them (and their
    columns) into the database layer, and to record ``ScanResult.skipped``
    somewhere visible (e.g. a scan-run log/report) so operators know which
    objects need investigation. This function should be called sequentially --
    do not fan it out across threads, since the underlying connector is not
    thread-safe.
    """
    objects: list[ObjectMetadata] = []
    skipped: list[tuple[str, str]] = []

    object_refs = connector.list_objects(database)
    for object_name, object_type in object_refs:
        if cancel_check is not None and cancel_check():
            break

        try:
            obj = connector.get_object_metadata(database, object_name, object_type)
        except Exception as exc:  # noqa: BLE001 - one bad object must not abort the scan
            logger.error(
                "Failed to fetch metadata for %s.%s: %s", database, object_name, exc
            )
            skipped.append((object_name, str(exc)))
            continue

        objects.append(obj)

    ensure_view_definitions(connector, objects)

    return ScanResult(objects=objects, skipped=skipped)


def scan_all_databases(connector: BaseConnector) -> dict[str, ScanResult]:
    """Scan every database visible to ``connector``.

    Calls ``connector.list_databases()`` and runs ``scan_database`` for each
    one in turn (sequentially -- the connector is not thread-safe), returning
    a mapping of database name to its ``ScanResult``.

    Caller contract (for the future scan worker): iterate the returned dict,
    persist each database's ``ScanResult.objects``, and surface each
    database's ``ScanResult.skipped`` list for operator visibility. A
    top-level failure to list or scan a given database is intentionally *not*
    swallowed here beyond what ``scan_database`` already handles per-object --
    if ``connector.list_databases()`` itself raises, that propagates to the
    caller.
    """
    results: dict[str, ScanResult] = {}
    for database in connector.list_databases():
        results[database] = scan_database(connector, database)
    return results
