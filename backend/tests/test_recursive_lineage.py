"""Tests for recursive_resolver.py using in-memory fake view/schema lookups.

These use plain dicts of fake view definitions rather than a real DB/connector,
so the resolver's traversal logic (leaves, cycles, depth truncation) can be
verified in isolation.
"""

from __future__ import annotations

from pathlib import Path

from app.parsers.recursive_resolver import resolve_recursive_lineage

FIXTURES_DIR = Path(__file__).parent / "sql_samples"


def _load(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def _fake_lookups(definitions: dict):
    def get_view_definition(name: str):
        return definitions.get(name)

    def get_schema(name: str):
        # Not used by the table-level resolver; present only for signature parity.
        return {}

    return get_view_definition, get_schema


def test_resolve_recursive_lineage_through_nested_views():
    # db.view_b -> db.view_a -> db.base_table (db.base_table is absent from
    # the fake definitions dict, so it resolves as a base-table leaf).
    definitions = {
        "db.view_b": _load("nested_view_b.sql"),
        "db.view_a": _load("nested_view_a.sql"),
    }
    get_view_definition, get_schema = _fake_lookups(definitions)

    result = resolve_recursive_lineage("db.view_b", get_view_definition, get_schema)

    assert result["root"] == "db.view_b"
    assert result["base_tables"] == ["db.base_table"]
    assert result["cycles"] == []
    assert result["depth_truncated"] == []
    assert ("db.view_b", "db.view_a") in result["edges"]
    assert ("db.view_a", "db.base_table") in result["edges"]


def test_resolve_recursive_lineage_treats_unknown_object_as_base_table():
    get_view_definition, get_schema = _fake_lookups({})

    result = resolve_recursive_lineage("db.only_table", get_view_definition, get_schema)

    assert result == {
        "root": "db.only_table",
        "base_tables": ["db.only_table"],
        "cycles": [],
        "depth_truncated": [],
        "edges": [],
    }


def test_resolve_recursive_lineage_detects_circular_views():
    # A synthetic cycle: view_x selects from view_y which selects from view_x.
    definitions = {
        "db.view_x": "CREATE VIEW db.view_x AS SELECT a FROM db.view_y",
        "db.view_y": "CREATE VIEW db.view_y AS SELECT a FROM db.view_x",
    }
    get_view_definition, get_schema = _fake_lookups(definitions)

    result = resolve_recursive_lineage("db.view_x", get_view_definition, get_schema)

    assert result["root"] == "db.view_x"
    assert result["cycles"] == ["db.view_x"]
    assert result["base_tables"] == []
    assert ("db.view_x", "db.view_y") in result["edges"]
    assert ("db.view_y", "db.view_x") in result["edges"]


def test_resolve_recursive_lineage_does_not_confuse_diamond_with_cycle():
    # db.top selects from both db.left and db.right, which both in turn
    # select from the same shared base table. This is a diamond dependency,
    # not a cycle, and must not be reported under "cycles".
    definitions = {
        "db.top": "CREATE VIEW db.top AS SELECT a FROM db.left l JOIN db.right r ON l.a = r.a",
        "db.left": "CREATE VIEW db.left AS SELECT a FROM db.shared",
        "db.right": "CREATE VIEW db.right AS SELECT a FROM db.shared",
    }
    get_view_definition, get_schema = _fake_lookups(definitions)

    result = resolve_recursive_lineage("db.top", get_view_definition, get_schema)

    assert result["cycles"] == []
    assert result["base_tables"] == ["db.shared"]


def test_resolve_recursive_lineage_respects_max_depth():
    # db.a -> db.b -> db.c -> db.d -> db.base, truncated once depth is exhausted.
    definitions = {
        "db.a": "CREATE VIEW db.a AS SELECT x FROM db.b",
        "db.b": "CREATE VIEW db.b AS SELECT x FROM db.c",
        "db.c": "CREATE VIEW db.c AS SELECT x FROM db.d",
        "db.d": "CREATE VIEW db.d AS SELECT x FROM db.base",
    }
    get_view_definition, get_schema = _fake_lookups(definitions)

    result = resolve_recursive_lineage("db.a", get_view_definition, get_schema, max_depth=2)

    assert result["root"] == "db.a"
    assert result["base_tables"] == []
    assert result["depth_truncated"] == ["db.c"]
    assert ("db.b", "db.c") in result["edges"]
    assert ("db.c", "db.d") not in result["edges"]
