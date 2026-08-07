"""Pure, dependency-free helpers for comparing and classifying schema metadata.

Nothing in this module performs I/O or talks to a connector; it only operates on
the dataclasses defined in ``app.connectors.base`` (``ColumnMetadata``). This
keeps the module trivially unit-testable and safe to import from anywhere.
"""

from __future__ import annotations

import re

from app.connectors.base import ColumnMetadata

# Matches a leading "CREATE [OR REPLACE] VIEW ..." statement, case-insensitive,
# tolerating leading whitespace/newlines before the CREATE keyword.
_VIEW_DDL_RE = re.compile(r"^\s*CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\b", re.IGNORECASE)


def diff_columns(
    existing: list[ColumnMetadata], new: list[ColumnMetadata]
) -> dict:
    """Compare two column lists by column name and report the differences.

    Returns a dict with three keys:
      - "added": columns present in ``new`` but not in ``existing``.
      - "removed": columns present in ``existing`` but not in ``new``.
      - "changed": list of ``(old, new)`` tuples for columns that exist in both
        lists (matched by name) but whose ``data_type`` or ``ordinal_position``
        differs between the two.
    """
    existing_by_name = {col.name: col for col in existing}
    new_by_name = {col.name: col for col in new}

    added = [col for name, col in new_by_name.items() if name not in existing_by_name]
    removed = [col for name, col in existing_by_name.items() if name not in new_by_name]

    changed: list[tuple[ColumnMetadata, ColumnMetadata]] = []
    for name, old_col in existing_by_name.items():
        new_col = new_by_name.get(name)
        if new_col is None:
            continue
        if (
            old_col.data_type != new_col.data_type
            or old_col.ordinal_position != new_col.ordinal_position
        ):
            changed.append((old_col, new_col))

    return {"added": added, "removed": removed, "changed": changed}


def is_view_ddl(ddl: str) -> bool:
    """Heuristically determine whether a DDL string looks like CREATE VIEW.

    Returns False for falsy input (e.g. None or empty string) and for DDL that
    looks like CREATE TABLE (or anything else not matching CREATE [OR REPLACE]
    VIEW).
    """
    if not ddl:
        return False
    return bool(_VIEW_DDL_RE.match(ddl))
