"""Equi-join column-pair extraction for whole-database ER/DR diagrams.

Unlike app.parsers.column_lineage (data *provenance* into a view's output
columns) or app.parsers.join_extractor (raw JOIN clause info as loose
strings, used for join-graph inspection), this module extracts structured
`table.column = table.column` equality pairs from a view's JOIN conditions --
the schema-level "this looks like a foreign key" relationships a DR/ER
diagram wants to draw between BASE tables, independent of any single view's
own output columns. This mirrors what tools like DBeaver/dictionary-driven
ER generators infer when no real FK constraints exist (which is normal for
Impala/Hive tables).
"""

from __future__ import annotations

from sqlglot import exp

from app.parsers.sqlglot_parser import parse_sql
from app.parsers.table_lineage import fully_qualified_table_name


def _alias_map(expression: exp.Expression) -> dict[str, str]:
    """Map every alias (and bare table name) appearing anywhere in the
    statement's table references to its fully-qualified table name, so
    `alias.col` references in ON conditions can be resolved back to a real
    table regardless of whether the query used the bare name or an alias.
    """
    aliases: dict[str, str] = {}
    for table in expression.find_all(exp.Table):
        full_name = fully_qualified_table_name(table)
        if not full_name:
            continue
        aliases[table.name.lower()] = full_name
        alias_name = table.alias
        if alias_name:
            aliases[alias_name.lower()] = full_name
    return aliases


def extract_equi_joins(sql: str, dialect: str = "hive") -> list[dict]:
    """Extract every `left.col = right.col` equality in a JOIN's ON
    condition, with `left`/`right` resolved from aliases to real table
    names.

    Returns a list of
    ``{"left_table": str, "left_col": str, "right_table": str, "right_col": str}``.

    Best-effort: a join with no ON clause, or a comparison that isn't a
    simple qualified-column-to-qualified-column equality (e.g. a literal
    comparison, or an unqualified column), contributes no pair rather than
    raising. A compound ON (`a.x = b.x AND a.y = b.y`) yields one pair per
    equality found anywhere in the condition tree.
    """
    expression = parse_sql(sql, dialect=dialect)
    aliases = _alias_map(expression)

    pairs: list[dict] = []
    for join in expression.find_all(exp.Join):
        on = join.args.get("on")
        if on is None:
            continue
        for eq in on.find_all(exp.EQ):
            left, right = eq.this, eq.expression
            if not (isinstance(left, exp.Column) and isinstance(right, exp.Column)):
                continue
            left_ref = left.table.lower() if left.table else None
            right_ref = right.table.lower() if right.table else None
            if not left_ref or not right_ref:
                continue

            left_table = aliases.get(left_ref)
            right_table = aliases.get(right_ref)
            if not left_table or not right_table or left_table == right_table:
                continue

            pairs.append(
                {
                    "left_table": left_table,
                    "left_col": left.name,
                    "right_table": right_table,
                    "right_col": right.name,
                }
            )
    return pairs
