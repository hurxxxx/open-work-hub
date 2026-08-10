from __future__ import annotations

import argparse
from collections.abc import Mapping


DEFAULT_QUEUE = "celery"
MEETING_TRANSCRIBE_QUEUE = "meeting_transcribe"
IMAGE_GENERATION_QUEUE = "image_generation"
MAIL_SYNC_QUEUE = "mail_sync"
RAG_SYNC_REALTIME_QUEUE = "rag_sync_realtime"
RAG_SYNC_BACKFILL_QUEUE = "rag_sync_backfill"
RAG_VISIBILITY_RECOMPUTE_QUEUE = "rag_visibility_recompute"
SEARCH_INDEX_REALTIME_QUEUE = "search_index_realtime"
SPEC_COMPARE_QUEUE = "spec_compare"
# PPT 생성 전용 큐. 과거 이름("ppt_generate")은 원격 long 워커의 -Q 설정에 박혀 있어,
# 그 워커가 브로커 재접속 때마다 재구독해 옛 코드로 가로채는 문제가 반복됐다. 큐 이름을
# 분리하면 옛 설정의 워커는 (빈) 옛 큐만 보고, 새 작업은 dedicated ppt 워커만 소비한다.
PPT_GENERATE_QUEUE = "ppt_generate_dedicated"
LEGACY_ISSUE_ATTACHMENT_INDEX_QUEUE = "legacy_issue_attachment_index"
LEGACY_ISSUE_EXCEL_EXPORT_QUEUE = "legacy_issue_excel_export"
# Server-managed patent prior-art queue. The old ``patent_prior_art`` name was
# consumed by generic long/all workers, including developer PCs connected to the
# shared dev broker. A new name is required so already-running old workers cannot
# intercept new deliveries.
PATENT_PRIOR_ART_QUEUE = "patent_prior_art_server_v1"
LEGACY_PATENT_PRIOR_ART_QUEUE = "patent_prior_art"
AI_GRAPH_QUEUE = "ai-graph"

GROUPWARE_HR_SYNC_TASK_NAME = "hr.sync_groupware"
GROUPWARE_HR_SYNC_QUEUE = DEFAULT_QUEUE
ERP_HR_SNAPSHOT_TASK_NAME = "hr.capture_erp_snapshot"
ERP_HR_SNAPSHOT_QUEUE = DEFAULT_QUEUE
HR_MASTER_TASK_NAME = "hr.build_master"
HR_MASTER_QUEUE = DEFAULT_QUEUE
NEWS_COLLECT_TASK_NAME = "news.collect_all"
# Dedicated queue so a news-only worker (local dev) can consume collection
# without pulling shared default-queue tasks. Deployed default workers also
# consume it via the "default" group below.
NEWS_COLLECT_QUEUE = "news"
QNA_BOARD_SYNC_TASK_NAME = "qna.crawl_board"
QNA_BOARD_SYNC_QUEUE = "groupware_notices"
INDUSTRY_REPORT_COLLECT_TASK_NAME = "industry_report.collect_all"
# Industry-report collection shares the news queue (both are low-frequency,
# global content crawls) so no new worker bootstrap group is needed.
INDUSTRY_REPORT_COLLECT_QUEUE = NEWS_COLLECT_QUEUE
FILE_STORAGE_CLEANUP_TASK_NAME = "files.cleanup_storage_object"
FILE_STORAGE_CLEANUP_REPUBLISH_TASK_NAME = "files.republish_storage_cleanup_jobs"
IMAGE_GENERATION_TASK_NAME = "images.generate_image"
MAIL_SYNC_TASK_NAME = "mail.sync_job"
RAG_SYNC_RESOURCE_TASK_NAME = "rag.sync_resource"
RAG_SYNC_BACKFILL_RESOURCE_TASK_NAME = "rag.sync_backfill_resource"
RAG_VISIBILITY_RECOMPUTE_TASK_NAME = "rag.recompute_visibility"
SEARCH_INDEX_RESOURCE_TASK_NAME = "search.index_resource"
SPEC_COMPARE_RUN_JOB_TASK_NAME = "spec_compare.run_job"
PPT_GENERATOR_GENERATE_TASK_NAME = "ppt_generator.generate"
PPT_GENERATOR_CHAT_EDIT_TASK_NAME = "ppt_generator.chat_edit"
PPT_GENERATOR_FINALIZE_TASK_NAME = "ppt_generator.finalize"
LEGACY_ISSUE_ATTACHMENT_INDEX_TASK_NAME = "legacy_issue_attachment.index"
LEGACY_ISSUE_ATTACHMENT_CLEANUP_TASK_NAME = (
    "legacy_issue_attachment.cleanup_vehicle_module_checklist_objects"
)
LEGACY_ISSUE_ATTACHMENT_ORPHAN_RECONCILE_TASK_NAME = (
    "legacy_issue_attachment.reconcile_vehicle_module_checklist_orphans"
)
LEGACY_ISSUE_EXCEL_EXPORT_TASK_NAME = "legacy_issues.excel_export.generate"
LEGACY_ISSUE_EXCEL_EXPORT_REPUBLISH_TASK_NAME = "legacy_issues.excel_export.republish"
LEGACY_ISSUE_EXCEL_EXPORT_CLEANUP_TASK_NAME = "legacy_issues.excel_export.cleanup"
PATENT_PRIOR_ART_RUN_JOB_TASK_NAME = "patent_prior_art.run_job"
PATENT_PRIOR_ART_REPUBLISH_TASK_NAME = "patent_prior_art.republish_pending_jobs"
PATENT_PRIOR_ART_RECOVER_TASK_NAME = "patent_prior_art.recover_jobs"
AI_GRAPH_RUN_TASK_NAME = "ai_graph.run"
AI_GRAPH_REPUBLISH_TASK_NAME = "ai_graph.republish"

TASK_QUEUE_ROUTES: Mapping[str, str] = {
    "documents.sync": DEFAULT_QUEUE,
    "ocr.normalize": DEFAULT_QUEUE,
    "drafts.export": DEFAULT_QUEUE,
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
    "recording.create_raw_transcript_doc": MEETING_TRANSCRIBE_QUEUE,
    "recording.analyze_transcript": MEETING_TRANSCRIBE_QUEUE,
    "recording.verify_transcript_summary": MEETING_TRANSCRIBE_QUEUE,
    "recording.create_minutes_doc": MEETING_TRANSCRIBE_QUEUE,
    RAG_SYNC_RESOURCE_TASK_NAME: RAG_SYNC_REALTIME_QUEUE,
    RAG_SYNC_BACKFILL_RESOURCE_TASK_NAME: RAG_SYNC_BACKFILL_QUEUE,
    RAG_VISIBILITY_RECOMPUTE_TASK_NAME: RAG_VISIBILITY_RECOMPUTE_QUEUE,
    "rag.republish_pending_jobs": DEFAULT_QUEUE,
    SEARCH_INDEX_RESOURCE_TASK_NAME: SEARCH_INDEX_REALTIME_QUEUE,
    LEGACY_ISSUE_ATTACHMENT_INDEX_TASK_NAME: LEGACY_ISSUE_ATTACHMENT_INDEX_QUEUE,
    LEGACY_ISSUE_ATTACHMENT_CLEANUP_TASK_NAME: DEFAULT_QUEUE,
    LEGACY_ISSUE_ATTACHMENT_ORPHAN_RECONCILE_TASK_NAME: DEFAULT_QUEUE,
    LEGACY_ISSUE_EXCEL_EXPORT_TASK_NAME: LEGACY_ISSUE_EXCEL_EXPORT_QUEUE,
    LEGACY_ISSUE_EXCEL_EXPORT_REPUBLISH_TASK_NAME: DEFAULT_QUEUE,
    LEGACY_ISSUE_EXCEL_EXPORT_CLEANUP_TASK_NAME: DEFAULT_QUEUE,
    PATENT_PRIOR_ART_RUN_JOB_TASK_NAME: PATENT_PRIOR_ART_QUEUE,
    PATENT_PRIOR_ART_REPUBLISH_TASK_NAME: DEFAULT_QUEUE,
    PATENT_PRIOR_ART_RECOVER_TASK_NAME: PATENT_PRIOR_ART_QUEUE,
    AI_GRAPH_RUN_TASK_NAME: AI_GRAPH_QUEUE,
    AI_GRAPH_REPUBLISH_TASK_NAME: DEFAULT_QUEUE,
    "search.republish_pending_index_jobs": DEFAULT_QUEUE,
    IMAGE_GENERATION_TASK_NAME: IMAGE_GENERATION_QUEUE,
    SPEC_COMPARE_RUN_JOB_TASK_NAME: SPEC_COMPARE_QUEUE,
    PPT_GENERATOR_GENERATE_TASK_NAME: PPT_GENERATE_QUEUE,
    PPT_GENERATOR_CHAT_EDIT_TASK_NAME: PPT_GENERATE_QUEUE,
    PPT_GENERATOR_FINALIZE_TASK_NAME: PPT_GENERATE_QUEUE,
    MAIL_SYNC_TASK_NAME: MAIL_SYNC_QUEUE,
    "mail.sync_account": MAIL_SYNC_QUEUE,
    "mail.dispatch_due_sync_jobs": DEFAULT_QUEUE,
    GROUPWARE_HR_SYNC_TASK_NAME: DEFAULT_QUEUE,
    ERP_HR_SNAPSHOT_TASK_NAME: ERP_HR_SNAPSHOT_QUEUE,
    HR_MASTER_TASK_NAME: HR_MASTER_QUEUE,
    NEWS_COLLECT_TASK_NAME: NEWS_COLLECT_QUEUE,
    QNA_BOARD_SYNC_TASK_NAME: QNA_BOARD_SYNC_QUEUE,
    INDUSTRY_REPORT_COLLECT_TASK_NAME: INDUSTRY_REPORT_COLLECT_QUEUE,
}

WORKER_QUEUE_NAMES = tuple(dict.fromkeys((DEFAULT_QUEUE, *TASK_QUEUE_ROUTES.values())))
WORKER_QUEUE_GROUPS: Mapping[str, tuple[str, ...]] = {
    "default": (DEFAULT_QUEUE, NEWS_COLLECT_QUEUE, QNA_BOARD_SYNC_QUEUE),
    "realtime": (
        MAIL_SYNC_QUEUE,
        RAG_SYNC_REALTIME_QUEUE,
        RAG_VISIBILITY_RECOMPUTE_QUEUE,
        SEARCH_INDEX_REALTIME_QUEUE,
    ),
    "long": (
        MEETING_TRANSCRIBE_QUEUE,
        IMAGE_GENERATION_QUEUE,
        RAG_SYNC_BACKFILL_QUEUE,
        SPEC_COMPARE_QUEUE,
        # PPT_GENERATE_QUEUE 는 long 이 아니라 아래 전용 "ppt" 그룹으로 분리(원격 long 워커 가로채기 방지).
        LEGACY_ISSUE_ATTACHMENT_INDEX_QUEUE,
        LEGACY_ISSUE_EXCEL_EXPORT_QUEUE,
    ),
    # PPT 생성은 브라우저(HTML→pptx)·전용 환경이 필요해 dedicated 워커만 소비해야 한다.
    # long 그룹에 두면 일반 long 워커(원격 등)가 가로채 옛 코드로 처리하는 문제가 있어 분리한다.
    "ppt": (PPT_GENERATE_QUEUE,),
    # Patent provider searches are deliberately serialized and may only run on
    # the server-managed worker bootstrap.
    "patent": (PATENT_PRIOR_ART_QUEUE,),
    "ai_graph": (AI_GRAPH_QUEUE,),
}
WORKER_QUEUE_GROUP_CONCURRENCY: Mapping[str, int] = {
    "default": 1,
    "realtime": 2,
    "long": 1,
    "ppt": 1,
    "patent": 1,
    "ai_graph": 1,
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
    "ppt",  # PPT 생성 워커도 등록 workload를 호출하므로 LLM 라우팅 제어면 부트스트랩 필요
    "patent",
    "ai_graph",
)

SERVER_MANAGED_QUEUE_GROUPS = frozenset({"patent"})
SERVER_MANAGED_QUEUE_NAMES = frozenset({PATENT_PRIOR_ART_QUEUE})
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
    "DEFAULT_QUEUE",
    "ERP_HR_SNAPSHOT_QUEUE",
    "ERP_HR_SNAPSHOT_TASK_NAME",
    "FILE_STORAGE_CLEANUP_REPUBLISH_TASK_NAME",
    "FILE_STORAGE_CLEANUP_TASK_NAME",
    "GROUPWARE_HR_SYNC_QUEUE",
    "GROUPWARE_HR_SYNC_TASK_NAME",
    "HR_MASTER_QUEUE",
    "HR_MASTER_TASK_NAME",
    "IMAGE_GENERATION_QUEUE",
    "IMAGE_GENERATION_TASK_NAME",
    "INDUSTRY_REPORT_COLLECT_QUEUE",
    "INDUSTRY_REPORT_COLLECT_TASK_NAME",
    "LEGACY_ISSUE_ATTACHMENT_INDEX_QUEUE",
    "LEGACY_PATENT_PRIOR_ART_QUEUE",
    "LEGACY_ISSUE_ATTACHMENT_CLEANUP_TASK_NAME",
    "LEGACY_ISSUE_ATTACHMENT_INDEX_TASK_NAME",
    "LEGACY_ISSUE_ATTACHMENT_ORPHAN_RECONCILE_TASK_NAME",
    "LEGACY_ISSUE_EXCEL_EXPORT_CLEANUP_TASK_NAME",
    "LEGACY_ISSUE_EXCEL_EXPORT_QUEUE",
    "LEGACY_ISSUE_EXCEL_EXPORT_REPUBLISH_TASK_NAME",
    "LEGACY_ISSUE_EXCEL_EXPORT_TASK_NAME",
    "LLM_ROUTING_CONTROL_PLANE_WORKER_BOOTSTRAP_GROUPS",
    "MAIL_SYNC_QUEUE",
    "MAIL_SYNC_TASK_NAME",
    "MEETING_TRANSCRIBE_QUEUE",
    "NEWS_COLLECT_QUEUE",
    "NEWS_COLLECT_TASK_NAME",
    "PPT_GENERATE_QUEUE",
    "PPT_GENERATOR_CHAT_EDIT_TASK_NAME",
    "PPT_GENERATOR_FINALIZE_TASK_NAME",
    "PPT_GENERATOR_GENERATE_TASK_NAME",
    "PATENT_PRIOR_ART_QUEUE",
    "PATENT_PRIOR_ART_RECOVER_TASK_NAME",
    "PATENT_PRIOR_ART_REPUBLISH_TASK_NAME",
    "PATENT_PRIOR_ART_RUN_JOB_TASK_NAME",
    "QNA_BOARD_SYNC_QUEUE",
    "QNA_BOARD_SYNC_TASK_NAME",
    "RAG_SYNC_BACKFILL_QUEUE",
    "RAG_SYNC_BACKFILL_RESOURCE_TASK_NAME",
    "RAG_SYNC_REALTIME_QUEUE",
    "RAG_SYNC_RESOURCE_TASK_NAME",
    "RAG_VISIBILITY_RECOMPUTE_QUEUE",
    "RAG_VISIBILITY_RECOMPUTE_TASK_NAME",
    "SEARCH_INDEX_REALTIME_QUEUE",
    "SEARCH_INDEX_RESOURCE_TASK_NAME",
    "SPEC_COMPARE_QUEUE",
    "SPEC_COMPARE_RUN_JOB_TASK_NAME",
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
