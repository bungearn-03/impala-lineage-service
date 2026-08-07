import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Column(Base):
    __tablename__ = "columns"
    __table_args__ = (
        UniqueConstraint("data_object_id", "name", name="uq_column_identity"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    data_object_id: Mapped[str] = mapped_column(ForeignKey("data_objects.id", ondelete="CASCADE"), nullable=False)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    data_type: Mapped[str] = mapped_column(String(255), nullable=False)
    ordinal_position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_nullable: Mapped[bool] = mapped_column(Boolean, default=True)

    data_object: Mapped["DataObject"] = relationship(back_populates="columns")
