from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors import get_connector
from app.core.database import get_db
from app.core.exceptions import NotFoundError
from app.core.security import encrypt_secret, require_api_key
from app.models.connection import Connection
from app.schemas.connection import (
    ConnectionCreate,
    ConnectionRead,
    ConnectionTestResult,
    ConnectionUpdate,
)

router = APIRouter(prefix="/connections", tags=["connections"], dependencies=[Depends(require_api_key)])


def _get_or_404(db: Session, connection_id: str) -> Connection:
    connection = db.get(Connection, connection_id)
    if connection is None:
        raise NotFoundError(f"Connection {connection_id} not found")
    return connection


@router.get("", response_model=list[ConnectionRead])
def list_connections(db: Session = Depends(get_db)) -> list[Connection]:
    return list(db.execute(select(Connection).order_by(Connection.name)).scalars().all())


@router.post("", response_model=ConnectionRead, status_code=status.HTTP_201_CREATED)
def create_connection(payload: ConnectionCreate, db: Session = Depends(get_db)) -> Connection:
    connection = Connection(
        name=payload.name,
        conn_type=payload.conn_type,
        host=payload.host,
        port=payload.port,
        default_database=payload.default_database,
        auth_mechanism=payload.auth_mechanism,
        username=payload.username,
        encrypted_password=encrypt_secret(payload.password) if payload.password else None,
        use_ssl=payload.use_ssl,
        extra_params=payload.extra_params,
    )
    db.add(connection)
    db.commit()
    db.refresh(connection)
    return connection


@router.get("/{connection_id}", response_model=ConnectionRead)
def get_connection(connection_id: str, db: Session = Depends(get_db)) -> Connection:
    return _get_or_404(db, connection_id)


@router.put("/{connection_id}", response_model=ConnectionRead)
def update_connection(connection_id: str, payload: ConnectionUpdate, db: Session = Depends(get_db)) -> Connection:
    connection = _get_or_404(db, connection_id)

    update_data = payload.model_dump(exclude_unset=True, exclude={"password"})
    for field, value in update_data.items():
        setattr(connection, field, value)

    if payload.password is not None:
        connection.encrypted_password = encrypt_secret(payload.password) if payload.password else None

    db.commit()
    db.refresh(connection)
    return connection


@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_connection(connection_id: str, db: Session = Depends(get_db)) -> None:
    connection = _get_or_404(db, connection_id)
    db.delete(connection)
    db.commit()


@router.post("/{connection_id}/test", response_model=ConnectionTestResult)
def test_connection(connection_id: str, db: Session = Depends(get_db)) -> ConnectionTestResult:
    connection = _get_or_404(db, connection_id)

    connector = get_connector(connection)
    try:
        success, message = connector.test_connection()
        databases_visible = None
        if success:
            try:
                databases_visible = len(connector.list_databases())
            except Exception:  # noqa: BLE001 - test succeeded even if listing databases fails
                databases_visible = None
        return ConnectionTestResult(success=success, message=message, databases_visible=databases_visible)
    finally:
        connector.close()
