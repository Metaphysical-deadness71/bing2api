from datetime import datetime
from typing import Optional, Set

from bing_api.core import get_settings
from bing_api.exceptions import VideoGenerationError
from bing_api.models.video import VideoGenerationRequest
from bing_api.services.account_concurrency import AccountConcurrencyManager
from bing_api.services.account_service import AccountService


class AccountRouter:
    def __init__(self, account_service: AccountService, concurrency: AccountConcurrencyManager) -> None:
        self.account_service = account_service
        self.concurrency = concurrency
        self.settings = get_settings()

    async def select_account(self, request: VideoGenerationRequest, exclude_ids: Optional[Set[str]] = None) -> str:
        accounts = await self.account_service.store.list()
        if not accounts:
            raise VideoGenerationError("No accounts available")

        request_type = "image_video" if request.input_image_bcid or request.input_media_context else "text_video"
        wants_fast = (request.extra_query or {}).get("mdl") == "0"
        candidates = []

        excluded = exclude_ids or set()
        for account in accounts:
            if account.account_id in excluded:
                continue

            # Auto-refresh short-lived session state only when needed.
            # This keeps the selected account pool warm without forcing the
            # caller to manually click "修复会话".
            if self.settings.auto_session_refresh_enabled and self.account_service.should_refresh_session(account, request_type):
                try:
                    await self.account_service.ensure_fresh_session(account.account_id, request_type)
                    account = await self.account_service.get_record(account.account_id)
                except Exception:
                    # If refresh fails, continue evaluating the account using
                    # current stored state; capability/cookie checks below will
                    # decide whether it remains eligible.
                    pass

            capabilities = account.metadata.get("video_capabilities") or {}
            if request_type == "image_video":
                if capabilities.get("image_video_enabled") == "false":
                    continue
                if not account.cookies.get("_U") or not account.cookies.get("_EDGE_S"):
                    continue
            else:
                if capabilities.get("text_video_enabled") == "false":
                    continue
                if not account.cookies.get("_U"):
                    continue

            cooldown_until = capabilities.get("cooldown_until")
            if cooldown_until:
                try:
                    if datetime.fromisoformat(cooldown_until) > datetime.utcnow():
                        continue
                except Exception:
                    pass

            if wants_fast:
                remaining = capabilities.get("fast_mode_remaining")
                if remaining is not None:
                    try:
                        if int(remaining) <= 0:
                            continue
                    except Exception:
                        pass

            if not await self.concurrency.can_acquire(account.account_id, request_type):
                continue

            inflight = await self.concurrency.snapshot(account.account_id)
            score = inflight["image_video_inflight"] if request_type == "image_video" else inflight["text_video_inflight"]
            candidates.append((score, account.created_at, account.account_id))

        if not candidates:
            raise VideoGenerationError("No eligible account available for this request")

        candidates.sort(key=lambda item: (item[0], item[1]))
        return candidates[0][2]
