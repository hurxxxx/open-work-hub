from __future__ import annotations

import argparse

from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.domains.rag import application as rag_application


def main() -> None:
    parser = argparse.ArgumentParser(description="Reindex registered company retrieval sources.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Override operator cooldown; outbox deduplication remains enforced.",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    with get_session_factory()() as db:
        if args.dry_run:
            counts = rag_application.count_rag_reindex_resources(db)
            external_counts = rag_application.count_company_rag_reindex_resources(db)
            print(
                f"Eligible resources: app={sum(counts.values())}, external={sum(external_counts.values())}"
            )
            return
        result = rag_application.enqueue_rag_reindex(db, force=args.force)
        external = rag_application.enqueue_company_rag_reindex(db)
        db.commit()
        print(
            f"Queued app={result['queued_count']}, external={external['queued_count']} RAG backfill jobs."
        )


if __name__ == "__main__":
    main()
