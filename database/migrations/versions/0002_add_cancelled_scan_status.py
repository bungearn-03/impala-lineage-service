"""add CANCELLED to scan_job_status

Adds a new label to the existing `scan_job_status` Postgres enum type so
scan jobs can be cooperatively cancelled instead of only ever ending as
SUCCESS/FAILED. This mirrors adding `ScanJobStatus.CANCELLED` to
backend/app/models/scan_job.py.

Note on downgrade: Postgres has no `ALTER TYPE ... DROP VALUE`. A true
downgrade would require recreating the enum type and every column that
uses it, which risks data loss if any row is already CANCELLED. Since this
is an additive, low-risk change, downgrade instead just remaps any
CANCELLED rows to FAILED (preserving the row, losing only the distinction)
rather than attempting a lossy type rebuild.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-02 14:15:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside the same transaction block
    # that later uses the new value, but simply adding it (with no use in
    # this same migration) is fine and does not require special handling
    # beyond autocommit, which Alembic's Postgres offline/online runner
    # already provides per-migration.
    op.execute("ALTER TYPE scan_job_status ADD VALUE IF NOT EXISTS 'CANCELLED'")


def downgrade() -> None:
    op.execute("UPDATE scan_jobs SET status = 'FAILED' WHERE status = 'CANCELLED'")
