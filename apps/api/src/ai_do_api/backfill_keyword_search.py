from __future__ import annotations

import argparse

from sqlalchemy import select

from ai_do_api.core.db import get_session_factory
from ai_do_api.domains.auth.models import Workspace
from ai_do_api.domains.search.service import refresh_workspace_keyword_index


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild OpenSearch keyword indexes for selected workspaces.")
    parser.add_argument(
        "--workspace-key",
        action="append",
        default=[],
        help="Workspace key to rebuild. Can be passed more than once.",
    )
    parser.add_argument(
        "--all-active",
        action="store_true",
        help="Rebuild all active workspaces.",
    )
    args = parser.parse_args()

    workspace_keys = [key.strip() for key in args.workspace_key if key.strip()]
    if not args.all_active and not workspace_keys:
        raise SystemExit("Pass at least one --workspace-key or use --all-active.")

    with get_session_factory()() as db:
        query = select(Workspace).where(Workspace.active.is_(True)).order_by(Workspace.key.asc())
        if not args.all_active:
            query = query.where(Workspace.key.in_(workspace_keys))
        workspaces = list(db.scalars(query))
        if not workspaces:
            raise SystemExit("No matching active workspaces found.")

        for workspace in workspaces:
            refresh_workspace_keyword_index(db, workspace=workspace)
            print(f"Rebuilt keyword search index for workspace {workspace.key} ({workspace.id}).")


if __name__ == "__main__":
    main()
