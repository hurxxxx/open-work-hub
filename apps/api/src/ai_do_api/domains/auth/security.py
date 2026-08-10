from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import re
import secrets
import uuid


PASSWORD_SCHEME = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 600_000
LOGIN_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{2,39}$")


@dataclass(frozen=True)
class IssuedToken:
    plain_text: str
    token_hash: str
    expires_at: datetime


def normalize_email(value: str) -> str:
    return value.strip().lower()


def normalize_login_id(value: str) -> str:
    return value.strip().lower()


def is_valid_login_id(value: str) -> bool:
    return LOGIN_ID_PATTERN.fullmatch(value) is not None


def derive_login_id_from_email(email: str) -> str:
    local_part = normalize_email(email).split("@", 1)[0]
    candidate = re.sub(r"[^a-z0-9._-]+", "-", normalize_login_id(local_part))
    candidate = candidate.strip("._-")[:40]
    if len(candidate) < 3:
        candidate = f"user-{candidate}" if candidate else "user"
    candidate = candidate[:40].strip("._-")
    if not candidate or not candidate[0].isalnum():
        candidate = f"user-{candidate}"[:40].strip("._-")
    return candidate if is_valid_login_id(candidate) else "user"


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_ITERATIONS,
    )
    return f"{PASSWORD_SCHEME}${PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded_password: str) -> bool:
    try:
        scheme, iteration_text, salt_hex, digest_hex = encoded_password.split("$", 3)
    except ValueError:
        return False

    if scheme != PASSWORD_SCHEME:
        return False

    candidate = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt_hex),
        int(iteration_text),
    ).hex()
    return hmac.compare_digest(candidate, digest_hex)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_session_token(ttl_hours: int) -> IssuedToken:
    token = secrets.token_urlsafe(32)
    return IssuedToken(
        plain_text=token,
        token_hash=hash_token(token),
        expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=ttl_hours),
    )


def new_id() -> str:
    return str(uuid.uuid4())
