from __future__ import annotations


def import_all_models() -> None:
    """Register every SQLAlchemy model class with the shared metadata registry."""
    from open_work_hub_api.domains.ai import approvals as ai_approvals  # noqa: F401
    from open_work_hub_api.domains.ai import interactions as ai_interactions  # noqa: F401
    from open_work_hub_api.domains.ai import model_settings_models as ai_model_settings_models  # noqa: F401
    from open_work_hub_api.domains.ai.runtime import models as ai_runtime_models  # noqa: F401
    from open_work_hub_api.domains.ai_artifacts import models as ai_artifact_models  # noqa: F401
    from open_work_hub_api.domains.ai_graph import models as ai_graph_models  # noqa: F401
    from open_work_hub_api.domains.announcements import models as announcements_models  # noqa: F401
    from open_work_hub_api.domains.auth import models as auth_models  # noqa: F401
    from open_work_hub_api.domains.bento import models as bento_models  # noqa: F401
    from open_work_hub_api.domains.community import models as community_models  # noqa: F401
    from open_work_hub_api.domains.conversations import (  # noqa: F401
        models as conversations_models,
    )
    from open_work_hub_api.domains.diagrams import models as diagrams_models  # noqa: F401
    from open_work_hub_api.domains.docs import models as docs_models  # noqa: F401
    from open_work_hub_api.domains.dm import models as dm_models  # noqa: F401
    from open_work_hub_api.domains.files import models as files_models  # noqa: F401
    from open_work_hub_api.domains.mail import models as mail_models  # noqa: F401
    from open_work_hub_api.domains.media import models as media_models  # noqa: F401
    from open_work_hub_api.domains.meeting import models as meeting_models  # noqa: F401
    from open_work_hub_api.domains.notifications import models as notifications_models  # noqa: F401
    from open_work_hub_api.domains.personal_widgets import models as personal_widgets_models  # noqa: F401
    from open_work_hub_api.domains.pms import models as pms_models  # noqa: F401
    from open_work_hub_api.domains.planner import models as planner_models  # noqa: F401
    from open_work_hub_api.domains.rag import models as rag_models  # noqa: F401
    from open_work_hub_api.domains.retrieval import models as retrieval_models  # noqa: F401
    from open_work_hub_api.domains.release_notes import models as release_notes_models  # noqa: F401
    from open_work_hub_api.domains.recording import models as recording_models  # noqa: F401
    from open_work_hub_api.domains.search import models as search_models  # noqa: F401
    from open_work_hub_api.domains.usage import models as usage_models  # noqa: F401
    from open_work_hub_api.domains.video_chat import models as video_chat_models  # noqa: F401
    from open_work_hub_api.domains.whiteboard import models as whiteboard_models  # noqa: F401
