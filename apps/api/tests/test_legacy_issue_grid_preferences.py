from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from fastapi.testclient import TestClient

from ai_do_api.domains.legacy_issues import router as legacy_issue_router
from dev_accounts import create_workspace_user_session


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _session(
    client: TestClient,
    *,
    workspace_key: str,
    login_id: str,
    email: str,
) -> dict:
    return create_workspace_user_session(
        client,
        workspace_key=workspace_key,
        login_id=login_id,
        email=email,
        full_name=login_id.replace("-", " ").title(),
        role="member",
    )


def _preference_payload(preference: dict) -> dict:
    return {
        "grid_kind": preference["grid_kind"],
        "grid_key": preference["grid_key"],
        "column_order": preference["column_order"],
        "hidden_column_keys": preference["hidden_column_keys"],
        "frozen_column_count": preference["frozen_column_count"],
    }


def test_grid_preferences_persist_per_workspace_user_kind_and_key(
    client: TestClient,
) -> None:
    first = _session(
        client,
        workspace_key="legacy-grid-pref-a",
        login_id="legacy-grid-pref-user-a",
        email="legacy-grid-pref-user-a@ai-do.local",
    )
    headers = _headers(first["token"])
    dataset_path = (
        "/api/v1/workspaces/legacy-grid-pref-a/legacy-issues/grid-preferences/dataset/aircon"
    )
    checklist_path = (
        "/api/v1/workspaces/legacy-grid-pref-a/legacy-issues/"
        "grid-preferences/vehicle-module-checklist/aircon"
    )

    default_response = client.get(dataset_path, headers=headers)
    assert default_response.status_code == 200, default_response.text
    assert default_response.json() == {"preference": None, "revision": 0}

    update_response = client.put(
        dataset_path,
        headers=headers,
        json={
            "expected_revision": 0,
            "column_order": [
                " symptom ",
                "cause",
                "symptom",
                "",
                "future_revision_field",
            ],
            "hidden_column_keys": [
                " cause ",
                "cause",
                "future_revision_hidden_field",
                " ",
            ],
            "frozen_column_count": 3,
        },
    )
    assert update_response.status_code == 200, update_response.text
    updated = update_response.json()
    assert _preference_payload(updated) == {
        "grid_kind": "dataset",
        "grid_key": "aircon",
        "column_order": ["symptom", "cause", "future_revision_field"],
        "hidden_column_keys": ["cause", "future_revision_hidden_field"],
        "frozen_column_count": 3,
    }
    assert updated["created_at"]
    assert updated["updated_at"]
    assert updated["revision"] == 1
    assert client.get(dataset_path, headers=headers).json() == {
        "preference": updated,
        "revision": 1,
    }

    replacement_response = client.put(
        dataset_path,
        headers=headers,
        json={
            "expected_revision": 1,
            "column_order": ["status", "symptom"],
            "hidden_column_keys": [],
            "frozen_column_count": 1,
        },
    )
    assert replacement_response.status_code == 200, replacement_response.text
    replacement = replacement_response.json()
    assert _preference_payload(replacement) == {
        "grid_kind": "dataset",
        "grid_key": "aircon",
        "column_order": ["status", "symptom"],
        "hidden_column_keys": [],
        "frozen_column_count": 1,
    }
    assert replacement["created_at"] == updated["created_at"]
    assert replacement["revision"] == 2
    assert client.get(dataset_path, headers=headers).json() == {
        "preference": replacement,
        "revision": 2,
    }

    second_user = _session(
        client,
        workspace_key="legacy-grid-pref-a",
        login_id="legacy-grid-pref-user-b",
        email="legacy-grid-pref-user-b@ai-do.local",
    )
    assert client.get(
        dataset_path,
        headers=_headers(second_user["token"]),
    ).json() == {"preference": None, "revision": 0}

    other_view_path = (
        "/api/v1/workspaces/legacy-grid-pref-a/legacy-issues/grid-preferences/dataset/interior"
    )
    assert client.get(other_view_path, headers=headers).json() == {
        "preference": None,
        "revision": 0,
    }

    same_user_other_workspace = _session(
        client,
        workspace_key="legacy-grid-pref-b",
        login_id="legacy-grid-pref-user-a",
        email="legacy-grid-pref-user-a@ai-do.local",
    )
    other_workspace_path = (
        "/api/v1/workspaces/legacy-grid-pref-b/legacy-issues/grid-preferences/dataset/aircon"
    )
    assert client.get(
        other_workspace_path,
        headers=_headers(same_user_other_workspace["token"]),
    ).json() == {"preference": None, "revision": 0}

    checklist_update = client.put(
        checklist_path,
        headers=headers,
        json={
            "expected_revision": 0,
            "column_order": ["check_plan", "revision_only_field"],
            "hidden_column_keys": [],
            "frozen_column_count": 1,
        },
    )
    assert checklist_update.status_code == 200, checklist_update.text
    assert _preference_payload(checklist_update.json()) == {
        "grid_kind": "vehicle-module-checklist",
        "grid_key": "aircon",
        "column_order": ["check_plan", "revision_only_field"],
        "hidden_column_keys": [],
        "frozen_column_count": 1,
    }

    delete_response = client.delete(
        f"{dataset_path}?expected_revision=2",
        headers=headers,
    )
    assert delete_response.status_code == 204, delete_response.text
    assert delete_response.content == b""
    assert client.get(dataset_path, headers=headers).json() == {
        "preference": None,
        "revision": 3,
    }
    assert (
        client.get(checklist_path, headers=headers).json()["preference"] == checklist_update.json()
    )
    assert client.delete(
        f"{dataset_path}?expected_revision=3",
        headers=headers,
    ).status_code == 204
    assert client.get(dataset_path, headers=headers).json()["revision"] == 4


def test_grid_preferences_validate_scope_payload_and_workspace_access(
    client: TestClient,
) -> None:
    session = _session(
        client,
        workspace_key="legacy-grid-pref-guards",
        login_id="legacy-grid-pref-guard-user",
        email="legacy-grid-pref-guard-user@ai-do.local",
    )
    headers = _headers(session["token"])
    base_path = "/api/v1/workspaces/legacy-grid-pref-guards/legacy-issues/grid-preferences"
    dataset_path = f"{base_path}/dataset/aircon"
    valid_payload = {
        "expected_revision": 0,
        "column_order": ["symptom"],
        "hidden_column_keys": [],
        "frozen_column_count": 0,
    }

    member_update = client.put(dataset_path, headers=headers, json=valid_payload)
    assert member_update.status_code == 200, member_update.text

    maximum_column_order = [f"future-field-{index}" for index in range(200)]
    maximum_boundary = client.put(
        dataset_path,
        headers=headers,
        json={
            "expected_revision": 1,
            "column_order": maximum_column_order,
            "hidden_column_keys": ["future-hidden-field"],
            "frozen_column_count": 200,
        },
    )
    assert maximum_boundary.status_code == 200, maximum_boundary.text
    assert maximum_boundary.json()["column_order"] == maximum_column_order
    assert maximum_boundary.json()["hidden_column_keys"] == ["future-hidden-field"]
    assert maximum_boundary.json()["frozen_column_count"] == 200

    anonymous_response = client.get(dataset_path)
    assert anonymous_response.status_code == 401

    cross_workspace_response = client.get(
        "/api/v1/workspaces/administrator/legacy-issues/grid-preferences/dataset/aircon",
        headers=headers,
    )
    assert cross_workspace_response.status_code == 403
    assert cross_workspace_response.json()["code"] == "workspace.membership_required"

    invalid_kind = client.get(
        f"{base_path}/report/aircon",
        headers=headers,
    )
    assert invalid_kind.status_code == 422, invalid_kind.text

    unknown_dataset_view = client.get(
        f"{base_path}/dataset/unknown-module",
        headers=headers,
    )
    assert unknown_dataset_view.status_code == 404, unknown_dataset_view.text

    invalid_checklist_scope = client.get(
        f"{base_path}/vehicle-module-checklist/common-master",
        headers=headers,
    )
    assert invalid_checklist_scope.status_code == 404, invalid_checklist_scope.text

    too_many_keys = client.put(
        dataset_path,
        headers=headers,
        json={
            **valid_payload,
            "column_order": [f"field-{index}" for index in range(201)],
        },
    )
    assert too_many_keys.status_code == 422, too_many_keys.text

    too_long_column_key = client.put(
        dataset_path,
        headers=headers,
        json={
            **valid_payload,
            "column_order": ["x" * 161],
        },
    )
    assert too_long_column_key.status_code == 422, too_long_column_key.text

    too_long_scope_key = client.get(
        f"{base_path}/dataset/{'x' * 161}",
        headers=headers,
    )
    assert too_long_scope_key.status_code == 422, too_long_scope_key.text

    for frozen_column_count in (-1, 201):
        invalid_frozen = client.put(
            dataset_path,
            headers=headers,
            json={
                **valid_payload,
                "frozen_column_count": frozen_column_count,
            },
        )
        assert invalid_frozen.status_code == 422, invalid_frozen.text

    for frozen_column_count in (True, "2"):
        coerced_frozen = client.put(
            dataset_path,
            headers=headers,
            json={
                **valid_payload,
                "expected_revision": 2,
                "frozen_column_count": frozen_column_count,
            },
        )
        assert coerced_frozen.status_code == 422, coerced_frozen.text

    for expected_revision in (-1, True, "2"):
        invalid_revision = client.put(
            dataset_path,
            headers=headers,
            json={
                **valid_payload,
                "expected_revision": expected_revision,
            },
        )
        assert invalid_revision.status_code == 422, invalid_revision.text

    missing_full_snapshot_field = client.put(
        dataset_path,
        headers=headers,
        json={
            "column_order": ["symptom"],
            "frozen_column_count": 0,
        },
    )
    assert missing_full_snapshot_field.status_code == 422

    missing_revision = client.put(
        dataset_path,
        headers=headers,
        json={
            "column_order": ["symptom"],
            "hidden_column_keys": [],
            "frozen_column_count": 0,
        },
    )
    assert missing_revision.status_code == 422
    assert client.delete(
        f"{dataset_path}?expected_revision=not-an-integer",
        headers=headers,
    ).status_code == 422


def test_grid_preference_put_delete_race_allows_exactly_one_revision_winner(
    client: TestClient,
    monkeypatch,
) -> None:
    session = _session(
        client,
        workspace_key="legacy-grid-pref-race",
        login_id="legacy-grid-pref-race-user",
        email="legacy-grid-pref-race-user@ai-do.local",
    )
    headers = _headers(session["token"])
    dataset_path = (
        "/api/v1/workspaces/legacy-grid-pref-race/legacy-issues/grid-preferences/dataset/aircon"
    )
    initial_response = client.put(
        dataset_path,
        headers=headers,
        json={
            "expected_revision": 0,
            "column_order": ["initial-order"],
            "hidden_column_keys": ["initial-hidden"],
            "frozen_column_count": 1,
        },
    )
    assert initial_response.status_code == 200, initial_response.text

    original_upsert = legacy_issue_router.upsert_grid_preference
    original_delete = legacy_issue_router.delete_grid_preference
    requests_ready = Barrier(2)

    def synchronized_upsert(*args, **kwargs):
        requests_ready.wait(timeout=2)
        return original_upsert(*args, **kwargs)

    def synchronized_delete(*args, **kwargs):
        requests_ready.wait(timeout=2)
        return original_delete(*args, **kwargs)

    monkeypatch.setattr(
        legacy_issue_router,
        "upsert_grid_preference",
        synchronized_upsert,
    )
    monkeypatch.setattr(
        legacy_issue_router,
        "delete_grid_preference",
        synchronized_delete,
    )
    replacement_payload = {
        "expected_revision": 1,
        "column_order": ["replacement-order", "future-revision-field"],
        "hidden_column_keys": ["replacement-hidden"],
        "frozen_column_count": 2,
    }

    with ThreadPoolExecutor(max_workers=2) as executor:
        put_future = executor.submit(
            client.put,
            dataset_path,
            headers=headers,
            json=replacement_payload,
        )
        delete_future = executor.submit(
            client.delete,
            f"{dataset_path}?expected_revision=1",
            headers=headers,
        )
        put_response = put_future.result()
        delete_response = delete_future.result()

    assert [put_response.status_code, delete_response.status_code].count(409) == 1
    assert put_response.status_code in (200, 409)
    assert delete_response.status_code in (204, 409)

    final_response = client.get(dataset_path, headers=headers)
    assert final_response.status_code == 200, final_response.text
    final_payload = final_response.json()
    assert final_payload["revision"] == 2
    final_preference = final_payload["preference"]
    if put_response.status_code == 200:
        assert delete_response.json()["code"] == (
            "legacy_issues.grid_preference_revision_conflict"
        )
        assert final_preference is not None
        assert {
            "column_order": final_preference["column_order"],
            "hidden_column_keys": final_preference["hidden_column_keys"],
            "frozen_column_count": final_preference["frozen_column_count"],
        } == {
            "column_order": replacement_payload["column_order"],
            "hidden_column_keys": replacement_payload["hidden_column_keys"],
            "frozen_column_count": replacement_payload["frozen_column_count"],
        }
    else:
        assert put_response.json()["code"] == (
            "legacy_issues.grid_preference_revision_conflict"
        )
        assert delete_response.status_code == 204
        assert final_preference is None


def test_grid_preference_reset_tombstone_rejects_late_stale_save(
    client: TestClient,
) -> None:
    session = _session(
        client,
        workspace_key="legacy-grid-pref-stale-save",
        login_id="legacy-grid-pref-stale-save-user",
        email="legacy-grid-pref-stale-save-user@ai-do.local",
    )
    headers = _headers(session["token"])
    dataset_path = (
        "/api/v1/workspaces/legacy-grid-pref-stale-save/legacy-issues/"
        "grid-preferences/dataset/aircon"
    )

    assert client.get(dataset_path, headers=headers).json() == {
        "preference": None,
        "revision": 0,
    }

    reset_response = client.delete(
        f"{dataset_path}?expected_revision=0",
        headers=headers,
    )
    assert reset_response.status_code == 204, reset_response.text

    stale_save_response = client.put(
        dataset_path,
        headers=headers,
        json={
            "expected_revision": 0,
            "column_order": ["stale-order"],
            "hidden_column_keys": ["stale-hidden"],
            "frozen_column_count": 1,
        },
    )
    assert stale_save_response.status_code == 409, stale_save_response.text
    assert stale_save_response.json()["code"] == (
        "legacy_issues.grid_preference_revision_conflict"
    )
    assert client.get(dataset_path, headers=headers).json() == {
        "preference": None,
        "revision": 1,
    }
