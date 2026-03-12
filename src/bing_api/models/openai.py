from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class OpenAIModel(BaseModel):
    id: str
    object: str = "model"
    created: int
    owned_by: str = "bing-api"


class OpenAIModelListResponse(BaseModel):
    object: str = "list"
    data: List[OpenAIModel]


class OpenAIVideoGenerationRequest(BaseModel):
    model: str
    prompt: str
    aspect_ratio: Optional[str] = None
    size: Optional[str] = None
    async_mode: bool = Field(default=True, alias="async")
    timeout_seconds: Optional[float] = None
    image_base64: Optional[str] = None
    image_mime_type: Optional[str] = None
    image_filename: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        allow_population_by_field_name = True


class OpenAIVideoResult(BaseModel):
    url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    mime_type: Optional[str] = None
    aspect_ratio: Optional[str] = None


class OpenAIErrorBody(BaseModel):
    message: str
    type: str
    code: str


class OpenAIErrorResponse(BaseModel):
    error: OpenAIErrorBody


class OpenAIVideoGenerationResponse(BaseModel):
    id: str
    object: str = "video.generation"
    created: int
    model: str
    status: str
    result: Optional[OpenAIVideoResult] = None
    error: Optional[OpenAIErrorBody] = None
