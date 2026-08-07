from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import NotFoundError, ValidationFailedError
from app.core.security import require_api_key
from app.models.scan_job import ScanJobStatus, ScanJobType
from app.repositories.job_repository import JobRepository
from app.schemas.scan import ScanJobCreate, ScanJobRead
from app.workers import cancellation
from app.workers.lineage_worker import run_lineage_scan
from app.workers.scan_worker import run_metadata_scan

router = APIRouter(prefix="/scans", tags=["scans"], dependencies=[Depends(require_api_key)])


@router.post("", response_model=ScanJobRead, status_code=status.HTTP_201_CREATED)
def create_scan(
    payload: ScanJobCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    job = JobRepository(db).create(
        connection_id=payload.connection_id,
        job_type=payload.job_type,
        target_database=payload.target_database,
    )
    db.commit()
    db.refresh(job)

    if payload.job_type == ScanJobType.METADATA_SCAN:
        background_tasks.add_task(run_metadata_scan, job.id)
    else:
        background_tasks.add_task(run_lineage_scan, job.id)

    return job


@router.get("", response_model=list[ScanJobRead])
def list_scans(connection_id: str | None = None, db: Session = Depends(get_db)):
    return JobRepository(db).list(connection_id=connection_id)


@router.get("/{job_id}", response_model=ScanJobRead)
def get_scan(job_id: str, db: Session = Depends(get_db)):
    job = JobRepository(db).get(job_id)
    if job is None:
        raise NotFoundError(f"Scan job {job_id} not found")
    return job


@router.post("/{job_id}/cancel", response_model=ScanJobRead)
def cancel_scan(job_id: str, db: Session = Depends(get_db)):
    """Request cancellation of a PENDING/RUNNING scan job.

    This only sets a cooperative in-memory flag (see app.workers.cancellation)
    -- the worker thread notices it at its next checkpoint (between databases
    for a metadata scan, between views for a lineage scan) and transitions the
    job to CANCELLED itself. The job's status in this response may therefore
    still show PENDING/RUNNING momentarily; poll GET /scans/{job_id} (as the
    frontend already does) to observe the eventual CANCELLED status.
    """
    job = JobRepository(db).get(job_id)
    if job is None:
        raise NotFoundError(f"Scan job {job_id} not found")
    if job.status not in (ScanJobStatus.PENDING, ScanJobStatus.RUNNING):
        raise ValidationFailedError(
            f"Scan job {job_id} is already {job.status.value} and cannot be cancelled"
        )
    cancellation.request_cancel(job_id)
    return job
