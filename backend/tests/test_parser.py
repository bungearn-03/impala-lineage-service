"""Tests for sql_normalizer.py and table_lineage.py."""

from __future__ import annotations

from pathlib import Path

from app.parsers.sql_normalizer import normalize_sql
from app.parsers.table_lineage import extract_table_lineage

FIXTURES_DIR = Path(__file__).parent / "sql_samples"


def _load(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


# --- sql_normalizer ----------------------------------------------------


def test_normalize_sql_strips_trailing_semicolons_and_whitespace():
    normalized = normalize_sql("SELECT 1 ;  ;  \n\n")
    assert not normalized.endswith(";")
    assert normalized == normalized.strip()


def test_normalize_sql_strips_comments_via_sqlglot():
    sql = "SELECT a -- trailing comment\nFROM db.t1 /* block comment */"
    normalized = normalize_sql(sql)
    assert "--" not in normalized
    assert "/*" not in normalized
    assert "db.t1" in normalized


def test_normalize_sql_falls_back_on_unparseable_sql():
    sql = "THIS IS NOT ; -- a valid statement /* at all */ !!!"
    normalized = normalize_sql(sql)
    assert "--" not in normalized
    assert "/*" not in normalized
    assert not normalized.endswith(";")
    assert "THIS IS NOT" in normalized


def test_normalize_sql_handles_empty_input():
    assert normalize_sql("") == ""
    assert normalize_sql("   ;  ;   ") == ""


# --- table_lineage -------------------------------------------------------


def test_bare_select_has_no_target():
    result = extract_table_lineage("SELECT a, b FROM db.t1")
    assert result["target"] is None
    assert result["sources"] == ["db.t1"]


def test_simple_view_target_and_sources():
    result = extract_table_lineage(_load("simple_view.sql"))
    assert result["target"] == "db.v1"
    assert result["sources"] == ["db.t1"]


def test_join_view_target_and_sources():
    result = extract_table_lineage(_load("join_view.sql"))
    assert result["target"] == "db.v_join"
    assert result["sources"] == ["db.customers", "db.orders"]


def test_cte_view_excludes_cte_alias_from_sources():
    result = extract_table_lineage(_load("cte_view.sql"))
    assert result["target"] == "db.v_cte"
    assert "cte" not in result["sources"]
    assert result["sources"] == ["db.t1", "db.t2"]


def test_agg_view_target_and_sources():
    result = extract_table_lineage(_load("agg_view.sql"))
    assert result["target"] == "db.v_agg"
    assert result["sources"] == ["db.orders"]


def test_nested_view_fixtures_chain():
    view_a = extract_table_lineage(_load("nested_view_a.sql"))
    view_b = extract_table_lineage(_load("nested_view_b.sql"))

    assert view_a["target"] == "db.view_a"
    assert view_a["sources"] == ["db.base_table"]

    assert view_b["target"] == "db.view_b"
    assert view_b["sources"] == ["db.view_a"]


def test_insert_into_select_target_and_sources():
    sql = "INSERT INTO db.t2 SELECT a, b FROM db.t1"
    result = extract_table_lineage(sql)
    assert result["target"] == "db.t2"
    assert result["sources"] == ["db.t1"]


def test_ctas_target_and_sources():
    sql = "CREATE TABLE db.t2 AS SELECT a, b FROM db.t1"
    result = extract_table_lineage(sql)
    assert result["target"] == "db.t2"
    assert result["sources"] == ["db.t1"]
