from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


CallerPrincipalKind = Literal["user", "service_account", "system"]


@dataclass(frozen=True)
class CallerPrincipal:
    kind: CallerPrincipalKind
    workspace_id: str
    source: str
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
            "workspace_id": self.workspace_id,
            "source": self.source,
            "user_id": self.user_id,
            "service_account_id": self.service_account_id,
            "session_id": self.session_id,
            "principal_id": self.principal_id,
        }


def user_principal(
    *,
    workspace_id: str,
    user_id: str,
    source: str,
    session_id: str | None = None,
) -> CallerPrincipal:
    return CallerPrincipal(
        kind="user",
        workspace_id=workspace_id,
        source=source,
        user_id=user_id,
        session_id=session_id,
    )


def system_principal(
    *,
    workspace_id: str,
    source: str,
) -> CallerPrincipal:
    return CallerPrincipal(
        kind="system",
        workspace_id=workspace_id,
        source=source,
    )
