from ai_do_api.ai_do_desktop_update_serving_policy import ai_do_desktop_update_serving_policy


def test_ai_do_desktop_update_serving_policy_uses_manifest_contract() -> None:
    policy = ai_do_desktop_update_serving_policy()

    assert policy.platforms == ("win", "mac", "linux")
    assert policy.feed_path_prefix == "/api/v1/ai-do-desktop/updates"
    assert policy.is_allowed_file_path("mac", "latest-mac.yml")
    assert not policy.is_allowed_file_path("mac", "latest.yml")
    assert policy.is_allowed_file_path("linux", "AI-DO-Desktop-latest.deb.blockmap")
    assert not policy.is_allowed_file_path("linux", "AI-DO-Desktop-latest.exe")


def test_ai_do_desktop_update_serving_policy_attachment_headers() -> None:
    policy = ai_do_desktop_update_serving_policy()

    headers = policy.attachment_headers("linux", "AI-DO-Desktop-latest.deb")

    assert headers is not None
    assert headers.content_type == "application/vnd.debian.binary-package"
    assert headers.content_disposition.startswith("attachment;")
    assert "AI-DO-Desktop-latest.deb" in headers.content_disposition
    assert policy.attachment_headers("linux", "AI-DO-Desktop-latest.deb.blockmap") is None
    assert policy.attachment_headers("linux", "nested/AI-DO-Desktop-latest.deb") is None


def test_ai_do_desktop_update_serving_policy_rejects_unsafe_public_paths() -> None:
    policy = ai_do_desktop_update_serving_policy()

    assert not policy.is_allowed_file_path("win", "")
    assert not policy.is_allowed_file_path("win", ".hidden.exe")
    assert not policy.is_allowed_file_path("win", "nested/AI-DO-Desktop-Setup-latest.exe")
    assert not policy.is_allowed_file_path("win", "AI-DO-Desktop-Setup-latest.exe\n")
    assert not policy.is_allowed_file_path("unknown", "AI-DO-Desktop-Setup-latest.exe")
