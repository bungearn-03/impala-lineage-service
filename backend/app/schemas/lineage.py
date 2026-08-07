from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.lineage import LineageSource, TransformationType


class LineageEndpoint(BaseModel):
    object_id: str
    object_full_name: str
    column_id: str | None = None
    column_name: str | None = None


class LineageEdgeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source: LineageEndpoint
    target: LineageEndpoint
    transformation_type: TransformationType
    transformation_expr: str | None
    confidence: float
    source_sql: str | None
    created_by: LineageSource
    created_at: datetime


class LineageQuery(BaseModel):
    object_id: str
    direction: str = "both"  # "upstream" | "downstream" | "both"
    depth: int = 3
    column_name: str | None = None
