"""Backfills missing view definitions on already-scanned ``ObjectMetadata``.

``BaseConnector.get_object_metadata`` already tries to populate
``view_definition`` for VIEW objects, but some connector implementations may
skip it (or fail silently) when fetching object metadata in bulk. This module
gives callers a second, explicit pass to fill in any gaps before lineage
computation, which absolutely requires ``view_definition`` for every view.
"""

from __future__ import annotations

from app.connectors.base import BaseConnector, ObjectMetadata
from app.core.logging import get_logger

logger = get_logger(__name__)


def ensure_view_definitions(
    connector: BaseConnector, objects: list[ObjectMetadata]
) -> list[ObjectMetadata]:
    """Ensure every VIEW object in ``objects`` has a ``view_definition``.

    For each object where ``object_type == "VIEW"`` and ``view_definition`` is
    falsy, this calls ``connector.get_view_definition(database_name,
    object_name)`` and fills the result in. The list is mutated in place and
    also returned for convenience.

    If a view's definition still cannot be retrieved (the connector returns
    None/empty), a warning is logged since lineage cannot be computed for that
    view later.
    """
    for obj in objects:
        if obj.object_type != "VIEW" or obj.view_definition:
            continue

        definition = connector.get_view_definition(obj.database_name, obj.object_name)
        obj.view_definition = definition

        if not definition:
            logger.warning(
                "Could not retrieve view definition for %s.%s; lineage cannot "
                "be computed for this view.",
                obj.database_name,
                obj.object_name,
            )

    return objects
