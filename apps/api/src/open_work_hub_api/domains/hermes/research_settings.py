from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from open_work_hub_api.domains.auth.models import utcnow_naive
from open_work_hub_api.domains.hermes.models import HermesResearchSourceSettings
from open_work_hub_api.domains.hermes.research_sources import (
    DEFAULT_RESEARCH_SOURCE_POLICY,
    RESEARCH_SOURCE_IDS,
    ResearchSourceId,
)


_SOURCE_COLUMNS: dict[ResearchSourceId, str] = {
    "semantic_scholar": "semantic_scholar_enabled",
    "arxiv": "arxiv_enabled",
    "openalex": "openalex_enabled",
    "crossref": "crossref_enabled",
}


@dataclass(frozen=True)
class HermesResearchSettingsSnapshot:
    policy: dict[ResearchSourceId, bool]
    revision: int
    updated_at: datetime | None
    updated_by: str | None


class HermesResearchSettingsConflictError(RuntimeError):
    pass


def _snapshot(
    row: HermesResearchSourceSettings | None,
) -> HermesResearchSettingsSnapshot:
    if row is None:
        return HermesResearchSettingsSnapshot(
            policy=dict(DEFAULT_RESEARCH_SOURCE_POLICY),
            revision=0,
            updated_at=None,
            updated_by=None,
        )
    return HermesResearchSettingsSnapshot(
        policy={
            source_id: bool(getattr(row, column_name))
            for source_id, column_name in _SOURCE_COLUMNS.items()
        },
        revision=row.revision,
        updated_at=row.updated_at,
        updated_by=row.updated_by,
    )


def get_research_settings(db: Session) -> HermesResearchSettingsSnapshot:
    return _snapshot(db.get(HermesResearchSourceSettings, 1))


def get_research_source_policy(db: Session) -> dict[ResearchSourceId, bool]:
    return get_research_settings(db).policy


def update_research_source(
    db: Session,
    *,
    source_id: ResearchSourceId,
    enabled: bool,
    expected_revision: int,
    actor_user_id: str,
) -> HermesResearchSettingsSnapshot:
    if source_id not in RESEARCH_SOURCE_IDS:
        raise ValueError("Unknown research source.")
    row = db.scalar(
        select(HermesResearchSourceSettings)
        .where(HermesResearchSourceSettings.id == 1)
        .with_for_update()
    )
    current_revision = row.revision if row is not None else 0
    if expected_revision != current_revision:
        raise HermesResearchSettingsConflictError(
            "The Hermes research settings changed in another request."
        )
    now = utcnow_naive()
    if row is None:
        row = HermesResearchSourceSettings(
            id=1,
            semantic_scholar_enabled=DEFAULT_RESEARCH_SOURCE_POLICY[
                "semantic_scholar"
            ],
            arxiv_enabled=DEFAULT_RESEARCH_SOURCE_POLICY["arxiv"],
            openalex_enabled=DEFAULT_RESEARCH_SOURCE_POLICY["openalex"],
            crossref_enabled=DEFAULT_RESEARCH_SOURCE_POLICY["crossref"],
            revision=1,
            updated_by=actor_user_id,
            created_at=now,
            updated_at=now,
        )
    else:
        row.revision += 1
        row.updated_by = actor_user_id
        row.updated_at = now
    setattr(row, _SOURCE_COLUMNS[source_id], enabled)
    db.add(row)
    db.flush()
    return _snapshot(row)
