"""Column-level lineage extraction using sqlglot's built-in lineage engine.

Pure and dependency-free: operates on plain SQL strings and a plain nested
schema dict, never on the app's models/DB layer.

Note on design: sqlglot's ``lineage()`` returns a tree of ``Node`` objects
rooted at the target column, where each node's ``.downstream`` list holds the
node(s) it was derived from, down to leaf ``Node``s whose ``.source`` is the
real ``exp.Table`` a column was ultimately read from. This module treats the
*root* node's ``.expression`` as "how the target column as a whole is
computed" (used for ``transformation_expr``/``transformation_type``, which are
therefore the same across every leaf emitted for a given target column), and
each *leaf* node as one physical-table contribution (used for
``source_table``/``source_column``).
"""

from __future__ import annotations

from typing import Any

from sqlglot import exp
from sqlglot.lineage import lineage as _sqlglot_lineage

from app.parsers.sqlglot_parser import parse_sql
from app.parsers.table_lineage import fully_qualified_table_name


def extract_column_lineage(
    sql: str,
    target_columns: list[str] | None,
    schema: dict,
    dialect: str = "hive",
) -> list[dict]:
    """Best-effort column-level lineage for ``sql`` via sqlglot's lineage engine.

    ``schema`` is a nested dict of the shape sqlglot's ``lineage()`` /
    ``sqlglot.optimizer.qualify`` expect -- either ``{db: {table: {column:
    type}}}`` or ``{table: {column: type}}`` -- and is passed straight
    through.

    For every target column (all output columns of the top-level ``SELECT``
    if ``target_columns`` is ``None``, else only the given ones), this calls
    ``sqlglot.lineage.lineage`` and walks the resulting node tree down to its
    leaves, emitting one dict per leaf::

        {
            "target_column": <column>,
            "source_table": <fully-qualified base table name>,
            "source_column": <column name/expression at the leaf>,
            "transformation_expr": <SQL text of how the target column is computed>,
            "transformation_type": "DIRECT" | "AGGREGATED" | "DERIVED",
        }

    This is best-effort: sqlglot's lineage engine can fail outright, or only
    partially resolve, on complex/unsupported SQL constructs. Any exception
    while resolving a single column is swallowed and that column is skipped,
    so one unresolvable column never kills the whole batch.
    """
    columns = (
        list(target_columns)
        if target_columns is not None
        else _output_columns(sql, dialect)
    )

    results: list[dict] = []
    for column in columns:
        try:
            results.extend(_lineage_for_column(column, sql, schema, dialect))
        except Exception:
            continue
    return results


def _output_columns(sql: str, dialect: str) -> list[str]:
    expression = parse_sql(sql, dialect=dialect)
    select = expression if isinstance(expression, exp.Select) else expression.find(exp.Select)
    if select is None:
        return []
    return [name for name in select.named_selects if name]


def _lineage_for_column(column: str, sql: str, schema: dict, dialect: str) -> list[dict]:
    root = _sqlglot_lineage(column, sql, schema=schema, dialect=dialect)

    root_expression = getattr(root, "expression", None)
    transformation_expr = (
        root_expression.sql(dialect=dialect) if root_expression is not None else None
    )
    transformation_type = _classify(root_expression)

    rows: list[dict] = []
    for leaf in _leaves(root):
        source = getattr(leaf, "source", None)
        if not isinstance(source, exp.Table):
            continue

        source_table = fully_qualified_table_name(source)
        if not source_table:
            continue

        leaf_expression = getattr(leaf, "expression", None)
        leaf_name = getattr(leaf, "name", None)
        source_column = leaf_name or (
            leaf_expression.sql(dialect=dialect) if leaf_expression is not None else column
        )

        rows.append(
            {
                "target_column": column,
                "source_table": source_table,
                "source_column": source_column,
                "transformation_expr": transformation_expr,
                "transformation_type": transformation_type,
            }
        )
    return rows


def _leaves(node: Any) -> list[Any]:
    """Recurse through ``node.downstream`` to collect leaf Nodes.

    A leaf is a node with no further ``.downstream`` entries.
    """
    downstream = list(getattr(node, "downstream", None) or [])
    if not downstream:
        return [node]

    leaves: list[Any] = []
    for child in downstream:
        leaves.extend(_leaves(child))
    return leaves


def _classify(expression: exp.Expression | None) -> str:
    if expression is None:
        return "DERIVED"
    if isinstance(expression, exp.Column):
        return "DIRECT"
    if next(expression.find_all(exp.AggFunc), None) is not None:
        return "AGGREGATED"
    return "DERIVED"
