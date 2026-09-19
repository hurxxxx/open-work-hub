import hashlib
import secrets
from datetime import timedelta

from sqlalchemy import delete, select

from .models import Owner, WebSession, now

COOKIE = "codex_console_session"
CSRF_COOKIE = "codex_console_csrf"


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    key = hashlib.scrypt(
        password.encode(), salt=bytes.fromhex(salt), n=32768, r=8, p=1, maxmem=67108864
    ).hex()
    return f"scrypt${salt}${key}"


def verify(password: str, encoded: str) -> bool:
    try:
        algorithm, salt, _ = encoded.split("$")
        return algorithm == "scrypt" and secrets.compare_digest(
            password_hash(password, salt), encoded
        )
    except (ValueError, TypeError):
        return False


def login(factory, password: str, hours: int) -> tuple[str, str] | None:
    with factory.begin() as db:
        owner = db.scalar(select(Owner).where(Owner.id == 1).with_for_update())
        if owner is None:
            # Constant-cost failure also when initial owner setup has not been run.
            password_hash(password)
            return None
        if owner.locked_until and owner.locked_until > now():
            return None
        if not verify(password, owner.password_hash):
            owner.failed_logins += 1
            if owner.failed_logins >= 5:
                owner.locked_until = now() + timedelta(minutes=5)
            return None
        owner.failed_logins = 0
        owner.locked_until = None
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        db.execute(delete(WebSession).where(WebSession.expires_at <= now()))
        db.add(
            WebSession(
                token_hash=digest(token),
                csrf_hash=digest(csrf),
                expires_at=now() + timedelta(hours=hours),
            )
        )
        return token, csrf


def authenticate(factory, token: str | None, csrf: str | None = None) -> bool:
    if not token or len(token) > 128:
        return False
    with factory() as db:
        session = db.get(WebSession, digest(token))
        return bool(
            session
            and session.expires_at > now()
            and (csrf is None or secrets.compare_digest(session.csrf_hash, digest(csrf)))
        )
