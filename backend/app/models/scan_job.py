import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ScanJobType(str, enum.Enum):
    METADATA_SCAN = "METADATA_SCAN"
    LINEAGE_SCAN = "LINEAGE_SCAN"


class ScanJobStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ScanJob(Base):
    __tablename__ = "scan_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    connection_id: Mapped[str] = mapped_column(ForeignKey("connections.id", ondelete="CASCADE"), nullable=False)

    job_type: Mapped[ScanJobType] = mapped_column(Enum(ScanJobType), nullable=False)
    status: Mapped[ScanJobStatus] = mapped_column(Enum(ScanJobStatus), default=ScanJobStatus.PENDING)

    target_database: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    stats: Mapped[dict] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    connection: Mapped["Connection"] = relationship(back_populates="scan_jobs")
