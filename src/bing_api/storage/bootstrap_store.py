import json
import sqlite3
import threading
from typing import Any, Dict, List, Optional


class SqliteBootstrapEventStore:
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
                CREATE TABLE IF NOT EXISTS bootstrap_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    source TEXT,
                    error TEXT,
                    create_probe_generation INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    trace_json TEXT NOT NULL
                )
                """
            )
            self._conn.commit()

    async def log_event(
        self,
        *,
        account_id: str,
        success: bool,
        source: Optional[str],
        error: Optional[str],
        create_probe_generation: bool,
        created_at: str,
        trace: List[str],
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO bootstrap_events (
                    account_id, success, source, error, create_probe_generation, created_at, trace_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    account_id,
                    1 if success else 0,
                    source,
                    error,
                    1 if create_probe_generation else 0,
                    created_at,
                    json.dumps(trace, ensure_ascii=True),
                ),
            )
            self._conn.commit()

    async def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            total = self._conn.execute(
                "SELECT COUNT(*) AS count FROM bootstrap_events"
            ).fetchone()["count"]
            success = self._conn.execute(
                "SELECT COUNT(*) AS count FROM bootstrap_events WHERE success = 1"
            ).fetchone()["count"]
            failed = total - success
            rows = self._conn.execute(
                """
                SELECT COALESCE(source, 'unknown') AS source, COUNT(*) AS count
                FROM bootstrap_events
                WHERE success = 1
                GROUP BY COALESCE(source, 'unknown')
                ORDER BY count DESC
                """
            ).fetchall()
            recent = self._conn.execute(
                """
                SELECT account_id, success, source, error, create_probe_generation, created_at
                FROM bootstrap_events
                ORDER BY id DESC
                LIMIT 20
                """
            ).fetchall()
        return {
            "total_attempts": int(total),
            "successful_attempts": int(success),
            "failed_attempts": int(failed),
            "success_rate": round((float(success) / total) * 100, 2) if total else 0.0,
            "source_breakdown": [dict(row) for row in rows],
            "recent_events": [dict(row) for row in recent],
        }


InMemoryBootstrapEventStore = SqliteBootstrapEventStore
