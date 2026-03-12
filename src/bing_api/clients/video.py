import asyncio
import re
import json
from time import monotonic
from typing import Dict, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from bing_api.clients.base import AsyncBingBaseClient
from bing_api.exceptions import ParseError, VideoGenerationError
from bing_api.models.video import AsyncResultsPayload, VideoCard, VideoCreateResult, VideoDetail
from bing_api.parsers import (
    extract_job_id_from_html,
    extract_job_id_from_url,
    extract_job_id_with_source,
    extract_skey_from_text,
    extract_skey_from_url,
    extract_video_card_from_html,
    parse_async_results_payload,
    parse_video_detail_payload,
)


class AsyncBingVideoClient(AsyncBingBaseClient):
    async def create_video_generation(
        self,
        prompt: str,
        aspect_ratio: str = "16:9",
        ar: Optional[str] = None,
        model: str = "gpt4o",
        input_media_context: Optional[str] = None,
        extra_query: Optional[Dict[str, str]] = None,
        extra_form: Optional[Dict[str, str]] = None,
    ) -> VideoCreateResult:
        # Determine mdl from extra_query: "0" = fast, "1" = slow
        mdl = (extra_query or {}).get("mdl", "1")
        is_fast = str(mdl) == "0"

        query: Dict[str, str] = {"q": prompt}
        if ar:
            query["ar"] = str(ar)

        if is_fast or input_media_context:
            # ---- Fast mode / image-to-video ----
            # Browser uses: POST /images/create/ai-video-generator
            #   query: q, rt=4, mdl=0, ar, FORM=GENCRE, sm=1, pt=4
            #   body:  q, model=dalle, aspectRatio
            create_path = "/images/create/ai-video-generator"
            query["rt"] = "4"
            query["mdl"] = str(mdl)
            query["sm"] = "1"
            query["pt"] = "4"
            query["FORM"] = "GENCRE"
            if input_media_context:
                query["ctxt"] = input_media_context
        else:
            # ---- Slow mode (text-to-video only) ----
            # Browser uses: POST /images/create
            #   query: q, sm=0, pt=3, ar, ctype=video
            #   body:  (empty)
            create_path = "/images/create"
            query["sm"] = "0"
            query["pt"] = "3"
            query["ctype"] = "video"

        # Merge any remaining extra_query (skip mdl since we handled it)
        if extra_query:
            for key, value in extra_query.items():
                if key != "mdl":
                    query[key] = str(value)

        # Warmup: fetch IG/IID from a lightweight page that does NOT
        # trigger video creation.  The main create endpoint treats GET
        # with the full creation params as a creation attempt, which
        # "consumes" the nonce so the subsequent POST returns 200 instead
        # of 302.  Use a clean landing page instead.
        warmup_params: Dict[str, str] = {"FORM": "GENEXP"}
        if ar:
            warmup_params["ar"] = str(ar)
        if is_fast or input_media_context:
            warmup_params["ctype"] = "video"
            warmup = await self.get("/images/create/ai-video-generator", params=warmup_params)
        else:
            warmup_params["ctype"] = "video"
            warmup = await self.get("/images/create", params=warmup_params)
        ig = self._extract_global_ig(warmup.text)
        iid = self._extract_iid(warmup)

        # Build POST body
        form = None
        if create_path == "/images/create/ai-video-generator":
            form = {
                "q": prompt,
                "model": model,
                "aspectRatio": aspect_ratio,
            }
            if extra_form:
                form.update({key: str(value) for key, value in extra_form.items()})

        response = await self.post(create_path, params=query, data=form, follow_redirects=False)
        response_text = response.text
        response_url = str(response.url)
        job_id = None
        job_id_source = None
        location = response.headers.get("location")
        if location:
            redirect_url = location if location.startswith("http") else "{0}{1}".format(self.settings.bing_base_url, location)
            job_id = extract_job_id_from_url(redirect_url)
            if job_id:
                response_url = redirect_url
                job_id_source = "location"
        if job_id is None:
            job_id = extract_job_id_from_url(response_url)
            if job_id:
                job_id_source = "response-url"
        if job_id is None:
            for previous in response.history:
                location = previous.headers.get("location")
                candidate_url = location if location else str(previous.url)
                job_id = extract_job_id_from_url(candidate_url)
                if job_id:
                    job_id_source = "redirect-url"
                    break
        # Retry: if first POST returned 200 with no redirect, try once
        # more with IG/IID attached.
        if job_id is None and response.status_code == 200 and not location:
            retry_query = dict(query)
            if "rt" not in retry_query:
                retry_query["rt"] = "4"
            if "FORM" not in retry_query:
                retry_query["FORM"] = "GENCRE"
            if ig:
                retry_query["IG"] = ig
            if iid:
                retry_query["IID"] = iid
            first = await self.post(create_path, params=retry_query, data=form, follow_redirects=False)
            response = first
            response_text = first.text
            response_url = str(first.url)
            location = first.headers.get("location")
            if location:
                redirect_url = location if location.startswith("http") else "{0}{1}".format(self.settings.bing_base_url, location)
                job_id = extract_job_id_from_url(redirect_url)
                if job_id:
                    response_url = redirect_url
                    job_id_source = "location-retry"
        if job_id is None:
            job_id, job_id_source = extract_job_id_with_source(response_text)
        if job_id is None:
            preview = response_text[:4000].replace("\n", " ")
            raise ParseError(
                "Could not extract video job id from create response. status={0} location={1} url={2} preview={3}".format(
                    response.status_code, location, response_url, preview
                )
            )

        poll_path = self._resolve_poll_path(response_url, response.history)
        if query.get("ctype") == "video" and "ai-video-generator" not in create_path:
            poll_path = "/images/create/async/results/{job_id}"
        poll_query: Dict[str, str] = {}
        if ig:
            poll_query["IG"] = ig
        if iid:
            poll_query["IID"] = iid
        poll_query["ctype"] = "video"
        poll_query["mdl"] = str(mdl)
        return VideoCreateResult(
            job_id=job_id,
            job_id_source=job_id_source,
            response_url=response_url,
            response_text=response_text,
            poll_path=poll_path,
            poll_query=poll_query,
        )

    def build_input_media_context(self, bcid: str) -> str:
        payload = [{"InputMediaList": [{"MediaSource": 1, "MediaType": 0, "MediaId": bcid}]}]
        return json.dumps(payload, separators=(",", ":"))

    async def detect_fast_mode_status(self) -> Dict[str, Optional[str]]:
        response = await self.get("/images/create?ctype=video&FORM=GENEXP&rt=4")
        text = response.text
        normalized = text.replace('\\u003a', ':').replace('&quot;', '"')
        status: Dict[str, Optional[str]] = {
            "page_url": str(response.url),
            "fast_mode_available": "unknown",
            "fast_mode_remaining": None,
            "raw_text": None,
        }
        remaining = self._extract_fast_remaining(normalized)
        if remaining is not None:
            status["fast_mode_available"] = "true" if remaining > 0 else "false"
            status["fast_mode_remaining"] = str(remaining)
            status["raw_text"] = "fast remaining parsed from page"
            return status
        if 'fast-cost-text">免费创建次数:' in normalized or 'fast-cost-text\\">免费创建次数:' in normalized:
            status["fast_mode_available"] = "true"
        elif "option-earn-more" in normalized:
            status["fast_mode_available"] = "limited"
        return status

    async def detect_fast_mode_status_from_url(self, page_url: str) -> Dict[str, Optional[str]]:
        response = await self.get(page_url)
        text = response.text
        normalized = text.replace('\\u003a', ':').replace('&quot;', '"')
        status: Dict[str, Optional[str]] = {
            "page_url": str(response.url),
            "fast_mode_available": "unknown",
            "fast_mode_remaining": None,
            "raw_text": None,
        }
        remaining = self._extract_fast_remaining(normalized)
        if remaining is not None:
            status["fast_mode_available"] = "true" if remaining > 0 else "false"
            status["fast_mode_remaining"] = str(remaining)
            status["raw_text"] = "fast remaining parsed from page"
            return status
        if 'fast-cost-text">免费创建次数:' in normalized:
            status["fast_mode_available"] = "true"
        elif "option-earn-more" in normalized:
            status["fast_mode_available"] = "limited"
        return status

    async def poll_video_results(
        self,
        poll_path: str,
        job_id: str,
        prompt: str,
        timeout_seconds: float,
        poll_interval_seconds: float,
        ar: Optional[str] = None,
        extra_query: Optional[Dict[str, str]] = None,
    ) -> AsyncResultsPayload:
        started = monotonic()
        while True:
            if monotonic() - started > timeout_seconds:
                raise VideoGenerationError("Timed out while polling video results")

            query = {
                "q": prompt,
                "mmasync": "1",
                "sm": "1",
            }
            if "mdl" not in (extra_query or {}):
                query["mdl"] = "0" if "ai-video-generator" in poll_path else "1"
            if ar:
                query["ar"] = str(ar)
            if extra_query:
                query.update({key: str(value) for key, value in extra_query.items()})
            query.setdefault("ctype", "video")
            query.setdefault("IID", "images.as")
            query.setdefault("girftp", "1")

            response = await self.get(poll_path.format(job_id=job_id), params=query)
            if response.status_code != 200:
                raise VideoGenerationError("Could not get video results from Bing")

            if not job_id.startswith("4-"):
                resolved = extract_job_id_from_html(response.text)
                if resolved and resolved.startswith("4-"):
                    payload = parse_async_results_payload(response.text, response.headers.get("content-type"))
                    payload.resolved_job_id = resolved
                    return payload

            error_hint = self._extract_generation_error(response.text)
            if error_hint:
                raise VideoGenerationError("Bing reported generation error: {0}".format(error_hint))

            payload = parse_async_results_payload(response.text, response.headers.get("content-type"))
            if payload.mode == "html" and not payload.cards and response.text:
                card = extract_video_card_from_html(response.text)
                if card:
                    payload.cards = [card]
            if payload.raw_text is None:
                payload.raw_text = response.text
            pending = False
            if payload.mode == "json" and not payload.details:
                pending = "Pending" in response.text and "showContent" in response.text
            if payload.details or payload.cards:
                return payload
            if not pending and response.text.strip():
                return payload

            await asyncio.sleep(poll_interval_seconds)

    async def acquire_skey_for_card(self, card: VideoCard) -> Tuple[str, Dict[str, str]]:
        candidates = []
        if card.host_page_url:
            candidates.append(card.host_page_url)
        if card.detail_path:
            candidates.append(card.detail_path)

        for candidate in candidates:
            absolute = candidate if candidate.startswith("http") else "https://www.bing.com{0}".format(candidate)
            response = await self.get(absolute)
            skey = extract_skey_from_text(response.text) or extract_skey_from_url(str(response.url))
            if skey:
                metadata = self._extract_card_request_metadata(card, response)
                return skey, metadata

            overlay_url = self._overlay_url(absolute)
            if overlay_url != absolute:
                overlay_response = await self.get(overlay_url)
                skey = self._extract_overlay_skey(overlay_response.text) or extract_skey_from_url(str(overlay_response.url))
                if skey:
                    metadata = self._extract_card_request_metadata(card, overlay_response)
                    return skey, metadata

                ig = self._extract_ig(overlay_response)
                iid = self._extract_iid(overlay_response)
                if ig:
                    query = {
                        "imageId": card.image_id,
                        "ctype": "video",
                        "safeSearch": card.safe_search or "Moderate",
                        "datatype": "video",
                        "IG": ig,
                        "IID": iid or "idpfs",
                        "SFX": "1",
                    }
                    parsed = urlparse(overlay_url)
                    job_id = self._extract_job_id_from_path(parsed.path)
                    if job_id:
                        detail_probe = await self.get("/images/create/detail/async/{0}".format(job_id), params=query)
                        skey = extract_skey_from_text(detail_probe.text) or extract_skey_from_url(str(detail_probe.url))
                        if skey:
                            metadata = self._extract_card_request_metadata(card, overlay_response)
                            metadata["IG"] = ig
                            metadata["IID"] = iid or "idpfs"
                            return skey, metadata

        raise VideoGenerationError("Could not acquire fresh skey for current video card")

    async def fetch_video_detail(
        self,
        job_id: str,
        image_id: str,
        skey: str,
        safe_search: str = "Strict",
        extra_query: Optional[Dict[str, str]] = None,
    ) -> VideoDetail:
        query = {
            "imageId": image_id,
            "ctype": "video",
            "skey": skey,
            "safeSearch": safe_search,
            "datatype": "video",
            "SFX": "1",
        }
        if extra_query:
            query.update({key: str(value) for key, value in extra_query.items()})
        response = await self.get("/images/create/detail/async/{0}".format(job_id), params=query)
        if response.status_code != 200:
            raise VideoGenerationError("Could not fetch video detail from Bing")
        details = parse_video_detail_payload(response.text)
        if not details:
            raise ParseError("Video detail payload did not include any results")
        return details[0]

    def _resolve_poll_path(self, response_url: str, history) -> str:
        urls = [response_url] + [str(item.url) for item in history]
        for url in urls:
            if "/images/create/ai-video-generator" in url:
                return "/images/create/ai-video-generator/async/results/{job_id}"
        return "/images/create/async/results/{job_id}"

    def _overlay_url(self, url: str) -> str:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        if query.get("view") == ["detailv2"] and query.get("mode") != ["overlay"]:
            query["mode"] = ["overlay"]
            rebuilt = []
            for key, values in query.items():
                for value in values:
                    rebuilt.append("{0}={1}".format(key, value))
            return "{0}?{1}".format(url.split("?")[0], "&".join(rebuilt))
        return url

    def _extract_card_request_metadata(self, card: VideoCard, response) -> Dict[str, str]:
        parsed = urlparse(str(response.url))
        query = parse_qs(parsed.query)
        metadata: Dict[str, str] = {}
        safe_search = card.safe_search or query.get("safeSearch", [None])[0] or "Moderate"
        market = card.market or query.get("mkt", [None])[0]
        set_lang = card.set_lang or query.get("setLang", [None])[0] or query.get("setlang", [None])[0]
        if not market:
            market = self._extract_persisted_query_value(response.text, "mkt")
        if not set_lang:
            set_lang = self._extract_persisted_query_value(response.text, "setLang")
        if safe_search == "Moderate":
            safe_search = self._extract_persisted_query_value(response.text, "safeSearch") or safe_search
        if safe_search:
            metadata["safeSearch"] = safe_search
        if market:
            metadata["mkt"] = market
        if set_lang:
            metadata["setLang"] = set_lang
        ig = self._extract_global_ig(response.text)
        if ig:
            metadata["IG"] = ig
        iid = self._extract_iid(response)
        if iid:
            metadata["IID"] = iid.replace('idpvid', 'idpfs')
        return metadata

    def _extract_overlay_skey(self, text: str) -> Optional[str]:
        value = self._extract_persisted_query_value(text, "skey")
        if value:
            return value
        return extract_skey_from_text(text)

    def _extract_persisted_query_value(self, text: str, key: str) -> Optional[str]:
        match = re.search(r'persistedQueryStrings&quot;:&quot;([^&]+(?:&[^&]+)*)&quot;', text)
        if match:
            query_string = match.group(1).replace('&amp;', '&')
            query = parse_qs(query_string)
            values = query.get(key)
            if values:
                return values[0]
        return None

    def _extract_global_ig(self, text: str) -> Optional[str]:
        match = re.search(r'_G\.IG\s*=\s*"([A-Z0-9]{10,})"', text)
        if match:
            return match.group(1)
        return None

    def _extract_fast_remaining(self, text: str) -> Optional[int]:
        patterns = [
            r'免费创建次数[:：]\s*(\d+)',
            r'aria-label="免费创建次数[:：]\s*(\d+)"',
            r'Fast \((\d+) free remaining\)',
            r'aria-label="(\d+) free creations"',
            r'>(\d+) free creations<',
            r'fast-cost-text">免费创建次数[:：]\s*(\d+)',
            r'fast-cost-text\\">免费创建次数[:：]\s*(\d+)',
            r'create_reward_coin_num[^0-9]{0,20}(\d+)',
            r'fast\s*remaining[^0-9]{0,20}(\d+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                if match.groups():
                    for group in match.groups():
                        if group and group.isdigit():
                            return int(group)
        return None

    def _extract_generation_error(self, text: str) -> Optional[str]:
        normalized = text.replace("\u003c", "<").replace("\u003e", ">")
        normalized = normalized.replace("\\u003c", "<").replace("\\u003e", ">")
        normalized = normalized.replace("&lt;", "<").replace("&gt;", ">")
        # Concurrency / rate-limit patterns (check first for specific diagnosis)
        concurrency_patterns = [
            r"请稍后重试",
            r"稍后再试",
            r"too many requests",
            r"rate limit",
            r"concurrent",
        ]
        for pattern in concurrency_patterns:
            if re.search(pattern, normalized, re.IGNORECASE):
                return "rate_or_concurrency: {0}".format(pattern)
        # General generation-error patterns
        patterns = [
            r"生成错误",
            r"生成视频时出错",
            r"出错",
            r"Something went wrong",
            r"Try again later",
            r"We couldn't create",
            r"糟糕",
            r"error occurred",
            r"unable to generate",
        ]
        for pattern in patterns:
            if re.search(pattern, normalized, re.IGNORECASE):
                return pattern
        return None

    def _extract_ig(self, response) -> Optional[str]:
        text = response.text
        match = re.search(r'IG=([A-Z0-9]{10,})', text)
        if match:
            return match.group(1)
        return None

    def _extract_iid(self, response) -> Optional[str]:
        text = response.text
        match = re.search(r'IID=([A-Za-z0-9\.]+)', text)
        if match:
            return match.group(1)
        return None

    def _extract_job_id_from_path(self, path: str) -> Optional[str]:
        match = re.search(r'(4-[A-Za-z0-9]{6,})', path)
        if match:
            return match.group(1)
        return None
