import logging
from datetime import datetime
from typing import Optional

from bing_api.clients.video import AsyncBingVideoClient
from bing_api.core import get_settings

logger = logging.getLogger(__name__)
from bing_api.exceptions import SkeyMissingError, VideoGenerationError
from bing_api.parsers import extract_skey_from_text, extract_skey_from_url
from bing_api.models.video import RetryJobRequest, VideoGenerationRequest, VideoGenerationResponse
from bing_api.services.account_concurrency import AccountConcurrencyManager
from bing_api.services.account_service import AccountService
from bing_api.storage.job_store import InMemoryJobStore


class VideoService:
    def __init__(
        self,
        account_service: AccountService,
        job_store: InMemoryJobStore,
        concurrency_manager: Optional[AccountConcurrencyManager] = None,
    ) -> None:
        self.account_service = account_service
        self.job_store = job_store
        self.settings = get_settings()
        self.concurrency_manager = concurrency_manager

    async def create_generation(self, request: VideoGenerationRequest) -> VideoGenerationResponse:
        return await self._run_generation(request)

    async def create_queued_generation(self, request: VideoGenerationRequest) -> VideoGenerationResponse:
        now = datetime.utcnow()
        account = await self.account_service.get_record(request.account_id)
        u_preview = None
        value = account.cookies.get("_U") if account.cookies else None
        if value:
            head = value[:6]
            tail = value[-6:] if len(value) > 12 else ""
            u_preview = "{0}...{1}".format(head, tail) if tail else head
        placeholder = VideoGenerationResponse(
            job_id="queued-{0}".format(int(now.timestamp() * 1000)),
            account_id=request.account_id,
            account_name=account.name,
            account_u_preview=u_preview,
            client_u_preview=u_preview,
            status="queued",
            prompt=request.prompt,
            result_mode="queued",
            created_at=now,
            updated_at=now,
            request_snapshot=self._dump_request(request),
            queue_status="queued",
        )
        await self.job_store.put(placeholder)
        return placeholder

    async def process_queued_generation(
        self,
        request: VideoGenerationRequest,
        *,
        queued_job_id: str,
        retried_from_job_id: Optional[str] = None,
    ) -> VideoGenerationResponse:
        existing = await self.job_store.get(queued_job_id)
        if existing is None:
            raise VideoGenerationError("Unknown queued job_id: {0}".format(queued_job_id))
        if not existing.account_name or not existing.account_u_preview or not existing.client_u_preview:
            account = await self.account_service.get_record(request.account_id)
            existing.account_name = account.name
            value = account.cookies.get("_U") if account.cookies else None
            if value is not None:
                head = value[:6]
                tail = value[-6:] if len(value) > 12 else ""
                existing.account_u_preview = "{0}...{1}".format(head, tail) if tail else head
                existing.client_u_preview = existing.account_u_preview
        existing.status = "processing"
        existing.queue_status = "processing"
        existing.message = "队列处理中"
        existing.updated_at = datetime.utcnow()
        await self.job_store.put(existing)

        result = await self._run_generation(request, job_override=queued_job_id)
        result.retried_from_job_id = retried_from_job_id
        result.queue_status = "completed"
        # Safety net: if _run_generation returned without completing the
        # polling cycle (e.g. status still "submitted"), mark as failed
        # so the job does not stay stuck forever.
        if result.status in ("submitted", "processing"):
            result.status = "failed"
            result.queue_status = "failed"
            result.message = result.message or ""
            result.message += " [队列处理异常: 轮询未完成即返回]"
            result.updated_at = datetime.utcnow()
        await self.job_store.put(result)
        return result

    async def _run_generation(
        self,
        request: VideoGenerationRequest,
        *,
        job_override: Optional[str] = None,
    ) -> VideoGenerationResponse:
        account = await self.account_service.get_record(request.account_id)
        request_type = "image_video" if request.input_image_bcid or request.input_media_context else "text_video"
        is_fast = str((request.extra_query or {}).get("mdl")) == "0"
        if self.concurrency_manager is not None:
            acquired = await self.concurrency_manager.acquire(request.account_id, request_type)
            if not acquired:
                raise VideoGenerationError("Account concurrency limit reached")
            await self.account_service.update_runtime_state(
                request.account_id,
                await self.concurrency_manager.snapshot(request.account_id),
            )
        def _u_preview(cookies):
            value = cookies.get("_U") if cookies else None
            if not value:
                return None
            head = value[:6]
            tail = value[-6:] if len(value) > 12 else ""
            return "{0}...{1}".format(head, tail) if tail else head

        async with AsyncBingVideoClient(account.cookies) as client:
            try:
                input_media_context = request.input_media_context
                if request.input_image_bcid:
                    input_media_context = client.build_input_media_context(request.input_image_bcid)
                created = await client.create_video_generation(
                    prompt=request.prompt,
                    aspect_ratio=request.aspect_ratio,
                    ar=request.ar,
                    model=request.model,
                    input_media_context=input_media_context,
                    extra_query=request.extra_query,
                    extra_form=request.extra_form,
                )

                if not created.job_id.startswith("4-"):
                    response = VideoGenerationResponse(
                        job_id=job_override or created.job_id,
                        account_id=request.account_id,
                        account_name=account.name,
                        account_u_preview=_u_preview(account.cookies),
                        client_u_preview=client.u_cookie_preview,
                        bing_job_id=created.job_id,
                        status="failed",
                        prompt=request.prompt,
                        final_url=created.response_url,
                        result_mode="create",
                        message="创建阶段未获取到正确的 4- job id，请重试",
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                        request_snapshot=self._dump_request(request),
                        queue_status="failed" if job_override else None,
                    )
                    await self.job_store.put(response)
                    raise VideoGenerationError("Create response did not include 4- job id")

                now = datetime.utcnow()
                response = VideoGenerationResponse(
                    job_id=job_override or created.job_id,
                    account_id=request.account_id,
                    account_name=account.name,
                    account_u_preview=_u_preview(account.cookies),
                    client_u_preview=client.u_cookie_preview,
                    bing_job_id=created.job_id,
                    status="submitted",
                    prompt=request.prompt,
                    final_url=created.response_url,
                    result_mode="create",
                    message="创建任务成功，准备轮询 (bing_job_id={0}, source={1})".format(
                        created.job_id, created.job_id_source or "unknown"
                    ),
                    created_at=now,
                    updated_at=now,
                    request_snapshot=self._dump_request(request),
                    queue_status="processing" if job_override else None,
                )
                await self.job_store.put(response)

                # When running inside the queue (job_override is set), always
                # continue to poll regardless of wait_for_result.  The flag
                # only controls whether a *direct* (non-queued) caller should
                # block waiting for the result.
                if not request.wait_for_result and job_override is None:
                    logger.info("Early return: wait_for_result=False, job_override=None, job=%s", response.job_id)
                    return response

                logger.info("Entering poll loop: job=%s, job_override=%s, wait_for_result=%s",
                            response.job_id, job_override, request.wait_for_result)

                poll_query = dict(getattr(created, "poll_query", {}) or {})
                if request.extra_query:
                    poll_query.update({key: str(value) for key, value in request.extra_query.items()})
                poll_url = "{0}{1}".format(client.settings.bing_base_url, created.poll_path.format(job_id=created.job_id))
                if poll_query:
                    pairs = "&".join(["{0}={1}".format(k, v) for k, v in poll_query.items()])
                    poll_url = "{0}?{1}".format(poll_url, pairs)
                response.status = "processing"
                response.message = "轮询中: {0} (job_id={1})".format(poll_url, created.job_id)
                response.updated_at = datetime.utcnow()
                await self.job_store.put(response)

                timeout_seconds = request.timeout_seconds
                if timeout_seconds is None:
                    is_slow = str((request.extra_query or {}).get("mdl")) == "1"
                    timeout_seconds = (
                        self.settings.default_slow_video_timeout_seconds
                        if is_slow
                        else self.settings.default_fast_video_timeout_seconds
                    )

                payload = await client.poll_video_results(
                    poll_path=created.poll_path,
                    job_id=created.job_id,
                    prompt=request.prompt,
                    timeout_seconds=timeout_seconds,
                    poll_interval_seconds=request.poll_interval_seconds or self.settings.default_poll_interval_seconds,
                    ar=request.ar,
                    extra_query=poll_query or None,
                )
                if payload.resolved_job_id and payload.resolved_job_id != created.job_id:
                    created.job_id = payload.resolved_job_id
                    response.bing_job_id = payload.resolved_job_id
                    poll_url = "{0}{1}".format(
                        client.settings.bing_base_url, created.poll_path.format(job_id=payload.resolved_job_id)
                    )
                    if poll_query:
                        pairs = "&".join(["{0}={1}".format(k, v) for k, v in poll_query.items()])
                        poll_url = "{0}?{1}".format(poll_url, pairs)
                    response.message = "轮询已纠正 job_id，继续: {0}".format(poll_url)
                    response.updated_at = datetime.utcnow()
                    await self.job_store.put(response)
                    payload = await client.poll_video_results(
                        poll_path=created.poll_path,
                        job_id=payload.resolved_job_id,
                        prompt=request.prompt,
                        timeout_seconds=timeout_seconds,
                        poll_interval_seconds=request.poll_interval_seconds or self.settings.default_poll_interval_seconds,
                        ar=request.ar,
                        extra_query=poll_query or None,
                    )

                response.cards = payload.cards
                response.result_mode = payload.mode
                response.updated_at = datetime.utcnow()
                response.message = "轮询完成，解析结果中"
                await self.job_store.put(response)

                if payload.details:
                    response.detail = payload.details[0]
                    response.final_url = payload.details[0].content_url
                    response.selected_image_id = payload.details[0].image_id
                    response.status = "succeeded"
                    response.queue_status = "completed" if job_override else response.queue_status
                    response.message = "生成完成"
                    if payload.cards:
                        try:
                            skey, _ = await client.acquire_skey_for_card(payload.cards[0])
                            if skey:
                                await self.account_service.set_skey(request.account_id, skey)
                        except Exception:
                            pass
                    await self.account_service.mark_validated(request.account_id)
                    await self.account_service.mark_generation_success(request.account_id, request_type, is_fast=is_fast)
                    await self.job_store.put(response)
                    return response

                if not payload.cards:
                    snippet = (payload.raw_text or "")[:400]
                    raise VideoGenerationError(
                        "Bing did not return any video cards or details. response_snippet={0}".format(
                            snippet
                        )
                    )

                detail_query = {}
                detail_ref = payload.cards[0].detail_path or payload.cards[0].host_page_url
                if detail_ref:
                    response.message = "已获取卡片，开始获取详情页 skey"
                    response.updated_at = datetime.utcnow()
                    await self.job_store.put(response)
                    absolute = detail_ref if detail_ref.startswith("http") else "https://www.bing.com{0}".format(detail_ref)
                    try:
                        pre = await client.get(absolute)
                        pre_skey = extract_skey_from_text(pre.text) or extract_skey_from_url(str(pre.url))
                        if pre_skey:
                            skey = pre_skey
                            detail_query.update(client._extract_card_request_metadata(payload.cards[0], pre))
                            await self.account_service.set_skey(request.account_id, skey)
                    except Exception:
                        pass
                if request.manual_skey:
                    skey = request.manual_skey
                else:
                    response.message = "已获取卡片，尝试获取 skey"
                    response.updated_at = datetime.utcnow()
                    await self.job_store.put(response)
                    try:
                        skey, detail_metadata = await client.acquire_skey_for_card(payload.cards[0])
                    except Exception as exc:
                        response.message = "获取 skey 失败: {0}".format(str(exc))
                        response.updated_at = datetime.utcnow()
                        await self.job_store.put(response)
                        raise
                    detail_query.update(detail_metadata)
                    if skey:
                        await self.account_service.set_skey(request.account_id, skey)

                if not skey:
                    raise SkeyMissingError("Could not acquire a fresh skey for the current video card")
                response.message = "获取详情中"
                response.updated_at = datetime.utcnow()
                await self.job_store.put(response)
                detail = await client.fetch_video_detail(
                    job_id=created.job_id,
                    image_id=payload.cards[0].image_id,
                    skey=skey,
                    safe_search=detail_query.get("safeSearch", request.safe_search),
                    extra_query=detail_query,
                )
            except Exception as exc:
                response = locals().get("response")
                if response is not None:
                    response.status = "failed"
                    response.message = str(exc)
                    response.updated_at = datetime.utcnow()
                    response.queue_status = "failed" if job_override else response.queue_status
                    await self.job_store.put(response)
                error_message = str(exc)
                is_timeout = "Timed out while polling video results" in error_message
                if not is_timeout:
                    await self.account_service.mark_stale(request.account_id)
                await self.account_service.mark_generation_failure(request.account_id, request_type, error_message)
                raise
            finally:
                if self.concurrency_manager is not None:
                    await self.concurrency_manager.release(request.account_id, request_type)
                    await self.account_service.update_runtime_state(
                        request.account_id,
                        await self.concurrency_manager.snapshot(request.account_id),
                    )

            response.detail = detail
            response.status = "succeeded"
            response.result_mode = "detail_async"
            response.selected_image_id = detail.image_id
            response.final_url = detail.content_url
            response.updated_at = datetime.utcnow()
            response.queue_status = "completed" if job_override else response.queue_status
            response.message = "生成完成"
            await self.account_service.mark_validated(request.account_id)
            await self.account_service.mark_generation_success(request.account_id, request_type, is_fast=is_fast)
            await self.job_store.put(response)
            return response

    async def list_generations(self, limit: int = 100):
        return await self.job_store.list(limit=limit)

    async def get_generation(self, job_id: str) -> VideoGenerationResponse:
        record = await self.job_store.get(job_id)
        if record is None:
            raise VideoGenerationError("Unknown video job_id: {0}".format(job_id))
        return record

    async def build_retry_request(self, job_id: str, request: RetryJobRequest) -> VideoGenerationRequest:
        existing = await self.get_generation(job_id)
        snapshot = dict(existing.request_snapshot or {})
        if not snapshot:
            if not existing.prompt:
                raise VideoGenerationError("Job has no retryable request snapshot")
            snapshot = {
                "account_id": existing.account_id,
                "prompt": existing.prompt,
                "aspect_ratio": "16:9",
                "ar": "5",
                "wait_for_result": True,
            }
        if request.wait_for_result is not None:
            snapshot["wait_for_result"] = request.wait_for_result
        if request.manual_skey is not None:
            snapshot["manual_skey"] = request.manual_skey
        return VideoGenerationRequest(**snapshot)

    async def create_retry_placeholder(self, job_id: str, request: RetryJobRequest) -> VideoGenerationResponse:
        retry_request = await self.build_retry_request(job_id, request)
        placeholder = await self.create_queued_generation(retry_request)
        placeholder.retried_from_job_id = job_id
        placeholder.queue_status = "queued"
        await self.job_store.put(placeholder)
        return placeholder

    async def retry_generation(self, job_id: str, request: RetryJobRequest) -> VideoGenerationResponse:
        retry_request = await self.build_retry_request(job_id, request)
        retried = await self._run_generation(retry_request)
        retried.retried_from_job_id = job_id
        await self.job_store.put(retried)
        return retried

    def _dump_request(self, request: VideoGenerationRequest):
        if hasattr(request, "model_dump"):
            return request.model_dump()
        return request.dict()
