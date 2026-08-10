import { useMemo, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import {
  GitCompareArrows,
  GitPullRequestDraft,
  History,
  Loader2,
  RotateCcw,
  Save,
  Send,
  X,
} from 'lucide-react';

import { cn } from '@/src/lib/utils';
import { LegacyIssueRevisionCompareGrid } from './LegacyIssueRevisionCompareGrid';
import type { LegacyIssueRevisionCompareView } from './legacy-issue-revision-compare-grid-model';

export type { LegacyIssueRevisionCompareView } from './legacy-issue-revision-compare-grid-model';

export type LegacyIssueRevisionView = {
  id: string;
  revision_no: number | null;
  status: string;
  base_revision_id: string | null;
  locked_by_id: string | null;
  locked_by_name: string | null;
  published_by_name: string | null;
  note: string | null;
  reviewer_id?: string | null;
  approver_id?: string | null;
  reviewed_at?: string | null;
  approved_at?: string | null;
  created_at: string;
  updated_at: string;
  published_at: string | null;
};

export type LegacyIssueRevisionEventView = {
  id: string;
  revision_id: string;
  action: string;
  actor_name: string | null;
  actor_email: string | null;
  note: string | null;
  details: Record<string, unknown> | null;
  created_at: string;
};

export function LegacyIssueRevisionBar({
  activeDraft,
  busy,
  canEditActiveDraft,
  canEditCurrentDraft,
  canForceCancelActiveDraft = false,
  canPublishCurrentDraft = true,
  comparing = false,
  compareResult,
  current,
  dirtyChangeCount = 0,
  events,
  onCancelDraft,
  onCompare,
  onPublishDraft,
  onRestoreRevision,
  onSaveDraftChanges,
  onSelectRevision,
  onStartDraft,
  revisions,
  savingDraftChanges = false,
}: {
  activeDraft: LegacyIssueRevisionView | null;
  busy?: boolean;
  canEditActiveDraft: boolean;
  canEditCurrentDraft: boolean;
  canForceCancelActiveDraft?: boolean;
  canPublishCurrentDraft?: boolean;
  comparing?: boolean;
  compareResult: LegacyIssueRevisionCompareView | null;
  current: LegacyIssueRevisionView | null;
  dirtyChangeCount?: number;
  events: LegacyIssueRevisionEventView[];
  onCancelDraft: (revision: LegacyIssueRevisionView) => void | Promise<void>;
  onCompare: (
    leftRevisionId: string,
    rightRevisionId: string,
  ) => void | Promise<void>;
  onPublishDraft: (
    revision: LegacyIssueRevisionView,
    note: string,
  ) => void | Promise<void>;
  onRestoreRevision: (
    revision: LegacyIssueRevisionView,
  ) => void | Promise<void>;
  onSaveDraftChanges?: () => void | Promise<void>;
  onSelectRevision: (revisionId: string) => void;
  onStartDraft: (baseRevisionId?: string | null) => void | Promise<void>;
  revisions: LegacyIssueRevisionView[];
  savingDraftChanges?: boolean;
}) {
  const { t } = useTranslation(['apps']);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [publishedOnly, setPublishedOnly] = useState(false);
  const [compareOpen, setCompareOpen] = useState(false);
  const [pendingPublishRevision, setPendingPublishRevision] =
    useState<LegacyIssueRevisionView | null>(null);
  const [actionMessage, setActionMessage] = useState('');
  const [actionError, setActionError] = useState(false);
  const visibleRevisions = useMemo(
    () => revisions.filter(isVisibleLegacyIssueRevision),
    [revisions],
  );
  const visibleRevisionIds = useMemo(
    () => new Set(visibleRevisions.map((revision) => revision.id)),
    [visibleRevisions],
  );
  const visibleRevisionEvents = useMemo(
    () =>
      events.filter(
        (event) =>
          visibleRevisionIds.has(event.revision_id) ||
          event.action === 'force_cancel',
      ),
    [events, visibleRevisionIds],
  );
  const publishedRevisions = useMemo(
    () =>
      visibleRevisions.filter((revision) => revision.status === 'published'),
    [visibleRevisions],
  );
  const revisionById = useMemo(
    () => new Map(visibleRevisions.map((revision) => [revision.id, revision])),
    [visibleRevisions],
  );
  const historyEvents = useMemo(
    () =>
      publishedOnly
        ? visibleRevisionEvents.filter((event) => isPublishEvent(event))
        : visibleRevisionEvents,
    [publishedOnly, visibleRevisionEvents],
  );
  const isDraft = current?.status === 'draft';
  const canRestore = current?.status === 'published';
  const openPublishAction = (revision: LegacyIssueRevisionView) => {
    setPendingPublishRevision(revision);
    setActionMessage('');
    setActionError(false);
  };
  const submitPublishAction = async () => {
    const note = actionMessage.trim();
    if (!pendingPublishRevision || !note) {
      setActionError(true);
      return;
    }
    await onPublishDraft(pendingPublishRevision, note);
    setPendingPublishRevision(null);
    setActionMessage('');
    setActionError(false);
  };

  return (
    <div className="border-b border-app-border bg-app-bg">
      <div
        className="overflow-x-auto px-4 py-1.5"
        data-testid="legacy-issue-revision-toolbar"
      >
        <div className="flex min-w-max flex-nowrap items-center gap-2">
          <span
            className={cn(
              'inline-flex h-7 shrink-0 items-center rounded-md border px-2 app-text-caption font-semibold',
              isDraft
                ? 'border-app-warning/30 bg-app-warning/10 text-app-warning-text'
                : 'border-app-success/30 bg-app-success/10 text-app-success',
            )}
          >
            {current
              ? revisionLabel(current, t)
              : t('coreBusiness.revision.loading')}
          </span>
          <select
            className="app-field-input-sm !w-36 min-w-36 max-w-36 shrink-0"
            disabled={busy || savingDraftChanges || dirtyChangeCount > 0}
            value={current?.id ?? ''}
            onChange={(event) => onSelectRevision(event.target.value)}
          >
            {visibleRevisions.map((revision) => (
              <option key={revision.id} value={revision.id}>
                {revisionOptionLabel(revision, revisionById, t)}
              </option>
            ))}
          </select>

          {isDraft && current ? (
            canEditCurrentDraft ? (
              <>
                <RevisionButton
                  disabled={busy || savingDraftChanges || !onSaveDraftChanges}
                  icon={
                    savingDraftChanges ? (
                      <Loader2 size={14} className="animate-spin" />
                    ) : (
                      <Save size={14} />
                    )
                  }
                  label={t(
                    dirtyChangeCount > 0
                      ? 'coreBusiness.revision.saveDraft'
                      : 'coreBusiness.revision.finishEditing',
                  )}
                  onClick={() => onSaveDraftChanges?.()}
                />
                <RevisionButton
                  disabled={
                    busy || savingDraftChanges || !canPublishCurrentDraft
                  }
                  icon={
                    busy ? (
                      <Loader2 size={14} className="animate-spin" />
                    ) : (
                      <Send size={14} />
                    )
                  }
                  label={t('coreBusiness.revision.publish')}
                  onClick={() => openPublishAction(current)}
                />
                <RevisionButton
                  disabled={busy || savingDraftChanges}
                  icon={<X size={14} />}
                  label={t('coreBusiness.revision.cancelDraft')}
                  onClick={() => onCancelDraft(current)}
                />
              </>
            ) : canForceCancelActiveDraft ? (
              <RevisionButton
                danger
                disabled={busy || savingDraftChanges}
                icon={<X size={14} />}
                label={t('coreBusiness.revision.forceCancelDraft')}
                onClick={() => onCancelDraft(current)}
              />
            ) : current.locked_by_id ? null : (
              <RevisionButton
                disabled={busy || savingDraftChanges || dirtyChangeCount > 0}
                icon={
                  busy ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : (
                    <GitPullRequestDraft size={14} />
                  )
                }
                label={t('coreBusiness.revision.startDraft')}
                onClick={() => onStartDraft(current.base_revision_id)}
              />
            )
          ) : activeDraft && current?.id !== activeDraft.id ? (
            <>
              <RevisionButton
                disabled={busy || savingDraftChanges || dirtyChangeCount > 0}
                icon={
                  busy ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : (
                    <GitPullRequestDraft size={14} />
                  )
                }
                label={t('coreBusiness.revision.openDraft')}
                onClick={() => onSelectRevision(activeDraft.id)}
              />
              {canEditActiveDraft || canForceCancelActiveDraft ? (
                <RevisionButton
                  danger={canForceCancelActiveDraft}
                  disabled={busy}
                  icon={<X size={14} />}
                  label={t(
                    canForceCancelActiveDraft
                      ? 'coreBusiness.revision.forceCancelDraft'
                      : 'coreBusiness.revision.cancelDraft',
                  )}
                  onClick={() => onCancelDraft(activeDraft)}
                />
              ) : null}
            </>
          ) : (
            <RevisionButton
              disabled={busy || savingDraftChanges || dirtyChangeCount > 0}
              icon={
                busy ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <GitPullRequestDraft size={14} />
                )
              }
              label={t('coreBusiness.revision.startDraft')}
              onClick={() => onStartDraft(current?.id)}
            />
          )}

          <RevisionButton
            disabled={
              busy ||
              savingDraftChanges ||
              dirtyChangeCount > 0 ||
              !canRestore ||
              Boolean(activeDraft)
            }
            icon={<RotateCcw size={14} />}
            label={t('coreBusiness.revision.restore')}
            onClick={() => {
              if (current) void onRestoreRevision(current);
            }}
          />
          <RevisionButton
            disabled={
              publishedRevisions.length < 2 && visibleRevisions.length < 2
            }
            icon={<GitCompareArrows size={14} />}
            label={t('coreBusiness.revision.compare')}
            onClick={() => setCompareOpen(true)}
          />
          <RevisionButton
            icon={<History size={14} />}
            label={t('coreBusiness.revision.history')}
            onClick={() => setHistoryOpen(true)}
          />
          {current?.locked_by_name && isDraft ? (
            <span className="app-text-caption text-app-ink/50">
              {t('coreBusiness.revision.lockedBy', {
                name: current.locked_by_name,
              })}
            </span>
          ) : null}
        </div>
      </div>

      {historyOpen ? (
        <RevisionModal
          title={t('coreBusiness.revision.history')}
          onClose={() => setHistoryOpen(false)}
        >
          <div className="mb-3 flex items-center justify-between gap-3">
            <label className="inline-flex items-center gap-2 app-text-caption text-app-ink/70">
              <input
                checked={publishedOnly}
                className="size-4 accent-app-accent"
                type="checkbox"
                onChange={(event) => setPublishedOnly(event.target.checked)}
              />
              <span>{t('coreBusiness.revision.showPublishedOnly')}</span>
            </label>
          </div>
          {visibleRevisionEvents.length === 0 ? (
            <p className="app-text-caption text-app-ink/50">
              {t('coreBusiness.revision.noHistory')}
            </p>
          ) : historyEvents.length === 0 ? (
            <p className="app-text-caption text-app-ink/50">
              {t('coreBusiness.revision.noFilteredHistory')}
            </p>
          ) : (
            <div className="max-h-[60vh] overflow-auto rounded-md border border-app-border">
              <table className="min-w-full border-collapse app-text-caption">
                <thead className="sticky top-0 bg-app-surface-sidebar">
                  <tr>
                    <th className="border-b border-app-border px-2 py-2 text-left">
                      {t('coreBusiness.revision.historyOccurredAt')}
                    </th>
                    <th className="border-b border-app-border px-2 py-2 text-left">
                      {t('coreBusiness.revision.historyAction')}
                    </th>
                    <th className="border-b border-app-border px-2 py-2 text-left">
                      {t('coreBusiness.revision.historyRevision')}
                    </th>
                    <th className="border-b border-app-border px-2 py-2 text-left">
                      {t('coreBusiness.revision.historyInfo')}
                    </th>
                    <th className="border-b border-app-border px-2 py-2 text-left">
                      {t('coreBusiness.revision.historyActor')}
                    </th>
                    <th className="border-b border-app-border px-2 py-2 text-left">
                      {t('coreBusiness.revision.historyMessage')}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {historyEvents.map((event) => {
                    const published = isPublishEvent(event);
                    return (
                      <tr
                        key={event.id}
                        className={cn(
                          'odd:bg-app-surface-sidebar/60',
                          published &&
                            'bg-app-success/10 odd:bg-app-success/10',
                        )}
                      >
                        <td className="border-b border-app-border px-2 py-2 align-top text-app-ink/60">
                          {formatDateTime(event.created_at)}
                        </td>
                        <td className="border-b border-app-border px-2 py-2 align-top font-semibold">
                          {published ? (
                            <span className="inline-flex rounded-md border border-app-success/30 bg-app-success/15 px-2 py-0.5 text-app-success-text">
                              {t(
                                `coreBusiness.revision.events.${event.action}`,
                                {
                                  defaultValue: event.action,
                                },
                              )}
                            </span>
                          ) : (
                            t(`coreBusiness.revision.events.${event.action}`, {
                              defaultValue: event.action,
                            })
                          )}
                        </td>
                        <td className="border-b border-app-border px-2 py-2 align-top">
                          {revisionEventLabel(event, revisionById, t)}
                        </td>
                        <td className="border-b border-app-border px-2 py-2 align-top text-app-ink/65">
                          {revisionEventInfo(event, revisionById, t)}
                        </td>
                        <td className="border-b border-app-border px-2 py-2 align-top">
                          {event.actor_name ||
                            event.actor_email ||
                            t('coreBusiness.history.unknownActor')}
                        </td>
                        <td className="whitespace-pre-wrap border-b border-app-border px-2 py-2 align-top">
                          {event.note || t('coreBusiness.grid.emptyValue')}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </RevisionModal>
      ) : null}

      {pendingPublishRevision ? (
        <RevisionActionModal
          busy={busy}
          error={actionError}
          message={actionMessage}
          onChange={(value) => {
            setActionMessage(value);
            if (value.trim()) setActionError(false);
          }}
          onClose={() => {
            setPendingPublishRevision(null);
            setActionMessage('');
            setActionError(false);
          }}
          onSubmit={() => void submitPublishAction()}
        />
      ) : null}

      {compareOpen ? (
        <LegacyIssueRevisionCompareModal
          comparing={comparing}
          compareResult={compareResult}
          current={current}
          onClose={() => setCompareOpen(false)}
          onCompare={onCompare}
          revisions={visibleRevisions}
        />
      ) : null}
    </div>
  );
}

function RevisionActionModal({
  busy,
  error,
  message,
  onChange,
  onClose,
  onSubmit,
}: {
  busy?: boolean;
  error: boolean;
  message: string;
  onChange: (value: string) => void;
  onClose: () => void;
  onSubmit: () => void;
}) {
  const { t } = useTranslation(['apps']);
  return (
    <RevisionModal
      title={t('coreBusiness.revision.publishMessageTitle')}
      onClose={onClose}
    >
      <form
        className="space-y-3"
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit();
        }}
      >
        <label className="block">
          <span className="mb-1 block app-text-caption font-semibold text-app-ink/70">
            {t('coreBusiness.revision.messageLabel')}
          </span>
          <textarea
            className="min-h-28 w-full resize-y rounded-md border border-app-border bg-app-bg px-3 py-2 app-text-body-sm outline-none focus:border-app-accent"
            maxLength={2000}
            placeholder={t('coreBusiness.revision.messagePlaceholder')}
            value={message}
            onChange={(event) => onChange(event.target.value)}
          />
        </label>
        {error ? (
          <p className="app-text-caption text-app-danger">
            {t('coreBusiness.revision.messageRequired')}
          </p>
        ) : null}
        <div className="flex justify-end gap-2">
          <button
            className="h-8 rounded-md border border-app-border px-3 app-text-caption hover:bg-app-surface-hover"
            disabled={busy}
            type="button"
            onClick={onClose}
          >
            {t('coreBusiness.module.actions.close')}
          </button>
          <button
            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-app-accent bg-app-accent px-3 app-text-caption font-semibold text-app-accent-fg disabled:cursor-not-allowed disabled:opacity-50"
            disabled={busy}
            type="submit"
          >
            {busy ? <Loader2 size={14} className="animate-spin" /> : null}
            {t('coreBusiness.revision.confirmAction')}
          </button>
        </div>
      </form>
    </RevisionModal>
  );
}

export function LegacyIssueRevisionCompareModal({
  comparing = false,
  compareResult,
  current,
  initialLeftRevisionId,
  initialRightRevisionId,
  onClose,
  onCompare,
  revisions,
}: {
  comparing?: boolean;
  compareResult: LegacyIssueRevisionCompareView | null;
  current: LegacyIssueRevisionView | null;
  initialLeftRevisionId?: string | null;
  initialRightRevisionId?: string | null;
  onClose: () => void;
  onCompare: (
    leftRevisionId: string,
    rightRevisionId: string,
  ) => void | Promise<void>;
  revisions: LegacyIssueRevisionView[];
}) {
  const { t } = useTranslation(['apps']);
  const [leftRevisionId, setLeftRevisionId] = useState(
    initialLeftRevisionId ?? revisions[1]?.id ?? revisions[0]?.id ?? '',
  );
  const [rightRevisionId, setRightRevisionId] = useState(
    initialRightRevisionId ?? current?.id ?? revisions[0]?.id ?? '',
  );
  const revisionById = useMemo(
    () => new Map(revisions.map((revision) => [revision.id, revision])),
    [revisions],
  );
  const changedRows =
    compareResult?.rows.filter((row) => row.status !== 'unchanged') ?? [];
  return (
    <RevisionModal
      contentClassName="flex min-h-0 flex-1 flex-col overflow-hidden"
      title={t('coreBusiness.revision.compare')}
      wide
      onClose={onClose}
    >
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <RevisionSelect
          label={t('coreBusiness.revision.leftRevision')}
          revisions={revisions}
          value={leftRevisionId}
          onChange={setLeftRevisionId}
        />
        <RevisionSelect
          label={t('coreBusiness.revision.rightRevision')}
          revisions={revisions}
          value={rightRevisionId}
          onChange={setRightRevisionId}
        />
        <RevisionButton
          disabled={
            comparing ||
            !leftRevisionId ||
            !rightRevisionId ||
            leftRevisionId === rightRevisionId
          }
          icon={
            comparing ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <GitCompareArrows size={14} />
            )
          }
          label={t('coreBusiness.revision.runCompare')}
          onClick={() => onCompare(leftRevisionId, rightRevisionId)}
        />
      </div>
      {!compareResult && comparing ? (
        <p className="inline-flex items-center gap-2 app-text-caption text-app-ink/50">
          <Loader2 size={14} className="animate-spin" />
          {t('coreBusiness.revision.comparing')}
        </p>
      ) : !compareResult ? (
        <p className="app-text-caption text-app-ink/50">
          {t('coreBusiness.revision.compareEmpty')}
        </p>
      ) : changedRows.length === 0 ? (
        <p className="app-text-caption text-app-ink/50">
          {t('coreBusiness.revision.noDiff')}
        </p>
      ) : (
        <div className="flex min-h-0 flex-1">
          <LegacyIssueRevisionCompareGrid
            compareResult={compareResult}
            leftTitle={revisionLabel(
              compareResult.left_revision ??
                revisionById.get(leftRevisionId) ?? {
                  revision_no: null,
                  status: 'draft',
                },
              t,
            )}
            rightTitle={revisionLabel(
              compareResult.right_revision ??
                revisionById.get(rightRevisionId) ?? {
                  revision_no: null,
                  status: 'draft',
                },
              t,
            )}
          />
        </div>
      )}
    </RevisionModal>
  );
}

function RevisionSelect({
  label,
  onChange,
  revisions,
  value,
}: {
  label: string;
  onChange: (value: string) => void;
  revisions: LegacyIssueRevisionView[];
  value: string;
}) {
  const { t } = useTranslation(['apps']);
  const revisionById = useMemo(
    () => new Map(revisions.map((revision) => [revision.id, revision])),
    [revisions],
  );
  return (
    <label className="inline-flex items-center gap-2 app-text-caption">
      <span className="text-app-ink/60">{label}</span>
      <select
        className="app-field-input-sm min-w-40"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        {revisions.map((revision) => (
          <option key={revision.id} value={revision.id}>
            {revisionOptionLabel(revision, revisionById, t)}
          </option>
        ))}
      </select>
    </label>
  );
}

export function isVisibleLegacyIssueRevision(
  revision: Pick<LegacyIssueRevisionView, 'status'>,
): boolean {
  return revision.status !== 'canceled';
}

function RevisionButton({
  danger = false,
  disabled,
  icon,
  label,
  onClick,
}: {
  danger?: boolean;
  disabled?: boolean;
  icon: ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      className={cn(
        'inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md border bg-app-bg px-2.5 app-text-caption font-medium hover:bg-app-surface-hover disabled:cursor-not-allowed disabled:opacity-50',
        danger
          ? 'border-app-danger/40 text-app-danger hover:bg-app-danger/10'
          : 'border-app-border text-app-ink/75',
      )}
      disabled={disabled}
      type="button"
      onClick={onClick}
    >
      {icon}
      <span>{label}</span>
    </button>
  );
}

function RevisionModal({
  children,
  contentClassName,
  onClose,
  title,
  wide = false,
}: {
  children: ReactNode;
  contentClassName?: string;
  onClose: () => void;
  title: string;
  wide?: boolean;
}) {
  const { t } = useTranslation(['apps']);
  return (
    <div
      aria-modal="true"
      className={cn(
        'fixed inset-0 z-[130] flex items-center justify-center bg-black/30',
        wide ? 'p-0' : 'px-4 py-6',
      )}
      role="dialog"
    >
      <div
        className={cn(
          'flex max-h-full w-full flex-col bg-app-bg shadow-xl',
          wide
            ? 'h-full max-w-none'
            : 'max-w-5xl rounded-md border border-app-border',
        )}
      >
        <header className="flex items-center justify-between gap-3 border-b border-app-border px-4 py-3">
          <h2 className="app-text-body-sm font-semibold">{title}</h2>
          <button
            aria-label={t('coreBusiness.grid.close')}
            className="flex size-8 items-center justify-center rounded-md border border-app-border hover:bg-app-surface-hover"
            type="button"
            onClick={onClose}
          >
            <X size={15} />
          </button>
        </header>
        <div className={cn('min-h-0 overflow-auto p-4', contentClassName)}>
          {children}
        </div>
      </div>
    </div>
  );
}

function revisionLabel(
  revision: Pick<LegacyIssueRevisionView, 'revision_no' | 'status'>,
  t: (key: string, options?: Record<string, unknown>) => string,
): string {
  if (revision.status === 'draft') {
    return t('coreBusiness.revision.draft');
  }
  return t('coreBusiness.revision.publishedRevision', {
    revision: revision.revision_no ?? '-',
  });
}

function revisionOptionLabel(
  revision: LegacyIssueRevisionView,
  revisionById: ReadonlyMap<string, LegacyIssueRevisionView>,
  t: (key: string, options?: Record<string, unknown>) => string,
): string {
  if (revision.status !== 'draft') return revisionLabel(revision, t);
  const baseRevisionNo = revision.base_revision_id
    ? revisionById.get(revision.base_revision_id)?.revision_no
    : null;
  if (baseRevisionNo === null || baseRevisionNo === undefined) {
    return revisionLabel(revision, t);
  }
  return t('coreBusiness.revision.draftFromRevision', {
    revision: baseRevisionNo,
  });
}

function isPublishEvent(event: LegacyIssueRevisionEventView): boolean {
  return event.action === 'publish' || event.action === 'initial_publish';
}

function revisionEventLabel(
  event: LegacyIssueRevisionEventView,
  revisionById: Map<string, LegacyIssueRevisionView>,
  t: (key: string, options?: Record<string, unknown>) => string,
): string {
  const revisionNo =
    detailNumber(event.details, 'revision_no') ??
    revisionById.get(event.revision_id)?.revision_no ??
    null;
  if (revisionNo) {
    return t('coreBusiness.revision.publishedRevision', {
      revision: revisionNo,
    });
  }
  const baseRevisionNo = detailNumber(event.details, 'base_revision_no');
  if (baseRevisionNo) {
    return t('coreBusiness.revision.historyBaseRevision', {
      revision: baseRevisionNo,
    });
  }
  return t('coreBusiness.revision.draft');
}

function revisionEventInfo(
  event: LegacyIssueRevisionEventView,
  revisionById: Map<string, LegacyIssueRevisionView>,
  t: (key: string, options?: Record<string, unknown>) => string,
): string {
  const revisionNo =
    detailNumber(event.details, 'revision_no') ??
    revisionById.get(event.revision_id)?.revision_no ??
    null;
  if (event.action === 'publish') {
    return t('coreBusiness.revision.historyInfoPublished', {
      revision: revisionNo ?? '-',
    });
  }
  if (event.action === 'initial_publish') {
    return t('coreBusiness.revision.historyInfoInitialPublished', {
      revision: revisionNo ?? '-',
    });
  }
  const baseRevisionNo = detailNumber(event.details, 'base_revision_no');
  if (event.action === 'draft_create' && baseRevisionNo) {
    return t('coreBusiness.revision.historyInfoDraftFrom', {
      revision: baseRevisionNo,
    });
  }
  if (event.action === 'draft_copy') {
    return t('coreBusiness.revision.historyInfoDraftCopy');
  }
  if (event.action === 'cancel') {
    return t('coreBusiness.revision.historyInfoCanceled');
  }
  if (event.action === 'force_cancel') {
    return t('coreBusiness.revision.historyInfoForceCanceled', {
      name:
        detailString(event.details, 'previous_locked_by_name') ??
        t('coreBusiness.revision.unknownDraftEditor'),
    });
  }
  return t('coreBusiness.grid.emptyValue');
}

function detailString(
  details: Record<string, unknown> | null,
  key: string,
): string | null {
  const value = details?.[key];
  return typeof value === 'string' && value.trim() ? value : null;
}

function detailNumber(
  details: Record<string, unknown> | null,
  key: string,
): number | null {
  const value = details?.[key];
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string') {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'short',
    timeStyle: 'short',
  }).format(date);
}
