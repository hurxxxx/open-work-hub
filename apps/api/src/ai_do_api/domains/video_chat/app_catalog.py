from ai_do_api.core.workspace_app_registry import (
    WorkspaceAppRegistration,
    WorkspaceNavRegistration,
)


VIDEO_CHAT_WORKSPACE_APP = WorkspaceAppRegistration(
    app_id="video-chat",
    title="화상채팅",
    route_base="/video-chat",
    icon_key="video",
    enabled_by_default=True,
    visible_by_default=True,
    launcher_category=True,
    nav_items=(
        WorkspaceNavRegistration(
            id="video-chat-room",
            title="화상채팅",
            category="Meetings",
            icon_key="video",
        ),
    ),
)
