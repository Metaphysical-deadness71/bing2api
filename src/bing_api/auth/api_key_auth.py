from typing import Iterable, Set


class OpenAIAPIKeyAuth:
    def __init__(self, api_keys: Iterable[str]) -> None:
        self.api_keys: Set[str] = {item.strip() for item in api_keys if item and item.strip()}

    def verify(self, authorization: str) -> str:
        if not authorization:
            raise ValueError("Missing authorization header")
        if not authorization.startswith("Bearer "):
            raise ValueError("Authorization header must use Bearer token")
        token = authorization[7:].strip()
        if token not in self.api_keys:
            raise ValueError("Invalid API key")
        return token
