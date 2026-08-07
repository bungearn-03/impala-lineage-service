from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.scan_job import ScanJobStatus, ScanJobType


class ScanJobCreate(BaseModel):
    connection_id: str
    job_type: ScanJobType
    target_database: str | None = None


class ScanJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    connection_id: str
    job_type: ScanJobType
    status: ScanJobStatus
    target_database: str | None
    error_message: str | None
    stats: dict
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
