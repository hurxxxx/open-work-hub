from open_work_hub_api.core.app_registry import (
    AppNavRegistration,
    app_registration,
)

VIDEO_CHAT_APP = app_registration(
    "video-chat",
    nav_items=(
        AppNavRegistration(
            id="video-chat-room",
            title="화상채팅",
            category="Meetings",
            icon_key="video",
        ),
    ),
)
