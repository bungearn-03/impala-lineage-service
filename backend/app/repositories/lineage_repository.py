from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.models.lineage import LineageEdge, LineageSource, TransformationType


class LineageRepository:
    def __init__(self, db: Session):
        self.db = db

    def replace_edges_for_target(self, target_object_id: str, edges: list[dict]) -> list[LineageEdge]:
        """Delete previously-computed (non-manual) edges into ``target_object_id``
        and insert the freshly-computed ``edges`` in their place.

        Each dict in ``edges`` must have keys: source_object_id, target_object_id,
        source_column_id (optional), target_column_id (optional), transformation_type,
        transformation_expr (optional), confidence, source_sql (optional), created_by.
        """
        self.db.execute(
            delete(LineageEdge).where(
                LineageEdge.target_object_id == target_object_id,
                LineageEdge.created_by != LineageSource.MANUAL,
            )
        )
        self.db.flush()

        created: list[LineageEdge] = []
        for edge in edges:
            row = LineageEdge(
                source_object_id=edge["source_object_id"],
                target_object_id=edge["target_object_id"],
                source_column_id=edge.get("source_column_id"),
                target_column_id=edge.get("target_column_id"),
                transformation_type=TransformationType(edge.get("transformation_type", "UNKNOWN")),
                transformation_expr=edge.get("transformation_expr"),
                confidence=edge.get("confidence", 1.0),
                source_sql=edge.get("source_sql"),
                created_by=LineageSource(edge.get("created_by", "PARSER")),
            )
            self.db.add(row)
            created.append(row)

        self.db.flush()
        return created

    def get_edges_for_object(self, object_id: str, direction: str = "both") -> list[LineageEdge]:
        stmt = select(LineageEdge).options(
            selectinload(LineageEdge.source_object),
            selectinload(LineageEdge.target_object),
            selectinload(LineageEdge.source_column),
            selectinload(LineageEdge.target_column),
        )
        if direction == "upstream":
            stmt = stmt.where(LineageEdge.target_object_id == object_id)
        elif direction == "downstream":
            stmt = stmt.where(LineageEdge.source_object_id == object_id)
        else:
            stmt = stmt.where(
                (LineageEdge.target_object_id == object_id) | (LineageEdge.source_object_id == object_id)
            )
        return list(self.db.execute(stmt).scalars().all())

    def get_all_edges_for_connection(self, connection_id: str) -> list[LineageEdge]:
        """Every lineage edge whose endpoints both belong to ``connection_id`` --
        used to build the full object/column graph for diagram rendering."""
        from app.models.data_object import DataObject

        stmt = (
            select(LineageEdge)
            .join(DataObject, LineageEdge.target_object_id == DataObject.id)
            .where(DataObject.connection_id == connection_id)
            .options(
                selectinload(LineageEdge.source_object),
                selectinload(LineageEdge.target_object),
                selectinload(LineageEdge.source_column),
                selectinload(LineageEdge.target_column),
            )
        )
        return list(self.db.execute(stmt).scalars().all())

    @staticmethod
    def to_raw_dict(edge: LineageEdge) -> dict:
        """Shape expected by app.graph.graph_builder.build_object_graph / build_column_graph."""
        return {
            "id": edge.id,
            "source_object_id": edge.source_object_id,
            "source_object_name": edge.source_object.full_name if edge.source_object else edge.source_object_id,
            "target_object_id": edge.target_object_id,
            "target_object_name": edge.target_object.full_name if edge.target_object else edge.target_object_id,
            "source_column_id": edge.source_column_id,
            "source_column_name": edge.source_column.name if edge.source_column else None,
            "target_column_id": edge.target_column_id,
            "target_column_name": edge.target_column.name if edge.target_column else None,
            "transformation_type": edge.transformation_type.value,
            "confidence": edge.confidence,
        }
