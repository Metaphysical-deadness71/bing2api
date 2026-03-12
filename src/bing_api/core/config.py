from dataclasses import dataclass
from functools import lru_cache
import os
from pathlib import Path
import json


@dataclass(frozen=True)
class Settings:
    bing_base_url: str
    request_timeout_seconds: float
    default_poll_interval_seconds: float
    default_fast_video_timeout_seconds: float
    default_slow_video_timeout_seconds: float
    admin_username: str
    admin_password: str
    sqlite_path: str
    queue_concurrency: int
    openai_api_keys: str
    global_proxy_url: str
    auto_session_refresh_enabled: bool
    image_upload_mode: str
    browser_upload_concurrency: int


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    data_dir = Path(os.getenv("BING_DATA_DIR", str(Path.cwd() / "data")))
    data_dir.mkdir(parents=True, exist_ok=True)
    settings_path = data_dir / "settings.json"
    file_settings = {}
    if settings_path.exists():
        try:
            file_settings = json.loads(settings_path.read_text(encoding="utf-8")) or {}
        except json.JSONDecodeError:
            file_settings = {}

    def pick(key: str, env_key: str, default: str) -> str:
        if key in file_settings and file_settings[key] is not None:
            return str(file_settings[key])
        return os.getenv(env_key, default)

    return Settings(
        bing_base_url=pick("bing_base_url", "BING_URL", "https://www.bing.com"),
        request_timeout_seconds=float(pick("request_timeout_seconds", "BING_REQUEST_TIMEOUT", "120")),
        default_poll_interval_seconds=float(pick("default_poll_interval_seconds", "BING_POLL_INTERVAL", "2")),
        default_fast_video_timeout_seconds=float(
            pick("default_fast_video_timeout_seconds", "BING_FAST_VIDEO_TIMEOUT", "500")
        ),
        default_slow_video_timeout_seconds=float(
            pick("default_slow_video_timeout_seconds", "BING_SLOW_VIDEO_TIMEOUT", "18000")
        ),
        admin_username=pick("admin_username", "BING_ADMIN_USERNAME", "admin"),
        admin_password=pick("admin_password", "BING_ADMIN_PASSWORD", "admin123"),
        sqlite_path=pick("sqlite_path", "BING_SQLITE_PATH", str(data_dir / "bing_async_api.db")),
        queue_concurrency=int(pick("queue_concurrency", "BING_QUEUE_CONCURRENCY", "2")),
        openai_api_keys=pick("openai_api_keys", "BING_OPENAI_API_KEYS", "bing-demo-key"),
        global_proxy_url=pick("global_proxy_url", "BING_GLOBAL_PROXY", ""),
        auto_session_refresh_enabled=pick("auto_session_refresh_enabled", "BING_AUTO_SESSION_REFRESH", "true").lower() in ("1", "true", "yes", "on"),
        image_upload_mode=pick("image_upload_mode", "BING_IMAGE_UPLOAD_MODE", "browser_first"),
        browser_upload_concurrency=int(pick("browser_upload_concurrency", "BING_BROWSER_UPLOAD_CONCURRENCY", "2")),
    )
