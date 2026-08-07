"""Recursive view-lineage flattening: walk nested views down to base tables.

Pure and dependency-free: takes plain callables for fetching view
definitions/schemas so it never has to import a DB/connector layer itself;
callers wire in the real connector-backed functions.
"""

from __future__ import annotations

from typing import Callable

from app.parsers.table_lineage import extract_table_lineage


def resolve_recursive_lineage(
    root_object: str,
    get_view_definition: Callable[[str], str | None],
    get_schema: Callable[[str], dict],
    max_depth: int = 10,
) -> dict:
    """Flatten lineage for ``root_object`` through nested views down to base tables.

    ``get_view_definition(name)`` should return the object's SQL text if it
    is a view, or a falsy value if ``name`` is a base table (a leaf -- not a
    view, so there is nothing further to recurse into).

    ``get_schema`` is accepted for API-shape parity/forward compatibility
    (e.g. future schema-aware resolution) but is not called by this
    table-level resolver.

    Cycles (a view directly or transitively selecting from itself) are
    detected by tracking the current recursion path and are stopped rather
    than raised, then recorded under the returned ``"cycles"`` key. This
    intentionally tracks the *path* (current ancestry chain) rather than a
    single global "already seen" set, so that two independent branches
    legitimately sharing the same base table (a diamond dependency) are not
    mistaken for a cycle.

    Recursion stops at ``max_depth``; any view that could not be expanded
    further because the depth limit was reached is recorded under
    ``"depth_truncated"`` instead of being resolved to its own sources.

    Returns::

        {
            "root": root_object,
            "base_tables": sorted list of all leaf base table names reached,
            "cycles": sorted list of object names where a cycle was detected,
            "depth_truncated": sorted list of object names not expanded due to max_depth,
            "edges": [(parent, child), ...] for every direct view->source edge traversed,
        }
    """
    del get_schema  # not used by table-level resolution; kept for signature parity.

    base_tables: set[str] = set()
    cycles: set[str] = set()
    depth_truncated: set[str] = set()
    edges: list[tuple[str, str]] = []

    def _walk(name: str, depth: int, path: frozenset[str]) -> None:
        if name in path:
            cycles.add(name)
            return

        definition = get_view_definition(name)
        if not definition:
            base_tables.add(name)
            return

        if depth >= max_depth:
            depth_truncated.add(name)
            return

        immediate = extract_table_lineage(definition)
        next_path = path | {name}
        for source in immediate["sources"]:
            edges.append((name, source))
            _walk(source, depth + 1, next_path)

    _walk(root_object, 0, frozenset())

    return {
        "root": root_object,
        "base_tables": sorted(base_tables),
        "cycles": sorted(cycles),
        "depth_truncated": sorted(depth_truncated),
        "edges": edges,
    }
