from typing import Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from bing_api.core.config import get_settings as load_settings
from bing_api.exceptions import AccountNotFoundError, BingAPIError, VideoGenerationError
from bing_api.models.account import (
    AccountAdminResponse,
    AccountBatchPrepareRequest,
    AccountBatchPrepareResponse,
    AccountBatchRefreshRequest,
    AccountBatchRefreshResponse,
    AccountBootstrapRequest,
    AccountCreateRequest,
    AccountImportRequest,
    AccountImportResponse,
    AccountUpdateRequest,
)
from bing_api.models.video import RetryJobRequest, VideoGenerationRequest, VideoGenerationResponse
from bing_api.models.settings import (
    ProxyTestRequest,
    ProxyTestResponse,
    SettingsResponse,
    SettingsUpdateRequest,
)


router = APIRouter(tags=["admin"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    success: bool
    token: Optional[str] = None
    message: Optional[str] = None


class DurationProbeRequest(BaseModel):
    prompt: str
    ar: str = "1"


class BrowserHealthResponse(BaseModel):
    ok: bool
    node_available: bool
    playwright_core_available: bool
    browser_executable_found: bool
    browser_executable: Optional[str] = None
    detail: Optional[str] = None


def _auth_service(request: Request):
    return request.app.state.admin_auth_service


def _account_service(request: Request):
    return request.app.state.account_service


def _bootstrap_service(request: Request):
    return request.app.state.bootstrap_service


def _video_service(request: Request):
    return request.app.state.video_service


def _duration_probe_service(request: Request):
    return request.app.state.duration_probe_service


def _queue_service(request: Request):
    return request.app.state.queue_service


def _job_store(request: Request):
    return request.app.state.job_store


def _settings_service(request: Request):
    return request.app.state.settings_service


def _proxy_service(request: Request):
    return request.app.state.proxy_service


def _openai_auth_service(request: Request):
    return request.app.state.openai_auth_service


def _account_router_service(request: Request):
    return request.app.state.account_router_service


def _image_upload_service(request: Request):
    return request.app.state.image_upload_service


def _browser_upload_service(request: Request):
    return request.app.state.browser_upload_service


def verify_admin_request(request: Request, authorization: Optional[str]) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")
    service = _auth_service(request)
    try:
        return service.verify(authorization)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.post("/api/login", response_model=LoginResponse)
async def login(payload: LoginRequest, request: Request):
    auth = _auth_service(request)
    try:
        token = auth.login(payload.username, payload.password)
    except ValueError:
        return LoginResponse(success=False, message="Invalid credentials")
    return LoginResponse(success=True, token=token, message="Login successful")


@router.post("/api/logout")
async def logout(request: Request, authorization: Optional[str] = Header(None)):
    token = verify_admin_request(request, authorization)
    _auth_service(request).logout(token)
    return {"success": True, "message": "Logged out successfully"}


@router.get("/api/stats")
async def get_stats(request: Request, authorization: Optional[str] = Header(None)) -> Dict[str, int]:
    verify_admin_request(request, authorization)
    stats = await _account_service(request).get_stats()
    stats.update(await _job_store(request).get_stats())
    bootstrap_stats = await _bootstrap_service(request).get_stats()
    stats["bootstrap_total_attempts"] = bootstrap_stats["total_attempts"]
    stats["bootstrap_successful_attempts"] = bootstrap_stats["successful_attempts"]
    stats["bootstrap_success_rate"] = bootstrap_stats["success_rate"]
    return stats


@router.get("/api/admin/bootstrap/stats")
async def get_bootstrap_stats(request: Request, authorization: Optional[str] = Header(None)):
    verify_admin_request(request, authorization)
    return await _bootstrap_service(request).get_stats()


@router.get("/api/admin/settings", response_model=SettingsResponse)
async def get_settings(request: Request, authorization: Optional[str] = Header(None)):
    verify_admin_request(request, authorization)
    settings = _settings_service(request).settings
    return SettingsResponse(
        openai_api_keys=settings.openai_api_keys,
        global_proxy_url=settings.global_proxy_url,
        request_timeout_seconds=settings.request_timeout_seconds,
        default_poll_interval_seconds=settings.default_poll_interval_seconds,
        default_fast_video_timeout_seconds=settings.default_fast_video_timeout_seconds,
        default_slow_video_timeout_seconds=settings.default_slow_video_timeout_seconds,
        auto_session_refresh_enabled=settings.auto_session_refresh_enabled,
        image_upload_mode=settings.image_upload_mode,
        browser_upload_concurrency=settings.browser_upload_concurrency,
    )


@router.put("/api/admin/settings", response_model=SettingsResponse)
async def update_settings(
    payload: SettingsUpdateRequest,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    verify_admin_request(request, authorization)
    service = _settings_service(request)
    updated = service.apply_updates(
        openai_api_keys=payload.openai_api_keys,
        global_proxy_url=payload.global_proxy_url,
        request_timeout_seconds=payload.request_timeout_seconds,
        default_poll_interval_seconds=payload.default_poll_interval_seconds,
        default_fast_video_timeout_seconds=payload.default_fast_video_timeout_seconds,
        default_slow_video_timeout_seconds=payload.default_slow_video_timeout_seconds,
        auto_session_refresh_enabled=payload.auto_session_refresh_enabled,
        image_upload_mode=payload.image_upload_mode,
        browser_upload_concurrency=payload.browser_upload_concurrency,
    )
    key_source = payload.openai_api_keys or updated.openai_api_keys
    _openai_auth_service(request).api_keys = {
        item.strip() for item in key_source.split(",") if item and item.strip()
    }
    _proxy_service(request).update_global_proxy(updated.global_proxy_url or None)
    # Hot reload runtime settings for already-instantiated services so newly
    # submitted tasks use the updated values immediately.
    load_settings.cache_clear()
    _video_service(request).settings = updated
    _account_router_service(request).settings = updated
    _image_upload_service(request).settings = updated
    _browser_upload_service(request).set_concurrency(updated.browser_upload_concurrency)
    return SettingsResponse(
        openai_api_keys=updated.openai_api_keys,
        global_proxy_url=updated.global_proxy_url,
        request_timeout_seconds=updated.request_timeout_seconds,
        default_poll_interval_seconds=updated.default_poll_interval_seconds,
        default_fast_video_timeout_seconds=updated.default_fast_video_timeout_seconds,
        default_slow_video_timeout_seconds=updated.default_slow_video_timeout_seconds,
        auto_session_refresh_enabled=updated.auto_session_refresh_enabled,
        image_upload_mode=updated.image_upload_mode,
        browser_upload_concurrency=updated.browser_upload_concurrency,
    )


@router.post("/api/admin/settings/test-proxy", response_model=ProxyTestResponse)
async def test_proxy(
    payload: ProxyTestRequest,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    import time

    import httpx

    verify_admin_request(request, authorization)
    target = "https://www.bing.com/"
    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(proxy=payload.proxy_url, timeout=10.0) as client:
            response = await client.get(target)
            response.raise_for_status()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    return ProxyTestResponse(ok=True, elapsed_ms=elapsed_ms, target=target)


@router.get("/api/admin/browser-health", response_model=BrowserHealthResponse)
async def browser_health(request: Request, authorization: Optional[str] = Header(None)):
    verify_admin_request(request, authorization)
    payload = await _browser_upload_service(request).browser_health()
    ok = bool(payload.get("ok"))
    browser_executable = payload.get("browser_executable")
    browser_executable_found = bool(payload.get("browser_executable_found"))
    detail = None if ok else (payload.get("message") or payload.get("error") or payload.get("detail"))
    return BrowserHealthResponse(
        ok=ok,
        node_available=bool(payload.get("node_available")),
        playwright_core_available=bool(payload.get("playwright_core_available")),
        browser_executable_found=browser_executable_found,
        browser_executable=browser_executable,
        detail=detail,
    )


@router.get("/api/admin/accounts", response_model=List[AccountAdminResponse])
async def list_accounts(request: Request, authorization: Optional[str] = Header(None)):
    verify_admin_request(request, authorization)
    return await _account_service(request).list_admin_accounts()


@router.get("/api/admin/accounts/export")
async def export_accounts(request: Request, authorization: Optional[str] = Header(None)):
    verify_admin_request(request, authorization)
    return await _account_service(request).export_accounts()


@router.post("/api/admin/accounts/import", response_model=AccountImportResponse)
async def import_accounts(
    payload: AccountImportRequest,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    verify_admin_request(request, authorization)
    try:
        return await _account_service(request).import_accounts(payload)
    except BingAPIError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/admin/accounts", response_model=AccountAdminResponse)
async def create_account(
    payload: AccountCreateRequest,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    verify_admin_request(request, authorization)
    try:
        created = await _account_service(request).create_account(payload)
        return await _account_service(request).get_admin_account(created.account_id)
    except BingAPIError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/admin/accounts/{account_id}", response_model=AccountAdminResponse)
async def get_account(account_id: str, request: Request, authorization: Optional[str] = Header(None)):
    verify_admin_request(request, authorization)
    try:
        return await _account_service(request).get_admin_account(account_id)
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/api/admin/accounts/{account_id}", response_model=AccountAdminResponse)
async def update_account(
    account_id: str,
    payload: AccountUpdateRequest,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    verify_admin_request(request, authorization)
    try:
        return await _account_service(request).update_account(account_id, payload)
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BingAPIError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/api/admin/accounts/{account_id}")
async def delete_account(account_id: str, request: Request, authorization: Optional[str] = Header(None)):
    verify_admin_request(request, authorization)
    try:
        await _account_service(request).delete_account(account_id)
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"success": True}


@router.post("/api/admin/accounts/{account_id}/bootstrap", response_model=AccountAdminResponse)
async def bootstrap_account(
    account_id: str,
    payload: AccountBootstrapRequest,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    verify_admin_request(request, authorization)
    try:
        response = await _bootstrap_service(request).bootstrap_account(account_id, payload)
        return await _account_service(request).get_admin_account(response.account_id)
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BingAPIError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/admin/accounts/{account_id}/refresh-fast-mode", response_model=AccountAdminResponse)
async def refresh_fast_mode(
    account_id: str,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    verify_admin_request(request, authorization)
    try:
        return await _account_service(request).refresh_fast_mode_status(account_id)
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BingAPIError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/admin/accounts/{account_id}/refresh-session", response_model=AccountAdminResponse)
async def refresh_session(
    account_id: str,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    verify_admin_request(request, authorization)
    try:
        return await _account_service(request).refresh_bing_session(account_id)
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BingAPIError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/admin/accounts/refresh-sessions", response_model=AccountBatchRefreshResponse)
async def refresh_sessions(
    payload: AccountBatchRefreshRequest,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    verify_admin_request(request, authorization)
    try:
        return await _account_service(request).refresh_bing_sessions(payload.account_ids)
    except BingAPIError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/admin/accounts/prepare", response_model=AccountBatchPrepareResponse)
async def prepare_accounts(
    payload: AccountBatchPrepareRequest,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    verify_admin_request(request, authorization)
    try:
        return await _account_service(request).prepare_accounts(payload.account_ids)
    except BingAPIError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/admin/accounts/{account_id}/probe-duration")
async def probe_duration(
    account_id: str,
    payload: DurationProbeRequest,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    verify_admin_request(request, authorization)
    try:
        return await _duration_probe_service(request).probe_hidden_duration(account_id, payload.prompt, payload.ar)
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BingAPIError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/admin/videos/generations", response_model=VideoGenerationResponse)
async def create_generation(
    payload: VideoGenerationRequest,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    verify_admin_request(request, authorization)
    try:
        if payload.use_queue:
            return await _queue_service(request).enqueue_generation(payload)
        return await _video_service(request).create_generation(payload)
    except BingAPIError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/admin/jobs", response_model=List[VideoGenerationResponse])
async def list_jobs(
    request: Request,
    limit: int = 100,
    authorization: Optional[str] = Header(None),
):
    verify_admin_request(request, authorization)
    return await _job_store(request).list(limit=limit)


@router.get("/api/admin/videos/generations/{job_id}", response_model=VideoGenerationResponse)
async def get_generation(job_id: str, request: Request, authorization: Optional[str] = Header(None)):
    verify_admin_request(request, authorization)
    try:
        return await _video_service(request).get_generation(job_id)
    except VideoGenerationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/admin/jobs/{job_id}/retry", response_model=VideoGenerationResponse)
async def retry_generation(
    job_id: str,
    payload: RetryJobRequest,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    verify_admin_request(request, authorization)
    try:
        if request.query_params.get("use_queue") == "1":
            return await _queue_service(request).enqueue_retry(job_id, payload)
        return await _video_service(request).retry_generation(job_id, payload)
    except VideoGenerationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BingAPIError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
