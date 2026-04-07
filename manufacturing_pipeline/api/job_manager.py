"""Job state manager with SQLite persistence and in-memory cache.

Active jobs are kept in memory for fast polling. All jobs are persisted
to SQLite so they survive server restarts and can be listed/queried.
"""

import json
import os
import sqlite3
import threading
import time
from copy import deepcopy
from datetime import datetime, timezone
from typing import Optional

from manufacturing_pipeline.api.config import JOB_TTL_SECONDS, DB_PATH


class Job:
    __slots__ = ("job_id", "status", "created_at", "started_at", "completed_at",
                 "result", "error", "file_path", "file_name", "file_hash",
                 "request_fingerprint",
                 "archived", "archived_at",
                 "file_size_bytes", "progress_events", "progress_summary",
                 "unfold_status", "unfold_requested_at", "unfold_started_at",
                 "unfold_completed_at", "unfold_result", "unfold_error")

    def __init__(self, job_id: str, file_path: str, file_name: str = "",
                 file_hash: str = "", request_fingerprint: str = "",
                 file_size_bytes: int = 0):
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
        self.request_fingerprint = request_fingerprint
        self.archived = False
        self.archived_at: Optional[datetime] = None
        self.file_size_bytes = file_size_bytes
        self.progress_events: list[dict] = []
        self.progress_summary: Optional[dict] = None
        self.unfold_status = "idle"
        self.unfold_requested_at: Optional[datetime] = None
        self.unfold_started_at: Optional[datetime] = None
        self.unfold_completed_at: Optional[datetime] = None
        self.unfold_result: Optional[dict] = None
        self.unfold_error: Optional[str] = None


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
                    file_path TEXT,
                    file_name TEXT NOT NULL,
                    file_hash TEXT,
                    request_fingerprint TEXT,
                    archived INTEGER NOT NULL DEFAULT 0,
                    archived_at TEXT,
                    file_size_bytes INTEGER,
                    status TEXT NOT NULL DEFAULT 'queued',
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    result_json TEXT,
                    error TEXT,
                    unfold_status TEXT NOT NULL DEFAULT 'idle',
                    unfold_requested_at TEXT,
                    unfold_started_at TEXT,
                    unfold_completed_at TEXT,
                    unfold_result_json TEXT,
                    unfold_error TEXT
                );
            """)
            existing_columns = {
                row[1]
                for row in conn.execute("PRAGMA table_info(api_jobs)").fetchall()
            }
            if "unfold_status" not in existing_columns:
                conn.execute("ALTER TABLE api_jobs ADD COLUMN unfold_status TEXT NOT NULL DEFAULT 'idle'")
            if "file_path" not in existing_columns:
                conn.execute("ALTER TABLE api_jobs ADD COLUMN file_path TEXT")
            if "request_fingerprint" not in existing_columns:
                conn.execute("ALTER TABLE api_jobs ADD COLUMN request_fingerprint TEXT")
            if "archived" not in existing_columns:
                conn.execute("ALTER TABLE api_jobs ADD COLUMN archived INTEGER NOT NULL DEFAULT 0")
            if "archived_at" not in existing_columns:
                conn.execute("ALTER TABLE api_jobs ADD COLUMN archived_at TEXT")
            if "unfold_requested_at" not in existing_columns:
                conn.execute("ALTER TABLE api_jobs ADD COLUMN unfold_requested_at TEXT")
            if "unfold_started_at" not in existing_columns:
                conn.execute("ALTER TABLE api_jobs ADD COLUMN unfold_started_at TEXT")
            if "unfold_completed_at" not in existing_columns:
                conn.execute("ALTER TABLE api_jobs ADD COLUMN unfold_completed_at TEXT")
            if "unfold_result_json" not in existing_columns:
                conn.execute("ALTER TABLE api_jobs ADD COLUMN unfold_result_json TEXT")
            if "unfold_error" not in existing_columns:
                conn.execute("ALTER TABLE api_jobs ADD COLUMN unfold_error TEXT")
            conn.executescript("""
                CREATE INDEX IF NOT EXISTS idx_api_jobs_status
                    ON api_jobs(status);
                CREATE INDEX IF NOT EXISTS idx_api_jobs_unfold_status
                    ON api_jobs(unfold_status);
                CREATE INDEX IF NOT EXISTS idx_api_jobs_created_at
                    ON api_jobs(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_api_jobs_file_hash
                    ON api_jobs(file_hash);
                CREATE INDEX IF NOT EXISTS idx_api_jobs_request_fingerprint
                    ON api_jobs(request_fingerprint);
                CREATE INDEX IF NOT EXISTS idx_api_jobs_archived
                    ON api_jobs(archived);
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
        job.request_fingerprint = row["request_fingerprint"] or ""
        job.archived = bool(row["archived"]) if "archived" in row.keys() else False
        job.archived_at = self._str_to_dt(row["archived_at"]) if "archived_at" in row.keys() else None
        job.file_size_bytes = row["file_size_bytes"] or 0
        job.status = row["status"]
        job.created_at = self._str_to_dt(row["created_at"])
        job.started_at = self._str_to_dt(row["started_at"])
        job.completed_at = self._str_to_dt(row["completed_at"])
        job.error = row["error"]
        job.file_path = row["file_path"] if "file_path" in row.keys() else ""
        result_json = row["result_json"]
        job.result = json.loads(result_json) if result_json else None
        job.progress_events = []
        job.progress_summary = None
        job.unfold_status = row["unfold_status"] or "idle"
        job.unfold_requested_at = self._str_to_dt(row["unfold_requested_at"])
        job.unfold_started_at = self._str_to_dt(row["unfold_started_at"])
        job.unfold_completed_at = self._str_to_dt(row["unfold_completed_at"])
        job.unfold_error = row["unfold_error"]
        unfold_result_json = row["unfold_result_json"]
        job.unfold_result = json.loads(unfold_result_json) if unfold_result_json else None
        return job

    # ------------------------------------------------------------------
    # Job lifecycle (in-memory + SQLite)
    # ------------------------------------------------------------------

    def create(self, job_id: str, file_path: str, file_name: str = "",
               file_hash: str = "", request_fingerprint: str = "",
               file_size_bytes: int = 0) -> Job:
        job = Job(job_id, file_path, file_name, file_hash, request_fingerprint, file_size_bytes)
        with self._lock:
            self._jobs[job_id] = job
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT INTO api_jobs
                   (job_id, file_path, file_name, file_hash, request_fingerprint, archived, archived_at,
                    file_size_bytes, status, created_at, unfold_status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (job_id, file_path, job.file_name, file_hash, request_fingerprint, 0, None,
                 file_size_bytes, "queued", self._dt_to_str(job.created_at), "idle")
            )
            conn.commit()
        finally:
            conn.close()
        return job

    def find_reusable_job(self, request_fingerprint: str) -> Optional[Job]:
        """Return the latest reusable job for an identical request."""
        if not request_fingerprint:
            return None
        conn = self._get_conn()
        try:
            row = conn.execute(
                """SELECT *
                   FROM api_jobs
                   WHERE request_fingerprint = ?
                     AND status IN ('queued', 'processing', 'completed')
                   ORDER BY
                     CASE status
                       WHEN 'completed' THEN 0
                       WHEN 'processing' THEN 1
                       WHEN 'queued' THEN 2
                       ELSE 3
                     END,
                     created_at DESC
                   LIMIT 1""",
                (request_fingerprint,),
            ).fetchone()
            if not row:
                return None
            return self._row_to_job(row)
        finally:
            conn.close()

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

    def set_archived(self, job_id: str, archived: bool) -> Optional[Job]:
        now = datetime.now(timezone.utc) if archived else None
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.archived = archived
                job.archived_at = now
        self._update_db(
            job_id,
            archived=1 if archived else 0,
            archived_at=self._dt_to_str(now),
        )
        return self.get(job_id)

    def archive_all(self) -> int:
        now = self._dt_to_str(datetime.now(timezone.utc))
        with self._lock:
            for job in self._jobs.values():
                job.archived = True
                job.archived_at = self._str_to_dt(now)
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                """UPDATE api_jobs
                   SET archived = 1, archived_at = ?
                   WHERE archived = 0""",
                (now,),
            )
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

    def mark_processing(self, job_id: str):
        now = datetime.now(timezone.utc)
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.status = "processing"
                job.started_at = now
                job.progress_events = []
                job.progress_summary = None
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

    def queue_unfold(self, job_id: str):
        now = datetime.now(timezone.utc)
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.unfold_status = "queued"
                job.unfold_requested_at = now
                job.unfold_started_at = None
                job.unfold_completed_at = None
                job.unfold_result = None
                job.unfold_error = None
        self._update_db(
            job_id,
            unfold_status="queued",
            unfold_requested_at=self._dt_to_str(now),
            unfold_started_at=None,
            unfold_completed_at=None,
            unfold_result_json=None,
            unfold_error=None,
        )

    def mark_unfold_processing(self, job_id: str):
        now = datetime.now(timezone.utc)
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.unfold_status = "processing"
                job.unfold_started_at = now
        self._update_db(
            job_id,
            unfold_status="processing",
            unfold_started_at=self._dt_to_str(now),
        )

    def mark_unfold_completed(self, job_id: str, result: dict):
        now = datetime.now(timezone.utc)
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.unfold_status = "completed"
                job.unfold_completed_at = now
                job.unfold_result = result
                job.unfold_error = None
        self._update_db(
            job_id,
            unfold_status="completed",
            unfold_completed_at=self._dt_to_str(now),
            unfold_result_json=json.dumps(result, default=str),
            unfold_error=None,
        )

    def mark_unfold_failed(self, job_id: str, error: str):
        now = datetime.now(timezone.utc)
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.unfold_status = "failed"
                job.unfold_completed_at = now
                job.unfold_error = error
        self._update_db(
            job_id,
            unfold_status="failed",
            unfold_completed_at=self._dt_to_str(now),
            unfold_error=error,
        )

    def record_progress(self, job_id: str, event: dict, summary: Optional[dict] = None):
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job.progress_events.append(deepcopy(event))
            if summary is not None:
                job.progress_summary = deepcopy(summary)

    # ------------------------------------------------------------------
    # Listing & stats (from SQLite)
    # ------------------------------------------------------------------

    def list_jobs(self, limit: int = 20, offset: int = 0,
                  status: Optional[str] = None,
                  include_archived: bool = False,
                  archived_only: bool = False) -> tuple[list[dict], int]:
        """List jobs (lightweight summaries, no result_json)."""
        conn = self._get_conn()
        try:
            where_clauses = []
            params: list = []
            if archived_only:
                where_clauses.append("archived = 1")
            elif not include_archived:
                where_clauses.append("archived = 0")
            if status:
                where_clauses.append("status = ?")
                params.append(status)
            where = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

            total = conn.execute(
                f"SELECT COUNT(*) FROM api_jobs {where}", params
            ).fetchone()[0]

            rows = conn.execute(
                f"""SELECT job_id, file_path, file_name, file_hash, archived, archived_at, file_size_bytes,
                           status, created_at, started_at, completed_at, error,
                           result_json, unfold_status, unfold_requested_at,
                           unfold_started_at, unfold_completed_at, unfold_result_json,
                           unfold_error
                    FROM api_jobs {where}
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?""",
                params + [limit, offset]
            ).fetchall()

            items = []
            for row in rows:
                item = {
                    "job_id": row["job_id"],
                    "file_name": row["file_name"],
                    "file_hash": row["file_hash"],
                    "archived": bool(row["archived"]),
                    "archived_at": row["archived_at"],
                    "file_size_bytes": row["file_size_bytes"],
                    "status": row["status"],
                    "source_step_available": bool(row["file_path"]) and os.path.exists(row["file_path"]),
                    "created_at": row["created_at"],
                    "started_at": row["started_at"],
                    "completed_at": row["completed_at"],
                    "error": row["error"],
                    "result": None,
                    "unfold": {
                        "status": row["unfold_status"] or "idle",
                        "requested_at": row["unfold_requested_at"],
                        "started_at": row["unfold_started_at"],
                        "completed_at": row["unfold_completed_at"],
                        "error": row["unfold_error"],
                        "result": None,
                    },
                }
                result_json = row["result_json"]
                if result_json:
                    try:
                        full = json.loads(result_json)
                        item["result"] = {
                            "category": full.get("category"),
                            "part_type": full.get("part_type"),
                            "thickness": full.get("thickness"),
                            "dimensions": full.get("dimensions"),
                            "production": full.get("production"),
                            "is_assembly": full.get("is_assembly"),
                            "solid_count": full.get("solid_count"),
                            "parts": full.get("parts"),
                        }
                    except Exception:
                        pass
                unfold_result_json = row["unfold_result_json"]
                if unfold_result_json:
                    try:
                        unfold_result = json.loads(unfold_result_json)
                        item["unfold"]["result"] = {
                            "success": bool(unfold_result.get("success")),
                            "error": unfold_result.get("error"),
                            "flat_length": unfold_result.get("flat_length"),
                            "flat_width": unfold_result.get("flat_width"),
                            "fold_lines": unfold_result.get("fold_lines", 0),
                            "raw_fold_lines": unfold_result.get("raw_fold_lines"),
                            "fold_details": unfold_result.get("fold_details", []),
                            "bends_logical": unfold_result.get("bends_logical", []),
                            "bend_line_segments": unfold_result.get("bend_line_segments", []),
                            "bend_line_groups": unfold_result.get("bend_line_groups", []),
                            "flat_step_url": unfold_result.get("flat_step_url"),
                            "dxf_url": unfold_result.get("dxf_url"),
                        }
                    except Exception:
                        pass
                items.append(item)

            return items, total
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
            stats["archived_jobs"] = conn.execute(
                "SELECT COUNT(*) FROM api_jobs WHERE archived = 1"
            ).fetchone()[0]
            for row in conn.execute(
                "SELECT status, COUNT(*) as cnt FROM api_jobs WHERE archived = 0 GROUP BY status"
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
