from typing import Optional

from pydantic import BaseModel


class SettingsResponse(BaseModel):
    openai_api_keys: str
    global_proxy_url: str
    request_timeout_seconds: float
    default_poll_interval_seconds: float
    default_fast_video_timeout_seconds: float
    default_slow_video_timeout_seconds: float
    auto_session_refresh_enabled: bool
    image_upload_mode: str
    browser_upload_concurrency: int


class SettingsUpdateRequest(BaseModel):
    openai_api_keys: Optional[str] = None
    global_proxy_url: Optional[str] = None
    request_timeout_seconds: Optional[float] = None
    default_poll_interval_seconds: Optional[float] = None
    default_fast_video_timeout_seconds: Optional[float] = None
    default_slow_video_timeout_seconds: Optional[float] = None
    auto_session_refresh_enabled: Optional[bool] = None
    image_upload_mode: Optional[str] = None
    browser_upload_concurrency: Optional[int] = None


class ProxyTestRequest(BaseModel):
    proxy_url: str


class ProxyTestResponse(BaseModel):
    ok: bool
    elapsed_ms: int
    target: str
