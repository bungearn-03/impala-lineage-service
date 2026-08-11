from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.custom_diagram_preset import CustomDiagramPreset


class CustomDiagramPresetRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_by_connection(self, connection_id: str) -> list[CustomDiagramPreset]:
        stmt = (
            select(CustomDiagramPreset)
            .where(CustomDiagramPreset.connection_id == connection_id)
            .order_by(CustomDiagramPreset.name)
        )
        return list(self.db.execute(stmt).scalars().all())

    def get_by_id(self, preset_id: str) -> CustomDiagramPreset | None:
        return self.db.get(CustomDiagramPreset, preset_id)

    def create(self, connection_id: str, name: str, object_ids: list[str]) -> CustomDiagramPreset:
        preset = CustomDiagramPreset(connection_id=connection_id, name=name, object_ids=object_ids)
        self.db.add(preset)
        self.db.flush()
        return preset

    def update(
        self, preset: CustomDiagramPreset, *, name: str | None = None, object_ids: list[str] | None = None
    ) -> CustomDiagramPreset:
        if name is not None:
            preset.name = name
        if object_ids is not None:
            preset.object_ids = object_ids
        self.db.flush()
        return preset

    def delete(self, preset: CustomDiagramPreset) -> None:
        self.db.delete(preset)
        self.db.flush()
