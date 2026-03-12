import base64
import hashlib
import hmac
import secrets
import time
from typing import Set


class AdminAuthService:
    def __init__(self, username: str, password: str) -> None:
        self.username = username
        self.password = password
        self._revoked_tokens: Set[str] = set()
        self.token_ttl_seconds = 7 * 24 * 60 * 60

    def _secret(self) -> bytes:
        seed = "{0}:{1}".format(self.username, self.password)
        return hashlib.sha256(seed.encode("utf-8")).digest()

    def _sign(self, body: str) -> str:
        digest = hmac.new(self._secret(), body.encode("utf-8"), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

    def login(self, username: str, password: str) -> str:
        if username != self.username or password != self.password:
            raise ValueError("Invalid credentials")
        issued_at = int(time.time())
        expires_at = issued_at + self.token_ttl_seconds
        nonce = secrets.token_urlsafe(12)
        body = "{0}:{1}:{2}".format(self.username, expires_at, nonce)
        token = "admin-{0}.{1}".format(body, self._sign(body))
        return token

    def verify(self, token: str) -> str:
        normalized = token[7:] if token.startswith("Bearer ") else token
        if normalized in self._revoked_tokens:
            raise ValueError("Invalid or expired token")
        if not normalized.startswith("admin-"):
            raise ValueError("Invalid or expired token")
        raw = normalized[6:]
        if "." not in raw:
            raise ValueError("Invalid or expired token")
        body, signature = raw.rsplit(".", 1)
        expected = self._sign(body)
        if not hmac.compare_digest(signature, expected):
            raise ValueError("Invalid or expired token")
        try:
            username, expires_at, _nonce = body.split(":", 2)
            expires_at = int(expires_at)
        except Exception as exc:
            raise ValueError("Invalid or expired token") from exc
        if username != self.username or expires_at < int(time.time()):
            raise ValueError("Invalid or expired token")
        return normalized

    def logout(self, token: str) -> None:
        normalized = token[7:] if token.startswith("Bearer ") else token
        self._revoked_tokens.add(normalized)
