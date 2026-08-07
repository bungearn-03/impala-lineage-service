import re

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import NotFoundError
from app.core.security import require_api_key
from app.graph.cytoscape_formatter import to_cytoscape_elements
from app.graph.graph_builder import build_column_graph, build_object_graph
from app.graph.graph_filter import ego_slice
from app.models.data_object import ObjectType
from app.parsers.schema_relationships import extract_equi_joins
from app.parsers.table_lineage import extract_table_lineage
from app.repositories.lineage_repository import LineageRepository
from app.repositories.object_repository import ObjectRepository
from app.schemas.diagram import DiagramResponse
from app.schemas.dr_diagram import DrDiagramResponse

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


def _bare_table_name(name: str) -> str:
    """Strip any db-qualifier a JOIN's table reference may carry -- callers
    here are always scoped to a single database already, so only the last
    segment is relevant for matching against that database's known tables."""
    return name.split(".")[-1].lower()


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

    table_objs = [obj for obj in objects if obj.object_type == ObjectType.TABLE]
    all_view_objs = [obj for obj in objects if obj.object_type == ObjectType.VIEW]
    parseable_view_objs = [obj for obj in all_view_objs if obj.view_definition]
    known_table_names = {obj.object_name.lower(): obj.object_name for obj in table_objs}

    tables: dict[str, dict] = {}
    for obj in table_objs:
        pk_columns = _detect_pk_columns(obj.ddl)
        tables[obj.object_name] = {
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
        tables[obj.object_name] = {
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

    # Known object names (tables AND views) a view's referenced tables can
    # resolve to -- used below for the view->source dependency edges, as
    # distinct from `known_table_names` (TABLE-only) which the JOIN-pair
    # matching keeps using, since a JOIN condition only ever makes sense
    # between two real tables.
    known_all_names = {**known_table_names, **{obj.object_name.lower(): obj.object_name for obj in all_view_objs}}

    relationships: list[dict] = []
    seen_pairs: set[tuple[str, str]] = set()
    for view in parseable_view_objs:
        try:
            pairs = extract_equi_joins(view.view_definition)
        except Exception:  # noqa: BLE001 - one unparsable view must not break the whole diagram
            continue

        for pair in pairs:
            left_name = known_table_names.get(_bare_table_name(pair["left_table"]))
            right_name = known_table_names.get(_bare_table_name(pair["right_table"]))
            if not left_name or not right_name or left_name == right_name:
                continue

            dedup_key = tuple(
                sorted([f"{left_name}.{pair['left_col']}", f"{right_name}.{pair['right_col']}"])
            )
            if dedup_key in seen_pairs:
                continue
            seen_pairs.add(dedup_key)

            relationships.append(
                {
                    "from_table": left_name,
                    "from_col": pair["left_col"],
                    "to_table": right_name,
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

        for source in sources:
            source_name = known_all_names.get(_bare_table_name(source))
            if not source_name or source_name == view.object_name:
                continue
            pair = (source_name, view.object_name)
            if pair in seen_view_sources:
                continue
            seen_view_sources.add(pair)

            relationships.append(
                {
                    "from_table": source_name,
                    "from_col": "",
                    "to_table": view.object_name,
                    "to_col": "",
                    "via_view": view.object_name,
                    "relationship_type": "VIEW_SOURCE",
                }
            )

    return {
        "database": database_name,
        "tables": tables,
        "relationships": relationships,
        "table_count": len(table_objs),
        "view_count": len(all_view_objs),
        "relationship_count": len(relationships),
    }
