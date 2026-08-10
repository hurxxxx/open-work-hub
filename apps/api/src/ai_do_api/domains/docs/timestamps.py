from __future__ import annotations

from datetime import datetime, timedelta

from ai_do_api.domains.docs.models import NativeDoc, utcnow_naive


def touch_native_doc(doc: NativeDoc, *, timestamp: datetime | None = None) -> None:
    next_updated_at = timestamp or utcnow_naive()
    if doc.updated_at is not None and next_updated_at <= doc.updated_at:
        next_updated_at = doc.updated_at + timedelta(microseconds=1)
    doc.updated_at = next_updated_at
