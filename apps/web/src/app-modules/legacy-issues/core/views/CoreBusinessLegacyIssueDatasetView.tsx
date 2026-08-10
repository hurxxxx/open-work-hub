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
import { useParams, useSearchParams } from 'react-router-dom';
import {
  Bell,
  ChevronDown,
  CheckCircle2,
  Download,
  FileText,
  GitCompareArrows,
  Loader2,
  Maximize2,
  Minimize2,
  Paperclip,
  Pencil,
  Plus,
  RefreshCw,
  Save,
  Search,
  Star,
  Trash2,
  Upload,
  X,
} from 'lucide-react';
import { Dialog, useConfirm, useToast } from '@ai-do/ui';

import { cn } from '@/src/lib/utils';
import { searchDmUsers, type DmUser } from '@/src/app-modules/dm';
import { ApiRequestError } from '@/src/platform/api/client';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { hasAnySystemRole } from '@/src/platform/auth/auth-api';
import { downloadBlobAsFile } from '@/src/platform/browser/browser-download';
import { formatByteSize } from '@/src/platform/format/byte-size';
import { formatNativeDateInputValue } from '@/src/platform/time/native-date-input';
import { UserOptionRow } from '@/src/platform/users/UserSearchMultiSelect';
import { selectUserOptionsForPicker } from '@/src/platform/users/user-option-picker-model';
import {
  LEGACY_ISSUE_DEFAULT_VIEW_KEY,
  LEGACY_ISSUE_VIEWS,
  type LegacyIssueViewDefinition,
  type LegacyIssueViewKey,
} from '../legacy-issue-datasets';
import {
  cancelLegacyIssueDatasetRevision,
  completeLegacyIssueDatasetRevisionApproval,
  completeLegacyIssueDatasetRevisionReview,
  compareLegacyIssueDatasetRevisions,
  createLegacyIssueDatasetExcelExport,
  createLegacyIssueDatasetDraftRevision,
  createLegacyIssueRevisionOverviewHistory,
  deleteLegacyIssueDatasetAttachment,
  deleteLegacyIssueDatasetRecord,
  deleteLegacyIssueRevisionOverviewHistory,
  fetchLegacyIssueExcelExportFile,
  fetchLegacyIssueExcelExportJob,
  fetchLegacyIssueColumnOrder,
  fetchLegacyIssueDatasetAttachmentBlob,
  fetchLegacyIssueDatasetDefinition,
  fetchLegacyIssueDatasetRecordHistory,
  fetchLegacyIssueDatasetRecords,
  fetchLegacyIssueDatasetRevisions,
  searchLegacyIssueOrgUnits,
  importLegacyIssueDatasetRecords,
  hideLegacyIssueRevisionFromOverviewHistory,
  publishLegacyIssueDatasetRevision,
  previewLegacyIssueDatasetImport,
  retryLegacyIssueDatasetAttachmentIndex,
  requestLegacyIssueDatasetRevisionApproval,
  restoreLegacyIssueDatasetRevision,
  releaseLegacyIssueDatasetDraftEditing,
  saveLegacyIssueDatasetRecordBatch,
  setLegacyIssueDatasetAttachmentPrimary,
  updateLegacyIssueDatasetRevisionAssignees,
  updateLegacyIssueRevisionOverviewHistory,
  updateLegacyIssueDatasetRecord,
  updateLegacyIssueDatasetAttachment,
  uploadLegacyIssueDatasetAttachment,
  type LegacyIssueDatasetAttachment,
  type LegacyIssueDatasetRecordBatchCreate,
  type LegacyIssueDatasetRecordBatchCreated,
  type LegacyIssueDatasetRecordBatchUpdate,
  type LegacyIssueDatasetDefinition,
  type LegacyIssueDatasetField,
  type LegacyIssueFieldValue,
  type LegacyIssueOrgUnitItem,
  type LegacyIssueReferenceValue,
  type LegacyIssueDatasetImportPreview,
  type LegacyIssueDatasetKey,
  type LegacyIssueDatasetRecord,
  type LegacyIssueDatasetRecordHistoryItem,
  type LegacyIssueRevision,
  type LegacyIssueRevisionCompareResponse,
  type LegacyIssueRevisionContext,
  type LegacyIssueRevisionEvent,
  type LegacyIssueRevisionOverviewHistory,
  type LegacyIssueRevisionOverviewHistoryUpdate,
} from '../api/legacy-issue-api';
import {
  legacyIssueExcelExportErrorKey,
  useLegacyIssueExcelExportJob,
} from './useLegacyIssueExcelExportJob';
import { LegacyIssueExcelExportControls } from './LegacyIssueExcelExportControls';
import {
  LegacyIssueDataGrid,
  legacyIssueGridCellKey,
  type LegacyIssueGridColumn,
  type LegacyIssueGridColumnLayout,
  type LegacyIssueGridPreferenceStatus,
  type LegacyIssueGridPreferenceValue,
  type LegacyIssueGridRowLayout,
  type LegacyIssueGridReferenceKind,
} from './LegacyIssueDataGrid';
import { LegacyIssueImportFileButton } from './LegacyIssueImportFileButton';
import { LegacyIssueImportMappingDialog } from './LegacyIssueImportMappingDialog';
import { LegacyIssueHistoryList } from './LegacyIssueHistoryList';
import {
  LegacyIssueRevisionMeetingAttachmentsPanel,
  LegacyIssueRevisionMeetingMinutes,
} from './LegacyIssueRevisionMeetingMinutes';
import {
  LegacyIssueRevisionBar,
  LegacyIssueRevisionCompareModal,
  isVisibleLegacyIssueRevision,
} from './LegacyIssueRevisionBar';
import {
  LegacyIssueGridToolbarSearch,
  LegacyIssuePageHeader,
  LegacyIssueToolbarButton,
} from './LegacyIssuePageParts';
import { useLegacyIssueGridPreference } from './useLegacyIssueGridPreference';

type PanelMode = 'create' | 'edit';
type DetailPanelTab = 'data' | 'attachments' | 'history';
export type LegacyIssueMainTab = 'sheet' | 'overview' | 'minutes';
type RevisionComparePair = {
  leftRevisionId: string;
  rightRevisionId: string;
};
type DraftCompareCacheEntry = {
  error: unknown | null;
  errorToastShown: boolean;
  request: Promise<LegacyIssueRevisionCompareResponse | null>;
};

const ATTACHMENT_DESCRIPTION_MAX_LENGTH = 500;
const BLANK_ROW_BATCH_SIZE = 1;
const EXCEL_EXPORT_RECORD_LIMIT = 100_000;
const INTRODUCED_REVISION_FIELD_KEY = 'introduced_revision_no';
const PENDING_CREATE_RECORD_PREFIX = 'pending-legacy-issue-create-';
const NEW_OVERVIEW_HISTORY_ROW_ID = 'new-overview-history-row';
const MAX_OVERVIEW_REVISION_NO = 2_147_483_647;

type LegacyIssueEditableValue = LegacyIssueFieldValue | null;

type LegacyIssueReferencePickerState = {
  field: LegacyIssueDatasetField;
  record: LegacyIssueDatasetRecord;
} | null;

export type PendingRecordEdits = Record<
  string,
  Record<string, LegacyIssueEditableValue>
>;

type PendingAttachmentDraftStatus = 'pending' | 'uploading' | 'failed';

export type PendingAttachmentDraft = {
  description: string;
  error: string | null;
  file: File;
  id: string;
  status: PendingAttachmentDraftStatus;
};

export type PendingAttachmentDraftsByRecordId = Record<
  string,
  PendingAttachmentDraft[]
>;

export type PendingAttachmentEdits = {
  deletedAttachmentIds: string[];
  descriptions: Record<string, string | null>;
  primaryAttachmentId?: string;
};

export type PendingAttachmentEditsByRecordId = Record<
  string,
  PendingAttachmentEdits
>;

export function CoreBusinessLegacyIssueDatasetView({
  datasetKey,
  viewKey = LEGACY_ISSUE_DEFAULT_VIEW_KEY,
}: {
  datasetKey: LegacyIssueDatasetKey;
  viewKey?: LegacyIssueViewKey;
}) {
  const { workspaceSlug = '' } = useParams<{ workspaceSlug: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const { token, user } = useAuth();
  const { t, i18n } = useTranslation(['apps', 'common', 'shell']);
  const { confirm, confirmDialog } = useConfirm();
  const toast = useToast();
  const userGridPreference = useLegacyIssueGridPreference({
    gridKey: viewKey,
    gridKind: 'dataset',
    onLoadError: () => {
      toast.error(t('coreBusiness.grid.preferenceLoadFailed'));
    },
    onSaveError: () => {
      toast.error(t('coreBusiness.grid.preferenceSaveFailed'));
    },
    token,
    workspaceSlug,
  });
  const [definition, setDefinition] =
    useState<LegacyIssueDatasetDefinition | null>(null);
  const [records, setRecords] = useState<LegacyIssueDatasetRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [query, setQuery] = useState('');
  const [appliedQuery, setAppliedQuery] = useState('');
  const [upperControlsCollapsed, setUpperControlsCollapsed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [definitionRefreshing, setDefinitionRefreshing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [selectedRecord, setSelectedRecord] =
    useState<LegacyIssueDatasetRecord | null>(null);
  const selectedRecordRef = useRef<LegacyIssueDatasetRecord | null>(null);
  const [panelMode, setPanelMode] = useState<PanelMode>('edit');
  const [draft, setDraft] = useState<Record<string, LegacyIssueEditableValue>>(
    {},
  );
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importPreview, setImportPreview] =
    useState<LegacyIssueDatasetImportPreview | null>(null);
  const [importMapping, setImportMapping] = useState<Record<string, number>>(
    {},
  );
  const [importPreviewing, setImportPreviewing] = useState(false);
  const [busyAttachmentId, setBusyAttachmentId] = useState<string | null>(null);
  const [historyItems, setHistoryItems] = useState<
    LegacyIssueDatasetRecordHistoryItem[]
  >([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [revisionContext, setRevisionContext] =
    useState<LegacyIssueRevisionContext | null>(null);
  const [revisions, setRevisions] = useState<LegacyIssueRevision[]>([]);
  const [revisionEvents, setRevisionEvents] = useState<
    LegacyIssueRevisionEvent[]
  >([]);
  const [revisionOverviewHistory, setRevisionOverviewHistory] = useState<
    LegacyIssueRevisionOverviewHistory[]
  >([]);
  const [selectedRevisionId, setSelectedRevisionId] = useState<string | null>(
    null,
  );
  const [revisionBusy, setRevisionBusy] = useState(false);
  const [compareResult, setCompareResult] =
    useState<LegacyIssueRevisionCompareResponse | null>(null);
  const [compareBusy, setCompareBusy] = useState(false);
  const [overviewComparePair, setOverviewComparePair] =
    useState<RevisionComparePair | null>(null);
  const [defaultColumnOrder, setDefaultColumnOrder] = useState<string[]>([]);
  const [defaultHiddenColumnKeys, setDefaultHiddenColumnKeys] = useState<
    string[]
  >([]);
  const [excelExportGridLayout, setExcelExportGridLayout] =
    useState<LegacyIssueGridColumnLayout | null>(null);
  const [excelExportRowLayout, setExcelExportRowLayout] =
    useState<LegacyIssueGridRowLayout | null>(null);
  const [blankRowCount, setBlankRowCount] = useState(0);
  const [pendingRecordEdits, setPendingRecordEdits] =
    useState<PendingRecordEdits>({});
  const [pendingCreateRecords, setPendingCreateRecords] = useState<
    LegacyIssueDatasetRecord[]
  >([]);
  const [
    pendingAttachmentDraftsByRecordId,
    setPendingAttachmentDraftsByRecordId,
  ] = useState<PendingAttachmentDraftsByRecordId>({});
  const [
    pendingAttachmentEditsByRecordId,
    setPendingAttachmentEditsByRecordId,
  ] = useState<PendingAttachmentEditsByRecordId>({});
  const [draftSaveVersion, setDraftSaveVersion] = useState(0);
  const [draftChangedCellKeys, setDraftChangedCellKeys] = useState<string[]>(
    [],
  );
  const [draftSaving, setDraftSaving] = useState(false);
  const pendingCreateIdRef = useRef(0);
  const pendingAttachmentIdRef = useRef(0);
  const baseRecordValuesRef = useRef<
    Record<string, Record<string, LegacyIssueFieldValue>>
  >({});
  const pendingRecordEditsRef = useRef<PendingRecordEdits>({});
  const pendingCreateRecordsRef = useRef<LegacyIssueDatasetRecord[]>([]);
  const pendingAttachmentDraftsRef = useRef<PendingAttachmentDraftsByRecordId>(
    {},
  );
  const pendingAttachmentEditsRef = useRef<PendingAttachmentEditsByRecordId>(
    {},
  );
  const draftCompareCacheRef = useRef<Map<string, DraftCompareCacheEntry>>(
    new Map(),
  );
  const draftCompareHydrationIdRef = useRef(0);
  const definitionRequestIdRef = useRef(0);
  const autoDraftSelectionAttemptedRef = useRef(false);
  const viewDefinition = LEGACY_ISSUE_VIEWS[viewKey];
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
  const isAggregateView = viewKey === LEGACY_ISSUE_DEFAULT_VIEW_KEY;
  const initialDraftValues = useMemo<Record<string, LegacyIssueEditableValue>>(
    () => ({}),
    [],
  );

  const localizedDefinition = useMemo(() => {
    if (!definition) return null;
    return resolveLegacyIssueLocalizedDefinition({
      definition,
      isKorean: i18n.language.startsWith('ko'),
      translate: t,
      viewDefinition,
      viewKey,
    });
  }, [definition, i18n.language, t, viewDefinition, viewKey]);
  const currentRevision = revisionContext?.current ?? null;
  const activeDraft = revisionContext?.active_draft ?? null;
  const activeTab = resolveLegacyIssueMainTab({
    isAggregateView,
    tab: searchParams.get('tab'),
  });
  const setActiveTab = useCallback(
    (tab: LegacyIssueMainTab) => {
      const next = legacyIssueMainTabSearchParams(searchParams, tab);
      setSearchParams(next, { replace: true });
    },
    [searchParams, setSearchParams],
  );
  useEffect(() => {
    setUpperControlsCollapsed(false);
  }, [activeTab, viewKey]);
  const isDraftRevision = currentRevision?.status === 'draft';
  const revisionOverviewRows = useMemo(
    () =>
      buildLegacyIssueRevisionOverviewRows(revisions, revisionOverviewHistory),
    [revisionOverviewHistory, revisions],
  );
  const isPlatformAdmin = hasAnySystemRole(user, ['platform_admin']);
  const canEditCurrentDraftRevision = canEditLegacyIssueDraftRevision({
    currentUserId: user?.id ?? null,
    revision: currentRevision,
  });
  const canDirectEditPublishedRevision =
    canDirectEditLegacyIssuePublishedRevision({
      activeDraft,
      canDirectEditPublishedRevision:
        revisionContext?.can_direct_edit_published_revision ?? false,
      currentRevision,
      isAggregateView,
      latestPublishedRevision: revisionContext?.latest_published ?? null,
    });
  const canEditCurrentRevision = canApplyLegacyIssueInlineCellEdits({
    canDirectEditPublishedRevision,
    canEditCurrentDraftRevision,
  });
  const canEditActiveDraftRevision = canEditLegacyIssueDraftRevision({
    currentUserId: user?.id ?? null,
    revision: activeDraft,
  });
  const canForceCancelActiveDraftRevision =
    canForceCancelLegacyIssueDraftRevision({
      activeDraftId: activeDraft?.id ?? null,
      canForceCancelActiveDraft:
        revisionContext?.can_force_cancel_active_draft ?? false,
      currentUserId: user?.id ?? null,
      revision: activeDraft,
    });
  const blankRowDefaultValues = useMemo<Record<string, string | null>>(() => {
    return buildLegacyIssueBlankRowDefaultValues({
      currentRevisionNo: currentRevision?.revision_no ?? null,
      isDraftRevision,
      latestPublishedRevisionNo:
        revisionContext?.latest_published?.revision_no ?? null,
    });
  }, [
    currentRevision?.revision_no,
    isDraftRevision,
    revisionContext?.latest_published?.revision_no,
  ]);
  const canEditAttachmentsInRevision = canEditLegacyIssueAttachmentsInRevision({
    canDirectEditPublishedRevision,
    canEditCurrentDraftRevision,
  });
  const hasPendingDraftChanges = hasLegacyIssuePendingDraftChanges({
    pendingAttachmentEditsByRecordId,
    pendingAttachmentDraftsByRecordId,
    pendingCreateRecords,
    pendingRecordEdits,
  });
  const pendingDraftChangeCount = countLegacyIssuePendingDraftChanges({
    pendingAttachmentEditsByRecordId,
    pendingAttachmentDraftsByRecordId,
    pendingCreateRecords,
    pendingRecordEdits,
  });
  const excelExportColumnKeys =
    excelExportGridLayout?.layoutId === viewDefinition.gridLayoutId
      ? excelExportGridLayout.columnKeys.filter(
          (columnKey) => columnKey !== 'primary_attachment',
        )
      : null;
  const excelExportRecordIds =
    excelExportRowLayout?.layoutId === viewDefinition.gridLayoutId
      ? appliedQuery || excelExportRowLayout.viewApplied
        ? excelExportRowLayout.recordIds
            .filter((recordId) => !isPendingCreateRecordId(recordId))
            .slice(0, EXCEL_EXPORT_RECORD_LIMIT)
        : null
      : undefined;
  const excelExport = useLegacyIssueExcelExportJob({
    createJob: async (includeAttachments) => {
      if (
        !token ||
        !workspaceSlug ||
        !currentRevision ||
        excelExportColumnKeys === null ||
        excelExportRecordIds === undefined
      ) {
        throw new Error();
      }
      return createLegacyIssueDatasetExcelExport({
        columnKeys: excelExportColumnKeys,
        datasetKey,
        departments: [],
        includeAttachments,
        recordIds: excelExportRecordIds,
        revisionId: currentRevision.id,
        token,
        viewKey,
        workspaceSlug,
      });
    },
    fallbackFilename: `legacy-issue-${viewKey}.xlsx`,
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
    sourceKey: currentRevision
      ? `dataset:${datasetKey}:${viewKey}:${currentRevision.id}`
      : null,
    userId: user?.id,
    workspaceSlug,
  });

  useEffect(() => {
    pendingRecordEditsRef.current = pendingRecordEdits;
    pendingCreateRecordsRef.current = pendingCreateRecords;
    pendingAttachmentDraftsRef.current = pendingAttachmentDraftsByRecordId;
    pendingAttachmentEditsRef.current = pendingAttachmentEditsByRecordId;
  }, [
    pendingAttachmentEditsByRecordId,
    pendingAttachmentDraftsByRecordId,
    pendingCreateRecords,
    pendingRecordEdits,
  ]);

  const refreshDefinition = useCallback(async () => {
    if (!workspaceSlug || !token) return null;
    const requestId = ++definitionRequestIdRef.current;
    setDefinitionRefreshing(true);
    try {
      const response = await fetchLegacyIssueDatasetDefinition({
        datasetKey,
        token,
        viewKey,
        workspaceSlug,
      });
      if (definitionRequestIdRef.current !== requestId) return null;
      setDefinition(response);
      return response;
    } catch (refreshError) {
      if (definitionRequestIdRef.current === requestId) {
        toast.error(
          errorMessage(
            refreshError,
            t('coreBusiness.module.errors.loadFailed'),
          ),
        );
      }
      return null;
    } finally {
      if (definitionRequestIdRef.current === requestId) {
        setDefinitionRefreshing(false);
      }
    }
  }, [datasetKey, t, toast, token, viewKey, workspaceSlug]);

  const loadRecords = useCallback(async (): Promise<
    LegacyIssueDatasetRecord[]
  > => {
    if (!workspaceSlug || !token) return [];
    setLoading(true);
    const draftCompareHydrationId = ++draftCompareHydrationIdRef.current;
    try {
      const [recordResponse, columnOrderResponse] = await Promise.all([
        fetchLegacyIssueDatasetRecords({
          datasetKey,
          query,
          revisionId: isAggregateView ? null : selectedRevisionId,
          token,
          viewKey,
          workspaceSlug,
        }),
        fetchLegacyIssueColumnOrder({
          token,
          viewKey,
          workspaceSlug,
        }),
      ]);
      if (draftCompareHydrationId !== draftCompareHydrationIdRef.current) {
        return [];
      }
      const revisionResponse = isAggregateView
        ? { items: [], events: [], overview_history: [] }
        : await fetchLegacyIssueDatasetRevisions({
            datasetKey,
            token,
            viewKey,
            workspaceSlug,
          });
      if (draftCompareHydrationId !== draftCompareHydrationIdRef.current) {
        return [];
      }
      const displayRecords = applyPendingDraftChangesToLoadedRecords({
        records: recordResponse.items,
        pendingCreateRecords: pendingCreateRecordsRef.current,
        pendingRecordEdits: pendingRecordEditsRef.current,
      });
      const loadedRevision = recordResponse.revision.current;
      setRecords(displayRecords);
      setTotal(recordResponse.total + pendingCreateRecordsRef.current.length);
      setAppliedQuery(query.trim());
      setRevisionContext(recordResponse.revision);
      setRevisions(revisionResponse.items);
      setRevisionEvents(revisionResponse.events);
      setRevisionOverviewHistory(revisionResponse.overview_history);
      setDefaultColumnOrder((current) =>
        preserveStringArrayReferenceWhenEqual(
          current,
          columnOrderResponse.column_order,
        ),
      );
      setDefaultHiddenColumnKeys((current) =>
        preserveStringArrayReferenceWhenEqual(
          current,
          columnOrderResponse.hidden_column_keys ?? [],
        ),
      );
      const syncedRecord = resolveLegacyIssueSelectedRecordForRecords(
        displayRecords,
        selectedRecordRef.current,
      );
      if (selectedRecordRef.current) {
        selectedRecordRef.current = syncedRecord;
        setSelectedRecord(syncedRecord);
        setDraft(syncedRecord?.values ?? {});
        if (!syncedRecord) {
          setHistoryItems([]);
        }
      }
      setLoading(false);
      if (
        loadedRevision.status === 'draft' &&
        loadedRevision.base_revision_id
      ) {
        const compareCacheKey = `${loadedRevision.base_revision_id}:${loadedRevision.id}:${loadedRevision.updated_at}`;
        let compareCacheEntry =
          draftCompareCacheRef.current.get(compareCacheKey);
        if (!compareCacheEntry) {
          compareCacheEntry = {
            error: null,
            errorToastShown: false,
            request: Promise.resolve(null),
          };
          const nextCompareCacheEntry = compareCacheEntry;
          nextCompareCacheEntry.request = compareLegacyIssueDatasetRevisions({
            leftRevisionId: loadedRevision.base_revision_id,
            datasetKey,
            rightRevisionId: loadedRevision.id,
            token,
            viewKey,
            workspaceSlug,
          }).catch((compareError: unknown) => {
            nextCompareCacheEntry.error = compareError;
            return null;
          });
          draftCompareCacheRef.current.set(compareCacheKey, compareCacheEntry);
        }
        void compareCacheEntry.request.then((persistedCompare) => {
          if (draftCompareHydrationId !== draftCompareHydrationIdRef.current) {
            return;
          }
          if (!persistedCompare && !compareCacheEntry.errorToastShown) {
            compareCacheEntry.errorToastShown = true;
            toast.error(
              errorMessage(
                compareCacheEntry.error,
                t('coreBusiness.module.errors.changedCellsLoadFailed'),
              ),
            );
          }
          if (persistedCompare) {
            setDraftChangedCellKeys(
              buildLegacyIssueDraftChangedCellKeys({
                compareResult: persistedCompare,
                records: displayRecords,
              }),
            );
          }
        });
      } else {
        if (draftCompareHydrationId === draftCompareHydrationIdRef.current) {
          setDraftChangedCellKeys([]);
        }
      }
      return displayRecords;
    } catch (loadError) {
      toast.error(
        errorMessage(loadError, t('coreBusiness.module.errors.loadFailed')),
      );
      return [];
    } finally {
      if (draftCompareHydrationId === draftCompareHydrationIdRef.current) {
        setLoading(false);
      }
    }
  }, [
    datasetKey,
    isAggregateView,
    query,
    selectedRevisionId,
    t,
    toast,
    token,
    viewKey,
    workspaceSlug,
  ]);

  useEffect(() => {
    void loadRecords();
  }, [loadRecords]);

  useEffect(() => {
    void refreshDefinition();
    return () => {
      definitionRequestIdRef.current += 1;
    };
  }, [refreshDefinition]);

  useEffect(() => {
    const handleWindowFocus = () => {
      if (document.visibilityState === 'visible') {
        void refreshDefinition();
      }
    };
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        void refreshDefinition();
      }
    };
    window.addEventListener('focus', handleWindowFocus);
    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => {
      window.removeEventListener('focus', handleWindowFocus);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [refreshDefinition]);

  useEffect(() => {
    autoDraftSelectionAttemptedRef.current = false;
  }, [datasetKey, viewKey, workspaceSlug]);

  useEffect(() => {
    if (isAggregateView && searchParams.has('revision_id')) {
      const next = new URLSearchParams(searchParams);
      next.delete('revision_id');
      next.delete('tab');
      setSearchParams(next, { replace: true });
      setSelectedRevisionId(null);
      return;
    }
    const revisionId = searchParams.get('revision_id');
    if (!revisionId || revisionId === selectedRevisionId) return;
    if (hasPendingDraftChanges || saving || draftSaving) {
      const next = new URLSearchParams(searchParams);
      if (selectedRevisionId) {
        next.set('revision_id', selectedRevisionId);
      } else {
        next.delete('revision_id');
      }
      setSearchParams(next, { replace: true });
      return;
    }
    setSelectedRevisionId(revisionId);
    setCompareResult(null);
  }, [
    draftSaving,
    hasPendingDraftChanges,
    isAggregateView,
    saving,
    searchParams,
    selectedRevisionId,
    setSearchParams,
  ]);

  useEffect(() => {
    if (!revisionContext) return;
    if (searchParams.get('revision_id')) return;
    const autoSelectionAttempted = autoDraftSelectionAttemptedRef.current;
    const nextRevisionId = resolveLegacyIssueAutoSelectedRevisionId({
      activeDraftId: revisionContext?.active_draft?.id ?? null,
      autoSelectionAttempted,
      selectedRevisionId,
    });
    autoDraftSelectionAttemptedRef.current = true;
    if (!nextRevisionId || nextRevisionId === selectedRevisionId) return;
    setSelectedRevisionId(nextRevisionId);
    setCompareResult(null);
  }, [revisionContext, searchParams, selectedRevisionId]);

  useEffect(() => {
    setBlankRowCount(0);
    setPendingRecordEdits({});
    setPendingCreateRecords([]);
    setPendingAttachmentDraftsByRecordId({});
    setPendingAttachmentEditsByRecordId({});
    setDraftChangedCellKeys([]);
    pendingRecordEditsRef.current = {};
    pendingCreateRecordsRef.current = [];
    pendingAttachmentDraftsRef.current = {};
    pendingAttachmentEditsRef.current = {};
    baseRecordValuesRef.current = {};
    setDraftSaveVersion((current) => current + 1);
  }, [selectedRevisionId, viewKey]);

  const loadRecordHistory = useCallback(
    async (recordId: string | null = selectedRecord?.id ?? null) => {
      if (!workspaceSlug || !token || !recordId) {
        setHistoryItems([]);
        return;
      }
      setHistoryLoading(true);
      try {
        const response = await fetchLegacyIssueDatasetRecordHistory({
          datasetKey,
          recordId,
          token,
          viewKey,
          workspaceSlug,
        });
        setHistoryItems(response.items);
      } catch {
        setHistoryItems([]);
      } finally {
        setHistoryLoading(false);
      }
    },
    [datasetKey, selectedRecord?.id, token, viewKey, workspaceSlug],
  );

  useEffect(() => {
    if (
      panelMode === 'edit' &&
      selectedRecord &&
      !isPendingCreateRecordId(selectedRecord.id)
    ) {
      void loadRecordHistory(selectedRecord.id);
      return;
    }
    setHistoryItems([]);
  }, [loadRecordHistory, panelMode, selectedRecord]);

  function openCreatePanel() {
    if (!canEditCurrentRevision) return;
    setActiveTab('sheet');
    setPanelMode('create');
    selectedRecordRef.current = null;
    setSelectedRecord(null);
    setDraft({ ...initialDraftValues, ...blankRowDefaultValues });
  }

  function openEditPanel(record: LegacyIssueDatasetRecord) {
    setPanelMode('edit');
    selectedRecordRef.current = record;
    setSelectedRecord(record);
    setDraft(record.values);
  }

  function clearPendingDraftChanges({
    clearAttachments = true,
    clearAttachmentEdits = true,
  }: {
    clearAttachments?: boolean;
    clearAttachmentEdits?: boolean;
  } = {}) {
    setPendingRecordEdits({});
    setPendingCreateRecords([]);
    pendingRecordEditsRef.current = {};
    pendingCreateRecordsRef.current = [];
    if (clearAttachments) {
      setPendingAttachmentDraftsByRecordId({});
      pendingAttachmentDraftsRef.current = {};
    }
    if (clearAttachmentEdits) {
      setPendingAttachmentEditsByRecordId({});
      pendingAttachmentEditsRef.current = {};
    }
    baseRecordValuesRef.current = {};
    setDraftSaveVersion((current) => current + 1);
  }

  function appendDraftChangedCellKeys(cellKeys: readonly string[]) {
    if (!isDraftRevision || cellKeys.length === 0) return;
    setDraftChangedCellKeys((current) => [
      ...new Set([...current, ...cellKeys]),
    ]);
  }

  function markSavedAttachmentRecords(recordIds: Iterable<string>) {
    appendDraftChangedCellKeys(
      [...recordIds].map((recordId) =>
        legacyIssueGridCellKey(recordId, 'primary_attachment'),
      ),
    );
  }

  function createPendingDraftRecord(
    values: Record<string, LegacyIssueEditableValue>,
  ): LegacyIssueDatasetRecord {
    const id = `${PENDING_CREATE_RECORD_PREFIX}${Date.now()}-${pendingCreateIdRef.current++}`;
    const now = new Date().toISOString();
    return {
      attachments: [],
      created_at: now,
      id,
      imported_at: null,
      imported_source_filename: null,
      module_key: viewKey === LEGACY_ISSUE_DEFAULT_VIEW_KEY ? null : viewKey,
      primary_attachment: null,
      raw_fields: {},
      revision_id: currentRevision?.id ?? null,
      stable_record_id: id,
      updated_at: now,
      values: normalizeLegacyIssueEditableRecordValues(
        mergeLegacyIssueRecordValues(
          { ...initialDraftValues, ...blankRowDefaultValues },
          values,
        ),
      ),
    };
  }

  function removePendingCreateRecordIds(recordIds: string[]) {
    if (recordIds.length === 0) return;
    const recordIdSet = new Set(recordIds);
    setPendingAttachmentDraftsByRecordId((current) =>
      omitPendingAttachmentDrafts(current, recordIdSet),
    );
    pendingAttachmentDraftsRef.current = omitPendingAttachmentDrafts(
      pendingAttachmentDraftsRef.current,
      recordIdSet,
    );
    setPendingCreateRecords((current) => {
      const next = current.filter((record) => !recordIdSet.has(record.id));
      pendingCreateRecordsRef.current = next;
      return next;
    });
    setRecords((current) =>
      current.filter((record) => !recordIdSet.has(record.id)),
    );
    setTotal((current) => Math.max(0, current - recordIdSet.size));
  }

  function applyInlineCellEdits({
    edits,
  }: {
    edits: Array<{
      columnKey: string;
      record: LegacyIssueDatasetRecord;
      value: LegacyIssueEditableValue;
    }>;
  }) {
    if (!workspaceSlug || !token || !currentRevision || !canEditCurrentRevision)
      return;
    const patchesByRecordId = new Map<
      string,
      Record<string, LegacyIssueEditableValue>
    >();
    const recordsById = new Map(records.map((record) => [record.id, record]));
    for (const edit of edits) {
      if (edit.columnKey === 'primary_attachment') continue;
      const recordId = edit.record.id;
      const patch = patchesByRecordId.get(recordId) ?? {};
      patch[edit.columnKey] = normalizeLegacyIssueEditableCellValue(
        edit.columnKey,
        edit.value,
      );
      patchesByRecordId.set(recordId, patch);
      if (
        !isPendingCreateRecordId(recordId) &&
        !baseRecordValuesRef.current[recordId]
      ) {
        baseRecordValuesRef.current[recordId] = {
          ...(recordsById.get(recordId)?.values ?? edit.record.values),
        };
      }
    }
    if (patchesByRecordId.size === 0) return;
    setRecords((current) =>
      current.map((record) => {
        const patch = patchesByRecordId.get(record.id);
        return patch ? applyLegacyIssueRecordValuePatch(record, patch) : record;
      }),
    );
    setPendingCreateRecords((current) => {
      const next = current.map((record) => {
        const patch = patchesByRecordId.get(record.id);
        return patch ? applyLegacyIssueRecordValuePatch(record, patch) : record;
      });
      pendingCreateRecordsRef.current = next;
      return next;
    });
    setPendingRecordEdits((current) => {
      const next = { ...current };
      for (const [recordId, patch] of patchesByRecordId.entries()) {
        if (isPendingCreateRecordId(recordId)) continue;
        const nextPatch = mergePendingRecordEditPatch({
          baseValues: baseRecordValuesRef.current[recordId] ?? {},
          currentPatch: next[recordId] ?? {},
          patch,
        });
        if (Object.keys(nextPatch).length > 0) {
          next[recordId] = nextPatch;
        } else {
          delete next[recordId];
          delete baseRecordValuesRef.current[recordId];
        }
      }
      pendingRecordEditsRef.current = next;
      return next;
    });
    const selectedId = selectedRecordRef.current?.id;
    const selectedPatch = selectedId
      ? patchesByRecordId.get(selectedId)
      : undefined;
    if (selectedId && selectedPatch && selectedRecordRef.current) {
      const nextSelected = applyLegacyIssueRecordValuePatch(
        selectedRecordRef.current,
        selectedPatch,
      );
      selectedRecordRef.current = nextSelected;
      setSelectedRecord((current) =>
        current?.id === selectedId ? nextSelected : current,
      );
      setDraft(nextSelected.values);
    }
  }

  function saveInlineCell({
    columnKey,
    record,
    value,
  }: {
    columnKey: string;
    record: LegacyIssueDatasetRecord;
    value: string | null;
  }) {
    applyInlineCellEdits({
      edits: [{ columnKey, record, value }],
    });
  }

  function saveInlineCells({
    edits,
  }: {
    edits: Array<{
      columnKey: string;
      record: LegacyIssueDatasetRecord;
      value: LegacyIssueEditableValue;
    }>;
  }) {
    applyInlineCellEdits({ edits });
  }

  function stagePendingAttachments(recordId: string, files: File[]) {
    if (files.length === 0) return;
    const drafts = files.map<PendingAttachmentDraft>((file) => ({
      description: '',
      error: null,
      file,
      id: `pending-legacy-issue-attachment-${Date.now()}-${pendingAttachmentIdRef.current++}`,
      status: 'pending',
    }));
    setPendingAttachmentDraftsByRecordId((current) => {
      const next = {
        ...current,
        [recordId]: [...(current[recordId] ?? []), ...drafts],
      };
      pendingAttachmentDraftsRef.current = next;
      return next;
    });
  }

  function updatePendingAttachmentDescription({
    attachmentId,
    description,
    recordId,
  }: {
    attachmentId: string;
    description: string;
    recordId: string;
  }) {
    setPendingAttachmentDraftsByRecordId((current) => {
      const next = updatePendingAttachmentDraft(
        current,
        recordId,
        attachmentId,
        (draft) => ({ ...draft, description }),
      );
      pendingAttachmentDraftsRef.current = next;
      return next;
    });
  }

  function removePendingAttachmentDraft({
    attachmentId,
    recordId,
  }: {
    attachmentId: string;
    recordId: string;
  }) {
    setPendingAttachmentDraftsByRecordId((current) => {
      const next = updatePendingAttachmentDraftsForRecord(
        current,
        recordId,
        (drafts) => drafts.filter((draft) => draft.id !== attachmentId),
      );
      pendingAttachmentDraftsRef.current = next;
      return next;
    });
  }

  function updatePendingAttachmentEditsForSelectedRecord(
    updater: (current: PendingAttachmentEdits) => PendingAttachmentEdits,
  ) {
    const recordId = selectedRecordRef.current?.id;
    if (!recordId || isPendingCreateRecordId(recordId)) return;
    setPendingAttachmentEditsByRecordId((current) => {
      const next = updatePendingAttachmentEditsForRecord(
        current,
        recordId,
        updater,
      );
      pendingAttachmentEditsRef.current = next;
      return next;
    });
  }

  async function uploadPendingAttachmentDrafts({
    createdRecords,
    draftsByRecordId,
  }: {
    createdRecords: LegacyIssueDatasetRecordBatchCreated[];
    draftsByRecordId: PendingAttachmentDraftsByRecordId;
  }): Promise<PendingAttachmentDraftsByRecordId> {
    if (!workspaceSlug || !token) return draftsByRecordId;
    const createdRecordByClientId =
      mapLegacyIssueCreatedRecordsByClientId(createdRecords);
    const failedDraftsByRecordId: PendingAttachmentDraftsByRecordId = {};
    const entries = Object.entries(draftsByRecordId).filter(
      ([, drafts]) => drafts.length > 0,
    );
    if (entries.length === 0) return failedDraftsByRecordId;

    setUploading(true);
    try {
      for (const [clientRecordId, drafts] of entries) {
        const createdRecord = createdRecordByClientId.get(clientRecordId);
        const targetRecordId = createdRecord?.id ?? clientRecordId;
        const sourceRecord =
          createdRecord ??
          records.find((record) => record.id === clientRecordId) ??
          (selectedRecordRef.current?.id === clientRecordId
            ? selectedRecordRef.current
            : null);
        const deletedAttachmentIds = new Set(
          pendingAttachmentEditsRef.current[clientRecordId]
            ?.deletedAttachmentIds ?? [],
        );
        let primaryAttachmentAvailable = Boolean(
          sourceRecord?.attachments.some(
            (attachment) => !deletedAttachmentIds.has(attachment.id),
          ),
        );
        setPendingAttachmentDraftsByRecordId((current) => {
          const next = updatePendingAttachmentDraftsForRecord(
            current,
            clientRecordId,
            (items) =>
              items.map((draft) => ({
                ...draft,
                error: null,
                status: 'uploading',
              })),
          );
          pendingAttachmentDraftsRef.current = next;
          return next;
        });

        for (const draft of drafts) {
          try {
            await uploadLegacyIssueDatasetAttachment({
              description: normalizeAttachmentDescription(draft.description),
              file: draft.file,
              isPrimary: !primaryAttachmentAvailable,
              datasetKey,
              recordId: targetRecordId,
              token,
              workspaceSlug,
            });
            primaryAttachmentAvailable = true;
          } catch (uploadError) {
            failedDraftsByRecordId[targetRecordId] = [
              ...(failedDraftsByRecordId[targetRecordId] ?? []),
              {
                ...draft,
                error: errorMessage(
                  uploadError,
                  t('coreBusiness.module.errors.attachmentUploadFailed'),
                ),
                status: 'failed',
              },
            ];
          }
        }
      }
    } finally {
      setUploading(false);
    }
    return failedDraftsByRecordId;
  }

  async function savePendingAttachmentEdits({
    blockedRecordIds = new Set<string>(),
    editsByRecordId,
  }: {
    blockedRecordIds?: ReadonlySet<string>;
    editsByRecordId: PendingAttachmentEditsByRecordId;
  }): Promise<{
    error: string | null;
    failedEditsByRecordId: PendingAttachmentEditsByRecordId;
  }> {
    if (!workspaceSlug || !token) {
      return {
        error: t('coreBusiness.module.errors.draftSaveFailed'),
        failedEditsByRecordId: editsByRecordId,
      };
    }
    let error: string | null = null;
    let failedEditsByRecordId: PendingAttachmentEditsByRecordId = {};
    const retainFailedEdit = (
      recordId: string,
      updater: (current: PendingAttachmentEdits) => PendingAttachmentEdits,
    ) => {
      failedEditsByRecordId = updatePendingAttachmentEditsForRecord(
        failedEditsByRecordId,
        recordId,
        updater,
      );
    };

    for (const [recordId, edits] of Object.entries(editsByRecordId)) {
      if (blockedRecordIds.has(recordId)) {
        failedEditsByRecordId = replacePendingAttachmentEditsForRecord(
          failedEditsByRecordId,
          recordId,
          edits,
        );
        continue;
      }
      const deletedAttachmentIds = new Set(edits.deletedAttachmentIds);
      for (const [attachmentId, description] of Object.entries(
        edits.descriptions,
      )) {
        if (deletedAttachmentIds.has(attachmentId)) continue;
        setBusyAttachmentId(attachmentId);
        try {
          await updateLegacyIssueDatasetAttachment({
            attachmentId,
            description,
            datasetKey,
            token,
            workspaceSlug,
          });
        } catch (descriptionError) {
          if (isMissingAttachmentError(descriptionError)) continue;
          error ??= errorMessage(
            descriptionError,
            t('coreBusiness.module.errors.attachmentDescriptionFailed'),
          );
          retainFailedEdit(recordId, (current) => ({
            ...current,
            descriptions: {
              ...current.descriptions,
              [attachmentId]: description,
            },
          }));
        }
      }

      if (
        edits.primaryAttachmentId &&
        !deletedAttachmentIds.has(edits.primaryAttachmentId)
      ) {
        setBusyAttachmentId(edits.primaryAttachmentId);
        try {
          await setLegacyIssueDatasetAttachmentPrimary({
            attachmentId: edits.primaryAttachmentId,
            datasetKey,
            token,
            workspaceSlug,
          });
        } catch (primaryError) {
          if (!isMissingAttachmentError(primaryError)) {
            error ??= errorMessage(
              primaryError,
              t('coreBusiness.module.errors.attachmentPrimaryFailed'),
            );
            retainFailedEdit(recordId, (current) => ({
              ...current,
              primaryAttachmentId: edits.primaryAttachmentId,
            }));
          }
        }
      }

      for (const attachmentId of edits.deletedAttachmentIds) {
        setBusyAttachmentId(attachmentId);
        try {
          await deleteLegacyIssueDatasetAttachment({
            attachmentId,
            datasetKey,
            token,
            workspaceSlug,
          });
        } catch (deleteError) {
          if (isMissingAttachmentError(deleteError)) continue;
          error ??= errorMessage(
            deleteError,
            t('coreBusiness.module.errors.attachmentDeleteFailed'),
          );
          retainFailedEdit(recordId, (current) => ({
            ...current,
            deletedAttachmentIds: [
              ...current.deletedAttachmentIds,
              attachmentId,
            ],
          }));
        }
      }
    }
    setBusyAttachmentId(null);
    return { error, failedEditsByRecordId };
  }

  async function savePendingDraftChanges() {
    if (
      !workspaceSlug ||
      !token ||
      !currentRevision ||
      !canEditCurrentRevision ||
      draftSaving ||
      saving
    )
      return;
    const payload = buildLegacyIssueDraftBatchPayload({
      pendingCreateRecords,
      pendingRecordEdits,
    });
    const pendingAttachmentDrafts = pendingAttachmentDraftsRef.current;
    const pendingAttachmentEdits = pendingAttachmentEditsRef.current;
    const hasPendingAttachmentChanges =
      countPendingAttachmentDrafts(pendingAttachmentDrafts) > 0 ||
      countPendingAttachmentEdits(pendingAttachmentEdits) > 0;
    const releaseWithRecordBatch =
      isDraftRevision && !hasPendingAttachmentChanges;
    setDraftSaving(true);
    try {
      const response =
        payload.creates.length > 0 ||
        payload.updates.length > 0 ||
        releaseWithRecordBatch
          ? await saveLegacyIssueDatasetRecordBatch({
              creates: payload.creates,
              datasetKey,
              releaseEditing: releaseWithRecordBatch,
              revisionId: currentRevision.id,
              token,
              updates: payload.updates,
              viewKey,
              workspaceSlug,
            })
          : null;
      const failedAttachmentDrafts = await uploadPendingAttachmentDrafts({
        createdRecords: response?.created_records ?? [],
        draftsByRecordId: pendingAttachmentDrafts,
      });
      const { error: attachmentEditError, failedEditsByRecordId } =
        await savePendingAttachmentEdits({
          blockedRecordIds: new Set(Object.keys(failedAttachmentDrafts)),
          editsByRecordId: pendingAttachmentEdits,
        });
      const selectedId = selectedRecordRef.current?.id;
      const createdRecordByClientId = mapLegacyIssueCreatedRecordsByClientId(
        response?.created_records ?? [],
      );
      const savedAttachmentRecordIds = new Set<string>();
      for (const [clientRecordId, drafts] of Object.entries(
        pendingAttachmentDrafts,
      )) {
        const targetRecordId =
          createdRecordByClientId.get(clientRecordId)?.id ?? clientRecordId;
        if (
          drafts.length > (failedAttachmentDrafts[targetRecordId]?.length ?? 0)
        ) {
          savedAttachmentRecordIds.add(targetRecordId);
        }
      }
      for (const [recordId, edits] of Object.entries(pendingAttachmentEdits)) {
        const failedEdits = failedEditsByRecordId[recordId];
        if (
          countPendingAttachmentEdits({ [recordId]: edits }) >
          countPendingAttachmentEdits(
            failedEdits ? { [recordId]: failedEdits } : {},
          )
        ) {
          savedAttachmentRecordIds.add(recordId);
        }
      }
      appendDraftChangedCellKeys([
        ...payload.updates.flatMap((update) =>
          Object.keys(update.values).map((fieldKey) =>
            legacyIssueGridCellKey(update.record_id, fieldKey),
          ),
        ),
        ...(response?.created_records ?? []).flatMap(({ record }) =>
          Object.keys(record.values).map((fieldKey) =>
            legacyIssueGridCellKey(record.id, fieldKey),
          ),
        ),
        ...[...savedAttachmentRecordIds].map((recordId) =>
          legacyIssueGridCellKey(recordId, 'primary_attachment'),
        ),
      ]);
      clearPendingDraftChanges({
        clearAttachments: false,
        clearAttachmentEdits: false,
      });
      setPendingAttachmentDraftsByRecordId(failedAttachmentDrafts);
      pendingAttachmentDraftsRef.current = failedAttachmentDrafts;
      setPendingAttachmentEditsByRecordId(failedEditsByRecordId);
      pendingAttachmentEditsRef.current = failedEditsByRecordId;

      const hasFailedAttachmentChanges =
        countPendingAttachmentDrafts(failedAttachmentDrafts) > 0 ||
        countPendingAttachmentEdits(failedEditsByRecordId) > 0;
      let editingReleased = releaseWithRecordBatch;
      if (
        !hasFailedAttachmentChanges &&
        isDraftRevision &&
        !releaseWithRecordBatch
      ) {
        await releaseLegacyIssueDatasetDraftEditing({
          datasetKey,
          revisionId: currentRevision.id,
          token,
          viewKey,
          workspaceSlug,
        });
        editingReleased = true;
      }
      if (editingReleased) {
        const unlockedRevision = {
          ...currentRevision,
          locked_by_id: null,
          locked_by_name: null,
        };
        setRevisions((current) =>
          upsertLegacyIssueRevision(current, unlockedRevision),
        );
        setRevisionContext((current) =>
          current
            ? {
                ...current,
                active_draft:
                  current.active_draft?.id === unlockedRevision.id
                    ? unlockedRevision
                    : current.active_draft,
                current:
                  current.current.id === unlockedRevision.id
                    ? unlockedRevision
                    : current.current,
              }
            : current,
        );
      }

      draftCompareCacheRef.current.clear();
      const latestRecords = await loadRecords();
      const remappedSelectedRecordId =
        selectedId && createdRecordByClientId.has(selectedId)
          ? createdRecordByClientId.get(selectedId)?.id
          : selectedId;
      if (remappedSelectedRecordId) {
        const refreshed = latestRecords.find(
          (record) => record.id === remappedSelectedRecordId,
        );
        if (refreshed) {
          selectedRecordRef.current = refreshed;
          setSelectedRecord(refreshed);
          setDraft(refreshed.values);
        }
      }

      if (hasFailedAttachmentChanges) {
        toast.error(
          attachmentEditError ??
            t('coreBusiness.module.errors.attachmentUploadPartialFailed'),
        );
      } else {
        toast.success(
          t(
            canDirectEditPublishedRevision
              ? 'coreBusiness.module.directSave.saved'
              : 'coreBusiness.module.draftSave.saved',
          ),
        );
      }
    } catch (saveError) {
      const invalidField = resolveLegacyIssueInvalidField({
        error: saveError,
        fields: definition?.fields ?? [],
      });
      toast.error(
        invalidField
          ? t('coreBusiness.module.errors.invalidFieldValue', {
              field: i18n.language.startsWith('ko')
                ? invalidField.label_ko
                : invalidField.label_en,
            })
          : errorMessage(
              saveError,
              t('coreBusiness.module.errors.draftSaveFailed'),
            ),
      );
    } finally {
      setDraftSaving(false);
    }
  }

  async function createInlineRecords({
    values,
  }: {
    values: Array<Record<string, string | null>>;
  }): Promise<number> {
    if (!workspaceSlug || !token || !currentRevision || !canEditCurrentRevision)
      return 0;
    const createdRecords = values.map((rowValues) =>
      createPendingDraftRecord(rowValues),
    );
    if (createdRecords.length > 0) {
      setPendingCreateRecords((current) => {
        const next = [...createdRecords, ...current];
        pendingCreateRecordsRef.current = next;
        return next;
      });
      setRecords((current) => [...createdRecords, ...current]);
      setTotal((current) => current + createdRecords.length);
      setBlankRowCount((current) =>
        Math.max(0, current - createdRecords.length),
      );
    }
    return createdRecords.length;
  }

  function closePanel() {
    setPanelMode('edit');
    selectedRecordRef.current = null;
    setSelectedRecord(null);
    setDraft(initialDraftValues);
  }

  async function saveSelectedRecordAttachments() {
    if (
      !workspaceSlug ||
      !token ||
      !selectedRecord ||
      !canEditAttachmentsInRevision ||
      saving ||
      draftSaving
    )
      return;
    if (isPendingCreateRecordId(selectedRecord.id)) {
      await savePendingDraftChanges();
      return;
    }
    const recordId = selectedRecord.id;
    const draftsByRecordId = pendingAttachmentDraftsRef.current[recordId]
      ? {
          [recordId]: pendingAttachmentDraftsRef.current[recordId],
        }
      : {};
    const editsByRecordId = pendingAttachmentEditsRef.current[recordId]
      ? { [recordId]: pendingAttachmentEditsRef.current[recordId] }
      : {};
    if (
      countPendingAttachmentDrafts(draftsByRecordId) === 0 &&
      countPendingAttachmentEdits(editsByRecordId) === 0
    )
      return;

    setSaving(true);
    try {
      const failedAttachmentDrafts = await uploadPendingAttachmentDrafts({
        createdRecords: [],
        draftsByRecordId,
      });
      const { error: attachmentEditError, failedEditsByRecordId } =
        await savePendingAttachmentEdits({
          blockedRecordIds: new Set(Object.keys(failedAttachmentDrafts)),
          editsByRecordId,
        });
      if (
        countPendingAttachmentDrafts(draftsByRecordId) +
          countPendingAttachmentEdits(editsByRecordId) >
        countPendingAttachmentDrafts(failedAttachmentDrafts) +
          countPendingAttachmentEdits(failedEditsByRecordId)
      ) {
        markSavedAttachmentRecords([recordId]);
      }
      const nextAttachmentDrafts = replacePendingAttachmentDraftsForRecord(
        pendingAttachmentDraftsRef.current,
        recordId,
        failedAttachmentDrafts[recordId] ?? [],
      );
      const nextAttachmentEdits = replacePendingAttachmentEditsForRecord(
        pendingAttachmentEditsRef.current,
        recordId,
        failedEditsByRecordId[recordId],
      );
      pendingAttachmentDraftsRef.current = nextAttachmentDrafts;
      pendingAttachmentEditsRef.current = nextAttachmentEdits;
      setPendingAttachmentDraftsByRecordId(nextAttachmentDrafts);
      setPendingAttachmentEditsByRecordId(nextAttachmentEdits);
      draftCompareCacheRef.current.clear();
      await refreshSelectedRecord(recordId);
      await loadRecordHistory(recordId);

      if (
        countPendingAttachmentDrafts(failedAttachmentDrafts) > 0 ||
        countPendingAttachmentEdits(failedEditsByRecordId) > 0
      ) {
        toast.error(
          attachmentEditError ??
            t('coreBusiness.module.errors.attachmentUploadPartialFailed'),
        );
      } else {
        toast.success(
          t(
            canDirectEditPublishedRevision
              ? 'coreBusiness.module.directSave.saved'
              : 'coreBusiness.module.attachmentSave.saved',
          ),
        );
      }
    } catch (saveError) {
      toast.error(
        errorMessage(saveError, t('coreBusiness.module.errors.saveFailed')),
      );
    } finally {
      setSaving(false);
    }
  }

  async function saveRecord(event: FormEvent) {
    event.preventDefault();
    if (!workspaceSlug || !token || !currentRevision || !canEditCurrentRevision)
      return;
    setSaving(true);
    try {
      if (
        canDirectEditPublishedRevision &&
        panelMode === 'edit' &&
        selectedRecord &&
        !isPendingCreateRecordId(selectedRecord.id)
      ) {
        await updateLegacyIssueDatasetRecord({
          datasetKey,
          recordId: selectedRecord.id,
          revisionId: currentRevision.id,
          token,
          values: draft,
          viewKey,
          workspaceSlug,
        });
        await loadRecords();
        toast.success(t('coreBusiness.module.directSave.saved'));
        return;
      }
      if (panelMode === 'create') {
        const values = mergeLegacyIssueRecordValues(initialDraftValues, draft);
        if (Object.keys(values).length === 0) {
          toast.error(t('coreBusiness.module.errors.saveFailed'));
          return;
        }
        const saved = createPendingDraftRecord(values);
        setPendingCreateRecords((current) => {
          const next = [saved, ...current];
          pendingCreateRecordsRef.current = next;
          return next;
        });
        setRecords((current) => [saved, ...current]);
        setTotal((current) => current + 1);
        selectedRecordRef.current = saved;
        setSelectedRecord(saved);
        setDraft(saved.values);
        setPanelMode('edit');
        return;
      }
      if (!selectedRecord) return;
      applyInlineCellEdits({
        edits: Object.entries(draft).map(([columnKey, fieldValue]) => ({
          columnKey,
          record: selectedRecord,
          value: isBlankLegacyIssueFieldValue(fieldValue) ? null : fieldValue,
        })),
      });
    } catch (saveError) {
      toast.error(
        errorMessage(saveError, t('coreBusiness.module.errors.saveFailed')),
      );
    } finally {
      setSaving(false);
    }
  }

  async function removeRecord() {
    if (!workspaceSlug || !token || !currentRevision || !selectedRecord) return;
    if (!canEditCurrentRevision && !isPendingCreateRecordId(selectedRecord.id))
      return;
    const confirmed = await confirm({
      cancelLabel: t('common:actions.cancel'),
      confirmLabel: t('common:actions.delete'),
      description: t('coreBusiness.module.confirmDelete'),
      title: t('coreBusiness.module.actions.delete'),
      variant: 'danger',
    });
    if (!confirmed) return;
    if (isPendingCreateRecordId(selectedRecord.id)) {
      removePendingCreateRecordIds([selectedRecord.id]);
      closePanel();
      return;
    }
    setSaving(true);
    try {
      await deleteLegacyIssueDatasetRecord({
        datasetKey,
        recordId: selectedRecord.id,
        revisionId: currentRevision.id,
        token,
        viewKey,
        workspaceSlug,
      });
      closePanel();
      draftCompareCacheRef.current.clear();
      await loadRecords();
    } catch (deleteError) {
      toast.error(
        errorMessage(deleteError, t('coreBusiness.module.errors.deleteFailed')),
      );
    } finally {
      setSaving(false);
    }
  }

  async function deleteInlineRecords(
    recordsToDelete: LegacyIssueDatasetRecord[],
  ) {
    if (!workspaceSlug || !token || !currentRevision || !canEditCurrentRevision)
      return;
    if (recordsToDelete.length === 0) return;
    const confirmed = await confirm({
      cancelLabel: t('common:actions.cancel'),
      confirmLabel: t('common:actions.delete'),
      description:
        recordsToDelete.length === 1
          ? t('coreBusiness.module.confirmDelete')
          : t('coreBusiness.module.confirmDeleteRows', {
              count: recordsToDelete.length,
            }),
      title: t('coreBusiness.module.actions.delete'),
      variant: 'danger',
    });
    if (!confirmed) return;
    const pendingRecordIds = recordsToDelete
      .filter((record) => isPendingCreateRecordId(record.id))
      .map((record) => record.id);
    const persistedRecordsToDelete = recordsToDelete.filter(
      (record) => !isPendingCreateRecordId(record.id),
    );
    if (pendingRecordIds.length > 0) {
      removePendingCreateRecordIds(pendingRecordIds);
    }
    if (persistedRecordsToDelete.length === 0) {
      if (recordsToDelete.some((record) => selectedRecord?.id === record.id)) {
        closePanel();
      }
      return;
    }
    try {
      await Promise.all(
        persistedRecordsToDelete.map((record) =>
          deleteLegacyIssueDatasetRecord({
            datasetKey,
            recordId: record.id,
            revisionId: currentRevision.id,
            token,
            viewKey,
            workspaceSlug,
          }),
        ),
      );
      if (recordsToDelete.some((record) => selectedRecord?.id === record.id)) {
        closePanel();
      }
      draftCompareCacheRef.current.clear();
      await loadRecords();
    } catch (deleteError) {
      toast.error(
        errorMessage(deleteError, t('coreBusiness.module.errors.deleteFailed')),
      );
    }
  }

  async function openImportPreview(file: File | null = importFile) {
    if (
      !workspaceSlug ||
      !token ||
      !file ||
      !canEditCurrentDraftRevision ||
      hasPendingDraftChanges ||
      importPreviewing
    )
      return;
    setImportPreviewing(true);
    try {
      const preview = await previewLegacyIssueDatasetImport({
        file,
        datasetKey,
        token,
        viewKey,
        workspaceSlug,
      });
      setImportFile(file);
      setImportPreview(preview);
      setImportMapping(preview.suggested_mapping);
    } catch (previewError) {
      toast.error(
        errorMessage(
          previewError,
          t('coreBusiness.module.errors.importPreviewFailed'),
        ),
      );
    } finally {
      setImportPreviewing(false);
    }
  }

  async function runImport() {
    if (
      !workspaceSlug ||
      !token ||
      !currentRevision ||
      !canEditCurrentDraftRevision ||
      hasPendingDraftChanges ||
      !importFile
    )
      return;
    setSaving(true);
    try {
      const result = await importLegacyIssueDatasetRecords({
        file: importFile,
        mapping: importMapping,
        datasetKey,
        revisionId: currentRevision.id,
        token,
        viewKey,
        workspaceSlug,
      });
      toast.success(
        t('coreBusiness.module.import.result', {
          created: result.created,
          skipped: result.skipped,
          total: result.total_rows,
          updated: result.updated,
        }),
      );
      setImportFile(null);
      setImportPreview(null);
      draftCompareCacheRef.current.clear();
      await loadRecords();
    } catch (importError) {
      toast.error(
        errorMessage(importError, t('coreBusiness.module.errors.importFailed')),
      );
    } finally {
      setSaving(false);
    }
  }

  async function downloadAttachment(attachment: LegacyIssueDatasetAttachment) {
    if (!workspaceSlug || !token) return;
    try {
      const blob = await fetchLegacyIssueDatasetAttachmentBlob({
        attachmentId: attachment.id,
        datasetKey,
        token,
        workspaceSlug,
      });
      downloadBlobAsFile(blob, attachment.filename);
    } catch (downloadError) {
      toast.error(
        errorMessage(
          downloadError,
          t('coreBusiness.module.errors.attachmentDownloadFailed'),
        ),
      );
    }
  }

  function uploadAttachments(files: FileList | File[]) {
    if (
      !workspaceSlug ||
      !token ||
      !canEditAttachmentsInRevision ||
      !selectedRecord
    )
      return;
    const selectedFiles = Array.from(files);
    if (selectedFiles.length === 0) return;
    stagePendingAttachments(selectedRecord.id, selectedFiles);
  }

  function updateAttachmentDescription(
    attachment: LegacyIssueDatasetAttachment,
    description: string,
  ) {
    if (
      !workspaceSlug ||
      !token ||
      !canEditAttachmentsInRevision ||
      !selectedRecord
    )
      return;
    const normalizedDescription = normalizeAttachmentDescription(description);
    const originalDescription = normalizeAttachmentDescription(
      attachment.description ?? '',
    );
    updatePendingAttachmentEditsForSelectedRecord((current) => {
      const descriptions = { ...current.descriptions };
      if (normalizedDescription === originalDescription) {
        delete descriptions[attachment.id];
      } else {
        descriptions[attachment.id] = normalizedDescription;
      }
      return { ...current, descriptions };
    });
  }

  function setPrimaryAttachment(attachment: LegacyIssueDatasetAttachment) {
    if (
      !workspaceSlug ||
      !token ||
      !selectedRecord ||
      !canEditAttachmentsInRevision
    )
      return;
    const originalPrimaryId = selectedRecord.attachments.find(
      (item) => item.is_primary,
    )?.id;
    updatePendingAttachmentEditsForSelectedRecord((current) => {
      if (attachment.id === originalPrimaryId) {
        const { primaryAttachmentId: _removed, ...rest } = current;
        return rest;
      }
      return { ...current, primaryAttachmentId: attachment.id };
    });
  }

  async function retryAttachmentIndex(
    attachment: LegacyIssueDatasetAttachment,
  ) {
    if (
      !workspaceSlug ||
      !token ||
      !selectedRecord ||
      !canEditAttachmentsInRevision ||
      saving ||
      draftSaving
    )
      return;
    setBusyAttachmentId(attachment.id);
    try {
      await retryLegacyIssueDatasetAttachmentIndex({
        attachmentId: attachment.id,
        datasetKey,
        token,
        workspaceSlug,
      });
      await refreshSelectedRecord(selectedRecord.id);
    } catch (retryError) {
      toast.error(
        errorMessage(
          retryError,
          t('coreBusiness.module.errors.attachmentIndexRetryFailed'),
        ),
      );
    } finally {
      setBusyAttachmentId(null);
    }
  }

  async function deleteAttachment(attachment: LegacyIssueDatasetAttachment) {
    if (
      !workspaceSlug ||
      !token ||
      !canEditAttachmentsInRevision ||
      !selectedRecord
    )
      return;
    const confirmed = await confirm({
      cancelLabel: t('common:actions.cancel'),
      confirmLabel: t('common:actions.delete'),
      description: attachment.filename,
      title: t('coreBusiness.module.actions.delete'),
      variant: 'danger',
    });
    if (!confirmed) return;
    updatePendingAttachmentEditsForSelectedRecord((current) => {
      const descriptions = { ...current.descriptions };
      delete descriptions[attachment.id];
      const next: PendingAttachmentEdits = {
        ...current,
        deletedAttachmentIds: [
          ...new Set([...current.deletedAttachmentIds, attachment.id]),
        ],
        descriptions,
      };
      if (next.primaryAttachmentId === attachment.id) {
        delete next.primaryAttachmentId;
      }
      return next;
    });
  }

  async function refreshSelectedRecord(recordId: string) {
    const latestRecords = await loadRecords();
    const refreshed = latestRecords.find((record) => record.id === recordId);
    if (refreshed) {
      selectedRecordRef.current = refreshed;
      setSelectedRecord(refreshed);
      setDraft(refreshed.values);
    }
  }

  function selectRevision(
    revisionId: string | null,
    { allowPendingChanges = false }: { allowPendingChanges?: boolean } = {},
  ) {
    if (
      !allowPendingChanges &&
      (hasPendingDraftChanges || saving || draftSaving)
    )
      return;
    const next = new URLSearchParams(searchParams);
    if (revisionId) {
      next.set('revision_id', revisionId);
    } else {
      next.delete('revision_id');
    }
    setSearchParams(next, { replace: true });
    setSelectedRevisionId(revisionId);
    setCompareResult(null);
  }

  async function startDraft(baseRevisionId?: string | null) {
    if (
      !workspaceSlug ||
      !token ||
      revisionBusy ||
      hasPendingDraftChanges ||
      saving ||
      draftSaving
    )
      return;
    setRevisionBusy(true);
    try {
      const draftRevision = await createLegacyIssueDatasetDraftRevision({
        baseRevisionId,
        datasetKey,
        token,
        viewKey,
        workspaceSlug,
      });
      setRevisions((current) =>
        upsertLegacyIssueRevision(current, draftRevision),
      );
      setRevisionContext((current) =>
        current
          ? {
              ...current,
              active_draft: draftRevision,
              current:
                current.current.id === draftRevision.id
                  ? draftRevision
                  : current.current,
            }
          : current,
      );
      selectRevision(draftRevision.id);
    } catch (revisionError) {
      toast.error(
        errorMessage(revisionError, t('coreBusiness.module.errors.saveFailed')),
      );
    } finally {
      setRevisionBusy(false);
    }
  }

  async function publishRevision(revision: LegacyIssueRevision, note: string) {
    if (!workspaceSlug || !token || revisionBusy) return;
    if (hasPendingDraftChanges) {
      toast.error(t('coreBusiness.module.errors.saveDraftBeforePublish'));
      return;
    }
    setRevisionBusy(true);
    try {
      await publishLegacyIssueDatasetRevision({
        datasetKey,
        note,
        revisionId: revision.id,
        token,
        viewKey,
        workspaceSlug,
      });
      selectRevision(null, { allowPendingChanges: true });
      closePanel();
    } catch (revisionError) {
      toast.error(
        errorMessage(revisionError, t('coreBusiness.module.errors.saveFailed')),
      );
    } finally {
      setRevisionBusy(false);
    }
  }

  async function cancelRevision(revision: LegacyIssueRevision) {
    if (!workspaceSlug || !token || revisionBusy) return;
    const force = canForceCancelLegacyIssueDraftRevision({
      activeDraftId: activeDraft?.id ?? null,
      canForceCancelActiveDraft:
        revisionContext?.can_force_cancel_active_draft ?? false,
      currentUserId: user?.id ?? null,
      revision,
    });
    if (force) {
      const editorName =
        revision.locked_by_name ??
        t('coreBusiness.revision.unknownDraftEditor');
      const confirmed = await confirm({
        cancelLabel: t('common:actions.cancel'),
        confirmLabel: t('coreBusiness.revision.forceCancelDraft'),
        description: t('coreBusiness.revision.forceCancelDraftDescription', {
          name: editorName,
        }),
        title: t('coreBusiness.revision.forceCancelDraftTitle', {
          name: editorName,
        }),
        variant: 'danger',
      });
      if (!confirmed) return;
      if (hasPendingDraftChanges) {
        clearPendingDraftChanges();
      }
    } else {
      const confirmed = await confirm({
        cancelLabel: t('common:actions.cancel'),
        confirmLabel: t('coreBusiness.revision.cancelDraft'),
        description: t('coreBusiness.revision.cancelDraftDescription'),
        title: t('coreBusiness.revision.cancelDraft'),
        variant: 'danger',
      });
      if (!confirmed) return;
      if (hasPendingDraftChanges) {
        clearPendingDraftChanges();
      }
    }
    setRevisionBusy(true);
    try {
      await cancelLegacyIssueDatasetRevision({
        datasetKey,
        force,
        revisionId: revision.id,
        token,
        viewKey,
        workspaceSlug,
      });
      if (force) {
        toast.success(t('coreBusiness.revision.forceCancelDraftSuccess'));
      }
      selectRevision(null, { allowPendingChanges: true });
      closePanel();
    } catch (revisionError) {
      toast.error(
        errorMessage(revisionError, t('coreBusiness.module.errors.saveFailed')),
      );
    } finally {
      setRevisionBusy(false);
    }
  }

  async function restoreRevision(revision: LegacyIssueRevision) {
    if (
      !workspaceSlug ||
      !token ||
      revisionBusy ||
      hasPendingDraftChanges ||
      saving ||
      draftSaving
    )
      return;
    setRevisionBusy(true);
    try {
      const draftRevision = await restoreLegacyIssueDatasetRevision({
        datasetKey,
        revisionId: revision.id,
        token,
        viewKey,
        workspaceSlug,
      });
      selectRevision(draftRevision.id);
    } catch (revisionError) {
      toast.error(
        errorMessage(revisionError, t('coreBusiness.module.errors.saveFailed')),
      );
    } finally {
      setRevisionBusy(false);
    }
  }

  async function compareRevisions(
    leftRevisionId: string,
    rightRevisionId: string,
  ) {
    if (!workspaceSlug || !token) return;
    setCompareBusy(true);
    try {
      const result = await compareLegacyIssueDatasetRevisions({
        leftRevisionId,
        datasetKey,
        rightRevisionId,
        token,
        viewKey,
        workspaceSlug,
      });
      setCompareResult(result);
    } catch (revisionError) {
      toast.error(
        errorMessage(revisionError, t('coreBusiness.module.errors.loadFailed')),
      );
    } finally {
      setCompareBusy(false);
    }
  }

  async function updateRevisionOverviewHistory(
    history: LegacyIssueRevisionOverviewHistory,
    payload: LegacyIssueRevisionOverviewHistoryUpdate,
  ): Promise<boolean> {
    if (!workspaceSlug || !token || revisionBusy || !isPlatformAdmin) {
      return false;
    }
    setRevisionBusy(true);
    try {
      const updated = await updateLegacyIssueRevisionOverviewHistory({
        datasetKey,
        historyId: history.id,
        payload,
        token,
        viewKey,
        workspaceSlug,
      });
      setRevisionOverviewHistory((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      );
      toast.success(t('coreBusiness.module.overview.historySaved'));
      return true;
    } catch (revisionError) {
      toast.error(
        errorMessage(revisionError, t('coreBusiness.module.errors.saveFailed')),
      );
      return false;
    } finally {
      setRevisionBusy(false);
    }
  }

  async function createRevisionOverviewHistory(
    payload: LegacyIssueRevisionOverviewHistoryUpdate,
    linkedRevisionId: string | null,
  ): Promise<boolean> {
    if (!workspaceSlug || !token || revisionBusy || !isPlatformAdmin) {
      return false;
    }
    setRevisionBusy(true);
    try {
      const created = await createLegacyIssueRevisionOverviewHistory({
        datasetKey,
        payload: {
          ...payload,
          linked_revision_id: linkedRevisionId,
        },
        token,
        viewKey,
        workspaceSlug,
      });
      setRevisionOverviewHistory((current) => [created, ...current]);
      toast.success(t('coreBusiness.module.overview.historyCreated'));
      return true;
    } catch (revisionError) {
      toast.error(
        errorMessage(
          revisionError,
          t('coreBusiness.module.errors.historyCreateFailed'),
        ),
      );
      return false;
    } finally {
      setRevisionBusy(false);
    }
  }

  async function deleteRevisionOverviewHistory(
    history: LegacyIssueRevisionOverviewHistory | null,
    revision: LegacyIssueRevision | null,
  ): Promise<boolean> {
    if (
      !workspaceSlug ||
      !token ||
      revisionBusy ||
      !isPlatformAdmin ||
      (!history && !revision)
    ) {
      return false;
    }
    const confirmed = await confirm({
      cancelLabel: t('common:actions.cancel'),
      confirmLabel: t('common:actions.delete'),
      description: t(
        'coreBusiness.module.overview.confirmDeleteHistoryDescription',
      ),
      title: t('coreBusiness.module.overview.confirmDeleteHistoryTitle'),
      variant: 'danger',
    });
    if (!confirmed) return false;
    setRevisionBusy(true);
    try {
      let deleted: LegacyIssueRevisionOverviewHistory;
      if (history) {
        deleted = await deleteLegacyIssueRevisionOverviewHistory({
          datasetKey,
          historyId: history.id,
          token,
          viewKey,
          workspaceSlug,
        });
      } else if (revision) {
        deleted = await hideLegacyIssueRevisionFromOverviewHistory({
          datasetKey,
          revisionId: revision.id,
          token,
          viewKey,
          workspaceSlug,
        });
      } else {
        return false;
      }
      setRevisionOverviewHistory((current) => {
        const exists = current.some((item) => item.id === deleted.id);
        return exists
          ? current.map((item) => (item.id === deleted.id ? deleted : item))
          : [deleted, ...current];
      });
      toast.success(t('coreBusiness.module.overview.historyDeleted'));
      return true;
    } catch (revisionError) {
      toast.error(
        errorMessage(
          revisionError,
          t('coreBusiness.module.errors.historyDeleteFailed'),
        ),
      );
      return false;
    } finally {
      setRevisionBusy(false);
    }
  }

  async function updateRevisionApprovalAssignees({
    approverId,
    reviewerId,
    revision,
  }: {
    approverId: string | null;
    reviewerId: string | null;
    revision: LegacyIssueRevision;
  }) {
    if (!workspaceSlug || !token || revisionBusy) return;
    if (
      isLegacyIssueRevisionAssigneeChangeBlocked({
        approverId,
        reviewerId,
        revision,
      })
    ) {
      return;
    }
    if (
      shouldConfirmLegacyIssueRevisionAssigneeChange({
        approverId,
        reviewerId,
        revision,
      })
    ) {
      const confirmed = await confirm({
        cancelLabel: t('common:actions.cancel'),
        confirmLabel: t('common:actions.update'),
        description: t(
          'coreBusiness.module.overview.confirmAssigneeChangeDescription',
        ),
        title: t('coreBusiness.module.overview.confirmAssigneeChangeTitle'),
      });
      if (!confirmed) return;
    }
    setRevisionBusy(true);
    try {
      await updateLegacyIssueDatasetRevisionAssignees({
        approverId,
        datasetKey,
        reviewerId,
        revisionId: revision.id,
        token,
        viewKey,
        workspaceSlug,
      });
      await loadRecords();
    } catch (revisionError) {
      toast.error(
        errorMessage(revisionError, t('coreBusiness.module.errors.saveFailed')),
      );
    } finally {
      setRevisionBusy(false);
    }
  }

  async function requestRevisionApproval(revision: LegacyIssueRevision) {
    if (!workspaceSlug || !token || revisionBusy) return;
    setRevisionBusy(true);
    try {
      await requestLegacyIssueDatasetRevisionApproval({
        datasetKey,
        revisionId: revision.id,
        token,
        viewKey,
        workspaceSlug,
      });
      await loadRecords();
      toast.success(t('coreBusiness.module.overview.requestSent'));
    } catch (revisionError) {
      toast.error(
        errorMessage(revisionError, t('coreBusiness.module.errors.saveFailed')),
      );
    } finally {
      setRevisionBusy(false);
    }
  }

  async function completeRevisionReview(revision: LegacyIssueRevision) {
    if (!workspaceSlug || !token || revisionBusy) return;
    setRevisionBusy(true);
    try {
      await completeLegacyIssueDatasetRevisionReview({
        datasetKey,
        revisionId: revision.id,
        token,
        viewKey,
        workspaceSlug,
      });
      await loadRecords();
      toast.success(t('coreBusiness.module.overview.reviewCompleted'));
    } catch (revisionError) {
      toast.error(
        errorMessage(revisionError, t('coreBusiness.module.errors.saveFailed')),
      );
    } finally {
      setRevisionBusy(false);
    }
  }

  async function completeRevisionApproval(revision: LegacyIssueRevision) {
    if (!workspaceSlug || !token || revisionBusy) return;
    setRevisionBusy(true);
    try {
      await completeLegacyIssueDatasetRevisionApproval({
        datasetKey,
        revisionId: revision.id,
        token,
        viewKey,
        workspaceSlug,
      });
      await loadRecords();
      toast.success(t('coreBusiness.module.overview.approvalCompleted'));
    } catch (revisionError) {
      toast.error(
        errorMessage(revisionError, t('coreBusiness.module.errors.saveFailed')),
      );
    } finally {
      setRevisionBusy(false);
    }
  }

  function openRevisionComparison({
    leftRevisionId,
    rightRevisionId,
  }: RevisionComparePair) {
    setCompareResult(null);
    setOverviewComparePair({ leftRevisionId, rightRevisionId });
    void compareRevisions(leftRevisionId, rightRevisionId);
  }

  return (
    <main className="relative flex h-full min-h-0 bg-app-bg text-app-ink">
      {confirmDialog}
      <section className="flex min-w-0 flex-1 flex-col">
        {!upperControlsCollapsed ? (
          <LegacyIssuePageHeader
            actions={
              <>
                {!isAggregateView && activeTab === 'sheet' ? (
                  <LegacyIssueToolbarButton
                    disabled={!canEditCurrentRevision}
                    icon={<Plus size={15} />}
                    label={t('coreBusiness.module.actions.create')}
                    onClick={openCreatePanel}
                  />
                ) : null}
                {!isAggregateView && activeTab === 'sheet' ? (
                  <LegacyIssueExcelExportControls
                    disabled={
                      !currentRevision ||
                      !user?.id ||
                      excelExportColumnKeys === null ||
                      excelExportRecordIds === undefined
                    }
                    exportLabel={t('coreBusiness.module.actions.export')}
                    workflow={excelExport}
                  />
                ) : null}
                {!isAggregateView && activeTab === 'sheet' ? (
                  <LegacyIssueImportFileButton
                    disabled={
                      importPreviewing ||
                      saving ||
                      hasPendingDraftChanges ||
                      !canEditCurrentDraftRevision
                    }
                    fileTypesLabel={t('coreBusiness.module.import.fileTypes')}
                    label={t('coreBusiness.module.actions.import')}
                    loading={importPreviewing}
                    onFileSelected={(file) => void openImportPreview(file)}
                  />
                ) : null}
                {activeTab === 'sheet' &&
                canDirectEditPublishedRevision &&
                hasPendingDraftChanges ? (
                  <LegacyIssueToolbarButton
                    disabled={draftSaving || saving}
                    icon={
                      draftSaving || saving ? (
                        <Loader2 size={15} className="animate-spin" />
                      ) : (
                        <Save size={15} />
                      )
                    }
                    label={t('coreBusiness.module.actions.save')}
                    onClick={() => void savePendingDraftChanges()}
                  />
                ) : null}
                <LegacyIssueToolbarButton
                  disabled={definitionRefreshing}
                  icon={
                    definitionRefreshing ? (
                      <Loader2 size={15} className="animate-spin" />
                    ) : (
                      <RefreshCw size={15} />
                    )
                  }
                  label={t('coreBusiness.module.actions.refreshCommonCodes')}
                  onClick={() => void refreshDefinition()}
                />
                <LegacyIssueToolbarButton
                  disabled={loading || hasPendingDraftChanges}
                  icon={
                    loading ? (
                      <Loader2 size={15} className="animate-spin" />
                    ) : (
                      <RefreshCw size={15} />
                    )
                  }
                  label={t('coreBusiness.module.actions.refresh')}
                  onClick={() => {
                    draftCompareCacheRef.current.clear();
                    void loadRecords();
                    void refreshDefinition();
                  }}
                />
              </>
            }
            eyebrow={t('coreBusiness.module.eyebrow', {
              path: localizedDefinition?.hierarchy.join(' > ') ?? '',
            })}
            title={
              localizedDefinition?.title ??
              t('coreBusiness.module.loadingTitle')
            }
          />
        ) : null}
        {!upperControlsCollapsed && !isAggregateView ? (
          <LegacyIssueDatasetTabs
            activeTab={activeTab}
            onChange={setActiveTab}
          />
        ) : null}
        {!upperControlsCollapsed &&
        !isAggregateView &&
        activeTab === 'sheet' &&
        currentRevision ? (
          <LegacyIssueRevisionBar
            activeDraft={activeDraft}
            busy={revisionBusy}
            canEditActiveDraft={canEditActiveDraftRevision}
            canEditCurrentDraft={canEditCurrentDraftRevision}
            canForceCancelActiveDraft={canForceCancelActiveDraftRevision}
            canPublishCurrentDraft={isLegacyIssueRevisionReadyToPublish(
              currentRevision,
            )}
            comparing={compareBusy}
            compareResult={compareResult}
            current={currentRevision}
            dirtyChangeCount={pendingDraftChangeCount}
            events={revisionEvents}
            onCancelDraft={(revision) =>
              void cancelRevision(revision as LegacyIssueRevision)
            }
            onCompare={(leftRevisionId, rightRevisionId) =>
              void compareRevisions(leftRevisionId, rightRevisionId)
            }
            onPublishDraft={(revision, note) =>
              void publishRevision(revision as LegacyIssueRevision, note)
            }
            onSaveDraftChanges={() => void savePendingDraftChanges()}
            onRestoreRevision={(revision) =>
              void restoreRevision(revision as LegacyIssueRevision)
            }
            onSelectRevision={selectRevision}
            onStartDraft={(baseRevisionId) => void startDraft(baseRevisionId)}
            revisions={revisions}
            savingDraftChanges={draftSaving || saving}
          />
        ) : null}
        {activeTab === 'sheet' ? (
          <>
            {!upperControlsCollapsed && !isAggregateView && currentRevision ? (
              <LegacyIssueRevisionApprovalPanel
                busy={revisionBusy || loading}
                canEditDraft={canEditCurrentDraftRevision}
                currentUserId={user?.id ?? null}
                revision={currentRevision}
                token={token}
                workspaceSlug={workspaceSlug}
                onApprovalComplete={(revision) =>
                  void completeRevisionApproval(revision)
                }
                onAssigneesChange={(params) =>
                  void updateRevisionApprovalAssignees(params)
                }
                onRequestApproval={(revision) =>
                  void requestRevisionApproval(revision)
                }
                onReviewComplete={(revision) =>
                  void completeRevisionReview(revision)
                }
              />
            ) : null}
            <LegacyIssueDatasetGrid
              allowRowCreate={canEditCurrentRevision && !draftSaving && !saving}
              allowRowDelete={canEditCurrentRevision && !draftSaving && !saving}
              definition={definition}
              detailOpen={panelMode === 'create' || Boolean(selectedRecord)}
              changedCellKeys={draftChangedCellKeys}
              loading={loading || userGridPreference.status === 'loading'}
              editable={canEditCurrentRevision && !draftSaving && !saving}
              blankRowCount={blankRowCount}
              blankRowDefaultValues={blankRowDefaultValues}
              defaultColumnOrder={defaultColumnOrder}
              defaultHiddenColumnKeys={defaultHiddenColumnKeys}
              gridPreference={resolvedUserGridPreference}
              gridPreferenceControlsDisabled={userGridPreference.loadFailed}
              gridPreferenceStatus={userGridPreference.status}
              onAddBlankRows={(count = BLANK_ROW_BATCH_SIZE) =>
                setBlankRowCount((current) => current + Math.max(1, count))
              }
              onRemoveBlankRows={(rowIndexes) =>
                setBlankRowCount((current) =>
                  Math.max(0, current - rowIndexes.length),
                )
              }
              onCreateRows={createInlineRecords}
              onDeleteRows={deleteInlineRecords}
              onDownloadAttachment={
                isAggregateView ? () => undefined : downloadAttachment
              }
              onEditCells={saveInlineCells}
              onEditCell={saveInlineCell}
              onOpenRecord={isAggregateView ? () => undefined : openEditPanel}
              onGridPreferenceChange={(preference) =>
                userGridPreference.updatePreference({
                  column_order: preference.columnOrder,
                  frozen_column_count: preference.frozenColumnCount,
                  hidden_column_keys: preference.hiddenColumnKeys,
                })
              }
              onGridPreferenceReset={userGridPreference.resetPreference}
              onGridPreferenceRetry={userGridPreference.retry}
              onVisibleColumnKeysChange={setExcelExportGridLayout}
              onVisibleRowsChange={setExcelExportRowLayout}
              records={records}
              revisionKey={`${revisionGridKey(
                currentRevision,
              )}:${draftSaveVersion}`}
              layoutId={viewDefinition.gridLayoutId}
              toolbarLeading={
                <LegacyIssueDatasetGridSummary
                  inputId={`legacy-issue-${datasetKey}-search`}
                  loaded={records.length}
                  query={query}
                  total={total}
                  onQueryChange={setQuery}
                  onSubmit={(event) => {
                    event.preventDefault();
                    if (hasPendingDraftChanges) {
                      toast.error(
                        t('coreBusiness.module.errors.saveDraftBeforeRefresh'),
                      );
                      return;
                    }
                    void loadRecords();
                  }}
                />
              }
              toolbarTrailing={
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
              }
            />
          </>
        ) : activeTab === 'overview' ? (
          <LegacyIssueRevisionOverview
            busy={revisionBusy || loading}
            canEditOverviewHistory={isPlatformAdmin}
            currentUserId={user?.id ?? null}
            datasetKey={datasetKey}
            onComparePair={openRevisionComparison}
            onOverviewHistoryCreate={createRevisionOverviewHistory}
            onOverviewHistoryDelete={deleteRevisionOverviewHistory}
            onOverviewHistorySave={updateRevisionOverviewHistory}
            overviewHistory={revisionOverviewHistory}
            revisions={revisions}
            token={token}
            viewKey={viewKey}
            workspaceSlug={workspaceSlug}
          />
        ) : (
          <LegacyIssueRevisionMeetingMinutes
            datasetKey={datasetKey}
            rows={revisionOverviewRows}
            token={token}
            viewKey={viewKey}
            workspaceSlug={workspaceSlug}
          />
        )}
      </section>
      {!isAggregateView &&
      activeTab === 'sheet' &&
      (panelMode === 'create' || selectedRecord) ? (
        <LegacyIssueDatasetDetailPanel
          allowDelete={
            canEditCurrentRevision ||
            Boolean(
              selectedRecord && isPendingCreateRecordId(selectedRecord.id),
            )
          }
          attachmentsReadonly={!canEditAttachmentsInRevision}
          busyAttachmentId={busyAttachmentId}
          definition={definition}
          draft={draft}
          historyItems={historyItems}
          historyLoading={historyLoading}
          hasPendingAttachmentChanges={
            selectedRecord
              ? (pendingAttachmentDraftsByRecordId[selectedRecord.id]?.length ??
                  0) > 0 ||
                countPendingAttachmentEdits({
                  ...(pendingAttachmentEditsByRecordId[selectedRecord.id]
                    ? {
                        [selectedRecord.id]:
                          pendingAttachmentEditsByRecordId[selectedRecord.id],
                      }
                    : {}),
                }) > 0
              : false
          }
          mode={panelMode}
          onAttachmentDelete={deleteAttachment}
          onAttachmentDescriptionSave={updateAttachmentDescription}
          onAttachmentDownload={downloadAttachment}
          onAttachmentIndexRetry={retryAttachmentIndex}
          onAttachmentPrimary={setPrimaryAttachment}
          onAttachmentUpload={uploadAttachments}
          onAttachmentSave={() => void saveSelectedRecordAttachments()}
          onPendingAttachmentDelete={removePendingAttachmentDraft}
          onPendingAttachmentDescriptionChange={
            updatePendingAttachmentDescription
          }
          canSetPrimaryAttachment={canEditAttachmentsInRevision}
          pendingCreateRecord={
            selectedRecord ? isPendingCreateRecordId(selectedRecord.id) : false
          }
          pendingAttachments={
            selectedRecord
              ? (pendingAttachmentDraftsByRecordId[selectedRecord.id] ?? [])
              : []
          }
          pendingAttachmentEdits={
            selectedRecord
              ? pendingAttachmentEditsByRecordId[selectedRecord.id]
              : undefined
          }
          onClose={closePanel}
          onDelete={removeRecord}
          onDraftChange={(key, value) =>
            setDraft((current) => ({ ...current, [key]: value }))
          }
          onSave={saveRecord}
          record={selectedRecord}
          readonly={!canEditCurrentRevision}
          saving={saving || draftSaving}
          uploading={uploading}
        />
      ) : null}

      {overviewComparePair ? (
        <LegacyIssueRevisionCompareModal
          comparing={compareBusy}
          compareResult={compareResult}
          current={currentRevision}
          initialLeftRevisionId={overviewComparePair.leftRevisionId}
          initialRightRevisionId={overviewComparePair.rightRevisionId}
          onClose={() => setOverviewComparePair(null)}
          onCompare={(leftRevisionId, rightRevisionId) =>
            void compareRevisions(leftRevisionId, rightRevisionId)
          }
          revisions={revisions.filter(isVisibleLegacyIssueRevision)}
        />
      ) : null}

      {importPreview && definition ? (
        <LegacyIssueImportMappingDialog
          definition={definition}
          mapping={importMapping}
          onClose={() => setImportPreview(null)}
          onImport={runImport}
          onMappingChange={setImportMapping}
          preview={importPreview}
          saving={saving}
        />
      ) : null}
    </main>
  );
}

export function resolveLegacyIssueMainTab({
  isAggregateView,
  tab,
}: {
  isAggregateView: boolean;
  tab: string | null;
}): LegacyIssueMainTab {
  if (isAggregateView) return 'sheet';
  return tab === 'overview' || tab === 'minutes' ? tab : 'sheet';
}

export function legacyIssueMainTabSearchParams(
  searchParams: URLSearchParams,
  tab: LegacyIssueMainTab,
): URLSearchParams {
  const next = new URLSearchParams(searchParams);
  if (tab === 'sheet') {
    next.delete('tab');
  } else {
    next.set('tab', tab);
  }
  return next;
}

function LegacyIssueDatasetTabs({
  activeTab,
  onChange,
}: {
  activeTab: LegacyIssueMainTab;
  onChange: (tab: LegacyIssueMainTab) => void;
}) {
  const { t } = useTranslation(['apps']);
  return (
    <div
      aria-label={t('coreBusiness.module.loadingTitle')}
      className="flex shrink-0 border-b border-app-border bg-app-bg px-4"
      role="group"
    >
      <button
        aria-pressed={activeTab === 'sheet'}
        className={legacyIssueMainTabClassName(activeTab === 'sheet')}
        type="button"
        onClick={() => onChange('sheet')}
      >
        {t('coreBusiness.module.tabs.sheet')}
      </button>
      <button
        aria-pressed={activeTab === 'overview'}
        className={legacyIssueMainTabClassName(activeTab === 'overview')}
        type="button"
        onClick={() => onChange('overview')}
      >
        {t('coreBusiness.module.tabs.overview')}
      </button>
      <button
        aria-pressed={activeTab === 'minutes'}
        className={legacyIssueMainTabClassName(activeTab === 'minutes')}
        type="button"
        onClick={() => onChange('minutes')}
      >
        {t('coreBusiness.module.tabs.meetingMinutes')}
      </button>
    </div>
  );
}

function legacyIssueMainTabClassName(active: boolean): string {
  return cn(
    'border-b-2 px-3 py-2 app-text-caption font-medium',
    active
      ? 'border-app-accent text-app-accent'
      : 'border-transparent text-app-ink/55 hover:text-app-ink',
  );
}

function LegacyIssueDatasetGridSummary({
  inputId,
  loaded,
  onQueryChange,
  onSubmit,
  query,
  total,
}: {
  inputId: string;
  loaded: number;
  onQueryChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  query: string;
  total: number;
}) {
  const { t } = useTranslation(['apps']);
  const searchLabel = t('coreBusiness.module.actions.search');
  return (
    <LegacyIssueGridToolbarSearch
      inputId={inputId}
      searchLabel={searchLabel}
      searchPlaceholder={t('coreBusiness.module.searchPlaceholder')}
      searchValue={query}
      summary={t('coreBusiness.module.grid.total', { loaded, total })}
      onSearchChange={onQueryChange}
      onSubmit={onSubmit}
    />
  );
}

function LegacyIssueRevisionApprovalPanel({
  busy,
  canEditDraft,
  currentUserId,
  onApprovalComplete,
  onAssigneesChange,
  onRequestApproval,
  onReviewComplete,
  revision,
  token,
  workspaceSlug,
}: {
  busy: boolean;
  canEditDraft: boolean;
  currentUserId: string | null;
  onApprovalComplete: (revision: LegacyIssueRevision) => void;
  onAssigneesChange: (params: {
    approverId: string | null;
    reviewerId: string | null;
    revision: LegacyIssueRevision;
  }) => void;
  onRequestApproval: (revision: LegacyIssueRevision) => void;
  onReviewComplete: (revision: LegacyIssueRevision) => void;
  revision: LegacyIssueRevision;
  token: string | null | undefined;
  workspaceSlug: string;
}) {
  const { t } = useTranslation(['apps']);
  const isDraft = revision.status === 'draft';
  const reviewerComplete = Boolean(revision.reviewed_at);
  const approverComplete = Boolean(revision.approved_at);
  const canRequestApproval = Boolean(
    isDraft &&
      revision.reviewer_id &&
      revision.approver_id &&
      (!reviewerComplete || !approverComplete),
  );
  const canCompleteReview = Boolean(
    isDraft &&
      revision.reviewer_id &&
      currentUserId &&
      revision.reviewer_id === currentUserId &&
      !revision.reviewed_at,
  );
  const canCompleteApproval = Boolean(
    isDraft &&
      revision.approver_id &&
      currentUserId &&
      revision.approver_id === currentUserId &&
      !revision.approved_at,
  );
  const canChangeAssignees = Boolean(
    isDraft && (canEditDraft || !revision.locked_by_id),
  );
  const reviewerUser = revisionReviewerUser(revision);
  const approverUser = revisionApproverUser(revision);
  const canEditReviewer = canEditLegacyIssueRevisionAssignee({
    revision,
    role: 'reviewer',
  });
  const canEditApprover = canEditLegacyIssueRevisionAssignee({
    revision,
    role: 'approver',
  });

  return (
    <section className="border-b border-app-border bg-app-surface-sidebar px-4 py-2">
      <div className="flex h-10 items-center gap-2 overflow-x-auto whitespace-nowrap">
        <LegacyIssueRevisionUserSelect
          currentUserId={currentUserId}
          disabled={busy || !canChangeAssignees || !canEditReviewer}
          label={t('coreBusiness.module.overview.reviewer')}
          placeholder={t('coreBusiness.grid.emptyValue')}
          selectedUser={reviewerUser}
          token={token}
          workspaceSlug={workspaceSlug}
          onChange={(reviewerId) =>
            onAssigneesChange({
              approverId: revision.approver_id,
              reviewerId,
              revision,
            })
          }
        />
        <LegacyIssueRevisionUserSelect
          currentUserId={currentUserId}
          disabled={busy || !canChangeAssignees || !canEditApprover}
          label={t('coreBusiness.module.overview.approver')}
          placeholder={t('coreBusiness.grid.emptyValue')}
          selectedUser={approverUser}
          token={token}
          workspaceSlug={workspaceSlug}
          onChange={(approverId) =>
            onAssigneesChange({
              approverId,
              reviewerId: revision.reviewer_id,
              revision,
            })
          }
        />
        <LegacyIssueToolbarButton
          disabled={busy || !isDraft || !canEditDraft || !canRequestApproval}
          icon={<Bell size={15} />}
          label={t('coreBusiness.module.overview.requestApproval')}
          onClick={() => onRequestApproval(revision)}
        />
        {reviewerComplete ? (
          <LegacyIssueApprovalStateLabel
            label={t('coreBusiness.module.overview.reviewDone')}
          />
        ) : (
          <LegacyIssueToolbarButton
            disabled={busy || !canCompleteReview}
            icon={<CheckCircle2 size={15} />}
            label={t('coreBusiness.module.overview.completeReview')}
            onClick={() => onReviewComplete(revision)}
          />
        )}
        {approverComplete ? (
          <LegacyIssueApprovalStateLabel
            label={t('coreBusiness.module.overview.approvalDone')}
          />
        ) : (
          <LegacyIssueToolbarButton
            disabled={busy || !canCompleteApproval}
            icon={<CheckCircle2 size={15} />}
            label={t('coreBusiness.module.overview.completeApproval')}
            onClick={() => onApprovalComplete(revision)}
          />
        )}
      </div>
    </section>
  );
}

function LegacyIssueApprovalStateLabel({ label }: { label: string }) {
  return (
    <span className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-md border border-app-success/30 bg-app-success/10 px-3 app-text-caption font-medium text-app-success">
      <CheckCircle2 size={15} aria-hidden="true" />
      {label}
    </span>
  );
}

export function LegacyIssueRevisionOverview({
  busy,
  canEditOverviewHistory,
  currentUserId,
  datasetKey,
  onComparePair,
  onOverviewHistoryCreate,
  onOverviewHistoryDelete,
  onOverviewHistorySave,
  overviewHistory,
  revisions,
  token,
  viewKey,
  workspaceSlug,
}: {
  busy: boolean;
  canEditOverviewHistory: boolean;
  currentUserId: string | null;
  datasetKey: LegacyIssueDatasetKey;
  onComparePair: (pair: RevisionComparePair) => void;
  onOverviewHistoryCreate: (
    payload: LegacyIssueRevisionOverviewHistoryUpdate,
    linkedRevisionId: string | null,
  ) => Promise<boolean>;
  onOverviewHistoryDelete: (
    history: LegacyIssueRevisionOverviewHistory | null,
    revision: LegacyIssueRevision | null,
  ) => Promise<boolean>;
  onOverviewHistorySave: (
    history: LegacyIssueRevisionOverviewHistory,
    payload: LegacyIssueRevisionOverviewHistoryUpdate,
  ) => Promise<boolean>;
  overviewHistory: LegacyIssueRevisionOverviewHistory[];
  revisions: LegacyIssueRevision[];
  token: string | null | undefined;
  viewKey: LegacyIssueViewKey;
  workspaceSlug: string;
}) {
  const { t } = useTranslation(['apps', 'common']);
  const [editingHistoryId, setEditingHistoryId] = useState<string | null>(null);
  const [historyDraft, setHistoryDraft] =
    useState<LegacyIssueRevisionOverviewHistoryUpdate | null>(null);
  const [meetingMinutesRow, setMeetingMinutesRow] =
    useState<LegacyIssueRevisionOverviewRow | null>(null);
  const meetingMinutesTriggerRef = useRef<HTMLButtonElement | null>(null);
  const overviewEditInputRef = useRef<HTMLInputElement | null>(null);
  const overviewRows = useMemo(
    () => buildLegacyIssueRevisionOverviewRows(revisions, overviewHistory),
    [overviewHistory, revisions],
  );
  const displayedOverviewRows = useMemo(
    () =>
      editingHistoryId === NEW_OVERVIEW_HISTORY_ROW_ID && historyDraft
        ? [
            {
              id: NEW_OVERVIEW_HISTORY_ROW_ID,
              revision: null,
              sourceHistory: null,
            },
            ...overviewRows,
          ]
        : overviewRows,
    [editingHistoryId, historyDraft, overviewRows],
  );
  const nextRevisionNo = useMemo(() => {
    const revisionNumbers = [
      ...revisions.map((revision) => revision.revision_no),
      ...overviewHistory
        .filter((history) => !history.deleted_at)
        .map((history) => history.revision_no),
    ].filter((revisionNo): revisionNo is number => revisionNo !== null);
    return Math.min(
      Math.max(-1, ...revisionNumbers) + 1,
      MAX_OVERVIEW_REVISION_NO,
    );
  }, [overviewHistory, revisions]);

  useEffect(() => {
    if (editingHistoryId !== null) {
      overviewEditInputRef.current?.focus();
    }
  }, [editingHistoryId]);

  return (
    <>
      <div className="min-h-0 flex-1 overflow-auto bg-app-surface-sidebar px-4 py-5">
        <article className="mx-auto w-full max-w-7xl border border-slate-500 bg-white p-5 text-slate-950 shadow-sm">
          <header className="relative mb-3 flex min-h-9 items-center justify-center">
            <h2 className="text-center text-2xl font-bold tracking-normal">
              {t('coreBusiness.module.overview.revisionHistoryTitle')}
            </h2>
            {canEditOverviewHistory ? (
              <button
                className="absolute right-0 inline-flex h-9 items-center justify-center gap-1.5 border border-slate-500 bg-white px-3 text-[13px] font-medium text-slate-800 hover:bg-slate-100 disabled:opacity-45"
                disabled={busy || editingHistoryId !== null}
                type="button"
                onClick={() => {
                  setEditingHistoryId(NEW_OVERVIEW_HISTORY_ROW_ID);
                  setHistoryDraft({
                    approver_name: null,
                    approver_user_id: null,
                    author_name: null,
                    author_user_id: currentUserId,
                    revised_on: formatNativeDateInputValue(new Date()),
                    reviewer_name: null,
                    reviewer_user_id: null,
                    revision_no: nextRevisionNo,
                    summary: null,
                    vehicle_models: null,
                  });
                }}
              >
                <Plus size={15} />
                {t('coreBusiness.module.overview.addHistory')}
              </button>
            ) : null}
          </header>

          <div className="overflow-x-auto">
            <table className="w-full min-w-[62rem] table-fixed border-collapse text-[13px] leading-5">
              <colgroup>
                <col className="w-20" />
                <col className="w-52" />
                <col className="w-20" />
                <col className="w-32" />
                <col className="w-28" />
                <col className="w-28" />
                <col className="w-28" />
                <col className="w-40" />
              </colgroup>
              <thead>
                <tr>
                  <OverviewTableHeader>
                    {t('coreBusiness.module.overview.revisionNo')}
                  </OverviewTableHeader>
                  <OverviewTableHeader>
                    {t('coreBusiness.module.overview.summary')}
                  </OverviewTableHeader>
                  <OverviewTableHeader>
                    {t('coreBusiness.module.overview.vehicleModels')}
                  </OverviewTableHeader>
                  <OverviewTableHeader>
                    {t('coreBusiness.module.overview.revisedAt')}
                  </OverviewTableHeader>
                  <OverviewTableHeader>
                    {t('coreBusiness.module.overview.author')}
                  </OverviewTableHeader>
                  <OverviewTableHeader>
                    {t('coreBusiness.module.overview.reviewer')}
                  </OverviewTableHeader>
                  <OverviewTableHeader>
                    {t('coreBusiness.module.overview.approver')}
                  </OverviewTableHeader>
                  <OverviewTableHeader>
                    {t('coreBusiness.module.overview.details')}
                  </OverviewTableHeader>
                </tr>
              </thead>
              <tbody>
                {displayedOverviewRows.length === 0 ? (
                  <tr>
                    <td
                      className="border border-slate-500 px-3 py-8 text-center text-slate-500"
                      colSpan={8}
                    >
                      {t('coreBusiness.module.overview.noPublishedRevisions')}
                    </td>
                  </tr>
                ) : (
                  displayedOverviewRows.map((row, index) => {
                    const previousRevision = displayedOverviewRows
                      .slice(index + 1)
                      .find((candidate) => candidate.revision)?.revision;
                    const revision = row.revision;
                    const sourceHistory = row.sourceHistory;
                    const revisionLabel = legacyIssueOverviewRevisionLabel(
                      row,
                      t,
                    );
                    const editing =
                      (row.id === editingHistoryId ||
                        sourceHistory?.id === editingHistoryId) &&
                      historyDraft;
                    const beginOverviewHistoryEdit = () => {
                      setEditingHistoryId(sourceHistory?.id ?? row.id);
                      const draft = overviewHistoryDraftForRow({
                        history: sourceHistory,
                        revision,
                      });
                      setHistoryDraft({
                        ...draft,
                        summary: editableLegacyIssueRevisionSummary(
                          draft.summary,
                          t,
                        ),
                      });
                    };
                    const compareWithPreviousRevision = () => {
                      if (!revision || !previousRevision) return;
                      onComparePair({
                        leftRevisionId: previousRevision.id,
                        rightRevisionId: revision.id,
                      });
                    };
                    return (
                      <tr key={row.id}>
                        <td className="border border-slate-500 px-2 py-2 text-center align-middle font-semibold">
                          {editing ? (
                            <input
                              ref={overviewEditInputRef}
                              aria-label={t(
                                'coreBusiness.module.overview.revisionNo',
                              )}
                              className="h-8 w-16 border border-slate-400 px-2 text-center"
                              max={MAX_OVERVIEW_REVISION_NO}
                              min={0}
                              step={1}
                              type="number"
                              value={historyDraft.revision_no ?? ''}
                              onChange={(event) =>
                                setHistoryDraft((current) =>
                                  current
                                    ? {
                                        ...current,
                                        revision_no: event.target.value
                                          ? Number(event.target.value)
                                          : null,
                                      }
                                    : current,
                                )
                              }
                            />
                          ) : (
                            revisionLabel
                          )}
                        </td>
                        <td className="border border-slate-500 px-2 py-2 align-top">
                          {editing ? (
                            <textarea
                              aria-label={t(
                                'coreBusiness.module.overview.summary',
                              )}
                              className="min-h-20 w-full resize-y border border-slate-400 px-2 py-1"
                              value={historyDraft.summary ?? ''}
                              onChange={(event) =>
                                setHistoryDraft((current) =>
                                  current
                                    ? {
                                        ...current,
                                        summary: event.target.value,
                                      }
                                    : current,
                                )
                              }
                            />
                          ) : (
                            <span className="whitespace-pre-wrap">
                              {displayLegacyIssueRevisionSummary(
                                sourceHistory
                                  ? sourceHistory.summary
                                  : (revision?.note ?? null),
                                t,
                              )}
                            </span>
                          )}
                        </td>
                        <td className="border border-slate-500 px-2 py-2 text-center align-middle">
                          {editing ? (
                            <input
                              aria-label={t(
                                'coreBusiness.module.overview.vehicleModels',
                              )}
                              className="h-8 min-w-0 w-full border border-slate-400 px-2"
                              value={historyDraft.vehicle_models ?? ''}
                              onChange={(event) =>
                                setHistoryDraft((current) =>
                                  current
                                    ? {
                                        ...current,
                                        vehicle_models: event.target.value,
                                      }
                                    : current,
                                )
                              }
                            />
                          ) : (
                            (sourceHistory?.vehicle_models ?? '-')
                          )}
                        </td>
                        <td className="whitespace-nowrap border border-slate-500 px-2 py-2 text-center align-middle">
                          {editing ? (
                            <input
                              aria-label={t(
                                'coreBusiness.module.overview.revisedAt',
                              )}
                              className="h-8 w-full border border-slate-400 px-2"
                              type="date"
                              value={historyDraft.revised_on ?? ''}
                              onChange={(event) =>
                                setHistoryDraft((current) =>
                                  current
                                    ? {
                                        ...current,
                                        revised_on: event.target.value || null,
                                      }
                                    : current,
                                )
                              }
                            />
                          ) : (
                            formatOverviewDate(
                              sourceHistory?.revised_on ??
                                revision?.published_at ??
                                revision?.updated_at ??
                                null,
                            )
                          )}
                        </td>
                        <td className="border border-slate-500 px-2 py-2 text-center align-middle">
                          {editing ? (
                            <LegacyIssueOverviewHistoryActorEditor
                              currentUserId={currentUserId}
                              label={t('coreBusiness.module.overview.author')}
                              name={historyDraft.author_name}
                              token={token}
                              userId={historyDraft.author_user_id}
                              workspaceSlug={workspaceSlug}
                              onChange={(author_user_id, author_name) =>
                                setHistoryDraft((current) =>
                                  current
                                    ? {
                                        ...current,
                                        author_name,
                                        author_user_id,
                                      }
                                    : current,
                                )
                              }
                            />
                          ) : (
                            displayRevisionUser({
                              email: null,
                              name:
                                sourceHistory?.author_name ??
                                revision?.published_by_name ??
                                revision?.created_by_name ??
                                null,
                              t,
                            })
                          )}
                        </td>
                        <td className="border border-slate-500 px-2 py-2 text-center align-middle">
                          {editing ? (
                            <LegacyIssueOverviewHistoryActorEditor
                              currentUserId={currentUserId}
                              label={t('coreBusiness.module.overview.reviewer')}
                              name={historyDraft.reviewer_name}
                              token={token}
                              userId={historyDraft.reviewer_user_id}
                              workspaceSlug={workspaceSlug}
                              onChange={(reviewer_user_id, reviewer_name) =>
                                setHistoryDraft((current) =>
                                  current
                                    ? {
                                        ...current,
                                        reviewer_name,
                                        reviewer_user_id,
                                      }
                                    : current,
                                )
                              }
                            />
                          ) : (
                            displayRevisionUser({
                              email: revision?.reviewer_email ?? null,
                              name:
                                sourceHistory?.reviewer_name ??
                                revision?.reviewed_by_name ??
                                revision?.reviewer_name ??
                                null,
                              t,
                            })
                          )}
                        </td>
                        <td className="border border-slate-500 px-2 py-2 text-center align-middle">
                          {editing ? (
                            <LegacyIssueOverviewHistoryActorEditor
                              currentUserId={currentUserId}
                              label={t('coreBusiness.module.overview.approver')}
                              name={historyDraft.approver_name}
                              token={token}
                              userId={historyDraft.approver_user_id}
                              workspaceSlug={workspaceSlug}
                              onChange={(approver_user_id, approver_name) =>
                                setHistoryDraft((current) =>
                                  current
                                    ? {
                                        ...current,
                                        approver_name,
                                        approver_user_id,
                                      }
                                    : current,
                                )
                              }
                            />
                          ) : (
                            displayRevisionUser({
                              email: revision?.approver_email ?? null,
                              name:
                                sourceHistory?.approver_name ??
                                revision?.approved_by_name ??
                                revision?.approver_name ??
                                null,
                              t,
                            })
                          )}
                        </td>
                        <td className="border border-slate-500 px-2 py-2 text-center align-middle">
                          <div className="grid grid-cols-2 gap-1">
                            {editing ? (
                              <>
                                <button
                                  className="inline-flex h-7 min-w-0 items-center justify-center whitespace-nowrap border border-slate-500 bg-slate-900 px-1 text-[11px] font-medium text-white disabled:opacity-45"
                                  disabled={
                                    busy ||
                                    !isValidOverviewHistoryDraft(historyDraft)
                                  }
                                  type="button"
                                  onClick={() => {
                                    const summarySource = sourceHistory
                                      ? sourceHistory.summary
                                      : (revision?.note ?? null);
                                    const payload = {
                                      ...historyDraft,
                                      summary:
                                        canonicalLegacyIssueRevisionSummaryDraft(
                                          historyDraft.summary,
                                          summarySource,
                                          t,
                                        ),
                                    };
                                    const savePromise = sourceHistory
                                      ? onOverviewHistorySave(
                                          sourceHistory,
                                          payload,
                                        )
                                      : onOverviewHistoryCreate(
                                          payload,
                                          revision?.id ?? null,
                                        );
                                    void savePromise.then((saved) => {
                                      if (!saved) return;
                                      setEditingHistoryId(null);
                                      setHistoryDraft(null);
                                    });
                                  }}
                                >
                                  {t('common:actions.save')}
                                </button>
                                <button
                                  className="inline-flex h-7 min-w-0 items-center justify-center whitespace-nowrap border border-slate-500 bg-white px-1 text-[11px] font-medium text-slate-800"
                                  disabled={busy}
                                  type="button"
                                  onClick={() => {
                                    setEditingHistoryId(null);
                                    setHistoryDraft(null);
                                  }}
                                >
                                  {t('common:actions.cancel')}
                                </button>
                              </>
                            ) : (
                              <>
                                <button
                                  aria-label={t(
                                    'coreBusiness.module.meetingMinutes.openForRevision',
                                    { revision: revisionLabel },
                                  )}
                                  className="inline-flex h-7 min-w-0 items-center justify-center gap-1 whitespace-nowrap border border-slate-500 bg-white px-1 text-[11px] font-medium text-slate-800 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-45"
                                  disabled={!sourceHistory}
                                  title={t(
                                    'coreBusiness.module.meetingMinutes.openForRevision',
                                    { revision: revisionLabel },
                                  )}
                                  type="button"
                                  onClick={(event) => {
                                    if (!sourceHistory) return;
                                    meetingMinutesTriggerRef.current =
                                      event.currentTarget;
                                    setMeetingMinutesRow(row);
                                  }}
                                >
                                  <Paperclip size={13} />
                                  {t('coreBusiness.module.meetingMinutes.open')}
                                </button>
                                {canEditOverviewHistory &&
                                (sourceHistory || revision) ? (
                                  <>
                                    <button
                                      className="inline-flex h-7 min-w-0 items-center justify-center gap-1 whitespace-nowrap border border-slate-500 bg-white px-1 text-[11px] font-medium text-slate-800 hover:bg-slate-100 disabled:opacity-45"
                                      disabled={
                                        busy || editingHistoryId !== null
                                      }
                                      type="button"
                                      onClick={beginOverviewHistoryEdit}
                                    >
                                      <Pencil size={13} />
                                      {t(
                                        'coreBusiness.module.overview.editHistory',
                                      )}
                                    </button>
                                    <button
                                      className="inline-flex h-7 min-w-0 items-center justify-center gap-1 whitespace-nowrap border border-red-500 bg-white px-1 text-[11px] font-medium text-red-700 hover:bg-red-50 disabled:opacity-45"
                                      disabled={
                                        busy || editingHistoryId !== null
                                      }
                                      type="button"
                                      onClick={() => {
                                        void onOverviewHistoryDelete(
                                          sourceHistory,
                                          revision,
                                        );
                                      }}
                                    >
                                      <Trash2 size={13} />
                                      {t(
                                        'coreBusiness.module.overview.deleteHistory',
                                      )}
                                    </button>
                                  </>
                                ) : null}
                                <button
                                  className="inline-flex h-7 min-w-0 items-center justify-center gap-1 whitespace-nowrap border border-slate-500 bg-white px-1 text-[11px] font-medium text-slate-800 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-45"
                                  disabled={!revision || !previousRevision}
                                  type="button"
                                  onClick={compareWithPreviousRevision}
                                >
                                  <GitCompareArrows size={13} />
                                  {t('coreBusiness.module.overview.viewDiff')}
                                </button>
                              </>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </article>
      </div>
      <Dialog
        closeLabel={t('common:actions.close')}
        description={t('coreBusiness.module.meetingMinutes.dialogDescription')}
        dismissOnInteractOutside={false}
        maxWidth="max-w-5xl"
        open={meetingMinutesRow !== null}
        title={t('coreBusiness.module.meetingMinutes.dialogTitle', {
          revision: meetingMinutesRow
            ? legacyIssueOverviewRevisionLabel(meetingMinutesRow, t)
            : '-',
        })}
        onOpenChange={(open) => {
          if (!open) {
            setMeetingMinutesRow(null);
            window.setTimeout(() => {
              meetingMinutesTriggerRef.current?.focus();
            }, 0);
          }
        }}
      >
        {meetingMinutesRow?.sourceHistory ? (
          <LegacyIssueRevisionMeetingAttachmentsPanel
            datasetKey={datasetKey}
            focusedHistoryId={meetingMinutesRow.sourceHistory.id}
            key={meetingMinutesRow.sourceHistory.id}
            rows={[meetingMinutesRow]}
            showPageHeader={false}
            token={token}
            viewKey={viewKey}
            workspaceSlug={workspaceSlug}
          />
        ) : null}
      </Dialog>
    </>
  );
}

function LegacyIssueOverviewHistoryActorEditor({
  currentUserId,
  label,
  name,
  onChange,
  token,
  userId,
  workspaceSlug,
}: {
  currentUserId: string | null;
  label: string;
  name: string | null;
  onChange: (userId: string | null, name: string | null) => void;
  token: string | null | undefined;
  userId: string | null;
  workspaceSlug: string;
}) {
  const { t } = useTranslation(['apps']);
  const selectedUser: RevisionUserOption | null = userId
    ? {
        display_name: name,
        email: '',
        full_name: name,
        id: userId,
      }
    : null;
  return (
    <div className="flex w-full min-w-0 flex-col gap-1">
      <LegacyIssueRevisionUserSelect
        clearLabel={t('coreBusiness.module.overview.clearEmployeeSelection')}
        currentUserId={currentUserId}
        disabled={false}
        fullWidth
        hideLabel
        label={label}
        placeholder={t('coreBusiness.module.overview.selectEmployee')}
        selectedUser={selectedUser}
        token={token}
        workspaceSlug={workspaceSlug}
        onChange={(selectedUserId, selectedOption) =>
          onChange(
            selectedUserId,
            selectedOption ? displayRevisionUserOption(selectedOption) : name,
          )
        }
      />
      <input
        aria-label={t('coreBusiness.module.overview.directNameInput', {
          role: label,
        })}
        className="h-8 min-w-0 w-full border border-slate-400 px-2"
        maxLength={255}
        placeholder={t('coreBusiness.module.overview.directNamePlaceholder')}
        value={name ?? ''}
        onChange={(event) => onChange(null, event.target.value || null)}
      />
    </div>
  );
}

function LegacyIssueRevisionUserSelect({
  clearLabel,
  currentUserId,
  disabled,
  fullWidth = false,
  hideLabel = false,
  label,
  onChange,
  placeholder,
  selectedUser,
  token,
  workspaceSlug,
}: {
  clearLabel?: string;
  currentUserId: string | null;
  disabled: boolean;
  fullWidth?: boolean;
  hideLabel?: boolean;
  label: string;
  onChange: (
    userId: string | null,
    selectedUser?: RevisionUserOption | null,
  ) => void;
  placeholder: string;
  selectedUser: RevisionUserOption | null;
  token: string | null | undefined;
  workspaceSlug: string;
}) {
  const { t } = useTranslation(['apps']);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [users, setUsers] = useState<DmUser[]>([]);
  const [searching, setSearching] = useState(false);
  const selectedLabel = selectedUser
    ? displayRevisionUserOption(selectedUser)
    : placeholder;
  const userOptions = useMemo(
    () => mergeRevisionUserOptions(users, selectedUser, null),
    [selectedUser, users],
  );
  const candidates = useMemo(
    () =>
      selectUserOptionsForPicker({
        currentUserId,
        limit: 20,
        query,
        users: userOptions,
      }),
    [currentUserId, query, userOptions],
  );

  useEffect(() => {
    if (!open || disabled || !token || !workspaceSlug) {
      setUsers([]);
      setSearching(false);
      return undefined;
    }

    let canceled = false;
    setSearching(true);
    const timeout = window.setTimeout(() => {
      searchDmUsers(token, query, {
        includeCurrent: true,
        limit: 40,
        workspaceKey: workspaceSlug,
      })
        .then((items) => {
          if (!canceled) {
            setUsers(items);
          }
        })
        .catch(() => {
          if (!canceled) {
            setUsers([]);
          }
        })
        .finally(() => {
          if (!canceled) {
            setSearching(false);
          }
        });
    }, 180);

    return () => {
      canceled = true;
      window.clearTimeout(timeout);
    };
  }, [disabled, open, query, token, workspaceSlug]);

  useEffect(() => {
    if (disabled) {
      setOpen(false);
    }
  }, [disabled]);

  return (
    <div
      className={cn(
        'relative inline-flex h-9 shrink-0 items-center gap-1.5 app-text-caption',
        fullWidth && 'w-full min-w-0',
      )}
    >
      {!hideLabel ? (
        <span className="font-medium text-app-ink/60">{label}</span>
      ) : null}
      <button
        aria-label={label}
        aria-expanded={open}
        aria-haspopup="dialog"
        className={cn(
          'app-control h-9 justify-between text-left focus-visible:border-app-accent focus-visible:ring-2 focus-visible:ring-app-accent/20',
          fullWidth ? 'w-full min-w-0 px-2' : 'w-40 px-3',
        )}
        disabled={disabled}
        type="button"
        onClick={() => {
          setOpen((current) => !current);
          setQuery('');
        }}
      >
        <span
          className={cn(
            'min-w-0 truncate',
            selectedUser ? 'text-app-ink' : 'text-app-ink/40',
          )}
        >
          {selectedLabel}
        </span>
        {!fullWidth ? (
          <ChevronDown size={13} className="shrink-0 text-app-ink/45" />
        ) : null}
      </button>
      {open && !disabled ? (
        <div
          className="fixed inset-0 z-[9999] flex items-start justify-center bg-black/30 px-4 py-[12vh]"
          role="presentation"
        >
          <button
            aria-label={t('coreBusiness.module.actions.close')}
            className="absolute inset-0 cursor-default"
            type="button"
            onClick={() => setOpen(false)}
          />
          <div
            aria-label={label}
            className="relative z-10 flex w-full max-w-md flex-col overflow-hidden rounded-lg border border-app-border bg-app-bg shadow-2xl"
            data-ui-floating-layer
            role="dialog"
          >
            <div className="flex h-11 items-center justify-between border-b border-app-border px-3">
              <div className="app-text-body-sm font-semibold text-app-ink">
                {label}
              </div>
              <button
                aria-label={t('coreBusiness.module.actions.close')}
                className="inline-flex size-7 items-center justify-center rounded-md text-app-ink/45 hover:bg-app-surface-hover hover:text-app-ink"
                type="button"
                onClick={() => setOpen(false)}
              >
                <X size={14} />
              </button>
            </div>
            <div className="border-b border-app-border p-3">
              <div className="flex h-9 items-center gap-2 rounded-md border border-app-border bg-app-surface-sidebar px-2">
                <Search size={14} className="shrink-0 text-app-ink/40" />
                <input
                  autoFocus
                  aria-label={t(
                    'coreBusiness.module.overview.userSearchPlaceholder',
                  )}
                  className="min-w-0 flex-1 bg-transparent app-text-body-sm text-app-ink outline-none placeholder:text-app-ink/40"
                  placeholder={t(
                    'coreBusiness.module.overview.userSearchPlaceholder',
                  )}
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Escape') {
                      setOpen(false);
                    }
                  }}
                />
                {query ? (
                  <button
                    aria-label={t('coreBusiness.module.overview.removeUser', {
                      name: query,
                    })}
                    className="text-app-ink/40 hover:text-app-ink"
                    type="button"
                    onClick={() => setQuery('')}
                  >
                    <X size={12} />
                  </button>
                ) : null}
              </div>
            </div>
            <div className="max-h-[min(24rem,55vh)] overflow-y-auto p-2">
              <button
                className="app-menu-item text-app-ink/55"
                type="button"
                onClick={() => {
                  onChange(null, null);
                  setOpen(false);
                }}
              >
                {clearLabel ?? placeholder}
              </button>
              {candidates.map((user) => (
                <UserOptionRow
                  currentUserId={currentUserId}
                  currentUserLabel={t(
                    'coreBusiness.module.overview.currentUser',
                  )}
                  density="compact"
                  key={user.id}
                  selected={selectedUser?.id === user.id}
                  user={user}
                  onClick={() => {
                    onChange(user.id, user);
                    setOpen(false);
                  }}
                />
              ))}
              {candidates.length === 0 ? (
                <p className="app-text-caption px-3 py-3 text-app-ink/40">
                  {searching
                    ? t('coreBusiness.module.overview.userSearching')
                    : query.trim()
                      ? t('coreBusiness.module.overview.noUserMatch')
                      : t('coreBusiness.module.overview.userSearchPrompt')}
                </p>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function mergeRevisionUserOptions(
  users: DmUser[],
  reviewerUser: RevisionUserOption | null,
  approverUser: RevisionUserOption | null,
): RevisionUserOption[] {
  const options = new Map<string, RevisionUserOption>();
  for (const user of users) {
    options.set(user.id, {
      display_name: user.display_name ?? null,
      email: user.email ?? '',
      full_name: user.full_name ?? null,
      id: user.id,
    });
  }
  for (const user of [reviewerUser, approverUser]) {
    if (user) {
      options.set(user.id, user);
    }
  }
  return Array.from(options.values()).sort((left, right) =>
    displayRevisionUserOption(left).localeCompare(
      displayRevisionUserOption(right),
    ),
  );
}

function displayRevisionUserOption(user: RevisionUserOption): string {
  return user.display_name || user.full_name || user.email || user.id;
}

function OverviewTableHeader({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <th
      className={cn(
        'border border-slate-500 bg-slate-100 px-2 py-2 text-center font-semibold text-slate-950',
        'whitespace-nowrap',
        className,
      )}
    >
      {children}
    </th>
  );
}

type RevisionUserOption = {
  id: string;
  display_name: string | null;
  email: string;
  full_name: string | null;
};

function revisionReviewerUser(
  revision: LegacyIssueRevision,
): RevisionUserOption | null {
  if (!revision.reviewer_id) return null;
  return {
    display_name: revision.reviewer_name,
    email: revision.reviewer_email ?? '',
    full_name: revision.reviewer_name,
    id: revision.reviewer_id,
  };
}

function revisionApproverUser(
  revision: LegacyIssueRevision,
): RevisionUserOption | null {
  if (!revision.approver_id) return null;
  return {
    display_name: revision.approver_name,
    email: revision.approver_email ?? '',
    full_name: revision.approver_name,
    id: revision.approver_id,
  };
}

export function isLegacyIssueRevisionReadyToPublish(
  revision: Pick<
    LegacyIssueRevision,
    'approved_at' | 'approver_id' | 'reviewed_at' | 'reviewer_id'
  >,
): boolean {
  return Boolean(
    revision.reviewer_id &&
      revision.approver_id &&
      revision.reviewed_at &&
      revision.approved_at,
  );
}

type LegacyIssueRevisionAssigneeRole = 'approver' | 'reviewer';

export function canEditLegacyIssueRevisionAssignee({
  revision,
  role,
}: {
  revision: Pick<LegacyIssueRevision, 'approved_at' | 'reviewed_at' | 'status'>;
  role: LegacyIssueRevisionAssigneeRole;
}): boolean {
  if (revision.status !== 'draft') return false;
  if (role === 'reviewer') return !revision.reviewed_at;
  return !revision.approved_at;
}

export function isLegacyIssueRevisionAssigneeChangeBlocked({
  approverId,
  reviewerId,
  revision,
}: {
  approverId: string | null;
  reviewerId: string | null;
  revision: Pick<
    LegacyIssueRevision,
    'approved_at' | 'approver_id' | 'reviewed_at' | 'reviewer_id'
  >;
}): boolean {
  const reviewerChanged = reviewerId !== revision.reviewer_id;
  const approverChanged = approverId !== revision.approver_id;
  return Boolean(
    (reviewerChanged && revision.reviewed_at) ||
      (approverChanged && revision.approved_at),
  );
}

export function shouldConfirmLegacyIssueRevisionAssigneeChange({
  approverId,
  reviewerId,
  revision,
}: {
  approverId: string | null;
  reviewerId: string | null;
  revision: Pick<
    LegacyIssueRevision,
    | 'approval_requested_at'
    | 'approved_at'
    | 'approver_id'
    | 'review_requested_at'
    | 'reviewed_at'
    | 'reviewer_id'
  >;
}): boolean {
  const reviewerChanged = reviewerId !== revision.reviewer_id;
  const approverChanged = approverId !== revision.approver_id;
  return Boolean(
    (reviewerChanged &&
      revision.review_requested_at &&
      !revision.reviewed_at) ||
      (approverChanged &&
        revision.approval_requested_at &&
        !revision.approved_at),
  );
}

export function sortedPublishedLegacyIssueRevisions(
  revisions: LegacyIssueRevision[],
): LegacyIssueRevision[] {
  return revisions
    .filter(
      (revision) =>
        isVisibleLegacyIssueRevision(revision) &&
        revision.status === 'published',
    )
    .sort((left, right) => (right.revision_no ?? 0) - (left.revision_no ?? 0));
}

export interface LegacyIssueRevisionOverviewRow {
  id: string;
  revision: LegacyIssueRevision | null;
  sourceHistory: LegacyIssueRevisionOverviewHistory | null;
}

export function legacyIssueOverviewRevisionLabel(
  row: LegacyIssueRevisionOverviewRow,
  translate: (key: string, options?: Record<string, unknown>) => string,
): string {
  if (row.sourceHistory) {
    return translate('coreBusiness.revision.publishedRevision', {
      revision:
        row.sourceHistory.revision_label ??
        row.sourceHistory.revision_no ??
        '-',
    });
  }
  return row.revision
    ? formatLegacyIssueRevisionLabel(row.revision, translate)
    : '-';
}

export function isValidOverviewHistoryDraft(
  draft: LegacyIssueRevisionOverviewHistoryUpdate,
): boolean {
  return (
    draft.revision_no === null ||
    (Number.isInteger(draft.revision_no) &&
      draft.revision_no >= 0 &&
      draft.revision_no <= MAX_OVERVIEW_REVISION_NO)
  );
}

const LEGACY_ISSUE_SYSTEM_REVISION_SUMMARY_KEYS = {
  'Initial compressor source import':
    'coreBusiness.module.overview.initialCompressorSourceImport',
  'Initial revision': 'coreBusiness.module.overview.initialRevision',
} as const;

export function displayLegacyIssueRevisionSummary(
  summary: string | null | undefined,
  translate: (key: string) => string,
): string {
  if (!summary?.trim()) return '-';
  const translationKey =
    LEGACY_ISSUE_SYSTEM_REVISION_SUMMARY_KEYS[
      summary.trim() as keyof typeof LEGACY_ISSUE_SYSTEM_REVISION_SUMMARY_KEYS
    ];
  return translationKey ? translate(translationKey) : summary;
}

function editableLegacyIssueRevisionSummary(
  summary: string | null | undefined,
  translate: (key: string) => string,
): string | null {
  return summary?.trim()
    ? displayLegacyIssueRevisionSummary(summary, translate)
    : null;
}

function canonicalLegacyIssueRevisionSummaryDraft(
  draftSummary: string | null,
  sourceSummary: string | null | undefined,
  translate: (key: string) => string,
): string | null {
  return draftSummary ===
    editableLegacyIssueRevisionSummary(sourceSummary, translate)
    ? (sourceSummary ?? null)
    : draftSummary;
}

function overviewHistoryDraftForRow({
  history,
  revision,
}: {
  history: LegacyIssueRevisionOverviewHistory | null;
  revision: LegacyIssueRevision | null;
}): LegacyIssueRevisionOverviewHistoryUpdate {
  if (history) {
    return {
      approver_name: history.approver_name,
      approver_user_id: history.approver_user_id,
      author_name: history.author_name,
      author_user_id: history.author_user_id,
      revised_on: history.revised_on,
      reviewer_name: history.reviewer_name,
      reviewer_user_id: history.reviewer_user_id,
      revision_no: history.revision_no,
      summary: history.summary,
      vehicle_models: history.vehicle_models,
    };
  }
  return {
    approver_name:
      revision?.approved_by_name ?? revision?.approver_name ?? null,
    approver_user_id: null,
    author_name:
      revision?.published_by_name ?? revision?.created_by_name ?? null,
    author_user_id: null,
    revised_on:
      revision?.published_at?.slice(0, 10) ??
      revision?.updated_at?.slice(0, 10) ??
      null,
    reviewer_name:
      revision?.reviewed_by_name ?? revision?.reviewer_name ?? null,
    reviewer_user_id: null,
    revision_no: revision?.revision_no ?? null,
    summary: revision?.note ?? null,
    vehicle_models: null,
  };
}

export function buildLegacyIssueRevisionOverviewRows(
  revisions: LegacyIssueRevision[],
  overviewHistory: LegacyIssueRevisionOverviewHistory[],
): LegacyIssueRevisionOverviewRow[] {
  const publishedRevisions = sortedPublishedLegacyIssueRevisions(revisions);
  const revisionByNumber = new Map(
    publishedRevisions
      .filter((revision) => revision.revision_no !== null)
      .map((revision) => [revision.revision_no as number, revision]),
  );
  const revisionById = new Map(
    publishedRevisions.map((revision) => [revision.id, revision]),
  );
  const matchedRevisionIds = new Set<string>();
  const sourceRows = [...overviewHistory]
    .sort(
      (left, right) =>
        left.sort_order - right.sort_order ||
        (left.source_row ?? 0) - (right.source_row ?? 0),
    )
    .flatMap((sourceHistory) => {
      if (sourceHistory.deleted_at && !sourceHistory.linked_revision_id) {
        return [];
      }
      const revision = sourceHistory.linked_revision_id
        ? (revisionById.get(sourceHistory.linked_revision_id) ?? null)
        : sourceHistory.revision_no === null
          ? null
          : (revisionByNumber.get(sourceHistory.revision_no) ?? null);
      if (revision) matchedRevisionIds.add(revision.id);
      if (sourceHistory.deleted_at) return [];
      return [
        {
          id: `source-${sourceHistory.id}`,
          revision,
          sourceHistory,
        },
      ];
    });
  const unmatchedRevisionRows = publishedRevisions
    .filter((revision) => !matchedRevisionIds.has(revision.id))
    .map((revision) => ({
      id: `revision-${revision.id}`,
      revision,
      sourceHistory: null,
    }));
  return [...unmatchedRevisionRows, ...sourceRows].sort((left, right) => {
    const leftRevisionNo =
      left.sourceHistory?.revision_no ?? left.revision?.revision_no ?? null;
    const rightRevisionNo =
      right.sourceHistory?.revision_no ?? right.revision?.revision_no ?? null;
    if (leftRevisionNo === null && rightRevisionNo === null) return 0;
    if (leftRevisionNo === null) return 1;
    if (rightRevisionNo === null) return -1;
    return rightRevisionNo - leftRevisionNo;
  });
}

function formatLegacyIssueRevisionLabel(
  revision: LegacyIssueRevision,
  translate: (key: string, options?: Record<string, unknown>) => string,
): string {
  if (revision.status === 'draft') {
    return translate('coreBusiness.revision.draft');
  }
  return translate('coreBusiness.revision.publishedRevision', {
    revision: revision.revision_no ?? '-',
  });
}

function displayRevisionUser({
  email,
  name,
  t,
}: {
  email: string | null;
  name: string | null;
  t: (key: string, options?: Record<string, unknown>) => string;
}): string {
  return name || email || t('coreBusiness.grid.emptyValue');
}

function formatOverviewDate(value: string | null): string {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString();
}

function LegacyIssueDatasetGrid({
  allowRowCreate,
  allowRowDelete,
  blankRowCount,
  blankRowDefaultValues,
  defaultColumnOrder,
  defaultHiddenColumnKeys,
  gridPreference,
  gridPreferenceControlsDisabled,
  gridPreferenceStatus,
  changedCellKeys,
  definition,
  detailOpen,
  editable,
  loading,
  onAddBlankRows,
  onCreateRows,
  onDownloadAttachment,
  onEditCell,
  onDeleteRows,
  onGridPreferenceChange,
  onGridPreferenceReset,
  onGridPreferenceRetry,
  onOpenRecord,
  onVisibleColumnKeysChange,
  onVisibleRowsChange,
  onRemoveBlankRows,
  onEditCells,
  records,
  revisionKey,
  layoutId,
  toolbarLeading,
  toolbarTrailing,
}: {
  allowRowCreate: boolean;
  allowRowDelete: boolean;
  blankRowCount: number;
  blankRowDefaultValues: Record<string, string | null>;
  defaultColumnOrder: string[];
  defaultHiddenColumnKeys: string[];
  gridPreference: LegacyIssueGridPreferenceValue | null | undefined;
  gridPreferenceControlsDisabled: boolean;
  gridPreferenceStatus: LegacyIssueGridPreferenceStatus;
  changedCellKeys: string[];
  definition: LegacyIssueDatasetDefinition | null;
  detailOpen: boolean;
  editable: boolean;
  loading: boolean;
  onAddBlankRows: (count?: number) => void;
  onCreateRows: (params: {
    values: Array<Record<string, string | null>>;
  }) => number | void | Promise<number | void>;
  onDeleteRows: (records: LegacyIssueDatasetRecord[]) => void | Promise<void>;
  onEditCell: (params: {
    columnKey: string;
    record: LegacyIssueDatasetRecord;
    value: string | null;
  }) => void | Promise<void>;
  onEditCells: (params: {
    edits: Array<{
      columnKey: string;
      record: LegacyIssueDatasetRecord;
      value: LegacyIssueEditableValue;
    }>;
  }) => void | Promise<void>;
  onDownloadAttachment: (attachment: LegacyIssueDatasetAttachment) => void;
  onGridPreferenceChange: (preference: LegacyIssueGridPreferenceValue) => void;
  onGridPreferenceReset: () => void;
  onGridPreferenceRetry: () => void;
  onOpenRecord: (record: LegacyIssueDatasetRecord) => void;
  onVisibleColumnKeysChange: (layout: LegacyIssueGridColumnLayout) => void;
  onVisibleRowsChange: (layout: LegacyIssueGridRowLayout) => void;
  onRemoveBlankRows: (rowIndexes: number[]) => void;
  records: LegacyIssueDatasetRecord[];
  revisionKey: string;
  layoutId: string;
  toolbarLeading?: ReactNode;
  toolbarTrailing?: ReactNode;
}) {
  const { t, i18n } = useTranslation(['apps', 'common']);
  const [referencePicker, setReferencePicker] =
    useState<LegacyIssueReferencePickerState>(null);
  const fieldsByKey = useMemo(() => {
    return new Map(
      (definition?.fields ?? []).map((field) => [field.key, field]),
    );
  }, [definition?.fields]);
  const defaultHiddenColumnKeySet = useMemo(
    () => new Set(defaultHiddenColumnKeys),
    [defaultHiddenColumnKeys],
  );

  const columns = useMemo<LegacyIssueGridColumn[]>(() => {
    const fields = definition?.fields ?? [];
    const groupLabels = i18n.language.startsWith('ko')
      ? (definition?.group_labels_ko ?? {})
      : (definition?.group_labels_en ?? {});
    return [
      ...fields.map((field) => ({
        allowMultiple: field.allow_multiple,
        group: field.group_key ? groupLabels[field.group_key] : undefined,
        inputKind: field.field_type === 'date' ? ('date' as const) : undefined,
        key: field.key,
        options:
          field.field_type === 'select' && !field.allow_multiple
            ? field.options
            : undefined,
        referenceKind: legacyIssueReferenceKindForField(field),
        required: field.required,
        title: displayConfiguredIssueFieldLabel({
          groupLabel: field.group_key
            ? groupLabels[field.group_key]
            : undefined,
          label: i18n.language.startsWith('ko')
            ? field.label_ko
            : field.label_en,
        }),
        tooltip:
          field.key === 'registrant'
            ? t('coreBusiness.module.grid.registrantDefinition')
            : undefined,
        width: defaultColumnWidth(field.key),
      })),
      {
        group: undefined,
        key: 'primary_attachment',
        title: t('coreBusiness.module.fields.primary_attachment'),
        width: 180,
      },
    ].filter((column) => !defaultHiddenColumnKeySet.has(column.key));
  }, [defaultHiddenColumnKeySet, definition, i18n.language, t]);

  const handleReferenceCellEditRequest = useCallback(
    ({
      columnKey,
      record,
    }: {
      allowMultiple: boolean;
      columnKey: string;
      record: LegacyIssueDatasetRecord;
      referenceKind: LegacyIssueGridReferenceKind;
    }) => {
      const field = fieldsByKey.get(columnKey);
      if (!field || !legacyIssueReferenceKindForField(field)) return;
      setReferencePicker({ field, record });
    },
    [fieldsByKey],
  );

  const getCellValue = useCallback(
    (record: LegacyIssueDatasetRecord, columnKey: string) => {
      if (columnKey === 'primary_attachment') {
        return record.primary_attachment?.filename;
      }
      return displayLegacyIssueFieldValue(record.values[columnKey]);
    },
    [],
  );

  const handleCellClick = useCallback(
    ({
      columnKey,
      record,
    }: {
      columnKey: string;
      record: LegacyIssueDatasetRecord;
    }) => {
      if (columnKey === 'primary_attachment' && record.primary_attachment) {
        onDownloadAttachment(record.primary_attachment);
        return true;
      }
      return false;
    },
    [onDownloadAttachment],
  );

  const readonlyColumnKeys = useMemo(() => {
    if (!editable) return columns.map((column) => column.key);
    return [
      'primary_attachment',
      ...fieldsReadonlyKeys(definition?.fields ?? []),
    ];
  }, [columns, definition?.fields, editable]);

  return (
    <>
      <LegacyIssueDataGrid
        blankRowCount={blankRowCount}
        blankRowDefaultValues={blankRowDefaultValues}
        columns={columns}
        changedCellKeys={changedCellKeys}
        defaultColumnOrder={defaultColumnOrder}
        detailOpen={detailOpen}
        emptyLabel={t('coreBusiness.module.grid.empty')}
        getCellValue={getCellValue}
        layoutId={layoutId}
        loading={loading}
        loadingLabel={t('common:feedback.loading')}
        onCellClick={handleCellClick}
        onCellBatchEdit={editable ? onEditCells : undefined}
        onCellEdit={editable ? onEditCell : undefined}
        onReferenceCellEditRequest={
          editable ? handleReferenceCellEditRequest : undefined
        }
        onAddBlankRows={allowRowCreate ? onAddBlankRows : undefined}
        onCreateRows={allowRowCreate ? onCreateRows : undefined}
        onDeleteRows={allowRowDelete ? onDeleteRows : undefined}
        onPreferenceChange={onGridPreferenceChange}
        onPreferenceReset={onGridPreferenceReset}
        onPreferenceRetry={onGridPreferenceRetry}
        onRemoveBlankRows={allowRowCreate ? onRemoveBlankRows : undefined}
        onRecordOpen={onOpenRecord}
        onVisibleColumnKeysChange={onVisibleColumnKeysChange}
        onVisibleRowsChange={onVisibleRowsChange}
        readonlyColumnKeys={readonlyColumnKeys}
        records={records}
        revisionKey={revisionKey}
        preference={gridPreference}
        preferenceControlsDisabled={gridPreferenceControlsDisabled}
        preferenceStatus={gridPreferenceStatus}
        toolbarLeading={
          <>
            {toolbarLeading}
            {changedCellKeys.length > 0 ? (
              <span
                className="inline-flex h-7 shrink-0 items-center gap-1.5 rounded-md border border-app-warning-border bg-app-warning-bg px-2 app-text-caption text-app-warning-text"
                role="status"
              >
                <span
                  aria-hidden="true"
                  className="size-3 rounded-sm border border-app-warning-border bg-app-warning-bg"
                />
                {t('coreBusiness.module.grid.changedCellCount', {
                  count: changedCellKeys.length,
                })}
              </span>
            ) : null}
          </>
        }
        toolbarTrailing={toolbarTrailing}
      />
      {referencePicker ? (
        <LegacyIssueReferencePickerDialog
          allowMultiple={referencePicker.field.allow_multiple}
          fieldLabel={
            i18n.language.startsWith('ko')
              ? referencePicker.field.label_ko
              : referencePicker.field.label_en
          }
          referenceKind={
            legacyIssueReferenceKindForField(referencePicker.field) ?? 'orgUnit'
          }
          value={
            referencePicker.record.values[referencePicker.field.key] ?? null
          }
          onClose={() => setReferencePicker(null)}
          onCommit={(nextValue) => {
            void onEditCells({
              edits: [
                {
                  columnKey: referencePicker.field.key,
                  record: referencePicker.record,
                  value: nextValue,
                },
              ],
            });
            setReferencePicker(null);
          }}
        />
      ) : null}
    </>
  );
}

function revisionGridKey(revision: LegacyIssueRevision | null): string {
  if (!revision) return 'none';
  return `${revision.id}:${revision.status}:${revision.revision_no ?? ''}`;
}

export function isPendingCreateRecordId(recordId: string): boolean {
  return recordId.startsWith(PENDING_CREATE_RECORD_PREFIX);
}

export function mergeLegacyIssueRecordValues(
  currentValues: Record<string, LegacyIssueEditableValue | undefined>,
  incomingValues: Record<string, LegacyIssueEditableValue | undefined>,
): Record<string, LegacyIssueFieldValue> {
  const next: Record<string, LegacyIssueFieldValue> = {};
  for (const [key, value] of Object.entries(currentValues)) {
    const normalizedValue = normalizeLegacyIssueDraftValue(value);
    if (normalizedValue !== null) {
      next[key] = normalizedValue;
    }
  }
  for (const [key, value] of Object.entries(incomingValues)) {
    const normalizedValue = normalizeLegacyIssueDraftValue(value);
    if (normalizedValue === null) {
      delete next[key];
    } else {
      next[key] = normalizedValue;
    }
  }
  return next;
}

function applyLegacyIssueRecordValuePatch(
  record: LegacyIssueDatasetRecord,
  patch: Record<string, LegacyIssueEditableValue>,
): LegacyIssueDatasetRecord {
  return {
    ...record,
    updated_at: new Date().toISOString(),
    values: mergeLegacyIssueRecordValues(record.values, patch),
  };
}

export function mergePendingRecordEditPatch({
  baseValues,
  currentPatch,
  patch,
}: {
  baseValues: Record<string, LegacyIssueEditableValue | undefined>;
  currentPatch: Record<string, LegacyIssueEditableValue>;
  patch: Record<string, LegacyIssueEditableValue>;
}): Record<string, LegacyIssueEditableValue> {
  const next = { ...currentPatch };
  for (const [key, value] of Object.entries(patch)) {
    const normalizedValue = normalizeLegacyIssueDraftValue(value);
    const normalizedBaseValue = normalizeLegacyIssueDraftValue(baseValues[key]);
    if (legacyIssueFieldValuesEqual(normalizedValue, normalizedBaseValue)) {
      delete next[key];
    } else {
      next[key] = normalizedValue;
    }
  }
  return next;
}

export function countLegacyIssuePendingDraftChanges({
  pendingAttachmentEditsByRecordId = {},
  pendingAttachmentDraftsByRecordId = {},
  pendingCreateRecords,
  pendingRecordEdits,
}: {
  pendingAttachmentEditsByRecordId?: PendingAttachmentEditsByRecordId;
  pendingAttachmentDraftsByRecordId?: PendingAttachmentDraftsByRecordId;
  pendingCreateRecords: LegacyIssueDatasetRecord[];
  pendingRecordEdits: PendingRecordEdits;
}): number {
  return (
    pendingCreateRecords.length +
    Object.values(pendingRecordEdits).reduce(
      (count, values) => count + Object.keys(values).length,
      0,
    ) +
    countPendingAttachmentDrafts(pendingAttachmentDraftsByRecordId) +
    countPendingAttachmentEdits(pendingAttachmentEditsByRecordId)
  );
}

export function hasLegacyIssuePendingDraftChanges({
  pendingAttachmentEditsByRecordId = {},
  pendingAttachmentDraftsByRecordId = {},
  pendingCreateRecords,
  pendingRecordEdits,
}: {
  pendingAttachmentEditsByRecordId?: PendingAttachmentEditsByRecordId;
  pendingAttachmentDraftsByRecordId?: PendingAttachmentDraftsByRecordId;
  pendingCreateRecords: LegacyIssueDatasetRecord[];
  pendingRecordEdits: PendingRecordEdits;
}): boolean {
  return (
    countLegacyIssuePendingDraftChanges({
      pendingAttachmentEditsByRecordId,
      pendingAttachmentDraftsByRecordId,
      pendingCreateRecords,
      pendingRecordEdits,
    }) > 0
  );
}

export function countPendingAttachmentDrafts(
  draftsByRecordId: PendingAttachmentDraftsByRecordId,
): number {
  return Object.values(draftsByRecordId).reduce(
    (count, drafts) => count + drafts.length,
    0,
  );
}

export function countPendingAttachmentEdits(
  editsByRecordId: PendingAttachmentEditsByRecordId,
): number {
  return Object.values(editsByRecordId).reduce(
    (count, edits) =>
      count +
      edits.deletedAttachmentIds.length +
      Object.keys(edits.descriptions).length +
      (edits.primaryAttachmentId ? 1 : 0),
    0,
  );
}

export function mapLegacyIssueCreatedRecordsByClientId(
  createdRecords: LegacyIssueDatasetRecordBatchCreated[],
): Map<string, LegacyIssueDatasetRecord> {
  return new Map(
    createdRecords
      .filter((item) => item.client_row_id)
      .map((item) => [item.client_row_id as string, item.record]),
  );
}

function updatePendingAttachmentDraftsForRecord(
  draftsByRecordId: PendingAttachmentDraftsByRecordId,
  recordId: string,
  updater: (drafts: PendingAttachmentDraft[]) => PendingAttachmentDraft[],
): PendingAttachmentDraftsByRecordId {
  const nextDrafts = updater(draftsByRecordId[recordId] ?? []);
  if (nextDrafts.length === 0) {
    const { [recordId]: _removed, ...remaining } = draftsByRecordId;
    return remaining;
  }
  return {
    ...draftsByRecordId,
    [recordId]: nextDrafts,
  };
}

function updatePendingAttachmentDraft(
  draftsByRecordId: PendingAttachmentDraftsByRecordId,
  recordId: string,
  attachmentId: string,
  updater: (draft: PendingAttachmentDraft) => PendingAttachmentDraft,
): PendingAttachmentDraftsByRecordId {
  return updatePendingAttachmentDraftsForRecord(
    draftsByRecordId,
    recordId,
    (drafts) =>
      drafts.map((draft) =>
        draft.id === attachmentId ? updater(draft) : draft,
      ),
  );
}

function updatePendingAttachmentEditsForRecord(
  editsByRecordId: PendingAttachmentEditsByRecordId,
  recordId: string,
  updater: (current: PendingAttachmentEdits) => PendingAttachmentEdits,
): PendingAttachmentEditsByRecordId {
  const nextEdits = updater(
    editsByRecordId[recordId] ?? {
      deletedAttachmentIds: [],
      descriptions: {},
    },
  );
  if (
    nextEdits.deletedAttachmentIds.length === 0 &&
    Object.keys(nextEdits.descriptions).length === 0 &&
    !nextEdits.primaryAttachmentId
  ) {
    const { [recordId]: _removed, ...remaining } = editsByRecordId;
    return remaining;
  }
  return { ...editsByRecordId, [recordId]: nextEdits };
}

function replacePendingAttachmentDraftsForRecord(
  draftsByRecordId: PendingAttachmentDraftsByRecordId,
  recordId: string,
  drafts: PendingAttachmentDraft[],
): PendingAttachmentDraftsByRecordId {
  return updatePendingAttachmentDraftsForRecord(
    draftsByRecordId,
    recordId,
    () => drafts,
  );
}

function replacePendingAttachmentEditsForRecord(
  editsByRecordId: PendingAttachmentEditsByRecordId,
  recordId: string,
  edits: PendingAttachmentEdits | undefined,
): PendingAttachmentEditsByRecordId {
  if (!edits) {
    const { [recordId]: _removed, ...remaining } = editsByRecordId;
    return remaining;
  }
  return updatePendingAttachmentEditsForRecord(
    editsByRecordId,
    recordId,
    () => edits,
  );
}

function omitPendingAttachmentDrafts(
  draftsByRecordId: PendingAttachmentDraftsByRecordId,
  recordIds: ReadonlySet<string>,
): PendingAttachmentDraftsByRecordId {
  return Object.fromEntries(
    Object.entries(draftsByRecordId).filter(
      ([recordId]) => !recordIds.has(recordId),
    ),
  );
}

export function buildLegacyIssueDraftBatchPayload({
  pendingCreateRecords,
  pendingRecordEdits,
}: {
  pendingCreateRecords: LegacyIssueDatasetRecord[];
  pendingRecordEdits: PendingRecordEdits;
}): {
  creates: LegacyIssueDatasetRecordBatchCreate[];
  updates: LegacyIssueDatasetRecordBatchUpdate[];
} {
  return {
    creates: pendingCreateRecords.map((record) => ({
      client_row_id: record.id,
      values: record.values,
    })),
    updates: Object.entries(pendingRecordEdits)
      .filter(([, values]) => Object.keys(values).length > 0)
      .map(([recordId, values]) => ({
        record_id: recordId,
        values,
      })),
  };
}

export function applyPendingDraftChangesToLoadedRecords({
  records,
  pendingCreateRecords,
  pendingRecordEdits,
}: {
  records: LegacyIssueDatasetRecord[];
  pendingCreateRecords: LegacyIssueDatasetRecord[];
  pendingRecordEdits: PendingRecordEdits;
}): LegacyIssueDatasetRecord[] {
  return [
    ...pendingCreateRecords,
    ...records.map((record) => {
      const patch = pendingRecordEdits[record.id];
      return patch ? applyLegacyIssueRecordValuePatch(record, patch) : record;
    }),
  ];
}

export function buildLegacyIssueDraftChangedCellKeys({
  compareResult,
  records,
}: {
  compareResult: LegacyIssueRevisionCompareResponse;
  records: LegacyIssueDatasetRecord[];
}): string[] {
  const recordIdByStableId = new Map(
    records.map((record) => [record.stable_record_id ?? record.id, record.id]),
  );
  const changedCellKeys = new Set<string>();
  for (const row of compareResult.rows) {
    if (row.status === 'removed') continue;
    const recordId = recordIdByStableId.get(row.stable_record_id);
    if (!recordId) continue;
    for (const cell of row.cells) {
      if (cell.changed) {
        changedCellKeys.add(legacyIssueGridCellKey(recordId, cell.field_key));
      }
    }
  }
  return [...changedCellKeys];
}

function normalizeLegacyIssueDraftValue(
  value: LegacyIssueEditableValue | undefined,
): LegacyIssueFieldValue | null {
  if (value === null || value === undefined) return null;
  if (typeof value === 'string') {
    const normalized = value.trim();
    return normalized || null;
  }
  if (Array.isArray(value)) {
    const stringItems: string[] = [];
    const referenceItems: LegacyIssueReferenceValue[] = [];
    for (const item of value) {
      const normalizedItem = normalizeLegacyIssueDraftValue(item);
      if (normalizedItem === null) continue;
      if (Array.isArray(normalizedItem)) {
        for (const nestedItem of normalizedItem) {
          if (typeof nestedItem === 'string') {
            stringItems.push(nestedItem);
          } else {
            referenceItems.push(nestedItem);
          }
        }
      } else if (typeof normalizedItem === 'string') {
        stringItems.push(normalizedItem);
      } else {
        referenceItems.push(normalizedItem);
      }
    }
    if (referenceItems.length > 0) return referenceItems;
    return stringItems.length > 0 ? stringItems : null;
  }
  const id = value.id.trim();
  const label = value.label.trim();
  if (!id || !label) return null;
  return {
    kind: value.kind,
    id,
    label,
    ...(value.email?.trim() ? { email: value.email.trim() } : {}),
    ...(value.path?.trim() ? { path: value.path.trim() } : {}),
  };
}

function legacyIssueStringValue(
  value: LegacyIssueFieldValue | null | undefined,
): string {
  return typeof value === 'string'
    ? value
    : displayLegacyIssueFieldValue(value);
}

function legacyIssueStringArrayValue(
  value: LegacyIssueFieldValue | null | undefined,
): string[] {
  if (typeof value === 'string') return value ? [value] : [];
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === 'string');
}

function legacyIssueReferenceArrayValue(
  value: LegacyIssueFieldValue | null | undefined,
  kind: LegacyIssueReferenceValue['kind'],
): LegacyIssueReferenceValue[] {
  const values = Array.isArray(value) ? value : value ? [value] : [];
  return values.filter(
    (item): item is LegacyIssueReferenceValue =>
      typeof item === 'object' &&
      item !== null &&
      !Array.isArray(item) &&
      item.kind === kind,
  );
}

function legacyIssueUserReferenceToDmUser(
  reference: LegacyIssueReferenceValue,
): DmUser {
  return {
    id: reference.id,
    email: reference.email ?? '',
    full_name: reference.label,
    display_name: reference.label,
    job_title: null,
    primary_org_unit_name: null,
  };
}

function legacyIssueDmUserToReference(user: DmUser): LegacyIssueReferenceValue {
  return {
    kind: 'user',
    id: user.id,
    label: user.display_name || user.full_name || user.email || user.id,
    email: user.email,
  };
}

function legacyIssueOrgUnitToReference(
  item: LegacyIssueOrgUnitItem,
): LegacyIssueReferenceValue {
  return {
    kind: 'orgUnit',
    id: item.id,
    label: item.name,
    path: item.path,
  };
}

function mergeLegacyIssueReferences(
  current: readonly LegacyIssueReferenceValue[],
  incoming: readonly LegacyIssueReferenceValue[],
): LegacyIssueReferenceValue[] {
  const byId = new Map(current.map((item) => [item.id, item]));
  for (const item of incoming) {
    byId.set(item.id, item);
  }
  return Array.from(byId.values());
}

function mergeLegacyIssueDmUserOptions(
  users: readonly DmUser[],
  selectedUsers: readonly DmUser[],
): DmUser[] {
  const byId = new Map<string, DmUser>();
  for (const item of selectedUsers) {
    byId.set(item.id, item);
  }
  for (const item of users) {
    byId.set(item.id, item);
  }
  return Array.from(byId.values());
}

function legacyIssueFieldValuesEqual(
  left: LegacyIssueFieldValue | null,
  right: LegacyIssueFieldValue | null,
) {
  return JSON.stringify(left ?? null) === JSON.stringify(right ?? null);
}

function isBlankLegacyIssueFieldValue(
  value: LegacyIssueEditableValue | undefined,
) {
  return normalizeLegacyIssueDraftValue(value) === null;
}

export function resolveLegacyIssueSelectedRecordForRecords(
  records: LegacyIssueDatasetRecord[],
  selectedRecord: LegacyIssueDatasetRecord | null,
): LegacyIssueDatasetRecord | null {
  if (!selectedRecord) return null;
  const exactMatch = records.find((record) => record.id === selectedRecord.id);
  if (exactMatch) return exactMatch;
  const stableRecordId = selectedRecord.stable_record_id ?? selectedRecord.id;
  return (
    records.find(
      (record) =>
        record.stable_record_id === stableRecordId ||
        record.id === stableRecordId,
    ) ?? null
  );
}

export function preserveStringArrayReferenceWhenEqual(
  current: string[],
  next: string[],
): string[] {
  if (current.length !== next.length) return next;
  return current.every((value, index) => value === next[index])
    ? current
    : next;
}

export function canEditLegacyIssueAttachmentsInRevision({
  canDirectEditPublishedRevision,
  canEditCurrentDraftRevision,
}: {
  canDirectEditPublishedRevision: boolean;
  canEditCurrentDraftRevision: boolean;
}): boolean {
  return canEditCurrentDraftRevision || canDirectEditPublishedRevision;
}

export function canEditLegacyIssueDraftRevision({
  currentUserId,
  revision,
}: {
  currentUserId: string | null;
  revision: Pick<LegacyIssueRevision, 'locked_by_id' | 'status'> | null;
}): boolean {
  if (!revision || revision.status !== 'draft') return false;
  return Boolean(currentUserId && revision.locked_by_id === currentUserId);
}

export function canForceCancelLegacyIssueDraftRevision({
  activeDraftId,
  canForceCancelActiveDraft,
  currentUserId,
  revision,
}: {
  activeDraftId: string | null;
  canForceCancelActiveDraft: boolean;
  currentUserId: string | null;
  revision: Pick<LegacyIssueRevision, 'id' | 'locked_by_id' | 'status'> | null;
}): boolean {
  return Boolean(
    canForceCancelActiveDraft &&
      activeDraftId &&
      revision?.id === activeDraftId &&
      revision?.status === 'draft' &&
      revision.locked_by_id &&
      revision.locked_by_id !== currentUserId,
  );
}

function upsertLegacyIssueRevision(
  revisions: LegacyIssueRevision[],
  revision: LegacyIssueRevision,
): LegacyIssueRevision[] {
  const existingIndex = revisions.findIndex((item) => item.id === revision.id);
  if (existingIndex < 0) return [revision, ...revisions];
  return revisions.map((item) => (item.id === revision.id ? revision : item));
}

export function canApplyLegacyIssueInlineCellEdits({
  canDirectEditPublishedRevision,
  canEditCurrentDraftRevision,
}: {
  canDirectEditPublishedRevision: boolean;
  canEditCurrentDraftRevision: boolean;
}): boolean {
  return canEditCurrentDraftRevision || canDirectEditPublishedRevision;
}

export function canDirectEditLegacyIssuePublishedRevision({
  activeDraft,
  canDirectEditPublishedRevision,
  currentRevision,
  isAggregateView,
  latestPublishedRevision,
}: {
  activeDraft: Pick<LegacyIssueRevision, 'id'> | null;
  canDirectEditPublishedRevision: boolean;
  currentRevision: Pick<LegacyIssueRevision, 'id' | 'status'> | null;
  isAggregateView: boolean;
  latestPublishedRevision: Pick<LegacyIssueRevision, 'id'> | null;
}): boolean {
  return Boolean(
    !isAggregateView &&
      canDirectEditPublishedRevision &&
      currentRevision?.status === 'published' &&
      latestPublishedRevision?.id === currentRevision.id &&
      !activeDraft,
  );
}

export function resolveLegacyIssueAutoSelectedRevisionId({
  activeDraftId,
  autoSelectionAttempted,
  selectedRevisionId,
}: {
  activeDraftId: string | null;
  autoSelectionAttempted: boolean;
  selectedRevisionId: string | null;
}): string | null {
  if (autoSelectionAttempted) return null;
  if (selectedRevisionId) return selectedRevisionId;
  return activeDraftId;
}

export function resolveLegacyIssueLocalizedDefinition({
  definition,
  isKorean,
  translate,
  viewDefinition,
  viewKey,
}: {
  definition: LegacyIssueDatasetDefinition;
  isKorean: boolean;
  translate: (key: string, options?: { ns?: string }) => string;
  viewDefinition: LegacyIssueViewDefinition;
  viewKey: LegacyIssueViewKey;
}): { hierarchy: string[]; title: string } {
  const baseHierarchy = isKorean
    ? definition.hierarchy_ko
    : definition.hierarchy_en;
  if (viewKey !== LEGACY_ISSUE_DEFAULT_VIEW_KEY) {
    const viewTitle = translate(`nav.${viewDefinition.navItemId}`, {
      ns: 'shell',
    });
    return {
      hierarchy: [...baseHierarchy, viewTitle],
      title: viewTitle,
    };
  }
  return {
    hierarchy: baseHierarchy,
    title: isKorean ? definition.title_ko : definition.title_en,
  };
}

function displayConfiguredIssueFieldLabel({
  groupLabel,
  label,
}: {
  groupLabel: string | undefined;
  label: string;
}) {
  if (!groupLabel) return label;
  const normalizedGroup = groupLabel.trim();
  const normalizedLabel = label.trim();
  for (const separator of [' - ', '-', ' / ', '/']) {
    const prefix = `${normalizedGroup}${separator}`;
    if (normalizedLabel.startsWith(prefix)) {
      return normalizedLabel.slice(prefix.length).trim() || normalizedLabel;
    }
  }
  return normalizedLabel;
}

function fieldsReadonlyKeys(fields: LegacyIssueDatasetField[]): string[] {
  return fields.filter((field) => field.readonly).map((field) => field.key);
}

export function legacyIssueReferenceKindForField(
  field: Pick<LegacyIssueDatasetField, 'field_type'>,
): LegacyIssueGridReferenceKind | undefined {
  if (field.field_type === 'user') return 'user';
  if (field.field_type === 'orgUnit') return 'orgUnit';
  return undefined;
}

function LegacyIssueDatasetDetailPanel({
  allowDelete,
  attachmentsReadonly,
  busyAttachmentId,
  canSetPrimaryAttachment,
  definition,
  draft,
  hasPendingAttachmentChanges,
  historyItems,
  historyLoading,
  mode,
  onAttachmentDelete,
  onAttachmentDescriptionSave,
  onAttachmentDownload,
  onAttachmentIndexRetry,
  onAttachmentPrimary,
  onAttachmentSave,
  onAttachmentUpload,
  onPendingAttachmentDelete,
  onPendingAttachmentDescriptionChange,
  onClose,
  onDelete,
  onDraftChange,
  onSave,
  pendingAttachments,
  pendingAttachmentEdits,
  pendingCreateRecord,
  record,
  readonly,
  saving,
  uploading,
}: {
  allowDelete: boolean;
  attachmentsReadonly: boolean;
  busyAttachmentId: string | null;
  canSetPrimaryAttachment: boolean;
  definition: LegacyIssueDatasetDefinition | null;
  draft: Record<string, LegacyIssueEditableValue>;
  hasPendingAttachmentChanges: boolean;
  historyItems: LegacyIssueDatasetRecordHistoryItem[];
  historyLoading: boolean;
  mode: PanelMode;
  onAttachmentDelete: (attachment: LegacyIssueDatasetAttachment) => void;
  onAttachmentDescriptionSave: (
    attachment: LegacyIssueDatasetAttachment,
    description: string,
  ) => void;
  onAttachmentDownload: (attachment: LegacyIssueDatasetAttachment) => void;
  onAttachmentIndexRetry: (attachment: LegacyIssueDatasetAttachment) => void;
  onAttachmentPrimary: (attachment: LegacyIssueDatasetAttachment) => void;
  onAttachmentSave: () => void;
  onAttachmentUpload: (files: FileList | File[]) => void;
  onPendingAttachmentDelete: (params: {
    attachmentId: string;
    recordId: string;
  }) => void;
  onPendingAttachmentDescriptionChange: (params: {
    attachmentId: string;
    description: string;
    recordId: string;
  }) => void;
  onClose: () => void;
  onDelete: () => void;
  onDraftChange: (key: string, value: LegacyIssueEditableValue) => void;
  onSave: (event: FormEvent) => void;
  pendingAttachments: PendingAttachmentDraft[];
  pendingAttachmentEdits: PendingAttachmentEdits | undefined;
  pendingCreateRecord: boolean;
  record: LegacyIssueDatasetRecord | null;
  readonly: boolean;
  saving: boolean;
  uploading: boolean;
}) {
  const { t, i18n } = useTranslation(['apps', 'common']);
  const korean = i18n.language.startsWith('ko');
  const fields = definition?.fields ?? [];
  const [activeTab, setActiveTab] = useState<DetailPanelTab>('data');
  useEffect(() => {
    setActiveTab('data');
  }, [record?.id, mode]);
  useEffect(() => {
    const closeOnEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key !== 'Escape' || event.defaultPrevented) return;
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
  }, [onClose]);

  return (
    <div className="pointer-events-none absolute inset-0 z-[40] flex justify-end">
      <aside
        aria-label={
          mode === 'create'
            ? t('coreBusiness.module.detail.createTitle')
            : t('coreBusiness.module.detail.editTitle')
        }
        className="pointer-events-auto relative z-10 flex h-full w-[min(45rem,92vw)] shrink-0 flex-col border-l border-app-border bg-app-surface shadow-2xl"
        role="dialog"
      >
        <header className="flex items-start justify-between gap-3 border-b border-app-border px-4 py-3">
          <div className="min-w-0">
            <h2 className="truncate app-text-body-sm font-semibold">
              {mode === 'create'
                ? t('coreBusiness.module.detail.createTitle')
                : t('coreBusiness.module.detail.editTitle')}
            </h2>
            {record ? (
              <p className="truncate app-text-caption text-app-ink/50">
                {record.id}
              </p>
            ) : null}
          </div>
          <button
            aria-label={t('coreBusiness.module.actions.close')}
            className="flex size-8 shrink-0 items-center justify-center rounded-md border border-app-border text-app-ink/60 hover:bg-app-surface-hover hover:text-app-ink"
            type="button"
            onClick={onClose}
          >
            <X size={16} />
          </button>
        </header>

        <div className="flex shrink-0 border-b border-app-border px-4">
          <DetailTabButton
            active={activeTab === 'data'}
            label={t('coreBusiness.history.tabs.data')}
            onClick={() => setActiveTab('data')}
          />
          <DetailTabButton
            active={activeTab === 'attachments'}
            disabled={mode !== 'edit' || !record}
            label={t('coreBusiness.history.tabs.attachments')}
            onClick={() => setActiveTab('attachments')}
          />
          <DetailTabButton
            active={activeTab === 'history'}
            disabled={mode !== 'edit'}
            label={t('coreBusiness.history.tabs.history')}
            onClick={() => setActiveTab('history')}
          />
        </div>

        <form className="flex min-h-0 flex-1 flex-col" onSubmit={onSave}>
          <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
            {activeTab === 'data' ? (
              <div className="grid grid-cols-2 gap-3">
                {fields.map((field) => {
                  const multiline =
                    field.field_type === 'longText' || isLongField(field.key);
                  const fieldLabel = korean ? field.label_ko : field.label_en;
                  return (
                    <label
                      key={field.key}
                      className={cn('min-w-0', multiline ? 'col-span-2' : '')}
                    >
                      <span className="mb-1 block app-text-micro font-medium text-app-ink/60">
                        {fieldLabel}
                      </span>
                      <LegacyIssueDetailFieldInput
                        field={field}
                        fieldLabel={fieldLabel}
                        multiline={multiline}
                        readonly={readonly || saving || field.readonly}
                        value={draft[field.key]}
                        onChange={(value) => onDraftChange(field.key, value)}
                      />
                    </label>
                  );
                })}
              </div>
            ) : activeTab === 'attachments' && mode === 'edit' && record ? (
              <LegacyIssueAttachmentManager
                busyAttachmentId={busyAttachmentId}
                onAttachmentDelete={onAttachmentDelete}
                onAttachmentDescriptionSave={onAttachmentDescriptionSave}
                onAttachmentDownload={onAttachmentDownload}
                onAttachmentIndexRetry={onAttachmentIndexRetry}
                onAttachmentPrimary={onAttachmentPrimary}
                onAttachmentUpload={onAttachmentUpload}
                onPendingAttachmentDelete={onPendingAttachmentDelete}
                onPendingAttachmentDescriptionChange={
                  onPendingAttachmentDescriptionChange
                }
                canSetPrimaryAttachment={canSetPrimaryAttachment}
                pendingAttachmentEdits={pendingAttachmentEdits}
                pendingAttachments={pendingAttachments}
                pendingCreateRecord={pendingCreateRecord}
                readonly={attachmentsReadonly || saving}
                record={record}
                uploading={uploading}
              />
            ) : (
              <LegacyIssueHistoryList
                items={historyItems}
                loading={historyLoading}
              />
            )}
          </div>

          <footer className="flex items-center justify-between gap-3 border-t border-app-border px-4 py-3">
            {mode === 'edit' ? (
              <button
                className="inline-flex h-8 items-center gap-2 rounded-md border border-app-danger/40 px-3 app-text-caption text-app-danger hover:bg-app-danger/10"
                disabled={!allowDelete || saving}
                type="button"
                onClick={onDelete}
              >
                <Trash2 size={15} />
                {t('coreBusiness.module.actions.delete')}
              </button>
            ) : (
              <span />
            )}
            {activeTab === 'data' || activeTab === 'attachments' ? (
              <button
                className="inline-flex h-8 items-center gap-2 rounded-md bg-app-accent px-3 app-text-caption font-medium text-app-accent-fg hover:bg-app-accent/90 disabled:opacity-50"
                disabled={
                  activeTab === 'data'
                    ? readonly || saving
                    : attachmentsReadonly ||
                      saving ||
                      !hasPendingAttachmentChanges
                }
                type={activeTab === 'data' ? 'submit' : 'button'}
                onClick={
                  activeTab === 'attachments' ? onAttachmentSave : undefined
                }
              >
                {saving ? (
                  <Loader2 size={15} className="animate-spin" />
                ) : (
                  <Save size={15} />
                )}
                {t('coreBusiness.module.actions.save')}
              </button>
            ) : (
              <span />
            )}
          </footer>
        </form>
      </aside>
    </div>
  );
}

function LegacyIssueDetailFieldInput({
  field,
  fieldLabel,
  multiline,
  onChange,
  readonly,
  value,
}: {
  field: LegacyIssueDatasetField;
  fieldLabel: string;
  multiline: boolean;
  onChange: (value: LegacyIssueEditableValue) => void;
  readonly: boolean;
  value: LegacyIssueEditableValue | undefined;
}) {
  const { t } = useTranslation(['apps', 'common']);
  if (field.field_type === 'select') {
    if (field.allow_multiple) {
      const selectedValues = new Set(legacyIssueStringArrayValue(value));
      return (
        <div className="max-h-36 overflow-y-auto rounded-md border border-app-border bg-app-bg p-2">
          {field.options.length === 0 ? (
            <div className="app-text-caption text-app-ink/45">
              {t('common:empty.none')}
            </div>
          ) : (
            <div className="space-y-1">
              {field.options.map((option) => (
                <label
                  key={option}
                  className="flex items-center gap-2 rounded px-1.5 py-1 app-text-caption text-app-ink/75 hover:bg-app-surface-hover"
                >
                  <input
                    checked={selectedValues.has(option)}
                    className="size-4 rounded border-app-border"
                    disabled={readonly}
                    type="checkbox"
                    onChange={(event) => {
                      const next = new Set(selectedValues);
                      if (event.target.checked) {
                        next.add(option);
                      } else {
                        next.delete(option);
                      }
                      const values = Array.from(next);
                      onChange(values.length > 0 ? values : null);
                    }}
                  />
                  <span className="truncate">{option}</span>
                </label>
              ))}
            </div>
          )}
        </div>
      );
    }
    return (
      <select
        className="app-field-input-sm"
        disabled={readonly}
        value={legacyIssueStringValue(value)}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">{t('common:empty.none')}</option>
        {field.options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    );
  }
  if (field.field_type === 'boolean') {
    return (
      <select
        className="app-field-input-sm"
        disabled={readonly}
        value={legacyIssueStringValue(value)}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">{t('common:empty.none')}</option>
        <option value="true">
          {t('coreBusiness.module.fieldValues.booleanTrue')}
        </option>
        <option value="false">
          {t('coreBusiness.module.fieldValues.booleanFalse')}
        </option>
      </select>
    );
  }
  const referenceKind = legacyIssueReferenceKindForField(field);
  if (referenceKind) {
    return (
      <LegacyIssueReferenceFieldControl
        allowMultiple={field.allow_multiple}
        fieldLabel={fieldLabel}
        readonly={readonly}
        referenceKind={referenceKind}
        value={value}
        onChange={onChange}
      />
    );
  }
  if (multiline) {
    return (
      <textarea
        className="app-field-input-sm min-h-20 resize-y py-1.5"
        readOnly={readonly}
        value={legacyIssueStringValue(value)}
        onChange={(event) => onChange(event.target.value)}
      />
    );
  }
  return (
    <input
      className="app-field-input-sm h-8"
      readOnly={readonly}
      type={
        field.field_type === 'date'
          ? 'date'
          : field.field_type === 'number'
            ? 'number'
            : 'text'
      }
      value={legacyIssueStringValue(value)}
      onChange={(event) => onChange(event.target.value)}
    />
  );
}

function LegacyIssueReferenceFieldControl({
  allowMultiple,
  fieldLabel,
  onChange,
  readonly,
  referenceKind,
  value,
}: {
  allowMultiple: boolean;
  fieldLabel: string;
  onChange: (value: LegacyIssueEditableValue) => void;
  readonly: boolean;
  referenceKind: LegacyIssueGridReferenceKind;
  value: LegacyIssueEditableValue | undefined;
}) {
  const { t } = useTranslation(['apps', 'common']);
  const [open, setOpen] = useState(false);
  const selectedReferences = legacyIssueReferenceArrayValue(
    value,
    referenceKind,
  );
  const displayValue = displayLegacyIssueFieldValue(value);

  return (
    <div className="space-y-2">
      {selectedReferences.length > 0 ? (
        <LegacyIssueReferenceChips
          references={selectedReferences}
          referenceKind={referenceKind}
          readonly={readonly}
          onRemove={(referenceId) => {
            const nextReferences = selectedReferences.filter(
              (reference) => reference.id !== referenceId,
            );
            onChange(nextReferences.length > 0 ? nextReferences : null);
          }}
        />
      ) : null}
      <div className="flex min-w-0 items-center gap-2">
        <button
          aria-label={fieldLabel}
          className={cn(
            'app-field-input-sm flex h-8 min-w-0 flex-1 items-center justify-between gap-2 text-left',
            readonly && 'cursor-not-allowed opacity-60',
          )}
          disabled={readonly}
          type="button"
          onClick={() => setOpen(true)}
        >
          <span
            className={cn(
              'min-w-0 truncate',
              displayValue ? 'text-app-ink' : 'text-app-ink/40',
            )}
          >
            {displayValue || t('common:empty.none')}
          </span>
          <Search size={14} className="shrink-0 text-app-ink/35" />
        </button>
        {selectedReferences.length > 0 && !readonly ? (
          <button
            aria-label={t('common:actions.reset')}
            className="inline-flex size-8 shrink-0 items-center justify-center rounded-md border border-app-border text-app-ink/55 hover:bg-app-surface-hover"
            type="button"
            onClick={() => onChange(null)}
          >
            <X size={14} />
          </button>
        ) : null}
      </div>
      {open ? (
        <LegacyIssueReferencePickerDialog
          allowMultiple={allowMultiple}
          fieldLabel={fieldLabel}
          referenceKind={referenceKind}
          value={value ?? null}
          onClose={() => setOpen(false)}
          onCommit={(nextValue) => {
            onChange(nextValue);
            setOpen(false);
          }}
        />
      ) : null}
    </div>
  );
}

function LegacyIssueReferencePickerDialog({
  allowMultiple,
  fieldLabel,
  onClose,
  onCommit,
  referenceKind,
  value,
}: {
  allowMultiple: boolean;
  fieldLabel: string;
  onClose: () => void;
  onCommit: (value: LegacyIssueEditableValue) => void;
  referenceKind: LegacyIssueGridReferenceKind;
  value: LegacyIssueEditableValue;
}) {
  const { workspaceSlug = '' } = useParams<{ workspaceSlug: string }>();
  const { token, user } = useAuth();
  const { t } = useTranslation(['apps', 'common']);
  const [query, setQuery] = useState('');
  const [users, setUsers] = useState<DmUser[]>([]);
  const [orgUnits, setOrgUnits] = useState<LegacyIssueOrgUnitItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedReferences, setSelectedReferences] = useState<
    LegacyIssueReferenceValue[]
  >(() => legacyIssueReferenceArrayValue(value, referenceKind));
  const selectedIds = useMemo(
    () => new Set(selectedReferences.map((reference) => reference.id)),
    [selectedReferences],
  );
  const selectedUsers = useMemo(
    () =>
      referenceKind === 'user'
        ? selectedReferences.map(legacyIssueUserReferenceToDmUser)
        : [],
    [referenceKind, selectedReferences],
  );
  const userOptions = useMemo(
    () => mergeLegacyIssueDmUserOptions(users, selectedUsers),
    [selectedUsers, users],
  );
  const userCandidates = useMemo(
    () =>
      selectUserOptionsForPicker({
        currentUserId: user?.id ?? null,
        limit: 30,
        query,
        users: userOptions,
      }).filter((candidate) => !selectedIds.has(candidate.id)),
    [query, selectedIds, user?.id, userOptions],
  );
  const orgUnitCandidates = useMemo(
    () => orgUnits.filter((item) => !selectedIds.has(item.id)),
    [orgUnits, selectedIds],
  );
  const searchPlaceholder =
    referenceKind === 'user'
      ? t('coreBusiness.module.reference.userSearchPlaceholder')
      : t('coreBusiness.module.reference.orgSearchPlaceholder');
  const emptyMessage = query.trim()
    ? referenceKind === 'user'
      ? t('coreBusiness.module.reference.noUserMatch')
      : t('coreBusiness.module.reference.noOrgMatch')
    : referenceKind === 'user'
      ? t('coreBusiness.module.reference.userSearchPrompt')
      : t('coreBusiness.module.reference.orgSearchPrompt');

  useEffect(() => {
    if (!token || !workspaceSlug) {
      setUsers([]);
      setOrgUnits([]);
      setLoading(false);
      return undefined;
    }
    let canceled = false;
    setLoading(true);
    const timeout = window.setTimeout(() => {
      const request =
        referenceKind === 'user'
          ? searchDmUsers(token, query, {
              includeCurrent: true,
              limit: 30,
            }).then((items) => {
              if (!canceled) setUsers(items);
            })
          : searchLegacyIssueOrgUnits({
              limit: 50,
              query,
              token,
              workspaceSlug,
            }).then((items) => {
              if (!canceled) setOrgUnits(items);
            });
      request
        .catch(() => {
          if (!canceled) {
            setUsers([]);
            setOrgUnits([]);
          }
        })
        .finally(() => {
          if (!canceled) setLoading(false);
        });
    }, 150);
    return () => {
      canceled = true;
      window.clearTimeout(timeout);
    };
  }, [query, referenceKind, token, workspaceSlug]);

  function commitReference(reference: LegacyIssueReferenceValue) {
    if (!allowMultiple) {
      onCommit(reference);
      return;
    }
    setSelectedReferences((current) =>
      mergeLegacyIssueReferences(current, [reference]),
    );
    setQuery('');
  }

  function commitSelectedReferences() {
    onCommit(selectedReferences.length > 0 ? selectedReferences : null);
  }

  return (
    <div
      className="fixed inset-0 z-[10000] flex items-start justify-center bg-black/30 px-4 py-[10vh]"
      role="presentation"
    >
      <button
        aria-label={t('common:actions.close')}
        className="absolute inset-0 cursor-default"
        type="button"
        onClick={onClose}
      />
      <div
        aria-label={fieldLabel}
        className="relative z-10 flex w-full max-w-lg flex-col overflow-hidden rounded-lg border border-app-border bg-app-bg shadow-2xl"
        data-ui-floating-layer
        role="dialog"
      >
        <header className="flex h-12 items-center justify-between border-b border-app-border px-4">
          <h3 className="min-w-0 truncate app-text-body-sm font-semibold text-app-ink">
            {fieldLabel}
          </h3>
          <button
            aria-label={t('common:actions.close')}
            className="inline-flex size-8 items-center justify-center rounded-md text-app-ink/45 hover:bg-app-surface-hover hover:text-app-ink"
            type="button"
            onClick={onClose}
          >
            <X size={15} />
          </button>
        </header>
        <div className="border-b border-app-border p-3">
          {selectedReferences.length > 0 ? (
            <div className="mb-2">
              <LegacyIssueReferenceChips
                references={selectedReferences}
                referenceKind={referenceKind}
                readonly={false}
                onRemove={(referenceId) =>
                  setSelectedReferences((current) =>
                    current.filter((reference) => reference.id !== referenceId),
                  )
                }
              />
            </div>
          ) : null}
          <div className="flex h-9 items-center gap-2 rounded-md border border-app-border bg-app-surface-sidebar px-2">
            <Search size={14} className="shrink-0 text-app-ink/40" />
            <input
              autoFocus
              aria-label={searchPlaceholder}
              className="min-w-0 flex-1 bg-transparent app-text-body-sm text-app-ink outline-none placeholder:text-app-ink/40"
              placeholder={searchPlaceholder}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Escape') onClose();
                if (
                  event.key === 'Enter' &&
                  allowMultiple &&
                  selectedReferences.length > 0
                ) {
                  event.preventDefault();
                  commitSelectedReferences();
                }
              }}
            />
            {query ? (
              <button
                aria-label={t('common:actions.reset')}
                className="text-app-ink/40 hover:text-app-ink"
                type="button"
                onClick={() => setQuery('')}
              >
                <X size={12} />
              </button>
            ) : null}
          </div>
        </div>
        <div className="max-h-[min(24rem,52vh)] overflow-y-auto p-2">
          <button
            className="app-menu-item text-app-ink/55"
            type="button"
            onClick={() => {
              if (allowMultiple) {
                setSelectedReferences([]);
              } else {
                onCommit(null);
              }
            }}
          >
            {t('common:empty.none')}
          </button>
          {referenceKind === 'user'
            ? userCandidates.map((candidate) => (
                <UserOptionRow
                  currentUserId={user?.id ?? null}
                  currentUserLabel={t(
                    'coreBusiness.module.reference.currentUser',
                  )}
                  density="compact"
                  key={candidate.id}
                  selected={false}
                  user={candidate}
                  onClick={() =>
                    commitReference(legacyIssueDmUserToReference(candidate))
                  }
                />
              ))
            : orgUnitCandidates.map((candidate) => (
                <button
                  className="app-menu-item gap-2.5"
                  key={candidate.id}
                  type="button"
                  onClick={() =>
                    commitReference(legacyIssueOrgUnitToReference(candidate))
                  }
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate">{candidate.name}</span>
                    <span className="app-text-caption block truncate text-app-ink/40">
                      {candidate.path}
                    </span>
                  </span>
                </button>
              ))}
          {loading &&
          (referenceKind === 'user'
            ? userCandidates.length === 0
            : orgUnitCandidates.length === 0) ? (
            <p className="app-text-caption px-3 py-3 text-app-ink/40">
              {t('coreBusiness.module.reference.searching')}
            </p>
          ) : !loading &&
            (referenceKind === 'user'
              ? userCandidates.length === 0
              : orgUnitCandidates.length === 0) ? (
            <p className="app-text-caption px-3 py-3 text-app-ink/40">
              {emptyMessage}
            </p>
          ) : null}
        </div>
        <footer className="flex items-center justify-end gap-2 border-t border-app-border px-4 py-3">
          <button
            className="inline-flex h-8 items-center rounded-md border border-app-border px-3 app-text-caption text-app-ink/70 hover:bg-app-surface-hover"
            type="button"
            onClick={onClose}
          >
            {t('common:actions.cancel')}
          </button>
          {allowMultiple ? (
            <button
              className="inline-flex h-8 items-center rounded-md bg-app-accent px-3 app-text-caption font-medium text-app-accent-fg hover:bg-app-accent/90"
              type="button"
              onClick={commitSelectedReferences}
            >
              {t('common:actions.done')}
            </button>
          ) : null}
        </footer>
      </div>
    </div>
  );
}

function LegacyIssueReferenceChips({
  onRemove,
  readonly,
  referenceKind,
  references,
}: {
  onRemove: (referenceId: string) => void;
  readonly: boolean;
  referenceKind: LegacyIssueGridReferenceKind;
  references: LegacyIssueReferenceValue[];
}) {
  const { t } = useTranslation(['apps']);
  return (
    <div className="flex flex-wrap gap-1.5">
      {references.map((reference) => {
        const label = reference.path || reference.label;
        return (
          <span
            key={reference.id}
            className="app-text-caption inline-flex max-w-full items-center gap-1 rounded-full border border-app-border bg-app-surface-sidebar px-2 py-1 text-app-ink"
          >
            <span className="max-w-[14rem] truncate">{label}</span>
            {!readonly ? (
              <button
                aria-label={t(
                  referenceKind === 'user'
                    ? 'coreBusiness.module.reference.removeUser'
                    : 'coreBusiness.module.reference.removeOrgUnit',
                  { name: reference.label },
                )}
                className="text-app-ink/40 hover:text-app-ink disabled:cursor-not-allowed disabled:opacity-40"
                type="button"
                onClick={() => onRemove(reference.id)}
              >
                <X size={12} />
              </button>
            ) : null}
          </span>
        );
      })}
    </div>
  );
}

function LegacyIssueAttachmentManager({
  busyAttachmentId,
  canSetPrimaryAttachment,
  onAttachmentDelete,
  onAttachmentDescriptionSave,
  onAttachmentDownload,
  onAttachmentIndexRetry,
  onAttachmentPrimary,
  onAttachmentUpload,
  onPendingAttachmentDelete,
  onPendingAttachmentDescriptionChange,
  pendingAttachmentEdits,
  pendingAttachments,
  pendingCreateRecord,
  readonly,
  record,
  uploading,
}: {
  busyAttachmentId: string | null;
  canSetPrimaryAttachment: boolean;
  onAttachmentDelete: (attachment: LegacyIssueDatasetAttachment) => void;
  onAttachmentDescriptionSave: (
    attachment: LegacyIssueDatasetAttachment,
    description: string,
  ) => void;
  onAttachmentDownload: (attachment: LegacyIssueDatasetAttachment) => void;
  onAttachmentIndexRetry: (attachment: LegacyIssueDatasetAttachment) => void;
  onAttachmentPrimary: (attachment: LegacyIssueDatasetAttachment) => void;
  onAttachmentUpload: (files: FileList | File[]) => void;
  onPendingAttachmentDelete: (params: {
    attachmentId: string;
    recordId: string;
  }) => void;
  onPendingAttachmentDescriptionChange: (params: {
    attachmentId: string;
    description: string;
    recordId: string;
  }) => void;
  pendingAttachmentEdits: PendingAttachmentEdits | undefined;
  pendingAttachments: PendingAttachmentDraft[];
  pendingCreateRecord: boolean;
  readonly: boolean;
  record: LegacyIssueDatasetRecord;
  uploading: boolean;
}) {
  const { t } = useTranslation(['apps']);
  const [dragOver, setDragOver] = useState(false);
  const deletedAttachmentIds = new Set(
    pendingAttachmentEdits?.deletedAttachmentIds ?? [],
  );
  const visibleAttachments = record.attachments.filter(
    (attachment) => !deletedAttachmentIds.has(attachment.id),
  );
  const effectivePrimaryAttachmentId =
    pendingAttachmentEdits?.primaryAttachmentId ??
    visibleAttachments.find((attachment) => attachment.is_primary)?.id;

  function handleFiles(files: FileList | File[]) {
    if (readonly || uploading) return;
    const selectedFiles = Array.from(files);
    if (selectedFiles.length === 0) return;
    onAttachmentUpload(selectedFiles);
  }

  const attachmentCount = visibleAttachments.length + pendingAttachments.length;
  const inputDisabled = readonly || uploading;

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <Paperclip size={15} className="shrink-0 text-app-ink/45" />
          <h3 className="truncate app-text-body-sm font-semibold">
            {t('coreBusiness.module.detail.attachments')}
          </h3>
          <span className="shrink-0 rounded-full bg-app-bg px-2 py-0.5 app-text-micro text-app-ink/55">
            {t('coreBusiness.module.detail.attachmentCount', {
              count: attachmentCount,
            })}
          </span>
        </div>
        <label
          className={cn(
            'inline-flex h-8 shrink-0 items-center gap-2 rounded-md border border-app-border px-2 app-text-caption hover:bg-app-surface-hover',
            inputDisabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer',
          )}
        >
          {uploading ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <Upload size={14} />
          )}
          <span>{t('coreBusiness.module.actions.uploadAttachments')}</span>
          <input
            className="hidden"
            disabled={inputDisabled}
            multiple
            type="file"
            onChange={(event) => {
              if (event.target.files?.length) {
                handleFiles(event.target.files);
              }
              event.target.value = '';
            }}
          />
        </label>
      </div>

      <label
        className={cn(
          'flex min-h-24 flex-col items-center justify-center gap-2 rounded-md border border-dashed px-3 py-4 text-center app-text-caption transition-colors',
          inputDisabled
            ? 'cursor-not-allowed border-app-border text-app-ink/35'
            : dragOver
              ? 'cursor-pointer border-app-accent bg-app-accent/5 text-app-accent'
              : 'cursor-pointer border-app-border text-app-ink/50 hover:border-app-accent/60 hover:text-app-ink',
        )}
        onDragLeave={
          inputDisabled
            ? undefined
            : () => {
                setDragOver(false);
              }
        }
        onDragOver={
          inputDisabled
            ? undefined
            : (event) => {
                event.preventDefault();
                event.dataTransfer.dropEffect = 'copy';
                setDragOver(true);
              }
        }
        onDrop={
          inputDisabled
            ? undefined
            : (event) => {
                event.preventDefault();
                setDragOver(false);
                if (event.dataTransfer.files.length) {
                  handleFiles(event.dataTransfer.files);
                }
              }
        }
      >
        {uploading ? (
          <Loader2 size={18} className="animate-spin text-app-accent" />
        ) : (
          <Upload size={18} />
        )}
        <span>
          {uploading
            ? t('coreBusiness.module.detail.uploadingAttachments')
            : dragOver
              ? t('coreBusiness.module.detail.dropAttachmentsActive')
              : t('coreBusiness.module.detail.dropAttachmentsTitle')}
        </span>
        <input
          aria-label={t('coreBusiness.module.actions.uploadAttachments')}
          className="hidden"
          disabled={inputDisabled}
          multiple
          type="file"
          onChange={(event) => {
            if (event.target.files?.length) {
              handleFiles(event.target.files);
            }
            event.target.value = '';
          }}
        />
      </label>

      {pendingCreateRecord && pendingAttachments.length > 0 ? (
        <p className="rounded-md border border-app-accent/20 bg-app-accent/5 px-3 py-2 app-text-caption text-app-ink/65">
          {t('coreBusiness.module.detail.pendingAttachmentsHelp')}
        </p>
      ) : null}

      {attachmentCount === 0 ? (
        <p className="rounded-md border border-dashed border-app-border px-3 py-4 app-text-caption text-app-ink/50">
          {t('coreBusiness.module.detail.noAttachments')}
        </p>
      ) : (
        <div className="space-y-3">
          {pendingAttachments.map((attachment, index) => (
            <PendingAttachmentDraftItem
              key={attachment.id}
              attachment={attachment}
              isPrimary={visibleAttachments.length === 0 && index === 0}
              readonly={readonly || uploading}
              recordId={record.id}
              saveOnDraft={pendingCreateRecord}
              onDelete={onPendingAttachmentDelete}
              onDescriptionChange={onPendingAttachmentDescriptionChange}
            />
          ))}
          {visibleAttachments.map((attachment) => {
            const draft = Object.prototype.hasOwnProperty.call(
              pendingAttachmentEdits?.descriptions ?? {},
              attachment.id,
            )
              ? (pendingAttachmentEdits?.descriptions[attachment.id] ?? '')
              : (attachment.description ?? '');
            const attachmentBusy = busyAttachmentId === attachment.id;
            const indexStatus = attachmentIndexStatusView(attachment);
            const summaryStatus = attachmentAiSummaryStatusView(attachment);
            const canRetryIndex =
              !attachmentBusy &&
              (['failed', 'not_indexed'].includes(attachment.index_status) ||
                attachment.ai_summary_status === 'failed');

            return (
              <article
                key={attachment.id}
                className="rounded-md border border-app-border bg-app-bg px-3 py-3"
              >
                <div className="flex items-start gap-3">
                  <div className="flex size-9 shrink-0 items-center justify-center rounded-md border border-app-border bg-app-surface text-app-ink/45">
                    <FileText size={16} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex min-w-0 flex-wrap items-center gap-2">
                      <p className="min-w-0 truncate app-text-caption font-medium text-app-ink">
                        {attachment.filename}
                      </p>
                      {attachment.id === effectivePrimaryAttachmentId ? (
                        <span className="shrink-0 rounded-full bg-app-accent/10 px-2 py-0.5 app-text-micro font-medium text-app-accent">
                          {t('coreBusiness.module.detail.primary')}
                        </span>
                      ) : null}
                      <span
                        className={cn(
                          'shrink-0 rounded-full px-2 py-0.5 app-text-micro font-medium',
                          indexStatus.className,
                        )}
                      >
                        {t(indexStatus.labelKey)}
                      </span>
                      <span
                        className={cn(
                          'shrink-0 rounded-full px-2 py-0.5 app-text-micro font-medium',
                          summaryStatus.className,
                        )}
                      >
                        {t(summaryStatus.labelKey)}
                      </span>
                    </div>
                    <div className="mt-1 flex flex-wrap gap-x-2 gap-y-0.5 app-text-micro text-app-ink/45">
                      <span>{formatByteSize(attachment.size_bytes)}</span>
                      <span>{attachment.content_type}</span>
                      <span>
                        {t('coreBusiness.module.detail.attachmentIndexStats', {
                          artifacts: attachment.artifact_count,
                          chunks: attachment.chunk_count,
                        })}
                      </span>
                      {attachment.indexed_at ? (
                        <span>
                          {t('coreBusiness.module.detail.attachmentIndexedAt', {
                            date: formatDateTime(attachment.indexed_at),
                          })}
                        </span>
                      ) : null}
                      {attachment.ai_summarized_at ? (
                        <span>
                          {t(
                            'coreBusiness.module.detail.attachmentAiSummaryAt',
                            {
                              date: formatDateTime(attachment.ai_summarized_at),
                            },
                          )}
                        </span>
                      ) : null}
                    </div>
                    {attachment.index_error ? (
                      <p className="mt-1 line-clamp-2 app-text-micro text-app-danger">
                        {attachment.index_error}
                      </p>
                    ) : null}
                    {attachment.ai_summary_error ? (
                      <p className="mt-1 line-clamp-2 app-text-micro text-app-danger">
                        {attachment.ai_summary_error}
                      </p>
                    ) : null}
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    <IconButton
                      icon={<Download size={14} />}
                      label={t(
                        'coreBusiness.module.actions.downloadAttachment',
                      )}
                      onClick={() => onAttachmentDownload(attachment)}
                    />
                    <IconButton
                      disabled={
                        readonly ||
                        !canSetPrimaryAttachment ||
                        attachmentBusy ||
                        attachment.id === effectivePrimaryAttachmentId
                      }
                      icon={<Star size={14} />}
                      label={t('coreBusiness.module.actions.setPrimary')}
                      onClick={() => onAttachmentPrimary(attachment)}
                    />
                    <IconButton
                      disabled={readonly || !canRetryIndex}
                      icon={
                        attachmentBusy &&
                        ['pending', 'processing'].includes(
                          attachment.index_status,
                        ) ? (
                          <Loader2 size={14} className="animate-spin" />
                        ) : (
                          <RefreshCw size={14} />
                        )
                      }
                      label={t(
                        'coreBusiness.module.actions.retryAttachmentIndex',
                      )}
                      onClick={() => onAttachmentIndexRetry(attachment)}
                    />
                    <IconButton
                      disabled={readonly || attachmentBusy}
                      icon={<Trash2 size={14} />}
                      label={t('coreBusiness.module.actions.delete')}
                      onClick={() => onAttachmentDelete(attachment)}
                    />
                  </div>
                </div>

                {attachment.ai_summary ? (
                  <div className="mt-3 rounded-md border border-app-border bg-app-surface px-3 py-2">
                    <p className="mb-1 app-text-micro font-semibold text-app-ink/60">
                      {t('coreBusiness.module.detail.attachmentAiSummary')}
                    </p>
                    <p className="max-h-36 overflow-auto whitespace-pre-wrap app-text-caption leading-5 text-app-ink/75">
                      {attachment.ai_summary}
                    </p>
                  </div>
                ) : null}

                <label className="mt-3 block">
                  <span className="mb-1 block app-text-micro font-medium text-app-ink/60">
                    {t('coreBusiness.module.detail.attachmentDescription')}
                  </span>
                  <textarea
                    className="app-field-input-sm min-h-16 resize-y py-1.5"
                    maxLength={ATTACHMENT_DESCRIPTION_MAX_LENGTH}
                    placeholder={t(
                      'coreBusiness.module.detail.attachmentDescriptionPlaceholder',
                    )}
                    readOnly={readonly}
                    value={draft}
                    onChange={(event) =>
                      onAttachmentDescriptionSave(
                        attachment,
                        event.target.value,
                      )
                    }
                  />
                </label>

                {!readonly ? (
                  <div className="mt-2 flex items-center justify-between gap-3">
                    <span className="app-text-micro text-app-ink/40">
                      {t(
                        'coreBusiness.module.detail.attachmentDescriptionLength',
                        {
                          count: draft.length,
                          max: ATTACHMENT_DESCRIPTION_MAX_LENGTH,
                        },
                      )}
                    </span>
                  </div>
                ) : null}
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}

function PendingAttachmentDraftItem({
  attachment,
  isPrimary,
  onDelete,
  onDescriptionChange,
  readonly,
  recordId,
  saveOnDraft,
}: {
  attachment: PendingAttachmentDraft;
  isPrimary: boolean;
  onDelete: (params: { attachmentId: string; recordId: string }) => void;
  onDescriptionChange: (params: {
    attachmentId: string;
    description: string;
    recordId: string;
  }) => void;
  readonly: boolean;
  recordId: string;
  saveOnDraft: boolean;
}) {
  const { t } = useTranslation(['apps']);
  const statusClassName =
    attachment.status === 'failed'
      ? 'bg-app-danger/10 text-app-danger'
      : attachment.status === 'uploading'
        ? 'bg-app-accent/10 text-app-accent'
        : 'bg-app-warning/10 text-app-warning-text';

  return (
    <article className="rounded-md border border-dashed border-app-accent/35 bg-app-bg px-3 py-3">
      <div className="flex items-start gap-3">
        <div className="flex size-9 shrink-0 items-center justify-center rounded-md border border-app-border bg-app-surface text-app-ink/45">
          {attachment.status === 'uploading' ? (
            <Loader2 size={16} className="animate-spin" />
          ) : (
            <FileText size={16} />
          )}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <p className="min-w-0 truncate app-text-caption font-medium text-app-ink">
              {attachment.file.name}
            </p>
            {isPrimary ? (
              <span className="shrink-0 rounded-full bg-app-accent/10 px-2 py-0.5 app-text-micro font-medium text-app-accent">
                {t('coreBusiness.module.detail.primary')}
              </span>
            ) : null}
            <span
              className={cn(
                'shrink-0 rounded-full px-2 py-0.5 app-text-micro font-medium',
                statusClassName,
              )}
            >
              {t(
                `coreBusiness.module.detail.pendingAttachmentStatus.${attachment.status}`,
              )}
            </span>
          </div>
          <div className="mt-1 flex flex-wrap gap-x-2 gap-y-0.5 app-text-micro text-app-ink/45">
            <span>{formatByteSize(attachment.file.size)}</span>
            <span>
              {attachment.file.type ||
                t('coreBusiness.module.detail.unknownContentType')}
            </span>
          </div>
          {attachment.error ? (
            <p className="mt-1 line-clamp-2 app-text-micro text-app-danger">
              {attachment.error}
            </p>
          ) : null}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <IconButton
            disabled={readonly || attachment.status === 'uploading'}
            icon={<Trash2 size={14} />}
            label={t('coreBusiness.module.actions.delete')}
            onClick={() => onDelete({ attachmentId: attachment.id, recordId })}
          />
        </div>
      </div>

      <label className="mt-3 block">
        <span className="mb-1 block app-text-micro font-medium text-app-ink/60">
          {t('coreBusiness.module.detail.attachmentDescription')}
        </span>
        <textarea
          className="app-field-input-sm min-h-16 resize-y py-1.5"
          maxLength={ATTACHMENT_DESCRIPTION_MAX_LENGTH}
          placeholder={t(
            'coreBusiness.module.detail.attachmentDescriptionPlaceholder',
          )}
          readOnly={readonly || attachment.status === 'uploading'}
          value={attachment.description}
          onChange={(event) =>
            onDescriptionChange({
              attachmentId: attachment.id,
              description: event.target.value,
              recordId,
            })
          }
        />
      </label>
      {!readonly ? (
        <div className="mt-2 flex items-center justify-between gap-3">
          <span className="app-text-micro text-app-ink/40">
            {t('coreBusiness.module.detail.attachmentDescriptionLength', {
              count: attachment.description.length,
              max: ATTACHMENT_DESCRIPTION_MAX_LENGTH,
            })}
          </span>
          <span className="app-text-micro text-app-ink/45">
            {t(
              saveOnDraft
                ? 'coreBusiness.module.detail.pendingAttachmentSaveHint'
                : 'coreBusiness.module.actions.save',
            )}
          </span>
        </div>
      ) : null}
    </article>
  );
}

function IconButton({
  disabled = false,
  icon,
  label,
  onClick,
}: {
  disabled?: boolean;
  icon: ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      aria-label={label}
      className="inline-flex size-8 items-center justify-center rounded-md border border-app-border text-app-ink/65 hover:bg-app-surface-hover disabled:opacity-40"
      disabled={disabled}
      title={label}
      type="button"
      onClick={onClick}
    >
      {icon}
    </button>
  );
}

function DetailTabButton({
  active,
  disabled = false,
  label,
  onClick,
}: {
  active: boolean;
  disabled?: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      className={cn(
        'border-b-2 px-3 py-2 app-text-caption font-medium disabled:cursor-not-allowed disabled:opacity-40',
        active
          ? 'border-app-accent text-app-accent'
          : 'border-transparent text-app-ink/55 hover:text-app-ink',
      )}
      disabled={disabled}
      type="button"
      onClick={onClick}
    >
      {label}
    </button>
  );
}

function defaultColumnWidth(key: string): number {
  if (
    [
      'symptom',
      'problem',
      'cause',
      'countermeasure',
      'reflection_result',
    ].includes(key)
  ) {
    return 260;
  }
  if (
    key.includes('review') ||
    key.includes('check') ||
    key.includes('design')
  ) {
    return 160;
  }
  return 130;
}

function isLongField(key: string): boolean {
  return [
    'symptom',
    'problem',
    'cause',
    'countermeasure',
    'reflection_result',
    'evaluation_method',
    'confirmation_content',
    'notes',
    'opinion',
  ].includes(key);
}

function normalizeAttachmentDescription(description: string): string | null {
  const normalized = description.trim().replace(/\s+/g, ' ');
  return normalized || null;
}

function isMissingAttachmentError(error: unknown): boolean {
  if (
    !(error instanceof ApiRequestError) ||
    error.status !== 404 ||
    !error.payload ||
    typeof error.payload !== 'object' ||
    !('code' in error.payload)
  ) {
    return false;
  }
  return error.payload.code === 'legacy_issues.dataset_attachment_not_found';
}

export function resolveLegacyIssueInvalidField({
  error,
  fields,
}: {
  error: unknown;
  fields: LegacyIssueDatasetField[];
}): LegacyIssueDatasetField | null {
  if (
    !(error instanceof ApiRequestError) ||
    error.status !== 400 ||
    !error.payload ||
    typeof error.payload !== 'object'
  ) {
    return null;
  }
  const payload = error.payload as {
    code?: unknown;
    params?: { detail?: unknown };
  };
  if (
    payload.code !== 'legacy_issues.module_field_value_invalid' ||
    typeof payload.params?.detail !== 'string'
  ) {
    return null;
  }
  return fields.find((field) => field.key === payload.params?.detail) ?? null;
}

function displayLegacyIssueFieldValue(
  value: LegacyIssueFieldValue | null | undefined,
): string {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string') return value;
  if (Array.isArray(value)) {
    return value.map(displayLegacyIssueFieldValue).filter(Boolean).join('; ');
  }
  return value.label || value.path || value.email || value.id;
}

export function buildLegacyIssueBlankRowDefaultValues({
  currentRevisionNo,
  isDraftRevision,
  latestPublishedRevisionNo,
}: {
  currentRevisionNo: number | null;
  isDraftRevision: boolean;
  latestPublishedRevisionNo: number | null;
}): Record<string, string | null> {
  const introducedRevisionNo =
    currentRevisionNo ??
    (isDraftRevision ? (latestPublishedRevisionNo ?? 0) + 1 : null);
  return introducedRevisionNo === null
    ? {}
    : { [INTRODUCED_REVISION_FIELD_KEY]: String(introducedRevisionNo) };
}

export function normalizeLegacyIssueEditableCellValue(
  columnKey: string,
  value: LegacyIssueEditableValue,
): LegacyIssueEditableValue {
  if (
    columnKey !== INTRODUCED_REVISION_FIELD_KEY ||
    typeof value !== 'string'
  ) {
    return value;
  }
  const normalized = value.replace(/^rev\.\s*/i, '').trim();
  return normalized || null;
}

function normalizeLegacyIssueEditableRecordValues(
  values: Record<string, LegacyIssueFieldValue>,
): Record<string, LegacyIssueFieldValue> {
  const normalizedValues: Record<string, LegacyIssueFieldValue> = {};
  for (const [key, value] of Object.entries(values)) {
    const normalizedValue = normalizeLegacyIssueEditableCellValue(key, value);
    if (normalizedValue !== null) {
      normalizedValues[key] = normalizedValue;
    }
  }
  return normalizedValues;
}

function attachmentIndexStatusView(attachment: LegacyIssueDatasetAttachment): {
  labelKey: string;
  className: string;
} {
  switch (attachment.index_status) {
    case 'indexed':
      return {
        labelKey: 'coreBusiness.module.detail.attachmentIndexStatus.indexed',
        className: 'bg-app-success/10 text-app-success',
      };
    case 'pending':
      return {
        labelKey: 'coreBusiness.module.detail.attachmentIndexStatus.pending',
        className: 'bg-app-warning/10 text-app-warning-text',
      };
    case 'processing':
      return {
        labelKey: 'coreBusiness.module.detail.attachmentIndexStatus.processing',
        className: 'bg-app-accent/10 text-app-accent',
      };
    case 'failed':
      return {
        labelKey: 'coreBusiness.module.detail.attachmentIndexStatus.failed',
        className: 'bg-app-danger/10 text-app-danger',
      };
    default:
      return {
        labelKey: 'coreBusiness.module.detail.attachmentIndexStatus.notIndexed',
        className: 'bg-app-bg text-app-ink/55',
      };
  }
}

function attachmentAiSummaryStatusView(
  attachment: LegacyIssueDatasetAttachment,
): { labelKey: string; className: string } {
  switch (attachment.ai_summary_status) {
    case 'summarized':
      return {
        labelKey:
          'coreBusiness.module.detail.attachmentAiSummaryStatus.summarized',
        className: 'bg-app-success/10 text-app-success',
      };
    case 'pending':
      return {
        labelKey:
          'coreBusiness.module.detail.attachmentAiSummaryStatus.pending',
        className: 'bg-app-warning/10 text-app-warning-text',
      };
    case 'processing':
      return {
        labelKey:
          'coreBusiness.module.detail.attachmentAiSummaryStatus.processing',
        className: 'bg-app-accent/10 text-app-accent',
      };
    case 'failed':
      return {
        labelKey: 'coreBusiness.module.detail.attachmentAiSummaryStatus.failed',
        className: 'bg-app-danger/10 text-app-danger',
      };
    default:
      return {
        labelKey:
          'coreBusiness.module.detail.attachmentAiSummaryStatus.notSummarized',
        className: 'bg-app-bg text-app-ink/55',
      };
  }
}

function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}
