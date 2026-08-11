from __future__ import annotations

import sys
from pathlib import Path


def _workspace_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "pnpm-workspace.yaml").exists():
            return parent
    return current.parents[4]


def _ensure_api_src_on_path() -> None:
    api_src = _workspace_root() / "apps" / "api" / "src"
    if str(api_src) not in sys.path:
        sys.path.insert(0, str(api_src))


_ensure_api_src_on_path()

from open_work_hub_api.core.worker_queue_contract import (  # noqa: E402,F401
    AI_GRAPH_QUEUE,
    AI_GRAPH_REPUBLISH_TASK_NAME,
    AI_GRAPH_RUN_TASK_NAME,
    DEFAULT_QUEUE,
    FILE_STORAGE_CLEANUP_REPUBLISH_TASK_NAME,
    FILE_STORAGE_CLEANUP_TASK_NAME,
    LLM_ROUTING_CONTROL_PLANE_WORKER_BOOTSTRAP_GROUPS,
    MAIL_SYNC_QUEUE,
    MAIL_SYNC_TASK_NAME,
    MEETING_TRANSCRIBE_QUEUE,
    RAG_SYNC_BACKFILL_QUEUE,
    RAG_SYNC_BACKFILL_RESOURCE_TASK_NAME,
    RAG_SYNC_REALTIME_QUEUE,
    RAG_SYNC_RESOURCE_TASK_NAME,
    RAG_VISIBILITY_RECOMPUTE_QUEUE,
    RAG_VISIBILITY_RECOMPUTE_TASK_NAME,
    GENERAL_WORKER_QUEUE_NAMES,
    SEARCH_INDEX_REALTIME_QUEUE,
    SEARCH_INDEX_RESOURCE_TASK_NAME,
    SERVER_MANAGED_QUEUE_GROUPS,
    SERVER_MANAGED_QUEUE_NAMES,
    TASK_QUEUE_ROUTES,
    WORKER_BOOTSTRAP_GROUP_ALL,
    WORKER_BOOTSTRAP_GROUP_BEAT,
    WORKER_BOOTSTRAP_GROUPS,
    WORKER_QUEUE_GROUP_CONCURRENCY,
    WORKER_QUEUE_GROUPS,
    WORKER_QUEUE_NAMES,
    celery_task_routes,
    celery_worker_group_concurrency,
    celery_worker_queue_argument,
    main,
    normalize_worker_bootstrap_group,
    worker_bootstrap_group_requires_llm_routing,
)


def assert_worker_queue_access(
    *,
    queue_group: str | None,
    requested_queues: object,
    env_profile: str,
    root: Path | None = None,
) -> None:
    """Reject protected queue subscriptions outside the server systemd worker.

    This is an accidental-consumption guard, not a broker security boundary.
    Redis ACL/network isolation remains a separate operational control.
    """

    if isinstance(requested_queues, str):
        queue_names = {item.strip() for item in requested_queues.split(",") if item.strip()}
    else:
        try:
            queue_names = {
                str(getattr(item, "name", item)).strip()
                for item in requested_queues  # type: ignore[union-attr]
                if str(getattr(item, "name", item)).strip()
            }
        except TypeError:
            queue_names = set()
    protected = queue_names.intersection(SERVER_MANAGED_QUEUE_NAMES)
    if not protected:
        return

    normalized_group = normalize_worker_bootstrap_group(queue_group)
    if normalized_group not in SERVER_MANAGED_QUEUE_GROUPS:
        raise RuntimeError("Protected queues require their dedicated managed worker group.")

    resolved_root = (root or _workspace_root()).resolve()
    normalized_profile = (env_profile or "").strip().lower()
    expected_root = {
        "dev": Path("/projects/open-work-hub/dev"),
        "prod": Path("/projects/open-work-hub/prod"),
        "production": Path("/projects/open-work-hub/prod"),
    }.get(normalized_profile)
    if expected_root is None or resolved_root != expected_root:
        raise RuntimeError(
            "Protected queues may only run from the managed dev/prod server checkout."
        )


if __name__ == "__main__":
    main()
