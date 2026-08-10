"""Preview or apply the one-shot legacy image model settings migration."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from open_alm_api.core.db import get_session_factory  # noqa: E402
from open_alm_api.core.explicit_env_file import (  # noqa: E402
    ExplicitEnvFileError,
    load_explicit_env_file,
)
from open_alm_api.domains.images.legacy_model_settings_import import (  # noqa: E402
    LEGACY_IMAGE_ENV_FIELDS,
    LegacyImageModelImportError,
    import_legacy_image_model_settings,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the migration in one transaction; the default only previews counts.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        required=True,
        help="Load legacy settings from this explicit dotenv file without printing values.",
    )
    args = parser.parse_args()

    try:
        environment = load_explicit_env_file(
            args.env_file,
            allowed_keys=LEGACY_IMAGE_ENV_FIELDS,
        )
        with get_session_factory()() as db:
            result = import_legacy_image_model_settings(
                db,
                environment=environment,
                apply=args.apply,
            )
    except (ExplicitEnvFileError, LegacyImageModelImportError) as exc:
        mode = "apply" if args.apply else "preview"
        reason = exc.code
        print(f"status=failed mode={mode} reason={reason}", file=sys.stderr)
        return 1

    print(result.status_line())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
