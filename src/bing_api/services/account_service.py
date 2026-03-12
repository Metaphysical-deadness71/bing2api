import asyncio
from datetime import datetime, timedelta
from http.cookies import SimpleCookie
from typing import Dict, List, Optional

from bing_api.clients.base import AsyncBingBaseClient
from bing_api.clients.video import AsyncBingVideoClient
from bing_api.exceptions import AccountNotFoundError, InvalidAccountConfigError
from bing_api.models.account import (
    AccountAdminResponse,
    AccountBatchPrepareResponse,
    AccountBatchRefreshResponse,
    AccountCreateRequest,
    AccountImportRequest,
    AccountImportResponse,
    AccountRecord,
    AccountResponse,
    AccountUpdateRequest,
)
from bing_api.storage.account_store import InMemoryAccountStore


def parse_cookie_header(cookie_header: str) -> Dict[str, str]:
    cookie = SimpleCookie()
    cookie.load(cookie_header)
    return {key: morsel.value for key, morsel in cookie.items()}


class AccountService:
    def __init__(self, store: InMemoryAccountStore) -> None:
        self.store = store
        self._locks: Dict[str, asyncio.Lock] = {}
        self.image_session_refresh_interval = timedelta(minutes=20)
        self.text_session_refresh_interval = timedelta(hours=6)

    def _lock_for(self, account_id: str) -> asyncio.Lock:
        if account_id not in self._locks:
            self._locks[account_id] = asyncio.Lock()
        return self._locks[account_id]

    async def create_account(self, request: AccountCreateRequest) -> AccountResponse:
        cookies = dict(request.cookies or {})
        metadata = dict(request.metadata or {})
        if request.cookie_header:
            cookies.update(parse_cookie_header(request.cookie_header))
            metadata["raw_cookie_header"] = request.cookie_header.strip()
        if not cookies:
            raise InvalidAccountConfigError("Account creation requires cookies or cookie_header")
        record = await self.store.create(
            name=request.name,
            cookies=cookies,
            skey=request.skey,
            metadata=metadata,
        )
        if "video_capabilities" not in record.metadata:
            record.metadata["video_capabilities"] = {
                "text_video_enabled": "true",
                "image_video_enabled": "true" if cookies.get("_EDGE_S") else "unknown",
            }
            await self.store.save(record)
        return record.to_response()

    async def import_accounts(self, request: AccountImportRequest) -> AccountImportResponse:
        response = AccountImportResponse()
        for item in request.accounts:
            try:
                if item.account_id:
                    await self.update_account(item.account_id, item)
                    response.updated += 1
                    response.details.append({"account_id": item.account_id, "status": "updated"})
                else:
                    created = await self.create_account(
                        AccountCreateRequest(
                            name=item.name,
                            cookies=item.cookies,
                            cookie_header=item.cookie_header,
                            skey=item.skey,
                            metadata=item.metadata or {},
                        )
                    )
                    response.created += 1
                    response.details.append({"account_id": created.account_id, "status": "created"})
            except Exception as exc:
                response.failed += 1
                response.details.append(
                    {
                        "account_id": item.account_id,
                        "name": item.name,
                        "status": "failed",
                        "error": str(exc),
                    }
                )
        return response

    async def export_accounts(self) -> List[Dict[str, object]]:
        records = await self.store.list()
        exported = []
        for record in records:
            exported.append(
                {
                    "account_id": record.account_id,
                    "name": record.name,
                    "cookie_header": "; ".join(
                        ["{0}={1}".format(name, value) for name, value in record.cookies.items()]
                    ),
                    "skey": record.skey,
                    "metadata": record.metadata,
                    "status": record.status,
                }
            )
        return exported

    async def list_accounts(self) -> List[AccountResponse]:
        records = await self.store.list()
        return [record.to_response() for record in records]

    async def list_admin_accounts(self) -> List[AccountAdminResponse]:
        records = await self.store.list()
        return [record.to_admin_response() for record in records]

    async def get_account(self, account_id: str) -> AccountResponse:
        record = await self.get_record(account_id)
        return record.to_response()

    async def get_admin_account(self, account_id: str) -> AccountAdminResponse:
        record = await self.get_record(account_id)
        return record.to_admin_response()

    async def refresh_fast_mode_status(self, account_id: str) -> AccountAdminResponse:
        record = await self.get_record(account_id)
        async with AsyncBingVideoClient(record.cookies) as client:
            status = await client.detect_fast_mode_status()
        async with self._lock_for(account_id):
            capabilities = dict(record.metadata.get("video_capabilities") or {})
            capabilities.update(status)
             
            if "text_video_enabled" not in capabilities:
                capabilities["text_video_enabled"] = "true"
            if "image_video_enabled" not in capabilities:
                capabilities["image_video_enabled"] = "true" if record.cookies.get("_EDGE_S") else "unknown"
            record.metadata["video_capabilities"] = capabilities
            record.updated_at = datetime.utcnow()
            await self.store.save(record)
        return record.to_admin_response()

    async def refresh_bing_session(self, account_id: str) -> AccountAdminResponse:
        record = await self.get_record(account_id)
        bootstrap_cookies = dict(record.cookies)
        raw_cookie_header = (record.metadata or {}).get("raw_cookie_header")
        if raw_cookie_header:
            try:
                bootstrap_cookies.update(parse_cookie_header(raw_cookie_header))
            except Exception:
                pass
        async with AsyncBingBaseClient(bootstrap_cookies) as client:
            await client.get("/")
            await client.get("/images/create?ctype=video&FORM=GENEXP")
            warmup = await client.get("/images/create/ai-video-generator?FORM=GENEXP")
            # Call reportActivity to trigger Bing to issue a fresh _SS cookie
            ig_match = __import__("re").search(r'"IG"\s*:\s*"([^"]+)"', warmup.text)
            ig = ig_match.group(1) if ig_match else None
            try:
                report_params = {"FORM": "GENEXP"}
                if ig:
                    report_params["IG"] = ig
                await client.post(
                    "/rewardsapp/reportActivity",
                    params=report_params,
                    data={"url": "https://www.bing.com/images/create/ai-video-generator", "action": "view"},
                )
            except Exception:
                pass
            refreshed_cookies = client.export_cookies()

        async with self._lock_for(account_id):
            record.cookies.update(refreshed_cookies)
            capabilities = dict(record.metadata.get("video_capabilities") or {})
            capabilities["last_session_refresh_at"] = datetime.utcnow().isoformat()
            if record.cookies.get("_EDGE_S"):
                capabilities["image_video_enabled"] = "true"
            record.metadata["video_capabilities"] = capabilities
            record.updated_at = datetime.utcnow()
            await self.store.save(record)
        return record.to_admin_response()

    def should_refresh_session(self, record: AccountRecord, request_type: str) -> bool:
        metadata = record.metadata or {}
        capabilities = metadata.get("video_capabilities") or {}
        raw_cookie_header = metadata.get("raw_cookie_header")

        # Without a full raw cookie header we do not try proactive refresh for
        # image upload, because the refresh may produce incomplete transient
        # cookies.  The account can still be used for text-to-video.
        if request_type == "image_video" and not raw_cookie_header:
            return False

        # Missing short-lived session cookies => refresh immediately.
        if request_type == "image_video":
            if not record.cookies.get("_EDGE_S") or not record.cookies.get("_SS"):
                return True
        else:
            if not record.cookies.get("_EDGE_S") and raw_cookie_header:
                return True

        last_refresh_at = capabilities.get("last_session_refresh_at")
        if not last_refresh_at:
            return request_type == "image_video"

        try:
            last_refresh = datetime.fromisoformat(last_refresh_at)
        except Exception:
            return True

        now = datetime.utcnow()
        interval = (
            self.image_session_refresh_interval
            if request_type == "image_video"
            else self.text_session_refresh_interval
        )
        return now - last_refresh >= interval

    async def ensure_fresh_session(self, account_id: str, request_type: str) -> AccountAdminResponse:
        record = await self.get_record(account_id)
        if not self.should_refresh_session(record, request_type):
            return record.to_admin_response()
        return await self.refresh_bing_session(account_id)

    async def refresh_bing_sessions(self, account_ids: List[str]) -> AccountBatchRefreshResponse:
        response = AccountBatchRefreshResponse()
        for account_id in account_ids:
            try:
                refreshed = await self.refresh_bing_session(account_id)
                response.refreshed += 1
                response.details.append(
                    {
                        "account_id": account_id,
                        "status": "refreshed",
                        "has_edge": "_EDGE_S" in refreshed.cookie_names,
                    }
                )
            except Exception as exc:
                response.failed += 1
                response.details.append(
                    {
                        "account_id": account_id,
                        "status": "failed",
                        "error": str(exc),
                    }
                )
        return response

    async def prepare_accounts(self, account_ids: List[str]) -> AccountBatchPrepareResponse:
        response = AccountBatchPrepareResponse()
        for account_id in account_ids:
            try:
                refreshed = await self.refresh_bing_session(account_id)
                refreshed = await self.refresh_fast_mode_status(account_id)
                response.prepared += 1
                response.details.append(
                    {
                        "account_id": account_id,
                        "status": "prepared",
                        "has_edge": "_EDGE_S" in refreshed.cookie_names,
                        "fast_mode_remaining": refreshed.fast_mode_remaining,
                        "image_video_enabled": refreshed.image_video_enabled,
                    }
                )
            except Exception as exc:
                response.failed += 1
                response.details.append(
                    {
                        "account_id": account_id,
                        "status": "failed",
                        "error": str(exc),
                    }
                )
        return response

    async def update_runtime_state(self, account_id: str, runtime_state: Dict[str, int]) -> None:
        record = await self.get_record(account_id)
        async with self._lock_for(account_id):
            record.metadata["runtime"] = dict(runtime_state)
            record.updated_at = datetime.utcnow()
            await self.store.save(record)

    async def mark_generation_failure(self, account_id: str, request_type: str, error_message: str) -> AccountAdminResponse:
        record = await self.get_record(account_id)
        async with self._lock_for(account_id):
            capabilities = dict(record.metadata.get("video_capabilities") or {})
            failure_key = "image_video_failures" if request_type == "image_video" else "text_video_failures"
            failures = int(capabilities.get(failure_key, 0)) + 1
            capabilities[failure_key] = failures
            capabilities["last_failure_at"] = datetime.utcnow().isoformat()
            capabilities["last_failure_message"] = error_message[:500]
            is_timeout = "Timed out while polling video results" in error_message
            # Only disable the account after 3 consecutive non-timeout failures
            # (previously a single failure would disable the account, which was
            # too aggressive for transient Bing errors)
            if not is_timeout and failures >= 3:
                if request_type == "image_video":
                    capabilities["image_video_enabled"] = "false"
                else:
                    capabilities["text_video_enabled"] = "false"
                # Set a 5-minute cooldown so the account is retried later
                cooldown = (datetime.utcnow() + timedelta(minutes=5)).isoformat()
                capabilities["cooldown_until"] = cooldown
            record.metadata["video_capabilities"] = capabilities
            record.updated_at = datetime.utcnow()
            await self.store.save(record)
        return record.to_admin_response()

    async def mark_generation_success(self, account_id: str, request_type: str, *, is_fast: bool = False) -> AccountAdminResponse:
        record = await self.get_record(account_id)
        async with self._lock_for(account_id):
            capabilities = dict(record.metadata.get("video_capabilities") or {})
            if request_type == "image_video":
                capabilities["image_video_enabled"] = "true"
                capabilities["image_video_failures"] = 0
                capabilities["last_image_video_ok_at"] = datetime.utcnow().isoformat()
            else:
                capabilities["text_video_enabled"] = "true"
                capabilities["text_video_failures"] = 0
                capabilities["last_text_video_ok_at"] = datetime.utcnow().isoformat()
            capabilities.pop("cooldown_until", None)
            # Auto-decrement fast quota on successful fast generation
            if is_fast:
                remaining = capabilities.get("fast_mode_remaining")
                if remaining is not None:
                    new_remaining = max(0, int(remaining) - 1)
                    capabilities["fast_mode_remaining"] = str(new_remaining)
                    if new_remaining <= 0:
                        capabilities["fast_mode_available"] = "false"
            record.metadata["video_capabilities"] = capabilities
            record.updated_at = datetime.utcnow()
            await self.store.save(record)
        return record.to_admin_response()

    async def get_record(self, account_id: str) -> AccountRecord:
        record = await self.store.get(account_id)
        if record is None:
            raise AccountNotFoundError("Unknown account_id: {0}".format(account_id))
        return record

    async def set_skey(self, account_id: str, skey: str) -> AccountResponse:
        record = await self.get_record(account_id)
        async with self._lock_for(account_id):
            now = datetime.utcnow()
            record.skey = skey
            record.status = "ready"
            record.last_bootstrapped_at = now
            record.updated_at = now
            await self.store.save(record)
        return record.to_response()

    async def record_bootstrap_result(
        self,
        account_id: str,
        *,
        source: Optional[str],
        trace: List[str],
        error: Optional[str] = None,
        skey: Optional[str] = None,
    ) -> AccountAdminResponse:
        record = await self.get_record(account_id)
        async with self._lock_for(account_id):
            now = datetime.utcnow()
            bootstrap_meta = dict(record.metadata.get("bootstrap") or {})
            bootstrap_meta["last_source"] = source
            bootstrap_meta["last_error"] = error
            bootstrap_meta["last_trace"] = trace
            bootstrap_meta["last_attempt_at"] = now.isoformat()
            if skey:
                bootstrap_meta["last_skey_preview"] = "{0}...{1}".format(skey[:6], skey[-6:])
                record.skey = skey
                record.status = "ready"
                record.last_bootstrapped_at = now
            elif error:
                record.status = "stale" if record.skey else "new"
            record.metadata["bootstrap"] = bootstrap_meta
            record.updated_at = now
            await self.store.save(record)
        return record.to_admin_response()

    async def update_account(self, account_id: str, request: AccountUpdateRequest) -> AccountAdminResponse:
        record = await self.get_record(account_id)
        cookies = dict(request.cookies or {})
        if request.cookie_header:
            cookies.update(parse_cookie_header(request.cookie_header))

        async with self._lock_for(account_id):
            if request.name is not None:
                record.name = request.name or None
            if cookies:
                record.cookies = cookies
            if request.skey is not None:
                record.skey = request.skey or None
                if record.skey:
                    record.status = "ready"
                    record.last_bootstrapped_at = datetime.utcnow()
                else:
                    record.status = "new"
            if request.metadata is not None:
                record.metadata = dict(request.metadata)
            if request.cookie_header:
                record.metadata["raw_cookie_header"] = request.cookie_header.strip()
            record.updated_at = datetime.utcnow()
            await self.store.save(record)
        return record.to_admin_response()

    async def delete_account(self, account_id: str) -> None:
        record = await self.store.delete(account_id)
        if record is None:
            raise AccountNotFoundError("Unknown account_id: {0}".format(account_id))
        self._locks.pop(account_id, None)

    async def get_stats(self) -> Dict[str, int]:
        records = await self.store.list()
        total = len(records)
        ready = len([record for record in records if record.status == "ready"])
        stale = len([record for record in records if record.status == "stale"])
        without_skey = len([record for record in records if not record.skey])
        return {
            "total_accounts": total,
            "ready_accounts": ready,
            "stale_accounts": stale,
            "accounts_without_skey": without_skey,
        }

    async def mark_validated(self, account_id: str) -> AccountResponse:
        record = await self.get_record(account_id)
        async with self._lock_for(account_id):
            now = datetime.utcnow()
            record.last_validated_at = now
            if record.skey:
                record.status = "ready"
            record.updated_at = now
            await self.store.save(record)
        return record.to_response()

    async def mark_stale(self, account_id: str) -> AccountResponse:
        record = await self.get_record(account_id)
        async with self._lock_for(account_id):
            record.status = "stale"
            record.updated_at = datetime.utcnow()
            await self.store.save(record)
        return record.to_response()
