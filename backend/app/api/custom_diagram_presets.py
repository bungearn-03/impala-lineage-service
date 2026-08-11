from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import NotFoundError
from app.core.security import require_api_key
from app.models.custom_diagram_preset import CustomDiagramPreset
from app.repositories.custom_diagram_preset_repository import CustomDiagramPresetRepository
from app.schemas.custom_diagram_preset import (
    CustomDiagramPresetCreate,
    CustomDiagramPresetRead,
    CustomDiagramPresetUpdate,
)

router = APIRouter(
    prefix="/connections/{connection_id}/custom-diagrams",
    tags=["custom-diagrams"],
    dependencies=[Depends(require_api_key)],
)


def _get_or_404(db: Session, connection_id: str, preset_id: str) -> CustomDiagramPreset:
    preset = CustomDiagramPresetRepository(db).get_by_id(preset_id)
    if preset is None or preset.connection_id != connection_id:
        raise NotFoundError(f"Custom diagram preset {preset_id} not found")
    return preset


@router.get("", response_model=list[CustomDiagramPresetRead])
def list_presets(connection_id: str, db: Session = Depends(get_db)):
    return CustomDiagramPresetRepository(db).list_by_connection(connection_id)


@router.post("", response_model=CustomDiagramPresetRead, status_code=status.HTTP_201_CREATED)
def create_preset(connection_id: str, payload: CustomDiagramPresetCreate, db: Session = Depends(get_db)):
    preset = CustomDiagramPresetRepository(db).create(connection_id, payload.name, payload.object_ids)
    db.commit()
    db.refresh(preset)
    return preset


@router.put("/{preset_id}", response_model=CustomDiagramPresetRead)
def update_preset(
    connection_id: str, preset_id: str, payload: CustomDiagramPresetUpdate, db: Session = Depends(get_db)
):
    preset = _get_or_404(db, connection_id, preset_id)
    CustomDiagramPresetRepository(db).update(preset, name=payload.name, object_ids=payload.object_ids)
    db.commit()
    db.refresh(preset)
    return preset


@router.delete("/{preset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_preset(connection_id: str, preset_id: str, db: Session = Depends(get_db)):
    preset = _get_or_404(db, connection_id, preset_id)
    CustomDiagramPresetRepository(db).delete(preset)
    db.commit()
