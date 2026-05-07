from __future__ import annotations

from dataclasses import dataclass, field
from string import Formatter
from typing import Any

from fastapi import HTTPException


DEFAULT_LOCALE = "ko-KR"
SUPPORTED_LOCALES = ("ko-KR", "en-US")
ERROR_CODE_HEADER = "X-AI-DO-Error-Code"


@dataclass(frozen=True)
class LocalizedApiMessage:
    code: str
    params: dict[str, Any] = field(default_factory=dict)


PARAM_VALUE_TRANSLATIONS: dict[str, dict[str, dict[str, str]]] = {
    "ai.approval.status": {
        "pending": {
            "ko-KR": "대기 중",
            "en-US": "pending",
        },
        "approved": {
            "ko-KR": "승인됨",
            "en-US": "approved",
        },
        "rejected": {
            "ko-KR": "거부됨",
            "en-US": "rejected",
        },
        "cancelled": {
            "ko-KR": "취소됨",
            "en-US": "cancelled",
        },
        "expired": {
            "ko-KR": "만료됨",
            "en-US": "expired",
        },
        "executed": {
            "ko-KR": "실행됨",
            "en-US": "executed",
        },
        "failed": {
            "ko-KR": "실패",
            "en-US": "failed",
        },
    },
}

MESSAGE_PARAM_VALUE_TRANSLATIONS: dict[tuple[str, str], str] = {
    ("ai.approval_already_status", "status"): "ai.approval.status",
    ("ai.tool_approval_already_status", "status"): "ai.approval.status",
    ("ai.tool_approval_no_longer_usable", "status"): "ai.approval.status",
}


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
    "auth.valid_email_required": {
        "ko-KR": "올바른 이메일 주소가 필요합니다.",
        "en-US": "A valid email address is required.",
    },
    "auth.invalid_locale": {
        "ko-KR": "locale이 올바르지 않습니다.",
        "en-US": "Invalid locale.",
    },
    "auth.invalid_time_zone": {
        "ko-KR": "time zone이 올바르지 않습니다.",
        "en-US": "Invalid time zone.",
    },
    "validation.request_invalid": {
        "ko-KR": "요청 값이 올바르지 않습니다.",
        "en-US": "Request validation failed.",
    },
    "validation.field_required": {
        "ko-KR": "필수 값입니다.",
        "en-US": "Field is required.",
    },
    "validation.value_invalid": {
        "ko-KR": "값이 올바르지 않습니다.",
        "en-US": "Value is invalid.",
    },
    "validation.string_type": {
        "ko-KR": "문자열이어야 합니다.",
        "en-US": "Value must be a string.",
    },
    "validation.integer_type": {
        "ko-KR": "정수여야 합니다.",
        "en-US": "Value must be an integer.",
    },
    "validation.float_type": {
        "ko-KR": "숫자여야 합니다.",
        "en-US": "Value must be a number.",
    },
    "validation.bool_type": {
        "ko-KR": "참/거짓 값이어야 합니다.",
        "en-US": "Value must be a boolean.",
    },
    "validation.array_type": {
        "ko-KR": "배열이어야 합니다.",
        "en-US": "Value must be an array.",
    },
    "validation.object_type": {
        "ko-KR": "객체여야 합니다.",
        "en-US": "Value must be an object.",
    },
    "validation.date_type": {
        "ko-KR": "날짜 형식이어야 합니다.",
        "en-US": "Value must be a valid date.",
    },
    "validation.datetime_type": {
        "ko-KR": "일시 형식이어야 합니다.",
        "en-US": "Value must be a valid datetime.",
    },
    "validation.string_too_short": {
        "ko-KR": "값이 너무 짧습니다. 최소 길이: {min_length}",
        "en-US": "Value is too short. Minimum length: {min_length}",
    },
    "validation.string_too_long": {
        "ko-KR": "값이 너무 깁니다. 최대 길이: {max_length}",
        "en-US": "Value is too long. Maximum length: {max_length}",
    },
    "validation.too_short": {
        "ko-KR": "항목이 너무 적습니다. 최소 개수: {min_length}",
        "en-US": "Too few items. Minimum count: {min_length}",
    },
    "validation.too_long": {
        "ko-KR": "항목이 너무 많습니다. 최대 개수: {max_length}",
        "en-US": "Too many items. Maximum count: {max_length}",
    },
    "validation.greater_than": {
        "ko-KR": "값은 {gt}보다 커야 합니다.",
        "en-US": "Value must be greater than {gt}.",
    },
    "validation.greater_than_equal": {
        "ko-KR": "값은 {ge} 이상이어야 합니다.",
        "en-US": "Value must be greater than or equal to {ge}.",
    },
    "validation.less_than": {
        "ko-KR": "값은 {lt}보다 작아야 합니다.",
        "en-US": "Value must be less than {lt}.",
    },
    "validation.less_than_equal": {
        "ko-KR": "값은 {le} 이하여야 합니다.",
        "en-US": "Value must be less than or equal to {le}.",
    },
    "validation.literal_error": {
        "ko-KR": "허용된 값이어야 합니다: {expected}",
        "en-US": "Value must be one of: {expected}",
    },
    "validation.extra_forbidden": {
        "ko-KR": "허용되지 않는 필드입니다.",
        "en-US": "Extra fields are not allowed.",
    },
    "llm.pool_disabled": {
        "ko-KR": "{pool} LLM pool이 비활성화되어 있습니다.",
        "en-US": "{pool} LLM pool is disabled.",
    },
    "llm.missing_settings": {
        "ko-KR": "{pool} LLM 설정이 누락되었습니다: {settings}",
        "en-US": "Missing LLM {pool} setting(s): {settings}",
    },
    "llm.provider_unavailable": {
        "ko-KR": "LLM provider를 사용할 수 없습니다: {reason}",
        "en-US": "LLM provider is unavailable: {reason}",
    },
    "llm.provider_status_error": {
        "ko-KR": "LLM provider 요청이 실패했습니다: {status_code}: {message}",
        "en-US": "LLM provider request failed: {status_code}: {message}",
    },
    "llm.configured_model_missing": {
        "ko-KR": "설정된 LLM model을 찾을 수 없습니다. 사용 가능한 model: {models}",
        "en-US": "Configured LLM model was not found. Available models: {models}",
    },
    "llm.policy_lookup_failed": {
        "ko-KR": "LLM 정책 조회에 실패했습니다: {reason}",
        "en-US": "LLM policy lookup failed: {reason}",
    },
    "llm.external_pool_disabled": {
        "ko-KR": "external LLM pool이 비활성화되어 있습니다.",
        "en-US": "External LLM pool is disabled.",
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
    "admin.invalid_workspace_role": {
        "ko-KR": "워크스페이스 역할이 올바르지 않습니다.",
        "en-US": "Invalid workspace role.",
    },
    "admin.user_already_exists": {
        "ko-KR": "사용자가 이미 존재합니다.",
        "en-US": "User already exists.",
    },
    "admin.self_delete_denied": {
        "ko-KR": "자기 자신의 사용자 계정은 삭제할 수 없습니다.",
        "en-US": "You cannot delete your own user account.",
    },
    "admin.user_linked_records_delete_denied": {
        "ko-KR": "사용자에 연결된 레코드가 있어 삭제할 수 없습니다.",
        "en-US": "User has linked records and cannot be deleted.",
    },
    "admin.org_unit_slug_exists": {
        "ko-KR": "조직 단위 slug가 이미 존재합니다.",
        "en-US": "Org unit slug already exists.",
    },
    "admin.org_unit_not_found": {
        "ko-KR": "조직 단위를 찾을 수 없습니다.",
        "en-US": "Org unit not found.",
    },
    "admin.group_slug_exists": {
        "ko-KR": "그룹 slug가 이미 존재합니다.",
        "en-US": "Group slug already exists.",
    },
    "admin.group_not_found": {
        "ko-KR": "그룹을 찾을 수 없습니다.",
        "en-US": "Group not found.",
    },
    "admin.workspace_key_exists": {
        "ko-KR": "워크스페이스 key가 이미 존재합니다.",
        "en-US": "Workspace key already exists.",
    },
    "admin.workspace_archive_before_delete": {
        "ko-KR": "영구 삭제 전에 워크스페이스를 먼저 보관 처리해야 합니다.",
        "en-US": "Workspace must be archived before it can be permanently deleted.",
    },
    "admin.workspace_contains_content": {
        "ko-KR": "워크스페이스에 콘텐츠가 남아 있습니다. 스페이스 {space_count}개, 회의 {meeting_count}개, 문서 {doc_count}개를 먼저 비워 주세요.",
        "en-US": "Workspace still contains content: {space_count} space(s), {meeting_count} meeting(s), {doc_count} document(s). Empty its content first.",
    },
    "admin.user_already_workspace_member": {
        "ko-KR": "사용자가 이미 이 워크스페이스의 멤버입니다.",
        "en-US": "User is already a member of this workspace.",
    },
    "admin.group_already_workspace_member": {
        "ko-KR": "그룹이 이미 이 워크스페이스의 멤버입니다.",
        "en-US": "Group is already a member of this workspace.",
    },
    "admin.workspace_member_not_found": {
        "ko-KR": "워크스페이스 멤버를 찾을 수 없습니다.",
        "en-US": "Workspace member not found.",
    },
    "admin.self_role_change_denied": {
        "ko-KR": "자기 자신의 역할은 직접 변경할 수 없습니다. 다른 관리자에게 요청해 주세요.",
        "en-US": "You cannot change your own role. Ask another admin to do it.",
    },
    "admin.self_workspace_remove_denied": {
        "ko-KR": "자기 자신은 워크스페이스에서 제거할 수 없습니다.",
        "en-US": "You cannot remove yourself from the workspace.",
    },
    "admin.invalid_workspace_role_filter": {
        "ko-KR": "워크스페이스 역할 필터가 올바르지 않습니다.",
        "en-US": "Invalid workspace role filter.",
    },
    "admin.role_required_for_add": {
        "ko-KR": "추가 작업에는 role이 필요합니다.",
        "en-US": "role is required for add.",
    },
    "admin.role_required_for_update_role": {
        "ko-KR": "역할 변경 작업에는 role이 필요합니다.",
        "en-US": "role is required for update_role.",
    },
    "admin.subject_already_member": {
        "ko-KR": "이미 멤버입니다.",
        "en-US": "Already a member.",
    },
    "admin.team_key_exists": {
        "ko-KR": "팀 key가 워크스페이스에 이미 존재합니다.",
        "en-US": "Team key already exists in workspace.",
    },
    "admin.platform_admin_required": {
        "ko-KR": "플랫폼 관리자 권한이 필요합니다.",
        "en-US": "Platform admin access required.",
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
    "learning.note_not_found": {
        "ko-KR": "학습 노트를 찾을 수 없습니다.",
        "en-US": "Learning note not found.",
    },
    "learning.my_note_not_found": {
        "ko-KR": "내 학습 노트를 찾을 수 없습니다.",
        "en-US": "My learning note not found.",
    },
    "learning.unknown_visibility": {
        "ko-KR": "알 수 없는 공개 범위입니다.",
        "en-US": "Unknown visibility.",
    },
    "learning.content_blocks_list_required": {
        "ko-KR": "content_blocks는 리스트여야 합니다.",
        "en-US": "content_blocks must be a list.",
    },
    "learning.content_block_object_required": {
        "ko-KR": "content_blocks[{index}]는 JSON 객체여야 합니다.",
        "en-US": "content_blocks[{index}] must be a JSON object.",
    },
    "learning.content_block_type_required": {
        "ko-KR": "content_blocks[{index}].type이 필요합니다.",
        "en-US": "content_blocks[{index}].type is required.",
    },
    "learning.content_blocks_not_serializable": {
        "ko-KR": "content_blocks를 JSON으로 직렬화할 수 없습니다.",
        "en-US": "content_blocks is not JSON-serializable.",
    },
    "learning.content_blocks_too_large": {
        "ko-KR": "content_blocks payload가 허용된 최대 크기를 초과했습니다.",
        "en-US": "content_blocks payload exceeds the maximum allowed size.",
    },
    "learning.note_page_missing": {
        "ko-KR": "노트에 페이지가 없습니다.",
        "en-US": "Note has no page.",
    },
    "learning.note_active_page_missing": {
        "ko-KR": "노트에 활성 페이지가 없습니다.",
        "en-US": "Note has no active page.",
    },
    "media.unsupported_file_type": {
        "ko-KR": "지원하지 않는 파일 형식입니다: {content_type}. 허용: {allowed_types}",
        "en-US": "Unsupported file type: {content_type}. Allowed: {allowed_types}",
    },
    "media.file_size_limit_exceeded": {
        "ko-KR": "파일 크기가 {limit_mb} MB 제한을 초과했습니다.",
        "en-US": "File size exceeds {limit_mb} MB limit.",
    },
    "media.create_record_failed": {
        "ko-KR": "미디어 레코드를 생성하지 못했습니다.",
        "en-US": "Failed to create media record.",
    },
    "media.storage_upload_failed": {
        "ko-KR": "스토리지 업로드에 실패했습니다.",
        "en-US": "Storage upload failed.",
    },
    "media.save_metadata_failed": {
        "ko-KR": "미디어 메타데이터를 저장하지 못했습니다.",
        "en-US": "Failed to save media metadata.",
    },
    "media.unsupported_resource_type": {
        "ko-KR": "지원하지 않는 미디어 리소스 유형입니다.",
        "en-US": "Unsupported media resource type.",
    },
    "media.task_list_space_access_required": {
        "ko-KR": "태스크 리스트 스페이스 접근 권한이 필요합니다.",
        "en-US": "Task list space access required.",
    },
    "search.keyword_backend_unavailable": {
        "ko-KR": "키워드 검색을 사용할 수 없습니다: {reason}",
        "en-US": "Keyword search is unavailable: {reason}",
    },
    "conversations.scope_pair_required": {
        "ko-KR": "scope_ref와 scope_resource_id는 함께 제공해야 합니다.",
        "en-US": "scope_ref and scope_resource_id must be provided together.",
    },
    "conversations.unsupported_scope": {
        "ko-KR": "지원하지 않는 대화 범위입니다: {scope_ref}",
        "en-US": "Unsupported conversation scope: {scope_ref}",
    },
    "conversations.cursor_missing_id": {
        "ko-KR": "cursor가 올바르지 않습니다: id 구성 요소가 없습니다.",
        "en-US": "Invalid cursor: missing id component.",
    },
    "conversations.cursor_empty_component": {
        "ko-KR": "cursor가 올바르지 않습니다: 비어 있는 구성 요소가 있습니다.",
        "en-US": "Invalid cursor: empty component.",
    },
    "conversations.cursor_invalid_timestamp": {
        "ko-KR": "cursor timestamp가 올바르지 않습니다: {error}",
        "en-US": "Invalid cursor timestamp: {error}",
    },
    "conversations.not_found": {
        "ko-KR": "대화를 찾을 수 없습니다.",
        "en-US": "Conversation not found.",
    },
    "conversations.title_empty": {
        "ko-KR": "제목은 비워둘 수 없습니다.",
        "en-US": "Title must not be empty.",
    },
    "rag.access_denied": {
        "ko-KR": "워크스페이스 RAG 접근이 거부되었습니다: {reason}",
        "en-US": "Workspace RAG access denied: {reason}",
    },
    "rag.unavailable": {
        "ko-KR": "RAG를 사용할 수 없습니다: {reason}",
        "en-US": "RAG is unavailable: {reason}",
    },
    "rag.disabled": {
        "ko-KR": "RAG가 비활성화되어 있습니다.",
        "en-US": "RAG is disabled.",
    },
    "rag.runtime_unavailable": {
        "ko-KR": "RAG 런타임을 사용할 수 없습니다: {reason}",
        "en-US": "RAG runtime is unavailable: {reason}",
    },
    "rag.query_unavailable": {
        "ko-KR": "RAG 조회를 사용할 수 없습니다: {reason}",
        "en-US": "RAG query is unavailable: {reason}",
    },
    "rag.access_denied_not_enabled": {
        "ko-KR": "이 워크스페이스에서 RAG가 활성화되어 있지 않습니다.",
        "en-US": "Workspace RAG is not enabled for this workspace.",
    },
    "rag.reindex_cooldown": {
        "ko-KR": "RAG 재색인을 지금 다시 실행할 수 없습니다: {reason}",
        "en-US": "RAG reindex cannot be retried yet: {reason}",
    },
    "rag.reindex_cooldown_recent": {
        "ko-KR": "RAG 재색인이 최근에 실행되었습니다. 몇 분 후 다시 시도하세요.",
        "en-US": "Workspace RAG reindex was triggered recently. Wait a few minutes before retrying.",
    },
    "rag.metadata_filter_key_length": {
        "ko-KR": "메타데이터 필터 key는 1~64자여야 합니다.",
        "en-US": "Metadata filter keys must be between 1 and 64 characters.",
    },
    "rag.metadata_filter_key_reserved": {
        "ko-KR": "예약된 메타데이터 필터 key입니다: {key}",
        "en-US": "Metadata filter key is reserved: {key}",
    },
    "rag.metadata_filter_key_invalid": {
        "ko-KR": "메타데이터 필터 key가 올바르지 않습니다: {key}",
        "en-US": "Invalid metadata filter key: {key}",
    },
    "rag.metadata_filter_list_empty": {
        "ko-KR": "메타데이터 필터 list는 비워둘 수 없습니다.",
        "en-US": "Metadata filter lists must not be empty.",
    },
    "rag.metadata_filter_list_scalar_required": {
        "ko-KR": "메타데이터 필터 list에는 문자열, 정수, boolean 값만 사용할 수 있습니다.",
        "en-US": "Metadata filter lists must contain only string/int/bool values.",
    },
    "rag.metadata_filter_value_invalid": {
        "ko-KR": "메타데이터 필터 값은 문자열, 정수, boolean 또는 해당 값의 list여야 합니다.",
        "en-US": "Metadata filter values must be string/int/bool or a list of those values.",
    },
    "whiteboard.workspace_slug_required": {
        "ko-KR": "워크스페이스 범위 화이트보드 협업 경로에는 워크스페이스 slug가 필요합니다.",
        "en-US": "Workspace-scoped whiteboard collaboration routes require a workspace slug.",
    },
    "whiteboard.invalid_yjs_state": {
        "ko-KR": "yjs_state payload가 올바르지 않습니다.",
        "en-US": "Invalid yjs_state payload.",
    },
    "whiteboard.workspace_context_required": {
        "ko-KR": "화이트보드 요청에는 워크스페이스 컨텍스트가 필요합니다.",
        "en-US": "Whiteboard requests require a workspace context.",
    },
    "whiteboard.not_found": {
        "ko-KR": "화이트보드를 찾을 수 없습니다.",
        "en-US": "Whiteboard not found.",
    },
    "whiteboard.shared_link_not_found": {
        "ko-KR": "공유 링크를 찾을 수 없습니다.",
        "en-US": "Shared link not found.",
    },
    "whiteboard.container_edit_access_required": {
        "ko-KR": "컨테이너 편집 권한이 필요합니다.",
        "en-US": "Container edit access required.",
    },
    "whiteboard.container_access_required": {
        "ko-KR": "컨테이너 접근 권한이 필요합니다.",
        "en-US": "Container access required.",
    },
    "whiteboard.edit_access_required": {
        "ko-KR": "화이트보드 편집 권한이 필요합니다.",
        "en-US": "Whiteboard edit access required.",
    },
    "whiteboard.manage_access_required": {
        "ko-KR": "화이트보드 관리 권한이 필요합니다.",
        "en-US": "Whiteboard manage access required.",
    },
    "whiteboard.archive_before_permanent_delete": {
        "ko-KR": "영구 삭제 전에 화이트보드를 먼저 보관 처리해야 합니다.",
        "en-US": "Archive the whiteboard before permanent deletion.",
    },
    "whiteboard.share_access_required": {
        "ko-KR": "화이트보드 공유 권한이 필요합니다.",
        "en-US": "Whiteboard share access required.",
    },
    "whiteboard.owner_already_has_full_access": {
        "ko-KR": "소유자는 이미 전체 권한을 가지고 있습니다.",
        "en-US": "Owner already has full access.",
    },
    "whiteboard.shared_users_workspace_required": {
        "ko-KR": "공유 대상 사용자는 같은 워크스페이스의 멤버여야 합니다.",
        "en-US": "Shared users must be members of the same workspace.",
    },
    "whiteboard.room_not_found": {
        "ko-KR": "방을 찾을 수 없습니다.",
        "en-US": "Room not found.",
    },
    "whiteboard.collab_relay_unavailable": {
        "ko-KR": "협업 relay를 사용할 수 없습니다.",
        "en-US": "Collaboration relay unavailable.",
    },
    "ai.tool_requires_approval": {
        "ko-KR": "AI 도구 실행 전에 승인이 필요합니다: {tool_name}",
        "en-US": "AI tool requires approval before execution: {tool_name}",
    },
    "ai.unknown_tool": {
        "ko-KR": "알 수 없는 AI 도구입니다: {tool_name}",
        "en-US": "Unknown AI tool: {tool_name}",
    },
    "ai.tool_discoverability_predicate_missing": {
        "ko-KR": "AI 도구 discoverability predicate가 등록되어 있지 않습니다: {tool_name}",
        "en-US": "AI tool discoverability predicate is not registered: {tool_name}",
    },
    "ai.tool_unavailable_in_workspace": {
        "ko-KR": "이 워크스페이스에서 AI 도구를 사용할 수 없습니다: {tool_name}",
        "en-US": "AI tool is not available in this workspace: {tool_name}",
    },
    "ai.tool_not_executable": {
        "ko-KR": "AI 도구가 등록되어 있지만 아직 실행할 수 없습니다: {tool_name}",
        "en-US": "AI tool is registered but not executable yet: {tool_name}",
    },
    "ai.invalid_tool_arguments": {
        "ko-KR": "AI 도구 인자가 올바르지 않습니다: {reason}",
        "en-US": "Invalid tool arguments: {reason}",
    },
    "ai.only_user_principal_approval_tools": {
        "ko-KR": "승인이 필요한 AI 도구는 사용자 principal만 resolve할 수 있습니다.",
        "en-US": "Only user principals can resolve approval-gated AI tools.",
    },
    "ai.tool_approval_no_longer_usable": {
        "ko-KR": "AI 도구 승인을 더 이상 사용할 수 없습니다: {status}",
        "en-US": "AI tool approval can no longer be used: {status}.",
    },
    "ai.tool_approval_already_status": {
        "ko-KR": "AI 도구 승인이 이미 {status} 상태입니다.",
        "en-US": "AI tool approval is already {status}.",
    },
    "ai.approval_tool_mismatch": {
        "ko-KR": "승인이 요청한 도구와 일치하지 않습니다.",
        "en-US": "Approval does not match the requested tool.",
    },
    "ai.approval_tool_call_mismatch": {
        "ko-KR": "승인이 요청한 도구 호출과 일치하지 않습니다.",
        "en-US": "Approval does not match the requested tool call.",
    },
    "ai.approval_not_found": {
        "ko-KR": "승인을 찾을 수 없습니다.",
        "en-US": "Approval not found.",
    },
    "ai.approval_different_user": {
        "ko-KR": "승인이 다른 사용자에게 속해 있습니다.",
        "en-US": "Approval belongs to a different user.",
    },
    "ai.agent_run_snapshot_not_found": {
        "ko-KR": "Agent run snapshot을 찾을 수 없습니다.",
        "en-US": "Agent run snapshot not found.",
    },
    "ai.agent_run_snapshot_not_awaiting_approval": {
        "ko-KR": "Agent run snapshot이 승인 대기 상태가 아닙니다.",
        "en-US": "Agent run snapshot is not awaiting approval.",
    },
    "ai.approval_expired": {
        "ko-KR": "승인이 만료되었습니다.",
        "en-US": "Approval has expired.",
    },
    "ai.approval_already_status": {
        "ko-KR": "승인이 이미 {status} 상태입니다.",
        "en-US": "Approval is already {status}.",
    },
    "ai.resume_scope_wider": {
        "ko-KR": "resume 범위는 승인된 agent run 범위보다 넓을 수 없습니다.",
        "en-US": "Resume scope cannot be wider than the approved agent run scope.",
    },
    "ai.resume_scope_excludes_approved_tool": {
        "ko-KR": "resume 범위에서 승인된 도구를 제외할 수 없습니다.",
        "en-US": "Resume scope cannot exclude the approved tool.",
    },
    "ai.approval_conversation_mismatch": {
        "ko-KR": "승인이 요청한 대화에 속하지 않습니다.",
        "en-US": "Approval does not belong to the requested conversation.",
    },
    "ai.approval_resume_requires_resolution": {
        "ko-KR": "resume 전에 승인을 먼저 resolve해야 합니다.",
        "en-US": "Approval must be resolved before resume.",
    },
    "ai.approval_resume_unavailable": {
        "ko-KR": "승인을 더 이상 resume할 수 없습니다.",
        "en-US": "Approval can no longer be resumed.",
    },
    "ai.agent_run_already_resuming": {
        "ko-KR": "Agent run이 이미 resume 중입니다.",
        "en-US": "Agent run is already being resumed.",
    },
    "ai.agent_run_snapshot_not_resumable": {
        "ko-KR": "Agent run snapshot을 더 이상 resume할 수 없습니다.",
        "en-US": "Agent run snapshot is no longer resumable.",
    },
    "ai.runtime_run_not_found": {
        "ko-KR": "Runtime run을 찾을 수 없습니다.",
        "en-US": "Runtime run not found.",
    },
    "ai.workspace_context_missing": {
        "ko-KR": "요청의 워크스페이스 컨텍스트가 누락되었습니다.",
        "en-US": "Workspace context is missing on the request.",
    },
    "ai.mcp_bridge_inspection_disabled": {
        "ko-KR": "AI MCP bridge inspection endpoint가 비활성화되어 있습니다.",
        "en-US": "AI MCP bridge inspection endpoints are disabled.",
    },
    "ai.unknown_workspace_app": {
        "ko-KR": "알 수 없는 워크스페이스 앱입니다: {app_id}",
        "en-US": "Unknown workspace app: {app_id}",
    },
    "ai.tool_command_syntax": {
        "ko-KR": "AI 도구 명령 형식: /tool <tool_name> {{\"arg\":\"value\"}}",
        "en-US": "Tool command syntax: /tool <tool_name> {{\"arg\":\"value\"}}",
    },
    "ai.invalid_tool_argument_json": {
        "ko-KR": "AI 도구 인자 JSON이 올바르지 않습니다: {error}",
        "en-US": "Invalid tool argument JSON: {error}",
    },
    "ai.tool_arguments_object_required": {
        "ko-KR": "AI 도구 인자는 JSON 객체로 해석되어야 합니다.",
        "en-US": "Tool arguments must decode to a JSON object.",
    },
    "ai.local_llm_pool_unavailable_override": {
        "ko-KR": "요청한 override에 사용할 로컬 LLM pool이 없습니다: {error}",
        "en-US": "Local LLM pool unavailable for the requested override: {error}",
    },
    "ai.llm_pool_unavailable_policy": {
        "ko-KR": "정책으로 결정된 LLM pool을 사용할 수 없습니다: {error}",
        "en-US": "LLM pool unavailable for the resolved policy: {error}",
    },
    "ai.configured_llm_model_required": {
        "ko-KR": "설정된 LLM model만 사용할 수 있습니다. 품질 관리를 위해 {canonical_model}을 사용하세요.",
        "en-US": "Only the configured LLM model is allowed. Use {canonical_model} for quality control.",
    },
    "ai.openrouter_backend_mode_unsupported": {
        "ko-KR": "backend_mode=openrouter는 더 이상 지원하지 않습니다. 정책 기반 라우팅에는 auto를, 로컬 pool 고정에는 local을 사용하세요.",
        "en-US": "backend_mode=openrouter is no longer supported. Use auto for policy-based routing or local to pin the local pool.",
    },
    "ai.unsupported_conversation_scope": {
        "ko-KR": "지원하지 않는 AI 대화 scope입니다: {scope_ref}",
        "en-US": "Unsupported AI conversation scope: {scope_ref}",
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
    "pms.update_mutable_field_required": {
        "ko-KR": "PMS 이슈 업데이트에는 변경할 필드를 하나 이상 제공해야 합니다.",
        "en-US": "PMS issue updates must provide at least one mutable field.",
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
    "calendar.invalid_iso_datetime": {
        "ko-KR": "ISO 날짜/시간이 올바르지 않습니다: {error}",
        "en-US": "Invalid ISO date/datetime: {error}",
    },
    "calendar.range_to_after_from": {
        "ko-KR": "범위의 'to'는 'from'보다 이후여야 합니다.",
        "en-US": "Range 'to' must be strictly after 'from'.",
    },
    "calendar.range_too_large": {
        "ko-KR": "범위가 최대 {days}일을 초과했습니다.",
        "en-US": "Range exceeds maximum {days} days.",
    },
    "calendar.unknown_source_types": {
        "ko-KR": "알 수 없는 소스 유형입니다: {source_types}",
        "en-US": "Unknown source types: {source_types}",
    },
    "planner.principal_workspace_mismatch": {
        "ko-KR": "Planner principal의 워크스페이스가 일치하지 않습니다.",
        "en-US": "Planner principal workspace mismatch.",
    },
    "planner.principal_user_mismatch": {
        "ko-KR": "Planner principal의 사용자가 일치하지 않습니다.",
        "en-US": "Planner principal user mismatch.",
    },
    "planner.write_user_principal_required": {
        "ko-KR": "Planner 쓰기 작업에는 사용자 principal이 필요합니다.",
        "en-US": "Planner write operations require a user principal.",
    },
    "planner.all_day_date_required": {
        "ko-KR": "종일 Planner 이벤트에는 YYYY-MM-DD 형식의 시작/종료일이 필요합니다.",
        "en-US": "All-day planner events require YYYY-MM-DD start/end.",
    },
    "planner.event_end_after_start": {
        "ko-KR": "Planner 이벤트 종료 시각은 시작 시각보다 이후여야 합니다.",
        "en-US": "Planner event end must be after start.",
    },
    "planner.timed_datetime_required": {
        "ko-KR": "시간 지정 Planner 이벤트에는 ISO datetime 시작/종료 시각이 필요합니다.",
        "en-US": "Timed planner events require ISO datetime start/end.",
    },
    "planner.event_not_found": {
        "ko-KR": "Planner 이벤트를 찾을 수 없습니다.",
        "en-US": "Planner event not found.",
    },
    "planner.owner_modify_required": {
        "ko-KR": "이 Planner 이벤트는 이벤트 소유자만 수정할 수 있습니다.",
        "en-US": "Only the event owner can modify this planner event.",
    },
    "planner.team_scope_unsupported": {
        "ko-KR": "팀 범위 Planner 이벤트는 아직 지원하지 않습니다.",
        "en-US": "Team-scoped planner events are not supported yet.",
    },
    "planner.team_id_unsupported": {
        "ko-KR": "Planner team_id는 아직 지원하지 않습니다.",
        "en-US": "Planner team_id is not supported yet.",
    },
    "planner.update_start_at_end_at_required": {
        "ko-KR": "Planner 이벤트 업데이트에는 start_at과 end_at을 함께 제공해야 합니다.",
        "en-US": "Planner event updates must provide both start_at and end_at together.",
    },
    "planner.update_mutable_field_required": {
        "ko-KR": "Planner 이벤트 업데이트에는 변경할 필드를 하나 이상 제공해야 합니다.",
        "en-US": "Planner event updates must provide at least one mutable field.",
    },
    "planner.list_range_required": {
        "ko-KR": "Planner 이벤트 목록에는 'from'과 'to'를 함께 제공해야 합니다.",
        "en-US": "Planner event list requires both 'from' and 'to' together.",
    },
    "planner.update_start_end_required": {
        "ko-KR": "Planner 이벤트 업데이트에는 start와 end를 함께 제공해야 합니다.",
        "en-US": "Planner event updates must provide both start and end together.",
    },
    "meeting.invalid_iso_datetime": {
        "ko-KR": "ISO 날짜/시간이 올바르지 않습니다: {error}",
        "en-US": "Invalid ISO date/datetime: {error}",
    },
    "meeting.invalid_iso_datetime_for_field": {
        "ko-KR": "'{field}'의 ISO 날짜/시간이 올바르지 않습니다: {error}",
        "en-US": "Invalid ISO date/datetime for '{field}': {error}",
    },
    "meeting.range_to_after_from": {
        "ko-KR": "범위의 'to'는 'from'보다 이후여야 합니다.",
        "en-US": "Range 'to' must be strictly after 'from'.",
    },
    "meeting.availability_range_too_large": {
        "ko-KR": "가능 시간 조회 범위는 최대 {days}일을 초과할 수 없습니다.",
        "en-US": "Availability range exceeds maximum {days} days.",
    },
    "meeting.principal_workspace_mismatch": {
        "ko-KR": "Meeting principal의 워크스페이스가 일치하지 않습니다.",
        "en-US": "Meeting principal workspace mismatch.",
    },
    "meeting.principal_user_mismatch": {
        "ko-KR": "Meeting principal의 사용자가 일치하지 않습니다.",
        "en-US": "Meeting principal user mismatch.",
    },
    "meeting.end_after_start": {
        "ko-KR": "end_at은 start_at보다 이후여야 합니다.",
        "en-US": "end_at must be after start_at.",
    },
    "meeting.write_user_principal_required": {
        "ko-KR": "Meeting 쓰기 작업에는 사용자 principal이 필요합니다.",
        "en-US": "Meeting write operations require a user principal.",
    },
    "meeting.unknown_attendees": {
        "ko-KR": "알 수 없거나 비활성인 참석자 사용자입니다: {user_ids}",
        "en-US": "Unknown or inactive attendee user(s): {user_ids}",
    },
    "meeting.attendees_workspace_required": {
        "ko-KR": "참석자는 회의 워크스페이스에 속해야 합니다: {user_ids}",
        "en-US": "Attendees must belong to the meeting workspace: {user_ids}",
    },
    "meeting.not_found": {
        "ko-KR": "회의를 찾을 수 없습니다.",
        "en-US": "Meeting not found.",
    },
    "meeting.access_required": {
        "ko-KR": "이 회의에 접근할 권한이 없습니다.",
        "en-US": "You do not have access to this meeting.",
    },
    "meeting.location_unsupported": {
        "ko-KR": "회의 위치는 아직 지원하지 않습니다.",
        "en-US": "Meeting location is not supported yet.",
    },
    "meeting.unsupported_scope": {
        "ko-KR": "지원하지 않는 범위입니다: {scope}",
        "en-US": "Unsupported scope: {scope}",
    },
    "meeting.requested_users_workspace_required": {
        "ko-KR": "요청한 사용자는 회의 워크스페이스에 속해야 합니다: {user_ids}",
        "en-US": "Requested users must belong to the meeting workspace: {user_ids}",
    },
    "meeting.file_size_limit_exceeded": {
        "ko-KR": "파일 크기가 {limit_mb} MB 제한을 초과했습니다.",
        "en-US": "File size exceeds {limit_mb} MB limit.",
    },
    "meeting.file_attachment_not_found": {
        "ko-KR": "파일 첨부를 찾을 수 없습니다.",
        "en-US": "File attachment not found.",
    },
    "meeting.only_organizer": {
        "ko-KR": "회의 주최자만 이 작업을 수행할 수 있습니다.",
        "en-US": "Only the meeting organizer can perform this action.",
    },
    "meeting.only_participants": {
        "ko-KR": "회의 참가자만 이 작업을 수행할 수 있습니다.",
        "en-US": "Only meeting participants can perform this action.",
    },
    "meeting.attachment_remove_permission": {
        "ko-KR": "회의 주최자 또는 첨부를 추가한 사용자만 삭제할 수 있습니다.",
        "en-US": "Only the meeting organizer or the user who added the attachment can remove it.",
    },
    "meeting.document_not_found": {
        "ko-KR": "문서를 찾을 수 없습니다.",
        "en-US": "Document not found.",
    },
    "meeting.document_access_required": {
        "ko-KR": "이 문서에 접근할 권한이 없습니다.",
        "en-US": "You do not have access to this document.",
    },
    "meeting.recording_not_found": {
        "ko-KR": "회의 녹화를 찾을 수 없습니다.",
        "en-US": "Meeting recording not found.",
    },
    "meeting.recording_in_progress": {
        "ko-KR": "이미 {recorder_name} 님이 녹음 중입니다.",
        "en-US": "A recording is already in progress by {recorder_name}.",
    },
    "meeting.recording_summary_unavailable": {
        "ko-KR": "회의 녹화 요약을 아직 사용할 수 없습니다.",
        "en-US": "Meeting recording summary is not available yet.",
    },
    "meeting.unsupported_recording_audio_format": {
        "ko-KR": "지원하지 않는 녹화 오디오 형식입니다.",
        "en-US": "Unsupported recording audio format.",
    },
    "meeting.recording_staging_not_found": {
        "ko-KR": "녹화 staging을 찾을 수 없습니다.",
        "en-US": "Recording staging not found.",
    },
    "meeting.linked_task_attached_required": {
        "ko-KR": "연결할 태스크는 먼저 회의에 첨부되어 있어야 합니다.",
        "en-US": "Linked task must already be attached to the meeting.",
    },
    "meeting.chunk_sequence_non_negative": {
        "ko-KR": "청크 순서는 0 이상이어야 합니다.",
        "en-US": "Chunk sequence must be non-negative.",
    },
    "meeting.uploader_resume_required": {
        "ko-KR": "업로더만 이 staging을 재개할 수 있습니다.",
        "en-US": "Only the uploader can resume this staging.",
    },
    "meeting.recording_staging_finalized": {
        "ko-KR": "녹화 staging이 이미 완료되었습니다.",
        "en-US": "Recording staging is already finalized.",
    },
    "meeting.empty_recording_chunk": {
        "ko-KR": "녹화 청크가 비어 있습니다.",
        "en-US": "Empty recording chunk.",
    },
    "meeting.chunk_checksum_mismatch": {
        "ko-KR": "청크 체크섬이 일치하지 않습니다.",
        "en-US": "Chunk checksum mismatch.",
    },
    "meeting.recording_size_limit_exceeded": {
        "ko-KR": "녹화가 설정된 크기 제한을 초과했습니다.",
        "en-US": "Recording exceeds the configured size limit.",
    },
    "meeting.chunk_payload_conflict": {
        "ko-KR": "청크 payload가 기존 순서와 충돌합니다.",
        "en-US": "Chunk payload conflicts with existing sequence.",
    },
    "meeting.uploader_discard_required": {
        "ko-KR": "업로더만 이 staging을 폐기할 수 있습니다.",
        "en-US": "Only the uploader can discard this staging.",
    },
    "meeting.finalized_staging_discard_denied": {
        "ko-KR": "완료된 녹화 staging은 폐기할 수 없습니다.",
        "en-US": "Finalized recording staging cannot be discarded.",
    },
    "meeting.no_recording_chunks_to_finalize": {
        "ko-KR": "완료할 업로드 청크가 없습니다.",
        "en-US": "No uploaded chunks to finalize.",
    },
    "meeting.recording_chunks_incomplete": {
        "ko-KR": "녹화 청크가 완전하지 않습니다.",
        "en-US": "Recording chunks are incomplete.",
    },
    "meeting.uploader_finalize_required": {
        "ko-KR": "업로더만 이 녹화를 완료할 수 있습니다.",
        "en-US": "Only the uploader can finalize this recording.",
    },
    "meeting.uploaded_recording_empty": {
        "ko-KR": "업로드한 녹화 파일이 비어 있습니다.",
        "en-US": "Uploaded recording file is empty.",
    },
    "meeting.recording_unavailable": {
        "ko-KR": "녹화를 사용할 수 없습니다.",
        "en-US": "Recording is not available.",
    },
    "meeting.only_failed_recordings_retry": {
        "ko-KR": "실패한 녹화만 다시 시도할 수 있습니다.",
        "en-US": "Only failed recordings can be retried.",
    },
    "meeting.recording_delete_permission": {
        "ko-KR": "회의 주최자 또는 녹화 업로더만 이 녹화를 삭제할 수 있습니다.",
        "en-US": "Only the meeting organizer or the recording uploader can delete this recording.",
    },
    "meeting.uploader_read_staging_required": {
        "ko-KR": "업로더만 이 staging을 읽을 수 있습니다.",
        "en-US": "Only the uploader can read this staging.",
    },
    "recording.not_found": {
        "ko-KR": "녹음을 찾을 수 없습니다.",
        "en-US": "Recording not found.",
    },
    "recording.access_required": {
        "ko-KR": "이 녹음에 접근할 권한이 없습니다.",
        "en-US": "You do not have access to this recording.",
    },
    "recording.owner_required": {
        "ko-KR": "녹음 소유자만 이 작업을 수행할 수 있습니다.",
        "en-US": "Only the recording owner can perform this action.",
    },
    "recording.container_filter_required": {
        "ko-KR": "첨부 대상 필터에는 app, type, id가 모두 필요합니다.",
        "en-US": "Container filters require app, type, and id.",
    },
    "recording.container_access_required": {
        "ko-KR": "첨부 대상에 접근할 권한이 없습니다.",
        "en-US": "You do not have access to the attached object.",
    },
    "recording.container_attach_required": {
        "ko-KR": "이 대상에 녹음을 첨부할 권한이 없습니다.",
        "en-US": "You do not have permission to attach a recording to this object.",
    },
    "recording.container_detach_required": {
        "ko-KR": "이 대상에서 녹음을 해제할 권한이 없습니다.",
        "en-US": "You do not have permission to detach the recording from this object.",
    },
    "recording.container_not_found": {
        "ko-KR": "녹음 첨부 대상을 찾을 수 없습니다.",
        "en-US": "Recording container not found.",
    },
    "recording.audio_unavailable": {
        "ko-KR": "원본 음성을 사용할 수 없습니다.",
        "en-US": "Original audio is not available.",
    },
    "recording.processing_in_progress": {
        "ko-KR": "녹음 후속 처리가 이미 진행 중입니다.",
        "en-US": "Recording background processing is already in progress.",
    },
    "recording.processing_already_done": {
        "ko-KR": "녹음 후속 처리가 이미 완료되었습니다.",
        "en-US": "Recording background processing is already complete.",
    },
    "recording.unsupported_audio_format": {
        "ko-KR": "지원하지 않는 녹음 오디오 형식입니다.",
        "en-US": "Unsupported recording audio format.",
    },
    "recording.uploaded_audio_empty": {
        "ko-KR": "업로드한 녹음 파일이 비어 있습니다.",
        "en-US": "Uploaded recording file is empty.",
    },
    "recording.size_limit_exceeded": {
        "ko-KR": "녹음이 설정된 크기 제한을 초과했습니다.",
        "en-US": "Recording exceeds the configured size limit.",
    },
    "recording.invalid_duration": {
        "ko-KR": "녹음 길이는 0 이상이어야 합니다.",
        "en-US": "Recording duration must be non-negative.",
    },
    "recording.staging_not_found": {
        "ko-KR": "녹음 업로드 세션을 찾을 수 없습니다.",
        "en-US": "Recording upload session not found.",
    },
    "recording.chunk_sequence_non_negative": {
        "ko-KR": "청크 순번은 0 이상이어야 합니다.",
        "en-US": "Chunk sequence must be non-negative.",
    },
    "recording.uploader_resume_required": {
        "ko-KR": "업로더만 이 녹음 업로드를 이어갈 수 있습니다.",
        "en-US": "Only the uploader can resume this recording upload.",
    },
    "recording.staging_finalized": {
        "ko-KR": "이미 완료된 녹음 업로드입니다.",
        "en-US": "This recording upload is already finalized.",
    },
    "recording.empty_chunk": {
        "ko-KR": "녹음 청크가 비어 있습니다.",
        "en-US": "Recording chunk is empty.",
    },
    "recording.chunk_checksum_mismatch": {
        "ko-KR": "녹음 청크 체크섬이 일치하지 않습니다.",
        "en-US": "Recording chunk checksum does not match.",
    },
    "recording.chunk_payload_conflict": {
        "ko-KR": "같은 순번의 녹음 청크 내용이 다릅니다.",
        "en-US": "Recording chunk payload conflicts with an existing chunk.",
    },
    "recording.uploader_discard_required": {
        "ko-KR": "업로더만 이 녹음 업로드를 폐기할 수 있습니다.",
        "en-US": "Only the uploader can discard this recording upload.",
    },
    "recording.finalized_staging_discard_denied": {
        "ko-KR": "완료된 녹음 업로드는 폐기할 수 없습니다.",
        "en-US": "Finalized recording uploads cannot be discarded.",
    },
    "recording.no_chunks_to_finalize": {
        "ko-KR": "완료할 녹음 청크가 없습니다.",
        "en-US": "No recording chunks are available to finalize.",
    },
    "recording.chunks_incomplete": {
        "ko-KR": "녹음 청크가 누락되어 완료할 수 없습니다.",
        "en-US": "Recording chunks are incomplete.",
    },
    "recording.uploader_finalize_required": {
        "ko-KR": "업로더만 이 녹음 업로드를 완료할 수 있습니다.",
        "en-US": "Only the uploader can finalize this recording upload.",
    },
    "images.feature_disabled": {
        "ko-KR": "이미지 위저드 기능이 비활성화되어 있습니다.",
        "en-US": "The image wizard feature is not enabled.",
    },
    "images.not_found": {
        "ko-KR": "이미지 작업을 찾을 수 없습니다.",
        "en-US": "Image generation not found.",
    },
    "images.forbidden": {
        "ko-KR": "이 이미지 작업에 접근할 권한이 없습니다.",
        "en-US": "You do not have access to this image generation.",
    },
    "images.locked_after_approval": {
        "ko-KR": "승인된 작업은 더 이상 수정할 수 없습니다.",
        "en-US": "Approved generations can no longer be modified.",
    },
    "images.invalid_role": {
        "ko-KR": "참고 이미지 역할이 올바르지 않습니다.",
        "en-US": "Reference image role is invalid.",
    },
    "images.empty_upload": {
        "ko-KR": "업로드된 파일이 비어 있습니다.",
        "en-US": "Uploaded file is empty.",
    },
    "images.upload_too_large": {
        "ko-KR": "이미지 파일이 허용된 크기를 초과합니다.",
        "en-US": "Image file exceeds the allowed size.",
    },
    "images.invalid_content_type": {
        "ko-KR": "이미지 파일만 업로드할 수 있습니다.",
        "en-US": "Only image files are allowed.",
    },
    "images.too_many_refs": {
        "ko-KR": "참고 이미지 개수 한도를 초과했습니다.",
        "en-US": "Reference image limit reached.",
    },
    "images.upload_failed": {
        "ko-KR": "참고 이미지를 저장하지 못했습니다.",
        "en-US": "Failed to store the reference image.",
    },
    "images.ref_not_found": {
        "ko-KR": "참고 이미지를 찾을 수 없습니다.",
        "en-US": "Reference image not found.",
    },
    "images.brief_failed": {
        "ko-KR": "이미지 계획 생성에 실패했습니다.",
        "en-US": "Failed to generate the image plan.",
    },
    "images.brief_empty": {
        "ko-KR": "LLM이 빈 이미지 계획을 반환했습니다.",
        "en-US": "The LLM returned an empty image plan.",
    },
    "images.brief_not_ready": {
        "ko-KR": "승인하려면 먼저 이미지 계획을 생성해야 합니다.",
        "en-US": "Generate an image plan before approving.",
    },
    "images.already_running": {
        "ko-KR": "이미지 생성이 이미 진행 중입니다.",
        "en-US": "Image generation is already in progress.",
    },
    "images.not_running": {
        "ko-KR": "진행 중인 이미지 생성이 없습니다.",
        "en-US": "No image generation is in progress.",
    },
    "images.dispatch_failed": {
        "ko-KR": "이미지 생성을 큐에 전달하지 못했습니다.",
        "en-US": "Failed to dispatch the image generation task.",
    },
    "images.not_ready": {
        "ko-KR": "이미지가 아직 준비되지 않았습니다.",
        "en-US": "Image is not ready yet.",
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
    normalized_locale = normalize_locale(locale)
    template = translations.get(normalized_locale) or translations[DEFAULT_LOCALE]
    safe_params = {
        field_name: translate_param_value(
            message.code,
            field_name,
            message.params.get(field_name, "{" + field_name + "}"),
            normalized_locale,
        )
        for _, field_name, _, _ in Formatter().parse(template)
        if field_name
    }
    return template.format(**safe_params)


def translate_param_value(
    message_code: str,
    field_name: str,
    value: Any,
    locale: str,
) -> Any:
    translation_key = MESSAGE_PARAM_VALUE_TRANSLATIONS.get((message_code, field_name))
    if translation_key is None or not isinstance(value, str):
        return value
    translations = PARAM_VALUE_TRANSLATIONS.get(translation_key, {}).get(value)
    if translations is None:
        return value
    return translations.get(normalize_locale(locale)) or translations[DEFAULT_LOCALE]


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
