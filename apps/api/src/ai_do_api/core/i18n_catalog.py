from __future__ import annotations

from dataclasses import dataclass, field
from string import Formatter
from typing import Any

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
    "platform.app_disabled": {
        "ko-KR": "관리자에 의해 비활성화된 앱입니다.",
        "en-US": "This app has been disabled by an administrator.",
    },
    "management_tasks.health_checkup.source_unavailable": {
        "ko-KR": "사용 가능한 통합 인사 ERP 기준 데이터가 없습니다. (사유: {reason})",
        "en-US": "No unified HR ERP-basis data is available. (reason: {reason})",
    },
    "management_tasks.health_checkup.not_available": {
        "ko-KR": "종합검진 기능 구현이 아직 활성화되지 않았습니다.",
        "en-US": "The health-checkup implementation is not active yet.",
    },
    "management_tasks.health_checkup.decision_not_found": {
        "ko-KR": "해당 연도의 종합검진 판정 결과가 없습니다.",
        "en-US": "No health-checkup determination exists for that year.",
    },
    "management_tasks.health_checkup.invalid_workbook": {
        "ko-KR": "전년도 검진 엑셀 파일을 처리할 수 없습니다. (사유: {reason})",
        "en-US": "The prior-year health-checkup workbook cannot be processed. (reason: {reason})",
    },
    "management_tasks.health_checkup.request_too_large": {
        "ko-KR": "업로드 요청 크기를 확인할 수 없거나 허용 한도를 초과했습니다.",
        "en-US": "The upload request size is unverifiable or exceeds the allowed limit.",
    },
    "management_tasks.health_checkup.invalid_settings": {
        "ko-KR": "종합검진 판정 기준이 올바르지 않습니다.",
        "en-US": "The health-checkup determination settings are invalid.",
    },
    "management_tasks.health_checkup.not_publishable": {
        "ko-KR": "현재 입력 자료 확인이 끝나지 않았거나 변경되어 결과를 출력할 수 없습니다. 판정을 새로고침해 주세요. (차단 사유: {blockers})",
        "en-US": "The result cannot be exported because its current inputs are unresolved or changed. Refresh the determination. (blockers: {blockers})",
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
    "auth.signup_disabled": {
        "ko-KR": "회원가입은 비활성화되어 있습니다. 관리자에게 계정 생성을 요청하세요.",
        "en-US": "Sign-up is disabled. Ask an administrator to create your account.",
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
    "auth.external_auth_unavailable": {
        "ko-KR": "외부 인증 서버에 연결할 수 없습니다.",
        "en-US": "External authentication server is unavailable.",
    },
    "auth.password_managed_externally": {
        "ko-KR": "이 계정의 비밀번호는 외부 인증 시스템에서 관리됩니다.",
        "en-US": "This account's password is managed by the external authentication system.",
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
    "platform_api_key.required": {
        "ko-KR": "플랫폼 API 키가 필요합니다.",
        "en-US": "A platform API key is required.",
    },
    "platform_api_key.invalid": {
        "ko-KR": "플랫폼 API 키가 올바르지 않거나 폐기되었습니다.",
        "en-US": "The platform API key is invalid or revoked.",
    },
    "platform_api_key.scope_required": {
        "ko-KR": "플랫폼 API 키에 {scope} 범위가 필요합니다.",
        "en-US": "The platform API key requires the {scope} scope.",
    },
    "hr.integration_snapshot_unavailable": {
        "ko-KR": "선택한 {basis} 기준 인사정보를 현재 제공할 수 없습니다.",
        "en-US": "The selected {basis} HR projection is currently unavailable.",
    },
    "hr.integration_snapshot_changed": {
        "ko-KR": "조회 중 {basis} 기준 데이터 버전이 변경되었습니다. 첫 페이지부터 다시 조회해 주세요.",
        "en-US": "The {basis} HR projection changed during pagination. Restart from the first page.",
    },
    "admin.invalid_workspace_role": {
        "ko-KR": "워크스페이스 역할이 올바르지 않습니다.",
        "en-US": "Invalid workspace role.",
    },
    "admin.user_already_exists": {
        "ko-KR": "사용자가 이미 존재합니다.",
        "en-US": "User already exists.",
    },
    "admin.batch_dispatch_failed": {
        "ko-KR": "배치 실행 요청을 큐에 등록하지 못했습니다.",
        "en-US": "Failed to queue the batch run.",
    },
    "admin.hr_master_record_not_found": {
        "ko-KR": "통합 인사정보를 찾을 수 없습니다.",
        "en-US": "Integrated HR record not found.",
    },
    "admin.hr_manual_match_stale_master": {
        "ko-KR": "통합 인사정보가 변경되었습니다. 최신 화면에서 다시 시도해 주세요.",
        "en-US": "Unified HR data changed. Retry from the latest view.",
    },
    "admin.hr_manual_match_invalid_candidate": {
        "ko-KR": "선택한 ERP 인력 또는 그룹웨어 사용자는 현재 매핑할 수 없습니다.",
        "en-US": "The selected ERP employee or groupware user is not currently available for mapping.",
    },
    "admin.hr_manual_match_reason_required": {
        "ko-KR": "이름이 다른 사용자를 매핑하려면 확인 사유가 필요합니다.",
        "en-US": "A review reason is required to map users with different names.",
    },
    "admin.hr_manual_match_already_linked": {
        "ko-KR": "그룹웨어 사용자 또는 ERP 인력이 이미 수동 매칭되어 있습니다.",
        "en-US": "The groupware user or ERP employee is already manually matched.",
    },
    "admin.hr_manual_match_not_found": {
        "ko-KR": "해제할 수동 매칭을 찾을 수 없습니다.",
        "en-US": "The manual match to revoke was not found.",
    },
    "admin.hr_manual_match_workforce_conflict": {
        "ko-KR": "두 사용자의 관리자 지정 인력 구분이 서로 달라 먼저 구분을 정리해야 합니다.",
        "en-US": "The selected users have conflicting administrator-assigned workforce categories. Resolve the categories before mapping them.",
    },
    "admin.hr_workforce_assignment_conflict": {
        "ko-KR": "식별 충돌 인력에는 인력 구분을 지정할 수 없습니다.",
        "en-US": "A workforce category cannot be assigned to an identity-conflict record.",
    },
    "admin.hr_workforce_assignment_invalid_subject": {
        "ko-KR": "인력 구분을 지정할 수 있는 원천 식별정보가 없습니다.",
        "en-US": "No stable source identity is available for a workforce category assignment.",
    },
    "admin.hr_workforce_assignment_stale_master": {
        "ko-KR": "통합 인사정보가 변경되었습니다. 최신 화면에서 다시 시도해 주세요.",
        "en-US": "Unified HR data changed. Retry from the latest view.",
    },
    "admin.hr_workforce_category_in_use": {
        "ko-KR": "사용 중인 인력 구분은 보관할 수 없습니다.",
        "en-US": "A workforce category that is in use cannot be archived.",
    },
    "admin.hr_workforce_category_inactive": {
        "ko-KR": "보관된 인력 구분은 지정할 수 없습니다.",
        "en-US": "An archived workforce category cannot be assigned.",
    },
    "admin.hr_workforce_category_name_exists": {
        "ko-KR": "같은 이름의 인력 구분이 이미 있습니다.",
        "en-US": "A workforce category with this name already exists.",
    },
    "admin.hr_workforce_category_name_required": {
        "ko-KR": "인력 구분 이름을 입력해 주세요.",
        "en-US": "Enter a workforce category name.",
    },
    "admin.hr_workforce_category_not_found": {
        "ko-KR": "인력 구분을 찾을 수 없습니다.",
        "en-US": "Workforce category not found.",
    },
    "admin.hr_workforce_system_category_required": {
        "ko-KR": "기본 인력 구분은 보관할 수 없습니다.",
        "en-US": "Built-in workforce categories cannot be archived.",
    },
    "admin.qna_workspace_not_found": {
        "ko-KR": "활성 Q&A 워크스페이스를 찾을 수 없습니다.",
        "en-US": "No active Q&A workspace found.",
    },
    "dataviz.app_disabled": {
        "ko-KR": "데이터 시각화 앱이 비활성화되어 있습니다.",
        "en-US": "Data visualization app is disabled.",
    },
    "dataviz.upload_too_large": {
        "ko-KR": "업로드 파일 크기가 허용 한도를 초과했습니다.",
        "en-US": "Uploaded file size exceeds the allowed limit.",
    },
    "dataviz.invalid_category": {
        "ko-KR": "데이터 시각화 카테고리가 올바르지 않습니다.",
        "en-US": "Data visualization category is invalid.",
    },
    "dataviz.core_series_not_found": {
        "ko-KR": "기준 시리즈를 찾을 수 없습니다.",
        "en-US": "Core series not found.",
    },
    "dataviz.parse_failed": {
        "ko-KR": "{filename} 파일을 파싱하지 못했습니다: {error}",
        "en-US": "Failed to parse {filename}: {error}",
    },
    "dataviz.row_not_found": {
        "ko-KR": "데이터 행을 찾을 수 없습니다.",
        "en-US": "Data row not found.",
    },
    "dataviz.no_valid_fields": {
        "ko-KR": "수정할 수 있는 유효한 필드가 없습니다.",
        "en-US": "No valid fields to update.",
    },
    "dataviz.car_model_code_required": {
        "ko-KR": "차종 코드가 필요합니다.",
        "en-US": "Car model code is required.",
    },
    "dataviz.car_model_duplicate": {
        "ko-KR": "이미 등록된 차종 코드입니다.",
        "en-US": "Car model code already exists.",
    },
    "dataviz.source_file_required": {
        "ko-KR": "원본 파일이 필요합니다.",
        "en-US": "Source file is required.",
    },
    "dataviz.no_files": {
        "ko-KR": "업로드할 파일이 없습니다.",
        "en-US": "No files were uploaded.",
    },
    "dataviz.no_data": {
        "ko-KR": "처리할 데이터가 없습니다.",
        "en-US": "No data to process.",
    },
    "dataviz.processing_failed": {
        "ko-KR": "데이터 시각화 처리 중 오류가 발생했습니다.",
        "en-US": "Data visualization processing failed.",
    },
    "dataviz.file_not_found": {
        "ko-KR": "파일을 찾을 수 없습니다.",
        "en-US": "File not found.",
    },
    "dataviz.no_mappings": {
        "ko-KR": "열 매핑이 없습니다.",
        "en-US": "No column mappings found.",
    },
    "dataviz.time_column_not_found": {
        "ko-KR": "시간 열을 찾을 수 없습니다.",
        "en-US": "Time column not found.",
    },
    "dataviz.time_column_no_numeric_values": {
        "ko-KR": "시간 열에 숫자 값이 없습니다.",
        "en-US": "Time column has no numeric values.",
    },
    "dataviz.parts_catalog_required": {
        "ko-KR": "부품 카테고리와 이름이 필요합니다.",
        "en-US": "Part category and name are required.",
    },
    "dataviz.file_id_required": {
        "ko-KR": "파일 ID가 필요합니다.",
        "en-US": "File ID is required.",
    },
    "dataviz.saved_test_not_found": {
        "ko-KR": "저장된 시험 데이터를 찾을 수 없습니다.",
        "en-US": "Saved test data not found.",
    },
    "dataviz.csv_file_missing": {
        "ko-KR": "CSV 파일을 찾을 수 없습니다.",
        "en-US": "CSV file is missing.",
    },
    "legacy_issues.app_disabled": {
        "ko-KR": "과거차 문제점 앱이 비활성화되어 있습니다.",
        "en-US": "Legacy issues app is disabled.",
    },
    "legacy_issues.dataset_not_found": {
        "ko-KR": "과거차 데이터셋을 찾을 수 없습니다.",
        "en-US": "Legacy issue dataset not found.",
    },
    "legacy_issues.dataset_record_not_found": {
        "ko-KR": "과거차 데이터 레코드를 찾을 수 없습니다.",
        "en-US": "Legacy issue record not found.",
    },
    "legacy_issues.aggregate_readonly": {
        "ko-KR": "전체 목록은 조회와 검색만 할 수 있습니다.",
        "en-US": "The aggregate list only supports viewing and search.",
    },
    "legacy_issues.dataset_import_pk_invalid": {
        "ko-KR": "가져오기 파일의 레코드 ID가 올바르지 않습니다.",
        "en-US": "Imported record IDs are invalid.",
    },
    "legacy_issues.dataset_required_field_missing": {
        "ko-KR": "필수 항목이 누락되었습니다: {fields}",
        "en-US": "Required fields are missing: {fields}",
    },
    "legacy_issues.dataset_attachment_too_large": {
        "ko-KR": "첨부파일 크기가 허용 한도를 초과했습니다. 최대 1GB까지 업로드할 수 있습니다.",
        "en-US": "Attachment size exceeds the allowed limit. Uploads are limited to 1 GB.",
    },
    "legacy_issues.dataset_attachment_not_found": {
        "ko-KR": "첨부파일을 찾을 수 없습니다.",
        "en-US": "Attachment not found.",
    },
    "legacy_issues.dataset_attachment_download_failed": {
        "ko-KR": "첨부파일 다운로드에 실패했습니다.",
        "en-US": "Failed to download attachment.",
    },
    "legacy_issues.revision_meeting_attachment_too_large": {
        "ko-KR": "회의록 첨부파일 크기가 허용 한도를 초과했습니다. 최대 1GB까지 업로드할 수 있습니다.",
        "en-US": "Meeting-minutes attachment size exceeds the allowed limit. Uploads are limited to 1 GB.",
    },
    "legacy_issues.revision_meeting_attachment_empty": {
        "ko-KR": "빈 파일은 회의록 첨부파일로 업로드할 수 없습니다.",
        "en-US": "An empty file cannot be uploaded as a meeting-minutes attachment.",
    },
    "legacy_issues.revision_meeting_attachment_not_found": {
        "ko-KR": "회의록 첨부파일을 찾을 수 없습니다.",
        "en-US": "Meeting-minutes attachment not found.",
    },
    "legacy_issues.revision_meeting_attachment_upload_failed": {
        "ko-KR": "회의록 첨부파일을 저장하지 못했습니다. 잠시 후 다시 시도해 주세요.",
        "en-US": "Could not store the meeting-minutes attachment. Try again later.",
    },
    "legacy_issues.revision_meeting_attachment_edit_forbidden": {
        "ko-KR": "첨부파일을 올린 사용자 또는 플랫폼 관리자만 파일 설명을 수정할 수 있습니다.",
        "en-US": "Only the uploader or a platform administrator can edit the file description.",
    },
    "legacy_issues.revision_meeting_attachment_description_too_long": {
        "ko-KR": "회의록 첨부파일 설명은 500자 이내로 입력해 주세요.",
        "en-US": "Meeting-minutes attachment descriptions are limited to 500 characters.",
    },
    "legacy_issues.revision_not_found": {
        "ko-KR": "과거차 데이터 리비전을 찾을 수 없습니다.",
        "en-US": "Legacy issue revision not found.",
    },
    "legacy_issues.revision_overview_history_exists": {
        "ko-KR": "이 게시 리비전에는 이미 개요 이력 행이 있습니다.",
        "en-US": "This published revision already has an overview history row.",
    },
    "legacy_issues.revision_overview_number_exists": {
        "ko-KR": "같은 번호의 개요 리비전 이력이 이미 있습니다.",
        "en-US": "An overview revision history row with this number already exists.",
    },
    "legacy_issues.revision_draft_required": {
        "ko-KR": "초안 리비전이 필요합니다.",
        "en-US": "Draft revision is required.",
    },
    "legacy_issues.revision_locked": {
        "ko-KR": "다른 사용자의 초안 리비전은 수정할 수 없습니다.",
        "en-US": "You cannot edit another user's draft revision.",
    },
    "legacy_issues.revision_force_cancel_confirmation_required": {
        "ko-KR": "다른 사용자의 초안을 강제 취소하려면 모듈 직접 수정 권한자의 확인이 필요합니다.",
        "en-US": "Confirmation from an authorized module direct editor is required to force-cancel another user's draft.",
    },
    "legacy_issues.revision_current_required": {
        "ko-KR": "최신 리비전에서만 대표 첨부를 변경할 수 있습니다.",
        "en-US": "Primary attachments can only be changed on the current revision.",
    },
    "legacy_issues.revision_restore_source_invalid": {
        "ko-KR": "복원 기준 리비전이 올바르지 않습니다.",
        "en-US": "Revision restore source is invalid.",
    },
    "legacy_issues.revision_canceled": {
        "ko-KR": "취소된 초안 리비전은 수정할 수 없습니다.",
        "en-US": "Canceled draft revisions cannot be edited.",
    },
    "legacy_issues.revision_approval_required": {
        "ko-KR": "검토와 승인이 완료되어야 리비전을 발행할 수 있습니다.",
        "en-US": "Review and approval must be completed before publishing the revision.",
    },
    "legacy_issues.revision_request_target_required": {
        "ko-KR": "요청할 검토자 또는 승인자가 없습니다.",
        "en-US": "There is no reviewer or approver to request.",
    },
    "legacy_issues.revision_review_assignee_required": {
        "ko-KR": "지정된 검토자만 검토를 완료할 수 있습니다.",
        "en-US": "Only the assigned reviewer can complete the review.",
    },
    "legacy_issues.revision_approval_assignee_required": {
        "ko-KR": "지정된 승인자만 승인을 완료할 수 있습니다.",
        "en-US": "Only the assigned approver can complete approval.",
    },
    "legacy_issues.assistant_run_not_found": {
        "ko-KR": "과거차 AI 분석 실행 기록을 찾을 수 없습니다.",
        "en-US": "Legacy issue assistant run not found.",
    },
    "legacy_issues.module_not_found": {
        "ko-KR": "과거차 모듈을 찾을 수 없습니다.",
        "en-US": "Legacy issue module not found.",
    },
    "legacy_issues.grid_preference_revision_conflict": {
        "ko-KR": "다른 화면에서 컬럼 설정이 변경되었습니다. 최신 설정을 다시 불러옵니다.",
        "en-US": "Grid preferences changed elsewhere. The latest settings will be reloaded.",
    },
    "legacy_issues.module_field_not_found": {
        "ko-KR": "과거차 모듈 컬럼을 찾을 수 없습니다.",
        "en-US": "Legacy issue module field not found.",
    },
    "legacy_issues.module_field_invalid": {
        "ko-KR": "과거차 모듈 컬럼 설정이 올바르지 않습니다.",
        "en-US": "Legacy issue module field setting is invalid.",
    },
    "legacy_issues.module_field_value_invalid": {
        "ko-KR": "과거차 모듈 컬럼 값이 올바르지 않습니다.",
        "en-US": "Legacy issue module field value is invalid.",
    },
    "legacy_issues.module_field_manage_required": {
        "ko-KR": "과거차 모듈 컬럼 관리 권한이 필요합니다.",
        "en-US": "Legacy issue module field manager access required.",
    },
    "legacy_issues.module_direct_editor_role_conflict": {
        "ko-KR": "다른 모듈 권한으로 관리 중인 사용자는 이 설정에서 변경할 수 없습니다.",
        "en-US": "This user is managed by another module role and cannot be changed here.",
    },
    "legacy_issues.vehicle_model_not_found": {
        "ko-KR": "차종을 찾을 수 없습니다.",
        "en-US": "Vehicle model not found.",
    },
    "legacy_issues.vehicle_model_invalid": {
        "ko-KR": "차종 정보가 올바르지 않습니다.",
        "en-US": "Vehicle model information is invalid.",
    },
    "legacy_issues.vehicle_model_duplicate": {
        "ko-KR": "이미 등록된 차종 코드입니다.",
        "en-US": "Vehicle model code already exists.",
    },
    "legacy_issues.vehicle_model_has_checklists": {
        "ko-KR": "생성된 체크리스트가 있는 차종은 영구 삭제할 수 없습니다.",
        "en-US": "A vehicle model with generated checklists cannot be permanently deleted.",
    },
    "legacy_issues.vehicle_stage_not_found": {
        "ko-KR": "차종 단계를 찾을 수 없습니다.",
        "en-US": "Vehicle stage not found.",
    },
    "legacy_issues.vehicle_stage_invalid": {
        "ko-KR": "차종 단계 정보가 올바르지 않습니다.",
        "en-US": "Vehicle stage information is invalid.",
    },
    "legacy_issues.vehicle_stage_duplicate": {
        "ko-KR": "이미 등록된 차종 단계입니다.",
        "en-US": "Vehicle stage already exists.",
    },
    "legacy_issues.vehicle_stage_vehicle_inactive": {
        "ko-KR": "비활성 차종에는 단계를 추가할 수 없습니다.",
        "en-US": "Stages cannot be added to an inactive vehicle model.",
    },
    "legacy_issues.excel_export_not_found": {
        "ko-KR": "Excel 내보내기 작업을 찾을 수 없습니다.",
        "en-US": "Excel export job not found.",
    },
    "legacy_issues.excel_export_expired": {
        "ko-KR": "Excel 내보내기 파일의 보관 기간이 만료되었습니다. 다시 생성해 주세요.",
        "en-US": "The Excel export has expired. Generate it again.",
    },
    "legacy_issues.excel_export_not_ready": {
        "ko-KR": "Excel 내보내기 파일이 아직 준비되지 않았습니다.",
        "en-US": "The Excel export file is not ready yet.",
    },
    "legacy_issues.excel_export_download_failed": {
        "ko-KR": "Excel 내보내기 파일을 불러올 수 없습니다.",
        "en-US": "The Excel export file could not be loaded.",
    },
    "legacy_issues.excel_export_invalid_columns": {
        "ko-KR": "현재 화면에서 내보낼 수 없는 컬럼이 포함되어 있습니다. 화면을 새로고침한 뒤 다시 시도해 주세요.",
        "en-US": "The export contains columns that are not available in the current view. Refresh the page and try again.",
    },
    "legacy_issues.excel_export_record_attachment_limit": {
        "ko-KR": "한 행의 첨부파일 수가 Excel 내보내기 제한을 초과했습니다.",
        "en-US": "A row exceeds the Excel export attachment limit.",
    },
    "legacy_issues.excel_export_attachment_count_limit": {
        "ko-KR": "첨부파일 수가 Excel 내보내기 제한을 초과했습니다.",
        "en-US": "The number of attachments exceeds the Excel export limit.",
    },
    "legacy_issues.excel_export_attachment_size_limit": {
        "ko-KR": "첨부파일의 전체 크기가 Excel 내보내기 제한을 초과했습니다.",
        "en-US": "The total attachment size exceeds the Excel export limit.",
    },
    "legacy_issues.excel_export_insufficient_space": {
        "ko-KR": "Excel 파일을 생성할 임시 저장 공간이 부족합니다.",
        "en-US": "There is not enough temporary storage to generate the Excel file.",
    },
    "legacy_issues.excel_export_failed": {
        "ko-KR": "Excel 내보내기 생성에 실패했습니다. 다시 시도해 주세요.",
        "en-US": "Excel export generation failed. Try again.",
    },
    "legacy_issues.vehicle_checklist_revision_not_found": {
        "ko-KR": "차종 체크리스트 리비전을 찾을 수 없습니다.",
        "en-US": "Vehicle checklist revision not found.",
    },
    "legacy_issues.vehicle_checklist_revision_completed": {
        "ko-KR": "완료된 차종 체크리스트 리비전은 수정할 수 없습니다.",
        "en-US": "Completed vehicle checklist revisions cannot be edited.",
    },
    "legacy_issues.vehicle_checklist_revision_invalid": {
        "ko-KR": "차종 체크리스트 기준 리비전이 올바르지 않습니다.",
        "en-US": "Vehicle checklist source revision is invalid.",
    },
    "legacy_issues.vehicle_checklist_field_invalid": {
        "ko-KR": "차종 체크리스트에서는 CHECK 컬럼만 수정할 수 있습니다.",
        "en-US": "Only CHECK columns can be edited in vehicle checklists.",
    },
    "legacy_issues.vehicle_checklist_transition_read_only": {
        "ko-KR": "차종별 체크리스트를 모듈별 구조로 전환 중입니다. 기존 체크리스트는 조회하거나 삭제만 할 수 있습니다.",
        "en-US": "Vehicle checklists are being migrated to a module-based structure. Existing checklists can only be viewed or deleted.",
    },
    "legacy_issues.vehicle_module_checklist_not_found": {
        "ko-KR": "차종의 모듈별 체크리스트를 찾을 수 없습니다.",
        "en-US": "Vehicle module checklist not found.",
    },
    "legacy_issues.vehicle_module_checklist_completed": {
        "ko-KR": "완료된 모듈별 체크리스트는 수정할 수 없습니다.",
        "en-US": "Completed module checklists cannot be edited.",
    },
    "legacy_issues.vehicle_module_checklist_revision_invalid": {
        "ko-KR": "모듈별 체크리스트의 기준 마스터 리비전이 올바르지 않습니다.",
        "en-US": "The module checklist source master revision is invalid.",
    },
    "legacy_issues.vehicle_module_checklist_previous_completed_not_found": {
        "ko-KR": "선택한 이전 단계의 완료 체크리스트를 가져올 수 없습니다.",
        "en-US": "The selected completed checklist from an earlier stage is unavailable.",
    },
    "legacy_issues.vehicle_module_checklist_stage_not_empty": {
        "ko-KR": "현재 단계의 모듈에 이미 체크리스트가 있어 이전 단계 완료본을 가져올 수 없습니다.",
        "en-US": "The previous-stage checklist cannot be imported because this module already has a checklist in the current stage.",
    },
    "legacy_issues.vehicle_module_checklist_field_invalid": {
        "ko-KR": "모듈별 체크리스트에서는 CHECK 컬럼만 수정할 수 있습니다.",
        "en-US": "Only CHECK columns can be edited in module checklists.",
    },
    "legacy_issues.vehicle_module_checklist_attachment_too_large": {
        "ko-KR": "체크리스트 첨부파일 크기가 허용 한도를 초과했습니다. 최대 1GB까지 업로드할 수 있습니다.",
        "en-US": "Checklist attachment size exceeds the allowed limit. Uploads are limited to 1 GB.",
    },
    "legacy_issues.vehicle_module_checklist_attachment_empty": {
        "ko-KR": "빈 파일은 체크리스트에 첨부할 수 없습니다.",
        "en-US": "Empty files cannot be attached to a checklist.",
    },
    "legacy_issues.vehicle_module_checklist_attachment_not_found": {
        "ko-KR": "체크리스트 첨부파일을 찾을 수 없습니다.",
        "en-US": "Checklist attachment not found.",
    },
    "legacy_issues.vehicle_module_checklist_attachment_upload_failed": {
        "ko-KR": "체크리스트 첨부파일 업로드에 실패했습니다.",
        "en-US": "Failed to upload the checklist attachment.",
    },
    "legacy_issues.vehicle_module_checklist_attachment_download_failed": {
        "ko-KR": "체크리스트 첨부파일 다운로드에 실패했습니다.",
        "en-US": "Failed to download the checklist attachment.",
    },
    "legacy_issues.vehicle_module_checklist_attachment_delete_failed": {
        "ko-KR": "체크리스트 첨부파일 삭제에 실패했습니다.",
        "en-US": "Failed to delete the checklist attachment.",
    },
    "qna.app_disabled": {
        "ko-KR": "사내 관리팀 Q&A 앱이 비활성화되어 있습니다.",
        "en-US": "Internal Ops Q&A app is disabled.",
    },
    "qna.file_too_large": {
        "ko-KR": "Q&A 문서 파일 크기가 허용 한도를 초과했습니다.",
        "en-US": "Q&A document file size exceeds the allowed limit.",
    },
    "qna.unsupported_document_type": {
        "ko-KR": "지원하지 않는 Q&A 문서 형식입니다.",
        "en-US": "Unsupported Q&A document type.",
    },
    "qna.document_not_found": {
        "ko-KR": "Q&A 문서를 찾을 수 없습니다.",
        "en-US": "Q&A document not found.",
    },
    "qna.answer_generation_failed": {
        "ko-KR": "Q&A 답변 생성에 실패했습니다. 잠시 후 다시 시도하세요.",
        "en-US": "Failed to generate the Q&A answer. Try again later.",
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
    "admin.hr_user_delete_denied": {
        "ko-KR": "인사정보 연동 사용자는 삭제할 수 없습니다. 로그인을 차단하세요.",
        "en-US": "HR-synced users cannot be deleted. Block login instead.",
    },
    "admin.org_unit_slug_exists": {
        "ko-KR": "조직 단위 slug가 이미 존재합니다.",
        "en-US": "Org unit slug already exists.",
    },
    "admin.org_unit_not_found": {
        "ko-KR": "조직 단위를 찾을 수 없습니다.",
        "en-US": "Org unit not found.",
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
    "admin.platform_api_key_not_found": {
        "ko-KR": "플랫폼 API 키를 찾을 수 없습니다.",
        "en-US": "Platform API key not found.",
    },
    "admin.platform_api_key_inactive": {
        "ko-KR": "폐기된 플랫폼 API 키에는 이 작업을 수행할 수 없습니다.",
        "en-US": "This action is not available for a revoked platform API key.",
    },
    "admin.platform_api_key_encryption_unavailable": {
        "ko-KR": "플랫폼 API 키 암호화 설정을 사용할 수 없습니다.",
        "en-US": "Platform API key encryption is not configured.",
    },
    "admin.platform_api_key_issue_failed": {
        "ko-KR": "플랫폼 API 키를 발급하지 못했습니다.",
        "en-US": "Could not issue the platform API key.",
    },
    "admin.platform_api_key_name_required": {
        "ko-KR": "플랫폼 API 키 이름을 입력해 주세요.",
        "en-US": "Enter a platform API key name.",
    },
    "admin.platform_api_key_name_invalid": {
        "ko-KR": "플랫폼 API 키 이름에 제어 문자나 방향 제어 문자를 사용할 수 없습니다.",
        "en-US": "Platform API key names cannot contain control or bidirectional formatting characters.",
    },
    "admin.platform_api_key_scope_invalid": {
        "ko-KR": "플랫폼 API 키 범위가 올바르지 않습니다.",
        "en-US": "The platform API key scope is invalid.",
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
    "admin.image_model_registry_changed": {
        "ko-KR": "배포 후 이미지 제공자 목록이 변경되었습니다. 설정을 새로고침하세요.",
        "en-US": "The image provider registry changed after deployment. Refresh the settings.",
    },
    "admin.image_model_version_conflict": {
        "ko-KR": "다른 관리자가 이미지 모델 설정을 변경했습니다. 새로고침 후 다시 시도하세요.",
        "en-US": "Another administrator changed the image model settings. Refresh and try again.",
    },
    "admin.image_model_provider_not_found": {
        "ko-KR": "이미지 제공자를 찾을 수 없습니다: {provider_id}",
        "en-US": "Image provider not found: {provider_id}",
    },
    "admin.image_model_provider_not_registered": {
        "ko-KR": "등록되지 않은 이미지 제공자입니다: {provider_id}",
        "en-US": "Image provider is not registered: {provider_id}",
    },
    "admin.image_model_provider_not_configured": {
        "ko-KR": "이미지 제공자 설정을 먼저 저장하세요: {provider_id}",
        "en-US": "Configure the image provider first: {provider_id}",
    },
    "admin.image_model_provider_disabled": {
        "ko-KR": "이미지 제공자가 비활성화되어 있습니다: {provider_id}",
        "en-US": "Image provider is disabled: {provider_id}",
    },
    "admin.image_model_adapter_not_registered": {
        "ko-KR": "이미지 제공자의 실행 어댑터가 등록되지 않았습니다: {provider_id}",
        "en-US": "No runtime adapter is registered for image provider {provider_id}.",
    },
    "admin.image_model_key_not_allowed": {
        "ko-KR": "{provider_id} 이미지 제공자에는 API 키를 저장할 수 없습니다.",
        "en-US": "An API key cannot be stored for image provider {provider_id}.",
    },
    "admin.image_model_credential_required": {
        "ko-KR": "{provider_id} 이미지 제공자를 활성화하려면 API 키가 필요합니다.",
        "en-US": "An API key is required to enable image provider {provider_id}.",
    },
    "admin.image_model_credential_encryption_unavailable": {
        "ko-KR": "이미지 모델 API 키 암호화 설정을 사용할 수 없습니다.",
        "en-US": "Image model API key encryption is not configured.",
    },
    "admin.image_model_credential_reference_invalid": {
        "ko-KR": "저장된 이미지 생성 작업의 자격증명 참조가 올바르지 않습니다.",
        "en-US": "The saved image generation credential reference is invalid.",
    },
    "admin.image_model_execution_profile_invalid": {
        "ko-KR": "저장된 이미지 생성 작업이 현재 이미지 모델 설정과 호환되지 않습니다.",
        "en-US": "The saved image generation job is incompatible with the current image model settings.",
    },
    "admin.image_model_endpoint_invalid": {
        "ko-KR": "이미지 제공자 엔드포인트가 올바른 HTTP(S) URL이 아닙니다.",
        "en-US": "The image provider endpoint is not a valid HTTP(S) URL.",
    },
    "admin.image_model_endpoint_public_https_required": {
        "ko-KR": "외부 이미지 제공자 엔드포인트는 공개 HTTPS 주소여야 합니다.",
        "en-US": "An external image provider endpoint must be a public HTTPS address.",
    },
    "admin.image_model_endpoint_unresolvable": {
        "ko-KR": "이미지 제공자 엔드포인트의 호스트를 확인할 수 없습니다.",
        "en-US": "The image provider endpoint host could not be resolved.",
    },
    "admin.image_model_endpoint_required": {
        "ko-KR": "외부 이미지 제공자 엔드포인트가 필요합니다.",
        "en-US": "An external image provider endpoint is required.",
    },
    "admin.image_model_supervisor_model_required": {
        "ko-KR": "이미지 생성을 감독할 모델을 명시적으로 선택해야 합니다.",
        "en-US": "Select an image supervisor model explicitly.",
    },
    "admin.image_model_generation_model_required": {
        "ko-KR": "이미지 생성 모델을 명시적으로 선택해야 합니다.",
        "en-US": "Select an image generation model explicitly.",
    },
    "admin.image_model_provider_not_allowed": {
        "ko-KR": "보안 설정에서 허용되지 않은 외부 이미지 제공자입니다: {provider_id}",
        "en-US": "The external image provider is not allowed by security settings: {provider_id}",
    },
    "admin.image_model_active_provider_required": {
        "ko-KR": "사용할 이미지 제공자를 선택해야 합니다.",
        "en-US": "Select an active image provider.",
    },
    "admin.image_model_profile_unavailable": {
        "ko-KR": "이미지 모델 설정을 사용할 수 없습니다. 데이터베이스 마이그레이션을 확인하세요.",
        "en-US": "Image model settings are unavailable. Check the database migration.",
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
    "patent_automation.app_disabled": {
        "ko-KR": "이 워크스페이스에서 특허업무 자동화 앱이 비활성화되어 있습니다.",
        "en-US": "The patent work automation app is disabled for this workspace.",
    },
    "patent_automation.invalid_file": {
        "ko-KR": "XLSX 형식의 특허현황관리 파일만 가져올 수 있습니다.",
        "en-US": "Only XLSX patent-status files can be imported.",
    },
    "patent_automation.record_not_found": {
        "ko-KR": "특허 레코드를 찾을 수 없습니다.",
        "en-US": "Patent record not found.",
    },
    "patent_automation.cost_run_not_found": {
        "ko-KR": "비용 처리 결과를 찾을 수 없습니다.",
        "en-US": "Cost run not found.",
    },
    "patent_automation.upload_too_large": {
        "ko-KR": "업로드 파일 수 또는 총 용량이 허용 한도를 초과했습니다.",
        "en-US": "The number or total size of uploaded files exceeds the allowed limit.",
    },
    "meal_invoice_ocr.app_disabled": {
        "ko-KR": "이 워크스페이스에서 식당 명세서 OCR 앱이 비활성화되어 있습니다.",
        "en-US": "The meal invoice OCR app is disabled for this workspace.",
    },
    "meal_invoice_ocr.admin_required": {
        "ko-KR": "이 작업(학습 데이터·기준 카탈로그 관리)은 워크스페이스 관리자만 할 수 있습니다.",
        "en-US": "Only a workspace admin can manage shared learning data and the reference catalog.",
    },
    "meal_invoice_ocr.empty_upload": {
        "ko-KR": "OCR 할 명세표 파일을 업로드해야 합니다.",
        "en-US": "Upload at least one invoice file to run OCR.",
    },
    "meal_invoice_ocr.upload_too_large": {
        "ko-KR": "업로드 파일 수 또는 총 용량이 허용 한도를 초과했습니다.",
        "en-US": "The number or total size of uploaded files exceeds the allowed limit.",
    },
    "meal_invoice_ocr.too_many_files": {
        "ko-KR": "한 번에 올릴 수 있는 파일 수를 초과했습니다. 나눠서 업로드하세요.",
        "en-US": "Too many files in one request. Please upload in smaller batches.",
    },
    "meal_invoice_ocr.unsupported_file_type": {
        "ko-KR": "지원하지 않는 파일 형식입니다. 명세표는 PDF·이미지, 기준 카탈로그는 xlsx 만 업로드하세요.",
        "en-US": "Unsupported file type. Upload PDF/image invoices, or an xlsx reference catalog.",
    },
    "meal_invoice_ocr.image_not_found": {
        "ko-KR": "해당 교정의 원본 이미지를 찾을 수 없습니다.",
        "en-US": "The original image for this correction was not found.",
    },
    "meal_invoice_ocr.catalog_parse_failed": {
        "ko-KR": "기준 카탈로그 엑셀을 읽지 못했습니다. 대장 양식(품목·단위·단가 열)의 xlsx 인지 확인하세요.",
        "en-US": "Could not read the reference catalog. Ensure it is a ledger-format xlsx with item/unit/price columns.",
    },
    "plm.sql_read_only_required": {
        "ko-KR": "PLM SQL은 읽기 전용 SELECT여야 합니다.",
        "en-US": "PLM SQL must be a read-only SELECT.",
    },
    "plm.sql_single_statement_required": {
        "ko-KR": "PLM SQL은 단일 문장이어야 합니다.",
        "en-US": "PLM SQL must contain exactly one statement.",
    },
    "plm.sql_comments_not_allowed": {
        "ko-KR": "PLM 원천 조회 SQL에는 주석을 사용할 수 없습니다.",
        "en-US": "PLM raw SQL cannot contain comments.",
    },
    "plm.sql_forbidden_token": {
        "ko-KR": "PLM SQL에 허용되지 않은 토큰이 포함되어 있습니다: {token}",
        "en-US": "PLM SQL contains a forbidden token: {token}",
    },
    "plm.sql_table_not_allowed": {
        "ko-KR": "PLM SQL이 allowlist에 없는 테이블을 참조합니다.",
        "en-US": "PLM SQL references a non-allowlisted table.",
    },
    "plm.access_scope_denied": {
        "ko-KR": "PLM 템플릿 접근 범위 권한이 필요합니다.",
        "en-US": "PLM template access scope permission is required.",
    },
    "plm.raw_admin_required": {
        "ko-KR": "PLM 원천 데이터 조회는 워크스페이스 admin 권한이 필요합니다.",
        "en-US": "PLM raw data access requires workspace admin permission.",
    },
    "plm.object_name_invalid": {
        "ko-KR": "PLM 객체명이 올바르지 않습니다.",
        "en-US": "PLM object name is invalid.",
    },
    "plm.connection_config_missing": {
        "ko-KR": "PLM Oracle 접속 설정이 누락되었습니다: {keys}",
        "en-US": "PLM Oracle connection configuration is missing: {keys}",
    },
    "plm.ojdbc_jar_not_found": {
        "ko-KR": "PLM Oracle JDBC jar를 찾을 수 없습니다: {path}",
        "en-US": "PLM Oracle JDBC jar was not found: {path}",
    },
    "plm.jdbc_runner_compile_failed": {
        "ko-KR": "PLM JDBC 조회 실행기를 컴파일하지 못했습니다: {error}",
        "en-US": "Could not compile the PLM JDBC query runner: {error}",
    },
    "plm.query_timeout": {
        "ko-KR": "PLM 원천 조회 시간이 초과되었습니다.",
        "en-US": "PLM raw query timed out.",
    },
    "plm.query_failed": {
        "ko-KR": "PLM 원천 조회에 실패했습니다: {error}",
        "en-US": "PLM raw query failed: {error}",
    },
    "plm.query_result_invalid": {
        "ko-KR": "PLM 원천 조회 결과를 해석하지 못했습니다: {error}",
        "en-US": "Could not parse the PLM raw query result: {error}",
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
        "ko-KR": "아이두 챗봇에서는 PMS와 문서 컨텍스트 도구만 사용할 수 있습니다.",
        "en-US": "I-Do Chatbot can only use PMS and Docs context tools.",
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
    "images.feature_disabled": {
        "ko-KR": "이미지 위저드 기능이 비활성화되어 있습니다.",
        "en-US": "The image wizard feature is not enabled.",
    },
    "images.app_disabled": {
        "ko-KR": "이 워크스페이스에서 이미지 위저드 앱이 비활성화되어 있습니다.",
        "en-US": "The image wizard app is disabled for this workspace.",
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
    "spec_compare.not_found": {
        "ko-KR": "규격서 비교 작업을 찾을 수 없습니다.",
        "en-US": "Specification comparison job not found.",
    },
    "spec_compare.forbidden": {
        "ko-KR": "이 규격서 비교 작업에 접근할 권한이 없습니다.",
        "en-US": "You do not have access to this specification comparison job.",
    },
    "spec_compare.empty_upload": {
        "ko-KR": "업로드된 규격서 파일이 비어 있습니다.",
        "en-US": "Uploaded specification file is empty.",
    },
    "spec_compare.upload_too_large": {
        "ko-KR": "규격서 파일이 허용된 크기를 초과합니다.",
        "en-US": "Specification file exceeds the allowed size.",
    },
    "spec_compare.invalid_file_type": {
        "ko-KR": "PPTX, DOCX, PDF 규격서 파일만 비교할 수 있습니다.",
        "en-US": "Only PPTX, DOCX, and PDF specification files are supported.",
    },
    "spec_compare.upload_failed": {
        "ko-KR": "규격서 파일을 저장하지 못했습니다.",
        "en-US": "Failed to store the specification files.",
    },
    "spec_compare.dispatch_failed": {
        "ko-KR": "규격서 비교 작업을 큐에 전달하지 못했습니다.",
        "en-US": "Failed to dispatch the specification comparison job.",
    },
    "spec_compare.not_ready": {
        "ko-KR": "규격서 비교 결과가 아직 준비되지 않았습니다.",
        "en-US": "Specification comparison result is not ready yet.",
    },
    "writing_assistant.download_render_failed": {
        "ko-KR": "문서를 생성할 수 없습니다.",
        "en-US": "Unable to render the document.",
    },
    "writing_assistant.app_disabled": {
        "ko-KR": "이 워크스페이스에서 작성 도우미 앱이 비활성화되어 있습니다.",
        "en-US": "The writing assistant app is disabled for this workspace.",
    },
    "fmea_compare.invalid_file_type": {
        "ko-KR": ".xls 또는 .xlsx FMEA 파일만 지원합니다.",
        "en-US": "Only .xls or .xlsx FMEA files are supported.",
    },
    "fmea_compare.upload_too_large": {
        "ko-KR": "FMEA 파일이 허용된 크기를 초과합니다. 최대 50MB까지 업로드할 수 있습니다.",
        "en-US": "FMEA file exceeds the allowed size. Uploads are limited to 50 MB.",
    },
    "fmea_compare.parse_failed": {
        "ko-KR": "FMEA 데이터를 인식할 수 없습니다. 헤더 형식과 파일 내용을 확인하세요.",
        "en-US": "Could not recognize FMEA data. Check the header format and file contents.",
    },
    "fmea_compare.empty_data": {
        "ko-KR": "FMEA 데이터가 없습니다.",
        "en-US": "No FMEA data was provided.",
    },
    "imds_minerals.invalid_pdf_type": {
        "ko-KR": "IMDS 보고서는 .pdf 파일만 지원합니다.",
        "en-US": "The IMDS report must be a .pdf file.",
    },
    "imds_minerals.app_disabled": {
        "ko-KR": "이 워크스페이스에서 IMDS 책임광물 조사표 앱이 비활성화되어 있습니다.",
        "en-US": "The IMDS responsible minerals app is disabled for this workspace.",
    },
    "imds_minerals.invalid_template_type": {
        "ko-KR": "조사표 양식은 .xlsx 또는 .xlsm 파일만 지원합니다.",
        "en-US": "The survey template must be a .xlsx or .xlsm file.",
    },
    "imds_minerals.invalid_list_type": {
        "ko-KR": "조사대상품목 리스트는 .xlsx 또는 .xlsm 파일만 지원합니다.",
        "en-US": "The target-item list must be a .xlsx or .xlsm file.",
    },
    "imds_minerals.upload_too_large": {
        "ko-KR": "업로드 파일이 허용된 크기를 초과합니다. 최대 50MB까지 업로드할 수 있습니다.",
        "en-US": "The uploaded file exceeds the allowed size. Uploads are limited to 50 MB.",
    },
    "imds_minerals.parse_failed": {
        "ko-KR": "IMDS 보고서를 인식할 수 없습니다. PDF 내용과 트리 표 형식을 확인하세요.",
        "en-US": "Could not recognize the IMDS report. Check the PDF contents and tree table format.",
    },
    "imds_minerals.sheet_not_found": {
        "ko-KR": "양식에서 해당 시트를 찾을 수 없습니다. 시트 이름을 확인하세요.",
        "en-US": "The specified sheet was not found in the template. Check the sheet name.",
    },
    "imds_minerals.template_parse_failed": {
        "ko-KR": "조사표 양식을 인식할 수 없습니다. 엑셀 파일 내용을 확인하세요.",
        "en-US": "Could not recognize the survey template. Check the Excel file contents.",
    },
    "imds_minerals.list_parse_failed": {
        "ko-KR": "조사대상품목 리스트를 인식할 수 없습니다. 헤더(차종/OEM품번/DCC품번/품명)를 확인하세요.",
        "en-US": "Could not recognize the target-item list. Check the header (vehicle/OEM no./DCC no./part name).",
    },
    "document_translate.unsupported_file_type": {
        "ko-KR": "지원하지 않는 파일 형식입니다. (PDF/DOCX/XLSX/PPTX/TXT)",
        "en-US": "Unsupported file type. (PDF/DOCX/XLSX/PPTX/TXT)",
    },
    "document_translate.upload_too_large": {
        "ko-KR": "업로드 파일이 너무 큽니다. 최대 50MB까지 업로드할 수 있습니다.",
        "en-US": "Uploaded file is too large. Uploads are limited to 50 MB.",
    },
    "document_translate.invalid_mode": {
        "ko-KR": "지원하지 않는 모드입니다. (translate/summarize/extract)",
        "en-US": "Unsupported mode. (translate/summarize/extract)",
    },
    "document_translate.invalid_language": {
        "ko-KR": "지원하지 않는 출력 언어입니다. (ko/en/zh/ja/es/de)",
        "en-US": "Unsupported output language. (ko/en/zh/ja/es/de)",
    },
    "document_translate.invalid_summary_level": {
        "ko-KR": "지원하지 않는 요약 수준입니다. (brief/detailed)",
        "en-US": "Unsupported summary level. (brief/detailed)",
    },
    "document_translate.extraction_failed": {
        "ko-KR": "문서에서 텍스트를 추출하지 못했습니다. (스캔 이미지 PDF 등은 지원하지 않습니다)",
        "en-US": "Could not extract text from the document. (scanned/image-only PDFs are not supported)",
    },
    "document_translate.empty_text": {
        "ko-KR": "처리할 텍스트가 없습니다.",
        "en-US": "No text to process.",
    },
    "ppt_generator.upload_too_large": {
        "ko-KR": "업로드 파일이 너무 큽니다. 파일당 50MB, 전체 120MB까지 업로드할 수 있습니다.",
        "en-US": "Uploaded files are too large. Uploads are limited to 50 MB per file and 120 MB total.",
    },
    "ppt_generator.app_disabled": {
        "ko-KR": "이 워크스페이스에서 PPT 생성 도우미 앱이 비활성화되어 있습니다.",
        "en-US": "The PPT assistant app is disabled for this workspace.",
    },
    "ppt_generator.too_many_files": {
        "ko-KR": "첨부 파일은 최대 {max_count}개까지 업로드할 수 있습니다.",
        "en-US": "You can upload up to {max_count} attachment files.",
    },
    "ppt_generator.topic_too_long": {
        "ko-KR": "주제는 최대 {max_length}자까지 입력할 수 있습니다.",
        "en-US": "Topic is limited to {max_length} characters.",
    },
    "ppt_generator.instructions_too_long": {
        "ko-KR": "추가 지시사항은 최대 {max_length}자까지 입력할 수 있습니다.",
        "en-US": "Additional instructions are limited to {max_length} characters.",
    },
    "ppt_generator.form_field_too_long": {
        "ko-KR": "요청 값이 너무 깁니다. 최대 길이: {max_length}",
        "en-US": "Request value is too long. Maximum length: {max_length}",
    },
    "ppt_generator.enqueue_failed": {
        "ko-KR": "작업 큐에 등록하지 못했습니다. 잠시 후 다시 시도해 주세요.",
        "en-US": "Could not enqueue the PPT job. Try again shortly.",
    },
    "ppt_generator.empty_input": {
        "ko-KR": "생성할 주제나 첨부 자료를 입력하세요.",
        "en-US": "Enter a topic or attach source material.",
    },
    "ppt_generator.job_not_found": {
        "ko-KR": "PPT 생성 작업을 찾을 수 없습니다.",
        "en-US": "PPT generation job not found.",
    },
    "ppt_generator.job_not_cancellable": {
        "ko-KR": "이미 완료되었거나 취소할 수 없는 작업입니다.",
        "en-US": "This job is already finished or cannot be cancelled.",
    },
    "ppt_generator.family_not_found": {
        "ko-KR": "PPT 템플릿을 찾을 수 없습니다.",
        "en-US": "PPT template was not found.",
    },
    "ppt_generator.template_preview_admin_required": {
        "ko-KR": "PPT 템플릿 미리보기 관리는 워크스페이스 관리자만 할 수 있습니다.",
        "en-US": "Only workspace admins can manage PPT template previews.",
    },
    "ppt_generator.template_preview_media_unavailable": {
        "ko-KR": "업로드한 미리보기 이미지를 찾을 수 없습니다.",
        "en-US": "Uploaded preview image was not found.",
    },
    "ppt_generator.template_preview_limit_exceeded": {
        "ko-KR": "이 템플릿에 등록할 수 있는 미리보기 이미지 수를 초과했습니다.",
        "en-US": "This template has reached the preview image limit.",
    },
    "ppt_generator.template_preview_not_found": {
        "ko-KR": "PPT 템플릿 미리보기 이미지를 찾을 수 없습니다.",
        "en-US": "PPT template preview image was not found.",
    },
    "ppt_generator.file_not_ready": {
        "ko-KR": "PPT 파일이 아직 준비되지 않았습니다.",
        "en-US": "PPT file is not ready yet.",
    },
    "ppt_generator.file_not_found": {
        "ko-KR": "PPT 파일을 찾을 수 없습니다.",
        "en-US": "PPT file not found.",
    },
    "ppt_generator.job_not_ready": {
        "ko-KR": "PPT 생성이 아직 완료되지 않았습니다.",
        "en-US": "PPT generation is not complete yet.",
    },
    "ppt_generator.chat_in_progress": {
        "ko-KR": "이전 수정 요청을 아직 처리 중입니다.",
        "en-US": "The previous edit request is still being processed.",
    },
    "patent.kipris_not_configured": {
        "ko-KR": "KIPRIS API 키가 설정되지 않았습니다. 관리자에게 문의하세요.",
        "en-US": "KIPRIS API key is not configured. Contact your administrator.",
    },
    "patent.query_required": {
        "ko-KR": "검색어를 입력하세요.",
        "en-US": "Enter a search query.",
    },
    "patent.keyword_extract_failed": {
        "ko-KR": "검색 키워드를 추출하지 못했습니다. 짧은 키워드로 다시 시도하세요.",
        "en-US": "Could not extract search keywords. Try shorter keywords.",
    },
    "patent.search_failed": {
        "ko-KR": "AI 검색에 실패했습니다: {error}",
        "en-US": "Patent search failed: {error}",
    },
    "patent.number_required": {
        "ko-KR": "특허번호를 입력하세요.",
        "en-US": "Enter a patent number.",
    },
    "patent.fetch_failed": {
        "ko-KR": "특허 조회에 실패했습니다: {error}",
        "en-US": "Failed to fetch the patent: {error}",
    },
    "patent.not_found": {
        "ko-KR": "특허 정보를 찾을 수 없습니다: {number}",
        "en-US": "Patent not found: {number}",
    },
    "patent.foreign_not_found": {
        "ko-KR": "KIPRIS 해외 DB에서 {country} 번호로 문헌을 찾지 못했습니다(해외는 등록번호 색인이 불완전할 수 있음). Google Patents 원문: {url}",
        "en-US": "Could not find a {country} document by number in the KIPRIS foreign database (foreign registration numbers may be poorly indexed). Google Patents: {url}",
    },
    "patent.translate_input_too_large": {
        "ko-KR": "번역할 내용이 너무 많습니다. 청구항 수나 길이를 줄여 다시 시도해 주세요.",
        "en-US": "The text to translate is too large. Reduce the number or length of claims and try again.",
    },
    "patent.tech_required": {
        "ko-KR": "기술 설명을 입력하세요.",
        "en-US": "Enter a technology description.",
    },
    "patent.content_required": {
        "ko-KR": "연구/발명 내용을 입력하세요.",
        "en-US": "Enter the research/invention content.",
    },
    "patent.invalid_report_type": {
        "ko-KR": "유효하지 않은 보고서 유형입니다.",
        "en-US": "Invalid report type.",
    },
    "patent.invention_required": {
        "ko-KR": "발명 내용을 입력하세요.",
        "en-US": "Enter the invention content.",
    },
    "patent.message_required": {
        "ko-KR": "메시지를 입력하세요.",
        "en-US": "Enter a message.",
    },
    "patent.question_required": {
        "ko-KR": "질문을 입력하세요.",
        "en-US": "Enter a question.",
    },
    "patent.claims_required": {
        "ko-KR": "청구항 데이터가 없습니다.",
        "en-US": "No claims data.",
    },
    "patent.claims_required_fetch": {
        "ko-KR": "청구항 데이터가 없습니다. 먼저 특허번호를 조회하세요.",
        "en-US": "No claims data. Look up a patent number first.",
    },
    "patent.tech_description_required": {
        "ko-KR": "사내기술 설명을 입력하세요.",
        "en-US": "Enter the in-house technology description.",
    },
    "patent.app_no_required": {
        "ko-KR": "출원번호가 필요합니다.",
        "en-US": "Application number is required.",
    },
    "patent.empty_file": {
        "ko-KR": "업로드된 파일이 비어 있습니다.",
        "en-US": "The uploaded file is empty.",
    },
    "patent.unsupported_file": {
        "ko-KR": "지원하지 않는 파일 형식입니다. PPTX/PDF/DOCX/XLSX만 가능합니다.",
        "en-US": "Unsupported file type. Only PPTX/PDF/DOCX/XLSX are supported.",
    },
    "patent.extract_empty": {
        "ko-KR": "파일에서 텍스트를 추출하지 못했습니다.",
        "en-US": "Could not extract any text from the file.",
    },
    "patent.file_too_large": {
        "ko-KR": "파일이 너무 큽니다. 100MB 이하 파일만 업로드할 수 있습니다.",
        "en-US": "The file is too large. Upload files up to 100MB.",
    },
    "patent_prior_art.not_available": {
        "ko-KR": "특허 선행기술 조사 기능은 아직 활성화되지 않았습니다.",
        "en-US": "Patent prior-art search is not active yet.",
    },
    "patent_prior_art.request_too_large": {
        "ko-KR": "요청 본문이 너무 크거나 크기 정보를 확인할 수 없습니다.",
        "en-US": "The request body is too large or its size cannot be verified.",
    },
    "patent_prior_art.empty_upload": {
        "ko-KR": "업로드한 파일이 비어 있습니다.",
        "en-US": "The uploaded file is empty.",
    },
    "patent_prior_art.upload_too_large": {
        "ko-KR": "파일이 너무 큽니다. 50MB 이하 파일을 업로드하세요.",
        "en-US": "The file is too large. Upload a file up to 50MB.",
    },
    "patent_prior_art.invalid_file_type": {
        "ko-KR": "지원하지 않는 파일 형식입니다.",
        "en-US": "This file type is not supported.",
    },
    "patent_prior_art.parse_failed": {
        "ko-KR": "파일 내용을 안전하게 추출하지 못했습니다.",
        "en-US": "The file content could not be extracted safely.",
    },
    "patent_prior_art.extraction_empty": {
        "ko-KR": "파일에서 조사할 텍스트를 찾지 못했습니다.",
        "en-US": "No searchable text was found in the file.",
    },
    "patent_prior_art.invalid_scope": {
        "ko-KR": "선택한 조사 범위가 올바르지 않습니다.",
        "en-US": "The selected research scope is invalid.",
    },
    "patent_prior_art.not_found": {
        "ko-KR": "선행기술 조사 작업을 찾을 수 없습니다.",
        "en-US": "The prior-art research job could not be found.",
    },
    "patent_prior_art.not_cancellable": {
        "ko-KR": "이 선행기술 조사 작업은 취소할 수 없습니다.",
        "en-US": "This prior-art research job cannot be cancelled.",
    },
    "patent_prior_art.not_ready": {
        "ko-KR": "선행기술 조사 결과가 아직 준비되지 않았습니다.",
        "en-US": "The prior-art research result is not ready yet.",
    },
    "patent_prior_art.artifact_not_found": {
        "ko-KR": "선행기술 조사 결과 파일을 찾을 수 없습니다.",
        "en-US": "The prior-art research artifact could not be found.",
    },
    "patent_prior_art.artifact_read_failed": {
        "ko-KR": "선행기술 조사 결과 파일을 안전하게 읽지 못했습니다.",
        "en-US": "The prior-art research artifact could not be read safely.",
    },
    "patent_prior_art.dispatch_failed": {
        "ko-KR": "선행기술 조사 작업을 시작하지 못했습니다.",
        "en-US": "The prior-art research job could not be started.",
    },
    "patent_prior_art.storage_failed": {
        "ko-KR": "선행기술 조사 파일을 안전하게 저장하거나 읽지 못했습니다.",
        "en-US": "The prior-art research file could not be stored or read safely.",
    },
    "news.admin_only": {
        "ko-KR": "뉴스 관리 권한이 필요합니다.",
        "en-US": "News administrator access is required.",
    },
    "news.article_not_found": {
        "ko-KR": "수집된 뉴스 기사를 찾을 수 없습니다.",
        "en-US": "The collected news article could not be found.",
    },
    "news.fetch_started": {
        "ko-KR": "뉴스 수집을 시작했습니다.",
        "en-US": "News collection has started.",
    },
    "news.missing_query": {
        "ko-KR": "검색어가 필요합니다.",
        "en-US": "A search query is required.",
    },
    "news.missing_url": {
        "ko-KR": "기사 URL이 필요합니다.",
        "en-US": "An article URL is required.",
    },
    "news.unknown_channel": {
        "ko-KR": "지원하지 않는 뉴스 채널입니다.",
        "en-US": "Unsupported news channel.",
    },
    "news.saved_not_found": {
        "ko-KR": "저장된 뉴스를 찾을 수 없습니다.",
        "en-US": "Saved news article not found.",
    },
    "news.recommended_not_found": {
        "ko-KR": "추천 뉴스를 찾을 수 없습니다.",
        "en-US": "Recommended news article not found.",
    },
    "news.scrap_not_found": {
        "ko-KR": "스크랩한 뉴스를 찾을 수 없습니다.",
        "en-US": "Scrapped news article not found.",
    },
    "industry_report.admin_only": {
        "ko-KR": "산업리포트 관리 권한이 필요합니다.",
        "en-US": "Industry report administrator access is required.",
    },
    "industry_report.empty_file": {
        "ko-KR": "업로드 파일이 비어 있습니다.",
        "en-US": "The uploaded file is empty.",
    },
    "industry_report.fetch_started": {
        "ko-KR": "산업리포트 수집을 시작했습니다.",
        "en-US": "Industry report collection has started.",
    },
    "industry_report.file_not_found": {
        "ko-KR": "리포트 파일을 찾을 수 없습니다.",
        "en-US": "The report file could not be found.",
    },
    "industry_report.file_too_large": {
        "ko-KR": "업로드 파일이 너무 큽니다.",
        "en-US": "The uploaded file is too large.",
    },
    "industry_report.invalid_issue_id": {
        "ko-KR": "지원하지 않는 오토저널 발행 ID입니다.",
        "en-US": "Unsupported Autojournal issue id.",
    },
    "industry_report.invalid_kdi_url": {
        "ko-KR": "지원하지 않는 KDI URL입니다.",
        "en-US": "Unsupported KDI URL.",
    },
    "industry_report.issue_unavailable": {
        "ko-KR": "오토저널 발행 정보를 가져올 수 없습니다.",
        "en-US": "The Autojournal issue could not be loaded.",
    },
    "industry_report.unknown_company": {
        "ko-KR": "지원하지 않는 산업리포트 회사입니다.",
        "en-US": "Unsupported industry report company.",
    },
    "industry_report.save_invalid": {
        "ko-KR": "저장할 산업 리포트 정보가 올바르지 않습니다.",
        "en-US": "Invalid industry report to save.",
    },
    "industry_report.saved_not_found": {
        "ko-KR": "저장된 산업 리포트를 찾을 수 없습니다.",
        "en-US": "Saved industry report not found.",
    },
    "industry_report.recommended_not_found": {
        "ko-KR": "추천 산업 리포트를 찾을 수 없습니다.",
        "en-US": "Recommended industry report not found.",
    },
    "industry_report.scrap_not_found": {
        "ko-KR": "스크랩한 산업 리포트를 찾을 수 없습니다.",
        "en-US": "Scrapped industry report not found.",
    },
    "industry_report.unknown_source": {
        "ko-KR": "지원하지 않는 산업리포트 소스입니다.",
        "en-US": "Unsupported industry report source.",
    },
    "industry_report.unsupported_file_type": {
        "ko-KR": "PDF 파일만 업로드할 수 있습니다.",
        "en-US": "Only PDF files can be uploaded.",
    },
    "lawsearch.competitor_not_found": {
        "ko-KR": "경쟁사를 찾을 수 없습니다.",
        "en-US": "Competitor not found.",
    },
    "lawsearch.item_not_found": {
        "ko-KR": "법규/규제 항목을 찾을 수 없습니다.",
        "en-US": "Law / regulation entry not found.",
    },
    "lawsearch.part_not_found": {
        "ko-KR": "부품을 찾을 수 없습니다.",
        "en-US": "Part not found.",
    },
    "lawsearch.region_not_found": {
        "ko-KR": "지역을 찾을 수 없습니다.",
        "en-US": "Region not found.",
    },
    "lawsearch.type_not_found": {
        "ko-KR": "규제 유형을 찾을 수 없습니다.",
        "en-US": "Regulation type not found.",
    },
    "lawsearch.validation_failed": {
        "ko-KR": "입력 검증에 실패했습니다.",
        "en-US": "Input validation failed.",
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
