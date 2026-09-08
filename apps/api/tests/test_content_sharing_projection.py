from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from company_admission_fixture import company_authority_tables, seed_company_app_access
from open_work_hub_api.core import settings
from open_work_hub_api.core.db import Base
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.docs.models import (
    NativeDoc,
    NativeDocGroupShare,
    NativeDocLinkShare,
    NativeDocUserShare,
)
from open_work_hub_api.domains.groups.models import Group
from open_work_hub_api.domains.whiteboard.models import (
    Whiteboard,
    WhiteboardGroupShare,
    WhiteboardLinkShare,
    WhiteboardUserShare,
)


@pytest.fixture
def content_projection_db(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "ENV_FILE", Path("/dev/null"))
    monkeypatch.setitem(settings.Settings.model_config, "env_file", None)
    monkeypatch.setenv("OPEN_WORK_HUB_POSTGRES_DSN", "sqlite://")
    settings.get_settings.cache_clear()
    from open_work_hub_api.domains.docs import service as docs_service
    from open_work_hub_api.domains.whiteboard import hub as whiteboard_hub

    engine = create_engine("sqlite://")
    try:
        Base.metadata.create_all(
            engine,
            tables=[
                *company_authority_tables(),
                *(
                    table
                    for table in Base.metadata.tables.values()
                    if table.name.startswith(("docs_", "whiteboard"))
                ),
            ],
        )
        with Session(engine) as db:
            seed_company_app_access(db, app_ids=["docs", "whiteboard"])
            yield db, docs_service, whiteboard_hub
    finally:
        engine.dispose()
        settings.get_settings.cache_clear()


@pytest.mark.parametrize("app_id", ["docs", "whiteboard"])
@pytest.mark.parametrize(
    "sharing",
    [
        "private",
        "user",
        "group",
        "inactive_group",
        "active_link",
        "inactive_link",
        "company_visible",
        "company_restricted",
    ],
)
def test_hub_marks_only_unshared_personal_content_private(
    content_projection_db, app_id: str, sharing: str
) -> None:
    db, docs_service, whiteboard_hub = content_projection_db
    owner = User(
        id="owner",
        login_id="owner",
        email="owner@example.test",
        full_name="Owner",
        password_hash="fixture",
    )
    recipient = User(
        id="recipient",
        login_id="recipient",
        email="recipient@example.test",
        full_name="Recipient",
        password_hash="fixture",
    )
    model = NativeDoc if app_id == "docs" else Whiteboard
    source = model(
        id="item",
        owner_id=owner.id,
        title="Sharing state",
        ownership_kind="company" if sharing.startswith("company_") else "personal",
        company_visible=sharing == "company_visible",
    )
    db.add_all([owner, recipient, source])
    db.flush()
    source_id = {"doc_id" if app_id == "docs" else "whiteboard_id": source.id}
    share = None
    if sharing in {"group", "inactive_group"}:
        group = Group(id="group", kind="manual", name="Project group", active=sharing == "group")
        db.add(group)
        share_model = NativeDocGroupShare if app_id == "docs" else WhiteboardGroupShare
        share = share_model(
            **source_id, group_id=group.id, access_level="read", created_by_id=owner.id
        )
        db.add(share)
    elif sharing == "user":
        share_model = NativeDocUserShare if app_id == "docs" else WhiteboardUserShare
        db.add(
            share_model(
                **source_id,
                id="user-share",
                user_id=recipient.id,
                access_level="read",
                created_by_id=owner.id,
            )
        )
    elif sharing in {"active_link", "inactive_link"}:
        share_model = NativeDocLinkShare if app_id == "docs" else WhiteboardLinkShare
        db.add(
            share_model(
                **source_id,
                id="link-share",
                token="fixture-link",
                active=sharing == "active_link",
                access_level="edit",
                created_by_id=owner.id,
            )
        )
    db.commit()
    db.expire_all()

    def hub_item():
        if app_id == "docs":
            return docs_service.list_hub(db, user=owner)["items"][0]
        return (
            whiteboard_hub.build_whiteboard_hub_response(
                db, current_user=owner, query=whiteboard_hub.WhiteboardHubQuery()
            )
            .items[0]
            .model_dump()
        )

    item = hub_item()
    assert item["is_private"] is (sharing in {"private", "inactive_link"})
    assert item["ownership_kind"] == source.ownership_kind
    assert item["company_visible"] is (sharing == "company_visible")
    if app_id == "docs":
        summary = item["sharing_summary"]
        assert summary["user_share_count"] == (1 if sharing == "user" else 0)
        assert summary["link_active"] is (sharing == "active_link")
        assert summary["link_access_level"] == ("edit" if sharing == "active_link" else None)
    if share is not None:
        db.delete(share)
        db.commit()
        db.expire_all()
        assert hub_item()["is_private"] is True
