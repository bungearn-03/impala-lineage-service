"""Build networkx graphs out of plain lineage-edge dicts.

This module is intentionally decoupled from ``app.models`` (the SQLAlchemy
ORM) and from ``app.schemas`` (the FastAPI/Pydantic response models). It only
ever consumes and produces plain dicts / networkx graphs so it can be tested
and reused without a database session or a FastAPI app context.

Expected shape of each raw edge dict (as persisted by the lineage worker)::

    {
        "id": str,
        "source_object_id": str, "source_object_name": str,
        "target_object_id": str, "target_object_name": str,
        "source_column_id": str | None, "source_column_name": str | None,
        "target_column_id": str | None, "target_column_name": str | None,
        "transformation_type": str,  # DIRECT|DERIVED|AGGREGATED|JOIN|UNKNOWN
        "confidence": float,
    }

Table-level edges have both column ids/names set to ``None``; column-level
edges have them populated.
"""

from __future__ import annotations

from typing import Any

import networkx as nx


def _as_confidence(raw_edge: dict[str, Any]) -> float:
    """Best-effort coercion of the raw edge's confidence to a float."""

    confidence = raw_edge.get("confidence")
    return float(confidence) if confidence is not None else 0.0


def build_object_graph(edges: list[dict[str, Any]]) -> nx.DiGraph:
    """Collapse raw lineage edges into one node per object and one directed
    edge per distinct (source_object, target_object) pair.

    All raw edges that connect the same pair of objects (whether they are
    table-level edges or several column-level edges) are folded into a
    single graph edge. No lineage detail is lost in the process: the full
    list of contributing raw edge dicts is kept on the edge under
    ``"contributing_edges"`` so a caller can recover column-level detail
    for a given object-to-object relationship later (e.g. to render a
    tooltip or a drill-down panel).

    Edge attributes:
        contributing_edges: list[dict] -- every raw edge dict that was
            folded into this object-to-object edge.
        transformation_types: set[str] -- distinct ``transformation_type``
            values seen across the contributing edges.
        max_confidence: float -- highest ``confidence`` seen across the
            contributing edges.
    """

    graph: nx.DiGraph = nx.DiGraph()

    for raw_edge in edges:
        source_object_id = raw_edge["source_object_id"]
        target_object_id = raw_edge["target_object_id"]

        if source_object_id not in graph:
            graph.add_node(
                source_object_id,
                label=raw_edge.get("source_object_name", source_object_id),
                type="object",
            )
        if target_object_id not in graph:
            graph.add_node(
                target_object_id,
                label=raw_edge.get("target_object_name", target_object_id),
                type="object",
            )

        confidence = _as_confidence(raw_edge)
        transformation_type = raw_edge.get("transformation_type")

        if graph.has_edge(source_object_id, target_object_id):
            edge_data = graph.edges[source_object_id, target_object_id]
            edge_data["contributing_edges"].append(raw_edge)
            edge_data["transformation_types"].add(transformation_type)
            edge_data["max_confidence"] = max(edge_data["max_confidence"], confidence)
        else:
            graph.add_edge(
                source_object_id,
                target_object_id,
                contributing_edges=[raw_edge],
                transformation_types={transformation_type},
                max_confidence=confidence,
            )

    return graph


def _column_node_id(object_id: str, column_id: str | None) -> str:
    """Node id for a column-level node, falling back to the bare object id
    for edges that only carry table-level information."""

    return f"{object_id}::{column_id}" if column_id is not None else object_id


def _add_column_graph_node(
    graph: nx.DiGraph,
    *,
    object_id: str,
    object_name: str,
    column_id: str | None,
    column_name: str | None,
) -> str:
    node_id = _column_node_id(object_id, column_id)
    if node_id not in graph:
        if column_id is not None:
            graph.add_node(
                node_id,
                label=column_name or node_id,
                type="column",
                parent_object_id=object_id,
            )
        else:
            graph.add_node(
                node_id,
                label=object_name,
                type="object",
                parent_object_id=object_id,
            )
    return node_id


def build_column_graph(edges: list[dict[str, Any]]) -> nx.DiGraph:
    """Build a finer-grained graph that keeps column-level detail.

    A node id is ``f"{object_id}::{column_id}"`` for column-level edges,
    falling back to the bare ``object_id`` for edges that only carry
    table-level information (``source_column_id``/``target_column_id`` is
    ``None``).

    Unlike :func:`build_object_graph`, this graph is not collapsed: each raw
    edge dict is meant to produce its own graph edge, since column-level
    detail matters here. The one caveat is that ``networkx.DiGraph`` (as
    opposed to a multigraph) cannot hold two parallel edges between the same
    ordered node pair. In practice this only happens when two *table-level*
    raw edges connect the very same pair of objects (column-level node ids
    already disambiguate on column, so real collisions are rare). When it
    does happen, the raw edges are merged onto the same graph edge and every
    contributing raw edge dict is preserved in a ``"contributing_edges"``
    list, so no data is silently dropped.
    """

    graph: nx.DiGraph = nx.DiGraph()

    for raw_edge in edges:
        source_node = _add_column_graph_node(
            graph,
            object_id=raw_edge["source_object_id"],
            object_name=raw_edge.get("source_object_name", raw_edge["source_object_id"]),
            column_id=raw_edge.get("source_column_id"),
            column_name=raw_edge.get("source_column_name"),
        )
        target_node = _add_column_graph_node(
            graph,
            object_id=raw_edge["target_object_id"],
            object_name=raw_edge.get("target_object_name", raw_edge["target_object_id"]),
            column_id=raw_edge.get("target_column_id"),
            column_name=raw_edge.get("target_column_name"),
        )

        if graph.has_edge(source_node, target_node):
            graph.edges[source_node, target_node]["contributing_edges"].append(raw_edge)
        else:
            graph.add_edge(
                source_node,
                target_node,
                id=raw_edge.get("id"),
                transformation_type=raw_edge.get("transformation_type"),
                confidence=_as_confidence(raw_edge),
                contributing_edges=[raw_edge],
            )

    return graph
