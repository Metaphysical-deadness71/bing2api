from typing import Optional


class ProxyService:
    def __init__(self, global_proxy_url: Optional[str] = None) -> None:
        self.global_proxy_url = global_proxy_url

    def resolve_proxy(self, account_metadata: Optional[dict] = None, request_proxy: Optional[str] = None) -> Optional[str]:
        if request_proxy:
            return request_proxy
        if account_metadata and account_metadata.get("proxy_url"):
            return account_metadata.get("proxy_url")
        return self.global_proxy_url

    def update_global_proxy(self, proxy_url: Optional[str]) -> None:
        self.global_proxy_url = proxy_url
