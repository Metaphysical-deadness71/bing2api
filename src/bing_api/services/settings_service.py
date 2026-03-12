from __future__ import annotations

from dataclasses import asdict
from typing import Dict, Optional

from bing_api.core.config import Settings
from bing_api.storage.settings_store import JsonSettingsStore


class SettingsService:
    def __init__(self, settings: Settings, store: JsonSettingsStore) -> None:
        self._settings = settings
        self._store = store

    def snapshot(self) -> Dict[str, object]:
        return {
            "bing_base_url": self._settings.bing_base_url,
            "request_timeout_seconds": self._settings.request_timeout_seconds,
            "default_poll_interval_seconds": self._settings.default_poll_interval_seconds,
            "default_fast_video_timeout_seconds": self._settings.default_fast_video_timeout_seconds,
            "default_slow_video_timeout_seconds": self._settings.default_slow_video_timeout_seconds,
            "admin_username": self._settings.admin_username,
            "admin_password": self._settings.admin_password,
            "sqlite_path": self._settings.sqlite_path,
            "queue_concurrency": self._settings.queue_concurrency,
            "openai_api_keys": self._settings.openai_api_keys,
            "global_proxy_url": self._settings.global_proxy_url,
            "auto_session_refresh_enabled": self._settings.auto_session_refresh_enabled,
            "image_upload_mode": self._settings.image_upload_mode,
            "browser_upload_concurrency": self._settings.browser_upload_concurrency,
        }

    def persist(self) -> None:
        self._store.save(self.snapshot())

    def apply_updates(
        self,
        *,
        openai_api_keys: Optional[str] = None,
        global_proxy_url: Optional[str] = None,
        queue_concurrency: Optional[int] = None,
        request_timeout_seconds: Optional[float] = None,
        default_poll_interval_seconds: Optional[float] = None,
        default_fast_video_timeout_seconds: Optional[float] = None,
        default_slow_video_timeout_seconds: Optional[float] = None,
        auto_session_refresh_enabled: Optional[bool] = None,
        image_upload_mode: Optional[str] = None,
        browser_upload_concurrency: Optional[int] = None,
    ) -> Settings:
        data = asdict(self._settings)
        if openai_api_keys is not None:
            data["openai_api_keys"] = openai_api_keys
        if global_proxy_url is not None:
            data["global_proxy_url"] = global_proxy_url
        if queue_concurrency is not None:
            data["queue_concurrency"] = queue_concurrency
        if request_timeout_seconds is not None:
            data["request_timeout_seconds"] = request_timeout_seconds
        if default_poll_interval_seconds is not None:
            data["default_poll_interval_seconds"] = default_poll_interval_seconds
        if default_fast_video_timeout_seconds is not None:
            data["default_fast_video_timeout_seconds"] = default_fast_video_timeout_seconds
        if default_slow_video_timeout_seconds is not None:
            data["default_slow_video_timeout_seconds"] = default_slow_video_timeout_seconds
        if auto_session_refresh_enabled is not None:
            data["auto_session_refresh_enabled"] = auto_session_refresh_enabled
        if image_upload_mode is not None:
            data["image_upload_mode"] = image_upload_mode
        if browser_upload_concurrency is not None:
            data["browser_upload_concurrency"] = browser_upload_concurrency
        self._settings = Settings(**data)
        self.persist()
        return self._settings

    @property
    def settings(self) -> Settings:
        return self._settings
