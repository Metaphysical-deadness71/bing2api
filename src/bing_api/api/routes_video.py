from fastapi import APIRouter, HTTPException, Request

from bing_api.exceptions import BingAPIError, SkeyMissingError
from bing_api.models.video import VideoGenerationRequest, VideoGenerationResponse


router = APIRouter(prefix="/videos", tags=["videos"])


def _video_service(request: Request):
    return request.app.state.video_service


def _queue_service(request: Request):
    return request.app.state.queue_service


@router.post("/generations", response_model=VideoGenerationResponse)
async def create_generation(payload: VideoGenerationRequest, request: Request):
    service = _queue_service(request) if payload.use_queue else _video_service(request)
    try:
        if payload.use_queue:
            return await service.enqueue_generation(payload)
        return await service.create_generation(payload)
    except SkeyMissingError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except BingAPIError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/generations/{job_id}", response_model=VideoGenerationResponse)
async def get_generation(job_id: str, request: Request):
    service = _video_service(request)
    try:
        return await service.get_generation(job_id)
    except BingAPIError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
