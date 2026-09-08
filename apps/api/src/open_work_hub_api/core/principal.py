from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

CallerPrincipalKind = Literal["user", "service_account", "system"]
CallerPrincipalScope = Literal["personal", "company"]


@dataclass(frozen=True)
class CallerPrincipal:
    kind: CallerPrincipalKind
    source: str
    scope: CallerPrincipalScope = "personal"
    user_id: str | None = None
    service_account_id: str | None = None
    session_id: str | None = None

    @property
    def principal_id(self) -> str | None:
        if self.kind == "user":
            return self.user_id
        if self.kind == "service_account":
            return self.service_account_id
        return None

    def as_payload(self) -> dict[str, str | None]:
        return {
            "kind": self.kind,
            "source": self.source,
            "user_id": self.user_id,
            "service_account_id": self.service_account_id,
            "session_id": self.session_id,
            "principal_id": self.principal_id,
            "scope": self.scope,
        }


def user_principal(
    *,
    user_id: str,
    source: str,
    session_id: str | None = None,
    scope: CallerPrincipalScope = "personal",
) -> CallerPrincipal:
    return CallerPrincipal(
        kind="user",
        scope=scope,
        source=source,
        user_id=user_id,
        session_id=session_id,
    )


def system_principal(
    *,
    source: str,
) -> CallerPrincipal:
    return CallerPrincipal(
        kind="system",
        scope="company",
        source=source,
    )
