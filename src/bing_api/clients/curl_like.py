from typing import Dict, Optional

import httpx


class CurlLikeClient:
    def __init__(self, base_url: str, headers: Dict[str, str], cookies: Dict[str, str], timeout: float, proxy_url: Optional[str] = None) -> None:
        self.base_url = base_url
        self.headers = headers
        self.cookies = cookies
        self.timeout = timeout
        self.proxy_url = proxy_url
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        kwargs = dict(
            base_url=self.base_url,
            headers=self.headers,
            cookies=self.cookies,
            follow_redirects=True,
            timeout=self.timeout,
            trust_env=True,
            proxy=self.proxy_url,
        )
        try:
            self._client = httpx.AsyncClient(http2=True, **kwargs)
        except ImportError:
            self._client = httpx.AsyncClient(**kwargs)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def get(self, path: str, **kwargs):
        return await self._client.get(path, **kwargs)

    async def post(self, path: str, **kwargs):
        return await self._client.post(path, **kwargs)
