"""In-memory job state manager with thread-safe access and TTL cleanup."""

import threading
import time
from datetime import datetime, timezone
from typing import Optional

from api.config import JOB_TTL_SECONDS


class Job:
    __slots__ = ("job_id", "status", "created_at", "started_at", "completed_at",
                 "result", "error", "file_path")

    def __init__(self, job_id: str, file_path: str):
        self.job_id = job_id
        self.status = "queued"
        self.created_at = datetime.now(timezone.utc)
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.result: Optional[dict] = None
        self.error: Optional[str] = None
        self.file_path = file_path


class JobManager:
    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, job_id: str, file_path: str) -> Job:
        job = Job(job_id, file_path)
        with self._lock:
            self._jobs[job_id] = job
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def mark_processing(self, job_id: str):
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.status = "processing"
                job.started_at = datetime.now(timezone.utc)

    def mark_completed(self, job_id: str, result: dict):
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.status = "completed"
                job.completed_at = datetime.now(timezone.utc)
                job.result = result

    def mark_failed(self, job_id: str, error: str):
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.status = "failed"
                job.completed_at = datetime.now(timezone.utc)
                job.error = error

    def cleanup_expired(self):
        """Remove jobs older than JOB_TTL_SECONDS."""
        now = time.time()
        with self._lock:
            expired = [
                jid for jid, job in self._jobs.items()
                if (now - job.created_at.timestamp()) > JOB_TTL_SECONDS
            ]
            for jid in expired:
                del self._jobs[jid]
        return len(expired)


# Singleton instance
jobs = JobManager()
