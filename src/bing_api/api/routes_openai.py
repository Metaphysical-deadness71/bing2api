from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from bing_api.adapters.openai_video_adapter import map_openai_request, map_video_response, supported_models
from bing_api.models.openai import OpenAIErrorBody, OpenAIErrorResponse, OpenAIVideoGenerationRequest


router = APIRouter(prefix="/v1", tags=["openai-compatible"])


def _openai_auth(request: Request):
    return request.app.state.openai_auth_service


def _queue_service(request: Request):
    return request.app.state.queue_service


def _video_service(request: Request):
    return request.app.state.video_service


def _image_upload_service(request: Request):
    return request.app.state.image_upload_service


def _router_service(request: Request):
    return request.app.state.account_router_service


def verify_openai_request(request: Request, authorization: Optional[str]) -> None:
    try:
        _openai_auth(request).verify(authorization or "")
    except ValueError as exc:
        raise HTTPException(
            status_code=401,
            detail=OpenAIErrorResponse(
                error=OpenAIErrorBody(
                    message=str(exc),
                    type="authentication_error",
                    code="invalid_api_key",
                )
            ).dict(),
        ) from exc


@router.get("/models")
async def list_models(request: Request, authorization: Optional[str] = Header(None)):
    verify_openai_request(request, authorization)
    return supported_models()


@router.post("/videos/generations")
async def create_video_generation(
    payload: OpenAIVideoGenerationRequest,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    verify_openai_request(request, authorization)
    excluded_accounts = set()
    try:
        while True:
            model_name, internal_request = map_openai_request(payload, "placeholder")
            account_id = await _router_service(request).select_account(internal_request, exclude_ids=excluded_accounts)
            internal_request.account_id = account_id
            if payload.image_base64:
                bcid = await _image_upload_service(request).upload_base64_for_account(
                    account_id,
                    payload.image_base64,
                    payload.image_filename or "upload.jpg",
                )
                internal_request.input_image_bcid = bcid
            try:
                if internal_request.use_queue:
                    response = await _queue_service(request).enqueue_generation(internal_request)
                else:
                    response = await _video_service(request).create_generation(internal_request)
                return map_video_response(model_name, response)
            except Exception:
                excluded_accounts.add(account_id)
                if len(excluded_accounts) >= 5:
                    raise
    except Exception as exc:
        return JSONResponse(
            status_code=400,
            content=OpenAIErrorResponse(
                error=OpenAIErrorBody(
                    message=str(exc),
                    type="invalid_request_error",
                    code="video_generation_error",
                )
            ).dict(),
        )


@router.get("/videos/generations/{job_id}")
async def get_video_generation(job_id: str, request: Request, authorization: Optional[str] = Header(None)):
    verify_openai_request(request, authorization)
    try:
        response = await _video_service(request).get_generation(job_id)
        snapshot = response.request_snapshot or {}
        model_name = snapshot.get("openai_model") or "sora-v2-fast"
        return map_video_response(model_name, response)
    except Exception as exc:
        return JSONResponse(
            status_code=404,
            content=OpenAIErrorResponse(
                error=OpenAIErrorBody(
                    message=str(exc),
                    type="invalid_request_error",
                    code="job_not_found",
                )
            ).dict(),
        )
