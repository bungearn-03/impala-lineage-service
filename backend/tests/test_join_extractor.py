"""Tests for join_extractor.py."""

from __future__ import annotations

from pathlib import Path

from app.parsers.join_extractor import extract_joins

FIXTURES_DIR = Path(__file__).parent / "sql_samples"


def _load(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def test_extract_joins_from_join_view():
    joins = extract_joins(_load("join_view.sql"))

    assert len(joins) == 1
    join = joins[0]

    assert join["join_type"] == "LEFT"
    assert join["right_table"] == "db.customers"
    assert join["left_context"] == "db.orders"
    assert join["condition"] is not None
    assert "customer_id" in join["condition"]


def test_extract_joins_from_cte_view():
    joins = extract_joins(_load("cte_view.sql"))

    assert len(joins) == 1
    join = joins[0]

    assert join["join_type"] == "INNER"
    assert join["right_table"] == "db.t2"
    assert join["condition"] is not None
    assert "x" in join["condition"]


def test_extract_joins_returns_empty_list_when_no_join():
    assert extract_joins("SELECT a FROM db.t1") == []


def test_extract_joins_cross_join_has_no_condition():
    sql = "SELECT a.x FROM db.t1 a CROSS JOIN db.t2 b"
    joins = extract_joins(sql)

    assert len(joins) == 1
    join = joins[0]
    assert join["join_type"] == "CROSS"
    assert join["right_table"] == "db.t2"
    assert join["condition"] is None
