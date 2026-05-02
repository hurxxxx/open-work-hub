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
