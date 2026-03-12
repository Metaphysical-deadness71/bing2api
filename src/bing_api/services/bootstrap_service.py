from datetime import datetime
from typing import Callable, Iterable, List, Optional, Set, Tuple
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from bing_api.clients.video import AsyncBingVideoClient
from bing_api.exceptions import BootstrapError
from bing_api.models.account import AccountBootstrapRequest, AccountResponse
from bing_api.models.video import VideoGenerationResponse
from bing_api.parsers import extract_skey_from_text, extract_video_cards_from_html, parse_async_results_payload
from bing_api.services.account_service import AccountService
from bing_api.storage.bootstrap_store import SqliteBootstrapEventStore
from bing_api.storage.job_store import SqliteJobStore


class BootstrapService:
    def __init__(
        self,
        account_service: AccountService,
        job_store: SqliteJobStore,
        bootstrap_event_store: SqliteBootstrapEventStore,
    ) -> None:
        self.account_service = account_service
        self.job_store = job_store
        self.bootstrap_event_store = bootstrap_event_store

    async def bootstrap_account(self, account_id: str, request: AccountBootstrapRequest) -> AccountResponse:
        trace: List[str] = []
        log = self._trace_logger(trace)

        if request.skey:
            log("manual skey provided in bootstrap request")
            response = await self.account_service.record_bootstrap_result(
                account_id,
                source="manual",
                trace=trace,
                skey=request.skey,
            )
            await self._log_attempt(
                account_id=account_id,
                success=True,
                source="manual",
                error=None,
                create_probe_generation=request.create_probe_generation,
                trace=trace,
            )
            return response

        account = await self.account_service.get_record(account_id)
        log("start automatic bootstrap for account {0}".format(account.account_id))
        async with AsyncBingVideoClient(account.cookies) as client:
            skey, source = await self._extract_from_video_home(client, log)
            if skey:
                response = await self.account_service.record_bootstrap_result(
                    account_id,
                    source=source,
                    trace=trace,
                    skey=skey,
                )
                await self._log_attempt(
                    account_id=account_id,
                    success=True,
                    source=source,
                    error=None,
                    create_probe_generation=request.create_probe_generation,
                    trace=trace,
                )
                return response

            recent_jobs = await self.job_store.list_for_account(account_id, limit=20)
            log("checking {0} recent jobs for bootstrap clues".format(len(recent_jobs)))
            skey, source = await self._extract_from_recent_jobs(client, recent_jobs, log)
            if skey:
                response = await self.account_service.record_bootstrap_result(
                    account_id,
                    source=source,
                    trace=trace,
                    skey=skey,
                )
                await self._log_attempt(
                    account_id=account_id,
                    success=True,
                    source=source,
                    error=None,
                    create_probe_generation=request.create_probe_generation,
                    trace=trace,
                )
                return response

            if request.create_probe_generation:
                log("starting probe generation bootstrap")
                skey, source = await self._extract_from_probe_generation(client, request, log)
                if skey:
                    response = await self.account_service.record_bootstrap_result(
                        account_id,
                        source=source,
                        trace=trace,
                        skey=skey,
                    )
                    await self._log_attempt(
                        account_id=account_id,
                        success=True,
                        source=source,
                        error=None,
                        create_probe_generation=request.create_probe_generation,
                        trace=trace,
                    )
                    return response
            else:
                log("probe generation disabled for this bootstrap request")

        message = (
            "Automatic skey bootstrap failed. Try again after this account has at least one self-generated video, "
            "or enable probe generation, or provide skey manually."
        )
        await self.account_service.record_bootstrap_result(
            account_id,
            source=None,
            trace=trace,
            error=message,
        )
        await self._log_attempt(
            account_id=account_id,
            success=False,
            source=None,
            error=message,
            create_probe_generation=request.create_probe_generation,
            trace=trace,
        )
        raise BootstrapError(message)

    async def _extract_from_video_home(
        self,
        client: AsyncBingVideoClient,
        log: Callable[[str], None],
    ) -> Tuple[Optional[str], Optional[str]]:
        candidate_paths = [
            "/images/create?FORM=GENEXP&ctype=video",
            "/images/create?ctype=video&FORM=Bvcmc1",
        ]
        for path in candidate_paths:
            try:
                log("fetching video home candidate {0}".format(path))
                response = await client.get(path)
            except Exception as exc:
                log("video home request failed: {0}".format(exc))
                continue
            skey = self._extract_skey_from_response(response)
            if skey:
                log("skey found directly from video home response")
                return skey, "video_home"
            cards = extract_video_cards_from_html(response.text)
            if cards:
                log("video home exposed {0} candidate cards".format(len(cards)))
                skey, source = await self._extract_from_candidate_cards(client, cards, log)
                if skey:
                    return skey, "video_home_cards:{0}".format(source)
            log("no skey in video home response")
        return None, None

    async def _extract_from_recent_jobs(
        self,
        client: AsyncBingVideoClient,
        jobs: Iterable[VideoGenerationResponse],
        log: Callable[[str], None],
    ) -> Tuple[Optional[str], Optional[str]]:
        seen: Set[str] = set()
        candidates: List[str] = []
        for job in jobs:
            skey, source = await self._extract_from_job_results(client, job, log)
            if skey:
                return skey, source
            if job.detail and job.detail.host_page_url:
                candidates.append(job.detail.host_page_url)
            for card in job.cards:
                if card.host_page_url:
                    candidates.append(card.host_page_url)
                if card.detail_path:
                    candidates.append(card.detail_path)

        for candidate in candidates:
            for url in self._expand_candidate_urls(candidate):
                if url in seen:
                    continue
                seen.add(url)
                log("checking job candidate url {0}".format(url))
                skey = await self._fetch_candidate_skey(client, url, log)
                if skey:
                    return skey, "recent_job_url"
        log("no skey found in recent jobs")
        return None, None

    async def _extract_from_job_results(
        self,
        client: AsyncBingVideoClient,
        job: VideoGenerationResponse,
        log: Callable[[str], None],
    ) -> Tuple[Optional[str], Optional[str]]:
        prompt = job.prompt or (job.request_snapshot or {}).get("prompt")
        if not prompt:
            return None, None
        params = {
            "q": prompt,
            "ctype": "video",
            "mmasync": "1",
            "sm": "1",
            "mdl": "1",
        }
        snapshot = job.request_snapshot or {}
        if snapshot.get("ar"):
            params["ar"] = str(snapshot["ar"])
        extra_query = snapshot.get("extra_query") or {}
        if isinstance(extra_query, dict):
            params.update({key: str(value) for key, value in extra_query.items()})
        log("reloading async results for job {0}".format(job.job_id))
        try:
            response = await client.get("/images/create/async/results/{0}".format(job.job_id), params=params)
        except Exception as exc:
            log("async results reload failed: {0}".format(exc))
            return None, None
        skey = self._extract_skey_from_response(response)
        if skey:
            log("skey found directly in reloaded async results")
            return skey, "recent_job_results"
        payload = parse_async_results_payload(response.text, response.headers.get("content-type"))
        if payload.cards:
            log("reloaded async results exposed {0} cards".format(len(payload.cards)))
            skey, source = await self._extract_from_candidate_cards(client, payload.cards, log)
            if skey:
                return skey, "recent_job_results:{0}".format(source)
        return None, None

    async def _extract_from_candidate_cards(
        self,
        client: AsyncBingVideoClient,
        cards,
        log: Callable[[str], None],
    ) -> Tuple[Optional[str], Optional[str]]:
        seen: Set[str] = set()
        for card in cards:
            candidates = []
            if getattr(card, "host_page_url", None):
                candidates.append(card.host_page_url)
            if getattr(card, "detail_path", None):
                candidates.append(card.detail_path)
            for candidate in candidates:
                for url in self._expand_candidate_urls(candidate):
                    if url in seen:
                        continue
                    seen.add(url)
                    log("checking card candidate url {0}".format(url))
                    skey = await self._fetch_candidate_skey(client, url, log)
                    if skey:
                        return skey, "card_url"
        return None, None

    async def _extract_from_probe_generation(
        self,
        client: AsyncBingVideoClient,
        request: AccountBootstrapRequest,
        log: Callable[[str], None],
    ) -> Tuple[Optional[str], Optional[str]]:
        created = await client.create_video_generation(
            prompt=request.probe_prompt,
            aspect_ratio="16:9",
            ar="5",
            model="gpt4o",
        )
        log("probe generation created job {0}".format(created.job_id))
        payload = await client.poll_video_results(
            poll_path=created.poll_path,
            job_id=created.job_id,
            prompt=request.probe_prompt,
            timeout_seconds=request.timeout_seconds,
            poll_interval_seconds=request.poll_interval_seconds,
        )
        log(
            "probe generation completed with mode={0}, cards={1}, details={2}".format(
                payload.mode,
                len(payload.cards),
                len(payload.details),
            )
        )
        probe_job = VideoGenerationResponse(
            job_id=created.job_id,
            account_id="probe",
            status="submitted",
            prompt=request.probe_prompt,
            cards=payload.cards,
            detail=payload.details[0] if payload.details else None,
            result_mode=payload.mode,
        )
        skey, source = await self._extract_from_recent_jobs(client, [probe_job], log)
        if skey:
            return skey, "probe_generation:{0}".format(source)
        return None, None

    async def _fetch_candidate_skey(
        self,
        client: AsyncBingVideoClient,
        url: str,
        log: Callable[[str], None],
    ) -> Optional[str]:
        try:
            response = await client.get(url)
        except Exception as exc:
            log("candidate request failed: {0}".format(exc))
            return None
        skey = self._extract_skey_from_response(response)
        if skey:
            log("skey found in candidate response")
        else:
            log("candidate response did not include skey")
        return skey

    def _extract_skey_from_response(self, response) -> Optional[str]:
        texts = [str(response.url), response.text]
        texts.extend([str(item.url) for item in getattr(response, "history", [])])
        for text in texts:
            skey = extract_skey_from_text(text)
            if skey:
                return skey
        return None

    def _expand_candidate_urls(self, url: str) -> List[str]:
        absolute = url if url.startswith("http") else "https://www.bing.com{0}".format(url)
        urls = [absolute]
        parsed = urlparse(absolute)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        if query.get("view") == "detailv2":
            overlay_query = dict(query)
            overlay_query.setdefault("mode", "overlay")
            overlay_url = urlunparse(parsed._replace(query=urlencode(overlay_query)))
            if overlay_url not in urls:
                urls.append(overlay_url)
        return urls

    def _trace_logger(self, trace: List[str]) -> Callable[[str], None]:
        def log(message: str) -> None:
            trace.append(message)

        return log

    async def get_stats(self):
        return await self.bootstrap_event_store.get_stats()

    async def _log_attempt(
        self,
        *,
        account_id: str,
        success: bool,
        source: Optional[str],
        error: Optional[str],
        create_probe_generation: bool,
        trace: List[str],
    ) -> None:
        await self.bootstrap_event_store.log_event(
            account_id=account_id,
            success=success,
            source=source,
            error=error,
            create_probe_generation=create_probe_generation,
            created_at=datetime.utcnow().isoformat(),
            trace=trace,
        )
