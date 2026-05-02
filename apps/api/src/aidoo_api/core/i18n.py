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
    "rag.reindex_cooldown": {
        "ko-KR": "RAG 재색인을 지금 다시 실행할 수 없습니다: {reason}",
        "en-US": "RAG reindex cannot be retried yet: {reason}",
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
