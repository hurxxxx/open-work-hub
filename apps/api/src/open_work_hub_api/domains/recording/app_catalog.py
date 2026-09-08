from open_work_hub_api.core.app_registry import (
    AppNavRegistration,
    app_registration,
)

RECORDING_APP = app_registration(
    "recording",
    nav_items=(
        AppNavRegistration(
            id="recording-quick",
            title="Quick Record",
            category="Recordings",
            icon_key="mic",
        ),
        AppNavRegistration(
            id="recording-mine",
            title="My Recordings",
            category="Recordings",
            icon_key="list-music",
            path_suffix="?view=mine",
        ),
        AppNavRegistration(
            id="recording-meeting",
            title="Meeting Recordings",
            category="Recording Categories",
            icon_key="users",
            path_suffix="?view=mine&category=meeting",
        ),
        AppNavRegistration(
            id="recording-task",
            title="Task Recordings",
            category="Recording Categories",
            icon_key="check-circle-2",
            path_suffix="?view=mine&category=task",
        ),
        AppNavRegistration(
            id="recording-unlinked",
            title="Unlinked",
            category="Recording Categories",
            icon_key="inbox",
            path_suffix="?view=mine&category=unlinked",
        ),
        AppNavRegistration(
            id="recording-processing",
            title="Processing",
            category="Recording Status",
            icon_key="clock-3",
            path_suffix="?view=processing",
        ),
        AppNavRegistration(
            id="recording-failed",
            title="Failed",
            category="Recording Status",
            icon_key="alert-triangle",
            path_suffix="?view=failed",
        ),
        AppNavRegistration(
            id="recording-archived",
            title="Archived",
            category="Recording Status",
            icon_key="archive",
            path_suffix="?view=archived",
        ),
    ),
)
