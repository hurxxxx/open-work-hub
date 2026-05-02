from __future__ import annotations

from dataclasses import dataclass, field
from string import Formatter
from typing import Any

from fastapi import HTTPException


DEFAULT_LOCALE = "ko-KR"
SUPPORTED_LOCALES = ("ko-KR", "en-US")
ERROR_CODE_HEADER = "X-Aidoo-Error-Code"


@dataclass(frozen=True)
class LocalizedApiMessage:
    code: str
    params: dict[str, Any] = field(default_factory=dict)


MESSAGES: dict[str, dict[str, str]] = {
    "auth.user_not_found": {
        "ko-KR": "사용자를 찾을 수 없습니다.",
        "en-US": "User not found.",
    },
    "auth.user_inactive": {
        "ko-KR": "사용자 계정이 비활성 상태입니다.",
        "en-US": "User account is inactive.",
    },
    "auth.not_found": {
        "ko-KR": "찾을 수 없습니다.",
        "en-US": "Not found.",
    },
    "auth.setup_already_complete": {
        "ko-KR": "초기 설정이 이미 완료되었습니다.",
        "en-US": "Initial setup is already complete.",
    },
    "auth.default_identity_seed_incomplete": {
        "ko-KR": "기본 identity seed가 완전하지 않습니다.",
        "en-US": "Default identity seed is incomplete.",
    },
    "auth.invalid_credentials": {
        "ko-KR": "이메일 또는 비밀번호가 올바르지 않습니다.",
        "en-US": "Email or password is invalid.",
    },
    "auth.no_active_admin": {
        "ko-KR": "사용 가능한 활성 관리자 계정이 없습니다.",
        "en-US": "No active administrator account is available.",
    },
    "auth.dev_account_unavailable": {
        "ko-KR": "요청한 개발 계정을 사용할 수 없습니다.",
        "en-US": "Requested development account is not available.",
    },
    "auth.current_password_invalid": {
        "ko-KR": "현재 비밀번호가 올바르지 않습니다.",
        "en-US": "Current password is invalid.",
    },
    "auth.session_not_found": {
        "ko-KR": "세션을 찾을 수 없습니다.",
        "en-US": "Session not found.",
    },
    "auth.session_invalid_or_expired": {
        "ko-KR": "세션이 유효하지 않거나 만료되었습니다.",
        "en-US": "Session is invalid or expired.",
    },
    "auth.required": {
        "ko-KR": "인증이 필요합니다.",
        "en-US": "Authentication required.",
    },
    "auth.system_role_required": {
        "ko-KR": "시스템 역할이 필요합니다: {roles}",
        "en-US": "System role required: {roles}",
    },
    "workspace.access_required": {
        "ko-KR": "워크스페이스 접근 권한이 필요합니다.",
        "en-US": "Workspace access required.",
    },
    "workspace.access_required_named": {
        "ko-KR": "워크스페이스 접근 권한이 필요합니다: {workspace}",
        "en-US": "Workspace access required: {workspace}",
    },
    "workspace.context_unavailable": {
        "ko-KR": "워크스페이스 컨텍스트를 사용할 수 없습니다.",
        "en-US": "Workspace context is not available.",
    },
    "workspace.slug_missing": {
        "ko-KR": "워크스페이스 slug가 누락되었습니다.",
        "en-US": "Missing workspace slug.",
    },
    "workspace.not_found": {
        "ko-KR": "워크스페이스를 찾을 수 없습니다.",
        "en-US": "Workspace not found.",
    },
    "workspace.membership_required": {
        "ko-KR": "워크스페이스 멤버십이 필요합니다: {workspace}",
        "en-US": "Workspace membership required: {workspace}",
    },
    "team.path_parameter_missing": {
        "ko-KR": "팀 path parameter가 누락되었습니다: {team_param}",
        "en-US": "Missing team path parameter: {team_param}",
    },
    "team.not_found": {
        "ko-KR": "팀을 찾을 수 없습니다.",
        "en-US": "Team not found.",
    },
    "team.access_required": {
        "ko-KR": "팀 접근 권한이 필요합니다.",
        "en-US": "Team access required.",
    },
    "docs.doc_not_found": {
        "ko-KR": "문서를 찾을 수 없습니다.",
        "en-US": "Doc not found.",
    },
    "docs.page_not_found": {
        "ko-KR": "페이지를 찾을 수 없습니다.",
        "en-US": "Page not found.",
    },
    "docs.workspace_slug_required": {
        "ko-KR": "워크스페이스 범위 협업 경로에는 워크스페이스 slug가 필요합니다.",
        "en-US": "Workspace-scoped collaboration routes require a workspace slug.",
    },
    "docs.invalid_yjs_state": {
        "ko-KR": "yjs_state payload가 올바르지 않습니다.",
        "en-US": "Invalid yjs_state payload.",
    },
    "docs.requests_workspace_context_required": {
        "ko-KR": "문서 요청에는 워크스페이스 컨텍스트가 필요합니다.",
        "en-US": "Docs requests require a workspace context.",
    },
    "docs.principal_workspace_mismatch": {
        "ko-KR": "문서 principal의 워크스페이스가 일치하지 않습니다.",
        "en-US": "Docs principal workspace mismatch.",
    },
    "docs.principal_user_mismatch": {
        "ko-KR": "문서 principal의 사용자가 일치하지 않습니다.",
        "en-US": "Docs principal user mismatch.",
    },
    "docs.write_user_principal_required": {
        "ko-KR": "문서 쓰기 작업에는 사용자 principal이 필요합니다.",
        "en-US": "Docs write operations require a user principal.",
    },
    "docs.parent_page_not_found": {
        "ko-KR": "부모 페이지를 찾을 수 없습니다.",
        "en-US": "Parent page not found.",
    },
    "docs.page_cannot_be_own_parent": {
        "ko-KR": "페이지를 자기 자신의 부모로 지정할 수 없습니다.",
        "en-US": "Page cannot be its own parent.",
    },
    "docs.page_parent_cycle": {
        "ko-KR": "페이지 부모 관계에 순환이 포함될 수 없습니다.",
        "en-US": "Page parent relationship cannot contain a cycle.",
    },
    "docs.container_edit_access_required": {
        "ko-KR": "컨테이너 편집 권한이 필요합니다.",
        "en-US": "Container edit access required.",
    },
    "docs.page_access_required": {
        "ko-KR": "페이지 접근 권한이 필요합니다.",
        "en-US": "Page access required.",
    },
    "docs.doc_manage_access_required": {
        "ko-KR": "문서 관리 권한이 필요합니다.",
        "en-US": "Doc manage access required.",
    },
    "docs.doc_access_required": {
        "ko-KR": "문서 접근 권한이 필요합니다.",
        "en-US": "Doc access required.",
    },
    "docs.doc_edit_access_required": {
        "ko-KR": "문서 편집 권한이 필요합니다.",
        "en-US": "Doc edit access required.",
    },
    "docs.doc_share_access_required": {
        "ko-KR": "문서 공유 권한이 필요합니다.",
        "en-US": "Doc share access required.",
    },
    "docs.owner_already_has_full_access": {
        "ko-KR": "소유자는 이미 전체 권한을 가지고 있습니다.",
        "en-US": "Owner already has full access.",
    },
    "docs.shared_users_workspace_required": {
        "ko-KR": "공유 대상 사용자는 같은 워크스페이스의 멤버여야 합니다.",
        "en-US": "Shared users must be members of the same workspace.",
    },
    "docs.shared_link_not_found": {
        "ko-KR": "공유 링크를 찾을 수 없습니다.",
        "en-US": "Shared link not found.",
    },
    "docs.room_not_found": {
        "ko-KR": "방을 찾을 수 없습니다.",
        "en-US": "Room not found.",
    },
    "docs.collaboration_actor_not_found": {
        "ko-KR": "협업 작성자를 찾을 수 없습니다.",
        "en-US": "Collaboration actor not found.",
    },
    "pms.principal_workspace_mismatch": {
        "ko-KR": "PMS principal의 워크스페이스가 일치하지 않습니다.",
        "en-US": "PMS principal workspace mismatch.",
    },
    "pms.principal_user_mismatch": {
        "ko-KR": "PMS principal의 사용자가 일치하지 않습니다.",
        "en-US": "PMS principal user mismatch.",
    },
    "pms.write_user_principal_required": {
        "ko-KR": "PMS 쓰기 작업에는 사용자 principal이 필요합니다.",
        "en-US": "PMS write operations require a user principal.",
    },
    "pms.workspace_context_unavailable": {
        "ko-KR": "PMS 워크스페이스 컨텍스트를 사용할 수 없습니다.",
        "en-US": "PMS workspace context is not available.",
    },
    "pms.space_not_found": {
        "ko-KR": "스페이스를 찾을 수 없습니다.",
        "en-US": "Space not found.",
    },
    "pms.space_access_required": {
        "ko-KR": "스페이스 접근 권한이 필요합니다.",
        "en-US": "Space access required.",
    },
    "pms.space_viewer_modify_denied": {
        "ko-KR": "뷰어 역할은 스페이스 데이터를 수정할 수 없습니다.",
        "en-US": "Viewer role cannot modify space data.",
    },
    "pms.space_owner_admin_required": {
        "ko-KR": "스페이스 소유자 또는 관리자 권한이 필요합니다.",
        "en-US": "Space owner/admin access required.",
    },
    "pms.space_owner_required": {
        "ko-KR": "스페이스 소유자 권한이 필요합니다.",
        "en-US": "Space owner access required.",
    },
    "pms.space_owner_must_remain": {
        "ko-KR": "스페이스에는 최소 한 명의 소유자가 남아 있어야 합니다.",
        "en-US": "At least one owner must remain in the space.",
    },
    "pms.space_owner_admin_manage_required": {
        "ko-KR": "소유자 또는 관리자 관리는 스페이스 소유자만 할 수 있습니다.",
        "en-US": "Only the space owner can manage owners or admins.",
    },
    "pms.user_already_space_member": {
        "ko-KR": "사용자가 이미 스페이스 멤버입니다.",
        "en-US": "User is already a space member.",
    },
    "pms.folder_not_found": {
        "ko-KR": "폴더를 찾을 수 없습니다.",
        "en-US": "Folder not found.",
    },
    "pms.folder_same_space_required": {
        "ko-KR": "폴더는 같은 스페이스에 속해야 합니다.",
        "en-US": "Folder must belong to the same space.",
    },
    "pms.folder_space_missing": {
        "ko-KR": "폴더 스페이스가 설정되어 있지 않습니다.",
        "en-US": "Folder space is not set.",
    },
    "pms.task_list_not_found": {
        "ko-KR": "태스크 리스트를 찾을 수 없습니다.",
        "en-US": "TaskList not found.",
    },
    "pms.task_list_space_missing": {
        "ko-KR": "태스크 리스트 스페이스가 설정되어 있지 않습니다.",
        "en-US": "Task list space is not set.",
    },
    "pms.task_list_access_required": {
        "ko-KR": "태스크 리스트 접근 권한이 필요합니다.",
        "en-US": "TaskList access required.",
    },
    "pms.task_list_owner_admin_required": {
        "ko-KR": "태스크 리스트 소유자 또는 관리자 권한이 필요합니다.",
        "en-US": "TaskList owner/admin access required.",
    },
    "pms.task_list_viewer_modify_denied": {
        "ko-KR": "뷰어 역할은 태스크 리스트 데이터를 수정할 수 없습니다.",
        "en-US": "Viewer role cannot modify task list data.",
    },
    "pms.user_already_task_list_member": {
        "ko-KR": "사용자가 이미 태스크 리스트 멤버입니다.",
        "en-US": "User is already a task list member.",
    },
    "pms.member_not_found": {
        "ko-KR": "멤버를 찾을 수 없습니다.",
        "en-US": "Member not found.",
    },
    "pms.duplicate_task_list_ids": {
        "ko-KR": "중복된 태스크 리스트 ID는 허용되지 않습니다.",
        "en-US": "Duplicate task list ids are not allowed.",
    },
    "pms.assignee_task_list_member_required": {
        "ko-KR": "담당자는 태스크 리스트 멤버여야 합니다.",
        "en-US": "Assignee must be a task list member.",
    },
    "pms.assignees_task_list_members_required": {
        "ko-KR": "담당자들은 태스크 리스트 멤버여야 합니다.",
        "en-US": "Assignees must be task list members.",
    },
    "pms.milestone_wrong_list": {
        "ko-KR": "마일스톤이 이 리스트에 속하지 않습니다.",
        "en-US": "Milestone does not belong to this list.",
    },
    "pms.milestone_not_found": {
        "ko-KR": "마일스톤을 찾을 수 없습니다.",
        "en-US": "Milestone not found.",
    },
    "pms.parent_issue_not_found": {
        "ko-KR": "부모 이슈를 찾을 수 없습니다.",
        "en-US": "Parent issue not found.",
    },
    "pms.parent_issue_same_list_required": {
        "ko-KR": "부모 이슈는 같은 리스트에 속해야 합니다.",
        "en-US": "Parent issue must belong to the same list.",
    },
    "pms.issue_cannot_be_own_parent": {
        "ko-KR": "이슈를 자기 자신의 부모로 지정할 수 없습니다.",
        "en-US": "Issue cannot be its own parent.",
    },
    "pms.issue_parent_cycle": {
        "ko-KR": "이슈 부모 관계에 순환이 포함될 수 없습니다.",
        "en-US": "Issue parent relationship cannot contain a cycle.",
    },
    "pms.labels_invalid_for_list": {
        "ko-KR": "하나 이상의 라벨이 이 리스트에 유효하지 않습니다.",
        "en-US": "One or more labels are invalid for this list.",
    },
    "pms.issue_not_found": {
        "ko-KR": "이슈를 찾을 수 없습니다.",
        "en-US": "Issue not found.",
    },
    "pms.issue_access_required": {
        "ko-KR": "이 이슈에 접근할 권한이 없습니다.",
        "en-US": "You do not have access to this issue.",
    },
    "pms.label_name_exists": {
        "ko-KR": "이 리스트에 같은 이름의 라벨이 이미 있습니다.",
        "en-US": "Label name already exists in this list.",
    },
    "pms.label_not_found": {
        "ko-KR": "라벨을 찾을 수 없습니다.",
        "en-US": "Label not found.",
    },
    "pms.no_matching_issues": {
        "ko-KR": "일치하는 이슈를 찾을 수 없습니다.",
        "en-US": "No matching issues found.",
    },
    "pms.dependencies_same_list_required": {
        "ko-KR": "의존성은 같은 리스트 안에 있어야 합니다.",
        "en-US": "Dependencies must stay within the same list.",
    },
    "pms.dependency_not_found": {
        "ko-KR": "의존성을 찾을 수 없습니다.",
        "en-US": "Dependency not found.",
    },
    "pms.file_size_limit_exceeded": {
        "ko-KR": "파일 크기가 {limit_mb} MB 제한을 초과했습니다.",
        "en-US": "File size exceeds {limit_mb} MB limit.",
    },
    "pms.attachment_not_found": {
        "ko-KR": "첨부파일을 찾을 수 없습니다.",
        "en-US": "Attachment not found.",
    },
    "pms.notification_not_found": {
        "ko-KR": "알림을 찾을 수 없습니다.",
        "en-US": "Notification not found.",
    },
    "pms.checklist_item_not_found": {
        "ko-KR": "체크리스트 항목을 찾을 수 없습니다.",
        "en-US": "Checklist item not found.",
    },
    "pms.time_entry_not_found": {
        "ko-KR": "시간 기록을 찾을 수 없습니다.",
        "en-US": "Time entry not found.",
    },
    "pms.status_name_exists": {
        "ko-KR": "같은 이름의 상태가 이미 있습니다.",
        "en-US": "Status with this name already exists.",
    },
    "pms.status_not_found": {
        "ko-KR": "상태를 찾을 수 없습니다.",
        "en-US": "Status not found.",
    },
    "pms.status_in_use": {
        "ko-KR": "상태를 삭제할 수 없습니다. {count}개의 이슈가 사용 중입니다.",
        "en-US": "Cannot delete status: {count} issue(s) are using it.",
    },
    "pms.template_not_found": {
        "ko-KR": "템플릿을 찾을 수 없습니다.",
        "en-US": "Template not found.",
    },
    "pms.custom_field_not_found": {
        "ko-KR": "커스텀 필드를 찾을 수 없습니다.",
        "en-US": "Custom field not found.",
    },
    "pms.custom_field_wrong_list": {
        "ko-KR": "커스텀 필드가 이 리스트에 속하지 않습니다.",
        "en-US": "Custom field does not belong to this list.",
    },
}


def normalize_locale(value: str | None) -> str:
    if not value:
        return DEFAULT_LOCALE
    normalized = value.strip()
    if normalized in SUPPORTED_LOCALES:
        return normalized
    lowered = normalized.lower()
    if lowered == "ko":
        return "ko-KR"
    if lowered == "en":
        return "en-US"
    return DEFAULT_LOCALE


def select_locale(*, explicit_locale: str | None = None, accept_language: str | None = None) -> str:
    if explicit_locale:
        return normalize_locale(explicit_locale)

    candidates: list[tuple[float, int, str]] = []
    for index, raw_part in enumerate((accept_language or "").split(",")):
        part = raw_part.strip()
        if not part:
            continue
        language, *params = [item.strip() for item in part.split(";")]
        quality = 1.0
        for param in params:
            if not param.startswith("q="):
                continue
            try:
                quality = float(param[2:])
            except ValueError:
                quality = 0.0
        if quality > 0:
            candidates.append((quality, -index, language))

    for _quality, _order, language in sorted(candidates, reverse=True):
        normalized = normalize_locale(language)
        if normalized != DEFAULT_LOCALE or language.lower().startswith("ko"):
            return normalized
    return DEFAULT_LOCALE


def translate_message(message: LocalizedApiMessage, locale: str) -> str:
    translations = MESSAGES.get(message.code)
    if translations is None:
        return message.code
    template = translations.get(normalize_locale(locale)) or translations[DEFAULT_LOCALE]
    safe_params = {
        field_name: message.params.get(field_name, "{" + field_name + "}")
        for _, field_name, _, _ in Formatter().parse(template)
        if field_name
    }
    return template.format(**safe_params)


def localized_http_exception(
    *,
    status_code: int,
    code: str,
    headers: dict[str, str] | None = None,
    **params: Any,
) -> HTTPException:
    merged_headers = {ERROR_CODE_HEADER: code}
    if headers:
        merged_headers.update(headers)
    return HTTPException(
        status_code=status_code,
        detail=LocalizedApiMessage(code=code, params=params),
        headers=merged_headers,
    )
