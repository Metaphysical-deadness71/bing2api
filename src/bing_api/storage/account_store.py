import json
import sqlite3
import threading
from datetime import datetime
from typing import Dict, List, Optional
from uuid import uuid4

from bing_api.models.account import AccountRecord


def _utcnow() -> datetime:
    return datetime.utcnow()


def _serialize_datetime(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def _deserialize_datetime(value: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(value) if value else None


class SqliteAccountStore:
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
                CREATE TABLE IF NOT EXISTS accounts (
                    account_id TEXT PRIMARY KEY,
                    name TEXT,
                    cookies_json TEXT NOT NULL,
                    skey TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_bootstrapped_at TEXT,
                    last_validated_at TEXT,
                    metadata_json TEXT NOT NULL
                )
                """
            )
            self._conn.commit()

    def _row_to_record(self, row: sqlite3.Row) -> AccountRecord:
        return AccountRecord(
            account_id=row["account_id"],
            name=row["name"],
            cookies=json.loads(row["cookies_json"]),
            skey=row["skey"],
            status=row["status"],
            created_at=_deserialize_datetime(row["created_at"]) or _utcnow(),
            updated_at=_deserialize_datetime(row["updated_at"]) or _utcnow(),
            last_bootstrapped_at=_deserialize_datetime(row["last_bootstrapped_at"]),
            last_validated_at=_deserialize_datetime(row["last_validated_at"]),
            metadata=json.loads(row["metadata_json"] or "{}"),
        )

    async def create(
        self,
        *,
        name: Optional[str],
        cookies: Dict[str, str],
        skey: Optional[str],
        metadata: Optional[Dict[str, object]] = None,
    ) -> AccountRecord:
        account_id = str(uuid4())
        now = _utcnow()
        record = AccountRecord(
            account_id=account_id,
            name=name,
            cookies=dict(cookies),
            skey=skey,
            status="ready" if skey else "new",
            created_at=now,
            updated_at=now,
            last_bootstrapped_at=now if skey else None,
            metadata=dict(metadata or {}),
        )
        return await self.save(record)

    async def get(self, account_id: str) -> Optional[AccountRecord]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM accounts WHERE account_id = ?",
                (account_id,),
            ).fetchone()
        return self._row_to_record(row) if row else None

    async def list(self) -> List[AccountRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM accounts ORDER BY created_at DESC"
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    async def save(self, record: AccountRecord) -> AccountRecord:
        record.updated_at = _utcnow()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO accounts (
                    account_id, name, cookies_json, skey, status, created_at,
                    updated_at, last_bootstrapped_at, last_validated_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(account_id) DO UPDATE SET
                    name=excluded.name,
                    cookies_json=excluded.cookies_json,
                    skey=excluded.skey,
                    status=excluded.status,
                    created_at=excluded.created_at,
                    updated_at=excluded.updated_at,
                    last_bootstrapped_at=excluded.last_bootstrapped_at,
                    last_validated_at=excluded.last_validated_at,
                    metadata_json=excluded.metadata_json
                """,
                (
                    record.account_id,
                    record.name,
                    json.dumps(record.cookies, ensure_ascii=True),
                    record.skey,
                    record.status,
                    _serialize_datetime(record.created_at) or _utcnow().isoformat(),
                    _serialize_datetime(record.updated_at) or _utcnow().isoformat(),
                    _serialize_datetime(record.last_bootstrapped_at),
                    _serialize_datetime(record.last_validated_at),
                    json.dumps(record.metadata, ensure_ascii=True),
                ),
            )
            self._conn.commit()
        return record

    async def delete(self, account_id: str) -> Optional[AccountRecord]:
        record = await self.get(account_id)
        if record is None:
            return None
        with self._lock:
            self._conn.execute("DELETE FROM accounts WHERE account_id = ?", (account_id,))
            self._conn.commit()
        return record


InMemoryAccountStore = SqliteAccountStore
