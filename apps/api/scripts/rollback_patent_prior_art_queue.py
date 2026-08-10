from __future__ import annotations

import sys

from redis import Redis
from sqlalchemy.orm import Session

from ai_do_api.core.db import get_engine
from ai_do_api.core.settings import get_settings
from ai_do_api.core.worker_queue_contract import LEGACY_PATENT_PRIOR_ART_QUEUE
from ai_do_api.domains.patent_prior_art.dispatch import (
    PatentPriorArtJobDispatcher,
    get_celery_client,
)
from ai_do_api.domains.patent_prior_art.queue_cutover import (
    PatentPriorArtQueueCutoverError,
    rollback_patent_prior_art_queue_cutover,
)


def main() -> int:
    settings = get_settings()
    broker = Redis.from_url(
        settings.worker_broker_url,
        socket_connect_timeout=5,
        socket_timeout=5,
    )
    dispatcher = PatentPriorArtJobDispatcher(
        publisher=get_celery_client(),
        queue=LEGACY_PATENT_PRIOR_ART_QUEUE,
    )
    try:
        with Session(get_engine()) as db:
            result = rollback_patent_prior_art_queue_cutover(
                db,
                broker,
                dispatcher=dispatcher,
            )
    except PatentPriorArtQueueCutoverError as error:
        print(f"status=error code={error}", file=sys.stderr)
        return 1
    except Exception as error:
        print(
            f"status=error code=unexpected_error type={type(error).__name__}",
            file=sys.stderr,
        )
        return 1
    finally:
        broker.close()

    print(result.status_line())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
