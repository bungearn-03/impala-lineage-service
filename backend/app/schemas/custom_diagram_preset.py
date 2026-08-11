from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CustomDiagramPresetCreate(BaseModel):
    name: str
    object_ids: list[str]


class CustomDiagramPresetUpdate(BaseModel):
    name: str | None = None
    object_ids: list[str] | None = None


class CustomDiagramPresetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    connection_id: str
    name: str
    object_ids: list[str]
    created_at: datetime
    updated_at: datetime
