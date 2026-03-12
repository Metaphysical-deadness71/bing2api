from typing import List

from fastapi import APIRouter, HTTPException, Request

from bing_api.exceptions import AccountNotFoundError, BingAPIError
from bing_api.models.account import (
    AccountBootstrapRequest,
    AccountCreateRequest,
    AccountResponse,
    AccountSkeyUpdateRequest,
)


router = APIRouter(prefix="/accounts", tags=["accounts"])


def _account_service(request: Request):
    return request.app.state.account_service


def _bootstrap_service(request: Request):
    return request.app.state.bootstrap_service


@router.get("", response_model=List[AccountResponse])
async def list_accounts(request: Request):
    service = _account_service(request)
    return await service.list_accounts()


@router.post("", response_model=AccountResponse)
async def create_account(payload: AccountCreateRequest, request: Request):
    service = _account_service(request)
    try:
        return await service.create_account(payload)
    except BingAPIError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{account_id}", response_model=AccountResponse)
async def get_account(account_id: str, request: Request):
    service = _account_service(request)
    try:
        return await service.get_account(account_id)
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{account_id}/skey", response_model=AccountResponse)
async def set_skey(account_id: str, payload: AccountSkeyUpdateRequest, request: Request):
    service = _account_service(request)
    try:
        return await service.set_skey(account_id, payload.skey)
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{account_id}/bootstrap", response_model=AccountResponse)
async def bootstrap_account(account_id: str, payload: AccountBootstrapRequest, request: Request):
    service = _bootstrap_service(request)
    try:
        return await service.bootstrap_account(account_id, payload)
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BingAPIError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
