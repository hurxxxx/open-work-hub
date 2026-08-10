"""Validate the Files partitioned-retrieval production cutover read-only."""

from __future__ import annotations

from pathlib import Path
import sys


_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from ai_do_api.core.db import get_session_factory  # noqa: E402
from ai_do_api.core.settings import get_settings  # noqa: E402
from ai_do_api.domains.retrieval.files_generation_backends import (  # noqa: E402
    FilesPhysicalGenerationBackends,
)
from ai_do_api.domains.retrieval.files_generation_materializer import (  # noqa: E402
    FilesCachedProjectionMaterializer,
)
from ai_do_api.domains.retrieval.files_generation_runner import (  # noqa: E402
    FilesGenerationError,
    FilesGenerationRunner,
)


def main() -> int:
    backends = None
    try:
        settings = get_settings()
        session_factory = get_session_factory()
        backends = FilesPhysicalGenerationBackends(settings)
        runner = FilesGenerationRunner(
            session_factory=session_factory,
            settings=settings,
            backends=backends,
            materializer=FilesCachedProjectionMaterializer(
                session_factory=session_factory,
                settings=settings,
            ),
        )
        result = runner.verify_active()
    except FilesGenerationError as error:
        print(f"status=failed reason={error.code}", file=sys.stderr)
        return 1
    except Exception:
        print("status=failed reason=cutover_check_failed", file=sys.stderr)
        return 1
    finally:
        if backends is not None:
            backends.close()
    print(result.status_line())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
