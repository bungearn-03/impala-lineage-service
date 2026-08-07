"""initial schema

Creates the five core tables (connections, data_objects, columns,
lineage_edges, scan_jobs) and their backing Postgres ENUM types, hand
written to mirror backend/app/models/*.py exactly (no live Postgres was
available in this environment to run `alembic revision --autogenerate`).

Note on enum values: SQLAlchemy's `sa.Enum(SomePyEnum)` persists the
enum MEMBER NAME by default (e.g. "IMPALA"), not `.value`, unless the
model passes `values_callable=...` (none of these models do). The enum
labels below intentionally use member names, not member values, so a
running app using these same model classes reads/writes rows that match
what this migration creates - even where name and value differ (see
ConnectionType: name "IMPALA" / value "impala").

Revision ID: 0001
Revises:
Create Date: 2026-08-02 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# Enum type definitions. create_type=False keeps SQLAlchemy from trying to
# auto-emit CREATE TYPE a second time when the enum is referenced inside
# op.create_table() below; we create/drop each type explicitly and exactly
# once instead.
# ---------------------------------------------------------------------------
connection_type_enum = postgresql.ENUM(
    "IMPALA", "HIVE_METASTORE", name="connection_type", create_type=False
)
auth_mechanism_enum = postgresql.ENUM(
    "NOSASL", "PLAIN", "LDAP", "KERBEROS", name="auth_mechanism", create_type=False
)
object_type_enum = postgresql.ENUM("TABLE", "VIEW", name="object_type", create_type=False)
transformation_type_enum = postgresql.ENUM(
    "DIRECT", "DERIVED", "AGGREGATED", "JOIN", "UNKNOWN",
    name="transformation_type", create_type=False,
)
lineage_source_enum = postgresql.ENUM(
    "PARSER", "AI", "MANUAL", name="lineage_source", create_type=False
)
scan_job_type_enum = postgresql.ENUM(
    "METADATA_SCAN", "LINEAGE_SCAN", name="scan_job_type", create_type=False
)
scan_job_status_enum = postgresql.ENUM(
    "PENDING", "RUNNING", "SUCCESS", "FAILED", name="scan_job_status", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()

    # Create enum types up front (checkfirst keeps this idempotent).
    connection_type_enum.create(bind, checkfirst=True)
    auth_mechanism_enum.create(bind, checkfirst=True)
    object_type_enum.create(bind, checkfirst=True)
    transformation_type_enum.create(bind, checkfirst=True)
    lineage_source_enum.create(bind, checkfirst=True)
    scan_job_type_enum.create(bind, checkfirst=True)
    scan_job_status_enum.create(bind, checkfirst=True)

    # ---- connections ----------------------------------------------------
    op.create_table(
        "connections",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("conn_type", connection_type_enum, nullable=False),
        sa.Column("host", sa.String(length=255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("default_database", sa.String(length=255), nullable=False),
        sa.Column("auth_mechanism", auth_mechanism_enum, nullable=False),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("encrypted_password", sa.String(length=1024), nullable=True),
        sa.Column("use_ssl", sa.Boolean(), nullable=False),
        sa.Column("extra_params", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_connections"),
        sa.UniqueConstraint("name", name="uq_connections_name"),
    )

    # ---- data_objects -----------------------------------------------------
    op.create_table(
        "data_objects",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("connection_id", sa.String(length=36), nullable=False),
        sa.Column("database_name", sa.String(length=255), nullable=False),
        sa.Column("object_name", sa.String(length=255), nullable=False),
        sa.Column("object_type", object_type_enum, nullable=False),
        sa.Column("ddl", sa.Text(), nullable=True),
        sa.Column("view_definition", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_scanned_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_data_objects"),
        sa.ForeignKeyConstraint(
            ["connection_id"], ["connections.id"], name="fk_data_objects_connection_id_connections", ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "connection_id", "database_name", "object_name", name="uq_object_identity"
        ),
    )

    # ---- columns ------------------------------------------------------------
    op.create_table(
        "columns",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("data_object_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("data_type", sa.String(length=255), nullable=False),
        sa.Column("ordinal_position", sa.Integer(), nullable=False),
        sa.Column("is_nullable", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_columns"),
        sa.ForeignKeyConstraint(
            ["data_object_id"], ["data_objects.id"], name="fk_columns_data_object_id_data_objects", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("data_object_id", "name", name="uq_column_identity"),
    )

    # ---- lineage_edges ------------------------------------------------------
    op.create_table(
        "lineage_edges",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_object_id", sa.String(length=36), nullable=False),
        sa.Column("target_object_id", sa.String(length=36), nullable=False),
        sa.Column("source_column_id", sa.String(length=36), nullable=True),
        sa.Column("target_column_id", sa.String(length=36), nullable=True),
        sa.Column("transformation_type", transformation_type_enum, nullable=False),
        sa.Column("transformation_expr", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("source_sql", sa.Text(), nullable=True),
        sa.Column("created_by", lineage_source_enum, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_lineage_edges"),
        sa.ForeignKeyConstraint(
            ["source_object_id"], ["data_objects.id"],
            name="fk_lineage_edges_source_object_id_data_objects", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_object_id"], ["data_objects.id"],
            name="fk_lineage_edges_target_object_id_data_objects", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_column_id"], ["columns.id"],
            name="fk_lineage_edges_source_column_id_columns", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_column_id"], ["columns.id"],
            name="fk_lineage_edges_target_column_id_columns", ondelete="CASCADE",
        ),
    )
    op.create_index("ix_lineage_target_object", "lineage_edges", ["target_object_id"])
    op.create_index("ix_lineage_source_object", "lineage_edges", ["source_object_id"])

    # ---- scan_jobs ------------------------------------------------------
    op.create_table(
        "scan_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("connection_id", sa.String(length=36), nullable=False),
        sa.Column("job_type", scan_job_type_enum, nullable=False),
        sa.Column("status", scan_job_status_enum, nullable=False),
        sa.Column("target_database", sa.String(length=255), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("stats", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_scan_jobs"),
        sa.ForeignKeyConstraint(
            ["connection_id"], ["connections.id"], name="fk_scan_jobs_connection_id_connections", ondelete="CASCADE"
        ),
    )


def downgrade() -> None:
    bind = op.get_bind()

    # Drop tables in reverse dependency order (children before parents).
    op.drop_table("scan_jobs")
    op.drop_index("ix_lineage_source_object", table_name="lineage_edges")
    op.drop_index("ix_lineage_target_object", table_name="lineage_edges")
    op.drop_table("lineage_edges")
    op.drop_table("columns")
    op.drop_table("data_objects")
    op.drop_table("connections")

    # Drop enum types last, in reverse creation order.
    scan_job_status_enum.drop(bind, checkfirst=True)
    scan_job_type_enum.drop(bind, checkfirst=True)
    lineage_source_enum.drop(bind, checkfirst=True)
    transformation_type_enum.drop(bind, checkfirst=True)
    object_type_enum.drop(bind, checkfirst=True)
    auth_mechanism_enum.drop(bind, checkfirst=True)
    connection_type_enum.drop(bind, checkfirst=True)
