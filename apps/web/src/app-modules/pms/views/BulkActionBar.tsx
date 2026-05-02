import { useState, useRef, useEffect } from 'react';
import { X, ChevronDown, Trash2, Archive } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { bulkUpdateIssues, type PmsTaskListMember, type PmsLabel, type PmsTaskListStatus } from '../api/pms-api';
import { useAuth } from '@/src/platform/auth/auth-provider';

const DEFAULT_STATUS_OPTIONS = [
  { value: 'backlog', labelKey: 'pms.filter.status.backlog' },
  { value: 'todo', labelKey: 'pms.filter.status.todo' },
  { value: 'in_progress', labelKey: 'pms.filter.status.inProgress' },
  { value: 'done', labelKey: 'pms.filter.status.done' },
  { value: 'canceled', labelKey: 'pms.filter.status.canceled' },
] as const;

const PRIORITY_OPTIONS = [
  { value: 'low', labelKey: 'pms.priorityLow' },
  { value: 'medium', labelKey: 'pms.priorityMedium' },
  { value: 'high', labelKey: 'pms.priorityHigh' },
  { value: 'critical', labelKey: 'pms.priorityCritical' },
] as const;

function ActionDropdown({
  label,
  children,
}: {
  label: string;
  children: (close: () => void) => React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    if (open) document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="app-text-control-sm flex items-center gap-1 rounded px-3 py-1.5 text-white/80 transition-colors hover:bg-white/10 hover:text-white"
      >
        {label}
        <ChevronDown size={12} />
      </button>
      {open && (
        <div className="absolute bottom-full left-0 mb-1 z-40 min-w-[160px] bg-app-bg border border-app-border rounded-lg shadow-xl py-1 max-h-48 overflow-y-auto custom-scrollbar">
          {children(() => setOpen(false))}
        </div>
      )}
    </div>
  );
}

export const BulkActionBar = ({
  taskListId,
  selectedIds,
  totalCount,
  onSelectAll,
  onDeselectAll,
  onDone,
  members,
  labels,
  taskListStatuses,
}: {
  taskListId: string;
  selectedIds: Set<string>;
  totalCount: number;
  onSelectAll: () => void;
  onDeselectAll: () => void;
  onDone: () => void;
  members: PmsTaskListMember[];
  labels: PmsLabel[];
  taskListStatuses?: PmsTaskListStatus[];
}) => {
  const { t } = useTranslation('apps');
  const statusOptions = taskListStatuses && taskListStatuses.length > 0
    ? taskListStatuses.map(s => ({ value: s.slug, label: s.name }))
    : DEFAULT_STATUS_OPTIONS.map((option) => ({
        value: option.value,
        label: t(option.labelKey),
      }));
  const { token } = useAuth();
  const [loading, setLoading] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const ids = Array.from(selectedIds);

  const exec = async (payload: Record<string, unknown>) => {
    if (!token || ids.length === 0) return;
    setLoading(true);
    try {
      await bulkUpdateIssues(token, taskListId, { issue_ids: ids, ...payload });
      onDone();
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-1 px-4 py-2 bg-gray-900 border border-gray-700 rounded-xl shadow-2xl shadow-black/40">
      <span className="app-text-control-sm mr-2 whitespace-nowrap font-medium text-white">
        {t('pms.bulk.selectedCount', { count: selectedIds.size })}
      </span>

      <div className="h-4 w-px bg-gray-700 mx-1" />

      <button type="button" onClick={onSelectAll} className="app-text-caption whitespace-nowrap px-2 py-1 text-white/60 transition-colors hover:text-white">
        {t('pms.bulk.selectAll', { count: totalCount })}
      </button>
      <button type="button" onClick={onDeselectAll} className="app-text-caption whitespace-nowrap px-2 py-1 text-white/60 transition-colors hover:text-white">
        {t('pms.bulk.selectNone')}
      </button>

      <div className="h-4 w-px bg-gray-700 mx-1" />

      {/* Status */}
      <ActionDropdown label={t('pms.filter.statusLabel')}>
        {(close) => (
          <>
            {statusOptions.map(opt => (
              <button
                key={opt.value}
                type="button"
                onClick={() => { exec({ status: opt.value }); close(); }}
                className="app-text-body-sm w-full px-3 py-1.5 text-left text-app-ink hover:bg-app-surface-hover"
              >
                {opt.label}
              </button>
            ))}
          </>
        )}
      </ActionDropdown>

      {/* Priority */}
      <ActionDropdown label={t('pms.filter.priorityLabel')}>
        {(close) => (
          <>
            {PRIORITY_OPTIONS.map(opt => (
              <button
                key={opt.value}
                type="button"
                onClick={() => { exec({ priority: opt.value }); close(); }}
                className="app-text-body-sm w-full px-3 py-1.5 text-left text-app-ink hover:bg-app-surface-hover"
              >
                {t(opt.labelKey)}
              </button>
            ))}
          </>
        )}
      </ActionDropdown>

      {/* Assignee */}
      <ActionDropdown label={t('pms.filter.assigneeLabel')}>
        {(close) => (
          <>
            <button
              type="button"
              onClick={() => { exec({ assignee_id: null }); close(); }}
              className="app-text-body-sm w-full px-3 py-1.5 text-left text-app-ink/50 hover:bg-app-surface-hover"
            >
              {t('pms.bulk.unassign')}
            </button>
            {members.map(m => (
              <button
                key={m.user_id}
                type="button"
                onClick={() => { exec({ assignee_id: m.user_id }); close(); }}
                className="app-text-body-sm w-full px-3 py-1.5 text-left text-app-ink hover:bg-app-surface-hover"
              >
                {m.full_name}
              </button>
            ))}
          </>
        )}
      </ActionDropdown>

      {/* Labels */}
      {labels.length > 0 && (
        <ActionDropdown label={t('pms.bulk.labelsLabel')}>
          {(close) => (
            <>
              <div className="app-text-overline px-3 py-1 text-app-ink/40">{t('common:actions.add')}</div>
              {labels.map(l => (
                <button
                  key={`add-${l.id}`}
                  type="button"
                  onClick={() => { exec({ add_label_ids: [l.id] }); close(); }}
                  className="app-text-body-sm flex w-full items-center gap-2 px-3 py-1.5 text-left text-app-ink hover:bg-app-surface-hover"
                >
                  <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: l.color }} />
                  {l.name}
                </button>
              ))}
              <hr className="border-app-border my-1" />
              <div className="app-text-overline px-3 py-1 text-app-ink/40">{t('pms.bulk.remove')}</div>
              {labels.map(l => (
                <button
                  key={`rm-${l.id}`}
                  type="button"
                  onClick={() => { exec({ remove_label_ids: [l.id] }); close(); }}
                  className="app-text-body-sm flex w-full items-center gap-2 px-3 py-1.5 text-left text-red-400/70 hover:bg-app-surface-hover"
                >
                  <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: l.color }} />
                  {l.name}
                </button>
              ))}
            </>
          )}
        </ActionDropdown>
      )}

      <div className="h-4 w-px bg-gray-700 mx-1" />

      {/* Archive */}
      <button
        type="button"
        onClick={() => exec({ archived: true })}
        disabled={loading}
        className="app-text-control-sm flex items-center gap-1 rounded px-3 py-1.5 text-white/60 transition-colors hover:bg-white/10 hover:text-yellow-400"
      >
        <Archive size={13} />
        {t('common:actions.archive')}
      </button>
      <button
        type="button"
        onClick={() => exec({ archived: false })}
        disabled={loading}
        className="app-text-control-sm flex items-center gap-1 rounded px-3 py-1.5 text-white/60 transition-colors hover:bg-white/10 hover:text-emerald-400"
      >
        <Archive size={13} />
        {t('pms.bulk.restore')}
      </button>

      {/* Delete */}
      {confirmDelete ? (
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => { exec({ delete: true }); setConfirmDelete(false); }}
            disabled={loading}
            className="app-text-control-sm rounded px-3 py-1.5 font-medium text-red-400 transition-colors hover:bg-red-500/20"
          >
            {t('pms.bulk.confirm')}
          </button>
          <button
            type="button"
            onClick={() => setConfirmDelete(false)}
            className="app-text-control-sm px-2 py-1.5 text-white/40 transition-colors hover:text-white"
          >
            {t('common:actions.cancel')}
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setConfirmDelete(true)}
          disabled={loading}
          className="app-text-control-sm flex items-center gap-1 rounded px-3 py-1.5 text-white/60 transition-colors hover:bg-white/10 hover:text-red-400"
        >
          <Trash2 size={13} />
          {t('common:actions.delete')}
        </button>
      )}

      <div className="h-4 w-px bg-gray-700 mx-1" />

      {/* Close */}
      <button type="button" onClick={onDeselectAll} className="p-1 text-white/40 hover:text-white transition-colors" aria-label={t('pms.bulk.closeSelection')}>
        <X size={14} />
      </button>
    </div>
  );
};
