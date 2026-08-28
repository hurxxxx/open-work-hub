from open_work_hub_api.core.workspace_app_registry import (
    WorkspaceNavRegistration,
    workspace_app_registration,
)


MAIL_WORKSPACE_APP = workspace_app_registration(
    "mail",
    nav_items=(
        WorkspaceNavRegistration(
            id="mail-inbox",
            title="Inbox",
            category="Mail",
            icon_key="inbox",
        ),
        WorkspaceNavRegistration(
            id="mail-unread",
            title="Unread",
            category="Mail",
            icon_key="mail-open",
            path_suffix="?unread=true",
        ),
        WorkspaceNavRegistration(
            id="mail-starred",
            title="Starred",
            category="Mail",
            icon_key="star",
            path_suffix="?starred=true",
        ),
        WorkspaceNavRegistration(
            id="mail-drafts",
            title="Drafts",
            category="Mail",
            icon_key="file-pen-line",
            path_suffix="?view=drafts",
        ),
        WorkspaceNavRegistration(
            id="mail-settings",
            title="Settings",
            category="Mail",
            icon_key="settings",
            path_suffix="?view=settings",
        ),
    ),
)
