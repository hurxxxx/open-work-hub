from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkspaceNavCatalogItem:
    id: str
    app_id: str
    title: str
    category: str
    icon_key: str
    link_app_id: str | None = None
    path_suffix: str | None = None
    absolute_path: str | None = None
    coming_soon: bool = False


@dataclass(frozen=True)
class WorkspaceAppCatalogItem:
    app_id: str
    title: str
    route_base: str
    icon_key: str
    enabled_by_default: bool = True
    nav_items: tuple[WorkspaceNavCatalogItem, ...] = ()


WORKSPACE_APP_CATALOG: tuple[WorkspaceAppCatalogItem, ...] = (
    WorkspaceAppCatalogItem(
        app_id="home",
        title="HOME",
        route_base="/home",
        icon_key="home",
    ),
    WorkspaceAppCatalogItem(
        app_id="ai",
        title="AI",
        route_base="/ai",
        icon_key="brain",
        nav_items=(
            WorkspaceNavCatalogItem(
                id="chatbot",
                app_id="ai",
                title="AI 챗봇",
                category="Core Tools",
                icon_key="message-square",
            ),
            WorkspaceNavCatalogItem(
                id="search",
                app_id="ai",
                title="아이두 통합검색",
                category="Core Tools",
                icon_key="search",
            ),
            WorkspaceNavCatalogItem(
                id="drafting",
                app_id="ai",
                title="기안작성 도우미",
                category="Core Tools",
                icon_key="file-text",
                coming_soon=True,
            ),
            WorkspaceNavCatalogItem(
                id="translate",
                app_id="ai",
                title="문서 번역/요약",
                category="Core Tools",
                icon_key="languages",
                coming_soon=True,
            ),
            WorkspaceNavCatalogItem(
                id="spec-compare",
                app_id="ai",
                title="규격서 비교",
                category="Core Tools",
                icon_key="file-search",
                coming_soon=True,
            ),
            WorkspaceNavCatalogItem(
                id="fmea-compare",
                app_id="ai",
                title="FMEA 비교",
                category="Core Tools",
                icon_key="alert-triangle",
                coming_soon=True,
            ),
            WorkspaceNavCatalogItem(
                id="meeting-minutes",
                app_id="ai",
                title="회의록",
                category="Assistants",
                icon_key="mic",
                link_app_id="meeting",
                path_suffix="?tab=recordings",
            ),
            WorkspaceNavCatalogItem(
                id="image-wizard",
                app_id="ai",
                title="이미지 위저드",
                category="Assistants",
                icon_key="image",
            ),
            WorkspaceNavCatalogItem(
                id="email-assistant",
                app_id="ai",
                title="메일 작성 도우미",
                category="Assistants",
                icon_key="mail",
                coming_soon=True,
            ),
            WorkspaceNavCatalogItem(
                id="ppt-assistant",
                app_id="ai",
                title="PPT 발표 도우미",
                category="Assistants",
                icon_key="presentation",
                coming_soon=True,
            ),
            WorkspaceNavCatalogItem(
                id="qa-assistant",
                app_id="ai",
                title="사내 관리팀 Q&A",
                category="Assistants",
                icon_key="help-circle",
                coming_soon=True,
            ),
            WorkspaceNavCatalogItem(
                id="news",
                app_id="ai",
                title="뉴스",
                category="Assistants",
                icon_key="newspaper",
                coming_soon=True,
            ),
            WorkspaceNavCatalogItem(
                id="industry-report",
                app_id="ai",
                title="산업 리포트",
                category="Assistants",
                icon_key="bar-chart-3",
                coming_soon=True,
            ),
            WorkspaceNavCatalogItem(
                id="patent-interpret",
                app_id="ai",
                title="특허 해석 도우미",
                category="Patent",
                icon_key="gavel",
                coming_soon=True,
            ),
            WorkspaceNavCatalogItem(
                id="patent-apply",
                app_id="ai",
                title="특허 출원 도우미",
                category="Patent",
                icon_key="file-plus",
                coming_soon=True,
            ),
            WorkspaceNavCatalogItem(
                id="patent-report",
                app_id="ai",
                title="AI 특허 보고서",
                category="Patent",
                icon_key="file-bar-chart",
                coming_soon=True,
            ),
        ),
    ),
    WorkspaceAppCatalogItem(
        app_id="pms",
        title="PMS",
        route_base="/pms",
        icon_key="folder-kanban",
        nav_items=(
            WorkspaceNavCatalogItem(
                id="pms-inbox",
                app_id="pms",
                title="Inbox",
                category="Personal",
                icon_key="inbox",
            ),
            WorkspaceNavCatalogItem(
                id="pms-tasks",
                app_id="pms",
                title="My Tasks",
                category="Personal",
                icon_key="check-circle-2",
                path_suffix="/assigned",
            ),
            WorkspaceNavCatalogItem(
                id="pms-tasks-assigned",
                app_id="pms",
                title="Assigned to me",
                category="Personal",
                icon_key="user",
                path_suffix="/assigned",
            ),
            WorkspaceNavCatalogItem(
                id="pms-tasks-today",
                app_id="pms",
                title="Today & Overdue",
                category="Personal",
                icon_key="calendar",
                path_suffix="/today",
            ),
            WorkspaceNavCatalogItem(
                id="pms-tasks-personal",
                app_id="pms",
                title="Personal List",
                category="Personal",
                icon_key="list",
                path_suffix="/personal",
            ),
        ),
    ),
    WorkspaceAppCatalogItem(
        app_id="docs",
        title="DOCS",
        route_base="/docs",
        icon_key="files",
        nav_items=(
            WorkspaceNavCatalogItem(
                id="docs-all",
                app_id="docs",
                title="All Docs",
                category="Library",
                icon_key="files",
            ),
            WorkspaceNavCatalogItem(
                id="docs-my",
                app_id="docs",
                title="My Docs",
                category="Library",
                icon_key="user",
            ),
            WorkspaceNavCatalogItem(
                id="docs-shared",
                app_id="docs",
                title="Shared with me",
                category="Library",
                icon_key="share-2",
            ),
            WorkspaceNavCatalogItem(
                id="docs-private",
                app_id="docs",
                title="Private",
                category="Library",
                icon_key="lock",
            ),
            WorkspaceNavCatalogItem(
                id="docs-notes",
                app_id="docs",
                title="Meeting Notes",
                category="Library",
                icon_key="mic",
            ),
            WorkspaceNavCatalogItem(
                id="docs-recent",
                app_id="docs",
                title="Recent Pages",
                category="Library",
                icon_key="history",
            ),
            WorkspaceNavCatalogItem(
                id="docs-archived",
                app_id="docs",
                title="Archived",
                category="Library",
                icon_key="history",
            ),
        ),
    ),
    WorkspaceAppCatalogItem(
        app_id="whiteboard",
        title="WHITEBOARD",
        route_base="/whiteboard",
        icon_key="pencil-ruler",
        nav_items=(
            WorkspaceNavCatalogItem(
                id="whiteboard-all",
                app_id="whiteboard",
                title="All Whiteboards",
                category="Library",
                icon_key="pencil-ruler",
            ),
            WorkspaceNavCatalogItem(
                id="whiteboard-my",
                app_id="whiteboard",
                title="My Whiteboards",
                category="Library",
                icon_key="user",
            ),
            WorkspaceNavCatalogItem(
                id="whiteboard-recent",
                app_id="whiteboard",
                title="Recent",
                category="Library",
                icon_key="history",
            ),
            WorkspaceNavCatalogItem(
                id="whiteboard-archived",
                app_id="whiteboard",
                title="Archived",
                category="Library",
                icon_key="history",
            ),
        ),
    ),
    WorkspaceAppCatalogItem(
        app_id="planner",
        title="Planner",
        route_base="/planner",
        icon_key="calendar",
        nav_items=(
            WorkspaceNavCatalogItem(
                id="planner-calendar",
                app_id="planner",
                title="캘린더",
                category="Schedule",
                icon_key="calendar",
            ),
            WorkspaceNavCatalogItem(
                id="planner-timeline",
                app_id="planner",
                title="타임라인",
                category="Schedule",
                icon_key="activity",
                path_suffix="?view=timeline",
            ),
        ),
    ),
    WorkspaceAppCatalogItem(
        app_id="meeting",
        title="MEETING",
        route_base="/meeting",
        icon_key="users",
        nav_items=(
            WorkspaceNavCatalogItem(
                id="meeting-upcoming",
                app_id="meeting",
                title="Upcoming",
                category="Meetings",
                icon_key="calendar",
            ),
            WorkspaceNavCatalogItem(
                id="meeting-mine",
                app_id="meeting",
                title="My Meetings",
                category="Meetings",
                icon_key="user",
                path_suffix="?scope=mine",
            ),
            WorkspaceNavCatalogItem(
                id="meeting-recordings",
                app_id="meeting",
                title="Recordings",
                category="Meetings",
                icon_key="video",
                path_suffix="?tab=recordings",
            ),
        ),
    ),
    WorkspaceAppCatalogItem(
        app_id="recording",
        title="RECORDING",
        route_base="/recording",
        icon_key="mic",
        nav_items=(
            WorkspaceNavCatalogItem(
                id="recording-quick",
                app_id="recording",
                title="Quick Record",
                category="Recordings",
                icon_key="mic",
            ),
            WorkspaceNavCatalogItem(
                id="recording-mine",
                app_id="recording",
                title="My Recordings",
                category="Recordings",
                icon_key="list-music",
                path_suffix="?view=mine",
            ),
            WorkspaceNavCatalogItem(
                id="recording-meeting",
                app_id="recording",
                title="Meeting Recordings",
                category="Recording Categories",
                icon_key="users",
                path_suffix="?view=mine&category=meeting",
            ),
            WorkspaceNavCatalogItem(
                id="recording-task",
                app_id="recording",
                title="Task Recordings",
                category="Recording Categories",
                icon_key="check-circle-2",
                path_suffix="?view=mine&category=task",
            ),
            WorkspaceNavCatalogItem(
                id="recording-unlinked",
                app_id="recording",
                title="Unlinked",
                category="Recording Categories",
                icon_key="inbox",
                path_suffix="?view=mine&category=unlinked",
            ),
            WorkspaceNavCatalogItem(
                id="recording-processing",
                app_id="recording",
                title="Processing",
                category="Recording Status",
                icon_key="clock-3",
                path_suffix="?view=processing",
            ),
            WorkspaceNavCatalogItem(
                id="recording-failed",
                app_id="recording",
                title="Failed",
                category="Recording Status",
                icon_key="alert-triangle",
                path_suffix="?view=failed",
            ),
            WorkspaceNavCatalogItem(
                id="recording-archived",
                app_id="recording",
                title="Archived",
                category="Recording Status",
                icon_key="archive",
                path_suffix="?view=archived",
            ),
        ),
    ),
    WorkspaceAppCatalogItem(
        app_id="learning",
        title="학습",
        route_base="/learning",
        icon_key="graduation-cap",
        nav_items=(
            WorkspaceNavCatalogItem(
                id="learning-all",
                app_id="learning",
                title="전체 코스",
                category="Courses",
                icon_key="graduation-cap",
            ),
        ),
    ),
)

WORKSPACE_APP_IDS = tuple(item.app_id for item in WORKSPACE_APP_CATALOG)


def iter_workspace_app_catalog() -> tuple[WorkspaceAppCatalogItem, ...]:
    return WORKSPACE_APP_CATALOG


def get_workspace_app_catalog_item(app_id: str) -> WorkspaceAppCatalogItem | None:
    for item in WORKSPACE_APP_CATALOG:
        if item.app_id == app_id:
            return item
    return None
