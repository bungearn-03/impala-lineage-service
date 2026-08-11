import re
from typing import Callable

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import NotFoundError, ValidationFailedError
from app.core.security import require_api_key
from app.graph.cytoscape_formatter import to_cytoscape_elements
from app.graph.graph_builder import build_column_graph, build_object_graph
from app.graph.graph_filter import ego_slice
from app.models.data_object import DataObject, ObjectType
from app.parsers.schema_relationships import extract_equi_joins
from app.parsers.table_lineage import extract_table_lineage
from app.repositories.lineage_repository import LineageRepository
from app.repositories.object_repository import ObjectRepository
from app.schemas.diagram import DiagramResponse
from app.schemas.dr_diagram import DrDiagramResponse, ObjectIdsRequest

router = APIRouter(prefix="/diagrams", tags=["diagrams"], dependencies=[Depends(require_api_key)])

DEFAULT_MAX_NODES = 300

_PK_REGEX = re.compile(r"PRIMARY\s+KEY\s*\(([^)]+)\)", re.IGNORECASE)


@router.get("/objects/{object_id}", response_model=DiagramResponse)
def get_object_diagram(
    object_id: str,
    direction: str = "both",
    depth: int = 3,
    granularity: str = "table",
    db: Session = Depends(get_db),
):
    obj_repo = ObjectRepository(db)
    lineage_repo = LineageRepository(db)

    obj = obj_repo.get_by_id(object_id)
    if obj is None:
        raise NotFoundError(f"Object {object_id} not found")

    all_edges = lineage_repo.get_all_edges_for_connection(obj.connection_id)
    raw_edges = [LineageRepository.to_raw_dict(edge) for edge in all_edges]

    if granularity == "column":
        graph = build_column_graph(raw_edges)
        candidate_roots = [
            node_id
            for node_id, attrs in graph.nodes(data=True)
            if node_id == object_id or attrs.get("parent_object_id") == object_id
        ]
    else:
        graph = build_object_graph(raw_edges)
        candidate_roots = [object_id] if object_id in graph else []

    if not candidate_roots:
        return {"elements": [], "node_count": 0, "edge_count": 0, "truncated": False}

    nodes_to_keep: set[str] = set()
    for root_id in candidate_roots:
        sliced = ego_slice(graph, root_id, direction=direction, depth=depth)
        nodes_to_keep |= set(sliced.nodes())

    combined = graph.subgraph(nodes_to_keep).copy()
    return to_cytoscape_elements(combined, max_nodes=DEFAULT_MAX_NODES)


@router.get("/databases/{connection_id}/{database_name}", response_model=DiagramResponse)
def get_database_diagram(
    connection_id: str,
    database_name: str,
    db: Session = Depends(get_db),
):
    """Whole-database ER-style diagram: every scanned table/view in
    ``database_name`` as a node (even ones with no lineage at all), with an
    edge for every pair connected by a lineage relationship whose source AND
    target both belong to this database. Table-level only -- a column-level
    graph for an entire database's worth of tables would be unreadably dense.
    """
    obj_repo = ObjectRepository(db)
    lineage_repo = LineageRepository(db)

    objects = obj_repo.list_by_database(connection_id, database_name)
    if not objects:
        raise NotFoundError(f"No objects found for database {database_name!r} on connection {connection_id}")

    object_ids = {obj.id for obj in objects}
    all_edges = lineage_repo.get_all_edges_for_connection(connection_id)
    scoped_edges = [
        edge
        for edge in all_edges
        if edge.source_object_id in object_ids and edge.target_object_id in object_ids
    ]
    raw_edges = [LineageRepository.to_raw_dict(edge) for edge in scoped_edges]

    graph = build_object_graph(raw_edges)

    # Every scanned object becomes a node, whether or not it has lineage --
    # build_object_graph only creates nodes for objects that appear in an
    # edge, and never sets object_type/database_name (it's kept generic), so
    # both need filling in here for every object regardless of edge presence.
    for obj in objects:
        node_attrs = {
            "label": obj.object_name,
            "type": "object",
            "object_type": obj.object_type.value,
            "database_name": obj.database_name,
        }
        if obj.id in graph:
            graph.nodes[obj.id].update(node_attrs)
        else:
            graph.add_node(obj.id, **node_attrs)

    return to_cytoscape_elements(graph, max_nodes=DEFAULT_MAX_NODES)


def _detect_pk_columns(ddl: str | None) -> set[str]:
    """Best-effort primary key detection from a table's DDL text.

    Impala tables generally have no declared primary key at all -- this only
    finds anything for Kudu-backed tables, whose `CREATE TABLE` includes a
    literal `PRIMARY KEY (col1, col2)` clause. Everything else is left to the
    frontend's existing "column participates in a relationship" heuristic
    for marking foreign-key-like columns.
    """
    if not ddl:
        return set()
    match = _PK_REGEX.search(ddl)
    if not match:
        return set()
    return {col.strip(" `\n\t").lower() for col in match.group(1).split(",")}


def _split_table_ref(name: str) -> tuple[str | None, str]:
    """Split a JOIN's table reference into (db-qualifier, bare name) --
    lowercased for case-insensitive matching. The qualifier is None when the
    reference carries none (the common case within a single database)."""
    parts = name.split(".")
    if len(parts) >= 2:
        return parts[-2].lower(), parts[-1].lower()
    return None, parts[-1].lower()


def _resolve_table_ref(
    ref: str,
    default_database: str,
    index_qualified: dict[tuple[str, str], str],
    index_by_bare: dict[str, list[str]],
) -> str | None:
    """Resolve a JOIN/source table reference to a key in the `tables` dict.

    Prefers an explicit db-qualifier on the reference itself, then falls
    back to the view's OWN database (an unqualified reference in real
    Impala/Hive SQL resolves there, not to some other database that happens
    to have a same-named table) and finally to a same-name match elsewhere
    IF it's unambiguous. Single-database callers only ever populate
    `index_qualified`/`index_by_bare` for that one database, so this
    degrades to the original bare-name lookup with no behavior change.
    """
    qualifier, bare = _split_table_ref(ref)
    if qualifier:
        hit = index_qualified.get((qualifier, bare))
        if hit:
            return hit
    hit = index_qualified.get((default_database.lower(), bare))
    if hit:
        return hit
    candidates = index_by_bare.get(bare, [])
    return candidates[0] if len(candidates) == 1 else None


def _build_dr_diagram_payload(objects: list[DataObject], key_fn: Callable[[DataObject], str]) -> dict:
    """Shared DR/ER diagram builder used by both the single-database and the
    cross-database (by-ids) endpoints. `key_fn` decides how each object is
    keyed in the returned `tables` dict (and therefore in relationships'
    from_table/to_table) -- bare object name for the single-database case
    (unambiguous, and keeps that endpoint's response unchanged), a
    database-qualified key for the cross-database case (multiple databases
    can otherwise contain same-named tables that would silently collide).
    """
    table_objs = [obj for obj in objects if obj.object_type == ObjectType.TABLE]
    all_view_objs = [obj for obj in objects if obj.object_type == ObjectType.VIEW]
    parseable_view_objs = [obj for obj in all_view_objs if obj.view_definition]

    # JOIN pairs only ever make sense between two real tables, so the
    # qualified/bare indexes used for JOIN resolution are TABLE-only.
    table_index_qualified: dict[tuple[str, str], str] = {}
    table_index_by_bare: dict[str, list[str]] = {}
    for obj in table_objs:
        key = key_fn(obj)
        table_index_qualified[(obj.database_name.lower(), obj.object_name.lower())] = key
        table_index_by_bare.setdefault(obj.object_name.lower(), []).append(key)

    # View -> source dependency edges can point at a table OR another view,
    # so this second pair of indexes additionally covers views.
    all_index_qualified: dict[tuple[str, str], str] = dict(table_index_qualified)
    all_index_by_bare: dict[str, list[str]] = {bare: list(keys) for bare, keys in table_index_by_bare.items()}
    for obj in all_view_objs:
        key = key_fn(obj)
        all_index_qualified[(obj.database_name.lower(), obj.object_name.lower())] = key
        all_index_by_bare.setdefault(obj.object_name.lower(), []).append(key)

    tables: dict[str, dict] = {}
    for obj in table_objs:
        pk_columns = _detect_pk_columns(obj.ddl)
        tables[key_fn(obj)] = {
            "name": obj.object_name,
            "object_type": "TABLE",
            "columns": [
                {
                    "name": col.name,
                    "type": col.data_type,
                    "is_key": col.name.lower() in pk_columns,
                    "description": "",
                }
                for col in obj.columns
            ],
        }
    for obj in all_view_objs:
        tables[key_fn(obj)] = {
            "name": obj.object_name,
            "object_type": "VIEW",
            "columns": [
                {
                    "name": col.name,
                    "type": col.data_type,
                    "is_key": False,
                    "description": "",
                }
                for col in obj.columns
            ],
        }

    relationships: list[dict] = []
    seen_pairs: set[tuple[str, str]] = set()
    for view in parseable_view_objs:
        try:
            pairs = extract_equi_joins(view.view_definition)
        except Exception:  # noqa: BLE001 - one unparsable view must not break the whole diagram
            continue

        for pair in pairs:
            left_key = _resolve_table_ref(
                pair["left_table"], view.database_name, table_index_qualified, table_index_by_bare
            )
            right_key = _resolve_table_ref(
                pair["right_table"], view.database_name, table_index_qualified, table_index_by_bare
            )
            if not left_key or not right_key or left_key == right_key:
                continue

            dedup_key = tuple(
                sorted([f"{left_key}.{pair['left_col']}", f"{right_key}.{pair['right_col']}"])
            )
            if dedup_key in seen_pairs:
                continue
            seen_pairs.add(dedup_key)

            relationships.append(
                {
                    "from_table": left_key,
                    "from_col": pair["left_col"],
                    "to_table": right_key,
                    "to_col": pair["right_col"],
                    "via_view": view.object_name,
                    "relationship_type": "JOIN",
                }
            )

    # View -> source-table/source-view dependency edges (a view reads from
    # these objects, regardless of whether its SQL has any parseable JOIN at
    # all) -- without this, a view scanned with no equi-join in its SQL (e.g.
    # a single-table SELECT) would render as a fully disconnected box, even
    # though it plainly depends on that one source.
    seen_view_sources: set[tuple[str, str]] = set()
    for view in parseable_view_objs:
        try:
            sources = extract_table_lineage(view.view_definition)["sources"]
        except Exception:  # noqa: BLE001 - one unparsable view must not break the whole diagram
            continue

        view_key = key_fn(view)
        for source in sources:
            source_key = _resolve_table_ref(source, view.database_name, all_index_qualified, all_index_by_bare)
            if not source_key or source_key == view_key:
                continue
            pair = (source_key, view_key)
            if pair in seen_view_sources:
                continue
            seen_view_sources.add(pair)

            relationships.append(
                {
                    "from_table": source_key,
                    "from_col": "",
                    "to_table": view_key,
                    "to_col": "",
                    "via_view": view.object_name,
                    "relationship_type": "VIEW_SOURCE",
                }
            )

    return {
        "tables": tables,
        "relationships": relationships,
        "table_count": len(table_objs),
        "view_count": len(all_view_objs),
        "relationship_count": len(relationships),
    }


@router.get("/dr/{connection_id}/{database_name}", response_model=DrDiagramResponse)
def get_dr_diagram(
    connection_id: str,
    database_name: str,
    db: Session = Depends(get_db),
):
    """DBeaver-style ER/DR diagram data for a whole database: every scanned
    TABLE with its real columns (real primary keys where detectable, e.g.
    Kudu tables), plus foreign-key-style relationships inferred by parsing
    every scanned VIEW's JOIN conditions for `table.col = table.col`
    equalities -- the schema-level relationships a DR diagram is meant to
    show, as distinct from column-lineage *provenance* (see the plain
    /diagrams/objects and /diagrams/databases endpoints for that).
    """
    obj_repo = ObjectRepository(db)
    objects = obj_repo.list_by_database(connection_id, database_name)
    if not objects:
        raise NotFoundError(f"No objects found for database {database_name!r} on connection {connection_id}")

    payload = _build_dr_diagram_payload(objects, key_fn=lambda obj: obj.object_name)
    return {"database": database_name, **payload}


@router.post("/dr/by-ids", response_model=DrDiagramResponse)
def get_dr_diagram_by_ids(
    payload: ObjectIdsRequest,
    db: Session = Depends(get_db),
):
    """Same DR/ER diagram shape as /dr/{connection_id}/{database_name}, but
    for an arbitrary hand-picked set of objects that may span multiple
    databases (always within one connection) -- backs the custom diagram
    picker. Tables are keyed by `database.object_name` instead of the bare
    object name so two different databases' same-named tables don't collide;
    ERDiagram.tsx needs no changes for this since it already renders
    whatever string is used as the dict key as the table's header label.
    """
    if not payload.object_ids:
        raise ValidationFailedError("object_ids must not be empty")

    obj_repo = ObjectRepository(db)
    objects = obj_repo.get_by_ids(payload.object_ids)
    if not objects:
        raise NotFoundError("None of the given object_ids were found")

    connection_ids = {obj.connection_id for obj in objects}
    if len(connection_ids) > 1:
        raise ValidationFailedError("All selected objects must belong to the same connection")

    result = _build_dr_diagram_payload(
        objects, key_fn=lambda obj: f"{obj.database_name}.{obj.object_name}"
    )
    database_names = sorted({obj.database_name for obj in objects})
    label = (
        database_names[0]
        if len(database_names) == 1
        else f"{len(database_names)} databases ({', '.join(database_names[:3])}{', ...' if len(database_names) > 3 else ''})"
    )
    return {"database": label, **result}
