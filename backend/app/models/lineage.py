import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class TransformationType(str, enum.Enum):
    DIRECT = "DIRECT"
    DERIVED = "DERIVED"
    AGGREGATED = "AGGREGATED"
    JOIN = "JOIN"
    UNKNOWN = "UNKNOWN"


class LineageSource(str, enum.Enum):
    PARSER = "PARSER"
    AI = "AI"
    MANUAL = "MANUAL"


class LineageEdge(Base):
    """A single upstream -> downstream edge, optionally at column granularity.

    Table-level edges have source_column_id/target_column_id = NULL.
    """

    __tablename__ = "lineage_edges"
    __table_args__ = (
        Index("ix_lineage_target_object", "target_object_id"),
        Index("ix_lineage_source_object", "source_object_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    source_object_id: Mapped[str] = mapped_column(ForeignKey("data_objects.id", ondelete="CASCADE"), nullable=False)
    target_object_id: Mapped[str] = mapped_column(ForeignKey("data_objects.id", ondelete="CASCADE"), nullable=False)

    source_column_id: Mapped[str | None] = mapped_column(ForeignKey("columns.id", ondelete="CASCADE"), nullable=True)
    target_column_id: Mapped[str | None] = mapped_column(ForeignKey("columns.id", ondelete="CASCADE"), nullable=True)

    transformation_type: Mapped[TransformationType] = mapped_column(
        Enum(TransformationType), default=TransformationType.UNKNOWN
    )
    transformation_expr: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    source_sql: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[LineageSource] = mapped_column(Enum(LineageSource), default=LineageSource.PARSER)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    source_object: Mapped["DataObject"] = relationship(foreign_keys=[source_object_id])
    target_object: Mapped["DataObject"] = relationship(foreign_keys=[target_object_id])
    source_column: Mapped["Column | None"] = relationship(foreign_keys=[source_column_id])
    target_column: Mapped["Column | None"] = relationship(foreign_keys=[target_column_id])
