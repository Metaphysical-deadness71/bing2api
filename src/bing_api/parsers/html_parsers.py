import html
import json
import re
from typing import Any, List, Optional, Tuple
from urllib.parse import parse_qs, unquote, urlparse

from bing_api.models.video import VideoCard


JOB_ID_PATTERN = re.compile(r"(4-[A-Za-z0-9]{6,})")


def extract_job_id_from_url(url: str) -> Optional[str]:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if "id" in query and query["id"]:
        candidate = query["id"][0]
        return candidate if JOB_ID_PATTERN.search(candidate) else None
    match = JOB_ID_PATTERN.search(url)
    if match:
        return match.group(1)
    return None


def extract_job_id_from_html(text: str) -> Optional[str]:
    match = JOB_ID_PATTERN.search(text)
    if match:
        return match.group(1)
    patterns = [
        r"jobId\"\s*:\s*\"(?P<id>[0-9a-fA-F\-]{8,})",
        r"jobid\"\s*:\s*\"(?P<id>[0-9a-fA-F\-]{8,})",
        r"taskId\"\s*:\s*\"(?P<id>[0-9a-fA-F\-]{8,})",
        r"requestId\"\s*:\s*\"(?P<id>[0-9a-fA-F\-]{8,})",
        r"jobId\s*=\s*\"(?P<id>[0-9a-fA-F\-]{8,})",
        r"async/results/(?P<id>[0-9a-fA-F\-]{8,})",
        r"detail/async/(?P<id>[0-9a-fA-F\-]{8,})",
        r"data-job-id=\"(?P<id>[0-9a-fA-F\-]{8,})",
        r"data-rewriteurl=\"[^\"]*/(?P<id>4-[A-Za-z0-9]{6,})",
        r"data-mseturl=\"[^\"]*/(?P<id>4-[A-Za-z0-9]{6,})",
        r"data-imgseturl=\"[^\"]*/(?P<id>4-[A-Za-z0-9]{6,})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            candidate = match.group("id") if "id" in match.groupdict() else match.group(1)
            if candidate and JOB_ID_PATTERN.search(candidate):
                return candidate
    embedded = _extract_embedded_state(text)
    if embedded:
        found = _find_job_id_in_json(embedded)
        if found:
            return found
    return None


def extract_job_id_with_source(text: str):
    match = JOB_ID_PATTERN.search(text)
    if match:
        return match.group(1), "jobid-4-prefix"
    patterns = [
        (r"jobId\"\s*:\s*\"(?P<id>[0-9a-fA-F\-]{8,})", "jobid-json"),
        (r"jobid\"\s*:\s*\"(?P<id>[0-9a-fA-F\-]{8,})", "jobid-json"),
        (r"taskId\"\s*:\s*\"(?P<id>[0-9a-fA-F\-]{8,})", "taskid-json"),
        (r"requestId\"\s*:\s*\"(?P<id>[0-9a-fA-F\-]{8,})", "requestid-json"),
        (r"jobId\s*=\s*\"(?P<id>[0-9a-fA-F\-]{8,})", "jobid-attr"),
        (r"async/results/(?P<id>[0-9a-fA-F\-]{8,})", "async-path"),
        (r"detail/async/(?P<id>[0-9a-fA-F\-]{8,})", "detail-path"),
        (r"data-job-id=\"(?P<id>[0-9a-fA-F\-]{8,})", "data-job-id"),
        (r"data-rewriteurl=\"[^\"]*/(?P<id>4-[A-Za-z0-9]{6,})", "data-rewriteurl"),
        (r"data-mseturl=\"[^\"]*/(?P<id>4-[A-Za-z0-9]{6,})", "data-mseturl"),
        (r"data-imgseturl=\"[^\"]*/(?P<id>4-[A-Za-z0-9]{6,})", "data-imgseturl"),
    ]
    for pattern, source in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            candidate = match.group("id") if "id" in match.groupdict() else match.group(1)
            if candidate and JOB_ID_PATTERN.search(candidate):
                return candidate, source
    embedded = _extract_embedded_state(text)
    if embedded:
        found = _find_job_id_in_json(embedded)
        if found:
            return found, "embedded-state"
    return None, None


def extract_video_card_from_html(text: str) -> Optional[VideoCard]:
    cards = extract_video_cards_from_html(text)
    if cards:
        return cards[0]
    return None


def _extract_embedded_state(text: str) -> Optional[Any]:
    markers = [
        "__NEXT_DATA__",
        "__INITIAL_STATE__",
        "__PRELOADED_STATE__",
        "initialState",
        "preloadedState",
        "__INITIAL_DATA__",
    ]
    for marker in markers:
        idx = text.find(marker)
        if idx == -1:
            continue
        json_text = _extract_balanced_json(text, idx)
        if not json_text:
            continue
        try:
            return json.loads(json_text)
        except json.JSONDecodeError:
            continue
    return None


def _extract_balanced_json(text: str, start_index: int) -> Optional[str]:
    brace_index = text.find("{", start_index)
    if brace_index == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(brace_index, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
        else:
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[brace_index : i + 1]
    return None


def _find_job_id_in_json(data: Any) -> Optional[str]:
    if isinstance(data, dict):
        for key, value in data.items():
            key_lower = str(key).lower()
            if key_lower in {"jobid", "taskid", "requestid", "videojobid"}:
                if isinstance(value, str):
                    match = JOB_ID_PATTERN.search(value)
                    if match:
                        return match.group(1)
            found = _find_job_id_in_json(value)
            if found:
                return found
    elif isinstance(data, list):
        for item in data:
            found = _find_job_id_in_json(item)
            if found:
                return found
    elif isinstance(data, str):
        match = JOB_ID_PATTERN.search(data)
        if match:
            return match.group(1)
    return None


def extract_skey_from_text(text: str) -> Optional[str]:
    patterns = [
        r"[?&]skey=([^&\"']+)",
        r"[\"']skey[\"']\s*[:=]\s*[\"']([^\"']+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return unquote(match.group(1))
    return None


def extract_video_cards_from_html(text: str) -> List[VideoCard]:
    source = html.unescape(text)
    pattern = re.compile(
        r'<a[^>]*aria-label="(?P<title>[^"]*)"[^>]*href="(?P<href>[^"]*view=detailv2[^"]*datatype=video[^"]*)"',
        re.IGNORECASE,
    )
    cards = []
    seen = set()
    for match in pattern.finditer(source):
        href = match.group("href")
        parsed = urlparse(href)
        query = parse_qs(parsed.query)
        image_id = query.get("id", [None])[0]
        if not image_id or image_id in seen:
            continue
        seen.add(image_id)
        title = match.group("title") or None
        th_id = query.get("thId", [None])[0]
        safe_search = query.get("safeSearch", [None])[0]
        market = query.get("mkt", [None])[0]
        set_lang = query.get("setLang", [None])[0] or query.get("setlang", [None])[0]
        host_page_url = href if href.startswith("http") else "https://www.bing.com{0}".format(href)
        window = source[match.end() : match.end() + 1000]
        thumb_match = re.search(r'<img[^>]+src="([^"]+)"', window, re.IGNORECASE)
        thumbnail_url = thumb_match.group(1) if thumb_match else None
        cards.append(
            VideoCard(
                image_id=image_id,
                detail_path=href,
                host_page_url=host_page_url,
                thumbnail_url=thumbnail_url,
                title=title,
                th_id=th_id,
                safe_search=safe_search,
                market=market,
                set_lang=set_lang,
            )
        )
    return cards


def extract_skey_from_url(url: str) -> Optional[str]:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    values = query.get("skey")
    if values:
        return values[0]
    return None
