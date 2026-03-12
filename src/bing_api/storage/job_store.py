import json
import sqlite3
import threading
from datetime import datetime
from typing import Dict, List, Optional

from bing_api.models.video import VideoGenerationResponse


def _serialize_response(response: VideoGenerationResponse) -> str:
    return response.json()


def _deserialize_response(payload: str) -> VideoGenerationResponse:
    return VideoGenerationResponse.parse_raw(payload)


class SqliteJobStore:
    def __init__(self, sqlite_path: str) -> None:
        self.sqlite_path = sqlite_path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.sqlite_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    prompt TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    response_json TEXT NOT NULL
                )
                """
            )
            self._conn.commit()

    async def put(self, response: VideoGenerationResponse) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO jobs (job_id, account_id, status, prompt, created_at, updated_at, response_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    account_id=excluded.account_id,
                    status=excluded.status,
                    prompt=excluded.prompt,
                    created_at=excluded.created_at,
                    updated_at=excluded.updated_at,
                    response_json=excluded.response_json
                """,
                (
                    response.job_id,
                    response.account_id,
                    response.status,
                    response.prompt,
                    response.created_at.isoformat() if response.created_at else None,
                    response.updated_at.isoformat() if response.updated_at else None,
                    _serialize_response(response),
                ),
            )
            self._conn.commit()

    async def get(self, job_id: str) -> Optional[VideoGenerationResponse]:
        with self._lock:
            row = self._conn.execute(
                "SELECT response_json FROM jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        return _deserialize_response(row["response_json"]) if row else None

    async def list(self, limit: int = 100) -> List[VideoGenerationResponse]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT response_json FROM jobs ORDER BY COALESCE(updated_at, created_at) DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_deserialize_response(row["response_json"]) for row in rows]

    async def list_for_account(self, account_id: str, limit: int = 20) -> List[VideoGenerationResponse]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT response_json FROM jobs WHERE account_id = ? ORDER BY COALESCE(updated_at, created_at) DESC LIMIT ?",
                (account_id, limit),
            ).fetchall()
        return [_deserialize_response(row["response_json"]) for row in rows]

    async def get_stats(self) -> Dict[str, int]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT status, COUNT(*) AS count FROM jobs GROUP BY status"
            ).fetchall()
            total = self._conn.execute("SELECT COUNT(*) AS count FROM jobs").fetchone()["count"]
        stats = {"total_jobs": total, "succeeded_jobs": 0, "failed_jobs": 0, "submitted_jobs": 0}
        for row in rows:
            key = "{0}_jobs".format(row["status"])
            stats[key] = row["count"]
        return stats

    def count(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) AS count FROM jobs").fetchone()
        return int(row["count"])


InMemoryJobStore = SqliteJobStore
