import json
from typing import Any, Dict, List, Optional, Union

from bing_api.exceptions import ParseError
from bing_api.models.video import AsyncResultsPayload, VideoDetail
from bing_api.parsers.html_parsers import extract_video_cards_from_html


JsonInput = Union[str, Dict[str, Any]]


def _ensure_dict(payload: JsonInput) -> Dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ParseError("Response payload is not valid JSON") from exc


def parse_video_detail_payload(payload: JsonInput) -> List[VideoDetail]:
    data = _ensure_dict(payload)
    values = data.get("value") or []
    details = []
    for item in values:
        metadata = item.get("generationMetadata") or {}
        details.append(
            VideoDetail(
                image_id=item.get("imageId") or item.get("latestEditedImageId") or "",
                content_url=item.get("contentUrl") or "",
                thumbnail_url=item.get("thumbnailUrl"),
                prompt=item.get("name") or item.get("imageAltText"),
                width=item.get("width"),
                height=item.get("height"),
                encoding_format=item.get("encodingFormat"),
                host_page_url=item.get("hostPageUrl"),
                model_name=metadata.get("modelName"),
                copyright_attr=metadata.get("copyrightAttr"),
                raw=item,
            )
        )
    return details


def parse_async_results_payload(text: str, content_type: Optional[str] = None) -> AsyncResultsPayload:
    normalized = (content_type or "").lower()
    stripped = text.lstrip()
    if "json" in normalized or stripped.startswith("{"):
        details = parse_video_detail_payload(text)
        return AsyncResultsPayload(mode="json", details=details, raw_text=text)
    cards = extract_video_cards_from_html(text)
    return AsyncResultsPayload(mode="html", cards=cards, raw_text=text)
