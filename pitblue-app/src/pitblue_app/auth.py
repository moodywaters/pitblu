from __future__ import annotations

import hmac
import os
from dataclasses import dataclass
from enum import StrEnum

from fastapi import Request

from pitblue_app.models import DomainError


class Scope(StrEnum):
    OPERATOR = "operator"
    DISPLAY = "display"
    INTEGRATION = "integration"


@dataclass(frozen=True, slots=True)
class AccessControl:
    tokens: dict[Scope, str]
    enabled: bool = True

    @classmethod
    def from_environment(cls) -> AccessControl:
        operator = os.getenv("PITBLUE_APP_OPERATOR_TOKEN", "")
        display = os.getenv("PITBLUE_APP_DISPLAY_TOKEN", "")
        integration = os.getenv("PITBLUE_APP_INTEGRATION_TOKEN", "")
        if len(operator) < 32 or len(display) < 32:
            raise RuntimeError(
                "PITBLUE_APP_OPERATOR_TOKEN and PITBLUE_APP_DISPLAY_TOKEN must each "
                "contain at least 32 characters"
            )
        tokens = {Scope.OPERATOR: operator, Scope.DISPLAY: display}
        if integration:
            if len(integration) < 32:
                raise RuntimeError(
                    "PITBLUE_APP_INTEGRATION_TOKEN must contain at least 32 characters"
                )
            tokens[Scope.INTEGRATION] = integration
        if len(set(tokens.values())) != len(tokens):
            raise RuntimeError("pitblue-app access tokens must be distinct")
        return cls(tokens)

    @classmethod
    def disabled(cls) -> AccessControl:
        return cls({}, enabled=False)

    def follower_signing_secret(self) -> bytes:
        if not self.enabled:
            return b"pitblu-test-follower-signing-secret"
        return self.tokens[Scope.OPERATOR].encode()

    def authenticate(self, request: Request) -> Scope:
        if not self.enabled:
            return Scope.OPERATOR
        authorization = request.headers.get("authorization", "")
        scheme, _, supplied = authorization.partition(" ")
        if scheme.lower() != "bearer":
            supplied = ""
        for scope, expected in self.tokens.items():
            if supplied and hmac.compare_digest(supplied, expected):
                return scope
        raise DomainError("valid bearer token required", 401, "authentication_required")
