"""Table-level (object-to-object) lineage extraction from a single SQL statement.

Pure and dependency-free: operates only on the SQL text and sqlglot's parsed
expression tree, never on the app's models/DB layer.
"""

from __future__ import annotations

from sqlglot import exp

from app.parsers.sqlglot_parser import parse_sql


def fully_qualified_table_name(table: exp.Table) -> str | None:
    """Return ``db.table`` when ``table`` has a db/schema qualifier, else just the bare name.

    Catalog qualifiers (rare in Impala/Hive) are intentionally ignored per the
    simple ``db.table`` naming convention used throughout this package.
    Returns ``None`` if the table node has no usable name at all.
    """
    name = table.name
    if not name:
        return None
    db = table.db
    return f"{db}.{name}" if db else name


def extract_table_lineage(sql: str, dialect: str = "hive") -> dict:
    """Extract the target object and base-table sources of a single SQL statement.

    Returns ``{"target": str | None, "sources": list[str]}``:

    - ``target`` is the fully-qualified table/view name being created or
      inserted into, for ``CREATE VIEW``, ``CREATE TABLE ... AS SELECT``, and
      ``INSERT INTO/OVERWRITE ... SELECT`` statements. For a bare ``SELECT``
      (no target), ``target`` is ``None``.
    - ``sources`` is the deduplicated, sorted list of fully-qualified
      base-table names referenced anywhere in the statement's query body
      (FROM/JOIN clauses, including inside subqueries and CTE bodies), with
      any name that is actually a CTE alias defined by a ``WITH`` clause in
      the same statement excluded (CTEs aren't real base tables). The
      DDL/DML target itself (the object being created/inserted into) is
      never counted as a source, even though it also appears as an
      ``exp.Table`` node in the same parsed tree.
    """
    expression = parse_sql(sql, dialect=dialect)

    target = _extract_target(expression)
    sources = _extract_sources(expression)

    return {"target": target, "sources": sources}


def _extract_target(expression: exp.Expression) -> str | None:
    if isinstance(expression, (exp.Create, exp.Insert)):
        return _target_table_name(expression.this)
    return None


def _target_table_name(node: exp.Expression | None) -> str | None:
    if node is None:
        return None
    table = node if isinstance(node, exp.Table) else node.find(exp.Table)
    if table is None:
        return None
    return fully_qualified_table_name(table)


def _query_scope(expression: exp.Expression) -> exp.Expression | None:
    """Return the sub-tree that represents the statement's query body.

    For ``CREATE``/``INSERT`` this is ``expression.expression`` -- the ``AS
    SELECT`` / inserted-``SELECT`` part -- deliberately excluding
    ``expression.this`` (the DDL/DML target table) so the target never gets
    walked as if it were a source. For anything else (a bare ``SELECT``,
    etc.) the whole expression *is* the query body.
    """
    if isinstance(expression, (exp.Create, exp.Insert)):
        return expression.expression
    return expression


def _extract_sources(expression: exp.Expression) -> list[str]:
    scope = _query_scope(expression)
    if scope is None:
        return []

    cte_aliases = {cte.alias_or_name for cte in scope.find_all(exp.CTE)}

    names: set[str] = set()
    for table in scope.find_all(exp.Table):
        if table.name in cte_aliases:
            continue
        full_name = fully_qualified_table_name(table)
        if full_name:
            names.add(full_name)

    return sorted(names)
