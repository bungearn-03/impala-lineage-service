from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.connectors.base import ObjectMetadata
from app.models.column import Column
from app.models.data_object import DataObject, ObjectType


class ObjectRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, object_id: str) -> DataObject | None:
        stmt = (
            select(DataObject)
            .where(DataObject.id == object_id)
            .options(selectinload(DataObject.columns))
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_identity(self, connection_id: str, database_name: str, object_name: str) -> DataObject | None:
        stmt = select(DataObject).where(
            DataObject.connection_id == connection_id,
            DataObject.database_name == database_name,
            DataObject.object_name == object_name,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list_by_connection(self, connection_id: str) -> list[DataObject]:
        stmt = select(DataObject).where(DataObject.connection_id == connection_id)
        return list(self.db.execute(stmt).scalars().all())

    def list_by_database(self, connection_id: str, database_name: str) -> list[DataObject]:
        stmt = select(DataObject).where(
            DataObject.connection_id == connection_id,
            DataObject.database_name == database_name,
        )
        return list(self.db.execute(stmt).scalars().all())

    def list_databases_summary(self, connection_id: str) -> list[dict]:
        """Returns [{"database_name": str, "table_count": int, "view_count": int}, ...]."""
        objects = self.list_by_connection(connection_id)
        summary: dict[str, dict] = {}
        for obj in objects:
            entry = summary.setdefault(
                obj.database_name, {"database_name": obj.database_name, "table_count": 0, "view_count": 0}
            )
            if obj.object_type == ObjectType.VIEW:
                entry["view_count"] += 1
            else:
                entry["table_count"] += 1
        return sorted(summary.values(), key=lambda e: e["database_name"])

    def upsert_object(self, connection_id: str, metadata: ObjectMetadata) -> DataObject:
        """Create or update a DataObject (and fully replace its columns) from scanned metadata."""
        existing = self.get_by_identity(connection_id, metadata.database_name, metadata.object_name)

        if existing is None:
            existing = DataObject(
                connection_id=connection_id,
                database_name=metadata.database_name,
                object_name=metadata.object_name,
                object_type=ObjectType(metadata.object_type),
            )
            self.db.add(existing)
            self.db.flush()

        existing.object_type = ObjectType(metadata.object_type)
        existing.ddl = metadata.ddl
        existing.view_definition = metadata.view_definition
        existing.last_scanned_at = datetime.now(timezone.utc)

        existing.columns.clear()
        self.db.flush()
        for col in metadata.columns:
            existing.columns.append(
                Column(
                    name=col.name,
                    data_type=col.data_type,
                    ordinal_position=col.ordinal_position,
                    is_nullable=col.is_nullable,
                )
            )

        self.db.flush()
        return existing

    def get_column_by_name(self, data_object_id: str, column_name: str) -> Column | None:
        stmt = select(Column).where(Column.data_object_id == data_object_id, Column.name == column_name)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_columns_schema(self, data_object: DataObject) -> dict[str, str]:
        """Returns {column_name: data_type} for a single object -- used to build
        the nested schema dict handed to app.parsers.column_lineage / app.ai."""
        return {col.name: col.data_type for col in data_object.columns}
