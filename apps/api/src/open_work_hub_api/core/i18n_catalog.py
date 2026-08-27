from __future__ import annotations

from dataclasses import dataclass, field
from string import Formatter
from typing import Any

DEFAULT_LOCALE = "ko-KR"
SUPPORTED_LOCALES = ("ko-KR", "en-US")
ERROR_CODE_HEADER = "X-Open-Work-Hub-Error-Code"


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
    "organization.unit_not_found": {
        "ko-KR": "조직 단위를 찾을 수 없습니다.",
        "en-US": "Organization unit not found.",
    },
    "organization.unit_inactive": {
        "ko-KR": "비활성 조직 단위에는 사용자를 배정할 수 없습니다.",
        "en-US": "Users cannot be assigned to an inactive organization unit.",
    },
    "organization.slug_exists": {
        "ko-KR": "이미 사용 중인 조직 식별자입니다.",
        "en-US": "This organization identifier is already in use.",
    },
    "organization.cycle_detected": {
        "ko-KR": "조직 계층에 순환 관계를 만들 수 없습니다.",
        "en-US": "Organization hierarchy cannot contain a cycle.",
    },
    "organization.filter_conflict": {
        "ko-KR": "조직 필터와 미소속 필터를 동시에 사용할 수 없습니다.",
        "en-US": "Organization and unassigned filters cannot be used together.",
    },
    "platform_api_key.required": {
        "ko-KR": "플랫폼 API 키가 필요합니다.",
        "en-US": "A platform API key is required.",
    },
    "platform_api_key.invalid": {
        "ko-KR": "플랫폼 API 키가 유효하지 않습니다.",
        "en-US": "Platform API key is invalid.",
    },
    "platform_api_key.scope_required": {
        "ko-KR": "이 작업에는 {scope} 범위가 필요합니다.",
        "en-US": "This operation requires the {scope} scope.",
    },
    "platform_api_key.scope_invalid": {
        "ko-KR": "플랫폼 API 키 범위가 유효하지 않습니다.",
        "en-US": "Platform API key scope is invalid.",
    },
    "platform_api_key.encryption_unavailable": {
        "ko-KR": "플랫폼 API 키 암호화 설정을 사용할 수 없습니다.",
        "en-US": "Platform API key encryption is unavailable.",
    },
    "platform_api_key.not_found": {
        "ko-KR": "플랫폼 API 키를 찾을 수 없습니다.",
        "en-US": "Platform API key not found.",
    },
    "platform_api_key.inactive": {
        "ko-KR": "활성 상태가 아닌 플랫폼 API 키입니다.",
        "en-US": "Platform API key is not active.",
    },
    "platform_api_key.issue_failed": {
        "ko-KR": "플랫폼 API 키를 발급할 수 없습니다.",
        "en-US": "Platform API key could not be issued.",
    },
    "platform_api_key.name_required": {
        "ko-KR": "플랫폼 API 키 이름이 필요합니다.",
        "en-US": "Platform API key name is required.",
    },
    "platform_api_key.name_invalid": {
        "ko-KR": "플랫폼 API 키 이름이 유효하지 않습니다.",
        "en-US": "Platform API key name is invalid.",
    },
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
    "platform.app_disabled": {
        "ko-KR": "관리자에 의해 비활성화된 앱입니다.",
        "en-US": "This app has been disabled by an administrator.",
    },
    "agent_terminal.disabled": {
        "ko-KR": "Codex 터미널이 서버에서 활성화되지 않았습니다.",
        "en-US": "The Codex terminal is not enabled on this server.",
    },
    "agent_terminal.runtime_unavailable": {
        "ko-KR": "Codex 터미널 런타임을 사용할 수 없습니다.",
        "en-US": "The Codex terminal runtime is unavailable.",
    },
    "agent_terminal.codex_unavailable": {
        "ko-KR": "서버에서 Codex CLI 실행 파일을 찾을 수 없습니다.",
        "en-US": "The Codex CLI executable is unavailable on the server.",
    },
    "agent_terminal.tmux_unavailable": {
        "ko-KR": "서버에서 tmux 실행 파일을 찾을 수 없습니다.",
        "en-US": "The tmux executable is unavailable on the server.",
    },
    "agent_terminal.tmux_session_lost": {
        "ko-KR": "유지 중이던 tmux 터미널 세션을 찾을 수 없습니다.",
        "en-US": "The persisted tmux terminal session could not be found.",
    },
    "agent_terminal.root_config_invalid": {
        "ko-KR": "허용된 작업 경로 설정이 올바르지 않습니다.",
        "en-US": "The allowed working-root configuration is invalid.",
    },
    "agent_terminal.root_unavailable": {
        "ko-KR": "설정된 작업 경로를 사용할 수 없습니다.",
        "en-US": "A configured working root is unavailable.",
    },
    "agent_terminal.root_not_found": {
        "ko-KR": "허용된 작업 경로를 찾을 수 없습니다.",
        "en-US": "The requested allowed working root was not found.",
    },
    "agent_terminal.session_limit": {
        "ko-KR": "동시에 실행할 수 있는 Codex 세션 수를 초과했습니다.",
        "en-US": "The concurrent Codex session limit has been reached.",
    },
    "agent_terminal.session_not_found": {
        "ko-KR": "Codex 터미널 세션을 찾을 수 없습니다.",
        "en-US": "The Codex terminal session was not found.",
    },
    "agent_terminal.session_not_local": {
        "ko-KR": "이 API 프로세스에서는 해당 세션에 연결할 수 없습니다.",
        "en-US": "This API process cannot attach to that session.",
    },
    "agent_terminal.session_closed": {
        "ko-KR": "Codex 터미널 세션이 이미 종료되었습니다.",
        "en-US": "The Codex terminal session has already ended.",
    },
    "agent_terminal.session_active": {
        "ko-KR": "실행 중인 Codex 터미널 세션은 먼저 종료해야 합니다.",
        "en-US": "Stop the active Codex terminal session before deleting it.",
    },
    "agent_terminal.start_failed": {
        "ko-KR": "Codex 터미널 세션을 시작하지 못했습니다.",
        "en-US": "The Codex terminal session could not be started.",
    },
    "agent_terminal.input_too_large": {
        "ko-KR": "터미널 입력이 허용된 크기를 초과했습니다.",
        "en-US": "The terminal input exceeds the allowed size.",
    },
    "agent_terminal.size_invalid": {
        "ko-KR": "터미널 크기가 허용 범위를 벗어났습니다.",
        "en-US": "The terminal size is outside the allowed range.",
    },
    "agent_terminal.message_invalid": {
        "ko-KR": "터미널 메시지 형식이 올바르지 않습니다.",
        "en-US": "The terminal message is invalid.",
    },
    "agent_terminal.git_unavailable": {
        "ko-KR": "서버에서 Git 실행 파일을 찾을 수 없습니다.",
        "en-US": "The Git executable is unavailable on the server.",
    },
    "agent_terminal.git_repository_unavailable": {
        "ko-KR": "선택한 작업 경로는 Git 저장소 루트가 아닙니다.",
        "en-US": "The selected working root is not a Git repository root.",
    },
    "agent_terminal.git_change_not_found": {
        "ko-KR": "선택한 Git 변경사항을 찾을 수 없습니다.",
        "en-US": "The selected Git change was not found.",
    },
    "agent_terminal.git_path_invalid": {
        "ko-KR": "Git 변경 파일 경로가 올바르지 않습니다.",
        "en-US": "The Git change path is invalid.",
    },
    "agent_terminal.git_status_failed": {
        "ko-KR": "Git 변경사항을 조회하지 못했습니다.",
        "en-US": "The Git working-tree status could not be read.",
    },
    "agent_terminal.git_summary_failed": {
        "ko-KR": "Git 브랜치와 참조 정보를 조회하지 못했습니다.",
        "en-US": "The Git branches and references could not be read.",
    },
    "agent_terminal.git_history_failed": {
        "ko-KR": "Git 커밋 히스토리를 조회하지 못했습니다.",
        "en-US": "The Git commit history could not be read.",
    },
    "agent_terminal.git_history_query_invalid": {
        "ko-KR": "Git 히스토리 조회 범위가 올바르지 않습니다.",
        "en-US": "The Git history query range is invalid.",
    },
    "agent_terminal.git_commit_not_found": {
        "ko-KR": "현재 HEAD 히스토리에서 Git 커밋을 찾을 수 없습니다.",
        "en-US": "The Git commit was not found in the current HEAD history.",
    },
    "agent_terminal.git_operation_failed": {
        "ko-KR": "Git 파일 내용을 조회하지 못했습니다.",
        "en-US": "The Git file content could not be read.",
    },
    "agent_terminal.git_output_invalid": {
        "ko-KR": "Git 명령의 출력 형식이 올바르지 않습니다.",
        "en-US": "The Git command returned invalid output.",
    },
    "agent_terminal.git_output_too_large": {
        "ko-KR": "Git 변경사항이 표시 제한을 초과했습니다.",
        "en-US": "The Git changes exceed the display limit.",
    },
    "auth.setup_already_complete": {
        "ko-KR": "초기 설정이 이미 완료되었습니다.",
        "en-US": "Initial setup is already complete.",
    },
    "auth.setup_required": {
        "ko-KR": "먼저 초기 관리자 설정을 완료해야 합니다.",
        "en-US": "Initial administrator setup must be completed first.",
    },
    "auth.user_already_exists": {
        "ko-KR": "이미 가입된 이메일입니다.",
        "en-US": "This email is already registered.",
    },
    "auth.login_id_already_exists": {
        "ko-KR": "이미 사용 중인 ID입니다.",
        "en-US": "This ID is already taken.",
    },
    "auth.default_identity_seed_incomplete": {
        "ko-KR": "기본 identity seed가 완전하지 않습니다.",
        "en-US": "Default identity seed is incomplete.",
    },
    "auth.invalid_credentials": {
        "ko-KR": "ID 또는 비밀번호가 올바르지 않습니다.",
        "en-US": "ID or password is invalid.",
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
    "auth.desktop_session_link_invalid": {
        "ko-KR": "데스크탑 세션 연결이 만료되었거나 이미 사용되었습니다.",
        "en-US": "Desktop session link is expired or already used.",
    },
    "auth.required": {
        "ko-KR": "인증이 필요합니다.",
        "en-US": "Authentication required.",
    },
    "auth.valid_email_required": {
        "ko-KR": "올바른 이메일 주소가 필요합니다.",
        "en-US": "A valid email address is required.",
    },
    "auth.valid_login_id_required": {
        "ko-KR": "ID는 영문 소문자, 숫자, 점, 밑줄, 하이픈으로 3~40자여야 합니다.",
        "en-US": "ID must be 3-40 characters using lowercase letters, numbers, dots, underscores, or hyphens.",
    },
    "auth.password_confirmation_mismatch": {
        "ko-KR": "비밀번호 확인이 일치하지 않습니다.",
        "en-US": "Password confirmation does not match.",
    },
    "auth.invalid_locale": {
        "ko-KR": "locale이 올바르지 않습니다.",
        "en-US": "Invalid locale.",
    },
    "auth.invalid_time_zone": {
        "ko-KR": "time zone이 올바르지 않습니다.",
        "en-US": "Invalid time zone.",
    },
    "auth.invalid_date_format": {
        "ko-KR": "날짜 형식이 올바르지 않습니다.",
        "en-US": "Invalid date format.",
    },
    "auth.invalid_app_bar_layout": {
        "ko-KR": "앱바 구성이 올바르지 않습니다.",
        "en-US": "Invalid app bar layout.",
    },
    "admin.app_bar_category_not_found": {
        "ko-KR": "앱바 카테고리를 찾을 수 없습니다.",
        "en-US": "App bar category not found.",
    },
    "admin.invalid_app_bar_icon": {
        "ko-KR": "앱바 카테고리 아이콘이 올바르지 않습니다.",
        "en-US": "Invalid app bar category icon.",
    },
    "admin.invalid_app_bar_layout": {
        "ko-KR": "앱바 구성이 올바르지 않습니다.",
        "en-US": "Invalid app bar layout.",
    },
    "community.channel_not_found": {
        "ko-KR": "커뮤니티 채널을 찾을 수 없습니다.",
        "en-US": "Community channel not found.",
    },
    "community.channel_key_exists": {
        "ko-KR": "커뮤니티 채널 key가 이미 존재합니다.",
        "en-US": "Community channel key already exists.",
    },
    "community.channel_delete_blocked": {
        "ko-KR": "기본 채널 또는 게시글이 있는 채널은 삭제할 수 없습니다. 비활성화를 사용하세요.",
        "en-US": "Default channels or channels with posts cannot be deleted. Disable the channel instead.",
    },
    "community.channel_read_only": {
        "ko-KR": "읽기 전용 채널에는 글이나 댓글을 작성할 수 없습니다.",
        "en-US": "Read-only community channels do not allow posts or comments.",
    },
    "community.post_not_found": {
        "ko-KR": "커뮤니티 글을 찾을 수 없습니다.",
        "en-US": "Community post not found.",
    },
    "community.comment_not_found": {
        "ko-KR": "커뮤니티 댓글을 찾을 수 없습니다.",
        "en-US": "Community comment not found.",
    },
    "community.not_author": {
        "ko-KR": "작성자 또는 관리자만 변경할 수 있습니다.",
        "en-US": "Only the author or an administrator can change it.",
    },
    "community.password_required": {
        "ko-KR": "비밀글에는 비밀번호가 필요합니다.",
        "en-US": "A password is required for secret posts.",
    },
    "community.invalid_password": {
        "ko-KR": "비밀번호가 올바르지 않습니다.",
        "en-US": "Password is invalid.",
    },
    "community.admin_only_content": {
        "ko-KR": "관리자만 볼 수 있는 커뮤니티 글입니다.",
        "en-US": "Only administrators can view this community post.",
    },
    "validation.request_invalid": {
        "ko-KR": "요청 값이 올바르지 않습니다.",
        "en-US": "Request validation failed.",
    },
    "request.invalid_payload": {
        "ko-KR": "요청 본문이 올바르지 않습니다.",
        "en-US": "Request payload is invalid.",
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
    "workspace.app_disabled": {
        "ko-KR": "이 워크스페이스에서 해당 앱이 비활성화되어 있습니다.",
        "en-US": "This app is disabled for the workspace.",
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
    "usage.invalid_event": {
        "ko-KR": "사용 현황 이벤트 값이 올바르지 않습니다.",
        "en-US": "Usage event value is invalid.",
    },
    "admin.usage_to_date_future": {
        "ko-KR": "사용 현황 종료일은 오늘 이후로 선택할 수 없습니다.",
        "en-US": "Usage end date cannot be in the future.",
    },
    "admin.usage_date_range_invalid": {
        "ko-KR": "사용 현황 시작일은 종료일보다 늦을 수 없습니다.",
        "en-US": "Usage start date must be on or before the end date.",
    },
    "admin.usage_date_range_too_long": {
        "ko-KR": "사용 현황 조회 기간은 {max_days}일을 초과할 수 없습니다.",
        "en-US": "Usage date range cannot exceed {max_days} days.",
    },
    "admin.self_delete_denied": {
        "ko-KR": "자기 자신의 사용자 계정은 삭제할 수 없습니다.",
        "en-US": "You cannot delete your own user account.",
    },
    "admin.user_linked_records_delete_denied": {
        "ko-KR": "사용자에 연결된 레코드가 있어 삭제할 수 없습니다.",
        "en-US": "User has linked records and cannot be deleted.",
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
    "admin.workspace_member_not_found": {
        "ko-KR": "워크스페이스 멤버를 찾을 수 없습니다.",
        "en-US": "Workspace member not found.",
    },
    "admin.ai_security_rule_not_found": {
        "ko-KR": "AI 보안 정책 룰을 찾을 수 없습니다.",
        "en-US": "AI security policy rule not found.",
    },
    "admin.ai_security_exception_not_found": {
        "ko-KR": "AI 보안 외부 전송 예외를 찾을 수 없습니다.",
        "en-US": "AI security external transfer exception not found.",
    },
    "admin.ai_security_task_not_found": {
        "ko-KR": "알 수 없는 LLM 작업 종류입니다: {task_kind}",
        "en-US": "Unknown LLM task kind: {task_kind}",
    },
    "ai_security_hard_blocker_exception": {
        "ko-KR": "하드 차단 항목은 외부 전송 예외 대상으로 사용할 수 없습니다.",
        "en-US": "Hard blockers cannot be used in external transfer exceptions.",
    },
    "ai_security_exception_blocker_required": {
        "ko-KR": "예외 허용 항목을 하나 이상 선택해야 합니다.",
        "en-US": "At least one exception-eligible blocker is required.",
    },
    "ai_security_exception_reason_required": {
        "ko-KR": "외부 전송 예외 승인 사유를 입력해야 합니다.",
        "en-US": "An external transfer exception reason is required.",
    },
    "ai_security_exception_expiry_required": {
        "ko-KR": "외부 전송 예외 만료일을 입력해야 합니다.",
        "en-US": "An external transfer exception expiration time is required.",
    },
    "ai_security_exception_expired": {
        "ko-KR": "외부 전송 예외 만료일은 현재 시각 이후여야 합니다.",
        "en-US": "External transfer exception expiration must be in the future.",
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
    "admin.ai_model_registry_changed": {
        "ko-KR": "배포 후 LLM 워크로드 목록이 변경되었습니다. 설정을 새로고침하세요.",
        "en-US": "The LLM workload registry changed after deployment. Refresh the settings.",
    },
    "admin.ai_model_version_conflict": {
        "ko-KR": "다른 관리자가 LLM 설정을 변경했습니다. 새로고침 후 다시 시도하세요.",
        "en-US": "Another administrator changed the LLM settings. Refresh and try again.",
    },
    "admin.ai_model_provider_not_found": {
        "ko-KR": "LLM 제공자를 찾을 수 없습니다: {provider_id}",
        "en-US": "LLM provider not found: {provider_id}",
    },
    "admin.ai_model_provider_key_required": {
        "ko-KR": "{provider_id} 제공자를 활성화하려면 API 키가 필요합니다.",
        "en-US": "An API key is required to enable provider {provider_id}.",
    },
    "admin.ai_model_local_key_not_allowed": {
        "ko-KR": "로컬 LLM 제공자에는 외부 API 키를 저장할 수 없습니다.",
        "en-US": "An external API key cannot be stored for the local LLM provider.",
    },
    "admin.ai_model_credential_encryption_unavailable": {
        "ko-KR": "LLM API 키 암호화 설정을 사용할 수 없습니다.",
        "en-US": "LLM API key encryption is not configured.",
    },
    "admin.ai_model_endpoint_invalid": {
        "ko-KR": "LLM 제공자 엔드포인트가 올바른 HTTP(S) URL이 아닙니다.",
        "en-US": "The LLM provider endpoint is not a valid HTTP(S) URL.",
    },
    "admin.ai_model_discovery_failed": {
        "ko-KR": "{provider_id} 제공자의 모델 목록을 불러오지 못했습니다.",
        "en-US": "Could not load the model inventory for provider {provider_id}.",
    },
    "admin.ai_model_discovered_key_read_only": {
        "ko-KR": "Provider에서 발견한 모델 ID는 변경할 수 없습니다: {model_id}",
        "en-US": "A provider-discovered model ID cannot be changed: {model_id}",
    },
    "admin.ai_model_catalog_duplicate": {
        "ko-KR": "동일한 제공자에 같은 모델이 이미 등록되어 있습니다.",
        "en-US": "The model is already registered for this provider.",
    },
    "admin.ai_model_catalog_not_found": {
        "ko-KR": "등록된 LLM 모델을 찾을 수 없습니다: {model_id}",
        "en-US": "Registered LLM model not found: {model_id}",
    },
    "admin.ai_model_catalog_in_use": {
        "ko-KR": "사용 중인 LLM 모델은 비활성화할 수 없습니다: {model_id}",
        "en-US": "An LLM model in use cannot be disabled: {model_id}",
    },
    "admin.ai_model_catalog_invalid_for_provider": {
        "ko-KR": "모델 {model_id}은(는) {provider_id} 제공자에서 사용할 수 없습니다.",
        "en-US": "Model {model_id} is not available for provider {provider_id}.",
    },
    "admin.ai_model_selected_model_not_served": {
        "ko-KR": "선택한 모델 {model_id}이(가) {provider_id} 제공자의 현재 모델 목록에 없습니다. 관리자가 기본 모델을 다시 선택해야 합니다.",
        "en-US": "Selected model {model_id} is not in provider {provider_id}'s current inventory. An administrator must select a default model again.",
    },
    "admin.ai_model_workload_not_found": {
        "ko-KR": "등록된 LLM 워크로드를 찾을 수 없습니다: {workload_id}",
        "en-US": "Registered LLM workload not found: {workload_id}",
    },
    "admin.ai_model_route_override_not_found": {
        "ko-KR": "LLM 워크로드 경로 오버라이드를 찾을 수 없습니다: {workload_id}",
        "en-US": "LLM workload route override not found: {workload_id}",
    },
    "admin.ai_model_route_not_allowed": {
        "ko-KR": "워크로드 {workload_id}에는 선택한 LLM 경로를 사용할 수 없습니다.",
        "en-US": "The selected LLM route is not allowed for workload {workload_id}.",
    },
    "admin.ai_model_runtime_adapter_not_allowed": {
        "ko-KR": "워크로드 {workload_id}에는 선택한 에이전트 런타임을 사용할 수 없습니다.",
        "en-US": "The selected agent runtime is not allowed for workload {workload_id}.",
    },
    "admin.ai_model_runtime_route_mismatch": {
        "ko-KR": "에이전트 런타임과 LLM 경로 또는 제공자가 일치하지 않습니다.",
        "en-US": "The agent runtime does not match the selected LLM route or provider.",
    },
    "admin.ai_model_provider_required": {
        "ko-KR": "외부 LLM 경로에는 제공자 선택이 필요합니다.",
        "en-US": "An external LLM route requires a provider selection.",
    },
    "admin.ai_model_route_provider_mismatch": {
        "ko-KR": "LLM 경로와 제공자 종류가 일치하지 않습니다.",
        "en-US": "The LLM route and provider type do not match.",
    },
    "admin.ai_model_provider_not_allowed": {
        "ko-KR": "워크로드 {workload_id}에는 선택한 제공자를 사용할 수 없습니다.",
        "en-US": "The selected provider is not allowed for workload {workload_id}.",
    },
    "admin.ai_model_provider_not_ready": {
        "ko-KR": "LLM 제공자 {provider_id}이(가) 활성화되어 있지 않습니다.",
        "en-US": "LLM provider {provider_id} is not enabled.",
    },
    "admin.ai_model_role_not_allowed": {
        "ko-KR": "허용되지 않은 모델 역할입니다: {model_role}",
        "en-US": "Model role is not allowed: {model_role}",
    },
    "admin.ai_model_selection_required": {
        "ko-KR": "외부 LLM 경로에는 사용할 모델 선택이 필요합니다.",
        "en-US": "An external LLM route requires a model selection.",
    },
    "admin.ai_model_capability_mismatch": {
        "ko-KR": "모델 {model_id}은(는) 워크로드 {workload_id}에 필요한 기능을 지원하지 않습니다.",
        "en-US": "Model {model_id} lacks capabilities required by workload {workload_id}.",
    },
    "admin.unknown_workspace_app": {
        "ko-KR": "알 수 없는 워크스페이스 앱입니다: {app_id}",
        "en-US": "Unknown workspace app: {app_id}",
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
    "docs.target_edit_access_required": {
        "ko-KR": "대상 편집 권한이 필요합니다.",
        "en-US": "Target edit access required.",
    },
    "docs.collection_not_found": {
        "ko-KR": "컬렉션을 찾을 수 없습니다.",
        "en-US": "Collection not found.",
    },
    "docs.collection_access_required": {
        "ko-KR": "컬렉션 접근 권한이 필요합니다.",
        "en-US": "Collection access required.",
    },
    "docs.collection_manage_access_required": {
        "ko-KR": "컬렉션 관리 권한이 필요합니다.",
        "en-US": "Collection manage access required.",
    },
    "docs.collection_scope_mismatch": {
        "ko-KR": "문서 위치와 컬렉션 범위가 일치하지 않습니다.",
        "en-US": "The doc location does not match the collection scope.",
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
    "docs.html_single_page_required": {
        "ko-KR": "HTML 문서는 이 버전에서 단일 페이지만 지원합니다.",
        "en-US": "HTML docs support a single page in this version.",
    },
    "docs.content_format_mismatch": {
        "ko-KR": "문서 콘텐츠 형식과 요청 본문이 일치하지 않습니다.",
        "en-US": "The request body does not match the doc content format.",
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
    "media.storage_download_failed": {
        "ko-KR": "스토리지 다운로드에 실패했습니다.",
        "en-US": "Storage download failed.",
    },
    "media.save_metadata_failed": {
        "ko-KR": "미디어 메타데이터를 저장하지 못했습니다.",
        "en-US": "Failed to save media metadata.",
    },
    "media.not_found": {
        "ko-KR": "미디어 파일을 찾을 수 없습니다.",
        "en-US": "Media file not found.",
    },
    "media.proxy_url_expired": {
        "ko-KR": "미디어 보기 링크가 만료되었습니다.",
        "en-US": "Media view link has expired.",
    },
    "media.proxy_url_invalid": {
        "ko-KR": "미디어 보기 링크가 올바르지 않습니다.",
        "en-US": "Media view link is invalid.",
    },
    "media.unsupported_resource_type": {
        "ko-KR": "지원하지 않는 미디어 리소스 유형입니다.",
        "en-US": "Unsupported media resource type.",
    },
    "media.task_list_space_access_required": {
        "ko-KR": "태스크 리스트 스페이스 접근 권한이 필요합니다.",
        "en-US": "Task list space access required.",
    },
    "files.app_disabled": {
        "ko-KR": "이 워크스페이스에서는 파일 앱이 비활성화되어 있습니다.",
        "en-US": "The files app is disabled for this workspace.",
    },
    "files.invalid_visibility": {
        "ko-KR": "지원하지 않는 파일 공개 범위입니다.",
        "en-US": "Unsupported file visibility.",
    },
    "files.name_required": {
        "ko-KR": "이름을 입력해야 합니다.",
        "en-US": "Name is required.",
    },
    "files.folder_not_found": {
        "ko-KR": "폴더를 찾을 수 없습니다.",
        "en-US": "Folder not found.",
    },
    "files.file_not_found": {
        "ko-KR": "파일을 찾을 수 없습니다.",
        "en-US": "File not found.",
    },
    "files.corpus_not_found": {
        "ko-KR": "파일 코퍼스를 찾을 수 없습니다.",
        "en-US": "File corpus not found.",
    },
    "files.corpus_access_required": {
        "ko-KR": "파일 코퍼스 관리 권한이 필요합니다.",
        "en-US": "File corpus management access is required.",
    },
    "files.corpus_conflict": {
        "ko-KR": "파일 코퍼스 상태가 요청과 일치하지 않습니다.",
        "en-US": "The file corpus state conflicts with the request.",
    },
    "files.folder_access_required": {
        "ko-KR": "폴더 접근 권한이 필요합니다.",
        "en-US": "Folder access required.",
    },
    "files.file_access_required": {
        "ko-KR": "파일 접근 권한이 필요합니다.",
        "en-US": "File access required.",
    },
    "files.delete_access_required": {
        "ko-KR": "삭제 또는 수정 권한이 필요합니다.",
        "en-US": "Delete or update access required.",
    },
    "files.parent_manage_access_required": {
        "ko-KR": "상위 폴더를 관리할 권한이 필요합니다.",
        "en-US": "Parent folder manage access required.",
    },
    "files.visibility_change_not_allowed": {
        "ko-KR": "폴더 권한은 생성 후 변경할 수 없습니다.",
        "en-US": "Folder visibility cannot be changed after creation.",
    },
    "files.file_size_limit_exceeded": {
        "ko-KR": "파일은 {limit_mb} MB 이하만 업로드할 수 있습니다.",
        "en-US": "Files must be {limit_mb} MB or smaller.",
    },
    "files.archive_limit_exceeded": {
        "ko-KR": "압축 다운로드는 최대 {limit_files}개 파일, {limit_mb} MB까지 가능합니다.",
        "en-US": "Archive downloads are limited to {limit_files} files and {limit_mb} MB.",
    },
    "files.storage_upload_failed": {
        "ko-KR": "파일 저장소 업로드에 실패했습니다.",
        "en-US": "File storage upload failed.",
    },
    "files.storage_download_failed": {
        "ko-KR": "파일 저장소 다운로드에 실패했습니다.",
        "en-US": "File storage download failed.",
    },
    "files.proxy_url_expired": {
        "ko-KR": "파일 링크가 만료되었습니다.",
        "en-US": "File link has expired.",
    },
    "files.proxy_url_invalid": {
        "ko-KR": "파일 링크가 올바르지 않습니다.",
        "en-US": "File link is invalid.",
    },
    "files.preview_unsupported_type": {
        "ko-KR": "이 파일 형식은 바로보기를 지원하지 않습니다.",
        "en-US": "This file type cannot be previewed.",
    },
    "files.selection_required": {
        "ko-KR": "파일 또는 폴더를 하나 이상 선택해야 합니다.",
        "en-US": "Select at least one file or folder.",
    },
    "files.search_unavailable": {
        "ko-KR": "파일 검색 색인이 아직 준비되지 않았습니다.",
        "en-US": "The file search index is not ready yet.",
    },
    "files.chat_no_evidence": {
        "ko-KR": "저장된 문서에서 답변할 근거를 찾지 못했습니다.",
        "en-US": "I could not find enough evidence in the stored documents to answer.",
    },
    "files.chat_retrieval_unavailable": {
        "ko-KR": "문서 검색을 현재 사용할 수 없습니다. 잠시 후 다시 시도해 주세요.",
        "en-US": "Document search is currently unavailable. Try again shortly.",
    },
    "files.chat_sources_title": {
        "ko-KR": "근거 문서",
        "en-US": "Source documents",
    },
    "search.keyword_backend_unavailable": {
        "ko-KR": "키워드 검색을 사용할 수 없습니다: {reason}",
        "en-US": "Keyword search is unavailable: {reason}",
    },
    "search.workspace_keyword_search_disabled": {
        "ko-KR": "이 워크스페이스에서 키워드 검색을 사용할 수 없습니다.",
        "en-US": "Keyword search is not available in this workspace.",
    },
    "retrieval.invalid_source": {
        "ko-KR": "지원하지 않는 검색 소스입니다: {source}",
        "en-US": "Unsupported retrieval source: {source}",
    },
    "retrieval.source_unavailable": {
        "ko-KR": "이 워크스페이스에서 검색 소스를 사용할 수 없습니다: {source}",
        "en-US": "Retrieval source is unavailable in this workspace: {source}",
    },
    "retrieval.source_failed": {
        "ko-KR": "요청한 검색 소스가 일시적으로 응답하지 않습니다: {source}",
        "en-US": "The requested retrieval source is temporarily unavailable: {source}",
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
    "ai.conversation_retry_requires_rewrite": {
        "ko-KR": "재응답 요청에는 대화 절단 지점이 필요합니다.",
        "en-US": "Retry requests require a conversation rewrite point.",
    },
    "ai.durable_stream_required": {
        "ko-KR": "이 AI 분석은 백그라운드 실행을 위해 스트리밍 요청이 필요합니다.",
        "en-US": "This AI analysis requires the streaming endpoint for durable background execution.",
    },
    "ai.conversation_rewrite_requires_persisted_thread": {
        "ko-KR": "대화 수정은 저장된 대화에서만 가능합니다.",
        "en-US": "Conversation rewrites require a persisted conversation.",
    },
    "ai.conversation_rewrite_turn_id_required": {
        "ko-KR": "수정할 대화 메시지 ID가 필요합니다.",
        "en-US": "Conversation rewrites require the target turn id.",
    },
    "ai.conversation_rewrite_tail_required": {
        "ko-KR": "대화 수정에는 마지막으로 확인한 메시지 정보가 필요합니다.",
        "en-US": "Conversation rewrites require the last seen turn.",
    },
    "ai.conversation_rewrite_approval_pending": {
        "ko-KR": "승인 또는 재개 중인 작업이 있어 이 대화를 수정할 수 없습니다.",
        "en-US": "This conversation cannot be rewritten while an approval run is active.",
    },
    "ai.conversation_run_active": {
        "ko-KR": "이 대화에서 다른 응답이 진행 중입니다. 완료 후 다시 시도하세요.",
        "en-US": "Another response is already running for this conversation. Try again after it finishes.",
    },
    "ai.conversation_persist_error": {
        "ko-KR": "채팅 기록 저장 중 오류가 발생했습니다.",
        "en-US": "An error occurred while saving chat history.",
    },
    "ai.conversation_persistence_required": {
        "ko-KR": "이 대화 기능을 사용하려면 대화 저장이 필요합니다.",
        "en-US": "This conversation experience requires saved chat history.",
    },
    "ai.conversation_rewrite_tail_mismatch": {
        "ko-KR": "대화가 다른 곳에서 먼저 변경되었습니다. 새로고침 후 다시 시도하세요.",
        "en-US": "This conversation changed elsewhere. Refresh and try again.",
    },
    "ai.conversation_rewrite_seq_missing": {
        "ko-KR": "수정할 대화 지점을 찾을 수 없습니다.",
        "en-US": "The requested conversation rewrite point was not found.",
    },
    "ai.conversation_rewrite_role_mismatch": {
        "ko-KR": "수정할 대화 메시지의 역할이 요청과 일치하지 않습니다.",
        "en-US": "The target turn role does not match the rewrite request.",
    },
    "ai.conversation_retry_context_mismatch": {
        "ko-KR": "재응답할 사용자 메시지가 현재 대화와 일치하지 않습니다.",
        "en-US": "The user message to retry does not match the current conversation.",
    },
    "mail.account_not_found": {
        "ko-KR": "메일 계정을 찾을 수 없습니다.",
        "en-US": "Mail account not found.",
    },
    "mail.account_duplicate": {
        "ko-KR": "이미 연결된 메일 계정입니다.",
        "en-US": "This mail account is already connected.",
    },
    "mail.message_not_found": {
        "ko-KR": "메일을 찾을 수 없습니다.",
        "en-US": "Mail message not found.",
    },
    "mail.draft_not_found": {
        "ko-KR": "메일 초안을 찾을 수 없습니다.",
        "en-US": "Mail draft not found.",
    },
    "mail.draft_not_sendable": {
        "ko-KR": "이 초안은 발송할 수 없습니다.",
        "en-US": "This draft cannot be sent.",
    },
    "mail.connection_failed": {
        "ko-KR": "메일 서버 연결에 실패했습니다: {error}",
        "en-US": "Mail server connection failed: {error}",
    },
    "mail.credential_key_missing": {
        "ko-KR": "메일 자격 증명 암호화 키가 설정되어 있지 않습니다.",
        "en-US": "Mail credential encryption key is not configured.",
    },
    "mail.sync_dispatch_failed": {
        "ko-KR": "메일 동기화 작업을 시작하지 못했습니다.",
        "en-US": "Could not start the mail sync task.",
    },
    "mail.smtp_failed": {
        "ko-KR": "메일 발송에 실패했습니다: {error}",
        "en-US": "Mail send failed: {error}",
    },
    "mail.ai_failed": {
        "ko-KR": "메일 AI 작업에 실패했습니다.",
        "en-US": "Mail AI task failed.",
    },
    "dm.recipient_not_found": {
        "ko-KR": "DM을 보낼 사용자를 찾을 수 없습니다.",
        "en-US": "DM recipient not found.",
    },
    "dm.recipients_not_found": {
        "ko-KR": "그룹 DM 참여자 중 찾을 수 없는 사용자가 있습니다.",
        "en-US": "One or more group DM recipients were not found.",
    },
    "dm.group_participants_required": {
        "ko-KR": "그룹 DM에는 본인을 제외하고 최소 2명의 참여자가 필요합니다.",
        "en-US": "A group DM requires at least two participants besides you.",
    },
    "dm.group_only": {
        "ko-KR": "그룹 DM에서만 사용할 수 있는 기능입니다.",
        "en-US": "This action is only available for group DMs.",
    },
    "dm.participant_not_found": {
        "ko-KR": "DM 참여자를 찾을 수 없습니다.",
        "en-US": "DM participant not found.",
    },
    "dm.manage_forbidden": {
        "ko-KR": "이 그룹 DM을 관리할 권한이 없습니다.",
        "en-US": "You do not have permission to manage this group DM.",
    },
    "dm.thread_not_found": {
        "ko-KR": "DM 대화를 찾을 수 없습니다.",
        "en-US": "DM thread not found.",
    },
    "dm.message_body_required": {
        "ko-KR": "DM 메시지 또는 첨부파일을 입력해 주세요.",
        "en-US": "Enter a DM message or attach a file.",
    },
    "dm.message_not_found": {
        "ko-KR": "답글을 달 DM 메시지를 찾을 수 없습니다.",
        "en-US": "The DM message to reply to was not found.",
    },
    "dm.attachment_not_found": {
        "ko-KR": "DM 첨부파일을 찾을 수 없습니다.",
        "en-US": "DM attachment not found.",
    },
    "dm.attachment_empty": {
        "ko-KR": "빈 파일은 첨부할 수 없습니다.",
        "en-US": "Empty files cannot be attached.",
    },
    "dm.attachment_size_limit_exceeded": {
        "ko-KR": "DM 첨부파일은 {limit_mb}MB 이하만 업로드할 수 있습니다.",
        "en-US": "DM attachments must be {limit_mb} MB or smaller.",
    },
    "dm.attachment_upload_failed": {
        "ko-KR": "DM 첨부파일 업로드에 실패했습니다.",
        "en-US": "DM attachment upload failed.",
    },
    "dm.attachment_save_failed": {
        "ko-KR": "DM 첨부파일 정보를 저장하지 못했습니다.",
        "en-US": "Could not save DM attachment metadata.",
    },
    "dm.attachment_already_sent": {
        "ko-KR": "이미 전송된 DM 첨부파일입니다.",
        "en-US": "This DM attachment has already been sent.",
    },
    "dm.attachment_preview_unsupported": {
        "ko-KR": "미리보기를 지원하지 않는 DM 첨부파일입니다.",
        "en-US": "This DM attachment cannot be previewed.",
    },
    "dm.attachment_proxy_url_invalid": {
        "ko-KR": "DM 첨부파일 링크가 만료되었거나 올바르지 않습니다.",
        "en-US": "The DM attachment link is expired or invalid.",
    },
    "dm.attachment_download_failed": {
        "ko-KR": "DM 첨부파일을 불러오지 못했습니다.",
        "en-US": "Could not load the DM attachment.",
    },
    "notifications.not_found": {
        "ko-KR": "알림을 찾을 수 없습니다.",
        "en-US": "Notification not found.",
    },
    "personal_widgets.todo_not_found": {
        "ko-KR": "개인 할 일을 찾을 수 없습니다.",
        "en-US": "Personal todo not found.",
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
    "whiteboard.target_edit_access_required": {
        "ko-KR": "대상 편집 권한이 필요합니다.",
        "en-US": "Target edit access required.",
    },
    "whiteboard.target_access_required": {
        "ko-KR": "대상 접근 권한이 필요합니다.",
        "en-US": "Target access required.",
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
    "bento.not_found": {
        "ko-KR": "Bento 프레젠테이션을 찾을 수 없습니다.",
        "en-US": "Bento presentation not found.",
    },
    "bento.manage_access_required": {
        "ko-KR": "Bento 프레젠테이션 관리 권한이 필요합니다.",
        "en-US": "Bento presentation manage access required.",
    },
    "bento.version_conflict": {
        "ko-KR": "프레젠테이션이 다른 곳에서 먼저 수정되었습니다. 다시 불러온 뒤 저장하세요.",
        "en-US": "The presentation was modified elsewhere. Reload it before saving.",
    },
    "bento.invalid_document": {
        "ko-KR": "올바른 bento/slides 문서가 아닙니다.",
        "en-US": "This is not a valid bento/slides document.",
    },
    "bento.invalid_document_title": {
        "ko-KR": "Bento 문서 제목이 올바르지 않습니다.",
        "en-US": "The Bento document title is invalid.",
    },
    "bento.document_too_large": {
        "ko-KR": "Bento 문서가 허용 크기를 초과했습니다.",
        "en-US": "The Bento document exceeds the allowed size.",
    },
    "bento.archived": {
        "ko-KR": "보관된 프레젠테이션은 복원한 뒤 수정할 수 있습니다.",
        "en-US": "Restore the archived presentation before editing it.",
    },
    "bento.archive_before_delete": {
        "ko-KR": "영구 삭제 전에 프레젠테이션을 먼저 보관해야 합니다.",
        "en-US": "Archive the presentation before permanent deletion.",
    },
    "bento.ai_unavailable": {
        "ko-KR": "로컬 AI 모델을 사용할 수 없습니다. 모델 실행 및 관리자 설정을 확인하세요.",
        "en-US": "The local AI model is unavailable. Check the model runtime and admin settings.",
    },
    "bento.ai_invalid_response": {
        "ko-KR": "로컬 AI 응답을 Bento 문서로 변환하지 못했습니다. 자동 교정 후에도 검증에 실패했습니다. 다시 시도하세요.",
        "en-US": "The local AI response could not be converted into a Bento document. Validation still failed after automatic repair. Try again.",
    },
    "bento.ai_document_too_large": {
        "ko-KR": "이 프레젠테이션은 AI로 수정하기에 너무 큽니다.",
        "en-US": "This presentation is too large for AI editing.",
    },
    "bento.ai_unsupported_document": {
        "ko-KR": "이 프레젠테이션에는 현재 AI 수정이 지원하지 않는 요소가 포함되어 있습니다.",
        "en-US": "This presentation contains elements that AI editing does not currently support.",
    },
    "bento.ai_job_not_found": {
        "ko-KR": "AI 작업을 찾을 수 없습니다.",
        "en-US": "The AI job was not found.",
    },
    "bento.ai_edit_already_running": {
        "ko-KR": "이 프레젠테이션의 AI 수정 작업이 이미 진행 중입니다.",
        "en-US": "An AI revision is already running for this presentation.",
    },
    "diagrams.not_found": {
        "ko-KR": "다이어그램을 찾을 수 없습니다.",
        "en-US": "Diagram not found.",
    },
    "diagrams.manage_access_required": {
        "ko-KR": "다이어그램 관리 권한이 필요합니다.",
        "en-US": "Diagram manage access required.",
    },
    "diagrams.version_conflict": {
        "ko-KR": "다이어그램이 다른 곳에서 먼저 수정되었습니다. 다시 불러온 뒤 저장하세요.",
        "en-US": "The diagram was modified elsewhere. Reload it before saving.",
    },
    "diagrams.invalid_preview": {
        "ko-KR": "다이어그램 미리보기 PNG payload가 올바르지 않습니다.",
        "en-US": "Invalid diagram preview PNG payload.",
    },
    "diagrams.source_too_large": {
        "ko-KR": "다이어그램 XML이 허용 크기를 초과했습니다.",
        "en-US": "Diagram XML exceeds the allowed size.",
    },
    "diagrams.preview_too_large": {
        "ko-KR": "다이어그램 미리보기 PNG가 허용 크기를 초과했습니다.",
        "en-US": "Diagram preview PNG exceeds the allowed size.",
    },
    "diagrams.preview_not_found": {
        "ko-KR": "다이어그램 미리보기를 찾을 수 없습니다.",
        "en-US": "Diagram preview not found.",
    },
    "diagrams.storage_unavailable": {
        "ko-KR": "다이어그램 저장소를 사용할 수 없습니다.",
        "en-US": "Diagram storage is unavailable.",
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
    "ai.chat_context_tool_not_allowed": {
        "ko-KR": "AI 어시스턴트에서는 PMS와 문서 컨텍스트 도구만 사용할 수 있습니다.",
        "en-US": "The AI assistant can only use PMS and Docs context tools.",
    },
    "ai.tool_domain_access_denied": {
        "ko-KR": "이 AI 도구가 조회하는 도메인에 접근할 권한이 없습니다: {domain}",
        "en-US": "You do not have access to the domain queried by this AI tool: {domain}",
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
        "ko-KR": 'AI 도구 명령 형식: /tool <tool_name> {{"arg":"value"}}',
        "en-US": 'Tool command syntax: /tool <tool_name> {{"arg":"value"}}',
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
    "ai.external_provider_requires_auto_backend": {
        "ko-KR": "external_provider는 backend_mode=auto에서만 사용할 수 있습니다.",
        "en-US": "external_provider can only be used with backend_mode=auto.",
    },
    "ai.external_provider_unsupported": {
        "ko-KR": "지원하지 않는 외부 LLM provider입니다: {error}",
        "en-US": "Unsupported external LLM provider: {error}",
    },
    "ai.external_provider_tools_unsupported": {
        "ko-KR": "{provider} 외부 provider는 현재 AI 도구 호출을 지원하지 않습니다.",
        "en-US": "External provider {provider} does not currently support AI tool calls.",
    },
    "ai.gateway_policy_violation": {
        "ko-KR": "AI Gateway 정책이 이 요청을 허용하지 않습니다: {reason}",
        "en-US": "AI Gateway policy does not allow this request: {reason}",
    },
    "ai.external_transfer_blocked": {
        "ko-KR": "AI 보안 정책에 따라 외부 전송이 차단되었습니다.",
        "en-US": "External transfer was blocked by the AI security policy.",
    },
    "ai.unsupported_conversation_scope": {
        "ko-KR": "지원하지 않는 AI 대화 scope입니다: {scope_ref}",
        "en-US": "Unsupported AI conversation scope: {scope_ref}",
    },
    "ai.conversation_scope_prompt_missing": {
        "ko-KR": "AI 대화 scope의 시스템 프롬프트가 설정되어 있지 않습니다: {scope_ref}",
        "en-US": "AI conversation scope system prompt is not configured: {scope_ref}",
    },
    "ai.conversation_scope_mismatch": {
        "ko-KR": "요청한 AI 대화 scope가 기존 대화 scope와 일치하지 않습니다.",
        "en-US": "Requested AI conversation scope does not match the existing conversation scope.",
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
        "ko-KR": "PMS 태스크 업데이트에는 변경할 필드를 하나 이상 제공해야 합니다.",
        "en-US": "PMS task updates must provide at least one mutable field.",
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
    "pms.task_list_archived_read_only": {
        "ko-KR": "보관된 리스트는 수정할 수 없습니다. 먼저 리스트를 복원해 주세요.",
        "en-US": "Archived task lists cannot be modified. Restore the list first.",
    },
    "pms.task_list_archive_before_delete": {
        "ko-KR": "리스트를 영구 삭제하려면 먼저 보관해야 합니다.",
        "en-US": "Archive the task list before permanently deleting it.",
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
    "pms.duplicate_task_ids": {
        "ko-KR": "중복된 태스크 ID는 허용되지 않습니다.",
        "en-US": "Duplicate task ids are not allowed.",
    },
    "pms.assignee_task_list_member_required": {
        "ko-KR": "담당자는 태스크 리스트 멤버여야 합니다.",
        "en-US": "Assignee must be a task list member.",
    },
    "pms.assignees_task_list_members_required": {
        "ko-KR": "담당자들은 태스크 리스트 멤버여야 합니다.",
        "en-US": "Assignees must be task list members.",
    },
    "pms.followers_task_list_members_required": {
        "ko-KR": "팔로워는 태스크 리스트 멤버여야 합니다.",
        "en-US": "Followers must be task list members.",
    },
    "pms.milestone_wrong_list": {
        "ko-KR": "마일스톤이 이 리스트에 속하지 않습니다.",
        "en-US": "Milestone does not belong to this list.",
    },
    "pms.milestone_not_found": {
        "ko-KR": "마일스톤을 찾을 수 없습니다.",
        "en-US": "Milestone not found.",
    },
    "pms.parent_task_not_found": {
        "ko-KR": "부모 태스크를 찾을 수 없습니다.",
        "en-US": "Parent task not found.",
    },
    "pms.parent_task_same_list_required": {
        "ko-KR": "부모 태스크는 같은 리스트에 속해야 합니다.",
        "en-US": "Parent task must belong to the same list.",
    },
    "pms.task_cannot_be_own_parent": {
        "ko-KR": "태스크를 자기 자신의 부모로 지정할 수 없습니다.",
        "en-US": "Task cannot be its own parent.",
    },
    "pms.task_parent_cycle": {
        "ko-KR": "태스크 부모 관계에 순환이 포함될 수 없습니다.",
        "en-US": "Task parent relationship cannot contain a cycle.",
    },
    "pms.labels_invalid_for_list": {
        "ko-KR": "하나 이상의 라벨이 이 리스트에 유효하지 않습니다.",
        "en-US": "One or more labels are invalid for this list.",
    },
    "pms.task_not_found": {
        "ko-KR": "태스크를 찾을 수 없습니다.",
        "en-US": "Task not found.",
    },
    "pms.task_access_required": {
        "ko-KR": "이 태스크에 접근할 권한이 없습니다.",
        "en-US": "You do not have access to this task.",
    },
    "pms.label_name_exists": {
        "ko-KR": "이 리스트에 같은 이름의 라벨이 이미 있습니다.",
        "en-US": "Label name already exists in this list.",
    },
    "pms.label_not_found": {
        "ko-KR": "라벨을 찾을 수 없습니다.",
        "en-US": "Label not found.",
    },
    "pms.no_matching_tasks": {
        "ko-KR": "일치하는 태스크를 찾을 수 없습니다.",
        "en-US": "No matching tasks found.",
    },
    "pms.file_size_limit_exceeded": {
        "ko-KR": "파일 크기가 {limit_mb} MB 제한을 초과했습니다.",
        "en-US": "File size exceeds {limit_mb} MB limit.",
    },
    "pms.attachment_not_found": {
        "ko-KR": "첨부파일을 찾을 수 없습니다.",
        "en-US": "Attachment not found.",
    },
    "pms.attachment_proxy_url_invalid": {
        "ko-KR": "첨부파일 다운로드 링크가 만료되었거나 유효하지 않습니다.",
        "en-US": "Attachment download link is expired or invalid.",
    },
    "pms.attachment_download_failed": {
        "ko-KR": "첨부파일을 다운로드하지 못했습니다.",
        "en-US": "Could not download the attachment.",
    },
    "pms.notification_not_found": {
        "ko-KR": "알림을 찾을 수 없습니다.",
        "en-US": "Notification not found.",
    },
    "pms.checklist_item_not_found": {
        "ko-KR": "체크리스트 항목을 찾을 수 없습니다.",
        "en-US": "Checklist item not found.",
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
        "ko-KR": "상태를 삭제할 수 없습니다. {count}개의 태스크가 사용 중입니다.",
        "en-US": "Cannot delete status: {count} task(s) are using it.",
    },
    "pms.closed_status_required": {
        "ko-KR": "종료 상태는 삭제할 수 없습니다.",
        "en-US": "The closed status cannot be deleted.",
    },
    "pms.closed_status_single": {
        "ko-KR": "종료 상태는 하나만 사용할 수 있습니다.",
        "en-US": "Only one closed status is allowed.",
    },
    "pms.status_inherit_requires_space": {
        "ko-KR": "Space가 없는 리스트는 상태를 상속할 수 없습니다.",
        "en-US": "Lists without a Space cannot inherit statuses.",
    },
    "pms.status_mode_incompatible": {
        "ko-KR": "Space에 없는 상태가 사용 중입니다: {statuses}",
        "en-US": "Some task statuses are not available in the Space workflow: {statuses}",
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
    "announcements.not_found": {
        "ko-KR": "공지사항을 찾을 수 없습니다.",
        "en-US": "Announcement not found.",
    },
    "announcements.admin_required": {
        "ko-KR": "공지사항은 워크스페이스 관리자만 작성·수정·삭제할 수 있습니다.",
        "en-US": "Only workspace admins can create, edit, or delete announcements.",
    },
    "announcements.company_admin_required": {
        "ko-KR": "사내 주요 공지는 플랫폼 관리자만 작성·수정·삭제할 수 있습니다.",
        "en-US": "Only platform admins can manage company-wide announcements.",
    },
    "release_notes.not_found": {
        "ko-KR": "릴리즈 내역을 찾을 수 없습니다.",
        "en-US": "Release note not found.",
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
    "meeting.file_not_found": {
        "ko-KR": "회의 첨부파일을 찾을 수 없습니다.",
        "en-US": "Meeting file attachment not found.",
    },
    "meeting.file_proxy_url_invalid": {
        "ko-KR": "회의 첨부파일 다운로드 링크가 만료되었거나 유효하지 않습니다.",
        "en-US": "Meeting file attachment link is expired or invalid.",
    },
    "meeting.file_download_failed": {
        "ko-KR": "회의 첨부파일을 다운로드하지 못했습니다.",
        "en-US": "Could not download the meeting file attachment.",
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
    "video_chat.disabled": {
        "ko-KR": "화상채팅 기능이 비활성화되어 있습니다.",
        "en-US": "Video chat is disabled.",
    },
    "video_chat.livekit_not_configured": {
        "ko-KR": "LiveKit 연결 정보가 설정되어 있지 않습니다.",
        "en-US": "LiveKit connection settings are not configured.",
    },
    "video_chat.session_not_found": {
        "ko-KR": "화상채팅 세션을 찾을 수 없습니다.",
        "en-US": "Video chat session not found.",
    },
    "video_chat.session_closed": {
        "ko-KR": "종료된 화상채팅 세션입니다.",
        "en-US": "Video chat session is closed.",
    },
    "video_chat.host_required": {
        "ko-KR": "화상채팅 방 개설자만 방을 종료할 수 있습니다.",
        "en-US": "Only the video chat host can end this room.",
    },
    "video_chat.meeting_not_found": {
        "ko-KR": "연결할 회의를 찾을 수 없습니다.",
        "en-US": "Linked meeting not found.",
    },
    "video_chat.recording_not_enabled": {
        "ko-KR": "화상채팅 녹화는 아직 활성화되어 있지 않습니다.",
        "en-US": "Video chat recording is not enabled.",
    },
    "video_chat.egress_not_configured": {
        "ko-KR": "LiveKit Egress 연결 정보가 설정되어 있지 않습니다.",
        "en-US": "LiveKit Egress settings are not configured.",
    },
    "video_chat.recording_not_active": {
        "ko-KR": "진행 중인 화상채팅 녹화가 없습니다.",
        "en-US": "There is no active video chat recording.",
    },
    "video_chat.captions_not_enabled": {
        "ko-KR": "실시간 자막은 아직 활성화되어 있지 않습니다.",
        "en-US": "Realtime captions are not enabled.",
    },
    "video_chat.captions_not_active": {
        "ko-KR": "진행 중인 실시간 자막 세션이 없습니다.",
        "en-US": "There is no active realtime caption session.",
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
    "recording.target_filter_required": {
        "ko-KR": "첨부 대상 필터에는 app, type, id가 모두 필요합니다.",
        "en-US": "Target filters require app, type, and id.",
    },
    "recording.target_access_required": {
        "ko-KR": "첨부 대상에 접근할 권한이 없습니다.",
        "en-US": "You do not have access to the attached object.",
    },
    "recording.target_attach_required": {
        "ko-KR": "이 대상에 녹음을 첨부할 권한이 없습니다.",
        "en-US": "You do not have permission to attach a recording to this object.",
    },
    "recording.target_detach_required": {
        "ko-KR": "이 대상에서 녹음을 해제할 권한이 없습니다.",
        "en-US": "You do not have permission to detach the recording from this object.",
    },
    "recording.target_not_found": {
        "ko-KR": "녹음 첨부 대상을 찾을 수 없습니다.",
        "en-US": "Recording target not found.",
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
    "recording.uploader_read_staging_required": {
        "ko-KR": "업로더만 이 녹음 업로드 상태를 확인할 수 있습니다.",
        "en-US": "Only the uploader can read this recording upload.",
    },
    "recording.tus_version_required": {
        "ko-KR": "지원되는 tus 버전 헤더가 필요합니다.",
        "en-US": "A supported tus version header is required.",
    },
    "recording.tus_metadata_required": {
        "ko-KR": "tus 업로드에는 녹음 식별자와 오디오 형식 메타데이터가 필요합니다.",
        "en-US": "Tus uploads require recording identity and audio format metadata.",
    },
    "recording.tus_metadata_invalid": {
        "ko-KR": "tus 업로드 메타데이터 형식이 올바르지 않습니다.",
        "en-US": "Tus upload metadata is malformed.",
    },
    "recording.tus_checksum_invalid": {
        "ko-KR": "tus 체크섬 헤더 형식이 올바르지 않습니다.",
        "en-US": "Tus checksum header is malformed.",
    },
    "recording.tus_offset_conflict": {
        "ko-KR": "tus 업로드 위치가 서버 상태와 일치하지 않습니다.",
        "en-US": "Tus upload offset does not match the server state.",
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
