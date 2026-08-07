"""Slice a neighborhood ("ego graph") around a node out of a lineage graph."""

from __future__ import annotations

from collections.abc import Callable, Iterable

import networkx as nx

_VALID_DIRECTIONS = ("upstream", "downstream", "both")


def _bounded_bfs(
    graph: nx.DiGraph,
    root_id: str,
    depth: int,
    neighbors_of: Callable[[str], Iterable[str]],
) -> set[str]:
    """BFS out from ``root_id`` up to ``depth`` hops using ``neighbors_of``
    (either ``graph.successors`` or ``graph.predecessors``) to expand each
    node. Returns the set of nodes reached, not including the root itself."""

    reached: set[str] = set()
    frontier = {root_id}

    for _ in range(depth):
        next_frontier: set[str] = set()
        for node in frontier:
            for neighbor in neighbors_of(node):
                if neighbor != root_id and neighbor not in reached:
                    next_frontier.add(neighbor)
        if not next_frontier:
            break
        reached |= next_frontier
        frontier = next_frontier

    return reached


def ego_slice(
    graph: nx.DiGraph,
    root_id: str,
    direction: str = "both",
    depth: int = 3,
) -> nx.DiGraph:
    """Return the induced subgraph of the neighborhood around ``root_id``.

    Args:
        graph: The full lineage graph to slice.
        root_id: The node to center the slice on.
        direction: ``"upstream"`` walks predecessors (ancestors, i.e. things
            that feed into ``root_id``), ``"downstream"`` walks successors
            (descendants, i.e. things ``root_id`` feeds into), ``"both"``
            walks both directions.
        depth: Maximum number of hops to walk in each requested direction.

    Returns:
        The induced subgraph containing the root, every node reached within
        ``depth`` hops in the requested direction(s), and only the edges of
        ``graph`` that run between those kept nodes.

    Raises:
        KeyError: If ``root_id`` is not a node in ``graph``.
        ValueError: If ``direction`` is not one of ``"upstream"``,
            ``"downstream"``, or ``"both"``.
    """

    if direction not in _VALID_DIRECTIONS:
        raise ValueError(
            f"Invalid direction {direction!r}; expected one of {_VALID_DIRECTIONS}"
        )

    if root_id not in graph:
        raise KeyError(f"Root node {root_id!r} not found in graph")

    nodes_to_keep = {root_id}

    if direction in ("downstream", "both"):
        nodes_to_keep |= _bounded_bfs(graph, root_id, depth, graph.successors)
    if direction in ("upstream", "both"):
        nodes_to_keep |= _bounded_bfs(graph, root_id, depth, graph.predecessors)

    return graph.subgraph(nodes_to_keep).copy()
