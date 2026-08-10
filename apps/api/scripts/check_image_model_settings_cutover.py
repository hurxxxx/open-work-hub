"""Validate the image-model production cutover without exposing settings."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from open_alm_api.core.db import get_session_factory  # noqa: E402
from open_alm_api.domains.images.cutover import (  # noqa: E402
    ImageModelCutoverError,
    check_image_model_cutover,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--jobs-only",
        action="store_true",
        help="Only require an empty image broker queue and no queued/running DB jobs.",
    )
    args = parser.parse_args()

    try:
        with get_session_factory()() as db:
            result = check_image_model_cutover(db, jobs_only=args.jobs_only)
    except ImageModelCutoverError as exc:
        print(f"status=failed reason={exc.code}", file=sys.stderr)
        return 1
    print(result.status_line())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
