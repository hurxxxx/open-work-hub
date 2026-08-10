import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
} from 'react';
import { useTranslation } from 'react-i18next';
import {
  Download,
  FileText,
  Loader2,
  Pencil,
  RefreshCw,
  Trash2,
  Upload,
  X,
} from 'lucide-react';
import { useConfirm, useToast } from '@open-alm/ui';

import { cn } from '@/src/lib/utils';
import { ApiRequestError } from '@/src/platform/api/client';
import { downloadBlobAsFile } from '@/src/platform/browser/browser-download';
import { formatByteSize } from '@/src/platform/format/byte-size';

import {
  deleteLegacyIssueRevisionMeetingAttachment,
  fetchLegacyIssueRevisionMeetingAttachmentBlob,
  fetchLegacyIssueRevisionMeetingAttachments,
  updateLegacyIssueRevisionMeetingAttachment,
  uploadLegacyIssueRevisionMeetingAttachment,
  type LegacyIssueRevisionMeetingAttachment,
} from '../api/legacy-issue-meeting-attachments-api';
import type {
  LegacyIssueRevision,
  LegacyIssueRevisionOverviewHistory,
} from '../api/legacy-issue-common-api';
import type {
  LegacyIssueDatasetKey,
  LegacyIssueViewKey,
} from '../legacy-issue-datasets';

const MEETING_ATTACHMENT_DESCRIPTION_MAX_LENGTH = 500;

export interface LegacyIssueRevisionMeetingMinutesRow {
  id: string;
  revision: LegacyIssueRevision | null;
  sourceHistory: LegacyIssueRevisionOverviewHistory | null;
}

type LegacyIssueRevisionMeetingMinutesCommonProps = {
  datasetKey: LegacyIssueDatasetKey;
  token: string | null | undefined;
  viewKey: LegacyIssueViewKey;
  workspaceSlug: string;
};

export type LegacyIssueRevisionMeetingMinutesProps =
  LegacyIssueRevisionMeetingMinutesCommonProps & {
    rows: LegacyIssueRevisionMeetingMinutesRow[];
  };

export type LegacyIssueRevisionMeetingAttachmentsPanelProps =
  LegacyIssueRevisionMeetingMinutesProps & {
    focusedHistoryId?: string | null;
    showPageHeader?: boolean;
  };

type PendingMeetingAttachment = {
  clientRequestId: string;
  description: string;
  error: string | null;
  file: File;
  id: string;
  status: 'pending' | 'uploading' | 'failed';
};

type PendingMeetingAttachmentsByHistoryId = Record<
  string,
  PendingMeetingAttachment[]
>;

type AttachmentListState = {
  canUpload: boolean;
  items: LegacyIssueRevisionMeetingAttachment[];
};

type MeetingAttachmentDescriptionEditor = {
  attachmentId: string;
  draft: string;
} | null;

export function LegacyIssueRevisionMeetingMinutes(
  props: LegacyIssueRevisionMeetingMinutesProps,
) {
  return <LegacyIssueRevisionMeetingAttachmentsPanel {...props} />;
}

export function LegacyIssueRevisionMeetingAttachmentsPanel({
  datasetKey,
  focusedHistoryId = null,
  rows,
  showPageHeader = true,
  token,
  viewKey,
  workspaceSlug,
}: LegacyIssueRevisionMeetingAttachmentsPanelProps) {
  const visibleRows = focusedHistoryId
    ? rows.filter((row) => row.sourceHistory?.id === focusedHistoryId)
    : rows;
  const { t, i18n } = useTranslation(['apps', 'common']);
  const toast = useToast();
  const { confirm, confirmDialog } = useConfirm();
  const [attachmentList, setAttachmentList] = useState<AttachmentListState>({
    canUpload: false,
    items: [],
  });
  const [pendingByHistoryId, setPendingByHistoryId] =
    useState<PendingMeetingAttachmentsByHistoryId>({});
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [busyAttachmentIds, setBusyAttachmentIds] = useState<Set<string>>(
    () => new Set(),
  );
  const [descriptionEditor, setDescriptionEditor] =
    useState<MeetingAttachmentDescriptionEditor>(null);
  const pendingIdRef = useRef(0);
  const requestIdRef = useRef(0);
  const mountedRef = useRef(false);
  const scopeKey = JSON.stringify([
    workspaceSlug,
    datasetKey,
    viewKey,
    token ?? null,
    focusedHistoryId,
  ]);
  const scopeKeyRef = useRef(scopeKey);
  scopeKeyRef.current = scopeKey;
  const isCurrentSession = useCallback(
    (expectedScopeKey: string) =>
      mountedRef.current && scopeKeyRef.current === expectedScopeKey,
    [],
  );

  const loadAttachments = useCallback(
    async ({ showLoading = true }: { showLoading?: boolean } = {}) => {
      if (!token || !workspaceSlug) {
        setLoading(false);
        return false;
      }
      const requestId = ++requestIdRef.current;
      const requestScopeKey = scopeKey;
      if (showLoading) setLoading(true);
      if (showLoading) setLoadFailed(false);
      try {
        const response = await fetchLegacyIssueRevisionMeetingAttachments({
          datasetKey,
          ...(focusedHistoryId ? { historyId: focusedHistoryId } : {}),
          token,
          viewKey,
          workspaceSlug,
        });
        if (
          !isCurrentSession(requestScopeKey) ||
          requestIdRef.current !== requestId
        ) {
          return false;
        }
        setAttachmentList({
          canUpload: response.can_upload,
          items: response.items,
        });
        return true;
      } catch (error) {
        if (
          isCurrentSession(requestScopeKey) &&
          requestIdRef.current === requestId
        ) {
          if (showLoading) setLoadFailed(true);
          toast.error(
            meetingMinutesErrorMessage(
              error,
              t('coreBusiness.module.meetingMinutes.errors.loadFailed'),
            ),
          );
        }
        return false;
      } finally {
        if (
          isCurrentSession(requestScopeKey) &&
          requestIdRef.current === requestId
        ) {
          setLoading(false);
        }
      }
    },
    [
      datasetKey,
      focusedHistoryId,
      isCurrentSession,
      scopeKey,
      t,
      toast,
      token,
      viewKey,
      workspaceSlug,
    ],
  );

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      requestIdRef.current += 1;
    };
  }, []);

  useEffect(() => {
    setAttachmentList({ canUpload: false, items: [] });
    setPendingByHistoryId({});
    setBusyAttachmentIds(new Set());
    setDescriptionEditor(null);
    void loadAttachments();
    return () => {
      requestIdRef.current += 1;
    };
  }, [loadAttachments]);

  const attachmentsByHistoryId = useMemo(() => {
    const grouped = new Map<string, LegacyIssueRevisionMeetingAttachment[]>();
    for (const attachment of attachmentList.items) {
      const current = grouped.get(attachment.overview_history_id) ?? [];
      current.push(attachment);
      grouped.set(attachment.overview_history_id, current);
    }
    for (const attachments of grouped.values()) {
      attachments.sort(
        (left, right) =>
          new Date(right.created_at).getTime() -
            new Date(left.created_at).getTime() ||
          left.filename.localeCompare(right.filename),
      );
    }
    return grouped;
  }, [attachmentList.items]);

  function addPendingFiles(
    historyId: string,
    event: ChangeEvent<HTMLInputElement>,
  ) {
    const files = Array.from(event.target.files ?? []);
    event.target.value = '';
    if (!attachmentList.canUpload || files.length === 0) return;
    setPendingByHistoryId((current) => ({
      ...current,
      [historyId]: [
        ...(current[historyId] ?? []),
        ...files.map((file) => {
          const sequence = ++pendingIdRef.current;
          return {
            clientRequestId: createMeetingAttachmentClientRequestId(sequence),
            description: '',
            error: null,
            file,
            id: `pending-meeting-attachment-${sequence}`,
            status: 'pending' as const,
          };
        }),
      ],
    }));
  }

  function updatePendingDescription(
    historyId: string,
    pendingId: string,
    description: string,
  ) {
    setPendingByHistoryId((current) => ({
      ...current,
      [historyId]: (current[historyId] ?? []).map((pending) =>
        pending.id === pendingId ? { ...pending, description } : pending,
      ),
    }));
  }

  function removePendingFile(historyId: string, pendingId: string) {
    setPendingByHistoryId((current) => ({
      ...current,
      [historyId]: (current[historyId] ?? []).filter(
        (pending) => pending.id !== pendingId,
      ),
    }));
  }

  async function uploadPendingFiles(historyId: string) {
    if (!token || !workspaceSlug || !attachmentList.canUpload) return;
    const targets = (pendingByHistoryId[historyId] ?? []).filter(
      (pending) => pending.status !== 'uploading',
    );
    if (targets.length === 0) return;
    const operationScopeKey = scopeKey;
    const targetIds = new Set(targets.map((target) => target.id));
    setPendingByHistoryId((current) => ({
      ...current,
      [historyId]: (current[historyId] ?? []).map((pending) =>
        targetIds.has(pending.id)
          ? { ...pending, error: null, status: 'uploading' }
          : pending,
      ),
    }));

    const uploaded: LegacyIssueRevisionMeetingAttachment[] = [];
    let failedCount = 0;
    for (const pending of targets) {
      if (!isCurrentSession(operationScopeKey)) {
        return;
      }
      try {
        const attachment = await uploadLegacyIssueRevisionMeetingAttachment({
          clientRequestId: pending.clientRequestId,
          datasetKey,
          description: pending.description || null,
          file: pending.file,
          historyId,
          token,
          viewKey,
          workspaceSlug,
        });
        if (!isCurrentSession(operationScopeKey)) {
          return;
        }
        uploaded.push(attachment);
        setAttachmentList((current) => ({
          ...current,
          items: upsertMeetingAttachments(current.items, [attachment]),
        }));
        setPendingByHistoryId((current) => ({
          ...current,
          [historyId]: (current[historyId] ?? []).filter(
            (item) => item.id !== pending.id,
          ),
        }));
      } catch (error) {
        if (!isCurrentSession(operationScopeKey)) {
          return;
        }
        failedCount += 1;
        const uploadError = meetingMinutesErrorMessage(
          error,
          t('coreBusiness.module.meetingMinutes.errors.uploadFailed'),
        );
        setPendingByHistoryId((current) => ({
          ...current,
          [historyId]: (current[historyId] ?? []).map((item) =>
            item.id === pending.id
              ? { ...item, error: uploadError, status: 'failed' }
              : item,
          ),
        }));
      }
    }
    if (uploaded.length > 0) {
      toast.success(
        t('coreBusiness.module.meetingMinutes.status.uploaded', {
          count: uploaded.length,
        }),
      );
    }
    if (failedCount > 0) {
      toast.error(
        t(
          uploaded.length > 0
            ? 'coreBusiness.module.meetingMinutes.errors.uploadPartialFailed'
            : 'coreBusiness.module.meetingMinutes.errors.uploadFailed',
        ),
      );
    }
    if (uploaded.length > 0) {
      await loadAttachments({ showLoading: false });
    }
  }

  async function saveDescription(
    attachment: LegacyIssueRevisionMeetingAttachment,
    descriptionDraft: string,
  ) {
    if (
      !token ||
      !workspaceSlug ||
      !attachment.can_edit_description ||
      busyAttachmentIds.has(attachment.id)
    ) {
      return;
    }
    const operationScopeKey = scopeKey;
    setBusyAttachmentIds((current) => addToSet(current, attachment.id));
    try {
      const updated = await updateLegacyIssueRevisionMeetingAttachment({
        attachmentId: attachment.id,
        datasetKey,
        description: descriptionDraft || null,
        token,
        viewKey,
        workspaceSlug,
      });
      if (!isCurrentSession(operationScopeKey)) {
        return;
      }
      setAttachmentList((current) => ({
        ...current,
        items: upsertMeetingAttachments(current.items, [updated]),
      }));
      setDescriptionEditor((current) =>
        current?.attachmentId === attachment.id ? null : current,
      );
      toast.success(
        t('coreBusiness.module.meetingMinutes.status.descriptionSaved'),
      );
      await loadAttachments({ showLoading: false });
    } catch (error) {
      if (isCurrentSession(operationScopeKey)) {
        toast.error(
          meetingMinutesErrorMessage(
            error,
            t(
              'coreBusiness.module.meetingMinutes.errors.descriptionSaveFailed',
            ),
          ),
        );
      }
    } finally {
      if (isCurrentSession(operationScopeKey)) {
        setBusyAttachmentIds((current) =>
          removeFromSet(current, attachment.id),
        );
      }
    }
  }

  async function downloadAttachment(
    attachment: LegacyIssueRevisionMeetingAttachment,
  ) {
    if (!token || !workspaceSlug || busyAttachmentIds.has(attachment.id)) {
      return;
    }
    const operationScopeKey = scopeKey;
    setBusyAttachmentIds((current) => addToSet(current, attachment.id));
    try {
      const blob = await fetchLegacyIssueRevisionMeetingAttachmentBlob({
        attachmentId: attachment.id,
        datasetKey,
        token,
        viewKey,
        workspaceSlug,
      });
      if (!isCurrentSession(operationScopeKey)) {
        return;
      }
      downloadBlobAsFile(blob, attachment.filename);
    } catch (error) {
      if (isCurrentSession(operationScopeKey)) {
        toast.error(
          meetingMinutesErrorMessage(
            error,
            t('coreBusiness.module.meetingMinutes.errors.downloadFailed'),
          ),
        );
      }
    } finally {
      if (isCurrentSession(operationScopeKey)) {
        setBusyAttachmentIds((current) =>
          removeFromSet(current, attachment.id),
        );
      }
    }
  }

  async function deleteAttachment(
    attachment: LegacyIssueRevisionMeetingAttachment,
  ) {
    if (
      !token ||
      !workspaceSlug ||
      !attachment.can_delete ||
      busyAttachmentIds.has(attachment.id)
    ) {
      return;
    }
    const operationScopeKey = scopeKey;
    const confirmed = await confirm({
      cancelLabel: t('common:actions.cancel'),
      confirmLabel: t('common:actions.delete'),
      description: t(
        'coreBusiness.module.meetingMinutes.confirmDeleteDescription',
        { filename: attachment.filename },
      ),
      title: t('coreBusiness.module.meetingMinutes.confirmDeleteTitle'),
      variant: 'danger',
    });
    if (!confirmed || !isCurrentSession(operationScopeKey)) {
      return;
    }
    setBusyAttachmentIds((current) => addToSet(current, attachment.id));
    try {
      await deleteLegacyIssueRevisionMeetingAttachment({
        attachmentId: attachment.id,
        datasetKey,
        token,
        viewKey,
        workspaceSlug,
      });
      if (!isCurrentSession(operationScopeKey)) {
        return;
      }
      setAttachmentList((current) => ({
        ...current,
        items: current.items.filter((item) => item.id !== attachment.id),
      }));
      setDescriptionEditor((current) =>
        current?.attachmentId === attachment.id ? null : current,
      );
      toast.success(t('coreBusiness.module.meetingMinutes.status.deleted'));
      await loadAttachments({ showLoading: false });
    } catch (error) {
      if (isCurrentSession(operationScopeKey)) {
        toast.error(
          meetingMinutesErrorMessage(
            error,
            t('coreBusiness.module.meetingMinutes.errors.deleteFailed'),
          ),
        );
      }
    } finally {
      if (isCurrentSession(operationScopeKey)) {
        setBusyAttachmentIds((current) =>
          removeFromSet(current, attachment.id),
        );
      }
    }
  }

  return (
    <div
      className={cn(
        'min-h-0',
        showPageHeader
          ? 'flex-1 overflow-auto bg-app-surface-sidebar px-4 py-5'
          : 'w-full',
      )}
    >
      {confirmDialog}
      <article
        className={cn(
          'w-full bg-white text-slate-950',
          showPageHeader &&
            'mx-auto max-w-[96rem] border border-slate-500 p-5 shadow-sm',
        )}
      >
        {showPageHeader ? (
          <header className="relative mb-3 flex min-h-9 items-center justify-center">
            <h2 className="text-center text-2xl font-bold tracking-normal">
              {t('coreBusiness.module.meetingMinutes.title')}
            </h2>
            <button
              className="absolute right-0 inline-flex h-9 items-center justify-center gap-1.5 border border-slate-500 bg-white px-3 text-[13px] font-medium text-slate-800 hover:bg-slate-100 disabled:opacity-45"
              disabled={loading}
              type="button"
              onClick={() => void loadAttachments()}
            >
              <RefreshCw className={cn(loading && 'animate-spin')} size={15} />
              {t('coreBusiness.module.meetingMinutes.refresh')}
            </button>
          </header>
        ) : null}

        {loading ? (
          <div
            className="flex min-h-48 items-center justify-center gap-2 text-slate-500"
            role="status"
          >
            <Loader2 className="animate-spin" size={18} />
            {t('coreBusiness.module.meetingMinutes.loading')}
          </div>
        ) : loadFailed ? (
          <div
            className="flex min-h-48 flex-col items-center justify-center gap-3 text-slate-600"
            role="alert"
          >
            <span>
              {t('coreBusiness.module.meetingMinutes.errors.loadFailed')}
            </span>
            <button
              className="inline-flex h-9 items-center gap-1.5 border border-slate-500 bg-white px-3 text-[13px] font-medium hover:bg-slate-100"
              type="button"
              onClick={() => void loadAttachments()}
            >
              <RefreshCw size={15} />
              {t('coreBusiness.module.meetingMinutes.retry')}
            </button>
          </div>
        ) : visibleRows.length === 0 ? (
          <div className="border border-slate-300 px-3 py-8 text-center text-slate-500">
            {t('coreBusiness.module.meetingMinutes.noRows')}
          </div>
        ) : (
          <div className="flex min-w-0 flex-col gap-3">
            {visibleRows.map((row) => {
              const revision = row.revision;
              const history = row.sourceHistory;
              const historyId = history?.id ?? null;
              const attachments = historyId
                ? (attachmentsByHistoryId.get(historyId) ?? [])
                : [];
              const pending = historyId
                ? (pendingByHistoryId[historyId] ?? [])
                : [];
              const rowUploading = pending.some(
                (item) => item.status === 'uploading',
              );
              const revisionLabel = meetingRevisionLabel(row, t);
              const revisionDate =
                history?.revised_on ??
                revision?.published_at ??
                revision?.updated_at ??
                null;
              const summary = displayMeetingRevisionSummary(
                history ? history.summary : revision?.note,
                t,
              );
              const isEmpty = attachments.length === 0 && pending.length === 0;
              const headingId = `meeting-revision-heading-${row.id}`;
              return (
                <section
                  aria-labelledby={headingId}
                  className="min-w-0 overflow-hidden border border-slate-400 bg-white text-[13px] leading-5"
                  data-testid={`meeting-row-${row.id}`}
                  key={row.id}
                >
                  <header className="flex min-w-0 items-center gap-3 border-b border-slate-300 bg-slate-50 px-3 py-2">
                    <h3
                      className="shrink-0 text-lg font-extrabold tracking-tight text-slate-950"
                      id={headingId}
                    >
                      {revisionLabel}
                    </h3>
                    <time
                      className="shrink-0 whitespace-nowrap text-[12px] font-medium text-slate-500"
                      dateTime={revisionDate ?? undefined}
                    >
                      {formatMeetingDate(revisionDate, i18n.language)}
                    </time>
                    <p
                      className="min-w-0 flex-1 truncate text-slate-700"
                      title={summary}
                    >
                      {summary}
                    </p>
                  </header>
                  <div className="flex min-w-0 flex-col gap-2 px-3 py-2">
                    {attachments.length > 0 ? (
                      <ul className="min-w-0 divide-y divide-slate-200 overflow-x-auto border border-slate-300">
                        {attachments.map((attachment) => (
                          <MeetingAttachmentItem
                            attachment={attachment}
                            busy={busyAttachmentIds.has(attachment.id)}
                            descriptionDraft={
                              descriptionEditor?.attachmentId === attachment.id
                                ? descriptionEditor.draft
                                : ''
                            }
                            editing={
                              descriptionEditor?.attachmentId === attachment.id
                            }
                            key={attachment.id}
                            locale={i18n.language}
                            onCancelEdit={() =>
                              setDescriptionEditor((current) =>
                                current?.attachmentId === attachment.id
                                  ? null
                                  : current,
                              )
                            }
                            onDelete={() => void deleteAttachment(attachment)}
                            onDescriptionDraftChange={(draft) =>
                              setDescriptionEditor((current) =>
                                current?.attachmentId === attachment.id
                                  ? { ...current, draft }
                                  : current,
                              )
                            }
                            onDownload={() =>
                              void downloadAttachment(attachment)
                            }
                            onEdit={() =>
                              setDescriptionEditor({
                                attachmentId: attachment.id,
                                draft: attachment.description ?? '',
                              })
                            }
                            onSaveDescription={() => {
                              if (
                                descriptionEditor?.attachmentId !==
                                attachment.id
                              ) {
                                return;
                              }
                              void saveDescription(
                                attachment,
                                descriptionEditor.draft,
                              );
                            }}
                          />
                        ))}
                      </ul>
                    ) : null}
                    {pending.length > 0 ? (
                      <div
                        className={cn(
                          'flex min-w-0 flex-col gap-2',
                          attachments.length > 0 &&
                            'border-t border-slate-200 pt-2',
                        )}
                      >
                        <p className="font-medium text-slate-700">
                          {t(
                            'coreBusiness.module.meetingMinutes.pendingFiles',
                            { count: pending.length },
                          )}
                        </p>
                        {pending.map((item) => (
                          <div
                            className="rounded border border-dashed border-slate-400 bg-slate-50 p-2"
                            key={item.id}
                          >
                            <div className="flex min-w-0 items-center gap-2">
                              {item.status === 'uploading' ? (
                                <Loader2
                                  className="shrink-0 animate-spin"
                                  size={15}
                                />
                              ) : (
                                <FileText className="shrink-0" size={15} />
                              )}
                              <span className="min-w-0 flex-1 truncate font-medium">
                                {item.file.name}
                              </span>
                              <span className="shrink-0 text-slate-500">
                                {formatByteSize(item.file.size, {
                                  locale: i18n.language,
                                  trailingZeros: 'trim',
                                  units: ['KB', 'MB', 'GB'],
                                })}
                              </span>
                              <button
                                aria-label={t(
                                  'coreBusiness.module.meetingMinutes.removePendingForFile',
                                  { filename: item.file.name },
                                )}
                                className="inline-flex h-7 w-7 shrink-0 items-center justify-center border border-slate-300 bg-white hover:bg-slate-100 disabled:opacity-45"
                                disabled={item.status === 'uploading'}
                                title={t(
                                  'coreBusiness.module.meetingMinutes.removePending',
                                )}
                                type="button"
                                onClick={() => {
                                  if (historyId) {
                                    removePendingFile(historyId, item.id);
                                  }
                                }}
                              >
                                <X size={14} />
                              </button>
                            </div>
                            <textarea
                              aria-label={t(
                                'coreBusiness.module.meetingMinutes.descriptionForFile',
                                { filename: item.file.name },
                              )}
                              className="mt-2 min-h-16 w-full resize-y border border-slate-300 bg-white px-2 py-1 disabled:opacity-60"
                              disabled={item.status === 'uploading'}
                              maxLength={
                                MEETING_ATTACHMENT_DESCRIPTION_MAX_LENGTH
                              }
                              placeholder={t(
                                'coreBusiness.module.meetingMinutes.descriptionPlaceholder',
                              )}
                              value={item.description}
                              onChange={(event) => {
                                if (historyId) {
                                  updatePendingDescription(
                                    historyId,
                                    item.id,
                                    event.target.value,
                                  );
                                }
                              }}
                            />
                            <div className="mt-1 flex items-start justify-between gap-2 text-[11px]">
                              <span
                                className={cn(
                                  'min-w-0 flex-1',
                                  item.error
                                    ? 'text-red-700'
                                    : 'text-slate-500',
                                )}
                                role={item.error ? 'alert' : undefined}
                              >
                                {item.error ?? ''}
                              </span>
                              <span className="shrink-0 text-slate-500">
                                {t(
                                  'coreBusiness.module.detail.attachmentDescriptionLength',
                                  {
                                    count: item.description.length,
                                    max: MEETING_ATTACHMENT_DESCRIPTION_MAX_LENGTH,
                                  },
                                )}
                              </span>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : null}
                    {attachmentList.canUpload && historyId ? (
                      <div
                        className={cn(
                          'flex flex-wrap items-center gap-2',
                          isEmpty
                            ? 'justify-between'
                            : 'border-t border-slate-200 pt-2',
                        )}
                      >
                        {isEmpty ? (
                          <span className="min-w-0 flex-1 text-slate-500">
                            {t(
                              'coreBusiness.module.meetingMinutes.noAttachments',
                            )}
                          </span>
                        ) : null}
                        <label
                          className={cn(
                            'inline-flex h-8 cursor-pointer items-center gap-1.5 border border-slate-500 bg-white px-2 font-medium text-slate-800 hover:bg-slate-100',
                            rowUploading && 'pointer-events-none opacity-45',
                          )}
                        >
                          <FileText size={14} />
                          {t('coreBusiness.module.meetingMinutes.selectFiles')}
                          <input
                            className="sr-only"
                            disabled={rowUploading}
                            multiple
                            type="file"
                            onChange={(event) =>
                              addPendingFiles(historyId, event)
                            }
                          />
                        </label>
                        {pending.length > 0 ? (
                          <button
                            className="inline-flex h-8 items-center gap-1.5 border border-slate-900 bg-slate-900 px-2 font-medium text-white disabled:opacity-45"
                            disabled={rowUploading}
                            type="button"
                            onClick={() => void uploadPendingFiles(historyId)}
                          >
                            {rowUploading ? (
                              <Loader2 className="animate-spin" size={14} />
                            ) : (
                              <Upload size={14} />
                            )}
                            {t('coreBusiness.module.meetingMinutes.upload')}
                          </button>
                        ) : null}
                      </div>
                    ) : isEmpty ? (
                      <span className="py-1 text-slate-500">
                        {t('coreBusiness.module.meetingMinutes.noAttachments')}
                      </span>
                    ) : null}
                  </div>
                </section>
              );
            })}
          </div>
        )}
      </article>
    </div>
  );
}

function MeetingAttachmentItem({
  attachment,
  busy,
  descriptionDraft,
  editing,
  locale,
  onCancelEdit,
  onDelete,
  onDescriptionDraftChange,
  onDownload,
  onEdit,
  onSaveDescription,
}: {
  attachment: LegacyIssueRevisionMeetingAttachment;
  busy: boolean;
  descriptionDraft: string;
  editing: boolean;
  locale: string;
  onCancelEdit: () => void;
  onDelete: () => void;
  onDescriptionDraftChange: (description: string) => void;
  onDownload: () => void;
  onEdit: () => void;
  onSaveDescription: () => void;
}) {
  const { t } = useTranslation(['apps', 'common']);
  const emptyValue = t('coreBusiness.grid.emptyValue');
  return (
    <li className="bg-white px-2 py-1.5">
      <div className="flex min-w-[52rem] items-center gap-2">
        {busy ? (
          <Loader2 className="shrink-0 animate-spin" size={15} />
        ) : (
          <FileText className="shrink-0" size={15} />
        )}
        <button
          className="flex min-w-0 basis-60 items-center gap-1.5 text-left font-semibold text-app-accent hover:underline disabled:opacity-45"
          disabled={busy}
          title={t('coreBusiness.module.meetingMinutes.download')}
          type="button"
          onClick={onDownload}
        >
          <Download className="shrink-0" size={14} />
          <span className="truncate">{attachment.filename}</span>
        </button>
        <span className="w-20 shrink-0 text-right text-[12px] text-slate-500">
          {formatByteSize(attachment.size_bytes, {
            locale,
            trailingZeros: 'trim',
            units: ['KB', 'MB', 'GB'],
          })}
        </span>
        <span
          className="w-28 shrink-0 truncate text-[12px] text-slate-500"
          title={`${t('coreBusiness.module.meetingMinutes.uploadedBy')} ${
            attachment.uploaded_by_name || emptyValue
          }`}
        >
          {attachment.uploaded_by_name || emptyValue}
        </span>
        <time
          className="w-40 shrink-0 truncate text-[12px] text-slate-500"
          dateTime={attachment.created_at}
          title={`${t('coreBusiness.module.meetingMinutes.uploadedAt')} ${formatMeetingDateTime(
            attachment.created_at,
            locale,
          )}`}
        >
          {formatMeetingDateTime(attachment.created_at, locale)}
        </time>
        <span
          className="min-w-0 flex-1 truncate text-slate-600"
          title={attachment.description || emptyValue}
        >
          {attachment.description || emptyValue}
        </span>
        {attachment.can_edit_description ? (
          <button
            aria-label={t(
              'coreBusiness.module.meetingMinutes.editDescriptionForFile',
              { filename: attachment.filename },
            )}
            className="inline-flex h-7 w-7 shrink-0 items-center justify-center border border-slate-300 bg-white hover:bg-slate-100 disabled:opacity-45"
            disabled={busy || editing}
            title={t('coreBusiness.module.meetingMinutes.editDescription')}
            type="button"
            onClick={onEdit}
          >
            <Pencil size={14} />
          </button>
        ) : null}
        {attachment.can_delete ? (
          <button
            aria-label={t('coreBusiness.module.meetingMinutes.deleteFile', {
              filename: attachment.filename,
            })}
            className="inline-flex h-7 w-7 shrink-0 items-center justify-center border border-red-400 bg-white text-red-700 hover:bg-red-50 disabled:opacity-45"
            disabled={busy}
            title={t('common:actions.delete')}
            type="button"
            onClick={onDelete}
          >
            <Trash2 size={14} />
          </button>
        ) : null}
      </div>
      {editing ? (
        <div className="mt-1 border-t border-slate-200 pt-2">
          <textarea
            aria-label={t(
              'coreBusiness.module.meetingMinutes.descriptionForFile',
              { filename: attachment.filename },
            )}
            className="min-h-16 w-full resize-y border border-slate-300 bg-white px-2 py-1"
            maxLength={MEETING_ATTACHMENT_DESCRIPTION_MAX_LENGTH}
            placeholder={t(
              'coreBusiness.module.meetingMinutes.descriptionPlaceholder',
            )}
            value={descriptionDraft}
            onChange={(event) => onDescriptionDraftChange(event.target.value)}
          />
          <div className="mt-1 flex items-center justify-between gap-2">
            <span className="text-[11px] text-slate-500">
              {t('coreBusiness.module.detail.attachmentDescriptionLength', {
                count: descriptionDraft.length,
                max: MEETING_ATTACHMENT_DESCRIPTION_MAX_LENGTH,
              })}
            </span>
            <div className="flex gap-1">
              <button
                className="inline-flex h-7 items-center border border-slate-900 bg-slate-900 px-2 text-[12px] font-medium text-white disabled:opacity-45"
                disabled={busy}
                type="button"
                onClick={onSaveDescription}
              >
                {t('common:actions.save')}
              </button>
              <button
                className="inline-flex h-7 items-center border border-slate-400 bg-white px-2 text-[12px] font-medium disabled:opacity-45"
                disabled={busy}
                type="button"
                onClick={onCancelEdit}
              >
                {t('common:actions.cancel')}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </li>
  );
}

function meetingRevisionLabel(
  row: LegacyIssueRevisionMeetingMinutesRow,
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
  if (!row.revision) return '-';
  return translate('coreBusiness.revision.publishedRevision', {
    revision: row.revision.revision_no ?? '-',
  });
}

const MEETING_SYSTEM_REVISION_SUMMARY_KEYS = {
  'Initial compressor source import':
    'coreBusiness.module.overview.initialCompressorSourceImport',
  'Initial revision': 'coreBusiness.module.overview.initialRevision',
} as const;

function displayMeetingRevisionSummary(
  summary: string | null | undefined,
  translate: (key: string) => string,
): string {
  if (!summary?.trim()) return '-';
  const translationKey =
    MEETING_SYSTEM_REVISION_SUMMARY_KEYS[
      summary.trim() as keyof typeof MEETING_SYSTEM_REVISION_SUMMARY_KEYS
    ];
  return translationKey ? translate(translationKey) : summary;
}

function formatMeetingDate(value: string | null, locale: string): string {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(locale);
}

function formatMeetingDateTime(value: string, locale: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(locale);
}

function upsertMeetingAttachments(
  current: LegacyIssueRevisionMeetingAttachment[],
  updates: LegacyIssueRevisionMeetingAttachment[],
): LegacyIssueRevisionMeetingAttachment[] {
  const updatesById = new Map(updates.map((item) => [item.id, item]));
  const retained = current.map((item) => updatesById.get(item.id) ?? item);
  const currentIds = new Set(current.map((item) => item.id));
  return [...retained, ...updates.filter((item) => !currentIds.has(item.id))];
}

function addToSet(current: Set<string>, value: string): Set<string> {
  const next = new Set(current);
  next.add(value);
  return next;
}

function removeFromSet(current: Set<string>, value: string): Set<string> {
  const next = new Set(current);
  next.delete(value);
  return next;
}

function createMeetingAttachmentClientRequestId(sequence: number): string {
  if (typeof globalThis.crypto?.randomUUID === 'function') {
    return globalThis.crypto.randomUUID();
  }
  return `meeting-attachment-${Date.now()}-${sequence}-${Math.random()
    .toString(36)
    .slice(2)}`;
}

function meetingMinutesErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiRequestError) {
    const detail =
      typeof error.payload === 'object' &&
      error.payload !== null &&
      'detail' in error.payload &&
      typeof error.payload.detail === 'string'
        ? error.payload.detail
        : '';
    return detail || fallback;
  }
  return fallback;
}
