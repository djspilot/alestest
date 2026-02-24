"""Job state manager with SQLite persistence and in-memory cache.

Active jobs are kept in memory for fast polling. All jobs are persisted
to SQLite so they survive server restarts and can be listed/queried.
"""

import json
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from typing import Optional

from api.config import JOB_TTL_SECONDS, DB_PATH


class Job:
    __slots__ = ("job_id", "status", "created_at", "started_at", "completed_at",
                 "result", "error", "file_path", "file_name", "file_hash",
                 "file_size_bytes")

    def __init__(self, job_id: str, file_path: str, file_name: str = "",
                 file_hash: str = "", file_size_bytes: int = 0):
        self.job_id = job_id
        self.status = "queued"
        self.created_at = datetime.now(timezone.utc)
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.result: Optional[dict] = None
        self.error: Optional[str] = None
        self.file_path = file_path
        self.file_name = file_name or os.path.basename(file_path)
        self.file_hash = file_hash
        self.file_size_bytes = file_size_bytes


class JobManager:
    def __init__(self, db_path: str = ""):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._db_path = db_path or DB_PATH
        self._init_db()

    # ------------------------------------------------------------------
    # Database helpers
    # ------------------------------------------------------------------

    def _init_db(self):
        """Create the api_jobs table if it doesn't exist."""
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS api_jobs (
                    job_id TEXT PRIMARY KEY,
                    file_name TEXT NOT NULL,
                    file_hash TEXT,
                    file_size_bytes INTEGER,
                    status TEXT NOT NULL DEFAULT 'queued',
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    result_json TEXT,
                    error TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_api_jobs_status
                    ON api_jobs(status);
                CREATE INDEX IF NOT EXISTS idx_api_jobs_created_at
                    ON api_jobs(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_api_jobs_file_hash
                    ON api_jobs(file_hash);
            """)
            conn.commit()
        finally:
            conn.close()

    def _get_conn(self) -> sqlite3.Connection:
        """Get a new DB connection (one per operation, thread-safe)."""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _dt_to_str(self, dt: Optional[datetime]) -> Optional[str]:
        return dt.isoformat() if dt else None

    def _str_to_dt(self, s: Optional[str]) -> Optional[datetime]:
        if not s:
            return None
        return datetime.fromisoformat(s)

    def _update_db(self, job_id: str, **kwargs):
        """Update specific columns for a job in SQLite."""
        if not kwargs:
            return
        set_clause = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [job_id]
        conn = self._get_conn()
        try:
            conn.execute(f"UPDATE api_jobs SET {set_clause} WHERE job_id = ?", values)
            conn.commit()
        finally:
            conn.close()

    def _row_to_job(self, row: sqlite3.Row) -> Job:
        """Convert a SQLite row to a Job object."""
        job = Job.__new__(Job)
        job.job_id = row["job_id"]
        job.file_name = row["file_name"] or ""
        job.file_hash = row["file_hash"] or ""
        job.file_size_bytes = row["file_size_bytes"] or 0
        job.status = row["status"]
        job.created_at = self._str_to_dt(row["created_at"])
        job.started_at = self._str_to_dt(row["started_at"])
        job.completed_at = self._str_to_dt(row["completed_at"])
        job.error = row["error"]
        job.file_path = ""
        result_json = row["result_json"]
        job.result = json.loads(result_json) if result_json else None
        return job

    # ------------------------------------------------------------------
    # Job lifecycle (in-memory + SQLite)
    # ------------------------------------------------------------------

    def create(self, job_id: str, file_path: str, file_name: str = "",
               file_hash: str = "", file_size_bytes: int = 0) -> Job:
        job = Job(job_id, file_path, file_name, file_hash, file_size_bytes)
        with self._lock:
            self._jobs[job_id] = job
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT INTO api_jobs
                   (job_id, file_name, file_hash, file_size_bytes, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (job_id, job.file_name, file_hash, file_size_bytes,
                 "queued", self._dt_to_str(job.created_at))
            )
            conn.commit()
        finally:
            conn.close()
        return job

    def get(self, job_id: str) -> Optional[Job]:
        """Get job: check in-memory first, fall back to SQLite."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                return job
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM api_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            if not row:
                return None
            return self._row_to_job(row)
        finally:
            conn.close()

    def mark_processing(self, job_id: str):
        now = datetime.now(timezone.utc)
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.status = "processing"
                job.started_at = now
        self._update_db(job_id, status="processing",
                        started_at=self._dt_to_str(now))

    def mark_completed(self, job_id: str, result: dict):
        now = datetime.now(timezone.utc)
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.status = "completed"
                job.completed_at = now
                job.result = result
        self._update_db(job_id, status="completed",
                        completed_at=self._dt_to_str(now),
                        result_json=json.dumps(result, default=str))

    def mark_failed(self, job_id: str, error: str):
        now = datetime.now(timezone.utc)
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.status = "failed"
                job.completed_at = now
                job.error = error
        self._update_db(job_id, status="failed",
                        completed_at=self._dt_to_str(now),
                        error=error)

    # ------------------------------------------------------------------
    # Listing & stats (from SQLite)
    # ------------------------------------------------------------------

    def list_jobs(self, limit: int = 20, offset: int = 0,
                  status: Optional[str] = None) -> tuple[list[dict], int]:
        """List jobs (lightweight summaries, no result_json)."""
        conn = self._get_conn()
        try:
            where = ""
            params: list = []
            if status:
                where = "WHERE status = ?"
                params.append(status)

            total = conn.execute(
                f"SELECT COUNT(*) FROM api_jobs {where}", params
            ).fetchone()[0]

            rows = conn.execute(
                f"""SELECT job_id, file_name, file_hash, file_size_bytes,
                           status, created_at, started_at, completed_at, error
                    FROM api_jobs {where}
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?""",
                params + [limit, offset]
            ).fetchall()

            return [dict(row) for row in rows], total
        finally:
            conn.close()

    def get_stats(self) -> dict:
        """Get aggregated job statistics."""
        conn = self._get_conn()
        try:
            stats = {}
            stats["total_jobs"] = conn.execute(
                "SELECT COUNT(*) FROM api_jobs"
            ).fetchone()[0]
            for row in conn.execute(
                "SELECT status, COUNT(*) as cnt FROM api_jobs GROUP BY status"
            ):
                stats[f"jobs_{row['status']}"] = row["cnt"]
            stats["jobs_last_24h"] = conn.execute(
                "SELECT COUNT(*) FROM api_jobs WHERE created_at > datetime('now', '-1 day')"
            ).fetchone()[0]
            return stats
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Cleanup & recovery
    # ------------------------------------------------------------------

    def cleanup_expired(self):
        """Remove expired jobs from memory only. SQLite records are kept."""
        now = time.time()
        with self._lock:
            expired = [
                jid for jid, job in self._jobs.items()
                if (now - job.created_at.timestamp()) > JOB_TTL_SECONDS
            ]
            for jid in expired:
                del self._jobs[jid]
        return len(expired)

    def recover_stale_jobs(self) -> int:
        """Mark any queued/processing jobs as failed (server restart recovery)."""
        conn = self._get_conn()
        try:
            now_str = self._dt_to_str(datetime.now(timezone.utc))
            cursor = conn.execute(
                """UPDATE api_jobs SET status = 'failed',
                          error = 'Server restarted during processing',
                          completed_at = ?
                   WHERE status IN ('queued', 'processing')""",
                (now_str,)
            )
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()


# Singleton instance
jobs = JobManager()
