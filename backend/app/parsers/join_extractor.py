"""Best-effort JOIN extraction from a single SQL statement.

Pure and dependency-free: operates only on the SQL text and sqlglot's parsed
expression tree, never on the app's models/DB layer.
"""

from __future__ import annotations

from sqlglot import exp

from app.parsers.sqlglot_parser import parse_sql
from app.parsers.table_lineage import fully_qualified_table_name


def extract_joins(sql: str, dialect: str = "hive") -> list[dict]:
    """Extract every JOIN in ``sql`` as a plain dict.

    Each entry is::

        {
            "left_context": <nearest enclosing FROM table name, or None>,
            "right_table": <joined table name>,
            "join_type": <"INNER" | "LEFT" | "RIGHT" | "FULL" | "CROSS" | ...>,
            "condition": <SQL text of the ON/USING clause, or None>,
        }

    This is best-effort: a join with no explicit condition (e.g. ``CROSS
    JOIN``, or a natural join sqlglot didn't attach an ``on``/``using`` to)
    simply gets ``condition: None`` instead of raising.
    """
    expression = parse_sql(sql, dialect=dialect)

    joins: list[dict] = []
    for join in expression.find_all(exp.Join):
        joins.append(
            {
                "left_context": _left_context(join),
                "right_table": _right_table_name(join),
                "join_type": _join_type(join),
                "condition": _join_condition(join, dialect),
            }
        )
    return joins


def _join_type(join: exp.Join) -> str:
    side = join.args.get("side")
    if side:
        return str(side).upper()
    kind = join.args.get("kind")
    if kind:
        return str(kind).upper()
    return "INNER"


def _join_condition(join: exp.Join, dialect: str) -> str | None:
    on = join.args.get("on")
    if on is not None:
        return on.sql(dialect=dialect)

    using = join.args.get("using")
    if using:
        columns = ", ".join(col.sql(dialect=dialect) for col in using)
        return f"USING ({columns})"

    return None


def _right_table_name(join: exp.Join) -> str | None:
    node = join.this
    if node is None:
        return None
    table = node if isinstance(node, exp.Table) else node.find(exp.Table)
    if table is None:
        # e.g. a joined derived table/subquery with no plain table inside;
        # fall back to whatever alias it was given.
        return node.alias_or_name or None
    return fully_qualified_table_name(table)


def _left_context(join: exp.Join) -> str | None:
    select = join.find_ancestor(exp.Select)
    if select is None:
        return None

    from_ = select.args.get("from")
    if from_ is None:
        return None

    table_expr = from_.this
    if table_expr is None:
        return None

    table = table_expr if isinstance(table_expr, exp.Table) else table_expr.find(exp.Table)
    if table is None:
        return table_expr.alias_or_name or None
    return fully_qualified_table_name(table)
