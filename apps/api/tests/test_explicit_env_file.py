from __future__ import annotations

from pathlib import Path

import pytest

from open_work_hub_api.core.explicit_env_file import (
    ExplicitEnvFileError,
    load_explicit_env_file,
)


def test_explicit_env_file_parses_dotenv_and_projects_allowlist(tmp_path: Path) -> None:
    env_file = tmp_path / "legacy.env"
    env_file.write_text(
        "\n".join(
            (
                "export OPEN_WORK_HUB_IMAGE_PROVIDER='openai' # provider",
                'OPEN_WORK_HUB_IMAGE_MODEL="image model"',
                "UNRELATED_SECRET=must-not-be-returned",
            )
        )
        + "\n",
        encoding="utf-8",
    )

    result = load_explicit_env_file(
        env_file,
        allowed_keys={"OPEN_WORK_HUB_IMAGE_PROVIDER", "OPEN_WORK_HUB_IMAGE_MODEL"},
    )

    assert result == {
        "OPEN_WORK_HUB_IMAGE_PROVIDER": "openai",
        "OPEN_WORK_HUB_IMAGE_MODEL": "image model",
    }
    assert "must-not-be-returned" not in repr(result)


@pytest.mark.parametrize(
    ("contents", "code"),
    (
        ("OPEN_WORK_HUB_IMAGE_MODEL=one\nOPEN_WORK_HUB_IMAGE_MODEL=two\n", "env_file_duplicate_key"),
        ("this is not dotenv\n", "env_file_invalid"),
    ),
)
def test_explicit_env_file_rejects_ambiguous_input(
    tmp_path: Path,
    contents: str,
    code: str,
) -> None:
    env_file = tmp_path / "legacy.env"
    env_file.write_text(contents, encoding="utf-8")

    with pytest.raises(ExplicitEnvFileError) as exc_info:
        load_explicit_env_file(env_file, allowed_keys={"OPEN_WORK_HUB_IMAGE_MODEL"})

    assert exc_info.value.code == code
    assert contents not in str(exc_info.value)


def test_explicit_env_file_requires_existing_regular_file(tmp_path: Path) -> None:
    with pytest.raises(ExplicitEnvFileError) as exc_info:
        load_explicit_env_file(
            tmp_path / "missing.env",
            allowed_keys={"OPEN_WORK_HUB_IMAGE_MODEL"},
        )

    assert exc_info.value.code == "env_file_unavailable"
