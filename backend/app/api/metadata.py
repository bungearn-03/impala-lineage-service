from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import NotFoundError
from app.core.security import require_api_key
from app.repositories.object_repository import ObjectRepository
from app.schemas.metadata import DatabaseSummary, DataObjectDetail, DataObjectSummary

router = APIRouter(tags=["metadata"], dependencies=[Depends(require_api_key)])


@router.get("/connections/{connection_id}/databases", response_model=list[DatabaseSummary])
def list_databases(connection_id: str, db: Session = Depends(get_db)) -> list[dict]:
    return ObjectRepository(db).list_databases_summary(connection_id)


@router.get(
    "/connections/{connection_id}/databases/{database_name}/objects",
    response_model=list[DataObjectSummary],
)
def list_objects(connection_id: str, database_name: str, db: Session = Depends(get_db)):
    return ObjectRepository(db).list_by_database(connection_id, database_name)


@router.get("/objects/{object_id}", response_model=DataObjectDetail)
def get_object(object_id: str, db: Session = Depends(get_db)):
    obj = ObjectRepository(db).get_by_id(object_id)
    if obj is None:
        raise NotFoundError(f"Object {object_id} not found")
    return obj
