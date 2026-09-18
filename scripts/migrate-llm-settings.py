"""Backfill DB-owned LLM connections, then retire the matching private env keys.

Run after `alembic upgrade head` and before starting the new API/worker. Dry run
is the default. Database values win; an existing encryption master key is never
changed. Output contains only key names and counts.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api/src"))

from dotenv import dotenv_values
from sqlalchemy import func, select
from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.core.model_registry import import_all_models
from open_work_hub_api.domains.ai.model_credentials import (
    decrypt_api_key,
    encrypt_api_key,
)
from open_work_hub_api.domains.ai.model_settings_models import (
    AiModelPolicyDefault,
    AiModelProviderConfig,
)
from open_work_hub_api.domains.hermes_terminal.models import (
    HermesTerminalSession,
    HERMES_TERMINAL_ACTIVE_STATUSES,
)

RETIRED = frozenset(
    {
        "OPEN_WORK_HUB_LLM_LOCAL_API_KEY",
        "OPEN_WORK_HUB_LLM_LOCAL_BASE_URL",
        "OPEN_WORK_HUB_LLM_LOCAL_PROVIDER",
        "OPEN_WORK_HUB_AI_DEFAULT_EXTERNAL_LLM_PROVIDER",
    }
)


def prune_keys(original: str, keys: set[str]) -> str:
    """Refuse multiline/interpolated changes rather than damaging another secret."""
    from io import StringIO

    values = dotenv_values(stream=StringIO(original), interpolate=False)
    names = re.findall(
        r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z_0-9]*)\s*=", original, re.M
    )
    if len(names) != len(set(names)):
        raise ValueError("duplicate env keys")
    kept = []
    for line in original.splitlines(keepends=True):
        match = re.match(r"\s*(?:export\s+)?([A-Za-z_][A-Za-z_0-9]*)\s*=", line)
        if match and match[1] in keys:
            if re.search(r"\$\{" + re.escape(match[1]) + r"(?::|\})", original):
                raise ValueError("referenced retired key")
        else:
            kept.append(line)
    updated = "".join(kept)
    if dotenv_values(stream=StringIO(updated), interpolate=False) != {
        k: v for k, v in values.items() if k not in keys
    }:
        raise ValueError("multiline env entry")
    return updated


def backfill(db, values: dict[str, str | None]) -> set[str]:
    """Idempotent: never overwrite existing DB endpoints or ciphertext."""
    from open_work_hub_api.core.llm_provider_registry import llm_provider_descriptor

    keys = set(RETIRED.intersection(values))
    if any("${" in (values.get(key) or "") for key in (*keys, "OPENROUTER_API_KEY")):
        raise ValueError("resolve referenced LLM settings before cutover")
    endpoint = values.get("OPEN_WORK_HUB_LLM_LOCAL_BASE_URL") or ""
    local_key = values.get("OPEN_WORK_HUB_LLM_LOCAL_API_KEY") or ""
    local = db.get(AiModelProviderConfig, "local")
    if endpoint or local_key:
        if local is None:
            local = AiModelProviderConfig(
                provider_id="local",
                provider_kind="local",
                route_mode="local",
                display_name="Local",
                credential_kind="none",
                enabled=False,
                version=1,
            )
            db.add(local)
        if not local.endpoint_url:
            local.endpoint_url = endpoint
        if local_key and not local.api_key_ciphertext:
            local.api_key_ciphertext = encrypt_api_key(local_key)
            local.credential_kind = "api_key"
        if local.api_key_ciphertext:
            decrypt_api_key(local.api_key_ciphertext)
    db.flush()
    for route in ("local", "external"):
        row = db.get(AiModelPolicyDefault, ("", route))
        if row is None:
            row = AiModelPolicyDefault(
                app_id="",
                route_mode=route,
                version=1,
                max_output_tokens=None,
            )
            db.add(row)
        legacy_id = (
            "local"
            if route == "local"
            else values.get("OPEN_WORK_HUB_AI_DEFAULT_EXTERNAL_LLM_PROVIDER")
        )
        provider = db.get(AiModelProviderConfig, legacy_id) if legacy_id else None
        if not row.provider_id and provider is not None and provider.enabled:
            row.provider_id = provider.provider_id
    # Older builtin connections relied on the static official endpoint.
    for row in db.scalars(select(AiModelProviderConfig)).all():
        descriptor = llm_provider_descriptor(row.provider_kind)
        if not row.endpoint_url and descriptor and descriptor.default_endpoint_url:
            row.endpoint_url = descriptor.default_endpoint_url
        if row.api_key_ciphertext:
            decrypt_api_key(row.api_key_ciphertext)
    if "OPENROUTER_API_KEY" in values:
        active = db.scalar(
            select(func.count())
            .select_from(HermesTerminalSession)
            .where(HermesTerminalSession.status.in_(HERMES_TERMINAL_ACTIVE_STATUSES))
        )
        if active:
            raise ValueError(
                "legacy Terminal sessions must drain before env key removal"
            )
        # Preserve a legacy credential only if the builtin DB connection has none.
        key = values.get("OPENROUTER_API_KEY") or ""
        if key:
            row = db.get(AiModelProviderConfig, "openrouter")
            if row is None:
                row = AiModelProviderConfig(
                    provider_id="openrouter",
                    provider_kind="openrouter",
                    route_mode="external",
                    display_name="OpenRouter",
                    credential_kind="api_key",
                    endpoint_url="https://openrouter.ai/api/v1",
                    enabled=False,
                    version=1,
                )
                db.add(row)
            if not row.api_key_ciphertext:
                row.api_key_ciphertext = encrypt_api_key(key)
            decrypt_api_key(row.api_key_ciphertext)
        keys.add("OPENROUTER_API_KEY")
    if local is not None and local.endpoint_url:
        from open_work_hub_api.domains.ai.model_settings_service import (
            _validate_endpoint_url,
        )

        _validate_endpoint_url(
            local.endpoint_url, provider_id="local", route_mode="local"
        )
    db.flush()
    return keys


def migrate(*, apply: bool) -> set[str]:
    target = ROOT / ".env"
    if (
        not stat.S_ISREG(target.lstat().st_mode)
        or stat.S_IMODE(target.stat().st_mode) != 0o600
    ):
        raise ValueError("env must be a regular file with mode 0600")
    if subprocess.run(
        ["git", "-C", str(ROOT), "check-ignore", "--quiet", ".env"], check=False
    ).returncode:
        raise ValueError("env must be Git ignored")
    original = target.read_text()
    values = dict(dotenv_values(target, interpolate=False))
    import_all_models()
    with get_session_factory()() as db:
        keys = backfill(db, values)
        updated = prune_keys(original, keys)
        if not apply:
            db.rollback()
            return keys
        if target.read_text() != original:
            raise ValueError("env changed during migration")
        db.commit()
    if keys:
        backup_fd, _backup = tempfile.mkstemp(prefix=".env.backup-llm-", dir=ROOT)
        with os.fdopen(backup_fd, "w") as stream:
            stream.write(original)
        fd, temporary = tempfile.mkstemp(prefix=".env.llm-", dir=ROOT)
        try:
            with os.fdopen(fd, "w") as stream:
                stream.write(updated)
                stream.flush()
                os.fsync(stream.fileno())
            if target.read_text() != original:
                raise ValueError("env changed after DB commit; rerun safely")
            os.replace(temporary, target)
        finally:
            Path(temporary).unlink(missing_ok=True)
    return keys


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        keys = migrate(apply=args.apply)
    except Exception:
        # Driver/credential exceptions may contain secrets: never print them.
        print(
            "LLM cutover failed. Check migration head, DB access, master key, env mode, and legacy Terminal sessions.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
    print(
        f"{'Removed' if args.apply else 'Would remove'} {len(keys)} env keys; master key preserved."
    )
    for name in sorted(keys):
        print(name)
