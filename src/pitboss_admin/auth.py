"""Bearer-token generation, hashing, verification and rotation."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass

from pitboss_admin.models import utc_now
from pitboss_admin.storage import AdministrativeStore


def _digest(token: str, salt: bytes) -> bytes:
    return hashlib.scrypt(token.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)


@dataclass(frozen=True, slots=True)
class TokenStatus:
    configured: bool
    changed_at: str | None


class AdministratorTokens:
    def __init__(self, store: AdministrativeStore) -> None:
        self._store = store

    def status(self) -> TokenStatus:
        record = self._store.auth_record()
        return TokenStatus(record is not None, None if record is None else record[2])

    def bootstrap(self) -> str:
        if self._store.auth_record() is not None:
            raise RuntimeError("administrator token is already configured")
        return self._replace()

    def rotate(self) -> str:
        return self._replace()

    def verify(self, token: str) -> bool:
        record = self._store.auth_record()
        if record is None:
            return False
        salt, expected, _changed_at = record
        return hmac.compare_digest(_digest(token, salt), expected)

    def _replace(self) -> str:
        token = secrets.token_urlsafe(32)
        salt = secrets.token_bytes(16)
        self._store.set_auth_record(salt, _digest(token, salt), utc_now().isoformat())
        return token
