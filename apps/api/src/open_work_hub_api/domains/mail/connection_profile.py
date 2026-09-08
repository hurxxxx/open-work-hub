from __future__ import annotations

from dataclasses import dataclass

from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.mail.clients import (
    MailConnectionPolicyError,
    MailConnectionSettings,
    validate_connection_settings,
)
from open_work_hub_api.domains.mail.crypto import (
    MailCredentialError,
    decrypt_secret,
    encrypt_secret,
)
from open_work_hub_api.domains.mail.models import MailAccount
from open_work_hub_api.domains.mail.schemas import (
    MailAccountConnectionRequest,
    MailAccountUpdateRequest,
)


@dataclass(frozen=True)
class MailConnectionSecrets:
    incoming_password_encrypted: str
    smtp_password_encrypted: str


def settings_from_payload(payload: MailAccountConnectionRequest) -> MailConnectionSettings:
    return MailConnectionSettings(
        protocol=payload.protocol,
        incoming_host=payload.incoming_host.strip(),
        incoming_port=payload.incoming_port,
        incoming_security=payload.incoming_security,
        incoming_username=payload.incoming_username.strip(),
        incoming_password=payload.incoming_password,
        smtp_host=payload.smtp_host.strip(),
        smtp_port=payload.smtp_port,
        smtp_security=payload.smtp_security,
        smtp_username=payload.smtp_username.strip(),
        smtp_password=payload.smtp_password,
        email_address=str(payload.email_address).strip().lower(),
        display_name=payload.display_name.strip(),
        provider_kind=payload.protocol,
    )


def settings_from_account(row: MailAccount) -> MailConnectionSettings:
    try:
        incoming_password = decrypt_secret(row.incoming_password_encrypted)
        smtp_password = decrypt_secret(row.smtp_password_encrypted)
    except MailCredentialError as exc:
        raise localized_http_exception(status_code=500, code="mail.credential_key_missing") from exc
    return MailConnectionSettings(
        protocol=row.protocol,
        incoming_host=row.incoming_host,
        incoming_port=row.incoming_port,
        incoming_security=row.incoming_security,
        incoming_username=row.incoming_username,
        incoming_password=incoming_password,
        smtp_host=row.smtp_host,
        smtp_port=row.smtp_port,
        smtp_security=row.smtp_security,
        smtp_username=row.smtp_username,
        smtp_password=smtp_password,
        email_address=row.email_address,
        display_name=row.display_name,
        provider_kind=row.provider_kind,
    )


def settings_from_account_update(
    row: MailAccount,
    payload: MailAccountUpdateRequest,
) -> MailConnectionSettings:
    current = settings_from_account(row)
    incoming_password = (
        payload.incoming_password if payload.incoming_password else current.incoming_password
    )
    smtp_password = payload.smtp_password if payload.smtp_password else current.smtp_password
    protocol = payload.protocol or current.protocol
    return MailConnectionSettings(
        protocol=protocol,
        incoming_host=(payload.incoming_host or current.incoming_host).strip(),
        incoming_port=payload.incoming_port or current.incoming_port,
        incoming_security=payload.incoming_security or current.incoming_security,
        incoming_username=(payload.incoming_username or current.incoming_username).strip(),
        incoming_password=incoming_password,
        smtp_host=(payload.smtp_host or current.smtp_host).strip(),
        smtp_port=payload.smtp_port or current.smtp_port,
        smtp_security=payload.smtp_security or current.smtp_security,
        smtp_username=(payload.smtp_username or current.smtp_username).strip(),
        smtp_password=smtp_password,
        email_address=str(payload.email_address or current.email_address).strip().lower(),
        display_name=(
            payload.display_name if payload.display_name is not None else current.display_name
        ).strip(),
        provider_kind=protocol,
    )


def incoming_identity(
    row: MailAccount | MailConnectionSettings,
) -> tuple[str, str, str, int, str, str]:
    return (
        row.email_address,
        row.protocol,
        row.incoming_host,
        row.incoming_port,
        row.incoming_security,
        row.incoming_username,
    )


def encrypt_connection_secrets(settings: MailConnectionSettings) -> MailConnectionSecrets:
    try:
        return MailConnectionSecrets(
            incoming_password_encrypted=encrypt_secret(settings.incoming_password),
            smtp_password_encrypted=encrypt_secret(settings.smtp_password),
        )
    except MailCredentialError as exc:
        raise localized_http_exception(status_code=500, code="mail.credential_key_missing") from exc


def validate_connection_profile(
    settings: MailConnectionSettings,
    *,
    incoming: bool = True,
    smtp: bool = True,
) -> str | None:
    try:
        enforce_connection_profile(settings, incoming=incoming, smtp=smtp)
    except MailConnectionPolicyError as exc:
        return str(exc)
    return None


def enforce_connection_profile(
    settings: MailConnectionSettings,
    *,
    incoming: bool = True,
    smtp: bool = True,
) -> None:
    validate_connection_settings(settings, incoming=incoming, smtp=smtp)
