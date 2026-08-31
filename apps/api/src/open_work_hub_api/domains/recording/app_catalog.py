from open_work_hub_api.core.workspace_app_registry import (
    WorkspaceNavRegistration,
    workspace_app_registration,
)


RECORDING_WORKSPACE_APP = workspace_app_registration(
    "recording",
    nav_items=(
        WorkspaceNavRegistration(
            id="recording-quick",
            title="Quick Record",
            category="Recordings",
            icon_key="mic",
        ),
        WorkspaceNavRegistration(
            id="recording-mine",
            title="My Recordings",
            category="Recordings",
            icon_key="list-music",
            path_suffix="?view=mine",
        ),
        WorkspaceNavRegistration(
            id="recording-meeting",
            title="Meeting Recordings",
            category="Recording Categories",
            icon_key="users",
            path_suffix="?view=mine&category=meeting",
        ),
        WorkspaceNavRegistration(
            id="recording-task",
            title="Task Recordings",
            category="Recording Categories",
            icon_key="check-circle-2",
            path_suffix="?view=mine&category=task",
        ),
        WorkspaceNavRegistration(
            id="recording-unlinked",
            title="Unlinked",
            category="Recording Categories",
            icon_key="inbox",
            path_suffix="?view=mine&category=unlinked",
        ),
        WorkspaceNavRegistration(
            id="recording-processing",
            title="Processing",
            category="Recording Status",
            icon_key="clock-3",
            path_suffix="?view=processing",
        ),
        WorkspaceNavRegistration(
            id="recording-failed",
            title="Failed",
            category="Recording Status",
            icon_key="alert-triangle",
            path_suffix="?view=failed",
        ),
        WorkspaceNavRegistration(
            id="recording-archived",
            title="Archived",
            category="Recording Status",
            icon_key="archive",
            path_suffix="?view=archived",
        ),
    ),
)
