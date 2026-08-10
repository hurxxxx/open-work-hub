import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import {
  ArrowLeft,
  CheckCircle2,
  CopyPlus,
  Download,
  Eye,
  FileText,
  History,
  Loader2,
  Maximize2,
  Minimize2,
  Paperclip,
  PencilLine,
  Plus,
  Save,
  Table2,
  Trash2,
  Upload,
  X,
} from 'lucide-react';
import { useConfirm, useToast } from '@open-alm/ui';

import { UserDateTime } from '@/src/components/date/UserDateTime';
import { FormDialog } from '@/src/components/form/FormDialog';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { downloadBlobAsFile } from '@/src/platform/browser/browser-download';
import { formatByteSize } from '@/src/platform/format/byte-size';
import { buildWorkspaceAppPath } from '@/src/platform/workspaces/workspace-utils';
import {
  completeLegacyIssueVehicleModuleChecklist,
  createLegacyIssueVehicleModuleChecklist,
  createLegacyIssueVehicleModuleChecklistExcelExport,
  deleteLegacyIssueVehicleModuleChecklistAttachment,
  deleteLegacyIssueVehicleModuleChecklist,
  fetchLegacyIssueVehicleModuleChecklistAttachmentBlob,
  fetchLegacyIssueExcelExportFile,
  fetchLegacyIssueExcelExportJob,
  fetchLegacyIssueVehicleModels,
  fetchLegacyIssueVehicleModuleChecklistHistory,
  fetchLegacyIssueVehicleModuleChecklistRecords,
  fetchLegacyIssueVehicleModuleChecklists,
  importPreviousStageLegacyIssueVehicleModuleChecklist,
  reopenLegacyIssueVehicleModuleChecklist,
  saveLegacyIssueVehicleModuleChecklistRecords,
  uploadLegacyIssueVehicleModuleChecklistAttachment,
  type LegacyIssueVehicleChecklistHistoryItem,
  type LegacyIssueVehicleChecklistMasterRevision,
  type LegacyIssueVehicleModel,
  type LegacyIssueVehicleModuleChecklist,
  type LegacyIssueVehicleModuleChecklistAttachment,
  type LegacyIssueVehicleModuleChecklistImportCandidate,
  type LegacyIssueVehicleModuleChecklistRecord,
} from '../api/legacy-issue-vehicle-api';
import {
  legacyIssueExcelExportErrorKey,
  useLegacyIssueExcelExportJob,
} from './useLegacyIssueExcelExportJob';
import { LegacyIssueExcelExportControls } from './LegacyIssueExcelExportControls';
import {
  fetchLegacyIssueColumnOrder,
  type LegacyIssueDatasetDefinition,
  type LegacyIssueDatasetField,
  type LegacyIssueFieldValue,
} from '../api/legacy-issue-dataset-api';
import {
  LegacyIssueDataGrid,
  type LegacyIssueGridColumn,
  type LegacyIssueGridColumnLayout,
  type LegacyIssueGridPreferenceStatus,
  type LegacyIssueGridPreferenceValue,
} from './LegacyIssueDataGrid';
import {
  LegacyIssueGridToolbarSearch,
  LegacyIssuePageHeader,
  LegacyIssueToolbarButton,
} from './LegacyIssuePageParts';
import {
  formatVehicleModelTitle,
  vehicleChecklistModuleLabel,
} from './CoreBusinessLegacyIssueVehicleChecklistView';
import { useLegacyIssueGridPreference } from './useLegacyIssueGridPreference';

const CHECK_FIELD_KEYS = [
  'check_plan',
  'applied',
  'reflection_result',
] as const;
const CHECK_FIELD_KEY_SET = new Set<string>(CHECK_FIELD_KEYS);
const CHECK_ATTACHMENT_COLUMN_KEY = 'check_attachments';

type VehicleChecklistCheckFieldKey = (typeof CHECK_FIELD_KEYS)[number];
type VehicleChecklistTab = 'sheet' | 'history';
type PendingChecklistEdits = Record<
  string,
  Record<string, LegacyIssueFieldValue | null>
>;
type ChecklistAttachmentMutation = {
  attachmentId: string | null;
  kind: 'delete' | 'upload';
  recordId: string;
};
type ModuleChecklistRouteScope = {
  moduleKey: string;
  stageId: string;
  vehicleModelId: string;
  workspaceSlug: string;
};

export function CoreBusinessLegacyIssueVehicleModuleChecklistView() {
  const {
    moduleKey = '',
    vehicleModelId = '',
    workspaceSlug = '',
  } = useParams<{
    moduleKey: string;
    vehicleModelId: string;
    workspaceSlug: string;
  }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const stageId = searchParams.get('stage_id') ?? '';
  const { token, user } = useAuth();
  const { t } = useTranslation(['apps', 'common', 'shell']);
  const toast = useToast();
  const { confirm, confirmDialog } = useConfirm();
  const userGridPreference = useLegacyIssueGridPreference({
    gridKey: moduleKey || null,
    gridKind: 'vehicle-module-checklist',
    onLoadError: () => {
      toast.error(t('coreBusiness.grid.preferenceLoadFailed'));
    },
    onSaveError: () => {
      toast.error(t('coreBusiness.grid.preferenceSaveFailed'));
    },
    token,
    workspaceSlug,
  });
  const [vehicles, setVehicles] = useState<LegacyIssueVehicleModel[]>([]);
  const [checklists, setChecklists] = useState<
    LegacyIssueVehicleModuleChecklist[]
  >([]);
  const [latestMasterRevision, setLatestMasterRevision] =
    useState<LegacyIssueVehicleChecklistMasterRevision | null>(null);
  const [masterRevisions, setMasterRevisions] = useState<
    LegacyIssueVehicleChecklistMasterRevision[]
  >([]);
  const [importCandidates, setImportCandidates] = useState<
    LegacyIssueVehicleModuleChecklistImportCandidate[]
  >([]);
  const [importDialogOpen, setImportDialogOpen] = useState(false);
  const [selectedImportChecklistId, setSelectedImportChecklistId] =
    useState('');
  const [sourceMasterRevisionId, setSourceMasterRevisionId] = useState('');
  const [definition, setDefinition] =
    useState<LegacyIssueDatasetDefinition | null>(null);
  const [defaultColumnOrder, setDefaultColumnOrder] = useState<string[]>([]);
  const [defaultHiddenColumnKeys, setDefaultHiddenColumnKeys] = useState<
    string[]
  >([]);
  const [gridDefaultsLoading, setGridDefaultsLoading] = useState(true);
  const [gridDefaultsLoadFailed, setGridDefaultsLoadFailed] = useState(false);
  const [records, setRecords] = useState<
    LegacyIssueVehicleModuleChecklistRecord[]
  >([]);
  const [historyItems, setHistoryItems] = useState<
    LegacyIssueVehicleChecklistHistoryItem[]
  >([]);
  const [total, setTotal] = useState(0);
  const [query, setQuery] = useState('');
  const [submittedQuery, setSubmittedQuery] = useState('');
  const [activeTab, setActiveTab] = useState<VehicleChecklistTab>('sheet');
  const [upperControlsCollapsed, setUpperControlsCollapsed] = useState(false);
  const [checkEditorRecordId, setCheckEditorRecordId] = useState<string | null>(
    null,
  );
  const [pendingEdits, setPendingEdits] = useState<PendingChecklistEdits>({});
  const [loadingChecklists, setLoadingChecklists] = useState(true);
  const [loadingRecords, setLoadingRecords] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [excelExportGridLayout, setExcelExportGridLayout] =
    useState<LegacyIssueGridColumnLayout | null>(null);
  const [saving, setSaving] = useState(false);
  const [deletingChecklistId, setDeletingChecklistId] = useState<string | null>(
    null,
  );
  const [attachmentMutation, setAttachmentMutation] =
    useState<ChecklistAttachmentMutation | null>(null);
  const [downloadingAttachmentId, setDownloadingAttachmentId] = useState<
    string | null
  >(null);
  const [attachmentStatus, setAttachmentStatus] = useState<string | null>(null);
  const routeScopeRef = useRef<ModuleChecklistRouteScope>({
    moduleKey,
    stageId,
    vehicleModelId,
    workspaceSlug,
  });
  const renderedRouteScope = {
    moduleKey,
    stageId,
    vehicleModelId,
    workspaceSlug,
  };
  routeScopeRef.current = renderedRouteScope;
  const routeGenerationRef = useRef({
    generation: 0,
    scope: renderedRouteScope,
  });
  if (
    !sameModuleChecklistScope(
      routeGenerationRef.current.scope,
      renderedRouteScope,
    )
  ) {
    routeGenerationRef.current = {
      generation: routeGenerationRef.current.generation + 1,
      scope: renderedRouteScope,
    };
  }
  const vehicleRequestIdRef = useRef(0);
  const checklistRequestIdRef = useRef(0);
  const checklistLoadedScopeRef = useRef<ModuleChecklistRouteScope | null>(
    null,
  );
  const recordRequestIdRef = useRef(0);
  const gridDefaultsRequestIdRef = useRef(0);
  const historyRequestIdRef = useRef(0);
  const mutationRequestIdRef = useRef(0);
  const attachmentMutationRequestIdRef = useRef(0);
  const attachmentDownloadRequestIdRef = useRef(0);
  const resetScopeRef = useRef<ModuleChecklistRouteScope>({
    moduleKey,
    stageId,
    vehicleModelId,
    workspaceSlug,
  });

  const selectedVehicle = useMemo(
    () => vehicles.find((vehicle) => vehicle.id === vehicleModelId) ?? null,
    [vehicleModelId, vehicles],
  );
  const selectedStage = useMemo(
    () =>
      selectedVehicle?.stages?.find((stage) => stage.id === stageId) ?? null,
    [selectedVehicle, stageId],
  );
  const selectedImportCandidate = useMemo(
    () =>
      importCandidates.find(
        (candidate) => candidate.checklist.id === selectedImportChecklistId,
      ) ?? null,
    [importCandidates, selectedImportChecklistId],
  );
  const latestStage = useMemo(
    () =>
      [...(selectedVehicle?.stages ?? [])]
        .sort((left, right) => left.sequence_no - right.sequence_no)
        .at(-1) ?? null,
    [selectedVehicle],
  );
  const requestedChecklistId = searchParams.get('checklist_id');
  const selectedChecklist = useMemo(() => {
    const candidate =
      checklists.find((item) => item.id === requestedChecklistId) ??
      checklists[0] ??
      null;
    return candidate &&
      candidate.vehicle_model_id === vehicleModelId &&
      candidate.stage_id === stageId &&
      candidate.module_key === moduleKey
      ? candidate
      : null;
  }, [checklists, moduleKey, requestedChecklistId, stageId, vehicleModelId]);
  const selectedChecklistIdRef = useRef<string | null>(
    selectedChecklist?.id ?? null,
  );
  selectedChecklistIdRef.current = selectedChecklist?.id ?? null;
  const checklistGridLayoutId = selectedChecklist
    ? `legacy-issues.vehicle-module-checklist.${vehicleModelId}.${stageId}.${moduleKey}.${selectedChecklist.id}`
    : null;
  const excelExportColumnKeys =
    checklistGridLayoutId &&
    excelExportGridLayout?.layoutId === checklistGridLayoutId
      ? excelExportGridLayout.columnKeys.filter(
          (columnKey) => columnKey !== CHECK_ATTACHMENT_COLUMN_KEY,
        )
      : null;
  const resolvedUserGridPreference = useMemo<
    LegacyIssueGridPreferenceValue | null | undefined
  >(() => {
    const preference = userGridPreference.preference;
    if (preference === null || preference === undefined) return preference;
    return {
      columnOrder: preference.column_order,
      frozenColumnCount: preference.frozen_column_count,
      hiddenColumnKeys: preference.hidden_column_keys,
    };
  }, [userGridPreference.preference]);
  const checkEditorRecordIdRef = useRef<string | null>(checkEditorRecordId);
  checkEditorRecordIdRef.current = checkEditorRecordId;
  const hasPendingEdits = Object.keys(pendingEdits).length > 0;
  const canEditSelectedChecklist = selectedChecklist?.status === 'draft';
  const attachmentBusy = attachmentMutation !== null;
  const checklistEditingEnabled = Boolean(
    canEditSelectedChecklist && !loadingRecords && !saving && !attachmentBusy,
  );
  const excelExport = useLegacyIssueExcelExportJob({
    createJob: async (includeAttachments) => {
      if (
        !token ||
        !workspaceSlug ||
        !selectedChecklist ||
        excelExportColumnKeys === null
      ) {
        throw new Error();
      }
      return createLegacyIssueVehicleModuleChecklistExcelExport({
        checklistId: selectedChecklist.id,
        columnKeys: excelExportColumnKeys,
        includeAttachments,
        token,
        workspaceSlug,
      });
    },
    fallbackFilename: `legacy-issue-${moduleKey}-checklist.xlsx`,
    fetchFile: (jobId) => {
      if (!token || !workspaceSlug) {
        throw new Error();
      }
      return fetchLegacyIssueExcelExportFile({
        jobId,
        token,
        workspaceSlug,
      });
    },
    fetchJob: (jobId) => {
      if (!token || !workspaceSlug) {
        throw new Error();
      }
      return fetchLegacyIssueExcelExportJob({
        jobId,
        token,
        workspaceSlug,
      });
    },
    onDownloaded: () => {
      toast.success(t('coreBusiness.excelExport.status.downloaded'));
    },
    onFailed: (reason, exportError) => {
      toast.error(
        errorMessage(exportError, t(legacyIssueExcelExportErrorKey(reason))),
      );
    },
    onFile: (blob, filename) => downloadBlobAsFile(blob, filename),
    sourceKey: selectedChecklist
      ? `vehicle-module-checklist:${selectedChecklist.id}`
      : null,
    userId: user?.id,
    workspaceSlug,
  });
  const appliedMasterRevisionIds = useMemo(
    () => new Set(checklists.map((item) => item.source_master_revision_id)),
    [checklists],
  );
  const creatableMasterRevisions = useMemo(
    () =>
      masterRevisions.filter(
        (revision) => !appliedMasterRevisionIds.has(revision.id),
      ),
    [appliedMasterRevisionIds, masterRevisions],
  );
  const selectedSourceMasterRevision = useMemo(
    () =>
      masterRevisions.find(
        (revision) => revision.id === sourceMasterRevisionId,
      ) ?? null,
    [masterRevisions, sourceMasterRevisionId],
  );
  const selectedSourceMasterRevisionIsOlder = Boolean(
    latestMasterRevision?.revision_no != null &&
      selectedSourceMasterRevision?.revision_no != null &&
      selectedSourceMasterRevision.revision_no <
        latestMasterRevision.revision_no,
  );
  const hasNewerMasterRevision = Boolean(
    latestMasterRevision?.revision_no != null &&
      selectedChecklist?.source_master_revision_no != null &&
      latestMasterRevision.revision_no >
        selectedChecklist.source_master_revision_no,
  );
  const checkEditorRecord = useMemo(
    () => records.find((record) => record.id === checkEditorRecordId) ?? null,
    [checkEditorRecordId, records],
  );

  useEffect(() => {
    setUpperControlsCollapsed(false);
  }, [activeTab, moduleKey, selectedChecklist?.id, stageId, vehicleModelId]);

  const selectChecklist = useCallback(
    (checklistId: string | null) => {
      const next = new URLSearchParams(searchParams);
      if (checklistId) {
        next.set('checklist_id', checklistId);
      } else {
        next.delete('checklist_id');
      }
      setSearchParams(next, { replace: true });
    },
    [searchParams, setSearchParams],
  );

  const loadVehicles = useCallback(async () => {
    if (!token || !workspaceSlug) return;
    const scope = { moduleKey, stageId, vehicleModelId, workspaceSlug };
    const requestId = ++vehicleRequestIdRef.current;
    try {
      const response = await fetchLegacyIssueVehicleModels({
        token,
        workspaceSlug,
      });
      if (
        requestId !== vehicleRequestIdRef.current ||
        !sameModuleChecklistScope(routeScopeRef.current, scope)
      ) {
        return;
      }
      setVehicles(response.items);
    } catch (error) {
      if (
        requestId !== vehicleRequestIdRef.current ||
        !sameModuleChecklistScope(routeScopeRef.current, scope)
      ) {
        return;
      }
      toast.error(
        errorMessage(
          error,
          t('coreBusiness.vehicleChecklist.errors.vehicleLoadFailed'),
        ),
      );
    }
  }, [moduleKey, stageId, t, toast, token, vehicleModelId, workspaceSlug]);

  const loadChecklists = useCallback(async (): Promise<
    LegacyIssueVehicleModuleChecklist[] | null
  > => {
    if (!token || !workspaceSlug || !vehicleModelId || !moduleKey || !stageId) {
      return null;
    }
    const scope = { moduleKey, stageId, vehicleModelId, workspaceSlug };
    const requestId = ++checklistRequestIdRef.current;
    checklistLoadedScopeRef.current = null;
    setLoadingChecklists(true);
    try {
      const response = await fetchLegacyIssueVehicleModuleChecklists({
        moduleKey,
        stageId,
        token,
        vehicleModelId,
        workspaceSlug,
      });
      if (
        requestId !== checklistRequestIdRef.current ||
        !sameModuleChecklistScope(routeScopeRef.current, scope)
      ) {
        return null;
      }
      checklistLoadedScopeRef.current = scope;
      setChecklists(response.items);
      setLatestMasterRevision(response.latest_master_revision);
      const nextImportCandidates = response.import_candidates ?? [];
      setImportCandidates(nextImportCandidates);
      setSelectedImportChecklistId((current) =>
        nextImportCandidates.some(
          (candidate) => candidate.checklist.id === current,
        )
          ? current
          : (nextImportCandidates[0]?.checklist.id ?? ''),
      );
      setMasterRevisions(response.master_revisions ?? []);
      setSourceMasterRevisionId((current) => {
        const appliedIds = new Set(
          response.items.map((item) => item.source_master_revision_id),
        );
        const available = (response.master_revisions ?? []).filter(
          (revision) => !appliedIds.has(revision.id),
        );
        return current && available.some((revision) => revision.id === current)
          ? current
          : (available[0]?.id ?? '');
      });
      return response.items;
    } catch (error) {
      if (
        requestId !== checklistRequestIdRef.current ||
        !sameModuleChecklistScope(routeScopeRef.current, scope)
      ) {
        return null;
      }
      const message = errorMessage(
        error,
        t('coreBusiness.vehicleChecklist.errors.checklistLoadFailed'),
      );
      toast.error(message);
      return null;
    } finally {
      if (
        requestId === checklistRequestIdRef.current &&
        sameModuleChecklistScope(routeScopeRef.current, scope)
      ) {
        setLoadingChecklists(false);
      }
    }
  }, [moduleKey, stageId, t, toast, token, vehicleModelId, workspaceSlug]);

  const loadGridDefaults = useCallback(async () => {
    if (!token || !workspaceSlug || !moduleKey) return;
    const requestId = ++gridDefaultsRequestIdRef.current;
    setGridDefaultsLoading(true);
    setGridDefaultsLoadFailed(false);
    try {
      const response = await fetchLegacyIssueColumnOrder({
        token,
        viewKey: moduleKey,
        workspaceSlug,
      });
      if (requestId !== gridDefaultsRequestIdRef.current) return;
      setDefaultColumnOrder(response.column_order);
      setDefaultHiddenColumnKeys(response.hidden_column_keys ?? []);
    } catch (error) {
      if (requestId !== gridDefaultsRequestIdRef.current) return;
      setDefaultColumnOrder([]);
      setDefaultHiddenColumnKeys([]);
      setGridDefaultsLoadFailed(true);
      toast.error(
        errorMessage(
          error,
          t('coreBusiness.fieldSettings.errors.columnOrderLoadFailed'),
        ),
      );
    } finally {
      if (requestId === gridDefaultsRequestIdRef.current) {
        setGridDefaultsLoading(false);
      }
    }
  }, [moduleKey, t, toast, token, workspaceSlug]);

  const loadRecords = useCallback(async () => {
    if (!token || !workspaceSlug || !selectedChecklist) return;
    const scope = { moduleKey, stageId, vehicleModelId, workspaceSlug };
    const checklistId = selectedChecklist.id;
    const requestId = ++recordRequestIdRef.current;
    setLoadingRecords(true);
    setDefinition(null);
    setRecords([]);
    setTotal(0);
    setCheckEditorRecordId(null);
    try {
      const response = await fetchLegacyIssueVehicleModuleChecklistRecords({
        checklistId,
        query: submittedQuery,
        token,
        workspaceSlug,
      });
      if (
        requestId !== recordRequestIdRef.current ||
        !sameModuleChecklistScope(routeScopeRef.current, scope) ||
        selectedChecklistIdRef.current !== checklistId ||
        response.checklist.id !== checklistId ||
        response.checklist.vehicle_model_id !== vehicleModelId ||
        response.checklist.stage_id !== stageId ||
        response.checklist.module_key !== moduleKey
      ) {
        return;
      }
      setChecklists((current) => {
        const existing = current.find(
          (checklist) => checklist.id === response.checklist.id,
        );
        if (
          existing?.updated_at === response.checklist.updated_at &&
          existing.status === response.checklist.status
        ) {
          return current;
        }
        return current.map((checklist) =>
          checklist.id === response.checklist.id
            ? response.checklist
            : checklist,
        );
      });
      setDefinition(response.definition);
      setRecords(response.items);
      setTotal(response.total);
      setPendingEdits({});
    } catch (error) {
      if (
        requestId !== recordRequestIdRef.current ||
        !sameModuleChecklistScope(routeScopeRef.current, scope) ||
        selectedChecklistIdRef.current !== checklistId
      ) {
        return;
      }
      const message = errorMessage(
        error,
        t('coreBusiness.vehicleChecklist.errors.recordLoadFailed'),
      );
      toast.error(message);
    } finally {
      if (
        requestId === recordRequestIdRef.current &&
        sameModuleChecklistScope(routeScopeRef.current, scope) &&
        selectedChecklistIdRef.current === checklistId
      ) {
        setLoadingRecords(false);
      }
    }
  }, [
    moduleKey,
    selectedChecklist,
    stageId,
    submittedQuery,
    t,
    toast,
    token,
    vehicleModelId,
    workspaceSlug,
  ]);

  const loadHistory = useCallback(async () => {
    if (!token || !workspaceSlug || !selectedChecklist) return;
    const scope = { moduleKey, stageId, vehicleModelId, workspaceSlug };
    const checklistId = selectedChecklist.id;
    const requestId = ++historyRequestIdRef.current;
    setLoadingHistory(true);
    try {
      const response = await fetchLegacyIssueVehicleModuleChecklistHistory({
        checklistId,
        token,
        workspaceSlug,
      });
      if (
        requestId !== historyRequestIdRef.current ||
        !sameModuleChecklistScope(routeScopeRef.current, scope) ||
        selectedChecklistIdRef.current !== checklistId ||
        response.checklist.id !== checklistId ||
        response.checklist.vehicle_model_id !== vehicleModelId ||
        response.checklist.stage_id !== stageId ||
        response.checklist.module_key !== moduleKey
      ) {
        return;
      }
      setHistoryItems(response.items);
    } catch (error) {
      if (
        requestId !== historyRequestIdRef.current ||
        !sameModuleChecklistScope(routeScopeRef.current, scope) ||
        selectedChecklistIdRef.current !== checklistId
      ) {
        return;
      }
      const message = errorMessage(
        error,
        t('coreBusiness.vehicleChecklist.errors.historyLoadFailed'),
      );
      toast.error(message);
    } finally {
      if (
        requestId === historyRequestIdRef.current &&
        sameModuleChecklistScope(routeScopeRef.current, scope) &&
        selectedChecklistIdRef.current === checklistId
      ) {
        setLoadingHistory(false);
      }
    }
  }, [
    moduleKey,
    selectedChecklist,
    stageId,
    t,
    toast,
    token,
    vehicleModelId,
    workspaceSlug,
  ]);

  useEffect(() => {
    const previousScope = resetScopeRef.current;
    const nextScope = { moduleKey, stageId, vehicleModelId, workspaceSlug };
    if (sameModuleChecklistScope(previousScope, nextScope)) return;
    resetScopeRef.current = nextScope;
    vehicleRequestIdRef.current += 1;
    checklistRequestIdRef.current += 1;
    recordRequestIdRef.current += 1;
    gridDefaultsRequestIdRef.current += 1;
    historyRequestIdRef.current += 1;
    mutationRequestIdRef.current += 1;
    attachmentMutationRequestIdRef.current += 1;
    attachmentDownloadRequestIdRef.current += 1;
    setVehicles([]);
    setChecklists([]);
    setLatestMasterRevision(null);
    setImportCandidates([]);
    setImportDialogOpen(false);
    setSelectedImportChecklistId('');
    setMasterRevisions([]);
    setSourceMasterRevisionId('');
    setDefinition(null);
    setDefaultColumnOrder([]);
    setDefaultHiddenColumnKeys([]);
    setGridDefaultsLoadFailed(false);
    setRecords([]);
    setHistoryItems([]);
    setTotal(0);
    setQuery('');
    setSubmittedQuery('');
    setActiveTab('sheet');
    setCheckEditorRecordId(null);
    setPendingEdits({});
    setSaving(false);
    setDeletingChecklistId(null);
    setAttachmentMutation(null);
    setDownloadingAttachmentId(null);
    setAttachmentStatus(null);
  }, [moduleKey, stageId, vehicleModelId, workspaceSlug]);

  useEffect(() => {
    void loadVehicles();
  }, [loadVehicles]);

  useEffect(() => {
    if (!selectedVehicle || selectedStage || !latestStage) return;
    const next = new URLSearchParams(searchParams);
    next.set('stage_id', latestStage.id);
    next.delete('checklist_id');
    setSearchParams(next, { replace: true });
  }, [
    latestStage,
    searchParams,
    selectedStage,
    selectedVehicle,
    setSearchParams,
  ]);

  useEffect(() => {
    void loadChecklists();
  }, [loadChecklists]);

  useEffect(() => {
    void loadGridDefaults();
  }, [loadGridDefaults]);

  useEffect(() => {
    if (
      loadingChecklists ||
      !requestedChecklistId ||
      !checklistLoadedScopeRef.current ||
      !sameModuleChecklistScope(
        checklistLoadedScopeRef.current,
        routeScopeRef.current,
      )
    ) {
      return;
    }
    const requestedChecklistExists = checklists.some(
      (checklist) =>
        checklist.id === requestedChecklistId &&
        checklist.vehicle_model_id === vehicleModelId &&
        checklist.stage_id === stageId &&
        checklist.module_key === moduleKey,
    );
    if (!requestedChecklistExists) {
      selectChecklist(selectedChecklist?.id ?? null);
    }
  }, [
    checklists,
    loadingChecklists,
    moduleKey,
    requestedChecklistId,
    selectChecklist,
    selectedChecklist?.id,
    stageId,
    vehicleModelId,
  ]);

  useEffect(() => {
    setDefinition(null);
    setRecords([]);
    setHistoryItems([]);
    setTotal(0);
    setPendingEdits({});
    setCheckEditorRecordId(null);
    setActiveTab('sheet');
    recordRequestIdRef.current += 1;
    historyRequestIdRef.current += 1;
    attachmentMutationRequestIdRef.current += 1;
    attachmentDownloadRequestIdRef.current += 1;
    setAttachmentMutation(null);
    setDownloadingAttachmentId(null);
    setAttachmentStatus(null);
    void loadRecords();
  }, [loadRecords]);

  useEffect(() => {
    if (activeTab === 'history') {
      setCheckEditorRecordId(null);
      void loadHistory();
    }
  }, [activeTab, loadHistory]);

  useEffect(() => {
    if (
      checkEditorRecordId &&
      !records.some((record) => record.id === checkEditorRecordId)
    ) {
      setCheckEditorRecordId(null);
    }
  }, [checkEditorRecordId, records]);

  useEffect(() => {
    setAttachmentStatus(null);
  }, [checkEditorRecordId]);

  async function createChecklist() {
    if (
      !token ||
      !workspaceSlug ||
      !vehicleModelId ||
      !moduleKey ||
      !stageId ||
      !sourceMasterRevisionId ||
      saving ||
      attachmentBusy ||
      hasPendingEdits
    ) {
      return;
    }
    const scope = { moduleKey, stageId, vehicleModelId, workspaceSlug };
    const routeGeneration = routeGenerationRef.current.generation;
    if (selectedSourceMasterRevisionIsOlder) {
      const confirmed = await confirm({
        cancelLabel: t('common:actions.cancel'),
        confirmLabel: t(
          'coreBusiness.vehicleChecklist.confirmPastMasterRevision.confirm',
        ),
        description: t(
          'coreBusiness.vehicleChecklist.confirmPastMasterRevision.description',
          {
            latest: latestMasterRevision?.revision_no ?? '-',
            selected: selectedSourceMasterRevision?.revision_no ?? '-',
          },
        ),
        title: t(
          'coreBusiness.vehicleChecklist.confirmPastMasterRevision.title',
        ),
      });
      if (!confirmed) return;
    }
    if (
      routeGeneration !== routeGenerationRef.current.generation ||
      !sameModuleChecklistScope(routeScopeRef.current, scope)
    ) {
      return;
    }
    const requestId = ++mutationRequestIdRef.current;
    setSaving(true);
    try {
      const created = await createLegacyIssueVehicleModuleChecklist({
        moduleKey,
        sourceMasterRevisionId,
        stageId,
        token,
        vehicleModelId,
        workspaceSlug,
      });
      if (
        requestId !== mutationRequestIdRef.current ||
        !sameModuleChecklistScope(routeScopeRef.current, scope) ||
        created.vehicle_model_id !== vehicleModelId ||
        created.stage_id !== stageId ||
        created.module_key !== moduleKey
      ) {
        return;
      }
      toast.success(t('coreBusiness.vehicleChecklist.status.checklistCreated'));
      await loadChecklists();
      if (sameModuleChecklistScope(routeScopeRef.current, scope)) {
        selectChecklist(created.id);
      }
    } catch (error) {
      if (
        requestId === mutationRequestIdRef.current &&
        sameModuleChecklistScope(routeScopeRef.current, scope)
      ) {
        toast.error(
          errorMessage(
            error,
            t('coreBusiness.vehicleChecklist.errors.checklistCreateFailed'),
          ),
        );
      }
    } finally {
      if (requestId === mutationRequestIdRef.current) setSaving(false);
    }
  }

  async function importPreviousStageChecklist() {
    if (
      !token ||
      !workspaceSlug ||
      !vehicleModelId ||
      !moduleKey ||
      !stageId ||
      !selectedImportCandidate ||
      checklists.length !== 0 ||
      saving ||
      attachmentBusy ||
      hasPendingEdits
    ) {
      return;
    }
    const scope = { moduleKey, stageId, vehicleModelId, workspaceSlug };
    const routeGeneration = routeGenerationRef.current.generation;
    const requestId = ++mutationRequestIdRef.current;
    setSaving(true);
    try {
      const imported =
        await importPreviousStageLegacyIssueVehicleModuleChecklist({
          moduleKey,
          sourceChecklistId: selectedImportCandidate.checklist.id,
          stageId,
          token,
          vehicleModelId,
          workspaceSlug,
        });
      if (
        requestId !== mutationRequestIdRef.current ||
        routeGeneration !== routeGenerationRef.current.generation ||
        !sameModuleChecklistScope(routeScopeRef.current, scope) ||
        imported.vehicle_model_id !== vehicleModelId ||
        imported.stage_id !== stageId ||
        imported.module_key !== moduleKey
      ) {
        return;
      }
      toast.success(
        t('coreBusiness.vehicleChecklist.status.previousStageImported', {
          stage: selectedImportCandidate.stage.name,
        }),
      );
      setImportDialogOpen(false);
      await loadChecklists();
      if (sameModuleChecklistScope(routeScopeRef.current, scope)) {
        selectChecklist(imported.id);
      }
    } catch (error) {
      if (
        requestId === mutationRequestIdRef.current &&
        sameModuleChecklistScope(routeScopeRef.current, scope)
      ) {
        toast.error(
          errorMessage(
            error,
            t('coreBusiness.vehicleChecklist.errors.previousStageImportFailed'),
          ),
        );
      }
    } finally {
      if (requestId === mutationRequestIdRef.current) setSaving(false);
    }
  }

  async function savePendingEdits() {
    if (
      !token ||
      !workspaceSlug ||
      !selectedChecklist ||
      !canEditSelectedChecklist ||
      saving ||
      attachmentBusy ||
      !hasPendingEdits
    ) {
      return;
    }
    const scope = { moduleKey, stageId, vehicleModelId, workspaceSlug };
    const checklistId = selectedChecklist.id;
    const requestId = ++mutationRequestIdRef.current;
    setSaving(true);
    try {
      await saveLegacyIssueVehicleModuleChecklistRecords({
        checklistId,
        token,
        updates: Object.entries(pendingEdits).map(([recordId, values]) => ({
          record_id: recordId,
          values,
        })),
        workspaceSlug,
      });
      if (
        requestId !== mutationRequestIdRef.current ||
        !sameModuleChecklistScope(routeScopeRef.current, scope) ||
        selectedChecklistIdRef.current !== checklistId
      ) {
        return;
      }
      toast.success(t('coreBusiness.vehicleChecklist.status.saved'));
      await loadRecords();
    } catch (error) {
      if (
        requestId === mutationRequestIdRef.current &&
        sameModuleChecklistScope(routeScopeRef.current, scope) &&
        selectedChecklistIdRef.current === checklistId
      ) {
        toast.error(
          errorMessage(
            error,
            t('coreBusiness.vehicleChecklist.errors.saveFailed'),
          ),
        );
      }
    } finally {
      if (requestId === mutationRequestIdRef.current) setSaving(false);
    }
  }

  async function changeChecklistStatus(action: 'complete' | 'reopen') {
    if (
      !token ||
      !workspaceSlug ||
      !selectedChecklist ||
      saving ||
      attachmentBusy ||
      hasPendingEdits
    ) {
      return;
    }
    const scope = { moduleKey, stageId, vehicleModelId, workspaceSlug };
    const checklistId = selectedChecklist.id;
    const requestId = ++mutationRequestIdRef.current;
    setSaving(true);
    try {
      const updated =
        action === 'complete'
          ? await completeLegacyIssueVehicleModuleChecklist({
              checklistId,
              token,
              workspaceSlug,
            })
          : await reopenLegacyIssueVehicleModuleChecklist({
              checklistId,
              token,
              workspaceSlug,
            });
      if (
        requestId !== mutationRequestIdRef.current ||
        !sameModuleChecklistScope(routeScopeRef.current, scope) ||
        selectedChecklistIdRef.current !== checklistId ||
        updated.id !== checklistId
      ) {
        return;
      }
      toast.success(
        t(
          `coreBusiness.vehicleChecklist.status.${
            action === 'complete' ? 'completed' : 'reopened'
          }`,
        ),
      );
      await loadChecklists();
      if (
        requestId !== mutationRequestIdRef.current ||
        !sameModuleChecklistScope(routeScopeRef.current, scope) ||
        selectedChecklistIdRef.current !== checklistId
      ) {
        return;
      }
      await loadRecords();
      if (selectedChecklistIdRef.current !== checklistId) return;
      if (activeTab === 'history') await loadHistory();
    } catch (error) {
      if (
        requestId === mutationRequestIdRef.current &&
        sameModuleChecklistScope(routeScopeRef.current, scope) &&
        selectedChecklistIdRef.current === checklistId
      ) {
        toast.error(
          errorMessage(
            error,
            t(
              `coreBusiness.vehicleChecklist.errors.${
                action === 'complete' ? 'completeFailed' : 'reopenFailed'
              }`,
            ),
          ),
        );
      }
    } finally {
      if (requestId === mutationRequestIdRef.current) setSaving(false);
    }
  }

  async function deleteChecklist() {
    if (
      !token ||
      !workspaceSlug ||
      !selectedChecklist ||
      saving ||
      attachmentBusy ||
      deletingChecklistId ||
      loadingChecklists ||
      hasPendingEdits
    ) {
      return;
    }
    const checklist = selectedChecklist;
    const scope = { moduleKey, stageId, vehicleModelId, workspaceSlug };
    const routeGeneration = routeGenerationRef.current.generation;
    const confirmed = await confirm({
      cancelLabel: t('common:actions.cancel'),
      confirmLabel: t('coreBusiness.vehicleChecklist.confirmDelete.confirm'),
      description: t(
        'coreBusiness.vehicleChecklist.confirmDelete.moduleDescription',
        {
          module: vehicleChecklistModuleLabel(moduleKey, t),
          revision: checklist.source_master_revision_no ?? '-',
          rowCount: checklist.row_count,
          status: t(
            `coreBusiness.vehicleChecklist.revisionStatus.${checklist.status}`,
            { defaultValue: checklist.status },
          ),
          vehicle: selectedVehicle
            ? formatVehicleModelTitle(selectedVehicle)
            : vehicleModelId,
        },
      ),
      title: t('coreBusiness.vehicleChecklist.confirmDelete.title'),
      variant: 'danger',
    });
    if (
      !confirmed ||
      routeGeneration !== routeGenerationRef.current.generation ||
      !sameModuleChecklistScope(routeScopeRef.current, scope) ||
      selectedChecklistIdRef.current !== checklist.id ||
      checklist.vehicle_model_id !== vehicleModelId ||
      checklist.stage_id !== stageId ||
      checklist.module_key !== moduleKey
    ) {
      return;
    }
    const requestId = ++mutationRequestIdRef.current;
    setDeletingChecklistId(checklist.id);
    try {
      await deleteLegacyIssueVehicleModuleChecklist({
        checklistId: checklist.id,
        token,
        workspaceSlug,
      });
      if (
        requestId !== mutationRequestIdRef.current ||
        !sameModuleChecklistScope(routeScopeRef.current, scope) ||
        selectedChecklistIdRef.current !== checklist.id
      ) {
        return;
      }
      const nextChecklistId = resolveNextVehicleModuleChecklistId(
        checklists,
        checklist.id,
      );
      setChecklists((current) =>
        current.filter((item) => item.id !== checklist.id),
      );
      setDefinition(null);
      setRecords([]);
      setHistoryItems([]);
      setPendingEdits({});
      setTotal(0);
      selectChecklist(nextChecklistId);
      toast.success(t('coreBusiness.vehicleChecklist.status.deleted'));
      const refreshed = await loadChecklists();
      if (refreshed && sameModuleChecklistScope(routeScopeRef.current, scope)) {
        const refreshedSelection =
          refreshed.find((item) => item.id === nextChecklistId)?.id ??
          refreshed[0]?.id ??
          null;
        selectChecklist(refreshedSelection);
      }
    } catch (error) {
      if (
        requestId === mutationRequestIdRef.current &&
        sameModuleChecklistScope(routeScopeRef.current, scope) &&
        selectedChecklistIdRef.current === checklist.id
      ) {
        toast.error(
          errorMessage(
            error,
            t('coreBusiness.vehicleChecklist.errors.deleteFailed'),
          ),
        );
      }
    } finally {
      if (requestId === mutationRequestIdRef.current) {
        setDeletingChecklistId(null);
      }
    }
  }

  function stageCellEdit({
    columnKey,
    record,
    value,
  }: {
    columnKey: string;
    record: LegacyIssueVehicleModuleChecklistRecord;
    value: string | null;
  }) {
    if (!CHECK_FIELD_KEY_SET.has(columnKey) || !checklistEditingEnabled) return;
    const normalizedValue = normalizeGridEditValue(value);
    setRecords((current) =>
      current.map((item) =>
        item.id === record.id
          ? {
              ...item,
              values: mergeVehicleChecklistValues(item.values, {
                [columnKey]: normalizedValue,
              }),
            }
          : item,
      ),
    );
    setPendingEdits((current) => ({
      ...current,
      [record.id]: {
        ...(current[record.id] ?? {}),
        [columnKey]: normalizedValue,
      },
    }));
  }

  function stageCellBatchEdit({
    edits,
  }: {
    edits: Array<{
      columnKey: string;
      record: LegacyIssueVehicleModuleChecklistRecord;
      value: string | null;
    }>;
  }) {
    for (const edit of edits) stageCellEdit(edit);
  }

  function applyCheckEditorValues({
    record,
    values,
  }: {
    record: LegacyIssueVehicleModuleChecklistRecord;
    values: Record<VehicleChecklistCheckFieldKey, string | null>;
  }) {
    const edits = CHECK_FIELD_KEYS.flatMap((columnKey) => {
      const currentValue = normalizeGridEditValue(
        displayVehicleChecklistFieldValue(record.values[columnKey]),
      );
      const nextValue = normalizeGridEditValue(values[columnKey]);
      return currentValue === nextValue
        ? []
        : [{ columnKey, record, value: nextValue }];
    });
    if (edits.length > 0) stageCellBatchEdit({ edits });
    setCheckEditorRecordId(null);
  }

  async function uploadChecklistAttachments(
    record: LegacyIssueVehicleModuleChecklistRecord,
    files: FileList | File[],
  ) {
    const selectedFiles = Array.from(files);
    if (
      selectedFiles.length === 0 ||
      !token ||
      !workspaceSlug ||
      !selectedChecklist ||
      selectedChecklist.status !== 'draft' ||
      selectedChecklist.id !== record.checklist_id ||
      checkEditorRecordIdRef.current !== record.id ||
      saving ||
      loadingRecords ||
      attachmentBusy
    ) {
      return;
    }
    const checklistId = selectedChecklist.id;
    const scope = { moduleKey, stageId, vehicleModelId, workspaceSlug };
    const routeGeneration = routeGenerationRef.current.generation;
    const requestId = ++attachmentMutationRequestIdRef.current;
    setAttachmentStatus(
      t('coreBusiness.vehicleChecklist.attachments.uploading', {
        count: selectedFiles.length,
      }),
    );
    setAttachmentMutation({
      attachmentId: null,
      kind: 'upload',
      recordId: record.id,
    });
    try {
      const results = await Promise.allSettled(
        selectedFiles.map((file) =>
          uploadLegacyIssueVehicleModuleChecklistAttachment({
            checklistId,
            file,
            recordId: record.id,
            token,
            workspaceSlug,
          }),
        ),
      );
      if (
        requestId !== attachmentMutationRequestIdRef.current ||
        routeGeneration !== routeGenerationRef.current.generation ||
        !sameModuleChecklistScope(routeScopeRef.current, scope) ||
        selectedChecklistIdRef.current !== checklistId ||
        checkEditorRecordIdRef.current !== record.id
      ) {
        return;
      }
      const uploaded = results.flatMap((result) =>
        result.status === 'fulfilled' &&
        result.value.checklist_id === checklistId &&
        result.value.record_id === record.id
          ? [result.value]
          : [],
      );
      if (uploaded.length > 0) {
        setRecords((current) =>
          mergeVehicleChecklistRecordAttachments(
            current,
            record.id,
            checklistId,
            uploaded,
          ),
        );
      }
      const failedCount = selectedFiles.length - uploaded.length;
      if (failedCount > 0) {
        if (uploaded.length > 0) {
          toast.success(
            t('coreBusiness.vehicleChecklist.status.attachmentsUploaded', {
              count: uploaded.length,
            }),
          );
        }
        const firstFailure = results.find(
          (result): result is PromiseRejectedResult =>
            result.status === 'rejected',
        );
        const fallback = t(
          uploaded.length > 0
            ? 'coreBusiness.vehicleChecklist.errors.attachmentUploadPartialFailed'
            : 'coreBusiness.vehicleChecklist.errors.attachmentUploadFailed',
          {
            failed: failedCount,
            total: selectedFiles.length,
          },
        );
        toast.error(
          firstFailure ? errorMessage(firstFailure.reason, fallback) : fallback,
        );
      } else {
        toast.success(
          t('coreBusiness.vehicleChecklist.status.attachmentsUploaded', {
            count: uploaded.length,
          }),
        );
      }
    } finally {
      if (requestId === attachmentMutationRequestIdRef.current) {
        setAttachmentStatus(null);
        setAttachmentMutation(null);
      }
    }
  }

  async function downloadChecklistAttachment(
    record: LegacyIssueVehicleModuleChecklistRecord,
    attachment: LegacyIssueVehicleModuleChecklistAttachment,
  ) {
    if (
      !token ||
      !workspaceSlug ||
      !selectedChecklist ||
      selectedChecklist.id !== record.checklist_id ||
      attachment.checklist_id !== selectedChecklist.id ||
      attachment.record_id !== record.id ||
      downloadingAttachmentId
    ) {
      return;
    }
    const checklistId = selectedChecklist.id;
    const scope = { moduleKey, stageId, vehicleModelId, workspaceSlug };
    const routeGeneration = routeGenerationRef.current.generation;
    const requestId = ++attachmentDownloadRequestIdRef.current;
    setDownloadingAttachmentId(attachment.id);
    try {
      const blob = await fetchLegacyIssueVehicleModuleChecklistAttachmentBlob({
        attachmentId: attachment.id,
        checklistId,
        token,
        workspaceSlug,
      });
      if (
        requestId !== attachmentDownloadRequestIdRef.current ||
        routeGeneration !== routeGenerationRef.current.generation ||
        !sameModuleChecklistScope(routeScopeRef.current, scope) ||
        selectedChecklistIdRef.current !== checklistId ||
        checkEditorRecordIdRef.current !== record.id
      ) {
        return;
      }
      downloadBlobAsFile(blob, attachment.filename);
    } catch (error) {
      if (
        requestId === attachmentDownloadRequestIdRef.current &&
        sameModuleChecklistScope(routeScopeRef.current, scope) &&
        selectedChecklistIdRef.current === checklistId &&
        checkEditorRecordIdRef.current === record.id
      ) {
        toast.error(
          errorMessage(
            error,
            t('coreBusiness.vehicleChecklist.errors.attachmentDownloadFailed'),
          ),
        );
      }
    } finally {
      if (requestId === attachmentDownloadRequestIdRef.current) {
        setDownloadingAttachmentId(null);
      }
    }
  }

  async function deleteChecklistAttachment(
    record: LegacyIssueVehicleModuleChecklistRecord,
    attachment: LegacyIssueVehicleModuleChecklistAttachment,
  ) {
    if (
      !token ||
      !workspaceSlug ||
      !selectedChecklist ||
      selectedChecklist.status !== 'draft' ||
      selectedChecklist.id !== record.checklist_id ||
      attachment.checklist_id !== selectedChecklist.id ||
      attachment.record_id !== record.id ||
      checkEditorRecordIdRef.current !== record.id ||
      saving ||
      loadingRecords ||
      attachmentBusy
    ) {
      return;
    }
    const checklistId = selectedChecklist.id;
    const scope = { moduleKey, stageId, vehicleModelId, workspaceSlug };
    const routeGeneration = routeGenerationRef.current.generation;
    const confirmed = await confirm({
      cancelLabel: t('common:actions.cancel'),
      confirmLabel: t(
        'coreBusiness.vehicleChecklist.confirmAttachmentDelete.confirm',
      ),
      description: t(
        'coreBusiness.vehicleChecklist.confirmAttachmentDelete.description',
        { filename: attachment.filename },
      ),
      title: t('coreBusiness.vehicleChecklist.confirmAttachmentDelete.title'),
      variant: 'danger',
    });
    if (
      !confirmed ||
      routeGeneration !== routeGenerationRef.current.generation ||
      !sameModuleChecklistScope(routeScopeRef.current, scope) ||
      selectedChecklistIdRef.current !== checklistId ||
      checkEditorRecordIdRef.current !== record.id
    ) {
      return;
    }
    const requestId = ++attachmentMutationRequestIdRef.current;
    setAttachmentStatus(null);
    setAttachmentMutation({
      attachmentId: attachment.id,
      kind: 'delete',
      recordId: record.id,
    });
    try {
      await deleteLegacyIssueVehicleModuleChecklistAttachment({
        attachmentId: attachment.id,
        checklistId,
        token,
        workspaceSlug,
      });
      if (
        requestId !== attachmentMutationRequestIdRef.current ||
        routeGeneration !== routeGenerationRef.current.generation ||
        !sameModuleChecklistScope(routeScopeRef.current, scope) ||
        selectedChecklistIdRef.current !== checklistId ||
        checkEditorRecordIdRef.current !== record.id
      ) {
        return;
      }
      setRecords((current) =>
        removeVehicleChecklistRecordAttachment(
          current,
          record.id,
          checklistId,
          attachment.id,
        ),
      );
      toast.success(
        t('coreBusiness.vehicleChecklist.status.attachmentDeleted', {
          filename: attachment.filename,
        }),
      );
    } catch (error) {
      if (
        requestId === attachmentMutationRequestIdRef.current &&
        sameModuleChecklistScope(routeScopeRef.current, scope) &&
        selectedChecklistIdRef.current === checklistId &&
        checkEditorRecordIdRef.current === record.id
      ) {
        toast.error(
          errorMessage(
            error,
            t('coreBusiness.vehicleChecklist.errors.attachmentDeleteFailed'),
          ),
        );
      }
    } finally {
      if (requestId === attachmentMutationRequestIdRef.current) {
        setAttachmentMutation(null);
      }
    }
  }

  const moduleLabel = vehicleChecklistModuleLabel(moduleKey, t);
  const pageTitle = [
    selectedVehicle ? formatVehicleModelTitle(selectedVehicle) : null,
    selectedStage?.name ?? null,
    moduleLabel,
  ]
    .filter(Boolean)
    .join(' · ');

  return (
    <div className="relative flex h-full min-h-0 bg-app-bg">
      {confirmDialog}
      <FormDialog
        cancelLabel={t('common:actions.cancel')}
        closeLabel={t('common:actions.close')}
        description={t(
          'coreBusiness.vehicleChecklist.importDialog.description',
        )}
        maxWidth="max-w-4xl"
        open={importDialogOpen}
        primaryDisabled={!selectedImportCandidate}
        primaryLabel={t('coreBusiness.vehicleChecklist.importDialog.confirm')}
        primaryPendingLabel={t(
          'coreBusiness.vehicleChecklist.importDialog.importing',
        )}
        submitting={saving}
        title={t('coreBusiness.vehicleChecklist.importDialog.title')}
        onCancel={() => {
          if (!saving) setImportDialogOpen(false);
        }}
        onPrimary={() => void importPreviousStageChecklist()}
      >
        <fieldset className="grid gap-2">
          <legend className="sr-only">
            {t('coreBusiness.vehicleChecklist.importDialog.selectionLabel')}
          </legend>
          {importCandidates.map((candidate) => {
            const checked =
              candidate.checklist.id === selectedImportChecklistId;
            const completedBy =
              candidate.completed_by_name ||
              candidate.completed_by_email ||
              t(
                'coreBusiness.vehicleChecklist.importDialog.unknownCompletedBy',
              );
            return (
              <label
                className={`grid cursor-pointer grid-cols-[auto_minmax(0,1fr)] gap-3 rounded-lg border p-3 transition-colors ${
                  checked
                    ? 'border-app-accent bg-app-accent/5'
                    : 'border-app-border bg-app-surface hover:border-app-accent/50'
                }`}
                key={candidate.checklist.id}
              >
                <input
                  checked={checked}
                  className="mt-1 accent-app-accent"
                  name="legacy-issue-checklist-import-source"
                  type="radio"
                  value={candidate.checklist.id}
                  onChange={() =>
                    setSelectedImportChecklistId(candidate.checklist.id)
                  }
                />
                <span className="grid min-w-0 gap-2">
                  <span className="flex flex-wrap items-center gap-2">
                    <span className="rounded-full border border-app-border bg-app-surface-sidebar px-2 py-1 app-text-caption font-semibold text-app-ink">
                      {candidate.stage.name}
                    </span>
                    <span className="font-semibold text-app-ink">
                      {t(
                        'coreBusiness.vehicleChecklist.importDialog.masterRevision',
                        {
                          revision:
                            candidate.checklist.source_master_revision_no ??
                            '-',
                        },
                      )}
                    </span>
                  </span>
                  <span className="grid gap-x-6 gap-y-1 text-app-ink/65 sm:grid-cols-3">
                    <span>
                      {t(
                        'coreBusiness.vehicleChecklist.importDialog.completedAt',
                      )}
                      {' · '}
                      {candidate.checklist.completed_at ? (
                        <UserDateTime
                          display="datetime"
                          value={candidate.checklist.completed_at}
                        />
                      ) : (
                        '-'
                      )}
                    </span>
                    <span>
                      {t(
                        'coreBusiness.vehicleChecklist.importDialog.completedBy',
                      )}
                      {' · '}
                      {completedBy}
                    </span>
                    <span>
                      {t(
                        'coreBusiness.vehicleChecklist.importDialog.rowCount',
                        { count: candidate.checklist.row_count },
                      )}
                    </span>
                  </span>
                </span>
              </label>
            );
          })}
        </fieldset>
      </FormDialog>
      <section className="flex min-h-0 min-w-0 flex-1 flex-col bg-app-bg">
        {!upperControlsCollapsed ? (
          <LegacyIssuePageHeader
            eyebrow={t('coreBusiness.vehicleChecklist.detail.eyebrow')}
            title={pageTitle}
            actions={
              <>
                <Link
                  className="app-control h-9 px-3"
                  to={buildWorkspaceAppPath(
                    workspaceSlug,
                    'legacy-issues',
                    `/vehicle-checklists/${vehicleModelId}${
                      stageId ? `?stage_id=${encodeURIComponent(stageId)}` : ''
                    }`,
                  )}
                >
                  <ArrowLeft size={16} />
                  {t('coreBusiness.vehicleChecklist.actions.backToModules')}
                </Link>
                <LegacyIssueExcelExportControls
                  disabled={
                    saving ||
                    attachmentBusy ||
                    hasPendingEdits ||
                    loadingRecords ||
                    !selectedChecklist ||
                    !user?.id ||
                    excelExportColumnKeys === null
                  }
                  exportLabel={t(
                    'coreBusiness.vehicleChecklist.actions.export',
                  )}
                  workflow={excelExport}
                />
                {checklists.length === 0 && importCandidates.length > 0 ? (
                  <LegacyIssueToolbarButton
                    disabled={
                      saving ||
                      attachmentBusy ||
                      loadingChecklists ||
                      hasPendingEdits
                    }
                    icon={
                      saving ? (
                        <Loader2 size={16} className="animate-spin" />
                      ) : (
                        <CopyPlus size={16} />
                      )
                    }
                    label={t(
                      'coreBusiness.vehicleChecklist.actions.importCompleted',
                    )}
                    onClick={() => {
                      setSelectedImportChecklistId(
                        importCandidates[0]?.checklist.id ?? '',
                      );
                      setImportDialogOpen(true);
                    }}
                  />
                ) : null}
                <LegacyIssueToolbarButton
                  disabled={
                    saving ||
                    attachmentBusy ||
                    hasPendingEdits ||
                    selectedChecklist?.status !== 'completed'
                  }
                  icon={<PencilLine size={16} />}
                  label={t('coreBusiness.vehicleChecklist.actions.reopen')}
                  onClick={() => void changeChecklistStatus('reopen')}
                />
                <LegacyIssueToolbarButton
                  disabled={
                    saving ||
                    attachmentBusy ||
                    hasPendingEdits ||
                    selectedChecklist?.status !== 'draft'
                  }
                  icon={<CheckCircle2 size={16} />}
                  label={t('coreBusiness.vehicleChecklist.actions.complete')}
                  onClick={() => void changeChecklistStatus('complete')}
                />
                <LegacyIssueToolbarButton
                  disabled={
                    saving ||
                    attachmentBusy ||
                    hasPendingEdits ||
                    loadingChecklists ||
                    !selectedChecklist ||
                    Boolean(deletingChecklistId)
                  }
                  icon={
                    deletingChecklistId ? (
                      <Loader2 size={16} className="animate-spin" />
                    ) : (
                      <Trash2 size={16} />
                    )
                  }
                  label={t('coreBusiness.vehicleChecklist.actions.delete')}
                  onClick={() => void deleteChecklist()}
                />
              </>
            }
          />
        ) : null}
        {!upperControlsCollapsed ? (
          <div className="overflow-x-auto border-b border-app-border bg-app-surface-sidebar">
            <div className="flex min-w-max flex-nowrap items-center gap-2 px-4 py-1.5">
              {selectedChecklist ? (
                <div className="flex shrink-0 items-center gap-1 border-r border-app-border pr-2">
                  <ChecklistTabButton
                    active={activeTab === 'sheet'}
                    icon={<Table2 size={15} />}
                    label={t('coreBusiness.vehicleChecklist.tabs.sheet')}
                    onClick={() => setActiveTab('sheet')}
                  />
                  <ChecklistTabButton
                    active={activeTab === 'history'}
                    icon={<History size={15} />}
                    label={t('coreBusiness.vehicleChecklist.tabs.history')}
                    onClick={() => setActiveTab('history')}
                  />
                </div>
              ) : null}
              <label
                className="shrink-0 app-text-caption font-semibold text-app-ink/55"
                htmlFor="legacy-issue-vehicle-module-checklist-select"
              >
                {t('coreBusiness.vehicleChecklist.checklist')}
              </label>
              <select
                id="legacy-issue-vehicle-module-checklist-select"
                className="app-field-input-sm !w-52 min-w-52 max-w-52 shrink-0"
                disabled={
                  loadingChecklists ||
                  saving ||
                  attachmentBusy ||
                  hasPendingEdits ||
                  Boolean(deletingChecklistId) ||
                  checklists.length === 0
                }
                value={selectedChecklist?.id ?? ''}
                onChange={(event) => selectChecklist(event.target.value)}
              >
                {checklists.length === 0 ? (
                  <option value="">
                    {t('coreBusiness.vehicleChecklist.noChecklist')}
                  </option>
                ) : (
                  checklists.map((checklist) => (
                    <option key={checklist.id} value={checklist.id}>
                      {t('coreBusiness.vehicleChecklist.revisionOption', {
                        master: checklist.source_master_revision_no ?? '-',
                        status: t(
                          `coreBusiness.vehicleChecklist.revisionStatus.${checklist.status}`,
                          { defaultValue: checklist.status },
                        ),
                      })}
                    </option>
                  ))
                )}
              </select>
              {hasNewerMasterRevision ? (
                <span className="shrink-0 rounded border border-app-border bg-app-bg px-2 py-1 app-text-caption text-app-ink/60">
                  {t('coreBusiness.vehicleChecklist.newMasterBadge', {
                    revision: latestMasterRevision?.revision_no ?? '-',
                  })}
                </span>
              ) : null}
              <span
                aria-hidden="true"
                className="mx-1 h-6 w-px shrink-0 bg-app-border"
              />
              <label
                className="shrink-0 app-text-caption font-semibold text-app-ink/55"
                htmlFor="legacy-issue-module-checklist-source-master"
              >
                {t(
                  'coreBusiness.vehicleChecklist.actions.sourceMasterRevision',
                )}
              </label>
              <select
                id="legacy-issue-module-checklist-source-master"
                className="app-field-input-sm !w-44 min-w-44 max-w-44 shrink-0"
                disabled={
                  saving ||
                  attachmentBusy ||
                  loadingChecklists ||
                  hasPendingEdits ||
                  creatableMasterRevisions.length === 0
                }
                value={sourceMasterRevisionId}
                onChange={(event) =>
                  setSourceMasterRevisionId(event.target.value)
                }
              >
                {creatableMasterRevisions.length === 0 ? (
                  <option value="">
                    {t(
                      'coreBusiness.vehicleChecklist.noCreatableMasterRevision',
                    )}
                  </option>
                ) : (
                  creatableMasterRevisions.map((revision) => (
                    <option key={revision.id} value={revision.id}>
                      {t('coreBusiness.vehicleChecklist.summaryRevision', {
                        revision: revision.revision_no ?? '-',
                      })}
                    </option>
                  ))
                )}
              </select>
              <LegacyIssueToolbarButton
                disabled={
                  saving ||
                  attachmentBusy ||
                  loadingChecklists ||
                  hasPendingEdits ||
                  !sourceMasterRevisionId
                }
                icon={
                  saving ? (
                    <Loader2 size={16} className="animate-spin" />
                  ) : (
                    <Plus size={16} />
                  )
                }
                label={t(
                  'coreBusiness.vehicleChecklist.actions.createChecklist',
                )}
                onClick={() => void createChecklist()}
              />
              {hasPendingEdits ? (
                <span className="shrink-0 app-text-caption font-medium text-app-warning-text">
                  {t('coreBusiness.vehicleChecklist.unsavedChanges')}
                </span>
              ) : null}
            </div>
          </div>
        ) : null}
        {selectedChecklist ? (
          activeTab === 'sheet' ? (
            gridDefaultsLoadFailed ? (
              <div
                className="flex flex-1 flex-col items-center justify-center gap-3 px-4 py-12 text-center app-text-body-sm text-app-ink/55"
                role="alert"
              >
                <span>
                  {t('coreBusiness.fieldSettings.errors.columnOrderLoadFailed')}
                </span>
                <button
                  className="app-control h-8 px-3"
                  type="button"
                  onClick={() => void loadGridDefaults()}
                >
                  {t('coreBusiness.grid.preferenceRetry')}
                </button>
              </div>
            ) : (
              <VehicleModuleChecklistGrid
                checklist={selectedChecklist}
                checkEditorOpen={Boolean(checkEditorRecord)}
                defaultColumnOrder={defaultColumnOrder}
                defaultHiddenColumnKeys={defaultHiddenColumnKeys}
                definition={definition}
                editable={checklistEditingEnabled}
                gridPreference={resolvedUserGridPreference}
                gridPreferenceControlsDisabled={userGridPreference.loadFailed}
                gridPreferenceStatus={userGridPreference.status}
                loading={
                  loadingRecords ||
                  gridDefaultsLoading ||
                  userGridPreference.status === 'loading'
                }
                layoutId={checklistGridLayoutId ?? ''}
                records={records}
                toolbarLeading={
                  <LegacyIssueGridToolbarSearch
                    inputId="legacy-issue-module-checklist-search"
                    searchLabel={t(
                      'coreBusiness.vehicleChecklist.actions.search',
                    )}
                    searchPlaceholder={t(
                      'coreBusiness.vehicleChecklist.searchPlaceholder',
                    )}
                    searchValue={query}
                    summary={t('coreBusiness.vehicleChecklist.grid.total', {
                      loaded: records.length,
                      total,
                    })}
                    onSearchChange={setQuery}
                    onSubmit={(event: FormEvent<HTMLFormElement>) => {
                      event.preventDefault();
                      if (hasPendingEdits || attachmentBusy) return;
                      if (query.trim() === submittedQuery.trim()) {
                        void loadRecords();
                      } else {
                        setSubmittedQuery(query);
                      }
                    }}
                  />
                }
                toolbarTrailing={
                  <>
                    <button
                      className="inline-flex h-7 shrink-0 items-center gap-1.5 rounded-md border border-app-border bg-app-bg px-2 app-text-caption font-medium text-app-ink/70 hover:bg-app-surface-hover disabled:cursor-not-allowed disabled:opacity-50"
                      disabled={
                        saving ||
                        attachmentBusy ||
                        !hasPendingEdits ||
                        !canEditSelectedChecklist
                      }
                      type="button"
                      onClick={() => void savePendingEdits()}
                    >
                      {saving ? (
                        <Loader2 size={14} className="animate-spin" />
                      ) : (
                        <Save size={14} />
                      )}
                      {t('coreBusiness.vehicleChecklist.actions.save')}
                    </button>
                    <button
                      aria-pressed={upperControlsCollapsed}
                      className="inline-flex h-7 shrink-0 items-center gap-1.5 rounded-md border border-app-border bg-app-bg px-2 app-text-caption text-app-ink/70 hover:bg-app-surface-hover"
                      title={t(
                        upperControlsCollapsed
                          ? 'coreBusiness.grid.defaultView'
                          : 'coreBusiness.grid.expandGrid',
                      )}
                      type="button"
                      onClick={() =>
                        setUpperControlsCollapsed((current) => !current)
                      }
                    >
                      {upperControlsCollapsed ? (
                        <Minimize2 size={14} />
                      ) : (
                        <Maximize2 size={14} />
                      )}
                      <span>
                        {t(
                          upperControlsCollapsed
                            ? 'coreBusiness.grid.defaultView'
                            : 'coreBusiness.grid.expandGrid',
                        )}
                      </span>
                    </button>
                  </>
                }
                onEditCell={stageCellEdit}
                onEditCells={stageCellBatchEdit}
                onGridPreferenceChange={(preference) =>
                  userGridPreference.updatePreference({
                    column_order: preference.columnOrder,
                    frozen_column_count: preference.frozenColumnCount,
                    hidden_column_keys: preference.hiddenColumnKeys,
                  })
                }
                onGridPreferenceReset={userGridPreference.resetPreference}
                onGridPreferenceRetry={userGridPreference.retry}
                onOpenCheckEditor={(record) =>
                  !saving && !attachmentBusy
                    ? setCheckEditorRecordId(record.id)
                    : undefined
                }
                onVisibleColumnKeysChange={setExcelExportGridLayout}
              />
            )
          ) : (
            <VehicleModuleChecklistHistoryList
              checklist={selectedChecklist}
              items={historyItems}
              loading={loadingHistory}
            />
          )
        ) : (
          <div className="flex flex-1 items-center justify-center px-4 py-12 text-center app-text-body-sm text-app-ink/55">
            {loadingChecklists
              ? t('common:feedback.loading')
              : t('coreBusiness.vehicleChecklist.emptyChecklistForModule')}
          </div>
        )}
      </section>
      {activeTab === 'sheet' && checkEditorRecord ? (
        <VehicleModuleChecklistCheckEditorPanel
          attachmentMutation={attachmentMutation}
          attachmentStatus={attachmentStatus}
          definition={definition}
          downloadingAttachmentId={downloadingAttachmentId}
          editable={Boolean(canEditSelectedChecklist)}
          record={checkEditorRecord}
          saving={saving || loadingRecords || attachmentBusy}
          onApply={applyCheckEditorValues}
          onAttachmentDelete={(attachment) =>
            void deleteChecklistAttachment(checkEditorRecord, attachment)
          }
          onAttachmentDownload={(attachment) =>
            void downloadChecklistAttachment(checkEditorRecord, attachment)
          }
          onAttachmentUpload={(files) =>
            void uploadChecklistAttachments(checkEditorRecord, files)
          }
          onClose={() => setCheckEditorRecordId(null)}
        />
      ) : null}
    </div>
  );
}

export function resolveNextVehicleModuleChecklistId(
  checklists: LegacyIssueVehicleModuleChecklist[],
  deletedChecklistId: string,
): string | null {
  const deletedIndex = checklists.findIndex(
    (checklist) => checklist.id === deletedChecklistId,
  );
  const remaining = checklists.filter(
    (checklist) => checklist.id !== deletedChecklistId,
  );
  if (remaining.length === 0) return null;
  if (deletedIndex < 0) return remaining[0]?.id ?? null;
  return remaining[Math.min(deletedIndex, remaining.length - 1)]?.id ?? null;
}

function ChecklistTabButton({
  active,
  icon,
  label,
  onClick,
}: {
  active: boolean;
  icon: ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={`inline-flex h-9 items-center gap-2 border-b-2 px-2 app-text-body-sm ${
        active
          ? 'border-app-accent font-semibold text-app-accent'
          : 'border-transparent text-app-ink/60 hover:text-app-ink'
      }`}
      aria-pressed={active}
      onClick={onClick}
    >
      {icon}
      {label}
    </button>
  );
}

function VehicleModuleChecklistCheckEditorPanel({
  attachmentMutation,
  attachmentStatus,
  definition,
  downloadingAttachmentId,
  editable,
  onAttachmentDelete,
  onAttachmentDownload,
  onAttachmentUpload,
  onApply,
  onClose,
  record,
  saving,
}: {
  attachmentMutation: ChecklistAttachmentMutation | null;
  attachmentStatus: string | null;
  definition: LegacyIssueDatasetDefinition | null;
  downloadingAttachmentId: string | null;
  editable: boolean;
  onAttachmentDelete: (
    attachment: LegacyIssueVehicleModuleChecklistAttachment,
  ) => void;
  onAttachmentDownload: (
    attachment: LegacyIssueVehicleModuleChecklistAttachment,
  ) => void;
  onAttachmentUpload: (files: FileList | File[]) => void;
  onApply: (params: {
    record: LegacyIssueVehicleModuleChecklistRecord;
    values: Record<VehicleChecklistCheckFieldKey, string | null>;
  }) => void;
  onClose: () => void;
  record: LegacyIssueVehicleModuleChecklistRecord;
  saving: boolean;
}) {
  const { t, i18n } = useTranslation(['apps']);
  const [draftValues, setDraftValues] = useState<
    Record<VehicleChecklistCheckFieldKey, string>
  >(() => createCheckEditorDraft(record.values));

  useEffect(() => {
    setDraftValues(createCheckEditorDraft(record.values));
  }, [record.values]);
  useEffect(() => {
    const closeOnEscape = (event: globalThis.KeyboardEvent) => {
      if (saving || event.key !== 'Escape' || event.defaultPrevented) return;
      const target = event.target;
      if (
        target instanceof HTMLElement &&
        target.closest('[data-ui-floating-layer]')
      ) {
        return;
      }
      onClose();
    };
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [onClose, saving]);

  const fields = useMemo(
    () =>
      CHECK_FIELD_KEYS.map((fieldKey) =>
        vehicleChecklistCheckFieldDefinition(definition, fieldKey, t),
      ),
    [definition, t],
  );
  const dirty = CHECK_FIELD_KEYS.some(
    (fieldKey) =>
      normalizeGridEditValue(draftValues[fieldKey]) !==
      normalizeGridEditValue(
        displayVehicleChecklistFieldValue(record.values[fieldKey]),
      ),
  );

  return (
    <div className="pointer-events-none absolute inset-0 z-[40] flex justify-end">
      <aside
        aria-label={t('coreBusiness.vehicleChecklist.checkEditor.title')}
        className="pointer-events-auto relative z-10 flex h-full w-[min(32rem,92vw)] shrink-0 flex-col border-l border-app-border bg-app-surface shadow-2xl"
        role="dialog"
      >
        <header className="flex items-start justify-between gap-3 border-b border-app-border px-4 py-3">
          <div className="min-w-0">
            <h2 className="truncate app-text-body-sm font-semibold text-app-ink">
              {t('coreBusiness.vehicleChecklist.checkEditor.title')}
            </h2>
            <p className="truncate app-text-caption text-app-ink/50">
              {vehicleChecklistCheckEditorRecordLabel(record, t)}
            </p>
          </div>
          <button
            aria-label={t('coreBusiness.vehicleChecklist.actions.close')}
            className="flex size-8 shrink-0 items-center justify-center rounded-md border border-app-border text-app-ink/60 hover:bg-app-surface-hover hover:text-app-ink"
            disabled={saving}
            type="button"
            onClick={onClose}
          >
            <X size={16} />
          </button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
          <div className="space-y-4">
            <div className="grid gap-2 border-b border-app-border pb-3 app-text-caption text-app-ink/65">
              <div>
                <span className="font-semibold text-app-ink/70">
                  {t('coreBusiness.vehicleChecklist.checkEditor.record')}
                </span>
                <div className="mt-1 text-app-ink">
                  {vehicleChecklistCheckEditorRecordLabel(record, t)}
                </div>
              </div>
            </div>
            {!editable ? (
              <div className="rounded-md border border-app-border bg-app-surface-muted px-3 py-2 app-text-caption text-app-ink/60">
                {t('coreBusiness.vehicleChecklist.checkEditor.readonly')}
              </div>
            ) : null}
            <div className="space-y-3">
              {fields.map((field) => {
                const fieldKey = field.key as VehicleChecklistCheckFieldKey;
                return (
                  <label className="block space-y-1" key={field.key}>
                    <span className="app-text-control-sm font-semibold text-app-ink/70">
                      {vehicleChecklistFieldLabel(field, i18n.language)}
                    </span>
                    {field.options.length > 0 && fieldKey === 'applied' ? (
                      <select
                        className="app-field-input"
                        disabled={!editable || saving}
                        value={draftValues[fieldKey]}
                        onChange={(event) =>
                          setDraftValues((current) => ({
                            ...current,
                            [fieldKey]: event.target.value,
                          }))
                        }
                      >
                        <option value="">
                          {t('coreBusiness.vehicleChecklist.checkEditor.empty')}
                        </option>
                        {field.options.map((option) => (
                          <option key={option} value={option}>
                            {option}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <textarea
                        className="min-h-24 w-full resize-y rounded-md border border-app-border bg-app-bg px-3 py-2 app-text-body-sm text-app-ink outline-none placeholder:text-app-ink/30 focus:border-app-accent disabled:bg-app-surface-muted disabled:text-app-ink/45"
                        disabled={!editable || saving}
                        value={draftValues[fieldKey]}
                        onChange={(event) =>
                          setDraftValues((current) => ({
                            ...current,
                            [fieldKey]: event.target.value,
                          }))
                        }
                      />
                    )}
                  </label>
                );
              })}
            </div>
            <VehicleModuleChecklistAttachmentManager
              attachmentMutation={attachmentMutation}
              attachmentStatus={attachmentStatus}
              downloadingAttachmentId={downloadingAttachmentId}
              editable={editable}
              record={record}
              saving={saving}
              onDelete={onAttachmentDelete}
              onDownload={onAttachmentDownload}
              onUpload={onAttachmentUpload}
            />
          </div>
        </div>
        <footer className="flex items-center justify-end gap-2 border-t border-app-border px-4 py-3">
          <button
            className="inline-flex h-8 items-center rounded-md border border-app-border px-3 app-text-caption text-app-ink/70 hover:bg-app-surface-hover"
            disabled={saving}
            type="button"
            onClick={onClose}
          >
            {t('coreBusiness.vehicleChecklist.actions.close')}
          </button>
          <button
            className="inline-flex h-8 items-center rounded-md bg-app-accent px-3 app-text-caption font-medium text-app-accent-fg hover:bg-app-accent/90 disabled:opacity-50"
            disabled={!editable || saving || !dirty}
            type="button"
            onClick={() =>
              onApply({
                record,
                values: {
                  applied: normalizeGridEditValue(draftValues.applied),
                  check_plan: normalizeGridEditValue(draftValues.check_plan),
                  reflection_result: normalizeGridEditValue(
                    draftValues.reflection_result,
                  ),
                },
              })
            }
          >
            {t('coreBusiness.vehicleChecklist.actions.applyCheckValues')}
          </button>
        </footer>
      </aside>
    </div>
  );
}

function VehicleModuleChecklistAttachmentManager({
  attachmentMutation,
  attachmentStatus,
  downloadingAttachmentId,
  editable,
  onDelete,
  onDownload,
  onUpload,
  record,
  saving,
}: {
  attachmentMutation: ChecklistAttachmentMutation | null;
  attachmentStatus: string | null;
  downloadingAttachmentId: string | null;
  editable: boolean;
  onDelete: (attachment: LegacyIssueVehicleModuleChecklistAttachment) => void;
  onDownload: (attachment: LegacyIssueVehicleModuleChecklistAttachment) => void;
  onUpload: (files: FileList | File[]) => void;
  record: LegacyIssueVehicleModuleChecklistRecord;
  saving: boolean;
}) {
  const { t } = useTranslation(['apps']);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const attachments = record.attachments ?? [];
  const uploading =
    attachmentMutation?.kind === 'upload' &&
    attachmentMutation.recordId === record.id;

  return (
    <section className="space-y-3 border-t border-app-border pt-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <Paperclip size={15} className="shrink-0 text-app-ink/45" />
          <h3 className="truncate app-text-body-sm font-semibold text-app-ink">
            {t('coreBusiness.vehicleChecklist.attachments.title')}
          </h3>
          <span className="shrink-0 rounded-full bg-app-bg px-2 py-0.5 app-text-micro text-app-ink/55">
            {t('coreBusiness.vehicleChecklist.attachments.count', {
              count: attachments.length,
            })}
          </span>
        </div>
        {editable ? (
          <>
            <button
              className="inline-flex h-8 shrink-0 items-center gap-2 rounded-md border border-app-border px-2 app-text-caption text-app-ink/70 hover:bg-app-surface-hover disabled:opacity-45"
              disabled={saving || uploading}
              type="button"
              onClick={() => fileInputRef.current?.click()}
            >
              {uploading ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Upload size={14} />
              )}
              {t('coreBusiness.vehicleChecklist.attachments.upload')}
            </button>
            <input
              ref={fileInputRef}
              aria-label={t('coreBusiness.vehicleChecklist.attachments.upload')}
              className="hidden"
              disabled={saving || uploading}
              multiple
              tabIndex={-1}
              type="file"
              onChange={(event) => {
                if (event.target.files?.length) onUpload(event.target.files);
                event.target.value = '';
              }}
            />
          </>
        ) : null}
      </div>

      {attachmentStatus ? (
        <p
          aria-live="polite"
          className="rounded-md border border-app-accent/20 bg-app-accent/5 px-3 py-2 app-text-caption text-app-ink/65"
          role="status"
        >
          {attachmentStatus}
        </p>
      ) : null}

      {attachments.length === 0 ? (
        <p className="rounded-md border border-dashed border-app-border px-3 py-4 app-text-caption text-app-ink/50">
          {t('coreBusiness.vehicleChecklist.attachments.empty')}
        </p>
      ) : (
        <ul className="space-y-2">
          {attachments.map((attachment) => {
            const deleting =
              attachmentMutation?.kind === 'delete' &&
              attachmentMutation.attachmentId === attachment.id;
            const downloading = downloadingAttachmentId === attachment.id;
            return (
              <li
                key={attachment.id}
                className="flex items-center gap-3 rounded-md border border-app-border bg-app-bg px-3 py-2"
              >
                <FileText
                  aria-hidden="true"
                  size={16}
                  className="shrink-0 text-app-ink/45"
                />
                <div className="min-w-0 flex-1">
                  <p className="truncate app-text-caption font-medium text-app-ink">
                    {attachment.filename}
                  </p>
                  <p className="truncate app-text-micro text-app-ink/45">
                    {formatByteSize(attachment.size_bytes)} ·{' '}
                    {attachment.content_type}
                  </p>
                </div>
                <button
                  aria-label={t(
                    'coreBusiness.vehicleChecklist.attachments.downloadFile',
                    { filename: attachment.filename },
                  )}
                  className="flex size-8 shrink-0 items-center justify-center rounded-md border border-app-border text-app-ink/60 hover:bg-app-surface-hover disabled:opacity-45"
                  disabled={Boolean(downloadingAttachmentId)}
                  title={t(
                    'coreBusiness.vehicleChecklist.attachments.downloadFile',
                    { filename: attachment.filename },
                  )}
                  type="button"
                  onClick={() => onDownload(attachment)}
                >
                  {downloading ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : (
                    <Download size={14} />
                  )}
                </button>
                {editable ? (
                  <button
                    aria-label={t(
                      'coreBusiness.vehicleChecklist.attachments.deleteFile',
                      { filename: attachment.filename },
                    )}
                    className="flex size-8 shrink-0 items-center justify-center rounded-md border border-app-border text-app-danger hover:bg-app-danger/5 disabled:opacity-45"
                    disabled={saving || Boolean(attachmentMutation)}
                    title={t(
                      'coreBusiness.vehicleChecklist.attachments.deleteFile',
                      { filename: attachment.filename },
                    )}
                    type="button"
                    onClick={() => onDelete(attachment)}
                  >
                    {deleting ? (
                      <Loader2 size={14} className="animate-spin" />
                    ) : (
                      <Trash2 size={14} />
                    )}
                  </button>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function VehicleModuleChecklistGrid({
  checklist,
  checkEditorOpen,
  defaultColumnOrder,
  defaultHiddenColumnKeys,
  definition,
  editable,
  gridPreference,
  gridPreferenceControlsDisabled,
  gridPreferenceStatus,
  layoutId,
  loading,
  onEditCell,
  onEditCells,
  onGridPreferenceChange,
  onGridPreferenceReset,
  onGridPreferenceRetry,
  onOpenCheckEditor,
  onVisibleColumnKeysChange,
  records,
  toolbarLeading,
  toolbarTrailing,
}: {
  checklist: LegacyIssueVehicleModuleChecklist;
  checkEditorOpen: boolean;
  defaultColumnOrder: string[];
  defaultHiddenColumnKeys: string[];
  definition: LegacyIssueDatasetDefinition | null;
  editable: boolean;
  gridPreference: LegacyIssueGridPreferenceValue | null | undefined;
  gridPreferenceControlsDisabled: boolean;
  gridPreferenceStatus: LegacyIssueGridPreferenceStatus;
  layoutId: string;
  loading: boolean;
  onEditCell: (params: {
    columnKey: string;
    record: LegacyIssueVehicleModuleChecklistRecord;
    value: string | null;
  }) => void;
  onEditCells: (params: {
    edits: Array<{
      columnKey: string;
      record: LegacyIssueVehicleModuleChecklistRecord;
      value: string | null;
    }>;
  }) => void;
  onGridPreferenceChange: (preference: LegacyIssueGridPreferenceValue) => void;
  onGridPreferenceReset: () => void;
  onGridPreferenceRetry: () => void;
  onOpenCheckEditor: (record: LegacyIssueVehicleModuleChecklistRecord) => void;
  onVisibleColumnKeysChange: (layout: LegacyIssueGridColumnLayout) => void;
  records: LegacyIssueVehicleModuleChecklistRecord[];
  toolbarLeading?: ReactNode;
  toolbarTrailing?: ReactNode;
}) {
  const { t, i18n } = useTranslation(['apps', 'common']);
  const defaultHiddenColumnKeySet = useMemo(
    () => new Set(defaultHiddenColumnKeys),
    [defaultHiddenColumnKeys],
  );
  const columns = useMemo<LegacyIssueGridColumn[]>(() => {
    const groupLabels = i18n.language.startsWith('ko')
      ? (definition?.group_labels_ko ?? {})
      : (definition?.group_labels_en ?? {});
    const nextColumns: LegacyIssueGridColumn[] = (definition?.fields ?? []).map(
      (field) => ({
        allowMultiple: field.allow_multiple,
        group: field.group_key ? groupLabels[field.group_key] : undefined,
        inputKind: field.field_type === 'date' ? 'date' : undefined,
        key: field.key,
        options:
          field.field_type === 'select' && !field.allow_multiple
            ? field.options
            : undefined,
        required: field.required,
        title: i18n.language.startsWith('ko') ? field.label_ko : field.label_en,
        width: vehicleChecklistColumnWidth(field.key),
      }),
    );
    const checkAttachmentColumn: LegacyIssueGridColumn = {
      group: groupLabels.check,
      key: CHECK_ATTACHMENT_COLUMN_KEY,
      title: t('coreBusiness.vehicleChecklist.attachments.column'),
      width: vehicleChecklistColumnWidth(CHECK_ATTACHMENT_COLUMN_KEY),
    };
    const reflectionResultIndex = nextColumns.findIndex(
      (column) => column.key === 'reflection_result',
    );
    nextColumns.splice(
      reflectionResultIndex >= 0
        ? reflectionResultIndex + 1
        : nextColumns.length,
      0,
      checkAttachmentColumn,
    );
    return nextColumns.filter(
      (column) => !defaultHiddenColumnKeySet.has(column.key),
    );
  }, [defaultHiddenColumnKeySet, definition, i18n.language, t]);
  const readonlyColumnKeys = useMemo(
    () =>
      editable
        ? columns
            .filter((column) => !CHECK_FIELD_KEY_SET.has(column.key))
            .map((column) => column.key)
        : columns.map((column) => column.key),
    [columns, editable],
  );
  const highlightedColumnKeys = useMemo(
    () =>
      editable ? [...CHECK_FIELD_KEYS, CHECK_ATTACHMENT_COLUMN_KEY] : undefined,
    [editable],
  );
  const getCellValue = useCallback(
    (record: LegacyIssueVehicleModuleChecklistRecord, columnKey: string) => {
      if (columnKey === CHECK_ATTACHMENT_COLUMN_KEY) {
        const attachments = record.attachments ?? [];
        const firstAttachment = attachments[0];
        return firstAttachment
          ? t('coreBusiness.vehicleChecklist.attachments.gridSummary', {
              count: attachments.length,
              filename: firstAttachment.filename,
            })
          : null;
      }
      return displayVehicleChecklistFieldValue(record.values[columnKey]);
    },
    [t],
  );

  return (
    <LegacyIssueDataGrid
      columns={columns}
      defaultColumnOrder={defaultColumnOrder}
      detailOpen={false}
      emptyLabel={t('coreBusiness.vehicleChecklist.grid.empty')}
      getCellValue={getCellValue}
      highlightedColumnKeys={highlightedColumnKeys}
      layoutId={layoutId}
      loading={loading}
      loadingLabel={t('common:feedback.loading')}
      onCellBatchEdit={editable ? onEditCells : undefined}
      onCellClick={({ columnKey, record }) => {
        if (columnKey === CHECK_ATTACHMENT_COLUMN_KEY) {
          onOpenCheckEditor(record);
          return true;
        }
        if (checkEditorOpen) onOpenCheckEditor(record);
        return false;
      }}
      onCellEdit={editable ? onEditCell : undefined}
      onPreferenceChange={onGridPreferenceChange}
      onPreferenceReset={onGridPreferenceReset}
      onPreferenceRetry={onGridPreferenceRetry}
      onRecordOpen={onOpenCheckEditor}
      onVisibleColumnKeysChange={onVisibleColumnKeysChange}
      readonlyColumnKeys={readonlyColumnKeys}
      recordOpenIcon={<Eye size={14} />}
      recordOpenLabel={t('coreBusiness.vehicleChecklist.checkEditor.title')}
      records={records}
      revisionKey={`${checklist.id}:${checklist.updated_at}`}
      preference={gridPreference}
      preferenceControlsDisabled={gridPreferenceControlsDisabled}
      preferenceStatus={gridPreferenceStatus}
      toolbarLeading={toolbarLeading}
      toolbarTrailing={toolbarTrailing}
    />
  );
}

function VehicleModuleChecklistHistoryList({
  checklist,
  items,
  loading,
}: {
  checklist: LegacyIssueVehicleModuleChecklist;
  items: LegacyIssueVehicleChecklistHistoryItem[];
  loading: boolean;
}) {
  const { t } = useTranslation(['apps']);
  return (
    <div className="min-h-0 flex-1 overflow-auto">
      <table className="w-full border-collapse app-text-body-sm">
        <thead className="sticky top-0 bg-app-surface-sidebar text-left app-text-caption text-app-ink/55">
          <tr className="border-b border-app-border">
            <th className="px-4 py-2 font-semibold">
              {t('coreBusiness.vehicleChecklist.history.record')}
            </th>
            <th className="px-4 py-2 font-semibold">
              {t('coreBusiness.vehicleChecklist.history.action')}
            </th>
            <th className="px-4 py-2 font-semibold">
              {t('coreBusiness.vehicleChecklist.history.field')}
            </th>
            <th className="px-4 py-2 font-semibold">
              {t('coreBusiness.vehicleChecklist.history.before')}
            </th>
            <th className="px-4 py-2 font-semibold">
              {t('coreBusiness.vehicleChecklist.history.after')}
            </th>
            <th className="px-4 py-2 font-semibold">
              {t('coreBusiness.vehicleChecklist.history.actor')}
            </th>
            <th className="px-4 py-2 font-semibold">
              {t('coreBusiness.vehicleChecklist.history.changedAt')}
            </th>
          </tr>
        </thead>
        <tbody>
          {loading ? (
            <HistoryMessage
              message={t('coreBusiness.vehicleChecklist.history.loading')}
            />
          ) : items.length === 0 ? (
            <HistoryMessage
              message={t('coreBusiness.vehicleChecklist.history.empty')}
            />
          ) : (
            items.map((item) => (
              <tr key={item.id} className="border-b border-app-border">
                <td className="max-w-96 px-4 py-2">
                  <div className="truncate font-medium text-app-ink">
                    {vehicleChecklistHistoryRecordLabel(item, checklist, t)}
                  </div>
                </td>
                <td className="px-4 py-2 text-app-ink/70">
                  {t(
                    `coreBusiness.vehicleChecklist.history.actions.${item.action}`,
                    {
                      defaultValue: item.action,
                    },
                  )}
                </td>
                <td className="px-4 py-2 text-app-ink/70">
                  {item.field_key === 'status'
                    ? t('coreBusiness.vehicleChecklist.history.statusField')
                    : item.field_key === 'attachment'
                      ? t('coreBusiness.vehicleChecklist.attachments.column')
                      : (item.field_label ?? item.field_key ?? '-')}
                </td>
                <td className="max-w-80 px-4 py-2 text-app-ink/60">
                  <span className="line-clamp-2">
                    {vehicleChecklistHistoryValue(item.old_value, item, t)}
                  </span>
                </td>
                <td className="max-w-80 px-4 py-2 text-app-ink/80">
                  <span className="line-clamp-2">
                    {vehicleChecklistHistoryValue(item.new_value, item, t)}
                  </span>
                </td>
                <td className="px-4 py-2 text-app-ink/60">
                  {item.actor_name ||
                    item.actor_email ||
                    t('coreBusiness.vehicleChecklist.history.unknownActor')}
                </td>
                <td className="px-4 py-2 text-app-ink/60">
                  <UserDateTime value={item.created_at} display="datetime" />
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

function HistoryMessage({ message }: { message: string }) {
  return (
    <tr>
      <td className="px-4 py-6 text-app-ink/55" colSpan={7}>
        {message}
      </td>
    </tr>
  );
}

function sameModuleChecklistScope(
  current: ModuleChecklistRouteScope,
  expected: ModuleChecklistRouteScope,
): boolean {
  return (
    current.workspaceSlug === expected.workspaceSlug &&
    current.vehicleModelId === expected.vehicleModelId &&
    current.stageId === expected.stageId &&
    current.moduleKey === expected.moduleKey
  );
}

function vehicleChecklistHistoryRecordLabel(
  item: LegacyIssueVehicleChecklistHistoryItem,
  checklist: LegacyIssueVehicleModuleChecklist,
  t: ReturnType<typeof useTranslation>['t'],
): string {
  if (item.field_key === 'status') {
    return t('coreBusiness.vehicleChecklist.history.masterRevision', {
      revision:
        item.source_master_revision_no ??
        checklist.source_master_revision_no ??
        '-',
    });
  }
  return (
    item.record_label ||
    t('coreBusiness.vehicleChecklist.history.checklistStatus')
  );
}

function vehicleChecklistHistoryValue(
  value: string | null,
  item: LegacyIssueVehicleChecklistHistoryItem,
  t: ReturnType<typeof useTranslation>['t'],
): string {
  if (!value) return t('coreBusiness.vehicleChecklist.history.emptyValue');
  if (item.field_key === 'status') {
    return t(`coreBusiness.vehicleChecklist.revisionStatus.${value}`, {
      defaultValue: value,
    });
  }
  return value;
}

type VehicleChecklistCheckEditorField = Pick<
  LegacyIssueDatasetField,
  'key' | 'label_ko' | 'label_en' | 'options'
>;

function createCheckEditorDraft(
  values: Record<string, LegacyIssueFieldValue> | null | undefined,
): Record<VehicleChecklistCheckFieldKey, string> {
  return {
    applied: displayVehicleChecklistFieldValue(values?.applied) ?? '',
    check_plan: displayVehicleChecklistFieldValue(values?.check_plan) ?? '',
    reflection_result:
      displayVehicleChecklistFieldValue(values?.reflection_result) ?? '',
  };
}

function vehicleChecklistCheckFieldDefinition(
  definition: LegacyIssueDatasetDefinition | null,
  fieldKey: VehicleChecklistCheckFieldKey,
  t: ReturnType<typeof useTranslation>['t'],
): VehicleChecklistCheckEditorField {
  const field = definition?.fields.find((item) => item.key === fieldKey);
  if (field) return field;
  return {
    key: fieldKey,
    label_en: fallbackVehicleChecklistCheckFieldLabel(fieldKey, 'en', t),
    label_ko: fallbackVehicleChecklistCheckFieldLabel(fieldKey, 'ko', t),
    options: [],
  };
}

const VEHICLE_CHECKLIST_CHECK_FIELD_LABEL_KEYS = {
  applied: 'coreBusiness.vehicleChecklist.checkEditor.fields.applied',
  check_plan: 'coreBusiness.vehicleChecklist.checkEditor.fields.checkPlan',
  reflection_result:
    'coreBusiness.vehicleChecklist.checkEditor.fields.reflectionResult',
} as const;

function fallbackVehicleChecklistCheckFieldLabel(
  fieldKey: VehicleChecklistCheckFieldKey,
  locale: 'ko' | 'en',
  t: ReturnType<typeof useTranslation>['t'],
): string {
  return t(VEHICLE_CHECKLIST_CHECK_FIELD_LABEL_KEYS[fieldKey], {
    lng: locale === 'ko' ? 'ko-KR' : 'en-US',
  });
}

function vehicleChecklistFieldLabel(
  field: VehicleChecklistCheckEditorField,
  language: string,
): string {
  return language.startsWith('ko') ? field.label_ko : field.label_en;
}

function vehicleChecklistCheckEditorRecordLabel(
  record: LegacyIssueVehicleModuleChecklistRecord,
  t: ReturnType<typeof useTranslation>['t'],
): string {
  const issueNumber = displayVehicleChecklistFieldValue(
    record.values.legacy_issue_number,
  );
  const symptom =
    displayVehicleChecklistFieldValue(record.values.symptom) ||
    displayVehicleChecklistFieldValue(record.values.problem);
  if (issueNumber && symptom) return `${issueNumber} · ${symptom}`;
  return (
    issueNumber ||
    symptom ||
    record.source_stable_record_id ||
    record.source_record_id ||
    t('coreBusiness.vehicleChecklist.checkEditor.emptyRecord')
  );
}

function normalizeGridEditValue(value: string | null): string | null {
  const normalized = value?.trim() ?? '';
  return normalized || null;
}

function mergeVehicleChecklistValues(
  current: Record<string, LegacyIssueFieldValue>,
  patch: Record<string, LegacyIssueFieldValue | null>,
): Record<string, LegacyIssueFieldValue> {
  const next = { ...current };
  for (const [key, value] of Object.entries(patch)) {
    if (value === null || value === '') delete next[key];
    else next[key] = value;
  }
  return next;
}

function displayVehicleChecklistFieldValue(
  value: LegacyIssueFieldValue | null | undefined,
): string | null {
  if (value === null || value === undefined) return null;
  if (Array.isArray(value)) {
    return value
      .map((item) => displayVehicleChecklistFieldValue(item))
      .filter((item): item is string => Boolean(item))
      .join('; ');
  }
  if (typeof value === 'object') {
    return value.label || value.path || value.email || value.id;
  }
  return String(value);
}

function vehicleChecklistColumnWidth(key: string): number {
  if (key === CHECK_ATTACHMENT_COLUMN_KEY) return 220;
  if (key === 'symptom' || key === 'cause' || key === 'countermeasure') {
    return 260;
  }
  if (key === 'check_plan' || key === 'reflection_result') return 240;
  if (key === 'legacy_issue_number' || key === 'vehicle_model') return 180;
  return 150;
}

export function mergeVehicleChecklistRecordAttachments(
  records: LegacyIssueVehicleModuleChecklistRecord[],
  recordId: string,
  checklistId: string,
  attachments: LegacyIssueVehicleModuleChecklistAttachment[],
): LegacyIssueVehicleModuleChecklistRecord[] {
  const matchingAttachments = attachments.filter(
    (attachment) =>
      attachment.checklist_id === checklistId &&
      attachment.record_id === recordId,
  );
  if (matchingAttachments.length === 0) return records;
  return records.map((record) => {
    if (record.id !== recordId || record.checklist_id !== checklistId) {
      return record;
    }
    const attachmentById = new Map(
      (record.attachments ?? []).map((attachment) => [
        attachment.id,
        attachment,
      ]),
    );
    for (const attachment of matchingAttachments) {
      attachmentById.set(attachment.id, attachment);
    }
    return { ...record, attachments: Array.from(attachmentById.values()) };
  });
}

export function removeVehicleChecklistRecordAttachment(
  records: LegacyIssueVehicleModuleChecklistRecord[],
  recordId: string,
  checklistId: string,
  attachmentId: string,
): LegacyIssueVehicleModuleChecklistRecord[] {
  return records.map((record) =>
    record.id === recordId && record.checklist_id === checklistId
      ? {
          ...record,
          attachments: (record.attachments ?? []).filter(
            (attachment) => attachment.id !== attachmentId,
          ),
        }
      : record,
  );
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}
