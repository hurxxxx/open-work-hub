from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ai_do_api.domains.hr.history import canonical_payload_hash, utcnow_naive
from ai_do_api.domains.hr.models import (
    HrIdentityResolutionState,
    HrManualIdentityLink,
    HrWorkforceCategoryAssignment,
)


EXTERNAL_GROUPWARE_EMPLOYEE_CODES = frozenset({"Z0000", "Z00000"})
IDENTITY_RESOLUTION_STATE_ID = 1


@dataclass(frozen=True)
class ManualIdentityLinkSnapshot:
    id: str
    groupware_source_identity: str
    groupware_employee_code: str
    erp_employee_code: str
    matched_name: str

    def checksum_payload(self) -> dict[str, str]:
        return {
            "id": self.id,
            "groupware_source_identity": self.groupware_source_identity,
            "groupware_employee_code": self.groupware_employee_code,
            "erp_employee_code": self.erp_employee_code,
            "matched_name": self.matched_name,
        }


@dataclass(frozen=True)
class WorkforceCategoryAssignmentSnapshot:
    id: str
    subject_kind: str
    subject_key: str
    category_code: str

    def checksum_payload(self) -> dict[str, str]:
        return {
            "id": self.id,
            "subject_kind": self.subject_kind,
            "subject_key": self.subject_key,
            "category_code": self.category_code,
        }


@dataclass(frozen=True)
class IdentityResolutionSnapshot:
    revision: int
    snapshot_hash: str
    links: tuple[ManualIdentityLinkSnapshot, ...]
    workforce_assignments: tuple[WorkforceCategoryAssignmentSnapshot, ...]


def load_identity_resolution_state(
    db: Session,
    *,
    for_update: bool = False,
    now: datetime | None = None,
) -> HrIdentityResolutionState:
    statement = select(HrIdentityResolutionState).where(
        HrIdentityResolutionState.id == IDENTITY_RESOLUTION_STATE_ID
    )
    if for_update:
        statement = statement.with_for_update()
    state = db.scalar(statement)
    if state is not None:
        return state
    state = HrIdentityResolutionState(
        id=IDENTITY_RESOLUTION_STATE_ID,
        revision=0,
        updated_at=now or utcnow_naive(),
    )
    db.add(state)
    db.flush()
    return state


def load_identity_resolution_snapshot(db: Session) -> IdentityResolutionSnapshot:
    state = load_identity_resolution_state(db)
    link_rows = db.scalars(
        select(HrManualIdentityLink)
        .where(
            HrManualIdentityLink.activated_revision <= state.revision,
            or_(
                HrManualIdentityLink.revoked_revision.is_(None),
                HrManualIdentityLink.revoked_revision > state.revision,
            ),
        )
        .order_by(
            HrManualIdentityLink.groupware_source_identity,
            HrManualIdentityLink.erp_employee_code,
            HrManualIdentityLink.id,
        )
    ).all()
    links = tuple(
        ManualIdentityLinkSnapshot(
            id=row.id,
            groupware_source_identity=row.groupware_source_identity,
            groupware_employee_code=row.groupware_employee_code,
            erp_employee_code=row.erp_employee_code,
            matched_name=row.matched_name,
        )
        for row in link_rows
    )
    assignment_rows = db.scalars(
        select(HrWorkforceCategoryAssignment)
        .where(
            HrWorkforceCategoryAssignment.activated_revision <= state.revision,
            or_(
                HrWorkforceCategoryAssignment.revoked_revision.is_(None),
                HrWorkforceCategoryAssignment.revoked_revision > state.revision,
            ),
        )
        .order_by(
            HrWorkforceCategoryAssignment.subject_kind,
            HrWorkforceCategoryAssignment.subject_key,
            HrWorkforceCategoryAssignment.id,
        )
    ).all()
    workforce_assignments = tuple(
        WorkforceCategoryAssignmentSnapshot(
            id=row.id,
            subject_kind=row.subject_kind,
            subject_key=row.subject_key,
            category_code=row.category_code,
        )
        for row in assignment_rows
    )
    return IdentityResolutionSnapshot(
        revision=state.revision,
        snapshot_hash=canonical_payload_hash(
            {
                "links": [link.checksum_payload() for link in links],
                "workforce_assignments": [
                    assignment.checksum_payload()
                    for assignment in workforce_assignments
                ],
            }
        ),
        links=links,
        workforce_assignments=workforce_assignments,
    )


def advance_identity_resolution_revision(
    db: Session,
    *,
    now: datetime | None = None,
) -> int:
    changed_at = now or utcnow_naive()
    state = load_identity_resolution_state(db, for_update=True, now=changed_at)
    state.revision += 1
    state.updated_at = changed_at
    db.flush()
    return state.revision


__all__ = [
    "EXTERNAL_GROUPWARE_EMPLOYEE_CODES",
    "IdentityResolutionSnapshot",
    "ManualIdentityLinkSnapshot",
    "WorkforceCategoryAssignmentSnapshot",
    "advance_identity_resolution_revision",
    "load_identity_resolution_snapshot",
    "load_identity_resolution_state",
]
