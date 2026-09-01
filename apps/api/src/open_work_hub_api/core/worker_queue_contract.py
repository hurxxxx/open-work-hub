from __future__ import annotations

import argparse
from collections.abc import Mapping


DEFAULT_QUEUE = "celery"
MEETING_TRANSCRIBE_QUEUE = "meeting_transcribe"
MAIL_SYNC_QUEUE = "mail_sync"
RAG_SYNC_REALTIME_QUEUE = "rag_sync_realtime"
RAG_SYNC_BACKFILL_QUEUE = "rag_sync_backfill"
RAG_VISIBILITY_RECOMPUTE_QUEUE = "rag_visibility_recompute"
SEARCH_INDEX_REALTIME_QUEUE = "search_index_realtime"
AI_GRAPH_QUEUE = "ai-graph"
HERMES_QUEUE = "hermes"

FILE_STORAGE_CLEANUP_TASK_NAME = "files.cleanup_storage_object"
FILE_STORAGE_CLEANUP_REPUBLISH_TASK_NAME = "files.republish_storage_cleanup_jobs"
MAIL_SYNC_TASK_NAME = "mail.sync_job"
RAG_SYNC_RESOURCE_TASK_NAME = "rag.sync_resource"
RAG_SYNC_BACKFILL_RESOURCE_TASK_NAME = "rag.sync_backfill_resource"
RAG_VISIBILITY_RECOMPUTE_TASK_NAME = "rag.recompute_visibility"
SEARCH_INDEX_RESOURCE_TASK_NAME = "search.index_resource"
AI_GRAPH_RUN_TASK_NAME = "ai_graph.run"
AI_GRAPH_REPUBLISH_TASK_NAME = "ai_graph.republish"
HERMES_RUN_TASK_NAME = "hermes.run"
HERMES_REPUBLISH_TASK_NAME = "hermes.republish"
HERMES_TERMINAL_MAINTENANCE_TASK_NAME = "hermes_terminal.maintenance"

TASK_QUEUE_ROUTES: Mapping[str, str] = {
    "documents.sync": DEFAULT_QUEUE,
    "ocr.normalize": DEFAULT_QUEUE,
    "media.cleanup_orphans": DEFAULT_QUEUE,
    FILE_STORAGE_CLEANUP_TASK_NAME: DEFAULT_QUEUE,
    FILE_STORAGE_CLEANUP_REPUBLISH_TASK_NAME: DEFAULT_QUEUE,
    "meeting.cleanup_stale_staging": DEFAULT_QUEUE,
    # Reserved for the dormant meeting-owned pipeline documented in the worker;
    # current in-repository producers publish the canonical recording.* chain.
    "meeting.transcribe": MEETING_TRANSCRIBE_QUEUE,
    "meeting.summarize": MEETING_TRANSCRIBE_QUEUE,
    "meeting.extract_insights": MEETING_TRANSCRIBE_QUEUE,
    "meeting.generate_doc": MEETING_TRANSCRIBE_QUEUE,
    "recording.transcribe": MEETING_TRANSCRIBE_QUEUE,
    "recording.analyze_transcript": MEETING_TRANSCRIBE_QUEUE,
    "recording.verify_transcript_summary": MEETING_TRANSCRIBE_QUEUE,
    "recording.persist_result": MEETING_TRANSCRIBE_QUEUE,
    RAG_SYNC_RESOURCE_TASK_NAME: RAG_SYNC_REALTIME_QUEUE,
    RAG_SYNC_BACKFILL_RESOURCE_TASK_NAME: RAG_SYNC_BACKFILL_QUEUE,
    RAG_VISIBILITY_RECOMPUTE_TASK_NAME: RAG_VISIBILITY_RECOMPUTE_QUEUE,
    "rag.republish_pending_jobs": DEFAULT_QUEUE,
    SEARCH_INDEX_RESOURCE_TASK_NAME: SEARCH_INDEX_REALTIME_QUEUE,
    AI_GRAPH_RUN_TASK_NAME: AI_GRAPH_QUEUE,
    AI_GRAPH_REPUBLISH_TASK_NAME: DEFAULT_QUEUE,
    HERMES_RUN_TASK_NAME: HERMES_QUEUE,
    HERMES_REPUBLISH_TASK_NAME: DEFAULT_QUEUE,
    HERMES_TERMINAL_MAINTENANCE_TASK_NAME: DEFAULT_QUEUE,
    "search.republish_pending_index_jobs": DEFAULT_QUEUE,
    MAIL_SYNC_TASK_NAME: MAIL_SYNC_QUEUE,
    "mail.sync_account": MAIL_SYNC_QUEUE,
    "mail.dispatch_due_sync_jobs": DEFAULT_QUEUE,
}

WORKER_QUEUE_NAMES = tuple(dict.fromkeys((DEFAULT_QUEUE, *TASK_QUEUE_ROUTES.values())))
WORKER_QUEUE_GROUPS: Mapping[str, tuple[str, ...]] = {
    "default": (DEFAULT_QUEUE,),
    "realtime": (
        MAIL_SYNC_QUEUE,
        RAG_SYNC_REALTIME_QUEUE,
        RAG_VISIBILITY_RECOMPUTE_QUEUE,
        SEARCH_INDEX_REALTIME_QUEUE,
    ),
    "long": (
        MEETING_TRANSCRIBE_QUEUE,
        RAG_SYNC_BACKFILL_QUEUE,
    ),
    "ai_graph": (AI_GRAPH_QUEUE,),
    "hermes": (HERMES_QUEUE,),
}
WORKER_QUEUE_GROUP_CONCURRENCY: Mapping[str, int] = {
    "default": 1,
    "realtime": 2,
    "long": 1,
    "ai_graph": 1,
    "hermes": 2,
}
WORKER_BOOTSTRAP_GROUP_ALL = "all"
WORKER_BOOTSTRAP_GROUP_BEAT = "beat"
WORKER_BOOTSTRAP_GROUPS = (
    WORKER_BOOTSTRAP_GROUP_ALL,
    *WORKER_QUEUE_GROUPS,
    WORKER_BOOTSTRAP_GROUP_BEAT,
)
LLM_ROUTING_CONTROL_PLANE_WORKER_BOOTSTRAP_GROUPS = (
    WORKER_BOOTSTRAP_GROUP_ALL,
    "long",
    "ai_graph",
)

SERVER_MANAGED_QUEUE_GROUPS: frozenset[str] = frozenset()
SERVER_MANAGED_QUEUE_NAMES: frozenset[str] = frozenset()
GENERAL_WORKER_QUEUE_NAMES = tuple(
    queue for queue in WORKER_QUEUE_NAMES if queue not in SERVER_MANAGED_QUEUE_NAMES
)


def celery_task_routes() -> dict[str, dict[str, str]]:
    return {task_name: {"queue": queue_name} for task_name, queue_name in TASK_QUEUE_ROUTES.items()}


def celery_worker_queue_argument(group: str | None = None) -> str:
    if group is None:
        # The no-group form is used by local/general workers. Server-only queues
        # must be selected through their explicit group.
        return ",".join(GENERAL_WORKER_QUEUE_NAMES)
    return ",".join(_worker_queue_group(group))


def celery_worker_group_concurrency(group: str) -> int:
    normalized = _normalize_worker_queue_group(group)
    return WORKER_QUEUE_GROUP_CONCURRENCY[normalized]


def normalize_worker_bootstrap_group(group: str | None) -> str:
    normalized = str(group or "").strip().lower() or WORKER_BOOTSTRAP_GROUP_ALL
    if normalized not in WORKER_BOOTSTRAP_GROUPS:
        raise ValueError(f"unknown worker bootstrap group: {group}")
    return normalized


def worker_bootstrap_group_requires_llm_routing(group: str | None) -> bool:
    return (
        normalize_worker_bootstrap_group(group) in LLM_ROUTING_CONTROL_PLANE_WORKER_BOOTSTRAP_GROUPS
    )


def _worker_queue_group(group: str) -> tuple[str, ...]:
    normalized = _normalize_worker_queue_group(group)
    return WORKER_QUEUE_GROUPS[normalized]


def _normalize_worker_queue_group(group: str) -> str:
    normalized = str(group or "").strip().lower()
    if normalized not in WORKER_QUEUE_GROUPS:
        raise ValueError(f"unknown worker queue group: {group}")
    return normalized


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--celery-queues",
        action="store_true",
        help="Print the comma-separated queue list for celery worker -Q.",
    )
    parser.add_argument(
        "--celery-queue-group",
        choices=sorted(WORKER_QUEUE_GROUPS),
        help="Print the comma-separated queue list for one celery worker group.",
    )
    args = parser.parse_args()
    if args.celery_queues:
        print(celery_worker_queue_argument(args.celery_queue_group))
        return
    parser.print_help()


if __name__ == "__main__":
    main()


__all__ = [
    "AI_GRAPH_QUEUE",
    "AI_GRAPH_REPUBLISH_TASK_NAME",
    "AI_GRAPH_RUN_TASK_NAME",
    "HERMES_QUEUE",
    "HERMES_REPUBLISH_TASK_NAME",
    "HERMES_RUN_TASK_NAME",
    "HERMES_TERMINAL_MAINTENANCE_TASK_NAME",
    "DEFAULT_QUEUE",
    "FILE_STORAGE_CLEANUP_REPUBLISH_TASK_NAME",
    "FILE_STORAGE_CLEANUP_TASK_NAME",
    "LLM_ROUTING_CONTROL_PLANE_WORKER_BOOTSTRAP_GROUPS",
    "MAIL_SYNC_QUEUE",
    "MAIL_SYNC_TASK_NAME",
    "MEETING_TRANSCRIBE_QUEUE",
    "RAG_SYNC_BACKFILL_QUEUE",
    "RAG_SYNC_BACKFILL_RESOURCE_TASK_NAME",
    "RAG_SYNC_REALTIME_QUEUE",
    "RAG_SYNC_RESOURCE_TASK_NAME",
    "RAG_VISIBILITY_RECOMPUTE_QUEUE",
    "RAG_VISIBILITY_RECOMPUTE_TASK_NAME",
    "SEARCH_INDEX_REALTIME_QUEUE",
    "SEARCH_INDEX_RESOURCE_TASK_NAME",
    "SERVER_MANAGED_QUEUE_GROUPS",
    "SERVER_MANAGED_QUEUE_NAMES",
    "TASK_QUEUE_ROUTES",
    "WORKER_BOOTSTRAP_GROUP_ALL",
    "WORKER_BOOTSTRAP_GROUP_BEAT",
    "WORKER_BOOTSTRAP_GROUPS",
    "WORKER_QUEUE_NAMES",
    "GENERAL_WORKER_QUEUE_NAMES",
    "WORKER_QUEUE_GROUP_CONCURRENCY",
    "WORKER_QUEUE_GROUPS",
    "celery_task_routes",
    "celery_worker_group_concurrency",
    "celery_worker_queue_argument",
    "normalize_worker_bootstrap_group",
    "worker_bootstrap_group_requires_llm_routing",
]
