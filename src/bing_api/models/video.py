from datetime import datetime
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class VideoCard(BaseModel):
    image_id: str
    detail_path: str
    host_page_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    title: Optional[str] = None
    th_id: Optional[str] = None
    safe_search: Optional[str] = None
    market: Optional[str] = None
    set_lang: Optional[str] = None


class VideoDetail(BaseModel):
    image_id: str
    content_url: str
    thumbnail_url: Optional[str] = None
    prompt: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    encoding_format: Optional[str] = None
    host_page_url: Optional[str] = None
    model_name: Optional[str] = None
    copyright_attr: Optional[str] = None
    raw: Dict[str, Any] = Field(default_factory=dict)


class AsyncResultsPayload(BaseModel):
    mode: str
    cards: List[VideoCard] = Field(default_factory=list)
    details: List[VideoDetail] = Field(default_factory=list)
    raw_text: Optional[str] = None
    resolved_job_id: Optional[str] = None


class VideoGenerationRequest(BaseModel):
    account_id: str
    prompt: str
    aspect_ratio: str = "16:9"
    ar: Optional[str] = None
    model: str = "gpt4o"
    wait_for_result: bool = True
    poll_interval_seconds: float = 2.0
    timeout_seconds: Optional[float] = None
    manual_skey: Optional[str] = None
    safe_search: str = "Strict"
    extra_query: Dict[str, str] = Field(default_factory=dict)
    extra_form: Dict[str, str] = Field(default_factory=dict)
    input_media_context: Optional[str] = None
    input_image_bcid: Optional[str] = None
    use_queue: bool = False
    openai_model: Optional[str] = None


class VideoGenerationResponse(BaseModel):
    job_id: str
    account_id: str
    account_name: Optional[str] = None
    account_u_preview: Optional[str] = None
    client_u_preview: Optional[str] = None
    bing_job_id: Optional[str] = None
    status: str
    prompt: Optional[str] = None
    detail: Optional[VideoDetail] = None
    cards: List[VideoCard] = Field(default_factory=list)
    final_url: Optional[str] = None
    result_mode: Optional[str] = None
    message: Optional[str] = None
    selected_image_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    request_snapshot: Dict[str, Any] = Field(default_factory=dict)
    retried_from_job_id: Optional[str] = None
    queue_status: Optional[str] = None


class RetryJobRequest(BaseModel):
    wait_for_result: Optional[bool] = None
    manual_skey: Optional[str] = None


@dataclass
class VideoCreateResult:
    job_id: str
    response_url: str
    response_text: str
    poll_path: str
    job_id_source: Optional[str] = None
    poll_query: Dict[str, str] = field(default_factory=dict)
