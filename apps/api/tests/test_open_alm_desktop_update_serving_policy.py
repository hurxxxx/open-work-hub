from open_alm_api.open_alm_desktop_update_serving_policy import open_alm_desktop_update_serving_policy


def test_open_alm_desktop_update_serving_policy_uses_manifest_contract() -> None:
    policy = open_alm_desktop_update_serving_policy()

    assert policy.platforms == ("win", "mac", "linux")
    assert policy.feed_path_prefix == "/api/v1/open-alm-desktop/updates"
    assert policy.is_allowed_file_path("mac", "latest-mac.yml")
    assert not policy.is_allowed_file_path("mac", "latest.yml")
    assert policy.is_allowed_file_path("linux", "Open ALM-Desktop-latest.deb.blockmap")
    assert not policy.is_allowed_file_path("linux", "Open ALM-Desktop-latest.exe")


def test_open_alm_desktop_update_serving_policy_attachment_headers() -> None:
    policy = open_alm_desktop_update_serving_policy()

    headers = policy.attachment_headers("linux", "Open ALM-Desktop-latest.deb")

    assert headers is not None
    assert headers.content_type == "application/vnd.debian.binary-package"
    assert headers.content_disposition.startswith("attachment;")
    assert "Open ALM-Desktop-latest.deb" in headers.content_disposition
    assert policy.attachment_headers("linux", "Open ALM-Desktop-latest.deb.blockmap") is None
    assert policy.attachment_headers("linux", "nested/Open ALM-Desktop-latest.deb") is None


def test_open_alm_desktop_update_serving_policy_rejects_unsafe_public_paths() -> None:
    policy = open_alm_desktop_update_serving_policy()

    assert not policy.is_allowed_file_path("win", "")
    assert not policy.is_allowed_file_path("win", ".hidden.exe")
    assert not policy.is_allowed_file_path("win", "nested/Open ALM-Desktop-Setup-latest.exe")
    assert not policy.is_allowed_file_path("win", "Open ALM-Desktop-Setup-latest.exe\n")
    assert not policy.is_allowed_file_path("unknown", "Open ALM-Desktop-Setup-latest.exe")
