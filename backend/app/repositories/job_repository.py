from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.scan_job import ScanJob, ScanJobStatus, ScanJobType


class JobRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, connection_id: str, job_type: ScanJobType, target_database: str | None = None) -> ScanJob:
        job = ScanJob(connection_id=connection_id, job_type=job_type, target_database=target_database)
        self.db.add(job)
        self.db.flush()
        return job

    def get(self, job_id: str) -> ScanJob | None:
        return self.db.get(ScanJob, job_id)

    def list(self, connection_id: str | None = None) -> list[ScanJob]:
        stmt = select(ScanJob).order_by(ScanJob.created_at.desc())
        if connection_id is not None:
            stmt = stmt.where(ScanJob.connection_id == connection_id)
        return list(self.db.execute(stmt).scalars().all())

    def mark_running(self, job: ScanJob) -> None:
        job.status = ScanJobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)
        self.db.flush()

    def mark_success(self, job: ScanJob, stats: dict) -> None:
        job.status = ScanJobStatus.SUCCESS
        job.stats = stats
        job.finished_at = datetime.now(timezone.utc)
        self.db.flush()

    def mark_failed(self, job: ScanJob, error_message: str, stats: dict | None = None) -> None:
        job.status = ScanJobStatus.FAILED
        job.error_message = error_message
        if stats is not None:
            job.stats = stats
        job.finished_at = datetime.now(timezone.utc)
        self.db.flush()

    def mark_cancelled(self, job: ScanJob, stats: dict | None = None) -> None:
        job.status = ScanJobStatus.CANCELLED
        job.error_message = "Cancelled by user"
        if stats is not None:
            job.stats = stats
        job.finished_at = datetime.now(timezone.utc)
        self.db.flush()
