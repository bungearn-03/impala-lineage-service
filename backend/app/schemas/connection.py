from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.connection import AuthMechanism, ConnectionType


class ConnectionBase(BaseModel):
    name: str
    conn_type: ConnectionType
    host: str
    port: int
    default_database: str = "default"
    auth_mechanism: AuthMechanism = AuthMechanism.NOSASL
    username: str | None = None
    use_ssl: bool = False
    extra_params: dict = Field(default_factory=dict)


class ConnectionCreate(ConnectionBase):
    password: str | None = None


class ConnectionUpdate(BaseModel):
    name: str | None = None
    host: str | None = None
    port: int | None = None
    default_database: str | None = None
    auth_mechanism: AuthMechanism | None = None
    username: str | None = None
    password: str | None = None
    use_ssl: bool | None = None
    extra_params: dict | None = None
    is_active: bool | None = None


class ConnectionRead(ConnectionBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ConnectionTestResult(BaseModel):
    success: bool
    message: str
    databases_visible: int | None = None
