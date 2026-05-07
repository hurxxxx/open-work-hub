import { useEffect, useMemo, useState } from 'react';
import { Button, Dialog } from '@ai-do/ui';
import { Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@/src/platform/auth/auth-provider';
import { hasWorkspaceMembership } from '@/src/platform/auth/auth-api';
import { NoAccessNotice } from '@/src/components/common/NoAccessNotice';
import {
  listPmsTaskLists,
  listTaskListIssues,
  type PmsIssue,
  type PmsTaskList,
} from '@/src/app-modules/pms/public-api';

interface TaskPickerModalProps {
  isOpen: boolean;
  onClose: () => void;
  onPick: (issue: PmsIssue) => Promise<void> | void;
  excludeIssueIds?: string[];
  workspaceSlug: string;
}

export function TaskPickerModal({
  isOpen,
  onClose,
  onPick,
  excludeIssueIds = [],
  workspaceSlug,
}: TaskPickerModalProps) {
  const { t } = useTranslation('apps');
  const { token, user } = useAuth();
  const canAccessPms = hasWorkspaceMembership(user, workspaceSlug);
  const [taskLists, setTaskLists] = useState<PmsTaskList[]>([]);
  const [selectedTaskListId, setSelectedTaskListId] = useState<string | null>(null);
  const [issues, setIssues] = useState<PmsIssue[]>([]);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [submittingId, setSubmittingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen || !token || !canAccessPms) return;
    setQuery('');
    setError(null);
    setSubmittingId(null);
    listPmsTaskLists(token, undefined, workspaceSlug)
      .then((response) => {
        setTaskLists(response.items);
        if (response.items.length > 0) {
          setSelectedTaskListId(response.items[0].id);
        }
      })
      .catch((err: Error) => setError(err.message ?? t('meeting.taskPicker.listLoadFailed')));
  }, [isOpen, token, canAccessPms, workspaceSlug]);

  useEffect(() => {
    if (!isOpen || !token || !canAccessPms || !selectedTaskListId) {
      setIssues([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    listTaskListIssues(token, selectedTaskListId, { archived_state: 'active' }, workspaceSlug)
      .then((response) => {
        if (cancelled) return;
        setIssues(response.items);
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setError(err.message ?? t('meeting.taskPicker.issueLoadFailed'));
        setIssues([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [isOpen, token, canAccessPms, selectedTaskListId, workspaceSlug]);

  const excludeSet = useMemo(() => new Set(excludeIssueIds), [excludeIssueIds]);

  const filteredIssues = useMemo(() => {
    const q = query.trim().toLowerCase();
    return issues
      .filter((issue) => !excludeSet.has(issue.id))
      .filter((issue) => {
        if (!q) return true;
        return issue.title.toLowerCase().includes(q);
      })
      .slice(0, 50);
  }, [issues, query, excludeSet]);

  async function handlePick(issue: PmsIssue) {
    setSubmittingId(issue.id);
    setError(null);
    try {
      await onPick(issue);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('meeting.taskPicker.attachFailed'));
    } finally {
      setSubmittingId(null);
    }
  }

  return (
    <Dialog
        closeLabel={t('common:actions.close')}
      open={isOpen}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title={t('meeting.taskPicker.title')}
      description={t('meeting.taskPicker.description')}
      maxWidth="max-w-xl"
      actions={
        <div className="flex w-full items-center justify-end">
          <Button variant="secondary" onClick={onClose}>{t('common:actions.close')}</Button>
        </div>
      }
    >
      <div className="space-y-4 text-app-ink">
        {!canAccessPms ? (
          <NoAccessNotice
            workspaceLabel={t('meeting.taskPicker.pmsWorkspace')}
            action={t('meeting.taskPicker.attachAction')}
          />
        ) : null}

        {canAccessPms && error ? (
          <div
            role="alert"
            className="app-text-body rounded-md border border-[var(--ui-color-danger)]/30 bg-[var(--ui-color-danger)]/10 px-3 py-2 text-[var(--ui-color-danger)]"
          >
            {error}
          </div>
        ) : null}

        {canAccessPms ? (
          <>
            <div className="space-y-1">
              <label className="app-text-control-sm text-app-ink/70">{t('meeting.taskPicker.list')}</label>
              <select
                value={selectedTaskListId ?? ''}
                onChange={(e) => setSelectedTaskListId(e.target.value || null)}
                className="app-text-body w-full rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink focus:border-app-accent focus:outline-none"
              >
                {taskLists.length === 0 ? <option value="">{t('meeting.taskPicker.noLists')}</option> : null}
                {taskLists.map((taskList) => (
                  <option key={taskList.id} value={taskList.id}>
                    {taskList.key} · {taskList.name}
                  </option>
                ))}
              </select>
            </div>

            <div className="space-y-1">
              <label className="app-text-control-sm text-app-ink/70">{t('common:actions.search')}</label>
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={t('meeting.taskPicker.searchPlaceholder')}
                className="app-text-body w-full rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink placeholder:text-app-ink/30 focus:border-app-accent focus:outline-none"
              />
            </div>

            <div className="max-h-72 overflow-y-auto rounded-md border border-app-border">
              {loading ? (
                <div className="flex h-24 items-center justify-center text-app-ink/40">
                  <Loader2 size={16} className="animate-spin" />
                </div>
              ) : filteredIssues.length === 0 ? (
                <div className="px-4 py-6 text-center app-text-caption text-app-ink/50">
                  {t('meeting.taskPicker.empty')}
                </div>
              ) : (
                <ul className="divide-y divide-app-border">
                  {filteredIssues.map((issue) => (
                    <li key={issue.id}>
                      <button
                        type="button"
                        onClick={() => handlePick(issue)}
                        disabled={submittingId !== null}
                        className="flex w-full items-center justify-between px-4 py-3 text-left transition-colors hover:bg-app-surface-hover disabled:opacity-50"
                      >
                        <div className="min-w-0">
                          <p className="app-text-body line-clamp-1 text-app-ink">
                            {issue.title}
                          </p>
                          <p className="app-text-caption text-app-ink/40">
                            {issue.reference} · {issue.status_label}
                          </p>
                        </div>
                        {submittingId === issue.id ? (
                          <Loader2 size={14} className="animate-spin text-app-ink/40" />
                        ) : null}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </>
        ) : null}
      </div>
    </Dialog>
  );
}
