from __future__ import annotations

import argparse

from sqlalchemy import select

from ai_do_api.core.db import get_session_factory
from ai_do_api.domains.auth.models import Workspace
from ai_do_api.domains.rag import application as rag_application


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enqueue RAG backfill jobs for selected workspaces or company scope."
    )
    parser.add_argument(
        "--company",
        action="store_true",
        help="Reindex company-scoped resources such as management Q&A.",
    )
    parser.add_argument(
        "--workspace-key",
        action="append",
        default=[],
        help="Workspace key to reindex. Can be passed more than once.",
    )
    parser.add_argument("--all-active", action="store_true", help="Reindex all active workspaces.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bypass the operator cooldown; existing pending jobs are reused by the outbox.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print eligible resource counts without enqueueing jobs or syncing connectors.",
    )
    args = parser.parse_args()

    workspace_keys = [key.strip() for key in args.workspace_key if key.strip()]
    if not args.company and not args.all_active and not workspace_keys:
        raise SystemExit("Pass --company, at least one --workspace-key, or use --all-active.")

    with get_session_factory()() as db:
        if args.company:
            if args.dry_run:
                resource_counts = rag_application.count_company_rag_reindex_resources(db)
                print(
                    f"Would queue {sum(resource_counts.values())} company RAG "
                    "backfill job(s)."
                )
                print(f"  resource_counts={resource_counts}")
            else:
                result = rag_application.enqueue_company_rag_reindex(db)
                db.commit()
                print(f"Queued {result['queued_count']} company RAG backfill job(s).")

        workspaces: list[Workspace] = []
        if args.all_active or workspace_keys:
            query = select(Workspace).where(Workspace.active.is_(True)).order_by(Workspace.key.asc())
            if not args.all_active:
                query = query.where(Workspace.key.in_(workspace_keys))
            workspaces = list(db.scalars(query))
        if (args.all_active or workspace_keys) and not workspaces:
            raise SystemExit("No matching active workspaces found.")

        for workspace in workspaces:
            try:
                if args.dry_run:
                    resource_counts = rag_application.count_workspace_rag_reindex_resources(
                        db,
                        workspace=workspace,
                    )
                    print(
                        f"Would queue {sum(resource_counts.values())} RAG backfill job(s) "
                        f"for workspace {workspace.key} ({workspace.id})."
                    )
                    print(f"  resource_counts={resource_counts}")
                    continue
                result = rag_application.enqueue_workspace_rag_reindex(
                    db,
                    workspace=workspace,
                    force=args.force,
                )
            except rag_application.RagApplicationError as error:
                db.rollback()
                print(f"Skipped workspace {workspace.key} ({workspace.id}): {error.code}")
                continue
            db.commit()
            print(
                f"Queued {result['queued_count']} RAG backfill job(s) "
                f"for workspace {workspace.key} ({workspace.id})."
            )


if __name__ == "__main__":
    main()
