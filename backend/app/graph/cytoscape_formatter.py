"""Format a networkx lineage graph into Cytoscape.js-ready plain dicts.

The output shape matches ``app.schemas.diagram.DiagramResponse`` /
``CytoscapeElement`` / ``CytoscapeNodeData`` / ``CytoscapeEdgeData``, but this
module deliberately does not import those Pydantic classes so the graph
package stays decoupled from the FastAPI/schema layer -- it only produces
plain dicts with matching field names. Whoever wires the API layer is
responsible for validating these dicts against the Pydantic schema.
"""

from __future__ import annotations

from typing import Any

import networkx as nx


def _node_element(node_id: str, attrs: dict[str, Any]) -> dict[str, Any]:
    """Build one ``CytoscapeElement``-shaped dict for a graph node.

    ``build_object_graph`` and ``build_column_graph`` produce different
    attribute sets (e.g. only column nodes have ``parent_object_id``), so
    every attribute is read with ``.get()`` and defaults to ``None`` rather
    than being required.
    """

    node_type = attrs.get("type", "object")

    # Only surface a Cytoscape compound-node "parent" for column nodes.
    # build_column_graph's table-level fallback nodes (column ids are None)
    # are themselves object-type nodes whose node id *is* the object id, so
    # their "parent_object_id" attr equals their own id -- surfacing that as
    # "parent" would make a node its own compound parent, which Cytoscape.js
    # rejects. Object-type nodes are containers, not children, so they never
    # get a "parent".
    parent = attrs.get("parent")
    if parent is None and node_type == "column":
        parent = attrs.get("parent_object_id")

    return {
        "id": node_id,
        "label": attrs.get("label", node_id),
        "type": node_type,
        "object_type": attrs.get("object_type"),
        "database_name": attrs.get("database_name"),
        "parent": parent,
    }


def _distinct_transformation_types(attrs: dict[str, Any]) -> list[str]:
    """Normalize either the collapsed ``transformation_types`` set (from
    ``build_object_graph``) or the single ``transformation_type`` string
    (from ``build_column_graph``) into a sorted list of distinct, non-empty
    type strings."""

    types = attrs.get("transformation_types")
    if types is not None:
        return sorted({t for t in types if t})

    single = attrs.get("transformation_type")
    return [single] if single else []


def _edge_label(distinct_types: list[str]) -> str | None:
    return ", ".join(distinct_types) if distinct_types else None


def _edge_transformation_type(distinct_types: list[str]) -> str | None:
    return ", ".join(distinct_types) if distinct_types else None


def _edge_confidence(attrs: dict[str, Any]) -> float | None:
    if "max_confidence" in attrs:
        return attrs.get("max_confidence")
    return attrs.get("confidence")


def _edge_element(source: str, target: str, attrs: dict[str, Any]) -> dict[str, Any]:
    distinct_types = _distinct_transformation_types(attrs)

    # build_column_graph stashes the raw lineage edge id under "id"; it is
    # already unique per edge. build_object_graph has no such single id
    # (many raw edges may be folded together), so fall back to a
    # source->target id, which is guaranteed unique since there is at most
    # one graph edge per ordered node pair.
    edge_id = attrs.get("id") or f"{source}->{target}"

    return {
        "id": edge_id,
        "source": source,
        "target": target,
        "label": _edge_label(distinct_types),
        "transformation_type": _edge_transformation_type(distinct_types),
        "confidence": _edge_confidence(attrs),
    }


def _truncate_to_top_degree_nodes(graph: nx.DiGraph, max_nodes: int) -> nx.DiGraph:
    """Keep only the ``max_nodes`` highest-degree nodes (in + out degree),
    since those are the most connected and most informative nodes to show
    when a diagram would otherwise be too large to render usefully."""

    degrees = dict(graph.degree())
    # Sort by degree descending; break ties by node id for determinism.
    kept_node_ids = sorted(degrees, key=lambda n: (-degrees[n], str(n)))[:max_nodes]
    return graph.subgraph(kept_node_ids)


def to_cytoscape_elements(
    graph: nx.DiGraph, max_nodes: int | None = None
) -> dict[str, Any]:
    """Convert a lineage graph (from ``build_object_graph`` or
    ``build_column_graph``, or a slice of either from ``ego_slice``) into a
    plain dict matching ``DiagramResponse``'s shape:
    ``{"elements": [...], "node_count": int, "edge_count": int, "truncated": bool}``.

    If ``max_nodes`` is given and the graph has more nodes than that, the
    graph is truncated down to the ``max_nodes`` highest-degree nodes; any
    edge touching a dropped node is dropped too, and ``"truncated"`` is set
    to ``True``.
    """

    truncated = False

    if max_nodes is not None and graph.number_of_nodes() > max_nodes:
        graph = _truncate_to_top_degree_nodes(graph, max_nodes)
        truncated = True

    elements: list[dict[str, Any]] = [
        {"group": "nodes", "data": _node_element(node_id, attrs)}
        for node_id, attrs in graph.nodes(data=True)
    ]
    elements.extend(
        {"group": "edges", "data": _edge_element(source, target, attrs)}
        for source, target, attrs in graph.edges(data=True)
    )

    return {
        "elements": elements,
        "node_count": graph.number_of_nodes(),
        "edge_count": graph.number_of_edges(),
        "truncated": truncated,
    }
