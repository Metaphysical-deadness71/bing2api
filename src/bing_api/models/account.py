import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.utcnow()


class AccountCreateRequest(BaseModel):
    name: Optional[str] = None
    cookies: Dict[str, str] = Field(default_factory=dict)
    cookie_header: Optional[str] = None
    skey: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AccountUpdateRequest(BaseModel):
    account_id: Optional[str] = None
    name: Optional[str] = None
    cookies: Dict[str, str] = Field(default_factory=dict)
    cookie_header: Optional[str] = None
    skey: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class AccountImportRequest(BaseModel):
    accounts: List[AccountUpdateRequest] = Field(default_factory=list)


class AccountImportResponse(BaseModel):
    created: int = 0
    updated: int = 0
    failed: int = 0
    details: List[Dict[str, Any]] = Field(default_factory=list)


class AccountBatchRefreshRequest(BaseModel):
    account_ids: List[str] = Field(default_factory=list)


class AccountBatchRefreshResponse(BaseModel):
    refreshed: int = 0
    failed: int = 0
    details: List[Dict[str, Any]] = Field(default_factory=list)


class AccountBatchPrepareRequest(BaseModel):
    account_ids: List[str] = Field(default_factory=list)


class AccountBatchPrepareResponse(BaseModel):
    prepared: int = 0
    failed: int = 0
    details: List[Dict[str, Any]] = Field(default_factory=list)


class AccountSkeyUpdateRequest(BaseModel):
    skey: str


class AccountBootstrapRequest(BaseModel):
    skey: Optional[str] = None
    create_probe_generation: bool = False
    probe_prompt: str = "A calm anime travel shot of clouds drifting slowly"
    timeout_seconds: float = 180.0
    poll_interval_seconds: float = 2.0


class AccountResponse(BaseModel):
    account_id: str
    name: Optional[str] = None
    status: str
    has_skey: bool
    created_at: datetime
    updated_at: datetime
    last_bootstrapped_at: Optional[datetime] = None
    last_validated_at: Optional[datetime] = None


class AccountAdminResponse(AccountResponse):
    skey: Optional[str] = None
    cookie_count: int = 0
    cookie_names: List[str] = Field(default_factory=list)
    cookie_header: str = ""
    raw_cookie_header: str = ""
    has_raw_cookie_header: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)
    fast_mode_available: Optional[str] = None
    fast_mode_remaining: Optional[str] = None
    image_video_cookie_count: int = 0
    image_video_cookie_names: List[str] = Field(default_factory=list)
    u_cookie_preview: Optional[str] = None
    text_video_inflight: int = 0
    image_video_inflight: int = 0
    text_video_limit: int = 0
    image_video_limit: int = 0
    cooldown_until: Optional[str] = None
    text_video_enabled: Optional[str] = None
    image_video_enabled: Optional[str] = None


@dataclass
class AccountRecord:
    account_id: str
    cookies: Dict[str, str]
    name: Optional[str] = None
    skey: Optional[str] = None
    status: str = "new"
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)
    last_bootstrapped_at: Optional[datetime] = None
    last_validated_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    def to_response(self) -> AccountResponse:
        return AccountResponse(
            account_id=self.account_id,
            name=self.name,
            status=self.status,
            has_skey=bool(self.skey),
            created_at=self.created_at,
            updated_at=self.updated_at,
            last_bootstrapped_at=self.last_bootstrapped_at,
            last_validated_at=self.last_validated_at,
        )

    def to_admin_response(self) -> AccountAdminResponse:
        cookie_names = sorted(self.cookies.keys())
        cookie_header = "; ".join(
            ["{0}={1}".format(name, value) for name, value in self.cookies.items()]
        )
        image_video_keys = ["_U", "_EDGE_S", "SRCHUSR", "SRCHUID", "SRCHD", "MUID", "MUIDB", "ANON", "WLS"]
        image_video_cookie_names = [key for key in image_video_keys if key in self.cookies]
        u_cookie = self.cookies.get("_U")
        u_cookie_preview = None
        if u_cookie:
            head = u_cookie[:6]
            tail = u_cookie[-6:] if len(u_cookie) > 12 else ""
            u_cookie_preview = "{0}...{1}".format(head, tail) if tail else head
        capabilities = self.metadata.get("video_capabilities") or {}
        runtime = self.metadata.get("runtime") or {}
        raw_cookie_header = self.metadata.get("raw_cookie_header") or ""
        return AccountAdminResponse(
            account_id=self.account_id,
            name=self.name,
            status=self.status,
            has_skey=bool(self.skey),
            created_at=self.created_at,
            updated_at=self.updated_at,
            last_bootstrapped_at=self.last_bootstrapped_at,
            last_validated_at=self.last_validated_at,
            skey=self.skey,
            cookie_count=len(self.cookies),
            cookie_names=cookie_names,
            cookie_header=cookie_header,
            raw_cookie_header=raw_cookie_header,
            has_raw_cookie_header=bool(raw_cookie_header),
            metadata=self.metadata,
            fast_mode_available=capabilities.get("fast_mode_available"),
            fast_mode_remaining=capabilities.get("fast_mode_remaining"),
            image_video_cookie_count=len(image_video_cookie_names),
            image_video_cookie_names=image_video_cookie_names,
            u_cookie_preview=u_cookie_preview,
            text_video_inflight=runtime.get("text_video_inflight", 0),
            image_video_inflight=runtime.get("image_video_inflight", 0),
            text_video_limit=runtime.get("text_video_limit", 0),
            image_video_limit=runtime.get("image_video_limit", 0),
            cooldown_until=capabilities.get("cooldown_until"),
            text_video_enabled=capabilities.get("text_video_enabled"),
            image_video_enabled=capabilities.get("image_video_enabled"),
        )
