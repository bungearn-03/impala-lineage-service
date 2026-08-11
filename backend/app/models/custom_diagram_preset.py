import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class CustomDiagramPreset(Base):
    """A named, saved selection of DataObject ids (any mix of databases,
    always within one connection) that the custom diagram picker re-fetches
    and renders as an ER diagram -- lets a user re-open a hand-picked
    cross-database set of tables without re-selecting them every time."""

    __tablename__ = "custom_diagram_presets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    connection_id: Mapped[str] = mapped_column(ForeignKey("connections.id", ondelete="CASCADE"), nullable=False)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    object_ids: Mapped[list[str]] = mapped_column(JSON, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    connection: Mapped["Connection"] = relationship(back_populates="custom_diagram_presets")
