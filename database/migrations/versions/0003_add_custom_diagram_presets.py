"""add custom_diagram_presets table

Backs the custom cross-database ER diagram picker: a named, saved list of
DataObject ids (any mix of databases within one connection) that the
frontend re-fetches and renders through the existing DR diagram renderer.
Mirrors adding backend/app/models/custom_diagram_preset.py.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-10 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "custom_diagram_presets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("connection_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("object_ids", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_custom_diagram_presets"),
        sa.ForeignKeyConstraint(
            ["connection_id"], ["connections.id"],
            name="fk_custom_diagram_presets_connection_id_connections", ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_custom_diagram_presets_connection_id", "custom_diagram_presets", ["connection_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_custom_diagram_presets_connection_id", table_name="custom_diagram_presets")
    op.drop_table("custom_diagram_presets")
