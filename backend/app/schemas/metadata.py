from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.data_object import ObjectType


class ColumnRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    data_type: str
    ordinal_position: int
    is_nullable: bool


class DataObjectSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    connection_id: str
    database_name: str
    object_name: str
    object_type: ObjectType
    last_scanned_at: datetime | None

    @property
    def full_name(self) -> str:
        return f"{self.database_name}.{self.object_name}"


class DataObjectDetail(DataObjectSummary):
    ddl: str | None
    view_definition: str | None
    columns: list[ColumnRead] = []


class DatabaseSummary(BaseModel):
    database_name: str
    table_count: int
    view_count: int
