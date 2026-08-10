from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
from typing import Any, Literal

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Path,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from open_alm_api.core.db import get_db_session
from open_alm_api.core.i18n import localized_http_exception
from open_alm_api.core.settings import get_settings
from open_alm_api.openapi_contract import ErrorResponse
from open_alm_api.domains.auth.dependencies import (
    require_current_user,
    require_current_workspace,
    require_workspace_membership,
)
from open_alm_api.domains.auth.access import record_audit_log
from open_alm_api.domains.auth.models import User, Workspace, utcnow_naive
from open_alm_api.domains.auth.security import new_id
from open_alm_api.domains.auth.workspace_app_gate import require_workspace_app_enabled
from open_alm_api.domains.legacy_issues.app_catalog import LEGACY_ISSUES_WORKSPACE_APP
from open_alm_api.domains.dm import (
    conversation_lifecycle,
    conversation_queries,
    message_delivery,
    message_flow,
)
from open_alm_api.domains.dm import realtime_event_types as dm_realtime_event_types
from open_alm_api.domains.dm.models import DmConversation, DmMessage
from open_alm_api.domains.dm.realtime_events import DmEventPublisher
from open_alm_api.domains.notifications import (
    realtime_event_types as notification_realtime_event_types,
)
from open_alm_api.domains.notifications import service as notification_service
from open_alm_api.domains.pms.models import Notification
from open_alm_api.domains.legacy_issues.history import (
    LEGACY_ISSUE_RECORD_KIND,
    collect_value_changes,
    list_record_history,
)
from open_alm_api.domains.legacy_issues.ai_assistant import (
    LegacyIssueAssistantResult,
    run_legacy_issue_assistant,
)
from open_alm_api.domains.legacy_issues.ai_search import (
    LegacyIssueAssistantSearchPlan,
    LegacyIssueEvidence,
    LegacyIssueMatchedChunk,
    LegacyIssueSearchProfile,
    delete_legacy_issue_record_ai_chunks,
    reindex_legacy_issue_record_ai_chunks,
    reindex_legacy_issue_revision_ai_chunks,
)
from open_alm_api.domains.legacy_issues.assistant_reports import (
    get_legacy_issue_report_query,
    get_visible_legacy_issue_report,
    legacy_issue_report_counts,
    list_legacy_issue_assistant_reports,
    list_legacy_issue_report_queries,
    list_legacy_issue_report_sources,
    list_legacy_issue_reports,
    report_owner,
    report_question,
)
from open_alm_api.domains.ai_artifacts.models import (
    AiArtifact,
    AiArtifactQuery,
    AiArtifactSource,
)
from open_alm_api.domains.ai_artifacts.repository import (
    AiArtifactNotFoundError,
    AiArtifactRepository,
)
from open_alm_api.domains.legacy_issues.attachment_indexing import (
    delete_legacy_issue_attachment_index_data,
    enqueue_legacy_issue_attachment_index_job,
)
from open_alm_api.domains.legacy_issues.models import (
    LegacyIssueAttachment,
    LegacyIssueAssistantRun,
    LegacyIssueDataRevision,
    LegacyIssueDataRevisionEvent,
    LegacyIssueExcelExportJob,
    LegacyIssueRecord,
    LegacyIssueRecordHistory,
    LegacyIssueRevisionMeetingAttachment,
    LegacyIssueRevisionOverviewHistory,
    LegacyIssueVehicleModuleChecklistAttachment,
)
from open_alm_api.domains.legacy_issues.column_orders import (
    COLUMN_ORDER_ATTACHMENT_KEY,
    get_column_order,
    normalize_column_order_view_key,
    upsert_column_order,
)
from open_alm_api.domains.legacy_issues.excel_exports import (
    create_dataset_excel_export_job,
    create_vehicle_module_checklist_excel_export_job,
    excel_export_includes_attachments,
    excel_export_job_status,
    get_excel_export_job,
    open_excel_export_result,
)
from open_alm_api.domains.legacy_issues.grid_preferences import (
    GRID_PREFERENCE_MAX_COLUMN_KEYS,
    GRID_PREFERENCE_MAX_FROZEN_COLUMN_COUNT,
    GRID_PREFERENCE_MAX_KEY_LENGTH,
    LegacyIssueGridPreferenceDTO,
    LegacyIssueGridPreferenceKind,
    delete_grid_preference,
    get_grid_preference,
    normalize_grid_preference_column_keys,
    normalize_grid_preference_scope_key,
    upsert_grid_preference,
)
from open_alm_api.domains.legacy_issues.module_fields import (
    LegacyIssueModuleFieldDTO,
    create_module_field,
    deactivate_module_field,
    ensure_legacy_issue_module_manager,
    get_module_field_row,
    list_module_fields,
    reorder_module_fields,
    update_module_field,
)
from open_alm_api.domains.legacy_issues.module_direct_editors import (
    LegacyIssueModuleDirectEditorDTO,
    can_user_direct_edit_module,
    grant_module_direct_editor,
    list_module_direct_editors,
    revoke_module_direct_editor,
)
from open_alm_api.domains.legacy_issues.dataset_records import (
    EXPORT_RECORD_ID_HEADER,
    DATASET_DEFINITIONS,
    DATASET_RECORD_EXPORT_LIMIT,
    LegacyIssueDatasetDefinition,
    DatasetSystemFieldSettingView,
    DatasetAttachmentUpload,
    build_import_preview,
    canonicalize_dataset_values,
    compare_dataset_revisions,
    create_dataset_draft_revision,
    create_dataset_record,
    delete_dataset_attachment,
    delete_dataset_record,
    display_dataset_value,
    export_dataset_records_xlsx,
    field_labels,
    get_dataset_attachment,
    get_dataset_definition,
    get_dataset_definition_for_view as get_dataset_definition_for_view_unchecked,
    get_dataset_definition_with_all_module_fields,
    get_dataset_record,
    import_dataset_records,
    list_system_field_setting_views,
    list_dataset_attachments_for_records,
    list_dataset_records,
    normalize_legacy_issue_module_key,
    org_unit_path,
    org_units_by_id,
    open_dataset_attachment_content,
    parse_mapping_json,
    refresh_dataset_record_projections,
    set_dataset_attachment_primary,
    stamp_introduced_revision_numbers,
    update_dataset_attachment_description,
    update_dataset_record,
    upload_dataset_attachment,
    upsert_system_field_setting,
)
from open_alm_api.domains.legacy_issues.revisioning import (
    REVISION_STATUS_DRAFT,
    REVISION_STATUS_PUBLISHED,
    cancel_draft_revision,
    can_direct_edit_published_revision,
    complete_revision_approval,
    complete_revision_review,
    create_revision_overview_history,
    delete_revision_overview_history,
    get_active_draft_revision,
    get_revision,
    hide_revision_from_overview_history,
    invalidate_revision_approval_for_content_change,
    list_revision_overview_history,
    list_revision_events,
    list_revisions,
    legacy_issue_dataset_revision_key,
    publish_draft_revision,
    release_draft_revision_editing,
    request_revision_approval,
    require_draft_revision_editor,
    require_record_revision_editor,
    resolve_read_revision,
    update_revision_approval_assignees,
    update_revision_note,
    update_revision_overview_history,
)
from open_alm_api.domains.legacy_issues.revision_meeting_attachments import (
    can_delete_revision_meeting_attachment,
    delete_revision_meeting_attachment,
    find_existing_revision_meeting_attachment_upload,
    list_revision_meeting_attachments,
    open_revision_meeting_attachment,
    process_pending_revision_meeting_attachment_cleanups,
    read_revision_meeting_attachment_upload,
    recover_revision_meeting_attachment_upload_commit,
    update_revision_meeting_attachment_description,
    upload_revision_meeting_attachment,
)
from open_alm_api.domains.legacy_issues.module_access import (
    enabled_legacy_issue_module_keys,
    require_compressor_module_enabled,
)
from open_alm_api.domains.legacy_issues.vehicle_checklists import (
    complete_vehicle_checklist_revision,
    create_vehicle_checklist_revision,
    create_vehicle_model,
    create_vehicle_stage,
    deactivate_vehicle_model,
    delete_vehicle_checklist_revision,
    list_vehicle_stages,
    list_published_master_revisions,
    list_vehicle_checklist_history,
    list_vehicle_checklist_records,
    list_vehicle_checklist_revisions,
    list_vehicle_models,
    permanently_delete_vehicle_model,
    reopen_vehicle_checklist_revision,
    update_vehicle_checklist_records,
    update_vehicle_model,
    update_vehicle_stage,
    vehicle_checklist_summaries,
    vehicle_generated_checklist_counts,
    vehicle_stages_by_vehicle_model_ids,
)
from open_alm_api.domains.legacy_issues.vehicle_module_checklists import (
    complete_vehicle_module_checklist,
    create_vehicle_module_checklist,
    delete_vehicle_module_checklist,
    get_vehicle_module_checklist,
    import_previous_stage_vehicle_module_checklist,
    list_prior_stage_completed_vehicle_module_checklists,
    list_published_module_master_revisions,
    list_vehicle_module_checklist_history,
    list_vehicle_module_checklist_records,
    list_vehicle_module_checklists,
    list_vehicle_module_summaries,
    reopen_vehicle_module_checklist,
    update_vehicle_module_checklist_records,
)
from open_alm_api.domains.legacy_issues.vehicle_module_checklist_attachments import (
    delete_vehicle_module_checklist_attachment,
    list_vehicle_module_checklist_attachments_for_records,
    open_vehicle_module_checklist_attachment,
    process_pending_vehicle_module_checklist_attachment_cleanups,
    read_vehicle_module_checklist_attachment_upload,
    remove_uploaded_vehicle_module_checklist_attachment,
    upload_vehicle_module_checklist_attachment,
)
from open_alm_api.domains.legacy_issues.settings import get_legacy_issue_settings
from open_alm_api.domains.retrieval.partitioning import resolve_read_scope


require_legacy_issues_app_enabled = require_workspace_app_enabled(
    LEGACY_ISSUES_WORKSPACE_APP.app_id,
    error_code="legacy_issues.app_disabled",
)


router = APIRouter(
    prefix="/legacy-issues",
    tags=["legacy-issues"],
    dependencies=[Depends(require_legacy_issues_app_enabled)],
)


def _compressor_enabled() -> bool:
    return get_settings().legacy_issue_compressor_enabled


def _require_enabled_module(module_key: str | None) -> None:
    require_compressor_module_enabled(
        module_key,
        compressor_enabled=_compressor_enabled(),
    )


def _enabled_module_keys() -> frozenset[str]:
    return enabled_legacy_issue_module_keys(compressor_enabled=_compressor_enabled())


def _raise_vehicle_checklist_transition_read_only() -> None:
    raise localized_http_exception(
        status_code=status.HTTP_409_CONFLICT,
        code="legacy_issues.vehicle_checklist_transition_read_only",
    )


def get_dataset_definition_for_view(
    db: Session,
    *,
    dataset_key: str,
    workspace: Workspace,
    view_key: str | None = None,
    include_inactive_module_fields: bool = False,
) -> LegacyIssueDatasetDefinition:
    _require_enabled_module(view_key)
    return get_dataset_definition_for_view_unchecked(
        db,
        dataset_key=dataset_key,
        workspace=workspace,
        view_key=view_key,
        include_inactive_module_fields=include_inactive_module_fields,
    )


def _module_revision_dataset_key(
    definition: LegacyIssueDatasetDefinition,
    view_key: str | None,
) -> str:
    _require_enabled_module(view_key)
    module_key = normalize_legacy_issue_module_key(view_key)
    if module_key is None:
        raise localized_http_exception(
            status_code=409,
            code="legacy_issues.aggregate_readonly",
        )
    return legacy_issue_dataset_revision_key(definition.key, module_key)


def _require_module_record_editor(
    db: Session,
    *,
    definition: LegacyIssueDatasetDefinition,
    workspace: Workspace,
    user: User,
    view_key: str | None,
    revision_id: str | None,
) -> tuple[str, LegacyIssueDataRevision]:
    _require_enabled_module(view_key)
    module_key = normalize_legacy_issue_module_key(view_key)
    if module_key is None:
        raise localized_http_exception(
            status_code=409,
            code="legacy_issues.aggregate_readonly",
        )
    revision = require_record_revision_editor(
        db,
        workspace=workspace,
        dataset_key=legacy_issue_dataset_revision_key(definition.key, module_key),
        module_key=module_key,
        user=user,
        revision_id=revision_id,
    )
    return module_key, revision


def _latest_module_revisions(
    db: Session,
    *,
    definition: LegacyIssueDatasetDefinition,
    workspace: Workspace,
) -> list[LegacyIssueDataRevision]:
    revisions: list[LegacyIssueDataRevision] = []
    for module_key in sorted(_enabled_module_keys()):
        context = resolve_read_revision(
            db,
            workspace=workspace,
            dataset_key=legacy_issue_dataset_revision_key(definition.key, module_key),
        )
        revisions.append(context.current)
    return revisions


def _record_revision_dataset_key(
    definition: LegacyIssueDatasetDefinition,
    record: LegacyIssueRecord,
) -> str:
    _require_enabled_module(record.module_key)
    module_key = normalize_legacy_issue_module_key(record.module_key)
    if module_key is None:
        raise localized_http_exception(
            status_code=409,
            code="legacy_issues.aggregate_readonly",
        )
    return legacy_issue_dataset_revision_key(definition.key, module_key)


class LegacyIssueDatasetFieldItem(BaseModel):
    key: str
    label_ko: str
    label_en: str
    group_key: str | None = None
    field_type: str = "text"
    options: list[str] = Field(default_factory=list)
    allow_multiple: bool = False
    required: bool = False
    source: str = "system"
    module_key: str | None = None
    field_id: str | None = None
    active: bool = True
    readonly: bool = False


class LegacyIssueDatasetItem(BaseModel):
    key: str
    title_ko: str
    title_en: str
    hierarchy_ko: list[str]
    hierarchy_en: list[str]
    header_rows: int
    fields: list[LegacyIssueDatasetFieldItem]
    group_labels_ko: dict[str, str] = Field(default_factory=dict)
    group_labels_en: dict[str, str] = Field(default_factory=dict)


class LegacyIssueDatasetListResponse(BaseModel):
    items: list[LegacyIssueDatasetItem]


class LegacyIssueModuleFieldItem(BaseModel):
    id: str
    module_key: str
    field_key: str
    label_ko: str
    label_en: str
    field_type: str
    options: list[str] = Field(default_factory=list)
    allow_multiple: bool
    required: bool
    sort_order: int
    active: bool
    created_at: Any
    updated_at: Any


class LegacyIssueModuleFieldListResponse(BaseModel):
    items: list[LegacyIssueModuleFieldItem] = Field(default_factory=list)


class LegacyIssueSystemFieldItem(BaseModel):
    id: str | None = None
    dataset_key: str
    key: str
    label_ko: str
    label_en: str
    group_key: str | None = None
    field_type: str = "text"
    options: list[str] = Field(default_factory=list)
    allow_multiple: bool = False
    required: bool = False
    source: str = "system"
    module_key: str | None = None
    field_id: str | None = None
    active: bool = True
    readonly: bool = False
    updated_at: Any | None = None


class LegacyIssueSystemFieldListResponse(BaseModel):
    items: list[LegacyIssueSystemFieldItem] = Field(default_factory=list)


class LegacyIssueModuleFieldCreateRequest(BaseModel):
    module_key: str = Field(..., min_length=1, max_length=80)
    label_ko: str = Field(..., min_length=1, max_length=120)
    label_en: str | None = Field(default=None, max_length=120)
    field_type: str = Field(default="text", max_length=24)
    options: list[str] | None = Field(default=None, max_length=100)
    allow_multiple: bool = False
    required: bool = False
    sort_order: int | None = Field(default=None, ge=0)


class LegacyIssueModuleFieldUpdateRequest(BaseModel):
    label_ko: str | None = Field(default=None, min_length=1, max_length=120)
    label_en: str | None = Field(default=None, max_length=120)
    field_type: str | None = Field(default=None, max_length=24)
    options: list[str] | None = Field(default=None, max_length=100)
    allow_multiple: bool | None = None
    required: bool | None = None
    sort_order: int | None = Field(default=None, ge=0)
    active: bool | None = None


class LegacyIssueSystemFieldUpdateRequest(BaseModel):
    dataset_key: str = Field(default="common-master", min_length=1, max_length=80)
    label_ko: str | None = Field(default=None, min_length=1, max_length=120)
    label_en: str | None = Field(default=None, max_length=120)
    field_type: str | None = Field(default=None, max_length=24)
    options: list[str] | None = Field(default=None, max_length=100)
    allow_multiple: bool | None = None
    required: bool | None = None


class LegacyIssueOrgUnitItem(BaseModel):
    id: str
    name: str
    slug: str
    parent_id: str | None = None
    path: str


@router.get("/org-units", response_model=list[LegacyIssueOrgUnitItem])
def search_legacy_issue_org_units(
    q: str = Query(default="", max_length=120),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db_session),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> list[LegacyIssueOrgUnitItem]:
    _ = current_workspace
    normalized_query = " ".join(q.strip().split()).casefold()
    units_by_id = org_units_by_id(db)
    items = sorted(units_by_id.values(), key=lambda item: (item.name.casefold(), item.slug))
    if normalized_query:
        items = [
            item
            for item in items
            if normalized_query in item.name.casefold()
            or normalized_query in item.slug.casefold()
            or normalized_query in org_unit_path(item, units_by_id).casefold()
        ]
    return [
        LegacyIssueOrgUnitItem(
            id=item.id,
            name=item.name,
            slug=item.slug,
            parent_id=item.parent_id,
            path=org_unit_path(item, units_by_id),
        )
        for item in items[:limit]
    ]


class LegacyIssueModuleFieldReorderRequest(BaseModel):
    module_key: str = Field(..., min_length=1, max_length=80)
    field_ids: list[str] = Field(..., min_length=1, max_length=200)


class LegacyIssueColumnOrderItem(BaseModel):
    view_key: str
    column_order: list[str] = Field(default_factory=list)
    hidden_column_keys: list[str] = Field(default_factory=list)
    updated_at: Any | None = None


class LegacyIssueColumnOrderUpdateRequest(BaseModel):
    column_order: list[str] = Field(..., min_length=1, max_length=200)
    hidden_column_keys: list[str] | None = Field(default=None, max_length=200)


class LegacyIssueGridPreferenceItem(BaseModel):
    grid_kind: LegacyIssueGridPreferenceKind
    grid_key: str
    column_order: list[str]
    hidden_column_keys: list[str]
    frozen_column_count: int
    revision: int
    created_at: datetime
    updated_at: datetime


class LegacyIssueGridPreferenceResponse(BaseModel):
    preference: LegacyIssueGridPreferenceItem | None
    revision: int


class LegacyIssueGridPreferenceUpdateRequest(BaseModel):
    expected_revision: int = Field(..., ge=0, strict=True)
    column_order: list[str] = Field(
        ...,
        max_length=GRID_PREFERENCE_MAX_COLUMN_KEYS,
    )
    hidden_column_keys: list[str] = Field(
        ...,
        max_length=GRID_PREFERENCE_MAX_COLUMN_KEYS,
    )
    frozen_column_count: int = Field(
        ...,
        ge=0,
        le=GRID_PREFERENCE_MAX_FROZEN_COLUMN_COUNT,
        strict=True,
    )

    @field_validator("column_order", "hidden_column_keys")
    @classmethod
    def normalize_column_keys(cls, value: list[str]) -> list[str]:
        return normalize_grid_preference_column_keys(value)


class LegacyIssueVehicleModelItem(BaseModel):
    id: str
    vehicle_code: str
    vehicle_name: str | None = None
    notes: str | None = None
    active: bool
    stages: list["LegacyIssueVehicleStageItem"] = Field(default_factory=list)
    generated_checklist_count: int = 0
    checklist_summary: "LegacyIssueVehicleChecklistSummary | None" = None
    created_at: Any
    updated_at: Any


class LegacyIssueVehicleModelListResponse(BaseModel):
    items: list[LegacyIssueVehicleModelItem] = Field(default_factory=list)


class LegacyIssueVehicleModelCreateRequest(BaseModel):
    vehicle_code: str = Field(..., min_length=1, max_length=80)
    vehicle_name: str | None = Field(default=None, max_length=160)
    notes: str | None = Field(default=None, max_length=1000)
    initial_stage_name: str = Field(..., min_length=1, max_length=80)

    @field_validator("vehicle_code", mode="before")
    @classmethod
    def normalize_vehicle_code(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())

    @field_validator("vehicle_name", "notes", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: Any) -> str | None:
        if value is None:
            return None
        normalized = " ".join(str(value).strip().split())
        return normalized or None

    @field_validator("initial_stage_name", mode="before")
    @classmethod
    def normalize_initial_stage_name(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())


class LegacyIssueVehicleModelUpdateRequest(BaseModel):
    vehicle_code: str | None = Field(default=None, min_length=1, max_length=80)
    vehicle_name: str | None = Field(default=None, max_length=160)
    notes: str | None = Field(default=None, max_length=1000)
    active: bool | None = None

    @field_validator("vehicle_code", mode="before")
    @classmethod
    def normalize_vehicle_code(cls, value: Any) -> str | None:
        if value is None:
            return None
        return " ".join(str(value).strip().split())

    @field_validator("vehicle_name", "notes", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: Any) -> str | None:
        if value is None:
            return None
        normalized = " ".join(str(value).strip().split())
        return normalized or None


class LegacyIssueVehicleStageItem(BaseModel):
    id: str
    vehicle_model_id: str
    name: str
    sequence_no: int
    previous_stage_id: str | None = None
    created_by_id: str | None = None
    created_at: Any
    updated_at: Any


class LegacyIssueVehicleStageListResponse(BaseModel):
    items: list[LegacyIssueVehicleStageItem] = Field(default_factory=list)


class LegacyIssueVehicleStageCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())


class LegacyIssueVehicleStageUpdateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())


def _validate_excel_export_column_keys(
    value: list[str] | None,
) -> list[str] | None:
    if value is None:
        return None
    normalized = [item.strip() for item in value]
    if any(not item or len(item) > 120 for item in normalized):
        raise ValueError("column_keys entries must be 1 to 120 characters")
    if len(normalized) != len(set(normalized)):
        raise ValueError("column_keys entries must be unique")
    return normalized


def _validate_excel_export_record_ids(
    value: list[str] | None,
) -> list[str] | None:
    if value is None:
        return None
    normalized = [item.strip() for item in value]
    if any(not item or len(item) > 36 for item in normalized):
        raise ValueError("record_ids entries must be 1 to 36 characters")
    if len(normalized) != len(set(normalized)):
        raise ValueError("record_ids entries must be unique")
    return normalized


class LegacyIssueExcelExportCreateRequest(BaseModel):
    revision_id: str | None = Field(default=None, max_length=36)
    view_key: str | None = Field(default=None, max_length=80)
    departments: list[str] = Field(default_factory=list, max_length=200)
    column_keys: list[str] | None = Field(default=None, max_length=200)
    record_ids: list[str] | None = Field(
        default=None,
        max_length=DATASET_RECORD_EXPORT_LIMIT,
    )
    include_attachments: bool = True

    @field_validator("column_keys")
    @classmethod
    def validate_column_keys(cls, value: list[str] | None) -> list[str] | None:
        return _validate_excel_export_column_keys(value)

    @field_validator("record_ids")
    @classmethod
    def validate_record_ids(cls, value: list[str] | None) -> list[str] | None:
        return _validate_excel_export_record_ids(value)


class LegacyIssueChecklistExcelExportCreateRequest(BaseModel):
    column_keys: list[str] | None = Field(default=None, max_length=200)
    include_attachments: bool = True

    @field_validator("column_keys")
    @classmethod
    def validate_column_keys(cls, value: list[str] | None) -> list[str] | None:
        return _validate_excel_export_column_keys(value)


class LegacyIssueExcelExportJobItem(BaseModel):
    id: str
    status: Literal["queued", "running", "completed", "failed", "expired"]
    source_kind: Literal["dataset", "vehicle_module_checklist"]
    include_attachments: bool
    record_count: int
    attachment_count: int
    attachment_bytes: int
    processed_attachment_count: int
    processed_attachment_bytes: int
    result_filename: str | None = None
    result_size_bytes: int | None = None
    error_code: str | None = None
    created_at: Any
    updated_at: Any
    completed_at: Any | None = None
    expires_at: Any | None = None


class LegacyIssueVehicleChecklistMasterRevisionItem(BaseModel):
    id: str
    revision_no: int | None = None


class LegacyIssueVehicleChecklistSummaryItem(BaseModel):
    revision_id: str
    source_master_revision_no: int | None = None
    updated_at: Any


class LegacyIssueVehicleChecklistSummary(BaseModel):
    latest_draft: LegacyIssueVehicleChecklistSummaryItem | None = None
    latest_completed: LegacyIssueVehicleChecklistSummaryItem | None = None


class LegacyIssueVehicleChecklistRevisionItem(BaseModel):
    id: str
    vehicle_model_id: str
    revision_no: int
    status: str
    source_dataset_key: str
    source_master_revision_id: str
    source_master_revision_no: int | None = None
    row_count: int
    created_by_id: str | None = None
    completed_by_id: str | None = None
    completed_at: Any | None = None
    created_at: Any
    updated_at: Any


class LegacyIssueVehicleChecklistRevisionListResponse(BaseModel):
    items: list[LegacyIssueVehicleChecklistRevisionItem] = Field(default_factory=list)
    latest_master_revision: LegacyIssueVehicleChecklistMasterRevisionItem | None = None
    master_revisions: list[LegacyIssueVehicleChecklistMasterRevisionItem] = Field(
        default_factory=list
    )


class LegacyIssueVehicleChecklistRevisionCreateRequest(BaseModel):
    source_master_revision_id: str | None = Field(default=None, max_length=80)


class LegacyIssueVehicleChecklistRecordItem(BaseModel):
    id: str
    checklist_revision_id: str
    source_record_id: str
    source_stable_record_id: str | None = None
    source_module_key: str | None = None
    values: dict[str, Any] = Field(default_factory=dict)
    created_at: Any
    updated_at: Any


class LegacyIssueVehicleChecklistRecordListResponse(BaseModel):
    definition: LegacyIssueDatasetItem
    items: list[LegacyIssueVehicleChecklistRecordItem] = Field(default_factory=list)
    revision: LegacyIssueVehicleChecklistRevisionItem
    total: int
    limit: int | None
    offset: int


class LegacyIssueVehicleChecklistRecordBatchUpdateItem(BaseModel):
    record_id: str
    values: dict[str, Any | None] = Field(default_factory=dict)


class LegacyIssueVehicleChecklistRecordBatchSaveRequest(BaseModel):
    updates: list[LegacyIssueVehicleChecklistRecordBatchUpdateItem] = Field(default_factory=list)


class LegacyIssueVehicleChecklistRecordBatchSaveResponse(BaseModel):
    items: list[LegacyIssueVehicleChecklistRecordItem] = Field(default_factory=list)
    updated: int = 0


class LegacyIssueVehicleChecklistHistoryItem(BaseModel):
    id: str
    action: str
    record_id: str
    record_label: str | None = None
    source_module_key: str | None = None
    source_master_revision_no: int | None = None
    field_key: str | None = None
    field_label: str | None = None
    old_value: str | None = None
    new_value: str | None = None
    actor_user_id: str | None = None
    actor_name: str | None = None
    actor_email: str | None = None
    details: dict[str, Any] | None = None
    created_at: Any


class LegacyIssueVehicleChecklistHistoryResponse(BaseModel):
    items: list[LegacyIssueVehicleChecklistHistoryItem] = Field(default_factory=list)
    revision: LegacyIssueVehicleChecklistRevisionItem


class LegacyIssueVehicleModuleChecklistItem(BaseModel):
    id: str
    vehicle_model_id: str
    stage_id: str
    module_key: str
    status: str
    source_dataset_key: str
    source_master_revision_id: str
    source_master_revision_no: int | None = None
    row_count: int
    created_by_id: str | None = None
    completed_by_id: str | None = None
    completed_at: Any | None = None
    seeded_from_checklist_id: str | None = None
    created_at: Any
    updated_at: Any


class LegacyIssueVehicleModuleSummaryItem(BaseModel):
    module_key: str
    latest_master_revision: LegacyIssueVehicleChecklistMasterRevisionItem | None = None
    latest_checklist: LegacyIssueVehicleModuleChecklistItem | None = None
    checklist_count: int


class LegacyIssueVehicleModuleSummaryListResponse(BaseModel):
    items: list[LegacyIssueVehicleModuleSummaryItem] = Field(default_factory=list)


class LegacyIssueVehicleModuleChecklistImportCandidateItem(BaseModel):
    checklist: LegacyIssueVehicleModuleChecklistItem
    stage: LegacyIssueVehicleStageItem
    completed_by_name: str | None = None
    completed_by_email: str | None = None


class LegacyIssueVehicleModuleChecklistListResponse(BaseModel):
    items: list[LegacyIssueVehicleModuleChecklistItem] = Field(default_factory=list)
    latest_master_revision: LegacyIssueVehicleChecklistMasterRevisionItem | None = None
    import_candidates: list[LegacyIssueVehicleModuleChecklistImportCandidateItem] = Field(
        default_factory=list
    )
    master_revisions: list[LegacyIssueVehicleChecklistMasterRevisionItem] = Field(
        default_factory=list
    )


class LegacyIssueVehicleModuleChecklistCreateRequest(BaseModel):
    stage_id: str | None = Field(default=None, max_length=36)
    source_master_revision_id: str | None = Field(default=None, max_length=80)


class LegacyIssueVehicleModuleChecklistImportPreviousRequest(BaseModel):
    stage_id: str = Field(..., min_length=1, max_length=36)
    source_checklist_id: str = Field(..., min_length=1, max_length=36)


class LegacyIssueVehicleModuleChecklistAttachmentItem(BaseModel):
    id: str
    checklist_id: str
    record_id: str
    filename: str
    content_type: str
    size_bytes: int
    uploaded_by_id: str | None = None
    created_at: Any


class LegacyIssueVehicleModuleChecklistRecordItem(BaseModel):
    id: str
    checklist_id: str
    source_record_id: str
    source_stable_record_id: str | None = None
    values: dict[str, Any] = Field(default_factory=dict)
    attachments: list[LegacyIssueVehicleModuleChecklistAttachmentItem] = Field(default_factory=list)
    created_at: Any
    updated_at: Any


class LegacyIssueVehicleModuleChecklistRecordListResponse(BaseModel):
    definition: LegacyIssueDatasetItem
    items: list[LegacyIssueVehicleModuleChecklistRecordItem] = Field(default_factory=list)
    checklist: LegacyIssueVehicleModuleChecklistItem
    total: int
    limit: int | None
    offset: int


class LegacyIssueVehicleModuleChecklistRecordBatchSaveRequest(BaseModel):
    updates: list[LegacyIssueVehicleChecklistRecordBatchUpdateItem] = Field(default_factory=list)


class LegacyIssueVehicleModuleChecklistRecordBatchSaveResponse(BaseModel):
    items: list[LegacyIssueVehicleModuleChecklistRecordItem] = Field(default_factory=list)
    updated: int = 0


class LegacyIssueVehicleModuleChecklistHistoryResponse(BaseModel):
    items: list[LegacyIssueVehicleChecklistHistoryItem] = Field(default_factory=list)
    checklist: LegacyIssueVehicleModuleChecklistItem


class LegacyIssueAttachmentItem(BaseModel):
    id: str
    record_id: str
    filename: str
    content_type: str
    size_bytes: int
    description: str | None = None
    is_primary: bool
    index_status: str = "not_indexed"
    index_error: str | None = None
    indexed_at: Any | None = None
    index_version: str | None = None
    chunk_count: int = 0
    artifact_count: int = 0
    ai_summary: str | None = None
    ai_summary_status: str = "not_summarized"
    ai_summary_error: str | None = None
    ai_summary_model: str | None = None
    ai_summary_version: str | None = None
    ai_summarized_at: Any | None = None
    created_at: Any


class LegacyIssueRecordItem(BaseModel):
    id: str
    revision_id: str | None = None
    stable_record_id: str | None = None
    module_key: str | None = None
    values: dict[str, Any] = Field(default_factory=dict)
    raw_fields: dict[str, Any] = Field(default_factory=dict)
    imported_source_filename: str | None = None
    imported_at: Any | None = None
    attachments: list[LegacyIssueAttachmentItem] = Field(default_factory=list)
    primary_attachment: LegacyIssueAttachmentItem | None = None
    created_at: Any
    updated_at: Any


class LegacyIssueRecordListResponse(BaseModel):
    items: list[LegacyIssueRecordItem]
    total: int
    limit: int | None
    offset: int
    revision: "LegacyIssueRevisionContextItem"


class LegacyIssueRecordUpsertRequest(BaseModel):
    values: dict[str, Any | None] = Field(default_factory=dict)


class LegacyIssueRecordBatchUpdateItem(BaseModel):
    record_id: str
    values: dict[str, Any | None] = Field(default_factory=dict)


class LegacyIssueRecordBatchCreateItem(BaseModel):
    client_row_id: str | None = None
    values: dict[str, Any | None] = Field(default_factory=dict)


class LegacyIssueRecordBatchSaveRequest(BaseModel):
    updates: list[LegacyIssueRecordBatchUpdateItem] = Field(default_factory=list)
    creates: list[LegacyIssueRecordBatchCreateItem] = Field(default_factory=list)
    release_editing: bool = False


class LegacyIssueRecordBatchCreatedItem(BaseModel):
    client_row_id: str | None = None
    record: LegacyIssueRecordItem


class LegacyIssueRecordBatchSaveResponse(BaseModel):
    items: list[LegacyIssueRecordItem] = Field(default_factory=list)
    created_records: list[LegacyIssueRecordBatchCreatedItem] = Field(default_factory=list)
    created: int = 0
    updated: int = 0


class LegacyIssueImportPreviewColumnItem(BaseModel):
    index: int
    header: str
    sample_values: list[str] = Field(default_factory=list)


class LegacyIssueImportPreviewResponse(BaseModel):
    columns: list[LegacyIssueImportPreviewColumnItem]
    preview_rows: list[list[str]] = Field(default_factory=list)
    suggested_mapping: dict[str, int]
    total_preview_rows: int
    record_id_field: str = EXPORT_RECORD_ID_HEADER


class LegacyIssueImportResponse(BaseModel):
    created: int
    updated: int
    skipped: int
    total_rows: int


class LegacyIssueAttachmentUpdateRequest(BaseModel):
    is_primary: bool | None = None
    description: str | None = Field(default=None, max_length=500)


class LegacyIssueRecordHistoryItem(BaseModel):
    id: str
    action: str
    revision_id: str | None = None
    revision_no: int | None = None
    revision_status: str | None = None
    field_key: str | None = None
    field_label: str | None = None
    old_value: str | None = None
    new_value: str | None = None
    actor_user_id: str | None = None
    actor_name: str | None = None
    actor_email: str | None = None
    details: dict[str, Any] | None = None
    created_at: Any


class LegacyIssueRecordHistoryResponse(BaseModel):
    items: list[LegacyIssueRecordHistoryItem] = Field(default_factory=list)


class LegacyIssueRevisionItem(BaseModel):
    id: str
    dataset_key: str
    revision_no: int | None = None
    status: str
    base_revision_id: str | None = None
    note: str | None = None
    locked_by_id: str | None = None
    locked_by_name: str | None = None
    created_by_id: str | None = None
    created_by_name: str | None = None
    published_by_id: str | None = None
    published_by_name: str | None = None
    canceled_by_id: str | None = None
    canceled_by_name: str | None = None
    reviewer_id: str | None = None
    reviewer_name: str | None = None
    reviewer_email: str | None = None
    approver_id: str | None = None
    approver_name: str | None = None
    approver_email: str | None = None
    review_requested_by_id: str | None = None
    review_requested_by_name: str | None = None
    approval_requested_by_id: str | None = None
    approval_requested_by_name: str | None = None
    reviewed_by_id: str | None = None
    reviewed_by_name: str | None = None
    approved_by_id: str | None = None
    approved_by_name: str | None = None
    created_at: Any
    updated_at: Any
    published_at: Any | None = None
    canceled_at: Any | None = None
    review_requested_at: Any | None = None
    approval_requested_at: Any | None = None
    reviewed_at: Any | None = None
    approved_at: Any | None = None


class LegacyIssueRevisionContextItem(BaseModel):
    current: LegacyIssueRevisionItem
    latest_published: LegacyIssueRevisionItem | None = None
    active_draft: LegacyIssueRevisionItem | None = None
    can_direct_edit_published_revision: bool = False
    can_force_cancel_active_draft: bool = False


class LegacyIssueModuleDirectEditorItem(BaseModel):
    id: str
    module_key: str
    user_id: str
    display_name: str
    email: str
    role: str
    can_revoke: bool
    active_member: bool
    created_at: Any
    updated_at: Any


class LegacyIssueModuleDirectEditorListResponse(BaseModel):
    items: list[LegacyIssueModuleDirectEditorItem] = Field(default_factory=list)


class LegacyIssueRevisionOverviewHistoryItem(BaseModel):
    id: str
    dataset_key: str
    linked_revision_id: str | None = None
    origin: str
    revision_no: int | None = None
    revision_label: str | None = None
    summary: str | None = None
    revised_on: date | None = None
    vehicle_models: str | None = None
    author_user_id: str | None = None
    reviewer_user_id: str | None = None
    approver_user_id: str | None = None
    author_name: str | None = None
    reviewer_name: str | None = None
    approver_name: str | None = None
    source_filename: str | None = None
    source_sha256: str | None = None
    source_sheet: str | None = None
    source_row: int | None = None
    sort_order: int
    deleted_at: datetime | None = None
    deleted_by_id: str | None = None


class LegacyIssueRevisionOverviewHistoryUpdateRequest(BaseModel):
    revision_no: int | None = Field(..., ge=0, le=2_147_483_647)
    summary: str | None = Field(..., max_length=10000)
    revised_on: date | None = Field(...)
    vehicle_models: str | None = Field(..., max_length=2000)
    author_user_id: str | None = Field(..., max_length=36)
    reviewer_user_id: str | None = Field(..., max_length=36)
    approver_user_id: str | None = Field(..., max_length=36)
    author_name: str | None = Field(..., max_length=255)
    reviewer_name: str | None = Field(..., max_length=255)
    approver_name: str | None = Field(..., max_length=255)

    @field_validator(
        "summary",
        "vehicle_models",
        "author_name",
        "reviewer_name",
        "approver_name",
        "author_user_id",
        "reviewer_user_id",
        "approver_user_id",
        mode="before",
    )
    @classmethod
    def normalize_optional_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip() or None
        return value


class LegacyIssueRevisionOverviewHistoryCreateRequest(
    LegacyIssueRevisionOverviewHistoryUpdateRequest
):
    linked_revision_id: str | None = Field(default=None, max_length=36)


class LegacyIssueRevisionListResponse(BaseModel):
    items: list[LegacyIssueRevisionItem] = Field(default_factory=list)
    events: list["LegacyIssueRevisionEventItem"] = Field(default_factory=list)
    overview_history: list[LegacyIssueRevisionOverviewHistoryItem] = Field(default_factory=list)


class LegacyIssueRevisionMeetingAttachmentItem(BaseModel):
    id: str
    overview_history_id: str
    filename: str
    content_type: str
    size_bytes: int
    description: str | None = None
    uploaded_by_id: str | None = None
    uploaded_by_name: str | None = None
    created_at: datetime
    updated_at: datetime
    can_edit_description: bool
    can_delete: bool


class LegacyIssueRevisionMeetingAttachmentListResponse(BaseModel):
    items: list[LegacyIssueRevisionMeetingAttachmentItem] = Field(default_factory=list)
    can_upload: bool = True


class LegacyIssueRevisionMeetingAttachmentUpdateRequest(BaseModel):
    description: str | None = Field(default=None, max_length=500)

    @field_validator("description", mode="before")
    @classmethod
    def normalize_description(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip() or None
        return value


class LegacyIssueRevisionActionRequest(BaseModel):
    note: str | None = Field(default=None, max_length=2000)

    @field_validator("note", mode="before")
    @classmethod
    def normalize_note(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip() or None
        return value


class LegacyIssueRevisionCancelRequest(LegacyIssueRevisionActionRequest):
    force: bool = False


class LegacyIssueRevisionNoteUpdateRequest(BaseModel):
    note: str | None = Field(default=None, max_length=2000)

    @field_validator("note", mode="before")
    @classmethod
    def normalize_note(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip() or None
        return value


class LegacyIssueRevisionPublishRequest(BaseModel):
    note: str = Field(..., min_length=1, max_length=2000)

    @field_validator("note", mode="before")
    @classmethod
    def normalize_publish_note(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value


class LegacyIssueRevisionAssigneesRequest(BaseModel):
    reviewer_id: str | None = Field(default=None, max_length=36)
    approver_id: str | None = Field(default=None, max_length=36)

    @field_validator("reviewer_id", "approver_id", mode="before")
    @classmethod
    def normalize_user_id(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip() or None
        return value


class LegacyIssueRevisionApprovalRequestPayload(BaseModel):
    view_key: str | None = Field(default=None, max_length=80)

    @field_validator("view_key", mode="before")
    @classmethod
    def normalize_view_key(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip() or None
        return value


class LegacyIssueRevisionEventItem(BaseModel):
    id: str
    revision_id: str
    dataset_key: str
    action: str
    actor_user_id: str | None = None
    actor_name: str | None = None
    actor_email: str | None = None
    note: str | None = None
    details: dict[str, Any] | None = None
    created_at: Any


class LegacyIssueRevisionCompareCellItem(BaseModel):
    field_key: str
    field_label: str
    left_value: str | None = None
    right_value: str | None = None
    changed: bool


class LegacyIssueRevisionCompareRowItem(BaseModel):
    stable_record_id: str
    status: str
    label: str
    cells: list[LegacyIssueRevisionCompareCellItem] = Field(default_factory=list)


class LegacyIssueRevisionCompareResponse(BaseModel):
    left_revision: LegacyIssueRevisionItem
    right_revision: LegacyIssueRevisionItem
    rows: list[LegacyIssueRevisionCompareRowItem] = Field(default_factory=list)


class LegacyIssueAssistantRunRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    dataset_keys: list[str] | None = None
    evidence_limit: int | None = Field(default=None, ge=1, le=50)

    @field_validator("question", mode="before")
    @classmethod
    def normalize_question(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value


class LegacyIssueAssistantPlanItem(BaseModel):
    query: str
    dataset_keys: list[str]
    primary_keywords: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    supporting_keywords: list[str] = Field(default_factory=list)
    field_hints: list[str] = Field(default_factory=list)
    intent: str
    report_focus: list[str] = Field(default_factory=list)
    related_field_expansions: list[str] = Field(default_factory=list)


class LegacyIssueAssistantMatchedChunkItem(BaseModel):
    chunk_id: str
    chunk_key: str
    chunk_kind: str
    field_key: str | None = None
    field_label: str | None = None
    field_value: str | None = None
    attachment_id: str | None = None
    attachment_filename: str | None = None
    attachment_page: int | None = None
    attachment_artifact_type: str | None = None
    excerpt: str
    methods: list[str] = Field(default_factory=list)
    score: float


class LegacyIssueAssistantEvidenceAttachmentItem(BaseModel):
    id: str
    filename: str
    description: str | None = None
    content_type: str
    size_bytes: int
    index_status: str
    indexed_at: Any | None = None
    matched_chunks: list[LegacyIssueAssistantMatchedChunkItem] = Field(default_factory=list)
    score: float
    methods: list[str] = Field(default_factory=list)


class LegacyIssueAssistantEvidenceItem(BaseModel):
    evidence_id: str
    dataset_key: str
    dataset_title: str
    revision_id: str | None = None
    revision_no: int | None = None
    record_id: str
    stable_record_id: str | None = None
    label: str
    values: dict[str, str] = Field(default_factory=dict)
    matched_fields: list[str] = Field(default_factory=list)
    matched_chunks: list[LegacyIssueAssistantMatchedChunkItem] = Field(default_factory=list)
    attachments: list[LegacyIssueAssistantEvidenceAttachmentItem] = Field(default_factory=list)
    score: float
    methods: list[str] = Field(default_factory=list)


class LegacyIssueAssistantEvidenceRefItem(BaseModel):
    id: str
    dataset_key: str
    dataset_title: str | None = None
    revision_id: str | None = None
    revision_no: int | None = None
    record_id: str
    source_record_id: str | None = None
    stable_record_id: str | None = None
    label: str | None = None
    matched_fields: list[str] = Field(default_factory=list)
    matched_chunks: list[LegacyIssueAssistantMatchedChunkItem] = Field(default_factory=list)
    score: float = 0
    methods: list[str] = Field(default_factory=list)


class LegacyIssueAssistantEvidenceResolveRequest(BaseModel):
    retrieval_profile: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: list[LegacyIssueAssistantEvidenceRefItem] = Field(default_factory=list)


class LegacyIssueAssistantEvidenceResolveResponse(BaseModel):
    retrieval_profile: dict[str, Any] = Field(default_factory=dict)
    evidence: list[LegacyIssueAssistantEvidenceItem] = Field(default_factory=list)


class LegacyIssueAssistantSearchProfileItem(BaseModel):
    semantic_enabled: bool
    vector_extension_available: bool
    vector_index_available: bool = False
    trigram_extension_available: bool
    full_text_enabled: bool
    searched_dataset_keys: list[str] = Field(default_factory=list)
    searched_revision_ids: list[str] = Field(default_factory=list)
    candidate_count: int
    evidence_count: int
    methods: list[str] = Field(default_factory=list)


class LegacyIssueAssistantRunResponse(BaseModel):
    run_id: str
    question: str | None = None
    created_at: Any | None = None
    requested_by_id: str | None = None
    requested_by_name: str | None = None
    requested_by_email: str | None = None
    answer_markdown: str
    analysis_plan: LegacyIssueAssistantPlanItem
    analysis_result: dict[str, Any] | None = None
    evidence: list[LegacyIssueAssistantEvidenceItem] = Field(default_factory=list)
    search_profile: LegacyIssueAssistantSearchProfileItem
    gateway_decisions: list[dict[str, Any]] = Field(default_factory=list)


class LegacyIssueAssistantRunSummaryItem(BaseModel):
    run_id: str
    question: str
    answer_preview: str
    created_at: Any
    requested_by_id: str | None = None
    requested_by_name: str | None = None
    requested_by_email: str | None = None
    evidence_count: int
    dataset_keys: list[str] = Field(default_factory=list)
    methods: list[str] = Field(default_factory=list)


class LegacyIssueAssistantRunListResponse(BaseModel):
    items: list[LegacyIssueAssistantRunSummaryItem] = Field(default_factory=list)
    total: int
    limit: int
    offset: int


class LegacyIssueAssistantReportItem(BaseModel):
    report_id: str
    conversation_id: str | None
    turn_id: str | None
    conversation_title: str | None
    question: str
    title: str
    preview: str
    created_at: datetime


class LegacyIssueAssistantReportListResponse(BaseModel):
    items: list[LegacyIssueAssistantReportItem] = Field(default_factory=list)
    total: int
    limit: int
    offset: int


class LegacyIssueReportListItem(BaseModel):
    report_id: str
    report_number: str
    title: str
    question: str
    preview: str
    completed_at: datetime
    owner_user_id: str | None
    owner_name: str | None
    visibility: Literal["private", "workspace"]
    query_count: int
    source_count: int


class LegacyIssueReportListResponse(BaseModel):
    items: list[LegacyIssueReportListItem] = Field(default_factory=list)
    total: int
    limit: int
    offset: int


class LegacyIssueReportDetailResponse(BaseModel):
    report_id: str
    report_number: str
    title: str
    question: str
    content: str
    content_type: str
    completed_at: datetime
    created_at: datetime
    owner_user_id: str | None
    owner_name: str | None
    visibility: Literal["private", "workspace"]
    query_count: int
    source_count: int
    conversation_id: str | None
    conversation_turn_id: str | None


class LegacyIssueReportQueryItem(BaseModel):
    id: str
    ordinal: int
    query_kind: str
    title: str | None
    family_id: str | None
    query_spec: dict[str, Any] | None
    statement_text: str | None
    typed_params: dict[str, Any] | None
    execution_status: Literal["not_executed", "completed", "failed"]
    error_code: str | None
    query_sha256: str
    result_sha256: str | None
    row_count: int | None
    duration_ms: int | None
    truncated: bool
    payload_bytes: int | None
    exactness: Literal["exact", "estimated", "semantic", "mixed", "unknown"]
    created_at: datetime


class LegacyIssueReportQueryListResponse(BaseModel):
    items: list[LegacyIssueReportQueryItem] = Field(default_factory=list)


class LegacyIssueReportQueryRowsResponse(BaseModel):
    query_id: str
    columns: list[dict[str, Any]] | None
    rows: list[dict[str, Any]] = Field(default_factory=list)
    row_count: int | None
    captured_row_count: int
    truncated: bool
    limit: int
    offset: int
    total: int


class LegacyIssueReportSourceItem(BaseModel):
    id: str
    ordinal: int
    source_kind: str
    source_ref: str
    source_version: str | None
    title: str | None
    locator: dict[str, Any] | None
    metadata: dict[str, Any] | None
    content_sha256: str | None
    grid_columns: list[dict[str, Any]] | None
    grid_rows: list[dict[str, Any]] | None
    row_count: int | None
    truncated: bool
    created_at: datetime


class LegacyIssueReportSourceListResponse(BaseModel):
    items: list[LegacyIssueReportSourceItem] = Field(default_factory=list)


def _report_not_found() -> HTTPException:
    return HTTPException(status_code=404, detail={"code": "ai.artifact_not_found"})


def _require_visible_report(
    db: Session,
    *,
    identifier: str,
    workspace: Workspace,
    user: User,
) -> AiArtifact:
    artifact = get_visible_legacy_issue_report(
        db,
        identifier=identifier,
        workspace_id=workspace.id,
        user_id=user.id,
    )
    if artifact is None:
        raise _report_not_found()
    return artifact


def _report_detail_response(
    db: Session,
    artifact: AiArtifact,
    *,
    requester_user_id: str,
) -> LegacyIssueReportDetailResponse:
    owner = report_owner(db, artifact)
    is_owner = artifact.owner_user_id == requester_user_id
    query_count, source_count = legacy_issue_report_counts(
        db,
        artifact_id=artifact.id,
    )
    return LegacyIssueReportDetailResponse(
        report_id=artifact.id,
        report_number=artifact.artifact_number,
        title=artifact.title,
        question=report_question(db, artifact),
        content=artifact.content_text or "",
        content_type=artifact.content_type,
        completed_at=artifact.completed_at or artifact.created_at,
        created_at=artifact.created_at,
        owner_user_id=artifact.owner_user_id,
        owner_name=owner.display_name if owner else None,
        visibility=artifact.visibility,
        query_count=query_count,
        source_count=source_count,
        conversation_id=artifact.conversation_id if is_owner else None,
        conversation_turn_id=artifact.conversation_turn_id if is_owner else None,
    )


def _report_query_item(query: AiArtifactQuery) -> LegacyIssueReportQueryItem:
    return LegacyIssueReportQueryItem(
        id=query.id,
        ordinal=query.ordinal,
        query_kind=query.query_kind,
        title=query.title,
        family_id=query.family_id,
        query_spec=query.query_spec_json,
        statement_text=query.statement_text,
        typed_params=query.typed_params_json,
        execution_status=query.execution_status,
        error_code=query.error_code,
        query_sha256=query.query_sha256,
        result_sha256=query.result_sha256,
        row_count=query.row_count,
        duration_ms=query.duration_ms,
        truncated=query.truncated,
        payload_bytes=query.payload_bytes,
        exactness=query.exactness,
        created_at=query.created_at,
    )


def _report_source_item(source: AiArtifactSource) -> LegacyIssueReportSourceItem:
    return LegacyIssueReportSourceItem(
        id=source.id,
        ordinal=source.ordinal,
        source_kind=source.source_kind,
        source_ref=source.source_ref,
        source_version=source.source_version,
        title=source.title,
        locator=source.locator_json,
        metadata=source.metadata_json,
        content_sha256=source.content_sha256,
        grid_columns=source.grid_columns_json,
        grid_rows=source.grid_rows_json,
        row_count=source.row_count,
        truncated=source.truncated,
        created_at=source.created_at,
    )


LegacyIssueRecordListResponse.model_rebuild()
LegacyIssueRevisionListResponse.model_rebuild()
LegacyIssueVehicleModelItem.model_rebuild()
LegacyIssueVehicleModuleChecklistItem.model_rebuild()


@router.post("/assistant/runs", response_model=LegacyIssueAssistantRunResponse)
def run_legacy_issue_assistant_analysis(
    payload: LegacyIssueAssistantRunRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueAssistantRunResponse:
    dataset_keys = tuple(payload.dataset_keys or ())
    invalid_dataset_keys = [key for key in dataset_keys if key not in DATASET_DEFINITIONS]
    if invalid_dataset_keys:
        raise localized_http_exception(status_code=404, code="legacy_issues.dataset_not_found")
    result = run_legacy_issue_assistant(
        db,
        workspace=current_workspace,
        user=current_user,
        question=payload.question,
        dataset_keys=dataset_keys or None,
        evidence_limit=payload.evidence_limit
        or get_legacy_issue_settings().ai_default_evidence_limit,
        module_keys=_enabled_module_keys(),
    )
    created_at = utcnow_naive()
    response = _serialize_assistant_result(
        result,
        question=payload.question,
        created_at=created_at,
        requested_by=current_user,
    )
    db.add(
        LegacyIssueAssistantRun(
            id=result.run_id,
            workspace_id=current_workspace.id,
            requested_by_id=current_user.id,
            question=payload.question,
            answer_markdown=response.answer_markdown,
            analysis_plan=response.analysis_plan.model_dump(mode="json"),
            analysis_result=response.analysis_result,
            evidence=[item.model_dump(mode="json") for item in response.evidence],
            search_profile=response.search_profile.model_dump(mode="json"),
            gateway_decisions=list(response.gateway_decisions),
            created_at=created_at,
            updated_at=created_at,
        )
    )
    db.commit()
    return response


@router.get("/assistant/runs", response_model=LegacyIssueAssistantRunListResponse)
def list_legacy_issue_assistant_runs(
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db_session),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueAssistantRunListResponse:
    statement = (
        select(LegacyIssueAssistantRun)
        .where(LegacyIssueAssistantRun.workspace_id == current_workspace.id)
        .order_by(LegacyIssueAssistantRun.created_at.desc())
    )
    visible_rows = _filter_enabled_assistant_runs(
        db,
        workspace=current_workspace,
        rows=list(db.scalars(statement)),
    )
    total = len(visible_rows)
    rows = visible_rows[offset : offset + limit]
    return LegacyIssueAssistantRunListResponse(
        items=[_serialize_assistant_run_summary(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/assistant/reports",
    response_model=LegacyIssueAssistantReportListResponse,
)
def list_legacy_issue_assistant_report_history(
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueAssistantReportListResponse:
    page = list_legacy_issue_assistant_reports(
        db,
        workspace_id=current_workspace.id,
        user_id=current_user.id,
        limit=limit,
        offset=offset,
    )
    return LegacyIssueAssistantReportListResponse(
        items=[
            LegacyIssueAssistantReportItem(
                report_id=item.report_id,
                conversation_id=item.conversation_id,
                turn_id=item.turn_id,
                conversation_title=item.conversation_title,
                question=item.question,
                title=item.title,
                preview=_compact_preview(item.preview_content),
                created_at=item.completed_at,
            )
            for item in page.items
        ],
        total=page.total,
        limit=limit,
        offset=offset,
    )


@router.get("/reports", response_model=LegacyIssueReportListResponse)
def list_legacy_issue_reports_for_management(
    view: Literal["mine", "shared"] = Query(default="mine"),
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueReportListResponse:
    page = list_legacy_issue_reports(
        db,
        workspace_id=current_workspace.id,
        user_id=current_user.id,
        view=view,
        limit=limit,
        offset=offset,
    )
    return LegacyIssueReportListResponse(
        items=[
            LegacyIssueReportListItem(
                report_id=item.report_id,
                report_number=item.report_number,
                title=item.title,
                question=item.question,
                preview=_compact_preview(item.preview_content),
                completed_at=item.completed_at,
                owner_user_id=item.owner_user_id,
                owner_name=item.owner_name,
                visibility=item.visibility,
                query_count=item.query_count,
                source_count=item.source_count,
            )
            for item in page.items
        ],
        total=page.total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/reports/{report_id}",
    response_model=LegacyIssueReportDetailResponse,
)
def get_legacy_issue_report_for_management(
    report_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueReportDetailResponse:
    return _report_detail_response(
        db,
        _require_visible_report(
            db,
            identifier=report_id,
            workspace=current_workspace,
            user=current_user,
        ),
        requester_user_id=current_user.id,
    )


@router.get(
    "/reports/{report_id}/queries",
    response_model=LegacyIssueReportQueryListResponse,
)
def list_legacy_issue_report_queries_for_management(
    report_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueReportQueryListResponse:
    artifact = _require_visible_report(
        db,
        identifier=report_id,
        workspace=current_workspace,
        user=current_user,
    )
    return LegacyIssueReportQueryListResponse(
        items=[
            _report_query_item(query)
            for query in list_legacy_issue_report_queries(
                db,
                artifact_id=artifact.id,
            )
        ]
    )


@router.get(
    "/reports/{report_id}/queries/{query_id}/rows",
    response_model=LegacyIssueReportQueryRowsResponse,
)
def list_legacy_issue_report_query_rows_for_management(
    report_id: str,
    query_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueReportQueryRowsResponse:
    artifact = _require_visible_report(
        db,
        identifier=report_id,
        workspace=current_workspace,
        user=current_user,
    )
    query = get_legacy_issue_report_query(
        db,
        artifact_id=artifact.id,
        query_id=query_id,
    )
    if query is None:
        raise _report_not_found()
    captured_rows = query.result_rows_json or []
    return LegacyIssueReportQueryRowsResponse(
        query_id=query.id,
        columns=query.result_schema_json,
        rows=captured_rows[offset : offset + limit],
        row_count=query.row_count,
        captured_row_count=len(captured_rows),
        truncated=query.truncated,
        limit=limit,
        offset=offset,
        total=len(captured_rows),
    )


@router.get(
    "/reports/{report_id}/sources",
    response_model=LegacyIssueReportSourceListResponse,
)
def list_legacy_issue_report_sources_for_management(
    report_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueReportSourceListResponse:
    artifact = _require_visible_report(
        db,
        identifier=report_id,
        workspace=current_workspace,
        user=current_user,
    )
    return LegacyIssueReportSourceListResponse(
        items=[
            _report_source_item(source)
            for source in list_legacy_issue_report_sources(
                db,
                artifact_id=artifact.id,
            )
        ]
    )


def _set_legacy_issue_report_workspace_share(
    *,
    report_id: str,
    visibility: Literal["private", "workspace"],
    db: Session,
    current_user: User,
    current_workspace: Workspace,
) -> LegacyIssueReportDetailResponse:
    try:
        artifact, changed = AiArtifactRepository(db).set_completed_visibility(
            report_id,
            workspace_id=current_workspace.id,
            owner_user_id=current_user.id,
            visibility=visibility,
            expected_app_id="legacy-issues",
            expected_artifact_type="report",
        )
    except AiArtifactNotFoundError as exc:
        raise _report_not_found() from exc
    if changed:
        action = (
            "legacy_issues.report.share"
            if visibility == "workspace"
            else "legacy_issues.report.unshare"
        )
        record_audit_log(
            db,
            actor_user_id=current_user.id,
            action=action,
            entity_kind="ai_artifact",
            entity_id=artifact.id,
            summary=f"{action}: {artifact.artifact_number}",
            payload={
                "workspace_id": current_workspace.id,
                "artifact_number": artifact.artifact_number,
                "previous_visibility": ("private" if visibility == "workspace" else "workspace"),
                "visibility": visibility,
            },
        )
    db.commit()
    return _report_detail_response(
        db,
        artifact,
        requester_user_id=current_user.id,
    )


@router.put(
    "/reports/{report_id}/workspace-share",
    response_model=LegacyIssueReportDetailResponse,
)
def share_legacy_issue_report_with_workspace(
    report_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueReportDetailResponse:
    return _set_legacy_issue_report_workspace_share(
        report_id=report_id,
        visibility="workspace",
        db=db,
        current_user=current_user,
        current_workspace=current_workspace,
    )


@router.delete(
    "/reports/{report_id}/workspace-share",
    response_model=LegacyIssueReportDetailResponse,
)
def unshare_legacy_issue_report_from_workspace(
    report_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueReportDetailResponse:
    return _set_legacy_issue_report_workspace_share(
        report_id=report_id,
        visibility="private",
        db=db,
        current_user=current_user,
        current_workspace=current_workspace,
    )


@router.get("/assistant/runs/{run_id}", response_model=LegacyIssueAssistantRunResponse)
def get_legacy_issue_assistant_run(
    run_id: str,
    db: Session = Depends(get_db_session),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueAssistantRunResponse:
    row = db.scalar(
        select(LegacyIssueAssistantRun).where(
            LegacyIssueAssistantRun.id == run_id,
            LegacyIssueAssistantRun.workspace_id == current_workspace.id,
        )
    )
    if row is None:
        raise localized_http_exception(
            status_code=404, code="legacy_issues.assistant_run_not_found"
        )
    if not _filter_enabled_assistant_runs(
        db,
        workspace=current_workspace,
        rows=[row],
    ):
        raise localized_http_exception(
            status_code=404,
            code="legacy_issues.assistant_run_not_found",
        )
    return _serialize_assistant_run(row)


@router.post(
    "/assistant/evidence/resolve",
    response_model=LegacyIssueAssistantEvidenceResolveResponse,
)
def resolve_legacy_issue_assistant_evidence(
    payload: LegacyIssueAssistantEvidenceResolveRequest,
    db: Session = Depends(get_db_session),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueAssistantEvidenceResolveResponse:
    partition_ids = _legacy_issue_evidence_partition_ids(
        db,
        workspace=current_workspace,
    )
    return LegacyIssueAssistantEvidenceResolveResponse(
        retrieval_profile=dict(payload.retrieval_profile or {}),
        evidence=[
            item
            for item in (
                _hydrate_assistant_evidence_ref(
                    db,
                    workspace=current_workspace,
                    ref=ref,
                    partition_ids=partition_ids,
                )
                for ref in payload.evidence_refs[:50]
            )
            if item is not None
        ],
    )


@router.get("/datasets", response_model=LegacyIssueDatasetListResponse)
def list_legacy_issue_datasets() -> LegacyIssueDatasetListResponse:
    return LegacyIssueDatasetListResponse(
        items=[
            _serialize_dataset_definition(definition) for definition in DATASET_DEFINITIONS.values()
        ]
    )


@router.get("/datasets/{dataset_key}", response_model=LegacyIssueDatasetItem)
def get_legacy_issue_dataset(
    dataset_key: str,
    view_key: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueDatasetItem:
    return _serialize_dataset_definition(
        get_dataset_definition_for_view(
            db,
            dataset_key=dataset_key,
            workspace=current_workspace,
            view_key=view_key,
        )
    )


@router.get("/vehicle-models", response_model=LegacyIssueVehicleModelListResponse)
def list_legacy_issue_vehicle_models(
    include_inactive: bool = Query(default=False),
    q: str | None = Query(default=None, max_length=120),
    db: Session = Depends(get_db_session),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueVehicleModelListResponse:
    rows = list_vehicle_models(
        db,
        workspace=current_workspace,
        include_inactive=include_inactive,
        query=q,
    )
    summaries = vehicle_checklist_summaries(
        db,
        workspace=current_workspace,
        vehicle_model_ids=[row.id for row in rows],
    )
    generated_counts = vehicle_generated_checklist_counts(
        db,
        workspace=current_workspace,
        vehicle_model_ids=[row.id for row in rows],
    )
    stages_by_vehicle_model_id = vehicle_stages_by_vehicle_model_ids(
        db,
        workspace=current_workspace,
        vehicle_model_ids=[row.id for row in rows],
    )
    return LegacyIssueVehicleModelListResponse(
        items=[
            _serialize_vehicle_model(
                item,
                checklist_summary=summaries.get(item.id),
                generated_checklist_count=generated_counts.get(item.id, 0),
                stages=stages_by_vehicle_model_id.get(item.id, []),
            )
            for item in rows
        ]
    )


@router.post(
    "/vehicle-models",
    response_model=LegacyIssueVehicleModelItem,
    status_code=status.HTTP_201_CREATED,
)
def create_legacy_issue_vehicle_model(
    payload: LegacyIssueVehicleModelCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueVehicleModelItem:
    row = create_vehicle_model(
        db,
        workspace=current_workspace,
        user=current_user,
        vehicle_code=payload.vehicle_code,
        vehicle_name=payload.vehicle_name,
        notes=payload.notes,
        initial_stage_name=payload.initial_stage_name,
    )
    db.commit()
    return _serialize_vehicle_model(
        row,
        stages=list_vehicle_stages(
            db,
            workspace=current_workspace,
            vehicle_model_id=row.id,
        ),
        generated_checklist_count=vehicle_generated_checklist_counts(
            db,
            workspace=current_workspace,
            vehicle_model_ids=[row.id],
        ).get(row.id, 0),
    )


@router.patch("/vehicle-models/{vehicle_model_id}", response_model=LegacyIssueVehicleModelItem)
def update_legacy_issue_vehicle_model(
    vehicle_model_id: str,
    payload: LegacyIssueVehicleModelUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueVehicleModelItem:
    ensure_legacy_issue_module_manager(
        db,
        user=current_user,
        workspace=current_workspace,
        module_key=None,
    )
    row = update_vehicle_model(
        db,
        workspace=current_workspace,
        vehicle_model_id=vehicle_model_id,
        vehicle_code=payload.vehicle_code,
        vehicle_name=payload.vehicle_name,
        vehicle_name_set="vehicle_name" in payload.model_fields_set,
        notes=payload.notes,
        notes_set="notes" in payload.model_fields_set,
        active=payload.active,
    )
    db.commit()
    return _serialize_vehicle_model(
        row,
        stages=list_vehicle_stages(
            db,
            workspace=current_workspace,
            vehicle_model_id=row.id,
        ),
        generated_checklist_count=vehicle_generated_checklist_counts(
            db,
            workspace=current_workspace,
            vehicle_model_ids=[row.id],
        ).get(row.id, 0),
    )


@router.delete("/vehicle-models/{vehicle_model_id}", response_model=LegacyIssueVehicleModelItem)
def deactivate_legacy_issue_vehicle_model(
    vehicle_model_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueVehicleModelItem:
    ensure_legacy_issue_module_manager(
        db,
        user=current_user,
        workspace=current_workspace,
        module_key=None,
    )
    row = deactivate_vehicle_model(
        db,
        workspace=current_workspace,
        vehicle_model_id=vehicle_model_id,
    )
    db.commit()
    return _serialize_vehicle_model(
        row,
        stages=list_vehicle_stages(
            db,
            workspace=current_workspace,
            vehicle_model_id=row.id,
        ),
        generated_checklist_count=vehicle_generated_checklist_counts(
            db,
            workspace=current_workspace,
            vehicle_model_ids=[row.id],
        ).get(row.id, 0),
    )


@router.get(
    "/vehicle-models/{vehicle_model_id}/stages",
    response_model=LegacyIssueVehicleStageListResponse,
)
def list_legacy_issue_vehicle_stages(
    vehicle_model_id: str,
    db: Session = Depends(get_db_session),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueVehicleStageListResponse:
    return LegacyIssueVehicleStageListResponse(
        items=[
            _serialize_vehicle_stage(item)
            for item in list_vehicle_stages(
                db,
                workspace=current_workspace,
                vehicle_model_id=vehicle_model_id,
            )
        ]
    )


@router.post(
    "/vehicle-models/{vehicle_model_id}/stages",
    response_model=LegacyIssueVehicleStageItem,
    status_code=status.HTTP_201_CREATED,
)
def create_legacy_issue_vehicle_stage(
    vehicle_model_id: str,
    payload: LegacyIssueVehicleStageCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueVehicleStageItem:
    ensure_legacy_issue_module_manager(
        db,
        user=current_user,
        workspace=current_workspace,
        module_key=None,
    )
    row = create_vehicle_stage(
        db,
        workspace=current_workspace,
        user=current_user,
        vehicle_model_id=vehicle_model_id,
        name=payload.name,
    )
    db.commit()
    return _serialize_vehicle_stage(row)


@router.patch(
    "/vehicle-models/{vehicle_model_id}/stages/{stage_id}",
    response_model=LegacyIssueVehicleStageItem,
)
def update_legacy_issue_vehicle_stage(
    vehicle_model_id: str,
    stage_id: str,
    payload: LegacyIssueVehicleStageUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueVehicleStageItem:
    ensure_legacy_issue_module_manager(
        db,
        user=current_user,
        workspace=current_workspace,
        module_key=None,
    )
    row = update_vehicle_stage(
        db,
        workspace=current_workspace,
        vehicle_model_id=vehicle_model_id,
        stage_id=stage_id,
        name=payload.name,
    )
    db.commit()
    return _serialize_vehicle_stage(row)


@router.delete(
    "/vehicle-models/{vehicle_model_id}/permanent",
    status_code=status.HTTP_204_NO_CONTENT,
)
def permanently_delete_legacy_issue_vehicle_model(
    vehicle_model_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
    _admin_context: Any = Depends(require_workspace_membership("admin")),
) -> Response:
    permanently_delete_vehicle_model(
        db,
        workspace=current_workspace,
        user=current_user,
        vehicle_model_id=vehicle_model_id,
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/vehicle-models/{vehicle_model_id}/checklist-revisions",
    response_model=LegacyIssueVehicleChecklistRevisionListResponse,
)
def list_legacy_issue_vehicle_checklist_revisions(
    vehicle_model_id: str,
    db: Session = Depends(get_db_session),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueVehicleChecklistRevisionListResponse:
    master_revisions = list_published_master_revisions(db, workspace=current_workspace)
    latest_revision = master_revisions[0] if master_revisions else None
    return LegacyIssueVehicleChecklistRevisionListResponse(
        items=[
            _serialize_vehicle_checklist_revision(item)
            for item in list_vehicle_checklist_revisions(
                db,
                workspace=current_workspace,
                vehicle_model_id=vehicle_model_id,
            )
        ],
        latest_master_revision=(
            LegacyIssueVehicleChecklistMasterRevisionItem(
                id=latest_revision.id,
                revision_no=latest_revision.revision_no,
            )
            if latest_revision
            else None
        ),
        master_revisions=[
            LegacyIssueVehicleChecklistMasterRevisionItem(
                id=revision.id,
                revision_no=revision.revision_no,
            )
            for revision in master_revisions
        ],
    )


@router.post(
    "/vehicle-models/{vehicle_model_id}/checklist-revisions",
    response_model=LegacyIssueVehicleChecklistRevisionItem,
    status_code=status.HTTP_201_CREATED,
)
def create_legacy_issue_vehicle_checklist_revision(
    vehicle_model_id: str,
    payload: LegacyIssueVehicleChecklistRevisionCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueVehicleChecklistRevisionItem:
    _raise_vehicle_checklist_transition_read_only()
    row = create_vehicle_checklist_revision(
        db,
        workspace=current_workspace,
        user=current_user,
        vehicle_model_id=vehicle_model_id,
        source_master_revision_id=payload.source_master_revision_id,
        module_keys=_enabled_module_keys(),
    )
    db.commit()
    return _serialize_vehicle_checklist_revision(row)


@router.get(
    "/vehicle-checklist-revisions/{revision_id}/records",
    response_model=LegacyIssueVehicleChecklistRecordListResponse,
)
def list_legacy_issue_vehicle_checklist_records(
    revision_id: str,
    q: str | None = Query(default=None, max_length=500),
    view_key: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db_session),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueVehicleChecklistRecordListResponse:
    _require_enabled_module(view_key)
    revision, definition, rows, total = list_vehicle_checklist_records(
        db,
        workspace=current_workspace,
        revision_id=revision_id,
        view_key=view_key,
        query=q,
        limit=limit,
        offset=offset,
        module_keys=_enabled_module_keys(),
    )
    return LegacyIssueVehicleChecklistRecordListResponse(
        definition=_serialize_dataset_definition(definition),
        items=[_serialize_vehicle_checklist_record(item) for item in rows],
        revision=_serialize_vehicle_checklist_revision(revision),
        total=total,
        limit=limit,
        offset=offset,
    )


@router.patch(
    "/vehicle-checklist-revisions/{revision_id}/records/batch",
    response_model=LegacyIssueVehicleChecklistRecordBatchSaveResponse,
)
def save_legacy_issue_vehicle_checklist_records_batch(
    revision_id: str,
    payload: LegacyIssueVehicleChecklistRecordBatchSaveRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueVehicleChecklistRecordBatchSaveResponse:
    _raise_vehicle_checklist_transition_read_only()
    rows = update_vehicle_checklist_records(
        db,
        workspace=current_workspace,
        user=current_user,
        revision_id=revision_id,
        updates={item.record_id: item.values for item in payload.updates},
        module_keys=_enabled_module_keys(),
    )
    db.commit()
    return LegacyIssueVehicleChecklistRecordBatchSaveResponse(
        items=[_serialize_vehicle_checklist_record(row) for row in rows],
        updated=len(rows),
    )


@router.get(
    "/vehicle-checklist-revisions/{revision_id}/history",
    response_model=LegacyIssueVehicleChecklistHistoryResponse,
)
def list_legacy_issue_vehicle_checklist_history(
    revision_id: str,
    db: Session = Depends(get_db_session),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueVehicleChecklistHistoryResponse:
    history = list_vehicle_checklist_history(
        db,
        workspace=current_workspace,
        revision_id=revision_id,
        module_keys=_enabled_module_keys(),
    )
    return LegacyIssueVehicleChecklistHistoryResponse(
        items=[
            _serialize_vehicle_checklist_history_item(
                row,
                context=history.record_contexts.get(row.record_id),
            )
            for row in history.items
        ],
        revision=_serialize_vehicle_checklist_revision(history.revision),
    )


@router.post(
    "/vehicle-checklist-revisions/{revision_id}/complete",
    response_model=LegacyIssueVehicleChecklistRevisionItem,
)
def complete_legacy_issue_vehicle_checklist_revision(
    revision_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueVehicleChecklistRevisionItem:
    _raise_vehicle_checklist_transition_read_only()
    row = complete_vehicle_checklist_revision(
        db,
        workspace=current_workspace,
        user=current_user,
        revision_id=revision_id,
    )
    db.commit()
    return _serialize_vehicle_checklist_revision(row)


@router.post(
    "/vehicle-checklist-revisions/{revision_id}/reopen",
    response_model=LegacyIssueVehicleChecklistRevisionItem,
)
def reopen_legacy_issue_vehicle_checklist_revision(
    revision_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueVehicleChecklistRevisionItem:
    _raise_vehicle_checklist_transition_read_only()
    row = reopen_vehicle_checklist_revision(
        db,
        workspace=current_workspace,
        user=current_user,
        revision_id=revision_id,
    )
    db.commit()
    return _serialize_vehicle_checklist_revision(row)


@router.delete(
    "/vehicle-checklist-revisions/{revision_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_legacy_issue_vehicle_checklist_revision(
    revision_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> Response:
    del current_user
    delete_vehicle_checklist_revision(
        db,
        workspace=current_workspace,
        revision_id=revision_id,
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/vehicle-models/{vehicle_model_id}/checklist-modules",
    response_model=LegacyIssueVehicleModuleSummaryListResponse,
)
def list_legacy_issue_vehicle_checklist_modules(
    vehicle_model_id: str,
    stage_id: str | None = Query(default=None, max_length=36),
    db: Session = Depends(get_db_session),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueVehicleModuleSummaryListResponse:
    summaries = list_vehicle_module_summaries(
        db,
        workspace=current_workspace,
        vehicle_model_id=vehicle_model_id,
        stage_id=stage_id,
        module_keys=_enabled_module_keys(),
    )
    return LegacyIssueVehicleModuleSummaryListResponse(
        items=[_serialize_vehicle_module_summary(item) for item in summaries]
    )


@router.get(
    "/vehicle-models/{vehicle_model_id}/checklist-modules/{module_key}/checklists",
    response_model=LegacyIssueVehicleModuleChecklistListResponse,
)
def list_legacy_issue_vehicle_module_checklists(
    vehicle_model_id: str,
    module_key: str,
    stage_id: str | None = Query(default=None, max_length=36),
    db: Session = Depends(get_db_session),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueVehicleModuleChecklistListResponse:
    _require_enabled_module(module_key)
    enabled_module_keys = _enabled_module_keys()
    import_candidates = list_prior_stage_completed_vehicle_module_checklists(
        db,
        workspace=current_workspace,
        vehicle_model_id=vehicle_model_id,
        stage_id=stage_id,
        module_key=module_key,
        module_keys=enabled_module_keys,
    )
    master_revisions = list_published_module_master_revisions(
        db,
        workspace=current_workspace,
        module_key=module_key,
        module_keys=enabled_module_keys,
    )
    latest_master_revision = master_revisions[0] if master_revisions else None
    return LegacyIssueVehicleModuleChecklistListResponse(
        items=[
            _serialize_vehicle_module_checklist(item)
            for item in list_vehicle_module_checklists(
                db,
                workspace=current_workspace,
                vehicle_model_id=vehicle_model_id,
                stage_id=stage_id,
                module_key=module_key,
                module_keys=enabled_module_keys,
            )
        ],
        latest_master_revision=(
            _serialize_vehicle_checklist_master_revision(latest_master_revision)
            if latest_master_revision is not None
            else None
        ),
        import_candidates=[
            LegacyIssueVehicleModuleChecklistImportCandidateItem(
                checklist=_serialize_vehicle_module_checklist(candidate.checklist),
                stage=_serialize_vehicle_stage(candidate.stage),
                completed_by_name=candidate.completed_by_name,
                completed_by_email=candidate.completed_by_email,
            )
            for candidate in import_candidates
        ],
        master_revisions=[
            _serialize_vehicle_checklist_master_revision(item) for item in master_revisions
        ],
    )


@router.post(
    "/vehicle-models/{vehicle_model_id}/checklist-modules/{module_key}/checklists",
    response_model=LegacyIssueVehicleModuleChecklistItem,
    status_code=status.HTTP_201_CREATED,
)
def create_legacy_issue_vehicle_module_checklist(
    vehicle_model_id: str,
    module_key: str,
    payload: LegacyIssueVehicleModuleChecklistCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueVehicleModuleChecklistItem:
    _require_enabled_module(module_key)
    checklist = create_vehicle_module_checklist(
        db,
        workspace=current_workspace,
        user=current_user,
        vehicle_model_id=vehicle_model_id,
        stage_id=payload.stage_id,
        module_key=module_key,
        source_master_revision_id=payload.source_master_revision_id,
        module_keys=_enabled_module_keys(),
    )
    db.commit()
    return _serialize_vehicle_module_checklist(checklist)


@router.post(
    (
        "/vehicle-models/{vehicle_model_id}/checklist-modules/{module_key}/"
        "checklists/import-previous-stage"
    ),
    response_model=LegacyIssueVehicleModuleChecklistItem,
    status_code=status.HTTP_201_CREATED,
)
def import_previous_stage_legacy_issue_vehicle_module_checklist(
    vehicle_model_id: str,
    module_key: str,
    payload: LegacyIssueVehicleModuleChecklistImportPreviousRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueVehicleModuleChecklistItem:
    _require_enabled_module(module_key)
    checklist = import_previous_stage_vehicle_module_checklist(
        db,
        workspace=current_workspace,
        user=current_user,
        vehicle_model_id=vehicle_model_id,
        stage_id=payload.stage_id,
        module_key=module_key,
        source_checklist_id=payload.source_checklist_id,
        module_keys=_enabled_module_keys(),
    )
    db.commit()
    return _serialize_vehicle_module_checklist(checklist)


@router.get(
    "/vehicle-module-checklists/{checklist_id}/records",
    response_model=LegacyIssueVehicleModuleChecklistRecordListResponse,
)
def list_legacy_issue_vehicle_module_checklist_records(
    checklist_id: str,
    q: str | None = Query(default=None, max_length=500),
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db_session),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueVehicleModuleChecklistRecordListResponse:
    checklist, definition, rows, total = list_vehicle_module_checklist_records(
        db,
        workspace=current_workspace,
        checklist_id=checklist_id,
        query=q,
        limit=limit,
        offset=offset,
        module_keys=_enabled_module_keys(),
    )
    attachments_by_record_id = list_vehicle_module_checklist_attachments_for_records(
        db,
        workspace=current_workspace,
        checklist=checklist,
        record_ids=[row.id for row in rows],
    )
    return LegacyIssueVehicleModuleChecklistRecordListResponse(
        definition=_serialize_dataset_definition(definition),
        items=[
            _serialize_vehicle_module_checklist_record(
                item,
                attachments=attachments_by_record_id.get(item.id, []),
            )
            for item in rows
        ],
        checklist=_serialize_vehicle_module_checklist(checklist),
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/vehicle-module-checklists/{checklist_id}/excel-exports",
    response_model=LegacyIssueExcelExportJobItem,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_legacy_issue_vehicle_module_checklist_excel_export(
    checklist_id: str,
    payload: LegacyIssueChecklistExcelExportCreateRequest | None = None,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueExcelExportJobItem:
    job = create_vehicle_module_checklist_excel_export_job(
        db,
        workspace=current_workspace,
        user=current_user,
        checklist_id=checklist_id,
        module_keys=_enabled_module_keys(),
        column_keys=payload.column_keys if payload is not None else None,
        include_attachments=payload.include_attachments if payload is not None else True,
    )
    db.commit()
    return _serialize_excel_export_job(job)


@router.patch(
    "/vehicle-module-checklists/{checklist_id}/records",
    response_model=LegacyIssueVehicleModuleChecklistRecordBatchSaveResponse,
)
def save_legacy_issue_vehicle_module_checklist_records(
    checklist_id: str,
    payload: LegacyIssueVehicleModuleChecklistRecordBatchSaveRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueVehicleModuleChecklistRecordBatchSaveResponse:
    rows = update_vehicle_module_checklist_records(
        db,
        workspace=current_workspace,
        user=current_user,
        checklist_id=checklist_id,
        updates={item.record_id: item.values for item in payload.updates},
        module_keys=_enabled_module_keys(),
    )
    checklist = get_vehicle_module_checklist(
        db,
        workspace=current_workspace,
        checklist_id=checklist_id,
        module_keys=_enabled_module_keys(),
    )
    attachments_by_record_id = list_vehicle_module_checklist_attachments_for_records(
        db,
        workspace=current_workspace,
        checklist=checklist,
        record_ids=[row.id for row in rows],
    )
    db.commit()
    return LegacyIssueVehicleModuleChecklistRecordBatchSaveResponse(
        items=[
            _serialize_vehicle_module_checklist_record(
                item,
                attachments=attachments_by_record_id.get(item.id, []),
            )
            for item in rows
        ],
        updated=len(rows),
    )


@router.post(
    "/vehicle-module-checklists/{checklist_id}/records/{record_id}/attachments",
    response_model=LegacyIssueVehicleModuleChecklistAttachmentItem,
    status_code=status.HTTP_201_CREATED,
)
async def upload_legacy_issue_vehicle_module_checklist_attachment(
    checklist_id: str,
    record_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueVehicleModuleChecklistAttachmentItem:
    upload = await read_vehicle_module_checklist_attachment_upload(file)
    try:
        checklist = get_vehicle_module_checklist(
            db,
            workspace=current_workspace,
            checklist_id=checklist_id,
            module_keys=_enabled_module_keys(),
            for_update=True,
        )
        row = upload_vehicle_module_checklist_attachment(
            db,
            workspace=current_workspace,
            user=current_user,
            checklist=checklist,
            record_id=record_id,
            upload=upload,
        )
        try:
            db.commit()
        except Exception:
            db.rollback()
            remove_uploaded_vehicle_module_checklist_attachment(row.storage_key)
            raise
        item = _serialize_vehicle_module_checklist_attachment(row)
        process_pending_vehicle_module_checklist_attachment_cleanups(
            db,
            workspace=current_workspace,
            limit=20,
        )
        return item
    finally:
        upload.content.close()


@router.get(
    "/vehicle-module-checklists/{checklist_id}/attachments/{attachment_id}/file",
    response_class=StreamingResponse,
    responses={
        status.HTTP_200_OK: {
            "content": {
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
            },
            "description": "Checklist attachment file",
        }
    },
)
def open_legacy_issue_vehicle_module_checklist_attachment(
    checklist_id: str,
    attachment_id: str,
    db: Session = Depends(get_db_session),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> StreamingResponse:
    checklist = get_vehicle_module_checklist(
        db,
        workspace=current_workspace,
        checklist_id=checklist_id,
        module_keys=_enabled_module_keys(),
    )
    content = open_vehicle_module_checklist_attachment(
        db,
        workspace=current_workspace,
        checklist=checklist,
        attachment_id=attachment_id,
    )
    return StreamingResponse(
        content.body,
        media_type=content.media_type,
        headers=content.headers,
    )


@router.delete(
    "/vehicle-module-checklists/{checklist_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_legacy_issue_vehicle_module_checklist_attachment(
    checklist_id: str,
    attachment_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> Response:
    checklist = get_vehicle_module_checklist(
        db,
        workspace=current_workspace,
        checklist_id=checklist_id,
        module_keys=_enabled_module_keys(),
        for_update=True,
    )
    delete_vehicle_module_checklist_attachment(
        db,
        workspace=current_workspace,
        user=current_user,
        checklist=checklist,
        attachment_id=attachment_id,
    )
    db.commit()
    process_pending_vehicle_module_checklist_attachment_cleanups(
        db,
        workspace=current_workspace,
        limit=100,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/vehicle-module-checklists/{checklist_id}/history",
    response_model=LegacyIssueVehicleModuleChecklistHistoryResponse,
)
def list_legacy_issue_vehicle_module_checklist_history(
    checklist_id: str,
    db: Session = Depends(get_db_session),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueVehicleModuleChecklistHistoryResponse:
    history = list_vehicle_module_checklist_history(
        db,
        workspace=current_workspace,
        checklist_id=checklist_id,
        module_keys=_enabled_module_keys(),
    )
    return LegacyIssueVehicleModuleChecklistHistoryResponse(
        items=[
            _serialize_vehicle_checklist_history_item(
                row,
                context=history.record_contexts.get(row.record_id),
            )
            for row in history.items
        ],
        checklist=_serialize_vehicle_module_checklist(history.checklist),
    )


@router.post(
    "/vehicle-module-checklists/{checklist_id}/complete",
    response_model=LegacyIssueVehicleModuleChecklistItem,
)
def complete_legacy_issue_vehicle_module_checklist(
    checklist_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueVehicleModuleChecklistItem:
    checklist = complete_vehicle_module_checklist(
        db,
        workspace=current_workspace,
        user=current_user,
        checklist_id=checklist_id,
        module_keys=_enabled_module_keys(),
    )
    db.commit()
    return _serialize_vehicle_module_checklist(checklist)


@router.post(
    "/vehicle-module-checklists/{checklist_id}/reopen",
    response_model=LegacyIssueVehicleModuleChecklistItem,
)
def reopen_legacy_issue_vehicle_module_checklist(
    checklist_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueVehicleModuleChecklistItem:
    checklist = reopen_vehicle_module_checklist(
        db,
        workspace=current_workspace,
        user=current_user,
        checklist_id=checklist_id,
        module_keys=_enabled_module_keys(),
    )
    db.commit()
    return _serialize_vehicle_module_checklist(checklist)


@router.delete(
    "/vehicle-module-checklists/{checklist_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_legacy_issue_vehicle_module_checklist(
    checklist_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> Response:
    del current_user
    delete_vehicle_module_checklist(
        db,
        workspace=current_workspace,
        checklist_id=checklist_id,
        module_keys=_enabled_module_keys(),
    )
    db.commit()
    process_pending_vehicle_module_checklist_attachment_cleanups(
        db,
        workspace=current_workspace,
        limit=100,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/column-orders", response_model=LegacyIssueColumnOrderItem)
def get_legacy_issue_column_order(
    view_key: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueColumnOrderItem:
    _require_enabled_module(view_key)
    normalized_view_key = normalize_column_order_view_key(view_key)
    return _serialize_column_order(
        get_column_order(
            db,
            workspace=current_workspace,
            view_key=normalized_view_key,
            available_keys=_available_column_keys_for_view(
                db,
                workspace=current_workspace,
                view_key=normalized_view_key,
            ),
        )
    )


@router.put("/column-orders/{view_key}", response_model=LegacyIssueColumnOrderItem)
def update_legacy_issue_column_order(
    view_key: str,
    payload: LegacyIssueColumnOrderUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueColumnOrderItem:
    _require_enabled_module(view_key)
    normalized_view_key = normalize_column_order_view_key(view_key)
    ensure_legacy_issue_module_manager(
        db,
        user=current_user,
        workspace=current_workspace,
        module_key=None,
    )
    item = upsert_column_order(
        db,
        workspace=current_workspace,
        user=current_user,
        view_key=normalized_view_key,
        column_order=payload.column_order,
        hidden_column_keys=payload.hidden_column_keys,
        available_keys=_available_column_keys_for_view(
            db,
            workspace=current_workspace,
            view_key=normalized_view_key,
        ),
    )
    db.commit()
    return _serialize_column_order(item)


@router.get(
    "/grid-preferences/{grid_kind}/{grid_key}",
    response_model=LegacyIssueGridPreferenceResponse,
)
def get_legacy_issue_grid_preference(
    grid_kind: LegacyIssueGridPreferenceKind,
    grid_key: str = Path(
        ...,
        min_length=1,
        max_length=GRID_PREFERENCE_MAX_KEY_LENGTH,
        pattern=r".*\S.*",
    ),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueGridPreferenceResponse:
    normalized_grid_key = normalize_grid_preference_scope_key(
        grid_kind,
        grid_key,
    )
    _require_enabled_module(normalized_grid_key)
    state = get_grid_preference(
        db,
        user=current_user,
        workspace=current_workspace,
        grid_kind=grid_kind,
        grid_key=normalized_grid_key,
    )
    return LegacyIssueGridPreferenceResponse(
        preference=(
            _serialize_grid_preference(state.preference) if state.preference is not None else None
        ),
        revision=state.revision,
    )


@router.put(
    "/grid-preferences/{grid_kind}/{grid_key}",
    response_model=LegacyIssueGridPreferenceItem,
    responses={
        status.HTTP_409_CONFLICT: {
            "model": ErrorResponse,
            "description": "Grid preference revision conflict.",
        }
    },
)
def update_legacy_issue_grid_preference(
    grid_kind: LegacyIssueGridPreferenceKind,
    payload: LegacyIssueGridPreferenceUpdateRequest,
    grid_key: str = Path(
        ...,
        min_length=1,
        max_length=GRID_PREFERENCE_MAX_KEY_LENGTH,
        pattern=r".*\S.*",
    ),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueGridPreferenceItem:
    normalized_grid_key = normalize_grid_preference_scope_key(
        grid_kind,
        grid_key,
    )
    _require_enabled_module(normalized_grid_key)
    item = upsert_grid_preference(
        db,
        user=current_user,
        workspace=current_workspace,
        grid_kind=grid_kind,
        grid_key=normalized_grid_key,
        column_order=payload.column_order,
        hidden_column_keys=payload.hidden_column_keys,
        frozen_column_count=payload.frozen_column_count,
        expected_revision=payload.expected_revision,
    )
    db.commit()
    return _serialize_grid_preference(item)


@router.delete(
    "/grid-preferences/{grid_kind}/{grid_key}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_409_CONFLICT: {
            "model": ErrorResponse,
            "description": "Grid preference revision conflict.",
        }
    },
)
def delete_legacy_issue_grid_preference(
    grid_kind: LegacyIssueGridPreferenceKind,
    expected_revision: int = Query(..., ge=0),
    grid_key: str = Path(
        ...,
        min_length=1,
        max_length=GRID_PREFERENCE_MAX_KEY_LENGTH,
        pattern=r".*\S.*",
    ),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> Response:
    normalized_grid_key = normalize_grid_preference_scope_key(
        grid_kind,
        grid_key,
    )
    _require_enabled_module(normalized_grid_key)
    delete_grid_preference(
        db,
        user=current_user,
        workspace=current_workspace,
        grid_kind=grid_kind,
        grid_key=normalized_grid_key,
        expected_revision=expected_revision,
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/system-fields", response_model=LegacyIssueSystemFieldListResponse)
def list_legacy_issue_system_fields(
    dataset_key: str = Query(default="common-master"),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueSystemFieldListResponse:
    ensure_legacy_issue_module_manager(
        db,
        user=current_user,
        workspace=current_workspace,
        module_key=None,
    )
    return LegacyIssueSystemFieldListResponse(
        items=[
            _serialize_system_field_setting(item)
            for item in list_system_field_setting_views(
                db,
                workspace=current_workspace,
                dataset_key=dataset_key,
            )
        ]
    )


@router.patch("/system-fields/{field_key}", response_model=LegacyIssueSystemFieldItem)
def update_legacy_issue_system_field(
    field_key: str,
    payload: LegacyIssueSystemFieldUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueSystemFieldItem:
    ensure_legacy_issue_module_manager(
        db,
        user=current_user,
        workspace=current_workspace,
        module_key=None,
    )
    field = upsert_system_field_setting(
        db,
        workspace=current_workspace,
        user=current_user,
        dataset_key=payload.dataset_key,
        field_key=field_key,
        label_ko=payload.label_ko,
        label_en=payload.label_en,
        field_type=payload.field_type,
        options=payload.options,
        allow_multiple=payload.allow_multiple,
        required=payload.required,
    )
    _refresh_module_field_record_projections(db, workspace=current_workspace)
    db.commit()
    return _serialize_system_field_setting(field)


@router.get(
    "/module-direct-editors",
    response_model=LegacyIssueModuleDirectEditorListResponse,
)
def list_legacy_issue_module_direct_editors(
    module_key: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueModuleDirectEditorListResponse:
    _require_enabled_module(module_key)
    rows = list_module_direct_editors(
        db,
        workspace=current_workspace,
        actor=current_user,
        module_key=module_key,
    )
    enabled_module_keys = _enabled_module_keys()
    return LegacyIssueModuleDirectEditorListResponse(
        items=[
            _serialize_module_direct_editor(item)
            for item in rows
            if item.module_key in enabled_module_keys
        ]
    )


@router.put(
    "/module-direct-editors/{module_key}/users/{user_id}",
    response_model=LegacyIssueModuleDirectEditorItem,
)
def grant_legacy_issue_module_direct_editor(
    module_key: str,
    user_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueModuleDirectEditorItem:
    _require_enabled_module(module_key)
    item = grant_module_direct_editor(
        db,
        workspace=current_workspace,
        actor=current_user,
        module_key=module_key,
        user_id=user_id,
    )
    db.commit()
    return _serialize_module_direct_editor(item)


@router.delete(
    "/module-direct-editors/{module_key}/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def revoke_legacy_issue_module_direct_editor(
    module_key: str,
    user_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> Response:
    _require_enabled_module(module_key)
    revoke_module_direct_editor(
        db,
        workspace=current_workspace,
        actor=current_user,
        module_key=module_key,
        user_id=user_id,
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/module-fields", response_model=LegacyIssueModuleFieldListResponse)
def list_legacy_issue_module_fields(
    module_key: str | None = Query(default=None),
    include_inactive: bool = Query(default=True),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueModuleFieldListResponse:
    _require_enabled_module(module_key)
    ensure_legacy_issue_module_manager(
        db,
        user=current_user,
        workspace=current_workspace,
        module_key=module_key,
    )
    return LegacyIssueModuleFieldListResponse(
        items=[
            _serialize_module_field(item)
            for item in list_module_fields(
                db,
                workspace=current_workspace,
                module_key=module_key,
                include_inactive=include_inactive,
            )
        ]
    )


@router.post(
    "/module-fields",
    response_model=LegacyIssueModuleFieldItem,
    status_code=status.HTTP_201_CREATED,
)
def create_legacy_issue_module_field(
    payload: LegacyIssueModuleFieldCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueModuleFieldItem:
    _require_enabled_module(payload.module_key)
    ensure_legacy_issue_module_manager(
        db,
        user=current_user,
        workspace=current_workspace,
        module_key=payload.module_key,
    )
    field = create_module_field(
        db,
        workspace=current_workspace,
        user=current_user,
        module_key=payload.module_key,
        label_ko=payload.label_ko,
        label_en=payload.label_en,
        field_type=payload.field_type,
        options=payload.options,
        allow_multiple=payload.allow_multiple,
        required=payload.required,
        sort_order=payload.sort_order,
    )
    _refresh_module_field_record_projections(db, workspace=current_workspace)
    db.commit()
    return _serialize_module_field(field)


@router.patch("/module-fields/reorder", response_model=LegacyIssueModuleFieldListResponse)
def reorder_legacy_issue_module_fields(
    payload: LegacyIssueModuleFieldReorderRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueModuleFieldListResponse:
    _require_enabled_module(payload.module_key)
    ensure_legacy_issue_module_manager(
        db,
        user=current_user,
        workspace=current_workspace,
        module_key=payload.module_key,
    )
    fields = reorder_module_fields(
        db,
        workspace=current_workspace,
        module_key=payload.module_key,
        field_ids=payload.field_ids,
    )
    _refresh_module_field_record_projections(db, workspace=current_workspace)
    db.commit()
    return LegacyIssueModuleFieldListResponse(
        items=[_serialize_module_field(field) for field in fields]
    )


@router.patch("/module-fields/{field_id}", response_model=LegacyIssueModuleFieldItem)
def update_legacy_issue_module_field(
    field_id: str,
    payload: LegacyIssueModuleFieldUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueModuleFieldItem:
    existing = get_module_field_row(
        db,
        workspace=current_workspace,
        field_id=field_id,
    )
    _require_enabled_module(existing.module_key)
    ensure_legacy_issue_module_manager(
        db,
        user=current_user,
        workspace=current_workspace,
        module_key=existing.module_key,
    )
    field = update_module_field(
        db,
        workspace=current_workspace,
        field_id=field_id,
        label_ko=payload.label_ko,
        label_en=payload.label_en,
        field_type=payload.field_type,
        options=payload.options,
        allow_multiple=payload.allow_multiple,
        required=payload.required,
        sort_order=payload.sort_order,
        active=payload.active,
    )
    _refresh_module_field_record_projections(db, workspace=current_workspace)
    db.commit()
    return _serialize_module_field(field)


@router.delete(
    "/module-fields/{field_id}",
    response_model=LegacyIssueModuleFieldItem,
)
def delete_legacy_issue_module_field(
    field_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueModuleFieldItem:
    existing = get_module_field_row(
        db,
        workspace=current_workspace,
        field_id=field_id,
    )
    _require_enabled_module(existing.module_key)
    ensure_legacy_issue_module_manager(
        db,
        user=current_user,
        workspace=current_workspace,
        module_key=existing.module_key,
    )
    field = deactivate_module_field(db, workspace=current_workspace, field_id=field_id)
    _refresh_module_field_record_projections(db, workspace=current_workspace)
    db.commit()
    return _serialize_module_field(field)


@router.get("/datasets/{dataset_key}/revisions", response_model=LegacyIssueRevisionListResponse)
def list_legacy_issue_dataset_revisions(
    dataset_key: str,
    view_key: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueRevisionListResponse:
    definition = get_dataset_definition(dataset_key)
    revision_dataset_key = _module_revision_dataset_key(definition, view_key)
    resolve_read_revision(db, workspace=current_workspace, dataset_key=revision_dataset_key)
    response = LegacyIssueRevisionListResponse(
        items=[
            _serialize_revision(row)
            for row in list_revisions(
                db,
                workspace=current_workspace,
                dataset_key=revision_dataset_key,
            )
        ],
        events=[
            _serialize_revision_event(row)
            for row in list_revision_events(
                db,
                workspace=current_workspace,
                dataset_key=revision_dataset_key,
            )
        ],
        overview_history=[
            _serialize_revision_overview_history(row)
            for row in list_revision_overview_history(
                db,
                workspace=current_workspace,
                dataset_key=revision_dataset_key,
            )
        ],
    )
    db.commit()
    return response


@router.post(
    "/datasets/{dataset_key}/revisions/overview-history",
    response_model=LegacyIssueRevisionOverviewHistoryItem,
    status_code=status.HTTP_201_CREATED,
)
def create_legacy_issue_revision_overview_history(
    dataset_key: str,
    payload: LegacyIssueRevisionOverviewHistoryCreateRequest,
    view_key: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueRevisionOverviewHistoryItem:
    definition = get_dataset_definition(dataset_key)
    revision_dataset_key = _module_revision_dataset_key(definition, view_key)
    row = create_revision_overview_history(
        db,
        workspace=current_workspace,
        dataset_key=revision_dataset_key,
        user=current_user,
        linked_revision_id=payload.linked_revision_id,
        revision_no=payload.revision_no,
        summary=payload.summary,
        revised_on=payload.revised_on,
        vehicle_models=payload.vehicle_models,
        author_user_id=payload.author_user_id,
        reviewer_user_id=payload.reviewer_user_id,
        approver_user_id=payload.approver_user_id,
        author_name=payload.author_name,
        reviewer_name=payload.reviewer_name,
        approver_name=payload.approver_name,
    )
    db.commit()
    return _serialize_revision_overview_history(row)


@router.patch(
    "/datasets/{dataset_key}/revisions/overview-history/{history_id}",
    response_model=LegacyIssueRevisionOverviewHistoryItem,
)
def update_legacy_issue_revision_overview_history(
    dataset_key: str,
    history_id: str,
    payload: LegacyIssueRevisionOverviewHistoryUpdateRequest,
    view_key: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueRevisionOverviewHistoryItem:
    definition = get_dataset_definition(dataset_key)
    revision_dataset_key = _module_revision_dataset_key(definition, view_key)
    row = update_revision_overview_history(
        db,
        workspace=current_workspace,
        dataset_key=revision_dataset_key,
        history_id=history_id,
        user=current_user,
        revision_no=payload.revision_no,
        summary=payload.summary,
        revised_on=payload.revised_on,
        vehicle_models=payload.vehicle_models,
        author_user_id=payload.author_user_id,
        reviewer_user_id=payload.reviewer_user_id,
        approver_user_id=payload.approver_user_id,
        author_name=payload.author_name,
        reviewer_name=payload.reviewer_name,
        approver_name=payload.approver_name,
    )
    db.commit()
    return _serialize_revision_overview_history(row)


@router.delete(
    "/datasets/{dataset_key}/revisions/overview-history/{history_id}",
    response_model=LegacyIssueRevisionOverviewHistoryItem,
)
def delete_legacy_issue_revision_overview_history(
    dataset_key: str,
    history_id: str,
    view_key: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueRevisionOverviewHistoryItem:
    definition = get_dataset_definition(dataset_key)
    revision_dataset_key = _module_revision_dataset_key(definition, view_key)
    row = delete_revision_overview_history(
        db,
        workspace=current_workspace,
        dataset_key=revision_dataset_key,
        history_id=history_id,
        user=current_user,
    )
    db.commit()
    return _serialize_revision_overview_history(row)


@router.delete(
    "/datasets/{dataset_key}/revisions/overview-history/by-revision/{revision_id}",
    response_model=LegacyIssueRevisionOverviewHistoryItem,
)
def hide_legacy_issue_revision_from_overview_history(
    dataset_key: str,
    revision_id: str,
    view_key: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueRevisionOverviewHistoryItem:
    definition = get_dataset_definition(dataset_key)
    revision_dataset_key = _module_revision_dataset_key(definition, view_key)
    row = hide_revision_from_overview_history(
        db,
        workspace=current_workspace,
        dataset_key=revision_dataset_key,
        revision_id=revision_id,
        user=current_user,
    )
    db.commit()
    return _serialize_revision_overview_history(row)


@router.get(
    "/datasets/{dataset_key}/revisions/meeting-attachments",
    response_model=LegacyIssueRevisionMeetingAttachmentListResponse,
)
def list_legacy_issue_revision_meeting_attachments(
    dataset_key: str,
    view_key: str | None = Query(default=None),
    history_id: str | None = Query(default=None, min_length=1, max_length=36),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueRevisionMeetingAttachmentListResponse:
    definition = get_dataset_definition(dataset_key)
    revision_dataset_key = _module_revision_dataset_key(definition, view_key)
    resolve_read_revision(
        db,
        workspace=current_workspace,
        dataset_key=revision_dataset_key,
    )
    rows = list_revision_meeting_attachments(
        db,
        workspace=current_workspace,
        dataset_key=revision_dataset_key,
        history_id=history_id,
    )
    can_delete = can_delete_revision_meeting_attachment(db, user=current_user)
    response = LegacyIssueRevisionMeetingAttachmentListResponse(
        items=[
            _serialize_revision_meeting_attachment(
                row,
                user=current_user,
                can_delete=can_delete,
            )
            for row in rows
        ],
        can_upload=True,
    )
    db.commit()
    return response


@router.post(
    "/datasets/{dataset_key}/revisions/overview-history/{history_id}/meeting-attachments",
    response_model=LegacyIssueRevisionMeetingAttachmentItem,
    status_code=status.HTTP_201_CREATED,
)
async def upload_legacy_issue_revision_meeting_attachment(
    dataset_key: str,
    history_id: str,
    view_key: str | None = Query(default=None),
    file: UploadFile = File(...),
    description: str | None = Form(default=None, max_length=500),
    client_request_id: str = Form(..., min_length=1, max_length=64),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueRevisionMeetingAttachmentItem:
    definition = get_dataset_definition(dataset_key)
    revision_dataset_key = _module_revision_dataset_key(definition, view_key)
    existing = find_existing_revision_meeting_attachment_upload(
        db,
        workspace=current_workspace,
        dataset_key=revision_dataset_key,
        history_id=history_id,
        user=current_user,
        client_request_id=client_request_id,
    )
    if existing is not None:
        can_delete = can_delete_revision_meeting_attachment(db, user=current_user)
        response = _serialize_revision_meeting_attachment(
            existing,
            user=current_user,
            can_delete=can_delete,
        )
        db.commit()
        return response

    upload = await read_revision_meeting_attachment_upload(file)
    try:
        result = upload_revision_meeting_attachment(
            db,
            workspace=current_workspace,
            dataset_key=revision_dataset_key,
            history_id=history_id,
            user=current_user,
            upload=upload,
            description=description,
            client_request_id=client_request_id,
        )
        row = result.attachment
        commit_recovery = {
            "workspace_id": current_workspace.id,
            "dataset_key": revision_dataset_key,
            "history_id": row.overview_history_id,
            "attachment_id": row.id,
            "storage_key": row.storage_key,
        }
        try:
            db.commit()
        except Exception as commit_error:
            try:
                db.rollback()
            finally:
                if result.created:
                    recover_revision_meeting_attachment_upload_commit(
                        commit_error=commit_error,
                        **commit_recovery,
                    )
            raise
        can_delete = can_delete_revision_meeting_attachment(db, user=current_user)
        return _serialize_revision_meeting_attachment(
            row,
            user=current_user,
            can_delete=can_delete,
        )
    finally:
        upload.content.close()


@router.patch(
    "/datasets/{dataset_key}/revisions/meeting-attachments/{attachment_id}",
    response_model=LegacyIssueRevisionMeetingAttachmentItem,
)
def update_legacy_issue_revision_meeting_attachment(
    dataset_key: str,
    attachment_id: str,
    payload: LegacyIssueRevisionMeetingAttachmentUpdateRequest,
    view_key: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueRevisionMeetingAttachmentItem:
    definition = get_dataset_definition(dataset_key)
    revision_dataset_key = _module_revision_dataset_key(definition, view_key)
    row = update_revision_meeting_attachment_description(
        db,
        workspace=current_workspace,
        dataset_key=revision_dataset_key,
        attachment_id=attachment_id,
        user=current_user,
        description=payload.description,
    )
    db.commit()
    can_delete = can_delete_revision_meeting_attachment(db, user=current_user)
    return _serialize_revision_meeting_attachment(
        row,
        user=current_user,
        can_delete=can_delete,
    )


@router.get(
    "/datasets/{dataset_key}/revisions/meeting-attachments/{attachment_id}/file",
    response_class=StreamingResponse,
    responses={
        status.HTTP_200_OK: {
            "content": {
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
            },
            "description": "Legacy issue revision meeting attachment file",
        }
    },
)
def open_legacy_issue_revision_meeting_attachment(
    dataset_key: str,
    attachment_id: str,
    view_key: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> StreamingResponse:
    definition = get_dataset_definition(dataset_key)
    revision_dataset_key = _module_revision_dataset_key(definition, view_key)
    content = open_revision_meeting_attachment(
        db,
        workspace=current_workspace,
        dataset_key=revision_dataset_key,
        attachment_id=attachment_id,
    )
    return StreamingResponse(
        content.body,
        media_type=content.media_type,
        headers=content.headers,
    )


@router.delete(
    "/datasets/{dataset_key}/revisions/meeting-attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_legacy_issue_revision_meeting_attachment(
    dataset_key: str,
    attachment_id: str,
    view_key: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> Response:
    definition = get_dataset_definition(dataset_key)
    revision_dataset_key = _module_revision_dataset_key(definition, view_key)
    delete_revision_meeting_attachment(
        db,
        workspace=current_workspace,
        dataset_key=revision_dataset_key,
        attachment_id=attachment_id,
        user=current_user,
    )
    db.commit()
    process_pending_revision_meeting_attachment_cleanups(
        db,
        workspace=current_workspace,
        limit=100,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/datasets/{dataset_key}/revisions/draft", response_model=LegacyIssueRevisionItem)
def create_legacy_issue_dataset_draft_revision(
    dataset_key: str,
    payload: LegacyIssueRevisionActionRequest | None = None,
    base_revision_id: str | None = Query(default=None),
    view_key: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueRevisionItem:
    definition = get_dataset_definition(dataset_key)
    revision = create_dataset_draft_revision(
        db,
        definition,
        workspace=current_workspace,
        user=current_user,
        base_revision_id=base_revision_id,
        note=payload.note if payload else None,
        module_key=view_key,
    )
    db.commit()
    return _serialize_revision(
        get_revision(
            db,
            workspace=current_workspace,
            dataset_key=_module_revision_dataset_key(definition, view_key),
            revision_id=revision.id,
        )
    )


@router.patch(
    "/datasets/{dataset_key}/revisions/{revision_id}",
    response_model=LegacyIssueRevisionItem,
)
def update_legacy_issue_dataset_revision_note(
    dataset_key: str,
    revision_id: str,
    payload: LegacyIssueRevisionNoteUpdateRequest,
    view_key: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueRevisionItem:
    definition = get_dataset_definition(dataset_key)
    revision_dataset_key = _module_revision_dataset_key(definition, view_key)
    revision = update_revision_note(
        db,
        workspace=current_workspace,
        dataset_key=revision_dataset_key,
        revision_id=revision_id,
        note=payload.note,
    )
    db.commit()
    return _serialize_revision(
        get_revision(
            db,
            workspace=current_workspace,
            dataset_key=revision_dataset_key,
            revision_id=revision.id,
        )
    )


@router.patch(
    "/datasets/{dataset_key}/revisions/{revision_id}/approval-assignees",
    response_model=LegacyIssueRevisionItem,
)
def update_legacy_issue_dataset_revision_approval_assignees(
    dataset_key: str,
    revision_id: str,
    payload: LegacyIssueRevisionAssigneesRequest,
    view_key: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueRevisionItem:
    definition = get_dataset_definition(dataset_key)
    revision_dataset_key = _module_revision_dataset_key(definition, view_key)
    revision = update_revision_approval_assignees(
        db,
        workspace=current_workspace,
        dataset_key=revision_dataset_key,
        user=current_user,
        revision_id=revision_id,
        reviewer_id=payload.reviewer_id,
        approver_id=payload.approver_id,
    )
    db.commit()
    return _serialize_revision(
        get_revision(
            db,
            workspace=current_workspace,
            dataset_key=revision_dataset_key,
            revision_id=revision.id,
        )
    )


@router.post(
    "/datasets/{dataset_key}/revisions/{revision_id}/review-request",
    response_model=LegacyIssueRevisionItem,
)
def request_legacy_issue_dataset_revision_approval(
    dataset_key: str,
    revision_id: str,
    request: Request,
    payload: LegacyIssueRevisionApprovalRequestPayload | None = None,
    view_key: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueRevisionItem:
    definition = get_dataset_definition(dataset_key)
    effective_view_key = payload.view_key if payload and payload.view_key else view_key
    revision_dataset_key = _module_revision_dataset_key(definition, effective_view_key)
    revision, recipients = request_revision_approval(
        db,
        workspace=current_workspace,
        dataset_key=revision_dataset_key,
        user=current_user,
        revision_id=revision_id,
    )
    event_publisher = DmEventPublisher(db=db, realtime=request.app.state.app_realtime)
    _create_revision_approval_notifications(
        db,
        workspace=current_workspace,
        revision=revision,
        requester=current_user,
        recipients=recipients,
        view_key=effective_view_key,
        events=event_publisher,
    )
    db.commit()
    return _serialize_revision(
        get_revision(
            db,
            workspace=current_workspace,
            dataset_key=revision_dataset_key,
            revision_id=revision.id,
        )
    )


@router.post(
    "/datasets/{dataset_key}/revisions/{revision_id}/review-complete",
    response_model=LegacyIssueRevisionItem,
)
def complete_legacy_issue_dataset_revision_review(
    dataset_key: str,
    revision_id: str,
    view_key: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueRevisionItem:
    definition = get_dataset_definition(dataset_key)
    revision_dataset_key = _module_revision_dataset_key(definition, view_key)
    revision = complete_revision_review(
        db,
        workspace=current_workspace,
        dataset_key=revision_dataset_key,
        user=current_user,
        revision_id=revision_id,
    )
    db.commit()
    return _serialize_revision(
        get_revision(
            db,
            workspace=current_workspace,
            dataset_key=revision_dataset_key,
            revision_id=revision.id,
        )
    )


@router.post(
    "/datasets/{dataset_key}/revisions/{revision_id}/approval-complete",
    response_model=LegacyIssueRevisionItem,
)
def complete_legacy_issue_dataset_revision_approval(
    dataset_key: str,
    revision_id: str,
    view_key: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueRevisionItem:
    definition = get_dataset_definition(dataset_key)
    revision_dataset_key = _module_revision_dataset_key(definition, view_key)
    revision = complete_revision_approval(
        db,
        workspace=current_workspace,
        dataset_key=revision_dataset_key,
        user=current_user,
        revision_id=revision_id,
    )
    db.commit()
    return _serialize_revision(
        get_revision(
            db,
            workspace=current_workspace,
            dataset_key=revision_dataset_key,
            revision_id=revision.id,
        )
    )


@router.post(
    "/datasets/{dataset_key}/revisions/{revision_id}/publish",
    response_model=LegacyIssueRevisionItem,
)
def publish_legacy_issue_dataset_revision(
    dataset_key: str,
    revision_id: str,
    payload: LegacyIssueRevisionPublishRequest,
    view_key: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueRevisionItem:
    definition = get_dataset_definition(dataset_key)
    revision_dataset_key = _module_revision_dataset_key(definition, view_key)
    revision = publish_draft_revision(
        db,
        workspace=current_workspace,
        dataset_key=revision_dataset_key,
        user=current_user,
        revision_id=revision_id,
        note=payload.note,
    )
    stamp_introduced_revision_numbers(
        db,
        definition,
        workspace=current_workspace,
        revision=revision,
    )
    reindex_definition = get_dataset_definition_with_all_module_fields(
        db,
        dataset_key=definition.key,
        workspace=current_workspace,
    )
    reindex_legacy_issue_revision_ai_chunks(
        db,
        reindex_definition,
        workspace=current_workspace,
        revision=revision,
    )
    db.commit()
    return _serialize_revision(
        get_revision(
            db,
            workspace=current_workspace,
            dataset_key=revision_dataset_key,
            revision_id=revision.id,
        )
    )


@router.post(
    "/datasets/{dataset_key}/revisions/{revision_id}/cancel", response_model=LegacyIssueRevisionItem
)
def cancel_legacy_issue_dataset_revision(
    dataset_key: str,
    revision_id: str,
    payload: LegacyIssueRevisionCancelRequest | None = None,
    view_key: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueRevisionItem:
    definition = get_dataset_definition(dataset_key)
    module_key = normalize_legacy_issue_module_key(view_key)
    revision_dataset_key = _module_revision_dataset_key(definition, view_key)
    if module_key is None:  # pragma: no cover - guarded by _module_revision_dataset_key
        raise localized_http_exception(
            status_code=409,
            code="legacy_issues.aggregate_readonly",
        )
    revision = cancel_draft_revision(
        db,
        workspace=current_workspace,
        dataset_key=revision_dataset_key,
        module_key=module_key,
        user=current_user,
        revision_id=revision_id,
        note=payload.note if payload else None,
        force=payload.force if payload else False,
    )
    db.commit()
    return _serialize_revision(
        get_revision(
            db,
            workspace=current_workspace,
            dataset_key=revision_dataset_key,
            revision_id=revision.id,
        )
    )


@router.post(
    "/datasets/{dataset_key}/revisions/{revision_id}/restore",
    response_model=LegacyIssueRevisionItem,
)
def restore_legacy_issue_dataset_revision(
    dataset_key: str,
    revision_id: str,
    payload: LegacyIssueRevisionActionRequest | None = None,
    view_key: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueRevisionItem:
    definition = get_dataset_definition(dataset_key)
    revision = create_dataset_draft_revision(
        db,
        definition,
        workspace=current_workspace,
        user=current_user,
        base_revision_id=revision_id,
        note=payload.note if payload else None,
        module_key=view_key,
    )
    db.commit()
    return _serialize_revision(
        get_revision(
            db,
            workspace=current_workspace,
            dataset_key=_module_revision_dataset_key(definition, view_key),
            revision_id=revision.id,
        )
    )


@router.get(
    "/datasets/{dataset_key}/revisions/compare", response_model=LegacyIssueRevisionCompareResponse
)
def compare_legacy_issue_dataset_revision(
    dataset_key: str,
    left_revision_id: str = Query(...),
    right_revision_id: str = Query(...),
    view_key: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueRevisionCompareResponse:
    definition = get_dataset_definition_for_view(
        db,
        dataset_key=dataset_key,
        workspace=current_workspace,
        view_key=view_key,
    )
    module_key = normalize_legacy_issue_module_key(view_key)
    revision_dataset_key = _module_revision_dataset_key(definition, view_key)
    left_revision = get_revision(
        db,
        workspace=current_workspace,
        dataset_key=revision_dataset_key,
        revision_id=left_revision_id,
    )
    right_revision = get_revision(
        db,
        workspace=current_workspace,
        dataset_key=revision_dataset_key,
        revision_id=right_revision_id,
    )
    return LegacyIssueRevisionCompareResponse(
        left_revision=_serialize_revision(left_revision),
        right_revision=_serialize_revision(right_revision),
        rows=[
            LegacyIssueRevisionCompareRowItem(
                stable_record_id=row.stable_record_id,
                status=row.status,
                label=row.label,
                cells=[
                    LegacyIssueRevisionCompareCellItem(
                        field_key=cell.field_key,
                        field_label=cell.field_label,
                        left_value=cell.left_value,
                        right_value=cell.right_value,
                        changed=cell.changed,
                    )
                    for cell in row.cells
                ],
            )
            for row in compare_dataset_revisions(
                db,
                definition,
                workspace=current_workspace,
                left_revision=left_revision,
                right_revision=right_revision,
                module_key=module_key,
            )
        ],
    )


@router.get("/datasets/{dataset_key}/records", response_model=LegacyIssueRecordListResponse)
def list_legacy_issue_dataset_records(
    dataset_key: str,
    department: list[str] | None = Query(default=None),
    q: str | None = Query(default=None, max_length=500),
    revision_id: str | None = Query(default=None),
    view_key: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueRecordListResponse:
    definition = get_dataset_definition_for_view(
        db,
        dataset_key=dataset_key,
        workspace=current_workspace,
        view_key=view_key,
    )
    module_key = normalize_legacy_issue_module_key(view_key)
    aggregate_revisions: list[LegacyIssueDataRevision] | None = None
    if module_key is None:
        if revision_id is not None:
            raise localized_http_exception(
                status_code=409,
                code="legacy_issues.aggregate_readonly",
            )
        aggregate_revisions = _latest_module_revisions(
            db,
            definition=definition,
            workspace=current_workspace,
        )
        revision_context = resolve_read_revision(
            db,
            workspace=current_workspace,
            dataset_key=legacy_issue_dataset_revision_key(definition.key),
        )
    else:
        revision_context = resolve_read_revision(
            db,
            workspace=current_workspace,
            dataset_key=legacy_issue_dataset_revision_key(definition.key, module_key),
            revision_id=revision_id,
        )
    rows, total = list_dataset_records(
        db,
        definition,
        workspace=current_workspace,
        revision=revision_context.current if module_key is not None else None,
        revisions=aggregate_revisions,
        module_key=module_key,
        departments=department,
        query=q,
        limit=limit,
        offset=offset,
    )
    attachments_by_record_id = list_dataset_attachments_for_records(
        db,
        definition,
        workspace=current_workspace,
        record_ids=[row.id for row in rows],
    )
    response = LegacyIssueRecordListResponse(
        items=[
            _serialize_record(
                row,
                attachments=attachments_by_record_id.get(row.id, []),
            )
            for row in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
        revision=_serialize_revision_context(
            revision_context,
            can_direct_edit_published_revision=(
                module_key is not None
                and can_direct_edit_published_revision(
                    db,
                    workspace=current_workspace,
                    user=current_user,
                    module_key=module_key,
                    context=revision_context,
                )
            ),
            can_force_cancel_active_draft=(
                module_key is not None
                and revision_context.active_draft is not None
                and revision_context.active_draft.locked_by_id is not None
                and revision_context.active_draft.locked_by_id != current_user.id
                and can_user_direct_edit_module(
                    db,
                    workspace=current_workspace,
                    user=current_user,
                    module_key=module_key,
                )
            ),
        ),
    )
    db.commit()
    return response


@router.post(
    "/datasets/{dataset_key}/records",
    response_model=LegacyIssueRecordItem,
    status_code=status.HTTP_201_CREATED,
)
def create_legacy_issue_dataset_record(
    dataset_key: str,
    payload: LegacyIssueRecordUpsertRequest,
    revision_id: str | None = Query(default=None),
    view_key: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueRecordItem:
    definition = get_dataset_definition_for_view(
        db,
        dataset_key=dataset_key,
        workspace=current_workspace,
        view_key=view_key,
    )
    module_key = normalize_legacy_issue_module_key(view_key)
    if module_key is None:
        raise localized_http_exception(
            status_code=409,
            code="legacy_issues.aggregate_readonly",
        )
    revision = require_draft_revision_editor(
        db,
        workspace=current_workspace,
        dataset_key=legacy_issue_dataset_revision_key(definition.key, module_key),
        user=current_user,
        revision_id=revision_id,
    )
    invalidate_revision_approval_for_content_change(
        db,
        workspace=current_workspace,
        revision=revision,
        user=current_user,
    )
    row = create_dataset_record(
        db,
        definition,
        workspace=current_workspace,
        user=current_user,
        revision=revision,
        values=payload.values,
        module_key=module_key,
    )
    reindex_legacy_issue_record_ai_chunks(
        db,
        definition,
        workspace=current_workspace,
        revision=revision,
        record=row,
    )
    db.commit()
    return _serialize_record(
        get_dataset_record(db, definition, workspace=current_workspace, record_id=row.id),
        attachments=[],
    )


@router.patch(
    "/datasets/{dataset_key}/records/batch",
    response_model=LegacyIssueRecordBatchSaveResponse,
)
def save_legacy_issue_dataset_records_batch(
    dataset_key: str,
    payload: LegacyIssueRecordBatchSaveRequest,
    revision_id: str | None = Query(default=None),
    view_key: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueRecordBatchSaveResponse:
    definition = get_dataset_definition_for_view(
        db,
        dataset_key=dataset_key,
        workspace=current_workspace,
        view_key=view_key,
    )
    module_key, revision = _require_module_record_editor(
        db,
        definition=definition,
        workspace=current_workspace,
        user=current_user,
        view_key=view_key,
        revision_id=revision_id,
    )
    merged_updates: dict[str, dict[str, Any | None]] = {}
    for update in payload.updates:
        if not update.values:
            continue
        merged_updates.setdefault(update.record_id, {}).update(update.values)

    if merged_updates or payload.creates:
        invalidate_revision_approval_for_content_change(
            db,
            workspace=current_workspace,
            revision=revision,
            user=current_user,
        )

    rows: list[LegacyIssueRecord] = []
    for record_id, values in merged_updates.items():
        row = update_dataset_record(
            db,
            definition,
            workspace=current_workspace,
            user=current_user,
            revision=revision,
            record_id=record_id,
            values=values,
            module_key=module_key,
        )
        reindex_legacy_issue_record_ai_chunks(
            db,
            definition,
            workspace=current_workspace,
            revision=revision,
            record=row,
        )
        rows.append(row)

    created = 0
    created_rows: list[tuple[str | None, LegacyIssueRecord]] = []
    for create in payload.creates:
        row = create_dataset_record(
            db,
            definition,
            workspace=current_workspace,
            user=current_user,
            revision=revision,
            values=create.values,
            module_key=module_key,
        )
        reindex_legacy_issue_record_ai_chunks(
            db,
            definition,
            workspace=current_workspace,
            revision=revision,
            record=row,
        )
        rows.append(row)
        created_rows.append((create.client_row_id, row))
        created += 1

    if revision.status == REVISION_STATUS_DRAFT and payload.release_editing:
        release_draft_revision_editing(
            db,
            workspace=current_workspace,
            dataset_key=revision.dataset_key,
            user=current_user,
            revision_id=revision.id,
        )

    db.commit()
    record_ids = [row.id for row in rows]
    attachments_by_record_id = list_dataset_attachments_for_records(
        db,
        definition,
        workspace=current_workspace,
        record_ids=record_ids,
    )
    serialized_items = [
        _serialize_record(
            row,
            attachments=attachments_by_record_id.get(row.id, []),
        )
        for row in rows
    ]
    serialized_by_id = {item.id: item for item in serialized_items}
    return LegacyIssueRecordBatchSaveResponse(
        items=serialized_items,
        created_records=[
            LegacyIssueRecordBatchCreatedItem(
                client_row_id=client_row_id,
                record=serialized_by_id[row.id],
            )
            for client_row_id, row in created_rows
        ],
        created=created,
        updated=len(merged_updates),
    )


@router.get("/datasets/{dataset_key}/records/{record_id}", response_model=LegacyIssueRecordItem)
def get_legacy_issue_dataset_record(
    dataset_key: str,
    record_id: str,
    view_key: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueRecordItem:
    definition = get_dataset_definition_for_view(
        db,
        dataset_key=dataset_key,
        workspace=current_workspace,
        view_key=view_key,
    )
    module_key = normalize_legacy_issue_module_key(view_key)
    if module_key is None:
        raise localized_http_exception(
            status_code=409,
            code="legacy_issues.aggregate_readonly",
        )
    row = get_dataset_record(
        db,
        definition,
        workspace=current_workspace,
        record_id=record_id,
        module_key=module_key,
    )
    attachments = list_dataset_attachments_for_records(
        db,
        definition,
        workspace=current_workspace,
        record_ids=[record_id],
    ).get(record_id, [])
    return _serialize_record(row, attachments=attachments)


@router.get(
    "/datasets/{dataset_key}/records/{record_id}/history",
    response_model=LegacyIssueRecordHistoryResponse,
)
def list_legacy_issue_dataset_record_history(
    dataset_key: str,
    record_id: str,
    view_key: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueRecordHistoryResponse:
    definition = get_dataset_definition_for_view(
        db,
        dataset_key=dataset_key,
        workspace=current_workspace,
        view_key=view_key,
    )
    module_key = normalize_legacy_issue_module_key(view_key)
    if module_key is None:
        raise localized_http_exception(
            status_code=409,
            code="legacy_issues.aggregate_readonly",
        )
    record = get_dataset_record(
        db,
        definition,
        workspace=current_workspace,
        record_id=record_id,
        module_key=module_key,
    )
    history_record_ids, record_revision_ids = _history_scope(
        db,
        definition=definition,
        workspace=current_workspace,
        record=record,
    )
    history_rows = list_record_history(
        db,
        workspace=current_workspace,
        record_kind=LEGACY_ISSUE_RECORD_KIND,
        dataset_key=definition.key,
        record_ids=history_record_ids,
    )
    revisions = _history_revisions(
        db, history_rows=history_rows, record_revision_ids=record_revision_ids
    )
    history_items = [
        _serialize_record_history(row, revisions=revisions, record_revision_ids=record_revision_ids)
        for row in history_rows
    ]
    history_items.extend(
        _revision_diff_history_items(
            db,
            definition=definition,
            workspace=current_workspace,
            record=record,
            existing_history_keys=_history_existing_revision_fields(
                history_rows,
                record_revision_ids=record_revision_ids,
            ),
        )
    )
    return LegacyIssueRecordHistoryResponse(items=_sort_history_items(history_items))


@router.patch("/datasets/{dataset_key}/records/{record_id}", response_model=LegacyIssueRecordItem)
def update_legacy_issue_dataset_record(
    dataset_key: str,
    record_id: str,
    payload: LegacyIssueRecordUpsertRequest,
    revision_id: str | None = Query(default=None),
    view_key: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueRecordItem:
    definition = get_dataset_definition_for_view(
        db,
        dataset_key=dataset_key,
        workspace=current_workspace,
        view_key=view_key,
    )
    module_key, revision = _require_module_record_editor(
        db,
        definition=definition,
        workspace=current_workspace,
        user=current_user,
        view_key=view_key,
        revision_id=revision_id,
    )
    invalidate_revision_approval_for_content_change(
        db,
        workspace=current_workspace,
        revision=revision,
        user=current_user,
    )
    row = update_dataset_record(
        db,
        definition,
        workspace=current_workspace,
        user=current_user,
        revision=revision,
        record_id=record_id,
        values=payload.values,
        module_key=module_key,
    )
    reindex_legacy_issue_record_ai_chunks(
        db,
        definition,
        workspace=current_workspace,
        revision=revision,
        record=row,
    )
    db.commit()
    attachments = list_dataset_attachments_for_records(
        db,
        definition,
        workspace=current_workspace,
        record_ids=[record_id],
    ).get(record_id, [])
    return _serialize_record(row, attachments=attachments)


@router.delete(
    "/datasets/{dataset_key}/records/{record_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_legacy_issue_dataset_record(
    dataset_key: str,
    record_id: str,
    revision_id: str | None = Query(default=None),
    view_key: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> Response:
    definition = get_dataset_definition_for_view(
        db,
        dataset_key=dataset_key,
        workspace=current_workspace,
        view_key=view_key,
    )
    _module_key, revision = _require_module_record_editor(
        db,
        definition=definition,
        workspace=current_workspace,
        user=current_user,
        view_key=view_key,
        revision_id=revision_id,
    )
    invalidate_revision_approval_for_content_change(
        db,
        workspace=current_workspace,
        revision=revision,
        user=current_user,
    )
    delete_legacy_issue_record_ai_chunks(
        db,
        workspace=current_workspace,
        dataset_key=definition.key,
        record_id=record_id,
    )
    delete_dataset_record(
        db, definition, workspace=current_workspace, revision=revision, record_id=record_id
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/datasets/{dataset_key}/import-preview",
    response_model=LegacyIssueImportPreviewResponse,
)
async def preview_legacy_issue_dataset_import(
    dataset_key: str,
    view_key: str | None = Query(default=None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db_session),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueImportPreviewResponse:
    definition = get_dataset_definition_for_view(
        db,
        dataset_key=dataset_key,
        workspace=current_workspace,
        view_key=view_key,
    )
    preview = build_import_preview(
        definition,
        filename=file.filename or "",
        content=await file.read(),
    )
    return _serialize_import_preview(preview)


@router.post("/datasets/{dataset_key}/imports", response_model=LegacyIssueImportResponse)
async def import_legacy_issue_dataset_records(
    dataset_key: str,
    mapping_json: str | None = Form(default=None),
    revision_id: str | None = Form(default=None),
    view_key: str | None = Form(default=None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueImportResponse:
    definition = get_dataset_definition_for_view(
        db,
        dataset_key=dataset_key,
        workspace=current_workspace,
        view_key=view_key,
    )
    module_key = normalize_legacy_issue_module_key(view_key)
    if module_key is None:
        raise localized_http_exception(
            status_code=409,
            code="legacy_issues.aggregate_readonly",
        )
    revision = require_draft_revision_editor(
        db,
        workspace=current_workspace,
        dataset_key=legacy_issue_dataset_revision_key(definition.key, module_key),
        user=current_user,
        revision_id=revision_id,
    )
    filename = file.filename or ""
    content = await file.read()
    mapping = (
        parse_mapping_json(mapping_json)
        if mapping_json
        else build_import_preview(definition, filename=filename, content=content).suggested_mapping
    )
    result = import_dataset_records(
        db,
        definition,
        workspace=current_workspace,
        user=current_user,
        revision=revision,
        filename=filename,
        content=content,
        mapping=mapping,
        module_key=module_key,
    )
    if result.created or result.updated:
        invalidate_revision_approval_for_content_change(
            db,
            workspace=current_workspace,
            revision=revision,
            user=current_user,
        )
    reindex_definition = get_dataset_definition_with_all_module_fields(
        db,
        dataset_key=definition.key,
        workspace=current_workspace,
    )
    reindex_legacy_issue_revision_ai_chunks(
        db,
        reindex_definition,
        workspace=current_workspace,
        revision=revision,
    )
    db.commit()
    return LegacyIssueImportResponse(
        created=result.created,
        updated=result.updated,
        skipped=result.skipped,
        total_rows=result.total_rows,
    )


@router.get("/datasets/{dataset_key}/export.xlsx")
def export_legacy_issue_dataset_records(
    dataset_key: str,
    department: list[str] | None = Query(default=None),
    revision_id: str | None = Query(default=None),
    view_key: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> StreamingResponse:
    definition = get_dataset_definition_for_view(
        db,
        dataset_key=dataset_key,
        workspace=current_workspace,
        view_key=view_key,
    )
    module_key = normalize_legacy_issue_module_key(view_key)
    if module_key is None:
        raise localized_http_exception(
            status_code=409,
            code="legacy_issues.aggregate_readonly",
        )
    revision = resolve_read_revision(
        db,
        workspace=current_workspace,
        dataset_key=legacy_issue_dataset_revision_key(definition.key, module_key),
        revision_id=revision_id,
    ).current
    rows, _total = list_dataset_records(
        db,
        definition,
        workspace=current_workspace,
        revision=revision,
        module_key=module_key,
        departments=department,
        limit=DATASET_RECORD_EXPORT_LIMIT,
        offset=0,
    )
    body = export_dataset_records_xlsx(definition, rows)
    return StreamingResponse(
        BytesIO(body),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=legacy-issue-{dataset_key}.xlsx",
            "Cache-Control": "no-store",
        },
    )


@router.post(
    "/datasets/{dataset_key}/excel-exports",
    response_model=LegacyIssueExcelExportJobItem,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_legacy_issue_dataset_excel_export(
    dataset_key: str,
    payload: LegacyIssueExcelExportCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueExcelExportJobItem:
    definition = get_dataset_definition_for_view(
        db,
        dataset_key=dataset_key,
        workspace=current_workspace,
        view_key=payload.view_key,
    )
    module_key = normalize_legacy_issue_module_key(payload.view_key)
    if module_key is None:
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="legacy_issues.aggregate_readonly",
        )
    revision = resolve_read_revision(
        db,
        workspace=current_workspace,
        dataset_key=legacy_issue_dataset_revision_key(definition.key, module_key),
        revision_id=payload.revision_id,
    ).current
    job = create_dataset_excel_export_job(
        db,
        workspace=current_workspace,
        user=current_user,
        definition=definition,
        revision=revision,
        view_key=module_key,
        departments=payload.departments or None,
        column_keys=payload.column_keys,
        record_ids=payload.record_ids,
        include_attachments=payload.include_attachments,
    )
    db.commit()
    return _serialize_excel_export_job(job)


@router.get(
    "/excel-exports/{job_id}",
    response_model=LegacyIssueExcelExportJobItem,
)
def get_legacy_issue_excel_export(
    job_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueExcelExportJobItem:
    job = get_excel_export_job(
        db,
        workspace=current_workspace,
        user=current_user,
        job_id=job_id,
    )
    return _serialize_excel_export_job(job)


@router.get(
    "/excel-exports/{job_id}/file",
    response_class=StreamingResponse,
    responses={
        status.HTTP_200_OK: {
            "content": {
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {
                    "schema": {"type": "string", "format": "binary"}
                }
            },
            "description": "Generated legacy issue Excel export",
        }
    },
)
def open_legacy_issue_excel_export(
    job_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> StreamingResponse:
    content = open_excel_export_result(
        db,
        workspace=current_workspace,
        user=current_user,
        job_id=job_id,
    )
    return StreamingResponse(
        content.body,
        media_type=content.media_type,
        headers=content.headers,
    )


@router.post(
    "/datasets/{dataset_key}/records/{record_id}/attachments",
    response_model=LegacyIssueAttachmentItem,
    status_code=status.HTTP_201_CREATED,
)
async def upload_legacy_issue_dataset_attachment(
    dataset_key: str,
    record_id: str,
    file: UploadFile = File(...),
    is_primary: bool = Form(False),
    description: str | None = Form(None, max_length=500),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueAttachmentItem:
    definition = get_dataset_definition(dataset_key)
    record = get_dataset_record(db, definition, workspace=current_workspace, record_id=record_id)
    revision = require_record_revision_editor(
        db,
        workspace=current_workspace,
        dataset_key=_record_revision_dataset_key(definition, record),
        module_key=record.module_key,
        user=current_user,
        revision_id=record.revision_id,
    )
    invalidate_revision_approval_for_content_change(
        db,
        workspace=current_workspace,
        revision=revision,
        user=current_user,
    )
    row = upload_dataset_attachment(
        db,
        definition,
        workspace=current_workspace,
        user=current_user,
        record_id=record_id,
        upload=DatasetAttachmentUpload(
            filename=file.filename,
            content_type=file.content_type,
            content=await file.read(),
            is_primary=is_primary,
            description=description,
        ),
    )
    if get_legacy_issue_settings().ai_attachment_index_enabled:
        enqueue_legacy_issue_attachment_index_job(
            db,
            attachment=row,
            trigger="upload",
        )
    db.commit()
    return _serialize_attachment(row)


@router.patch(
    "/datasets/{dataset_key}/attachments/{attachment_id}",
    response_model=LegacyIssueAttachmentItem,
)
def update_legacy_issue_dataset_attachment(
    dataset_key: str,
    attachment_id: str,
    payload: LegacyIssueAttachmentUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueAttachmentItem:
    definition = get_dataset_definition(dataset_key)
    attachment = get_dataset_attachment(
        db, definition, workspace=current_workspace, attachment_id=attachment_id
    )
    record = get_dataset_record(
        db,
        definition,
        workspace=current_workspace,
        record_id=attachment.record_id,
    )
    revision_dataset_key = _record_revision_dataset_key(definition, record)
    revision = require_record_revision_editor(
        db,
        workspace=current_workspace,
        dataset_key=revision_dataset_key,
        module_key=record.module_key,
        user=current_user,
        revision_id=record.revision_id,
    )
    if payload.model_fields_set:
        invalidate_revision_approval_for_content_change(
            db,
            workspace=current_workspace,
            revision=revision,
            user=current_user,
        )
    row = attachment
    if "is_primary" in payload.model_fields_set and payload.is_primary is not None:
        row = set_dataset_attachment_primary(
            db,
            definition,
            workspace=current_workspace,
            user=current_user,
            attachment_id=attachment_id,
            is_primary=payload.is_primary,
        )
    if "description" in payload.model_fields_set:
        row = update_dataset_attachment_description(
            db,
            definition,
            workspace=current_workspace,
            user=current_user,
            attachment_id=attachment_id,
            description=payload.description,
        )
        if get_legacy_issue_settings().ai_attachment_index_enabled:
            enqueue_legacy_issue_attachment_index_job(
                db,
                attachment=row,
                trigger="description_update",
            )
    db.commit()
    return _serialize_attachment(row)


@router.post(
    "/datasets/{dataset_key}/attachments/{attachment_id}/index",
    response_model=LegacyIssueAttachmentItem,
)
def retry_legacy_issue_dataset_attachment_index(
    dataset_key: str,
    attachment_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> LegacyIssueAttachmentItem:
    definition = get_dataset_definition(dataset_key)
    attachment = get_dataset_attachment(
        db, definition, workspace=current_workspace, attachment_id=attachment_id
    )
    record = get_dataset_record(
        db,
        definition,
        workspace=current_workspace,
        record_id=attachment.record_id,
    )
    require_record_revision_editor(
        db,
        workspace=current_workspace,
        dataset_key=_record_revision_dataset_key(definition, record),
        module_key=record.module_key,
        user=current_user,
        revision_id=record.revision_id,
    )
    enqueue_legacy_issue_attachment_index_job(
        db,
        attachment=attachment,
        trigger="manual_retry",
    )
    db.commit()
    return _serialize_attachment(attachment)


@router.delete(
    "/datasets/{dataset_key}/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_legacy_issue_dataset_attachment(
    dataset_key: str,
    attachment_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> Response:
    definition = get_dataset_definition(dataset_key)
    attachment = get_dataset_attachment(
        db, definition, workspace=current_workspace, attachment_id=attachment_id
    )
    record = get_dataset_record(
        db,
        definition,
        workspace=current_workspace,
        record_id=attachment.record_id,
    )
    revision = require_record_revision_editor(
        db,
        workspace=current_workspace,
        dataset_key=_record_revision_dataset_key(definition, record),
        module_key=record.module_key,
        user=current_user,
        revision_id=record.revision_id,
    )
    invalidate_revision_approval_for_content_change(
        db,
        workspace=current_workspace,
        revision=revision,
        user=current_user,
    )
    delete_legacy_issue_attachment_index_data(
        db,
        workspace_id=current_workspace.id,
        attachment_id=attachment_id,
    )
    delete_dataset_attachment(
        db,
        definition,
        workspace=current_workspace,
        user=current_user,
        attachment_id=attachment_id,
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/datasets/{dataset_key}/attachments/{attachment_id}/file")
def open_legacy_issue_dataset_attachment(
    dataset_key: str,
    attachment_id: str,
    db: Session = Depends(get_db_session),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> StreamingResponse:
    definition = get_dataset_definition(dataset_key)
    attachment = get_dataset_attachment(
        db,
        definition,
        workspace=current_workspace,
        attachment_id=attachment_id,
    )
    _require_attachment_module_enabled(
        db,
        definition=definition,
        workspace=current_workspace,
        attachment=attachment,
    )
    content = open_dataset_attachment_content(
        db,
        definition,
        workspace=current_workspace,
        attachment_id=attachment_id,
    )
    return StreamingResponse(
        content.body,
        media_type=content.media_type,
        headers=content.headers,
    )


def _require_attachment_module_enabled(
    db: Session,
    *,
    definition: LegacyIssueDatasetDefinition,
    workspace: Workspace,
    attachment: LegacyIssueAttachment,
) -> None:
    record = get_dataset_record(
        db,
        definition,
        workspace=workspace,
        record_id=attachment.record_id,
    )
    _require_enabled_module(record.module_key)


def _serialize_assistant_result(
    result: LegacyIssueAssistantResult,
    *,
    question: str | None = None,
    created_at: Any | None = None,
    requested_by: User | None = None,
) -> LegacyIssueAssistantRunResponse:
    return LegacyIssueAssistantRunResponse(
        run_id=result.run_id,
        question=question,
        created_at=created_at,
        requested_by_id=requested_by.id if requested_by else None,
        requested_by_name=_user_display_name(requested_by) if requested_by else None,
        requested_by_email=requested_by.email if requested_by else None,
        answer_markdown=result.answer_markdown,
        analysis_plan=_serialize_assistant_plan(result.analysis_plan),
        analysis_result=getattr(result, "analysis_result", None),
        evidence=[_serialize_assistant_evidence(item) for item in result.evidence],
        search_profile=_serialize_assistant_search_profile(result.search_profile),
        gateway_decisions=result.gateway_decisions,
    )


def _serialize_assistant_run(row: LegacyIssueAssistantRun) -> LegacyIssueAssistantRunResponse:
    requested_by = row.requested_by
    return LegacyIssueAssistantRunResponse(
        run_id=row.id,
        question=row.question,
        created_at=row.created_at,
        requested_by_id=row.requested_by_id,
        requested_by_name=_user_display_name(requested_by) if requested_by else None,
        requested_by_email=requested_by.email if requested_by else None,
        answer_markdown=row.answer_markdown,
        analysis_plan=LegacyIssueAssistantPlanItem.model_validate(row.analysis_plan or {}),
        analysis_result=dict(row.analysis_result)
        if isinstance(row.analysis_result, dict)
        else None,
        evidence=[
            LegacyIssueAssistantEvidenceItem.model_validate(item)
            for item in (row.evidence or [])
            if isinstance(item, dict)
        ],
        search_profile=LegacyIssueAssistantSearchProfileItem.model_validate(
            row.search_profile or {}
        ),
        gateway_decisions=list(row.gateway_decisions or []),
    )


_INVALID_ASSISTANT_ANALYSIS_SCOPE = frozenset({"__invalid_legacy_issue_analysis_scope__"})


def _filter_enabled_assistant_runs(
    db: Session,
    *,
    workspace: Workspace,
    rows: list[LegacyIssueAssistantRun],
) -> list[LegacyIssueAssistantRun]:
    if _compressor_enabled():
        return [
            row
            for row in rows
            if _assistant_run_analysis_module_keys(row) != _INVALID_ASSISTANT_ANALYSIS_SCOPE
        ]
    enabled_module_keys = _enabled_module_keys()
    references_by_run: dict[str, set[str] | None] = {}
    analysis_scope_visible_by_run: dict[str, bool] = {}
    record_ids: set[str] = set()
    for row in rows:
        references: set[str] = set()
        valid = True
        for item in row.evidence or []:
            if not isinstance(item, dict) or not str(item.get("record_id") or "").strip():
                valid = False
                break
            references.add(str(item["record_id"]))
        references_by_run[row.id] = references if valid else None
        analysis_module_keys = _assistant_run_analysis_module_keys(row)
        analysis_scope_visible_by_run[row.id] = (
            analysis_module_keys is None or analysis_module_keys <= enabled_module_keys
        )
        record_ids.update(references)
    if not record_ids:
        return [
            row
            for row in rows
            if references_by_run[row.id] is not None and analysis_scope_visible_by_run[row.id]
        ]
    records = list(
        db.scalars(
            select(LegacyIssueRecord).where(
                LegacyIssueRecord.workspace_id == workspace.id,
                LegacyIssueRecord.id.in_(record_ids),
            )
        )
    )
    enabled_record_ids = {
        record.id
        for record in records
        if record.module_key is None or record.module_key in enabled_module_keys
    }
    return [
        row
        for row in rows
        if references_by_run[row.id] is not None
        and references_by_run[row.id] <= enabled_record_ids
        and analysis_scope_visible_by_run[row.id]
    ]


def _assistant_run_analysis_module_keys(
    row: LegacyIssueAssistantRun,
) -> frozenset[str] | None:
    payload = getattr(row, "analysis_result", None)
    if payload is None:
        return None
    if not isinstance(payload, dict):
        return _INVALID_ASSISTANT_ANALYSIS_SCOPE
    version = payload.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version != 1:
        return _INVALID_ASSISTANT_ANALYSIS_SCOPE
    scope = payload.get("scope")
    if not isinstance(scope, dict):
        return _INVALID_ASSISTANT_ANALYSIS_SCOPE
    raw_module_keys = scope.get("module_keys")
    if not isinstance(raw_module_keys, list):
        return _INVALID_ASSISTANT_ANALYSIS_SCOPE
    module_keys: set[str] = set()
    for raw_module_key in raw_module_keys:
        if not isinstance(raw_module_key, str) or not raw_module_key.strip():
            return _INVALID_ASSISTANT_ANALYSIS_SCOPE
        module_keys.add(raw_module_key.strip())
    if not module_keys:
        return _INVALID_ASSISTANT_ANALYSIS_SCOPE
    return frozenset(module_keys)


def _serialize_assistant_run_summary(
    row: LegacyIssueAssistantRun,
) -> LegacyIssueAssistantRunSummaryItem:
    requested_by = row.requested_by
    plan = row.analysis_plan or {}
    profile = row.search_profile or {}
    return LegacyIssueAssistantRunSummaryItem(
        run_id=row.id,
        question=row.question,
        answer_preview=_compact_preview(row.answer_markdown),
        created_at=row.created_at,
        requested_by_id=row.requested_by_id,
        requested_by_name=_user_display_name(requested_by) if requested_by else None,
        requested_by_email=requested_by.email if requested_by else None,
        evidence_count=int(profile.get("evidence_count") or 0),
        dataset_keys=[str(key) for key in plan.get("dataset_keys") or []],
        methods=[str(method) for method in profile.get("methods") or []],
    )


def _serialize_assistant_plan(plan: LegacyIssueAssistantSearchPlan) -> LegacyIssueAssistantPlanItem:
    return LegacyIssueAssistantPlanItem(
        query=plan.query,
        dataset_keys=list(plan.dataset_keys),
        primary_keywords=list(plan.primary_keywords),
        keywords=list(plan.keywords),
        supporting_keywords=list(plan.supporting_keywords),
        field_hints=list(plan.field_hints),
        intent=plan.intent,
        report_focus=list(plan.report_focus),
        related_field_expansions=list(plan.related_field_expansions),
    )


def _serialize_assistant_evidence(item: LegacyIssueEvidence) -> LegacyIssueAssistantEvidenceItem:
    return LegacyIssueAssistantEvidenceItem(
        evidence_id=item.evidence_id,
        dataset_key=item.dataset_key,
        dataset_title=item.dataset_title,
        revision_id=item.revision_id,
        revision_no=item.revision_no,
        record_id=item.record_id,
        stable_record_id=item.stable_record_id,
        label=item.label,
        values=item.values,
        matched_fields=list(item.matched_fields),
        matched_chunks=[_serialize_assistant_matched_chunk(chunk) for chunk in item.matched_chunks],
        attachments=[
            LegacyIssueAssistantEvidenceAttachmentItem(
                id=attachment.id,
                filename=attachment.filename,
                description=attachment.description,
                content_type=attachment.content_type,
                size_bytes=attachment.size_bytes,
                index_status=attachment.index_status,
                indexed_at=attachment.indexed_at,
                matched_chunks=[
                    _serialize_assistant_matched_chunk(chunk) for chunk in attachment.matched_chunks
                ],
                score=attachment.score,
                methods=list(attachment.methods),
            )
            for attachment in item.attachments
        ],
        score=item.score,
        methods=list(item.methods),
    )


def _serialize_assistant_matched_chunk(
    chunk: LegacyIssueMatchedChunk,
) -> LegacyIssueAssistantMatchedChunkItem:
    return LegacyIssueAssistantMatchedChunkItem(
        chunk_id=chunk.chunk_id,
        chunk_key=chunk.chunk_key,
        chunk_kind=chunk.chunk_kind,
        field_key=chunk.field_key,
        field_label=chunk.field_label,
        field_value=chunk.field_value,
        attachment_id=chunk.attachment_id,
        attachment_filename=chunk.attachment_filename,
        attachment_page=chunk.attachment_page,
        attachment_artifact_type=chunk.attachment_artifact_type,
        excerpt=chunk.excerpt,
        methods=list(chunk.methods),
        score=chunk.score,
    )


def _serialize_assistant_search_profile(
    profile: LegacyIssueSearchProfile,
) -> LegacyIssueAssistantSearchProfileItem:
    return LegacyIssueAssistantSearchProfileItem(
        semantic_enabled=profile.semantic_enabled,
        vector_extension_available=profile.vector_extension_available,
        vector_index_available=profile.vector_index_available,
        trigram_extension_available=profile.trigram_extension_available,
        full_text_enabled=profile.full_text_enabled,
        searched_dataset_keys=list(profile.searched_dataset_keys),
        searched_revision_ids=list(profile.searched_revision_ids),
        candidate_count=profile.candidate_count,
        evidence_count=profile.evidence_count,
        methods=list(profile.methods),
    )


def _hydrate_assistant_evidence_ref(
    db: Session,
    *,
    workspace: Workspace,
    ref: LegacyIssueAssistantEvidenceRefItem,
    partition_ids: tuple[str, ...] | None = None,
) -> LegacyIssueAssistantEvidenceItem | None:
    definition = DATASET_DEFINITIONS.get(ref.dataset_key)
    if definition is None:
        return None
    effective_partition_ids = (
        _legacy_issue_evidence_partition_ids(db, workspace=workspace)
        if partition_ids is None
        else partition_ids
    )
    target_revision = _assistant_evidence_target_revision(
        db,
        workspace=workspace,
        definition=definition,
        ref=ref,
        partition_ids=effective_partition_ids,
    )
    if target_revision is None:
        return None
    record_id = ref.source_record_id or ref.record_id
    row = db.scalar(
        select(LegacyIssueRecord).where(
            LegacyIssueRecord.workspace_id == workspace.id,
            LegacyIssueRecord.dataset_key == definition.key,
            LegacyIssueRecord.id == record_id,
            LegacyIssueRecord.revision_id == target_revision.id,
            or_(
                LegacyIssueRecord.retrieval_partition_id.is_(None),
                LegacyIssueRecord.retrieval_partition_id.in_(effective_partition_ids),
            ),
        )
    )
    if row is None and ref.stable_record_id:
        row = db.scalar(
            select(LegacyIssueRecord).where(
                LegacyIssueRecord.workspace_id == workspace.id,
                LegacyIssueRecord.dataset_key == definition.key,
                LegacyIssueRecord.stable_record_id == ref.stable_record_id,
                LegacyIssueRecord.revision_id == target_revision.id,
                or_(
                    LegacyIssueRecord.retrieval_partition_id.is_(None),
                    LegacyIssueRecord.retrieval_partition_id.in_(effective_partition_ids),
                ),
            )
        )
    if row is None:
        return None
    if row.module_key not in _enabled_module_keys():
        return None
    if target_revision.dataset_key != legacy_issue_dataset_revision_key(
        definition.key,
        row.module_key,
    ):
        return None
    values = _record_values(row)
    return LegacyIssueAssistantEvidenceItem(
        evidence_id=ref.id,
        dataset_key=definition.key,
        dataset_title=definition.title_ko,
        revision_id=row.revision_id,
        revision_no=target_revision.revision_no,
        record_id=row.id,
        stable_record_id=row.stable_record_id,
        label=_evidence_label(values, row=row, fallback=ref.label),
        values=values,
        matched_fields=list(ref.matched_fields),
        matched_chunks=list(ref.matched_chunks),
        attachments=[],
        score=ref.score,
        methods=list(ref.methods),
    )


def _assistant_evidence_target_revision(
    db: Session,
    *,
    workspace: Workspace,
    definition: LegacyIssueDatasetDefinition,
    ref: LegacyIssueAssistantEvidenceRefItem,
    partition_ids: tuple[str, ...],
) -> LegacyIssueDataRevision | None:
    if not ref.revision_id:
        return None
    revision = db.scalar(
        select(LegacyIssueDataRevision).where(
            LegacyIssueDataRevision.id == ref.revision_id,
            LegacyIssueDataRevision.workspace_id == workspace.id,
            LegacyIssueDataRevision.dataset_key.like(
                f"{legacy_issue_dataset_revision_key(definition.key)}.%"
            ),
            or_(
                LegacyIssueDataRevision.retrieval_partition_id.is_(None),
                LegacyIssueDataRevision.retrieval_partition_id.in_(partition_ids),
            ),
        )
    )
    # Hydration replays saved evidence; it is not a discovery/search path.
    # Historical published refs remain stable, while drafts must still be active.
    if revision is None or revision.status == REVISION_STATUS_PUBLISHED:
        return revision
    if revision.status != REVISION_STATUS_DRAFT:
        return None
    active_draft = get_active_draft_revision(
        db,
        workspace=workspace,
        dataset_key=revision.dataset_key,
    )
    return revision if active_draft is not None and active_draft.id == revision.id else None


def _legacy_issue_evidence_partition_ids(
    db: Session,
    *,
    workspace: Workspace,
) -> tuple[str, ...]:
    return tuple(
        str(partition_id)
        for partition_id in resolve_read_scope(
            db,
            source_namespaces=["legacy_issues"],
            workspace_id=workspace.id,
            user_id=None,
        ).for_source("legacy_issues")
    )


def _record_values(row: LegacyIssueRecord) -> dict[str, str]:
    values = canonicalize_dataset_values(row.field_values)
    return {
        str(key): display_dataset_value(value) or ""
        for key, value in values.items()
        if str(key).strip()
    }


def _evidence_label(
    values: dict[str, str],
    *,
    row: LegacyIssueRecord,
    fallback: str | None,
) -> str:
    return (
        fallback
        or values.get("legacy_issue_number")
        or values.get("row_no")
        or row.stable_record_id
        or row.id
    )


def _user_display_name(user: User | None) -> str | None:
    if user is None:
        return None
    return user.display_name or user.full_name or user.email


def _compact_preview(value: str, limit: int = 220) -> str:
    compacted = " ".join(value.split())
    if len(compacted) <= limit:
        return compacted
    return compacted[: max(limit - 3, 0)].rstrip() + "..."


def _serialize_dataset_definition(
    definition: LegacyIssueDatasetDefinition,
) -> LegacyIssueDatasetItem:
    return LegacyIssueDatasetItem(
        key=definition.key,
        title_ko=definition.title_ko,
        title_en=definition.title_en,
        hierarchy_ko=list(definition.hierarchy_ko),
        hierarchy_en=list(definition.hierarchy_en),
        header_rows=definition.header_rows,
        fields=[
            LegacyIssueDatasetFieldItem(
                key=field.key,
                label_ko=field.label_ko,
                label_en=field.label_en,
                group_key=field.group_key,
                field_type=field.field_type,
                options=list(field.options),
                allow_multiple=field.allow_multiple,
                required=field.required,
                source=field.source,
                module_key=field.module_key,
                field_id=field.field_id,
                active=field.active,
                readonly=field.readonly,
            )
            for field in definition.fields
        ],
        group_labels_ko=definition.group_labels_ko,
        group_labels_en=definition.group_labels_en,
    )


def _available_column_keys_for_view(
    db: Session,
    *,
    workspace: Workspace,
    view_key: str,
) -> list[str]:
    definition = get_dataset_definition_for_view(
        db,
        dataset_key="common-master",
        workspace=workspace,
        view_key=view_key,
    )
    return [field.key for field in definition.fields] + [COLUMN_ORDER_ATTACHMENT_KEY]


def _serialize_column_order(item) -> LegacyIssueColumnOrderItem:
    return LegacyIssueColumnOrderItem(
        view_key=item.view_key,
        column_order=item.column_order,
        hidden_column_keys=item.hidden_column_keys,
        updated_at=item.updated_at,
    )


def _serialize_grid_preference(
    item: LegacyIssueGridPreferenceDTO,
) -> LegacyIssueGridPreferenceItem:
    return LegacyIssueGridPreferenceItem(
        grid_kind=item.grid_kind,
        grid_key=item.grid_key,
        column_order=item.column_order,
        hidden_column_keys=item.hidden_column_keys,
        frozen_column_count=item.frozen_column_count,
        revision=item.revision,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _serialize_vehicle_model(
    row,
    *,
    checklist_summary=None,
    generated_checklist_count: int = 0,
    stages=None,
) -> LegacyIssueVehicleModelItem:
    return LegacyIssueVehicleModelItem(
        id=row.id,
        vehicle_code=row.vehicle_code,
        vehicle_name=row.vehicle_name,
        notes=row.notes,
        active=row.active,
        stages=[_serialize_vehicle_stage(item) for item in (stages or ())],
        generated_checklist_count=generated_checklist_count,
        checklist_summary=_serialize_vehicle_checklist_summary(checklist_summary),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _serialize_vehicle_stage(row) -> LegacyIssueVehicleStageItem:
    return LegacyIssueVehicleStageItem(
        id=row.id,
        vehicle_model_id=row.vehicle_model_id,
        name=row.name,
        sequence_no=row.sequence_no,
        previous_stage_id=row.previous_stage_id,
        created_by_id=row.created_by_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _serialize_excel_export_job(
    job: LegacyIssueExcelExportJob,
) -> LegacyIssueExcelExportJobItem:
    return LegacyIssueExcelExportJobItem(
        id=job.id,
        status=excel_export_job_status(job),
        source_kind=job.source_kind,
        include_attachments=excel_export_includes_attachments(job),
        record_count=job.record_count,
        attachment_count=job.attachment_count,
        attachment_bytes=job.attachment_bytes,
        processed_attachment_count=job.processed_attachment_count,
        processed_attachment_bytes=job.processed_attachment_bytes,
        result_filename=job.result_filename,
        result_size_bytes=job.result_size_bytes,
        error_code=job.error_code,
        created_at=job.created_at,
        updated_at=job.updated_at,
        completed_at=job.completed_at,
        expires_at=job.expires_at,
    )


def _serialize_vehicle_checklist_summary(summary) -> LegacyIssueVehicleChecklistSummary | None:
    if summary is None:
        return None
    return LegacyIssueVehicleChecklistSummary(
        latest_draft=_serialize_vehicle_checklist_summary_entry(summary.latest_draft),
        latest_completed=_serialize_vehicle_checklist_summary_entry(summary.latest_completed),
    )


def _serialize_vehicle_checklist_summary_entry(
    entry,
) -> LegacyIssueVehicleChecklistSummaryItem | None:
    if entry is None:
        return None
    return LegacyIssueVehicleChecklistSummaryItem(
        revision_id=entry.revision_id,
        source_master_revision_no=entry.source_master_revision_no,
        updated_at=entry.updated_at,
    )


def _serialize_vehicle_checklist_revision(
    row,
) -> LegacyIssueVehicleChecklistRevisionItem:
    return LegacyIssueVehicleChecklistRevisionItem(
        id=row.id,
        vehicle_model_id=row.vehicle_model_id,
        revision_no=row.revision_no,
        status=row.status,
        source_dataset_key=row.source_dataset_key,
        source_master_revision_id=row.source_master_revision_id,
        source_master_revision_no=row.source_master_revision_no,
        row_count=row.row_count,
        created_by_id=row.created_by_id,
        completed_by_id=row.completed_by_id,
        completed_at=row.completed_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _serialize_vehicle_checklist_record(
    row,
) -> LegacyIssueVehicleChecklistRecordItem:
    return LegacyIssueVehicleChecklistRecordItem(
        id=row.id,
        checklist_revision_id=row.checklist_revision_id,
        source_record_id=row.source_record_id,
        source_stable_record_id=row.source_stable_record_id,
        source_module_key=row.source_module_key,
        values=canonicalize_dataset_values(row.field_values),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _serialize_vehicle_checklist_history_item(
    row,
    *,
    context,
) -> LegacyIssueVehicleChecklistHistoryItem:
    actor = row.actor
    return LegacyIssueVehicleChecklistHistoryItem(
        id=row.id,
        action=row.action,
        record_id=row.record_id,
        record_label=context.record_label if context else None,
        source_module_key=context.source_module_key if context else None,
        source_master_revision_no=context.source_master_revision_no if context else None,
        field_key=row.field_key,
        field_label=row.field_label,
        old_value=row.old_value,
        new_value=row.new_value,
        actor_user_id=row.actor_user_id,
        actor_name=(actor.display_name or actor.full_name if actor is not None else None),
        actor_email=actor.email if actor is not None else None,
        details=row.details,
        created_at=row.created_at,
    )


def _serialize_vehicle_checklist_master_revision(
    row,
) -> LegacyIssueVehicleChecklistMasterRevisionItem:
    return LegacyIssueVehicleChecklistMasterRevisionItem(
        id=row.id,
        revision_no=row.revision_no,
    )


def _serialize_vehicle_module_checklist(
    row,
) -> LegacyIssueVehicleModuleChecklistItem:
    return LegacyIssueVehicleModuleChecklistItem(
        id=row.id,
        vehicle_model_id=row.vehicle_model_id,
        stage_id=row.vehicle_stage_id,
        module_key=row.module_key,
        status=row.status,
        source_dataset_key=row.source_dataset_key,
        source_master_revision_id=row.source_master_revision_id,
        source_master_revision_no=row.source_master_revision_no,
        row_count=row.row_count,
        created_by_id=row.created_by_id,
        completed_by_id=row.completed_by_id,
        completed_at=row.completed_at,
        seeded_from_checklist_id=row.seeded_from_checklist_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _serialize_vehicle_module_summary(row) -> LegacyIssueVehicleModuleSummaryItem:
    return LegacyIssueVehicleModuleSummaryItem(
        module_key=row.module_key,
        latest_master_revision=(
            _serialize_vehicle_checklist_master_revision(row.latest_master_revision)
            if row.latest_master_revision is not None
            else None
        ),
        latest_checklist=(
            _serialize_vehicle_module_checklist(row.latest_checklist)
            if row.latest_checklist is not None
            else None
        ),
        checklist_count=row.checklist_count,
    )


def _serialize_vehicle_module_checklist_record(
    row,
    *,
    attachments: list[LegacyIssueVehicleModuleChecklistAttachment],
) -> LegacyIssueVehicleModuleChecklistRecordItem:
    return LegacyIssueVehicleModuleChecklistRecordItem(
        id=row.id,
        checklist_id=row.checklist_id,
        source_record_id=row.source_record_id,
        source_stable_record_id=row.source_stable_record_id,
        values=canonicalize_dataset_values(row.field_values),
        attachments=[_serialize_vehicle_module_checklist_attachment(item) for item in attachments],
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _serialize_vehicle_module_checklist_attachment(
    row: LegacyIssueVehicleModuleChecklistAttachment,
) -> LegacyIssueVehicleModuleChecklistAttachmentItem:
    return LegacyIssueVehicleModuleChecklistAttachmentItem(
        id=row.id,
        checklist_id=row.checklist_id,
        record_id=row.record_id,
        filename=row.filename,
        content_type=row.content_type,
        size_bytes=row.size_bytes,
        uploaded_by_id=row.uploaded_by_id,
        created_at=row.created_at,
    )


def _serialize_system_field_setting(
    item: DatasetSystemFieldSettingView,
) -> LegacyIssueSystemFieldItem:
    field = item.field
    return LegacyIssueSystemFieldItem(
        id=item.id,
        dataset_key=item.dataset_key,
        key=field.key,
        label_ko=field.label_ko,
        label_en=field.label_en,
        group_key=field.group_key,
        field_type=field.field_type,
        options=list(field.options),
        allow_multiple=field.allow_multiple,
        required=field.required,
        source=field.source,
        module_key=field.module_key,
        field_id=field.field_id,
        active=field.active,
        readonly=field.settings_readonly,
        updated_at=item.updated_at,
    )


def _serialize_module_field(field: LegacyIssueModuleFieldDTO) -> LegacyIssueModuleFieldItem:
    return LegacyIssueModuleFieldItem(
        id=field.id,
        module_key=field.module_key,
        field_key=field.field_key,
        label_ko=field.label_ko,
        label_en=field.label_en,
        field_type=field.field_type,
        options=field.options,
        allow_multiple=field.allow_multiple,
        required=field.required,
        sort_order=field.sort_order,
        active=field.active,
        created_at=field.created_at,
        updated_at=field.updated_at,
    )


def _refresh_module_field_record_projections(
    db: Session,
    *,
    workspace: Workspace,
) -> None:
    definition = get_dataset_definition_with_all_module_fields(
        db,
        dataset_key="common-master",
        workspace=workspace,
    )
    refresh_dataset_record_projections(db, definition, workspace=workspace)


def _serialize_import_preview(preview) -> LegacyIssueImportPreviewResponse:
    return LegacyIssueImportPreviewResponse(
        columns=[
            LegacyIssueImportPreviewColumnItem(
                index=column.index,
                header=column.header,
                sample_values=column.sample_values,
            )
            for column in preview.columns
        ],
        preview_rows=preview.preview_rows,
        suggested_mapping=preview.suggested_mapping,
        total_preview_rows=preview.total_preview_rows,
    )


def _serialize_attachment(row: LegacyIssueAttachment) -> LegacyIssueAttachmentItem:
    return LegacyIssueAttachmentItem(
        id=row.id,
        record_id=row.record_id,
        filename=row.filename,
        content_type=row.content_type,
        size_bytes=row.size_bytes,
        description=row.description,
        is_primary=row.is_primary,
        index_status=row.index_status,
        index_error=row.index_error,
        indexed_at=row.indexed_at,
        index_version=row.index_version,
        chunk_count=row.chunk_count,
        artifact_count=row.artifact_count,
        ai_summary=row.ai_summary,
        ai_summary_status=row.ai_summary_status,
        ai_summary_error=row.ai_summary_error,
        ai_summary_model=row.ai_summary_model,
        ai_summary_version=row.ai_summary_version,
        ai_summarized_at=row.ai_summarized_at,
        created_at=row.created_at,
    )


def _serialize_record(
    row: LegacyIssueRecord,
    *,
    attachments: list[LegacyIssueAttachment],
) -> LegacyIssueRecordItem:
    attachment_items = [_serialize_attachment(item) for item in attachments]
    primary_attachment = next((item for item in attachment_items if item.is_primary), None)
    return LegacyIssueRecordItem(
        id=row.id,
        revision_id=row.revision_id,
        stable_record_id=row.stable_record_id,
        module_key=row.module_key,
        values=canonicalize_dataset_values(row.field_values),
        raw_fields=row.raw_fields or {},
        imported_source_filename=row.imported_source_filename,
        imported_at=row.imported_at,
        attachments=attachment_items,
        primary_attachment=primary_attachment,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _history_scope(
    db: Session,
    *,
    definition: LegacyIssueDatasetDefinition,
    workspace: Workspace,
    record: LegacyIssueRecord,
) -> tuple[set[str], dict[str, str]]:
    stable_record_id = record.stable_record_id or record.id
    rows = list(
        db.scalars(
            select(LegacyIssueRecord).where(
                LegacyIssueRecord.workspace_id == workspace.id,
                LegacyIssueRecord.dataset_key == definition.key,
                LegacyIssueRecord.stable_record_id == stable_record_id,
            )
        )
    )
    if not rows:
        rows = [record]
    history_record_ids = {stable_record_id, *(row.id for row in rows)}
    record_revision_ids = {row.id: row.revision_id for row in rows if row.revision_id}
    return history_record_ids, {key: value for key, value in record_revision_ids.items() if value}


def _history_existing_revision_fields(
    history_rows: list[LegacyIssueRecordHistory],
    *,
    record_revision_ids: dict[str, str],
) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for row in history_rows:
        revision_id = _history_revision_id(row, record_revision_ids)
        if revision_id and row.field_key:
            keys.add((revision_id, row.field_key))
    return keys


def _revision_diff_history_items(
    db: Session,
    *,
    definition: LegacyIssueDatasetDefinition,
    workspace: Workspace,
    record: LegacyIssueRecord,
    existing_history_keys: set[tuple[str, str]],
) -> list[LegacyIssueRecordHistoryItem]:
    stable_record_id = record.stable_record_id or record.id
    rows = list(
        db.scalars(
            select(LegacyIssueRecord).where(
                LegacyIssueRecord.workspace_id == workspace.id,
                LegacyIssueRecord.dataset_key == definition.key,
                LegacyIssueRecord.stable_record_id == stable_record_id,
            )
        )
    )
    rows_by_revision_id = {row.revision_id: row for row in rows if row.revision_id}
    revisions = _record_revisions(db, workspace=workspace, revision_ids=set(rows_by_revision_id))
    ordered_revisions = _ordered_record_revisions(revisions)
    labels = field_labels(definition)
    field_keys = tuple(field.key for field in definition.fields)
    items: list[LegacyIssueRecordHistoryItem] = []
    previous_revision: LegacyIssueDataRevision | None = None
    previous_row: LegacyIssueRecord | None = None
    for revision in ordered_revisions:
        row = rows_by_revision_id.get(revision.id)
        if row is None:
            continue
        if previous_revision is not None and previous_row is not None:
            old_field_values = canonicalize_dataset_values(previous_row.field_values)
            new_field_values = canonicalize_dataset_values(row.field_values)
            old_values = {key: old_field_values.get(key) for key in field_keys}
            new_values = {key: new_field_values.get(key) for key in field_keys}
            items.extend(
                _revision_diff_items_from_changes(
                    revision=revision,
                    stable_record_id=stable_record_id,
                    action=_revision_diff_action(revision, previous_revision),
                    changes=collect_value_changes(
                        old_values=old_values,
                        new_values=new_values,
                        field_labels=labels,
                    ),
                    existing_history_keys=existing_history_keys,
                )
            )
        previous_revision = revision
        previous_row = row
    return items


def _record_revisions(
    db: Session,
    *,
    workspace: Workspace,
    revision_ids: set[str],
) -> dict[str, LegacyIssueDataRevision]:
    if not revision_ids:
        return {}
    return {
        revision.id: revision
        for revision in db.scalars(
            select(LegacyIssueDataRevision).where(
                LegacyIssueDataRevision.workspace_id == workspace.id,
                LegacyIssueDataRevision.id.in_(revision_ids),
                LegacyIssueDataRevision.status.in_(("published", "draft")),
            )
        )
    }


def _ordered_record_revisions(
    revisions: dict[str, LegacyIssueDataRevision],
) -> list[LegacyIssueDataRevision]:
    return sorted(
        revisions.values(),
        key=lambda revision: (
            revision.published_at or revision.created_at,
            revision.revision_no or 0,
            revision.id,
        ),
    )


def _revision_diff_action(
    revision: LegacyIssueDataRevision,
    previous_revision: LegacyIssueDataRevision,
) -> str:
    if revision.base_revision_id and revision.base_revision_id != previous_revision.id:
        return "restore"
    return "update"


def _revision_diff_items_from_changes(
    *,
    revision: LegacyIssueDataRevision,
    stable_record_id: str,
    action: str,
    changes: list,
    existing_history_keys: set[tuple[str, str]],
) -> list[LegacyIssueRecordHistoryItem]:
    actor = revision.published_by or revision.created_by or revision.locked_by
    actor_user_id = revision.published_by_id or revision.created_by_id or revision.locked_by_id
    created_at = revision.published_at or revision.updated_at or revision.created_at
    items: list[LegacyIssueRecordHistoryItem] = []
    for change in changes:
        if (revision.id, change.field_key) in existing_history_keys:
            continue
        items.append(
            LegacyIssueRecordHistoryItem(
                id=f"revision-diff:{revision.id}:{stable_record_id}:{change.field_key}",
                action=action,
                revision_id=revision.id,
                revision_no=revision.revision_no,
                revision_status=revision.status,
                field_key=change.field_key,
                field_label=change.field_label,
                old_value=change.old_value,
                new_value=change.new_value,
                actor_user_id=actor_user_id,
                actor_name=_actor_name(actor),
                actor_email=actor.email if actor else None,
                details={"revision_id": revision.id, "synthetic": True},
                created_at=created_at,
            )
        )
    return items


def _sort_history_items(
    items: list[LegacyIssueRecordHistoryItem],
) -> list[LegacyIssueRecordHistoryItem]:
    return sorted(items, key=lambda item: item.created_at, reverse=True)


def _history_revisions(
    db: Session,
    *,
    history_rows: list[LegacyIssueRecordHistory],
    record_revision_ids: dict[str, str],
) -> dict[str, LegacyIssueDataRevision]:
    revision_ids = set(record_revision_ids.values())
    for row in history_rows:
        revision_id = _history_revision_id(row, record_revision_ids)
        if revision_id:
            revision_ids.add(revision_id)
    if not revision_ids:
        return {}
    return {
        revision.id: revision
        for revision in db.scalars(
            select(LegacyIssueDataRevision).where(LegacyIssueDataRevision.id.in_(revision_ids))
        )
    }


def _history_revision_id(
    row: LegacyIssueRecordHistory, record_revision_ids: dict[str, str]
) -> str | None:
    detail_revision_id = _history_detail_revision_id(row)
    if isinstance(detail_revision_id, str) and detail_revision_id:
        return detail_revision_id
    return record_revision_ids.get(row.record_id)


def _history_detail_revision_id(row: LegacyIssueRecordHistory) -> str | None:
    detail_revision_id = row.details.get("revision_id") if isinstance(row.details, dict) else None
    return (
        detail_revision_id if isinstance(detail_revision_id, str) and detail_revision_id else None
    )


def _serialize_record_history(
    row: LegacyIssueRecordHistory,
    *,
    revisions: dict[str, LegacyIssueDataRevision],
    record_revision_ids: dict[str, str],
) -> LegacyIssueRecordHistoryItem:
    actor = row.actor
    revision_id = _history_revision_id(row, record_revision_ids)
    revision = revisions.get(revision_id or "")
    if revision and not _history_detail_revision_id(row) and row.created_at < revision.created_at:
        revision_id = None
        revision = None
    return LegacyIssueRecordHistoryItem(
        id=row.id,
        action=row.action,
        revision_id=revision_id,
        revision_no=revision.revision_no if revision else None,
        revision_status=revision.status if revision else None,
        field_key=row.field_key,
        field_label=row.field_label,
        old_value=row.old_value,
        new_value=row.new_value,
        actor_user_id=row.actor_user_id,
        actor_name=(actor.display_name or actor.full_name) if actor else None,
        actor_email=actor.email if actor else None,
        details=row.details,
        created_at=row.created_at,
    )


def _actor_name(user: Any | None) -> str | None:
    if user is None:
        return None
    return user.display_name or user.full_name or user.email


LEGACY_ISSUE_VIEW_PATH_SUFFIXES = {
    "common-master": "/common-master",
    "aircon": "/aircon",
    "heat-exchanger": "/heat-exchanger",
    "compressor-electric": "/compressor/electric",
    "compressor-mechanical": "/compressor/mechanical",
    "interior": "/interior",
    "cooling-module": "/cooling-module",
    "electrical-mechanical": "/electrical/mechanical",
    "electrical-control-hw": "/electrical/control/hw",
    "electrical-control-sw": "/electrical/control/sw",
}


def _create_revision_approval_notifications(
    db: Session,
    *,
    workspace: Workspace,
    revision: LegacyIssueDataRevision,
    requester: User,
    recipients: list[tuple[str, User]],
    view_key: str | None,
    events: DmEventPublisher | None,
) -> None:
    action_url = _legacy_issue_revision_action_url(
        workspace=workspace,
        revision=revision,
        view_key=view_key,
    )
    for role, recipient in recipients:
        title, body = _revision_approval_notification_copy(
            recipient=recipient,
            requester=requester,
            revision=revision,
            role=role,
        )
        notification = Notification(
            id=new_id(),
            user_id=recipient.id,
            type="legacy_issue_revision_review_request",
            title=title,
            body=body,
            reference_type="legacy_issue_revision",
            reference_id=revision.id,
            action_url=action_url,
        )
        db.add(notification)
        db.flush()
        dm_delivery_result = _send_revision_approval_request_dm(
            db,
            requester=requester,
            recipient=recipient,
            body=f"{title}\n{body}\n{action_url}",
        )
        if events is not None and dm_delivery_result is not None:
            conversation, message = dm_delivery_result
            events.publish_conversation_snapshot(
                conversation,
                dm_realtime_event_types.DM_MESSAGE_CREATED,
                message=message,
            )
        if events is not None:
            events.publish_notification(
                recipient.id,
                event_type=notification_realtime_event_types.NOTIFICATION_CREATED,
                notification=notification_service.serialize_notification(notification).model_dump(
                    mode="json"
                ),
                unread_count=notification_service.unread_count(db, recipient.id),
            )


def _send_revision_approval_request_dm(
    db: Session,
    *,
    requester: User,
    recipient: User,
    body: str,
) -> tuple[DmConversation, DmMessage] | None:
    if requester.id == recipient.id:
        return None
    now = utcnow_naive()
    conversation = _get_or_create_direct_conversation_without_commit(
        db,
        requester=requester,
        recipient=recipient,
        now=now,
    )
    draft = message_flow.compose_dm_message(
        db,
        conversation=conversation,
        sender=requester,
        body=body,
        attachment_ids=[],
        reply_to_message_id=None,
        now=now,
    )
    sent = message_delivery.persist_message_draft(db, draft=draft, commit=False)
    published_conversation = (
        conversation_queries.conversation_for_publish(db, conversation.id) or conversation
    )
    return published_conversation, sent.message


def _get_or_create_direct_conversation_without_commit(
    db: Session,
    *,
    requester: User,
    recipient: User,
    now: Any,
) -> DmConversation:
    direct_key = conversation_lifecycle.direct_conversation_key(
        requester.id,
        recipient.id,
    )
    conversation = db.scalar(select(DmConversation).where(DmConversation.direct_key == direct_key))
    if conversation is None:
        draft = conversation_lifecycle.new_direct_conversation(
            current_user=requester,
            recipient=recipient,
            now=now,
        )
        draft.conversation.participants = draft.participants
        db.add(draft.conversation)
        db.add_all(draft.participants)
        db.flush()
        conversation = draft.conversation
    latest_message = conversation_queries.latest_message(db, conversation.id)
    restored = [
        participant
        for participant in (
            conversation_lifecycle.restore_direct_participant_if_needed(
                conversation,
                user_id,
                joined_at=now,
                last_read_message_id=(latest_message.id if latest_message is not None else None),
            )
            for user_id in (requester.id, recipient.id)
        )
        if participant is not None
    ]
    if restored:
        db.add_all(restored)
        db.flush()
    return conversation_queries.conversation_for_publish(db, conversation.id) or conversation


def _legacy_issue_revision_action_url(
    *,
    workspace: Workspace,
    revision: LegacyIssueDataRevision,
    view_key: str | None,
) -> str:
    suffix = LEGACY_ISSUE_VIEW_PATH_SUFFIXES.get(view_key or "", "/common-master")
    params = f"tab=overview&revision_id={revision.id}"
    return f"/w/{workspace.key}/legacy-issues{suffix}?{params}"


def _revision_approval_notification_copy(
    *,
    recipient: User,
    requester: User,
    revision: LegacyIssueDataRevision,
    role: str,
) -> tuple[str, str]:
    requester_name = _actor_name(requester) or requester.email
    revision_label = f"Rev. {revision.revision_no}" if revision.revision_no is not None else "초안"
    if recipient.locale == "en-US":
        role_label = "review" if role == "review" else "approval"
        return (
            "Legacy issue revision request",
            f"{requester_name} requested your {role_label} for {revision_label}.",
        )
    role_label = "검토" if role == "review" else "승인"
    return (
        "과거차 문제점 리비전 요청",
        f"{requester_name}님이 {revision_label} {role_label}를 요청했습니다.",
    )


def _serialize_revision(row: LegacyIssueDataRevision) -> LegacyIssueRevisionItem:
    return LegacyIssueRevisionItem(
        id=row.id,
        dataset_key=row.dataset_key,
        revision_no=row.revision_no,
        status=row.status,
        base_revision_id=row.base_revision_id,
        note=row.note,
        locked_by_id=row.locked_by_id,
        locked_by_name=_actor_name(row.locked_by),
        created_by_id=row.created_by_id,
        created_by_name=_actor_name(row.created_by),
        published_by_id=row.published_by_id,
        published_by_name=_actor_name(row.published_by),
        canceled_by_id=row.canceled_by_id,
        canceled_by_name=_actor_name(row.canceled_by),
        reviewer_id=row.reviewer_id,
        reviewer_name=_actor_name(row.reviewer),
        reviewer_email=row.reviewer.email if row.reviewer else None,
        approver_id=row.approver_id,
        approver_name=_actor_name(row.approver),
        approver_email=row.approver.email if row.approver else None,
        review_requested_by_id=row.review_requested_by_id,
        review_requested_by_name=_actor_name(row.review_requested_by),
        approval_requested_by_id=row.approval_requested_by_id,
        approval_requested_by_name=_actor_name(row.approval_requested_by),
        reviewed_by_id=row.reviewed_by_id,
        reviewed_by_name=_actor_name(row.reviewed_by),
        approved_by_id=row.approved_by_id,
        approved_by_name=_actor_name(row.approved_by),
        created_at=row.created_at,
        updated_at=row.updated_at,
        published_at=row.published_at,
        canceled_at=row.canceled_at,
        review_requested_at=row.review_requested_at,
        approval_requested_at=row.approval_requested_at,
        reviewed_at=row.reviewed_at,
        approved_at=row.approved_at,
    )


def _serialize_revision_overview_history(
    row: LegacyIssueRevisionOverviewHistory,
) -> LegacyIssueRevisionOverviewHistoryItem:
    deleted = row.deleted_at is not None
    return LegacyIssueRevisionOverviewHistoryItem(
        id=row.id,
        dataset_key=row.dataset_key,
        linked_revision_id=row.linked_revision_id,
        origin=row.origin,
        revision_no=None if deleted else row.revision_no,
        revision_label=None if deleted else row.revision_label,
        summary=None if deleted else row.summary,
        revised_on=None if deleted else row.revised_on,
        vehicle_models=None if deleted else row.vehicle_models,
        author_user_id=None if deleted else row.author_user_id,
        reviewer_user_id=None if deleted else row.reviewer_user_id,
        approver_user_id=None if deleted else row.approver_user_id,
        author_name=None if deleted else row.author_name,
        reviewer_name=None if deleted else row.reviewer_name,
        approver_name=None if deleted else row.approver_name,
        source_filename=None if deleted else row.source_filename,
        source_sha256=None if deleted else row.source_sha256,
        source_sheet=None if deleted else row.source_sheet,
        source_row=None if deleted else row.source_row,
        sort_order=row.sort_order,
        deleted_at=row.deleted_at,
        deleted_by_id=None,
    )


def _serialize_revision_meeting_attachment(
    row: LegacyIssueRevisionMeetingAttachment,
    *,
    user: User,
    can_delete: bool,
) -> LegacyIssueRevisionMeetingAttachmentItem:
    return LegacyIssueRevisionMeetingAttachmentItem(
        id=row.id,
        overview_history_id=row.overview_history_id,
        filename=row.filename,
        content_type=row.content_type,
        size_bytes=row.size_bytes,
        description=row.description,
        uploaded_by_id=row.uploaded_by_id,
        uploaded_by_name=_actor_name(row.uploaded_by),
        created_at=row.created_at,
        updated_at=row.updated_at,
        can_edit_description=can_delete or row.uploaded_by_id == user.id,
        can_delete=can_delete,
    )


def _serialize_revision_context(
    context,
    *,
    can_direct_edit_published_revision: bool = False,
    can_force_cancel_active_draft: bool = False,
) -> LegacyIssueRevisionContextItem:
    return LegacyIssueRevisionContextItem(
        current=_serialize_revision(context.current),
        latest_published=_serialize_revision(context.latest_published)
        if context.latest_published
        else None,
        active_draft=_serialize_revision(context.active_draft) if context.active_draft else None,
        can_direct_edit_published_revision=can_direct_edit_published_revision,
        can_force_cancel_active_draft=can_force_cancel_active_draft,
    )


def _serialize_module_direct_editor(
    item: LegacyIssueModuleDirectEditorDTO,
) -> LegacyIssueModuleDirectEditorItem:
    return LegacyIssueModuleDirectEditorItem(
        id=item.id,
        module_key=item.module_key,
        user_id=item.user_id,
        display_name=item.display_name,
        email=item.email,
        role=item.role,
        can_revoke=item.can_revoke,
        active_member=item.active_member,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _serialize_revision_event(row: LegacyIssueDataRevisionEvent) -> LegacyIssueRevisionEventItem:
    actor = row.actor
    return LegacyIssueRevisionEventItem(
        id=row.id,
        revision_id=row.revision_id,
        dataset_key=row.dataset_key,
        action=row.action,
        actor_user_id=row.actor_user_id,
        actor_name=_actor_name(actor),
        actor_email=actor.email if actor else None,
        note=row.note,
        details=row.details,
        created_at=row.created_at,
    )
