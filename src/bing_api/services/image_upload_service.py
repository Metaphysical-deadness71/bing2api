import base64
import tempfile
from io import BytesIO
from pathlib import Path

from bing_api.clients.base import AsyncBingBaseClient
from bing_api.core import get_settings
from bing_api.exceptions import VideoGenerationError
from bing_api.services.account_service import AccountService
from bing_api.services.browser_upload_service import BrowserUploadService
from bing_api.services.proxy_service import ProxyService

try:
    from PIL import Image
except Exception:  # pragma: no cover - optional at runtime until installed
    Image = None


class ImageUploadService:
    def __init__(
        self,
        account_service: AccountService,
        proxy_service: ProxyService | None = None,
        browser_upload_service: BrowserUploadService | None = None,
    ) -> None:
        self.account_service = account_service
        self.proxy_service = proxy_service or ProxyService()
        self.browser_upload_service = browser_upload_service or BrowserUploadService()
        self.settings = get_settings()

    async def upload_for_account(self, account_id: str, image_path: str) -> str:
        if self.settings.auto_session_refresh_enabled:
            await self.account_service.ensure_fresh_session(account_id, "image_video")
        record = await self.account_service.get_record(account_id)
        mode = (self.settings.image_upload_mode or "browser_first").lower()
        if mode not in {"browser_only", "browser_first"}:
            mode = "browser_first"

        browser_result = await self._upload_with_browser(record, image_path)
        if browser_result and browser_result.get("ok") and browser_result.get("bcid"):
            return str(browser_result.get("bcid"))
        if mode == "browser_only" and browser_result and browser_result.get("error"):
            raise VideoGenerationError(browser_result.get("error"))
        proxy_url = self.proxy_service.resolve_proxy(record.metadata)
        async with AsyncBingBaseClient(record.cookies, proxy_url=proxy_url) as client:
            client.raw_cookie_header = record.metadata.get("raw_cookie_header")
            sid = await client.get_sid()
            if not sid:
                raise VideoGenerationError("Could not derive SID from current account session")
            try:
                return await client.upload_image_variants(image_path, sid)
            except Exception:
                if browser_result and browser_result.get("error"):
                    raise VideoGenerationError(browser_result.get("error"))
                raise

    async def upload_base64_for_account(
        self,
        account_id: str,
        image_base64: str,
        image_filename: str = "upload.jpg",
    ) -> str:
        raw = image_base64
        if "," in image_base64 and image_base64.startswith("data:"):
            raw = image_base64.split(",", 1)[1]
        image_bytes = base64.b64decode(raw)
        suffix = Path(image_filename).suffix or ".jpg"
        image_bytes, suffix = self._prepare_image_for_bing_upload(image_bytes, suffix)
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(image_bytes)
            tmp_path = tmp.name
        try:
            return await self.upload_for_account(account_id, tmp_path)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def _prepare_image_for_bing_upload(self, image_bytes: bytes, suffix: str) -> tuple[bytes, str]:
        # Browser uploads that succeed are much smaller than the raw images
        # users often provide through the API.  Pre-compress oversized inputs
        # for image-to-video only; this does not affect text-to-video.
        if Image is None:
            print("[image_upload] Pillow not installed; skipping image compression")
            return image_bytes, suffix
        # Fast path: keep small images unchanged.
        if len(image_bytes) <= 220 * 1024:
            print(f"[image_upload] image already small enough: {len(image_bytes)} bytes")
            return image_bytes, suffix
        try:
            original_size = len(image_bytes)
            with Image.open(BytesIO(image_bytes)) as img:
                if img.mode not in ("RGB", "L"):
                    img = img.convert("RGB")
                else:
                    img = img.copy()
                max_side = 1024
                img.thumbnail((max_side, max_side))

                for quality in (88, 82, 76, 70, 64, 58):
                    buf = BytesIO()
                    img.save(buf, format="JPEG", quality=quality, optimize=True)
                    payload = buf.getvalue()
                    if len(payload) <= 220 * 1024:
                        print(
                            f"[image_upload] compressed image from {original_size} to {len(payload)} bytes "
                            f"using JPEG quality={quality}"
                        )
                        return payload, ".jpg"

                buf = BytesIO()
                img.save(buf, format="JPEG", quality=52, optimize=True)
                print(
                    f"[image_upload] compressed image from {original_size} to {len(buf.getvalue())} bytes "
                    "using JPEG quality=52 fallback"
                )
                return buf.getvalue(), ".jpg"
        except Exception:
            return image_bytes, suffix

    async def _upload_with_browser(self, record, image_path: str) -> dict | None:
        proxy_url = self.proxy_service.resolve_proxy(record.metadata)
        payload = await self.browser_upload_service.upload_with_cookies(
            cookies=record.cookies,
            image_path=str(image_path),
            account_name=str(record.name or record.account_id),
            proxy_url=proxy_url,
        )
        stderr_text = payload.get("stderr")
        if stderr_text:
            print(stderr_text)
        if payload.get("ok") and payload.get("bcid"):
            return payload
        if not payload.get("ok"):
            message = self.browser_upload_service.explain_error(payload)
            return {"ok": False, "error": message, "payload": payload}
        return {"ok": False, "error": "图生视频浏览器上传未返回 bcid", "payload": payload}
