from __future__ import annotations


def import_all_models() -> None:
    """Register every SQLAlchemy model class with the shared metadata registry."""
    from ai_do_api.domains.ai import approvals as ai_approvals  # noqa: F401
    from ai_do_api.domains.ai import interactions as ai_interactions  # noqa: F401
    from ai_do_api.domains.ai import model_settings_models as ai_model_settings_models  # noqa: F401
    from ai_do_api.domains.ai.runtime import models as ai_runtime_models  # noqa: F401
    from ai_do_api.domains.ai_artifacts import models as ai_artifact_models  # noqa: F401
    from ai_do_api.domains.ai_graph import models as ai_graph_models  # noqa: F401
    from ai_do_api.domains.announcements import models as announcements_models  # noqa: F401
    from ai_do_api.domains.auth import models as auth_models  # noqa: F401
    from ai_do_api.domains.community import models as community_models  # noqa: F401
    from ai_do_api.domains.conversations import (  # noqa: F401
        models as conversations_models,
    )
    from ai_do_api.domains.dataviz import models as dataviz_models  # noqa: F401
    from ai_do_api.domains.dataviz import sys_perf_models  # noqa: F401
    from ai_do_api.domains.diagrams import models as diagrams_models  # noqa: F401
    from ai_do_api.domains.lawsearch import models as lawsearch_models  # noqa: F401
    from ai_do_api.domains.legacy_issues import models as legacy_issues_models  # noqa: F401
    from ai_do_api.domains.docs import models as docs_models  # noqa: F401
    from ai_do_api.domains.dm import models as dm_models  # noqa: F401
    from ai_do_api.domains.files import models as files_models  # noqa: F401
    from ai_do_api.domains.hr import models as hr_models  # noqa: F401
    from ai_do_api.domains.images import models as images_models  # noqa: F401
    from ai_do_api.domains.images import (  # noqa: F401
        model_settings_models as image_model_settings_models,
    )
    from ai_do_api.domains.industry_report import models as industry_report_models  # noqa: F401
    from ai_do_api.domains.mail import models as mail_models  # noqa: F401
    from ai_do_api.domains.management_tasks import models as management_tasks_models  # noqa: F401
    from ai_do_api.domains.meal_invoice_ocr import (  # noqa: F401
        models as meal_invoice_ocr_models,
    )
    from ai_do_api.domains.media import models as media_models  # noqa: F401
    from ai_do_api.domains.meeting import models as meeting_models  # noqa: F401
    from ai_do_api.domains.mcloudoc import models as mcloudoc_models  # noqa: F401
    from ai_do_api.domains.news import models as news_models  # noqa: F401
    from ai_do_api.domains.notifications import models as notifications_models  # noqa: F401
    from ai_do_api.domains.patent_automation import models as patent_automation_models  # noqa: F401
    from ai_do_api.domains.patent_prior_art import models as patent_prior_art_models  # noqa: F401
    from ai_do_api.domains.personal_widgets import models as personal_widgets_models  # noqa: F401
    from ai_do_api.domains.pms import models as pms_models  # noqa: F401
    from ai_do_api.domains.planner import models as planner_models  # noqa: F401
    from ai_do_api.domains.ppt_generator import models as ppt_generator_models  # noqa: F401
    from ai_do_api.domains.qna import models as qna_models  # noqa: F401
    from ai_do_api.domains.rag import models as rag_models  # noqa: F401
    from ai_do_api.domains.retrieval import models as retrieval_models  # noqa: F401
    from ai_do_api.domains.release_notes import models as release_notes_models  # noqa: F401
    from ai_do_api.domains.recording import models as recording_models  # noqa: F401
    from ai_do_api.domains.search import models as search_models  # noqa: F401
    from ai_do_api.domains.spec_compare import models as spec_compare_models  # noqa: F401
    from ai_do_api.domains.usage import models as usage_models  # noqa: F401
    from ai_do_api.domains.video_chat import models as video_chat_models  # noqa: F401
    from ai_do_api.domains.whiteboard import models as whiteboard_models  # noqa: F401
