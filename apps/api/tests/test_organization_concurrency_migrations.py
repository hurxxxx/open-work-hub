from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Event
from time import monotonic, sleep
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from open_work_hub_api.domains.auth.dependencies import AuthContext
from open_work_hub_api.domains.auth.models import AuthSession, User
from open_work_hub_api.domains.organization import admin_router
from open_work_hub_api.domains.organization.models import OrganizationUnit
from open_work_hub_api.domains.organization.schemas import OrganizationUnitUpdateRequest

pytestmark = pytest.mark.migration


@pytest.mark.parametrize("preload_hierarchy", [False, True])
def test_concurrent_subtree_moves_cannot_create_organization_cycle(
    application_postgres_dsn, monkeypatch, preload_hierarchy
):
    engine = create_engine(
        application_postgres_dsn,
        connect_args={"options": "-c statement_timeout=15000 -c lock_timeout=12000"},
    )
    factory = sessionmaker(engine, expire_on_commit=False)
    first_validated, second_validated, second_started, release = (
        Event(),
        Event(),
        Event(),
        Event(),
    )
    backend_ids: dict[str, int] = {}
    original_validate = admin_router.ensure_valid_parent

    def pause_after_validation(db, *, organization_unit_id, parent_id):
        original_validate(db, organization_unit_id=organization_unit_id, parent_id=parent_id)
        (first_validated if organization_unit_id == "root-a" else second_validated).set()
        assert release.wait(10), "Concurrent move was not released"

    monkeypatch.setattr(admin_router, "ensure_valid_parent", pause_after_validation)

    def move(unit_id: str, parent_id: str):
        with factory() as db:
            backend_ids[unit_id] = db.scalar(text("select pg_backend_pid()"))
            cached_units = list(db.scalars(select(OrganizationUnit))) if preload_hierarchy else []
            if unit_id == "root-b":
                second_started.set()
            actor = db.get(User, "org-race-admin")
            context = AuthContext(
                user=actor,
                session=AuthSession(
                    id=f"session-{unit_id}",
                    user_id=actor.id,
                    token_hash=f"fixture-{unit_id}",
                    expires_at=datetime.now() + timedelta(hours=1),
                ),
                system_roles=frozenset({"platform_admin"}),
            )
            request = Request({"type": "http", "app": SimpleNamespace(state=SimpleNamespace())})
            try:
                admin_router.update_organization_unit(
                    unit_id,
                    OrganizationUnitUpdateRequest(parent_id=parent_id),
                    request,
                    context,
                    db,
                )
                if preload_hierarchy:
                    assert cached_units
                return "updated"
            except HTTPException as error:
                assert error.status_code == 409
                assert error.detail.code == "organization.cycle_detected"
                return "cycle-rejected"

    try:
        with factory.begin() as db:
            db.add(
                User(
                    id="org-race-admin",
                    login_id="org-race-admin",
                    email="org-race@example.test",
                    full_name="Organization race admin",
                    password_hash="fixture",
                )
            )
            for unit_id in ("root-a", "root-b"):
                db.add(OrganizationUnit(id=unit_id, name=unit_id, slug=unit_id))
            db.flush()
            for unit_id, parent_id in (("child-a", "root-a"), ("child-b", "root-b")):
                db.add(
                    OrganizationUnit(id=unit_id, name=unit_id, slug=unit_id, parent_id=parent_id)
                )

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(move, "root-a", "child-b")
            try:
                assert first_validated.wait(5)
                second = pool.submit(move, "root-b", "child-a")
                assert second_started.wait(5)
                deadline = monotonic() + 5
                with engine.connect() as observer:
                    while not second_validated.is_set():
                        blockers = observer.scalar(
                            text("select pg_blocking_pids(:pid)"),
                            {"pid": backend_ids["root-b"]},
                        )
                        if backend_ids["root-a"] in blockers:
                            break
                        assert monotonic() < deadline, (
                            "Second move never reached validation or lock"
                        )
                        sleep(0.01)
            finally:
                release.set()
            assert sorted([first.result(timeout=10), second.result(timeout=10)]) == [
                "cycle-rejected",
                "updated",
            ]
        with factory() as db:
            parents = dict(
                db.execute(select(OrganizationUnit.id, OrganizationUnit.parent_id)).all()
            )
            for unit_id in ("root-a", "root-b", "child-a", "child-b"):
                visited: set[str] = set()
                while unit_id is not None:
                    assert unit_id not in visited
                    visited.add(unit_id)
                    unit_id = parents[unit_id]
    finally:
        release.set()
        engine.dispose()
