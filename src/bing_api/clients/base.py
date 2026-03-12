import base64
import random
import re
import secrets
from pathlib import Path
from typing import Dict, Optional, TypeVar

import httpx

from bing_api.core import get_settings


ClientT = TypeVar("ClientT", bound="AsyncBingBaseClient")


def build_default_headers() -> Dict[str, str]:
    forwarded_ip = "13.{0}.{1}.{2}".format(
        random.randint(104, 107),
        random.randint(0, 255),
        random.randint(0, 255),
    )
    return {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "max-age=0",
        "content-type": "application/x-www-form-urlencoded",
        "origin": "https://www.bing.com",
        "referrer": "https://www.bing.com/images/create/",
        "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0",
        "x-forwarded-for": forwarded_ip,
    }


class AsyncBingBaseClient:
    def __init__(self, cookies: Dict[str, str], timeout_seconds: Optional[float] = None, proxy_url: Optional[str] = None) -> None:
        self.settings = get_settings()
        self.cookies = dict(cookies)
        self.timeout_seconds = timeout_seconds or self.settings.request_timeout_seconds
        self.proxy_url = proxy_url
        self.raw_cookie_header: Optional[str] = None
        self._client: Optional[httpx.AsyncClient] = None
        self.u_cookie_preview = self._build_u_preview(self.cookies.get("_U"))

    def _build_u_preview(self, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        head = value[:6]
        tail = value[-6:] if len(value) > 12 else ""
        return "{0}...{1}".format(head, tail) if tail else head

    async def __aenter__(self: ClientT) -> ClientT:
        await self.ensure_client()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    async def ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.settings.bing_base_url,
                headers=build_default_headers(),
                cookies=self.cookies,
                follow_redirects=True,
                timeout=self.timeout_seconds,
                trust_env=True,
                proxy=self.proxy_url,
            )
        return self._client

    async def get(self, path: str, **kwargs) -> httpx.Response:
        client = await self.ensure_client()
        return await client.get(path, **kwargs)

    async def post(self, path: str, **kwargs) -> httpx.Response:
        client = await self.ensure_client()
        return await client.post(path, **kwargs)

    def _safe_get_cookie_value(self, jar, name: str) -> Optional[str]:
        try:
            return jar.get(name)
        except Exception:
            for cookie in getattr(jar, "jar", []):
                if cookie.name == name:
                    return cookie.value
            return None

    def _sid_from_cookie(self, jar, name: str) -> Optional[str]:
        value = self._safe_get_cookie_value(jar, name)
        if value:
            match = re.search(r"SID=([^&;]+)", value)
            if match:
                return match.group(1)
        return None

    def _cookie_header_from_jar(self, jar) -> str:
        pairs = []
        seen = set()
        for cookie in getattr(jar, "jar", []):
            if cookie.value is None:
                continue
            key = (cookie.name, cookie.domain, cookie.path)
            if key in seen:
                continue
            seen.add(key)
            pairs.append("{0}={1}".format(cookie.name, cookie.value))
        return "; ".join(pairs)

    def _extract_global_ig(self, text: str) -> Optional[str]:
        match = re.search(r'_G\.IG\s*=\s*"([A-Z0-9]{10,})"', text)
        if match:
            return match.group(1)
        match = re.search(r'IG=([A-Z0-9]{10,})', text)
        if match:
            return match.group(1)
        return None

    def _extract_iid(self, text: str) -> Optional[str]:
        match = re.search(r'IID=([A-Za-z0-9\.]+)', text)
        if match:
            return match.group(1)
        return None

    async def prepare_image_upload_session(self) -> Dict[str, Optional[str]]:
        client = await self.ensure_client()
        create_referer = "https://www.bing.com/images/create?FORM=GENEXP&ctype=video"

        create_page = await client.get("/images/create", params={"FORM": "GENEXP", "ctype": "video"})
        generator_page = await client.get("/images/create/ai-video-generator", params={"FORM": "GENEXP"})

        create_text = create_page.text or ""
        generator_text = generator_page.text or ""
        ig = self._extract_global_ig(generator_text) or self._extract_global_ig(create_text)
        iid = self._extract_iid(generator_text) or self._extract_iid(create_text) or "images.5041"

        report = None
        try:
            params: Dict[str, str] = {"FORM": "GENEXP", "IID": iid}
            if ig:
                params["IG"] = ig
            report = await client.post(
                "/rewardsapp/reportActivity",
                params=params,
                data={
                    "url": "https://www.bing.com/images/create/ai-video-generator",
                    "action": "view",
                },
                headers={
                    "origin": "https://www.bing.com",
                    "referer": create_referer,
                    "accept": "*/*",
                },
            )
        except Exception:
            report = None

        sid = None
        if report is not None:
            sid = self._sid_from_cookie(report.cookies, "_SS")
        if not sid:
            sid = self._sid_from_cookie(client.cookies, "_SS")
        if not sid:
            sid = self._sid_from_cookie(client.cookies, "_EDGE_S")

        return {
            "sid": sid,
            "ig": ig,
            "iid": iid,
            "referer": create_referer,
        }

    async def set_referer(self, referer: str) -> None:
        client = await self.ensure_client()
        client.headers["referer"] = referer

    async def upload_image(self, image_bytes: bytes, filename: str, sid: str, content_type: str) -> str:
        client = await self.ensure_client()
        encoded = base64.b64encode(image_bytes).decode("ascii")
        session = await self.prepare_image_upload_session()
        upload_sid = session.get("sid") or sid
        referer = session.get("referer") or "https://www.bing.com/images/create?FORM=GENEXP&ctype=video"
        cookie_header = self.raw_cookie_header or self._cookie_header_from_jar(client.cookies)
        # The default client headers include
        #   content-type: application/x-www-form-urlencoded
        # which prevents httpx from auto-setting the correct
        #   content-type: multipart/form-data; boundary=...
        # when files= is used.  Temporarily remove it for this request.
        saved_ct = client.headers.pop("content-type", None)
        boundary = "----WebKitFormBoundary{0}".format(secrets.token_hex(8))
        body = (
            "--{0}\r\n"
            "Content-Disposition: form-data; name=\"imageBase64\"\r\n\r\n"
            "{1}\r\n"
            "--{0}--\r\n"
        ).format(boundary, encoded).encode("utf-8")
        try:
            response = await client.post(
                "/images/create/upload?&sid={0}".format(upload_sid),
                content=body,
                headers={
                    "origin": "https://www.bing.com",
                    "referer": referer,
                    "accept": "*/*",
                    "accept-language": "en-US,en;q=0.9",
                    "cookie": cookie_header,
                    "content-type": "multipart/form-data; boundary={0}".format(boundary),
                    "priority": "u=1, i",
                    "sec-ch-ua": '"Chromium";v="140", "Not=A?Brand";v="24", "Google Chrome";v="140"',
                    "sec-ch-ua-arch": '"x86"',
                    "sec-ch-ua-bitness": '"64"',
                    "sec-ch-ua-full-version": '"140.0.7339.127"',
                    "sec-ch-ua-full-version-list": '"Chromium";v="140.0.7339.127", "Not=A?Brand";v="24.0.0.0", "Google Chrome";v="140.0.7339.127"',
                    "sec-ch-ua-mobile": "?0",
                    "sec-ch-ua-model": '""',
                    "sec-ch-ua-platform": '"Windows"',
                    "sec-ch-ua-platform-version": '"10.0.0"',
                    "sec-fetch-dest": "empty",
                    "sec-fetch-mode": "cors",
                    "sec-fetch-site": "same-origin",
                    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
                },
            )
        finally:
            if saved_ct is not None:
                client.headers["content-type"] = saved_ct
        if response.status_code != 200:
            print(
                f"[upload_image] FAILED status={response.status_code} body={response.text[:500]} "
                f"sid={upload_sid} referer={referer} cookie_pairs={cookie_header.count(';') + 1 if cookie_header else 0}"
            )
        response.raise_for_status()
        data = response.json()
        bcid = data.get("bcid")
        if not bcid:
            raise ValueError("Upload response did not include bcid")
        return bcid

    def minimal_image_video_cookies(self) -> Dict[str, str]:
        source = self.export_cookies()
        keys = ["_U", "_EDGE_S", "_SS", "SRCHUSR", "SRCHUID", "SRCHD", "MUID", "MUIDB", "ANON", "WLS"]
        reduced = {key: source[key] for key in keys if key in source}
        return reduced or source

    def export_cookies(self) -> Dict[str, str]:
        source: Dict[str, str] = {}
        if self._client is not None:
            for cookie in self._client.cookies.jar:
                if cookie.value is None:
                    continue
                # First occurrence wins; avoids KeyError on duplicate names
                if cookie.name not in source:
                    source[cookie.name] = str(cookie.value)
        else:
            source = dict(self.cookies)
        return source

    async def upload_image_variants(self, image_path: str, sid: str) -> str:
        path = Path(image_path)
        image_bytes = path.read_bytes()
        variants = [
            (path.name, image_bytes, self._guess_content_type(path.name)),
        ]
        if path.suffix.lower() in {".jpg", ".jpeg"}:
            variants.append(("upload.jpg", image_bytes, "image/jpeg"))
            variants.append(("upload.png", image_bytes, "image/png"))

        last_error = None
        for filename, payload, content_type in variants:
            try:
                return await self.upload_image(payload, filename, sid, content_type)
            except Exception as exc:
                last_error = exc
        if last_error:
            raise last_error
        raise ValueError("No upload variants available")

    async def get_sid(self) -> Optional[str]:
        session = await self.prepare_image_upload_session()
        return session.get("sid")

    def _guess_content_type(self, filename: str) -> str:
        lower = filename.lower()
        if lower.endswith(".png"):
            return "image/png"
        if lower.endswith(".jpg") or lower.endswith(".jpeg"):
            return "image/jpeg"
        if lower.endswith(".webp"):
            return "image/webp"
        return "application/octet-stream"

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
