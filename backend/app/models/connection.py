import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Enum, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ConnectionType(str, enum.Enum):
    IMPALA = "impala"
    HIVE_METASTORE = "hive_metastore"


class AuthMechanism(str, enum.Enum):
    NOSASL = "NOSASL"
    PLAIN = "PLAIN"
    LDAP = "LDAP"
    KERBEROS = "KERBEROS"


class Connection(Base):
    __tablename__ = "connections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    conn_type: Mapped[ConnectionType] = mapped_column(Enum(ConnectionType), nullable=False)

    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    default_database: Mapped[str] = mapped_column(String(255), default="default")

    auth_mechanism: Mapped[AuthMechanism] = mapped_column(Enum(AuthMechanism), default=AuthMechanism.NOSASL)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    encrypted_password: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    use_ssl: Mapped[bool] = mapped_column(Boolean, default=False)
    extra_params: Mapped[dict] = mapped_column(JSON, default=dict)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    data_objects: Mapped[list["DataObject"]] = relationship(
        back_populates="connection", cascade="all, delete-orphan"
    )
    scan_jobs: Mapped[list["ScanJob"]] = relationship(
        back_populates="connection", cascade="all, delete-orphan"
    )
    custom_diagram_presets: Mapped[list["CustomDiagramPreset"]] = relationship(
        back_populates="connection", cascade="all, delete-orphan"
    )
