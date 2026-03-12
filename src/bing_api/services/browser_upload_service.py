import asyncio
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional


class BrowserUploadService:
    def __init__(self, browser_proxy_url: Optional[str] = None, concurrency: int = 2) -> None:
        self.browser_proxy_url = browser_proxy_url
        self.set_concurrency(concurrency)

    @property
    def project_root(self) -> Path:
        return Path(__file__).resolve().parents[3]

    @property
    def script_path(self) -> Path:
        return self.project_root / "scripts" / "browser_image_upload.js"

    def set_concurrency(self, concurrency: int) -> None:
        self.concurrency = max(1, int(concurrency))
        self._semaphore = asyncio.Semaphore(self.concurrency)

    async def upload_with_cookies(
        self,
        *,
        cookies: Dict[str, str],
        image_path: str,
        account_name: str,
        proxy_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        script_path = self.script_path
        if not script_path.exists():
            return {"ok": False, "error": "图生视频浏览器上传脚本缺失", "code": "script_missing"}
        async with self._semaphore:
            cookie_file = None
            try:
                with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json", encoding="utf-8") as tmp:
                    json.dump(cookies, tmp, ensure_ascii=False)
                    cookie_file = tmp.name
                env = os.environ.copy()
                effective_proxy = proxy_url or self.browser_proxy_url
                if effective_proxy:
                    env["BROWSER_PROXY"] = effective_proxy
                proc = await asyncio.create_subprocess_exec(
                    "node",
                    str(script_path),
                    "--cookies",
                    cookie_file,
                    "--image",
                    str(image_path),
                    "--accountName",
                    str(account_name),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(self.project_root),
                    env=env,
                )
                stdout, stderr = await proc.communicate()
                stderr_text = stderr.decode("utf-8", errors="ignore") if stderr else ""
                if not stdout:
                    return {"ok": False, "error": "图生视频浏览器上传没有返回结果", "code": "empty_stdout", "stderr": stderr_text, "returncode": proc.returncode}
                try:
                    payload = json.loads(stdout.decode("utf-8", errors="ignore"))
                except Exception:
                    return {"ok": False, "error": "图生视频浏览器上传返回了无效 JSON", "code": "invalid_json", "stdout": stdout.decode("utf-8", errors="ignore"), "stderr": stderr_text, "returncode": proc.returncode}
                if stderr_text:
                    payload["stderr"] = stderr_text
                payload["returncode"] = proc.returncode
                return payload
            finally:
                if cookie_file:
                    Path(cookie_file).unlink(missing_ok=True)

    async def browser_health(self, proxy_url: Optional[str] = None) -> Dict[str, Any]:
        node_available = shutil.which("node") is not None
        playwright_core_available = (self.project_root / "node_modules" / "playwright-core").exists()
        candidates = [
            "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
            "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
            "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
            "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
            "/usr/bin/google-chrome",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/usr/bin/microsoft-edge",
        ]
        browser_executable = next((candidate for candidate in candidates if Path(candidate).exists()), None)
        browser_executable_found = browser_executable is not None
        ok = node_available and playwright_core_available and browser_executable_found
        detail = None
        if not ok:
            missing = []
            if not node_available:
                missing.append("node")
            if not playwright_core_available:
                missing.append("playwright-core")
            if not browser_executable_found:
                missing.append("chrome/edge")
            detail = "缺少: {0}".format(", ".join(missing))
        return {"ok": ok, "node_available": node_available, "playwright_core_available": playwright_core_available, "browser_executable_found": browser_executable_found, "browser_executable": browser_executable, "detail": detail}

    async def aclose(self) -> None:
        return None

    def explain_error(self, payload: Dict[str, Any]) -> str:
        code = str(payload.get("code") or "")
        detail = str(payload.get("message") or payload.get("error") or "").strip()
        converted = payload.get("converted") or {}
        converted_hint = ""
        if converted:
            quality = converted.get("quality")
            width = converted.get("width")
            height = converted.get("height")
            chars = converted.get("chars")
            converted_hint = " (JPEG quality={0}, {1}x{2}, chars={3})".format(
                quality if quality is not None else "?",
                width if width is not None else "?",
                height if height is not None else "?",
                chars if chars is not None else "?",
            )

        explanations = {
            "script_missing": "图生视频浏览器上传脚本缺失",
            "cookie_file_missing": "图生视频上传缺少账号 Cookie 文件",
            "image_file_missing": "图生视频上传缺少图片文件",
            "browser_not_found": "未找到 Chrome / Edge，请安装浏览器或设置 CHROME_PATH",
            "browser_launch_failed": "浏览器启动失败，请检查浏览器路径、代理或运行环境",
            "create_page_open_failed": "无法打开 Bing 图生视频页面，请检查代理、网络或账号会话",
            "sid_missing": "未能从当前账号会话中获取有效 SID，请先修复会话或重新导入完整 cookie header",
            "upload_http_400": "Bing 图片上传返回 400，通常表示当前会话不可用于图生视频上传{0}".format(converted_hint),
            "upload_invalid_json": "Bing 图片上传返回了非 JSON 内容",
            "upload_no_bcid": "Bing 图片上传成功但未返回 bcid",
            "empty_stdout": "浏览器上传脚本没有返回结果",
            "invalid_json": "浏览器上传脚本返回了无效 JSON",
            "unexpected_error": "浏览器上传出现未分类异常",
        }
        base = explanations.get(code, "图生视频浏览器上传失败")
        return "{0}{1}{2}".format(base, "：" if detail else "", detail)
