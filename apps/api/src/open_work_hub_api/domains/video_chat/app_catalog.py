from open_work_hub_api.core.workspace_app_registry import (
    WorkspaceNavRegistration,
    workspace_app_registration,
)


VIDEO_CHAT_WORKSPACE_APP = workspace_app_registration(
    "video-chat",
    nav_items=(
        WorkspaceNavRegistration(
            id="video-chat-room",
            title="화상채팅",
            category="Meetings",
            icon_key="video",
        ),
    ),
)
