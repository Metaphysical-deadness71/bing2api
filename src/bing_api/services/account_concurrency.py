import asyncio
from typing import Dict


class AccountConcurrencyManager:
    def __init__(self) -> None:
        self._text_limits: Dict[str, int] = {}
        self._image_limits: Dict[str, int] = {}
        self._text_inflight: Dict[str, int] = {}
        self._image_inflight: Dict[str, int] = {}
        self._lock = asyncio.Lock()

    async def configure_account(self, account_id: str, text_limit: int = 3, image_limit: int = 3) -> None:
        async with self._lock:
            self._text_limits[account_id] = max(1, text_limit)
            self._image_limits[account_id] = max(1, image_limit)
            self._text_inflight.setdefault(account_id, 0)
            self._image_inflight.setdefault(account_id, 0)

    async def can_acquire(self, account_id: str, request_type: str) -> bool:
        async with self._lock:
            if request_type == "image_video":
                return self._image_inflight.get(account_id, 0) < self._image_limits.get(account_id, 1)
            else:
                return self._text_inflight.get(account_id, 0) < self._text_limits.get(account_id, 3)

    async def acquire(self, account_id: str, request_type: str) -> bool:
        async with self._lock:
            if request_type == "image_video":
                current = self._image_inflight.get(account_id, 0)
                limit = self._image_limits.get(account_id, 1)
                if current >= limit:
                    return False
                self._image_inflight[account_id] = current + 1
                return True
            current = self._text_inflight.get(account_id, 0)
            limit = self._text_limits.get(account_id, 3)
            if current >= limit:
                return False
            self._text_inflight[account_id] = current + 1
            return True

    async def release(self, account_id: str, request_type: str) -> None:
        async with self._lock:
            if request_type == "image_video":
                current = self._image_inflight.get(account_id, 0)
                self._image_inflight[account_id] = max(0, current - 1)
            else:
                current = self._text_inflight.get(account_id, 0)
                self._text_inflight[account_id] = max(0, current - 1)

    async def snapshot(self, account_id: str) -> Dict[str, int]:
        async with self._lock:
            return {
                "text_video_limit": self._text_limits.get(account_id, 3),
                "image_video_limit": self._image_limits.get(account_id, 3),
                "text_video_inflight": self._text_inflight.get(account_id, 0),
                "image_video_inflight": self._image_inflight.get(account_id, 0),
            }
