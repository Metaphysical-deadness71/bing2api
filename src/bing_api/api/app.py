from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from bing_api.api.routes_admin import router as admin_router
from bing_api.api.routes_accounts import router as accounts_router
from bing_api.api.routes_health import router as health_router
from bing_api.api.routes_openai import router as openai_router
from bing_api.api.routes_video import router as video_router
from bing_api.auth import OpenAIAPIKeyAuth
from bing_api.core import AdminAuthService, get_settings
from bing_api.services.account_concurrency import AccountConcurrencyManager
from bing_api.services.account_router import AccountRouter
from bing_api.services.account_service import AccountService
from bing_api.services.bootstrap_service import BootstrapService
from bing_api.services.browser_upload_service import BrowserUploadService
from bing_api.services.duration_probe_service import DurationProbeService
from bing_api.services.image_upload_service import ImageUploadService
from bing_api.services.proxy_service import ProxyService
from bing_api.services.queue_service import JobQueueService
from bing_api.services.settings_service import SettingsService
from bing_api.services.video_service import VideoService
from bing_api.storage.account_store import SqliteAccountStore
from bing_api.storage.bootstrap_store import SqliteBootstrapEventStore
from bing_api.storage.job_store import SqliteJobStore
from bing_api.storage.settings_store import JsonSettingsStore


def create_app() -> FastAPI:
    app = FastAPI(title="Bing Async API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    settings = get_settings()
    static_dir = Path(__file__).resolve().parent.parent / "static"

    account_store = SqliteAccountStore(settings.sqlite_path)
    bootstrap_event_store = SqliteBootstrapEventStore(settings.sqlite_path)
    job_store = SqliteJobStore(settings.sqlite_path)
    account_service = AccountService(account_store)
    concurrency_service = AccountConcurrencyManager()
    router_service = AccountRouter(account_service, concurrency_service)
    proxy_service = ProxyService(settings.global_proxy_url or None)
    browser_upload_service = BrowserUploadService(concurrency=settings.browser_upload_concurrency)
    bootstrap_service = BootstrapService(account_service, job_store, bootstrap_event_store)
    duration_probe_service = DurationProbeService(account_service)
    video_service = VideoService(account_service, job_store, concurrency_service)
    image_upload_service = ImageUploadService(account_service, proxy_service, browser_upload_service)
    queue_service = JobQueueService(video_service, concurrency=settings.queue_concurrency)
    settings_store = JsonSettingsStore(settings.sqlite_path.replace("bing_async_api.db", "settings.json"))
    settings_store.save(settings_store.load() or {
        "bing_base_url": settings.bing_base_url,
        "request_timeout_seconds": settings.request_timeout_seconds,
        "default_poll_interval_seconds": settings.default_poll_interval_seconds,
        "default_fast_video_timeout_seconds": settings.default_fast_video_timeout_seconds,
        "default_slow_video_timeout_seconds": settings.default_slow_video_timeout_seconds,
        "admin_username": settings.admin_username,
        "admin_password": settings.admin_password,
        "sqlite_path": settings.sqlite_path,
        "queue_concurrency": settings.queue_concurrency,
        "openai_api_keys": settings.openai_api_keys,
        "global_proxy_url": settings.global_proxy_url,
        "auto_session_refresh_enabled": settings.auto_session_refresh_enabled,
        "image_upload_mode": settings.image_upload_mode,
        "browser_upload_concurrency": settings.browser_upload_concurrency,
        "browser_upload_concurrency": settings.browser_upload_concurrency,
    })
    settings_service = SettingsService(settings, settings_store)
    admin_auth_service = AdminAuthService(
        username=settings.admin_username,
        password=settings.admin_password,
    )
    openai_auth_service = OpenAIAPIKeyAuth(settings.openai_api_keys.split(","))

    app.state.account_store = account_store
    app.state.bootstrap_event_store = bootstrap_event_store
    app.state.job_store = job_store
    app.state.account_service = account_service
    app.state.account_concurrency_service = concurrency_service
    app.state.account_router_service = router_service
    app.state.proxy_service = proxy_service
    app.state.browser_upload_service = browser_upload_service
    app.state.bootstrap_service = bootstrap_service
    app.state.duration_probe_service = duration_probe_service
    app.state.image_upload_service = image_upload_service
    app.state.video_service = video_service
    app.state.queue_service = queue_service
    app.state.settings_service = settings_service
    app.state.admin_auth_service = admin_auth_service
    app.state.openai_auth_service = openai_auth_service
    default_account = None
    with_default = []
    try:
        with_default = account_store._conn.execute("SELECT account_id FROM accounts ORDER BY created_at ASC LIMIT 1").fetchall()
    except Exception:
        with_default = []
    default_account = with_default[0][0] if with_default else None
    app.state.default_openai_account_id = default_account
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.on_event("startup")
    async def startup_event():
        accounts = await account_store.list()
        for account in accounts:
            await concurrency_service.configure_account(account.account_id)
        await queue_service.start()

    @app.on_event("shutdown")
    async def shutdown_event():
        await queue_service.stop()
        await browser_upload_service.aclose()

    @app.get("/", include_in_schema=False)
    async def root_redirect():
        return RedirectResponse(url="/manage")

    @app.get("/login", include_in_schema=False)
    async def login_page():
        return FileResponse(static_dir / "login.html")

    @app.get("/manage", include_in_schema=False)
    async def manage_page():
        return FileResponse(static_dir / "manage.html")

    app.include_router(health_router)
    app.include_router(admin_router)
    app.include_router(accounts_router)
    app.include_router(video_router)
    app.include_router(openai_router)
    return app


app = create_app()
