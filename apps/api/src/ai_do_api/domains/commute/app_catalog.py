"""근태 도메인 앱 카탈로그.

포털 앱바(런처)에 근태 앱을 노출하기 위한 등록. 여기 등록된 app_id가 프론트
app-module의 app_id와 일치해야 화면이 라우팅된다(백엔드=노출/배치, 프론트=화면).

역할별 앱(사용자/부서장/인사/근태담당자)을 개별 앱으로 추가할 예정.
1단계: 개인근태(personal-attendance) — 개인 도구(personal-tools) 카테고리.
"""

from ai_do_api.core.workspace_app_registry import (
    WorkspaceAppRegistration,
    WorkspaceNavRegistration,
)


# 페이지1 — 사용자 개인용. 개인 도구(personal-tools)에 노출.
PERSONAL_ATTENDANCE_WORKSPACE_APP = WorkspaceAppRegistration(
    app_id="personal-attendance",
    title="개인근태",
    route_base="/personal-attendance",
    icon_key="clock",
    availability_scope="platform",
    # 화면이 Mock 이고 commute API 가 없으므로 운영자가 플랫폼 가시성을 명시적으로
    # 켜기 전에는 노출하지 않는다. backend Core Enablement 후 기본값을 재검토한다.
    enabled_by_default=False,
    visible_by_default=False,
    launcher_category=False,
    launcher_personal_tools=True,
    nav_items=(
        WorkspaceNavRegistration(
            id="personal-attendance-overview",
            title="근태 현황",
            # 프론트 manifest 와 같은 kebab category key — shell:categories.attendance 로 번역된다.
            category="attendance",
            icon_key="clock",
        ),
    ),
)
