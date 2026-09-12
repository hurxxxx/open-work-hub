"""Explicit company authority state for isolated database behavior tests."""

from sqlalchemy.orm import Session

from open_work_hub_api.domains.auth.app_access_models import (
    AppAccessPolicy,
    AppGroupGrant,
    AppUserGrant,
)
from open_work_hub_api.domains.auth.app_catalog import iter_app_catalog
from open_work_hub_api.domains.auth.models import (
    AuditLog,
    CompanyAppControl,
    User,
    UserSystemRole,
)
from open_work_hub_api.domains.groups.models import Group, GroupMember


def company_authority_tables():
    return [
        model.__table__
        for model in (
            User,
            UserSystemRole,
            AuditLog,
            CompanyAppControl,
            AppAccessPolicy,
            AppUserGrant,
            AppGroupGrant,
            Group,
            GroupMember,
        )
    ]


def seed_company_app_access(db: Session, app_ids=None) -> None:
    """Create normal all-user app policies; callers still own user/resource grants."""
    for app_id in app_ids if app_ids is not None else [app.app_id for app in iter_app_catalog()]:
        master = db.get(CompanyAppControl, app_id)
        if master is None:
            db.add(CompanyAppControl(app_id=app_id, enabled=True))
        else:
            master.enabled = True
        policy = db.get(AppAccessPolicy, app_id)
        if policy is None:
            db.add(AppAccessPolicy(app_id=app_id, audience="all"))
        else:
            policy.audience = "all"
    db.flush()
