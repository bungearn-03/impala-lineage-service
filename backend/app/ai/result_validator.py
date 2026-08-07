"""Validation of AI-proposed lineage edges against known schema.

Deliberately dependency-free of the ORM layer (``app.models``) as well as the
rest of the app — this module only deals with plain dicts/lists so it can be
unit-tested in isolation and reused by whatever worker eventually turns
validated edges into ``LineageEdge`` rows with ``created_by="AI"``.
"""

from __future__ import annotations

from .response_schema import AILineageResponse


def validate_ai_edges(
    response: AILineageResponse,
    available_tables: dict,
    target_columns: list[str],
) -> list[dict]:
    """Filter AI-proposed edges down to ones that reference real identifiers.

    An edge survives only if:
      - ``source_table`` is a key in ``available_tables``, AND
      - ``source_column`` is a key in ``available_tables[source_table]``, AND
      - ``target_column`` is in ``target_columns``

    This is the hallucination guard: anything referencing a table/column that
    doesn't actually exist in the known schema, or a target column that
    wasn't even asked about, is dropped silently.

    ``confidence`` is clamped into ``[0.0, 1.0]`` on the way out.

    Returns:
        A list of plain dicts (not ORM objects) with keys
        ``source_table, source_column, target_column, transformation_type,
        transformation_expr, confidence`` — ready for a worker to turn into
        ``LineageEdge`` rows with ``created_by="AI"``.
    """
    validated: list[dict] = []

    target_column_set = set(target_columns)

    for edge in response.edges:
        table_columns = available_tables.get(edge.source_table)
        if table_columns is None:
            continue
        if edge.source_column not in table_columns:
            continue
        if edge.target_column not in target_column_set:
            continue

        confidence = max(0.0, min(1.0, edge.confidence))

        validated.append(
            {
                "source_table": edge.source_table,
                "source_column": edge.source_column,
                "target_column": edge.target_column,
                "transformation_type": edge.transformation_type,
                "transformation_expr": edge.transformation_expr,
                "confidence": confidence,
            }
        )

    return validated
