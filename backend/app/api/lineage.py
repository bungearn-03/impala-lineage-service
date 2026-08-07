from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import NotFoundError
from app.core.security import require_api_key
from app.graph.graph_builder import build_column_graph, build_object_graph
from app.graph.graph_filter import ego_slice
from app.models.lineage import LineageEdge
from app.repositories.lineage_repository import LineageRepository
from app.repositories.object_repository import ObjectRepository
from app.schemas.lineage import LineageEdgeRead, LineageEndpoint

router = APIRouter(prefix="/lineage", tags=["lineage"], dependencies=[Depends(require_api_key)])


def _to_lineage_edge_read(edge: LineageEdge) -> LineageEdgeRead:
    return LineageEdgeRead(
        id=edge.id,
        source=LineageEndpoint(
            object_id=edge.source_object_id,
            object_full_name=edge.source_object.full_name,
            column_id=edge.source_column_id,
            column_name=edge.source_column.name if edge.source_column else None,
        ),
        target=LineageEndpoint(
            object_id=edge.target_object_id,
            object_full_name=edge.target_object.full_name,
            column_id=edge.target_column_id,
            column_name=edge.target_column.name if edge.target_column else None,
        ),
        transformation_type=edge.transformation_type,
        transformation_expr=edge.transformation_expr,
        confidence=edge.confidence,
        source_sql=edge.source_sql,
        created_by=edge.created_by,
        created_at=edge.created_at,
    )


@router.get("/objects/{object_id}", response_model=list[LineageEdgeRead])
def get_object_lineage(
    object_id: str,
    direction: str = "both",
    depth: int = 3,
    column_name: str | None = None,
    db: Session = Depends(get_db),
) -> list[LineageEdgeRead]:
    obj_repo = ObjectRepository(db)
    lineage_repo = LineageRepository(db)

    obj = obj_repo.get_by_id(object_id)
    if obj is None:
        raise NotFoundError(f"Object {object_id} not found")

    all_edges = lineage_repo.get_all_edges_for_connection(obj.connection_id)
    edge_by_id = {edge.id: edge for edge in all_edges}
    raw_edges = [LineageRepository.to_raw_dict(edge) for edge in all_edges]

    if column_name:
        column = obj_repo.get_column_by_name(object_id, column_name)
        if column is None:
            raise NotFoundError(f"Column {column_name} not found on object {object_id}")
        graph = build_column_graph(raw_edges)
        root_id = f"{object_id}::{column.id}"
    else:
        graph = build_object_graph(raw_edges)
        root_id = object_id

    if root_id not in graph:
        return []

    sliced = ego_slice(graph, root_id, direction=direction, depth=depth)

    result_edge_ids: set[str] = set()
    for _, _, attrs in sliced.edges(data=True):
        for contributing in attrs.get("contributing_edges", []):
            edge_id = contributing.get("id")
            if edge_id:
                result_edge_ids.add(edge_id)

    result_edges = [edge_by_id[edge_id] for edge_id in result_edge_ids if edge_id in edge_by_id]
    result_edges.sort(key=lambda e: e.created_at)

    return [_to_lineage_edge_read(edge) for edge in result_edges]
