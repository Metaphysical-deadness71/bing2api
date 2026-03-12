from datetime import datetime
from typing import Dict, Tuple

from bing_api.models.openai import (
    OpenAIErrorBody,
    OpenAIModel,
    OpenAIModelListResponse,
    OpenAIVideoGenerationRequest,
    OpenAIVideoGenerationResponse,
    OpenAIVideoResult,
)
from bing_api.models.video import VideoGenerationRequest, VideoGenerationResponse


MODEL_DEFAULTS: Dict[str, Dict[str, str]] = {
    "sora-v2-fast": {"aspect_ratio": "16:9", "ar": "5", "mdl": "0"},
    "sora-v2-slow": {"aspect_ratio": "16:9", "ar": "5", "mdl": "1"},
    "sora-v2-landscape-fast": {"aspect_ratio": "16:9", "ar": "5", "mdl": "0"},
    "sora-v2-landscape-slow": {"aspect_ratio": "16:9", "ar": "5", "mdl": "1"},
    "sora-v2-portrait-fast": {"aspect_ratio": "9:16", "ar": "1", "mdl": "0"},
    "sora-v2-portrait-slow": {"aspect_ratio": "9:16", "ar": "1", "mdl": "1"},
}


def supported_models() -> OpenAIModelListResponse:
    now = int(datetime.utcnow().timestamp())
    return OpenAIModelListResponse(
        data=[OpenAIModel(id=model_id, created=now) for model_id in MODEL_DEFAULTS.keys()]
    )


def map_openai_request(payload: OpenAIVideoGenerationRequest, account_id: str) -> Tuple[str, VideoGenerationRequest]:
    if payload.model not in MODEL_DEFAULTS:
        raise ValueError("Unsupported model: {0}".format(payload.model))

    defaults = MODEL_DEFAULTS[payload.model]
    aspect_ratio = payload.aspect_ratio or defaults["aspect_ratio"]
    if payload.size == "landscape":
        aspect_ratio = "16:9"
    elif payload.size == "portrait":
        aspect_ratio = "9:16"

    ar = defaults["ar"]
    mdl = defaults["mdl"]
    if aspect_ratio == "16:9":
        ar = "5"
    elif aspect_ratio == "9:16":
        ar = "1"

    request = VideoGenerationRequest(
        account_id=account_id,
        prompt=payload.prompt,
        aspect_ratio=aspect_ratio,
        ar=ar,
        model="gpt4o",
        wait_for_result=not payload.async_mode,
        use_queue=payload.async_mode,
        timeout_seconds=payload.timeout_seconds,
        extra_form={"aspectRatio": aspect_ratio},
        extra_query={"ar": ar, "mdl": mdl},
        openai_model=payload.model,
    )
    return payload.model, request


def map_status(status: str) -> str:
    if status in {"queued"}:
        return "queued"
    if status in {"submitted", "processing"}:
        return "in_progress"
    if status == "succeeded":
        return "succeeded"
    if status == "failed":
        return "failed"
    return status or "in_progress"


def map_video_response(model: str, response: VideoGenerationResponse) -> OpenAIVideoGenerationResponse:
    created_dt = response.created_at or datetime.utcnow()
    result = None
    error = None
    aspect_ratio = None
    snapshot = response.request_snapshot or {}
    if snapshot.get("aspect_ratio"):
        aspect_ratio = snapshot.get("aspect_ratio")
    if response.detail:
        result = OpenAIVideoResult(
            url=response.detail.content_url,
            thumbnail_url=response.detail.thumbnail_url,
            mime_type="video/mp4",
            aspect_ratio=aspect_ratio,
        )
    if response.status == "failed":
        error = OpenAIErrorBody(
            message=response.message or "Video generation failed",
            type="invalid_request_error",
            code="video_generation_failed",
        )
    return OpenAIVideoGenerationResponse(
        id=response.job_id,
        created=int(created_dt.timestamp()),
        model=model,
        status=map_status(response.status),
        result=result,
        error=error,
    )
