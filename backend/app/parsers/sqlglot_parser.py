"""Thin, dependency-free wrapper around sqlglot's parsing entry points.

Deliberately does not import ``app.core.exceptions`` (or anything else from
the rest of the app) so this package stays independently unit-testable;
parse failures are surfaced as plain ``ValueError``\\ s instead of app-specific
exception types, leaving it to callers in other layers to translate that into
whatever error type they need.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp


def parse_sql(sql: str, dialect: str = "hive") -> exp.Expression:
    """Parse a single SQL statement into a sqlglot expression tree.

    Raises ``ValueError`` (with the original sqlglot error text included) if
    the statement cannot be parsed.
    """
    try:
        return sqlglot.parse_one(sql, read=dialect)
    except Exception as exc:
        raise ValueError(
            f"Failed to parse SQL with dialect={dialect!r}: {exc}"
        ) from exc


def parse_statements(sql: str, dialect: str = "hive") -> list[exp.Expression]:
    """Parse possibly-multi-statement SQL text into a list of expressions.

    Statements sqlglot could not turn into a node (e.g. an empty statement
    between two semicolons) come back as ``None`` from ``sqlglot.parse`` and
    are filtered out of the returned list.

    Raises ``ValueError`` (with the original sqlglot error text included) if
    the input cannot be parsed at all.
    """
    try:
        statements = sqlglot.parse(sql, read=dialect)
    except Exception as exc:
        raise ValueError(
            f"Failed to parse SQL with dialect={dialect!r}: {exc}"
        ) from exc
    return [statement for statement in statements if statement is not None]
