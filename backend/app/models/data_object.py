import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ObjectType(str, enum.Enum):
    TABLE = "TABLE"
    VIEW = "VIEW"


class DataObject(Base):
    __tablename__ = "data_objects"
    __table_args__ = (
        UniqueConstraint("connection_id", "database_name", "object_name", name="uq_object_identity"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    connection_id: Mapped[str] = mapped_column(ForeignKey("connections.id", ondelete="CASCADE"), nullable=False)

    database_name: Mapped[str] = mapped_column(String(255), nullable=False)
    object_name: Mapped[str] = mapped_column(String(255), nullable=False)
    object_type: Mapped[ObjectType] = mapped_column(Enum(ObjectType), nullable=False)

    ddl: Mapped[str | None] = mapped_column(Text, nullable=True)
    view_definition: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    connection: Mapped["Connection"] = relationship(back_populates="data_objects")
    columns: Mapped[list["Column"]] = relationship(
        back_populates="data_object", cascade="all, delete-orphan", order_by="Column.ordinal_position"
    )

    @property
    def full_name(self) -> str:
        return f"{self.database_name}.{self.object_name}"
