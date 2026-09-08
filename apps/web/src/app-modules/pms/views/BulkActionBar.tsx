import { useAuth } from '@/src/platform/auth/auth-provider';
import { UserOptionRow } from '@/src/platform/users/UserSearchMultiSelect';
import { selectUserOptionsForPicker } from '@/src/platform/users/user-option-picker-model';
import { Archive, ChevronDown, Trash2, X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  bulkUpdateTasks,
  type PmsLabel,
  type PmsTaskListMember,
  type PmsTaskListStatus,
} from '../api/pms-api';
import { StatusIconGlyph } from './StatusIcon';
import {
  buildBulkActionPayload,
  buildBulkLabelActions,
  buildBulkStatusOptions,
  buildBulkUpdateRequest,
  selectedTaskIdsToArray,
  type BulkUpdateActionPayload,
} from './bulk-action-bar-model';

const PRIORITY_OPTIONS = [
  { value: 'low', labelKey: 'pms.priorityLow' },
  { value: 'medium', labelKey: 'pms.priorityMedium' },
  { value: 'high', labelKey: 'pms.priorityHigh' },
  { value: 'critical', labelKey: 'pms.priorityCritical' },
] as const;

type MemberUserOption = PmsTaskListMember & { id: string };

function memberUserOption(member: PmsTaskListMember): MemberUserOption {
  return { ...member, id: member.user_id };
}

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
      if (ref.current && !ref.current.contains(e.target as Node))
        setOpen(false);
    }
    if (open) document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
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
  const statusOptions = buildBulkStatusOptions({
    taskListStatuses,
    translate: t,
  });
  const labelActions = buildBulkLabelActions(labels);
  const { token, user } = useAuth();
  const [loading, setLoading] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [assigneeQuery, setAssigneeQuery] = useState('');

  const ids = selectedTaskIdsToArray(selectedIds);
  const assigneeOptions = selectUserOptionsForPicker({
    users: members.map(memberUserOption),
    query: assigneeQuery,
    currentUserId: user?.id,
    limit: 12,
  });

  const exec = async (payload: BulkUpdateActionPayload) => {
    if (!token || ids.length === 0) return;
    setLoading(true);
    try {
      await bulkUpdateTasks(
        token,
        taskListId,
        buildBulkUpdateRequest(ids, payload),
      );
      onDone();
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-1 px-4 py-2 bg-app-bg-strong border border-app-border-strong rounded-xl shadow-2xl shadow-black/40">
      <span className="app-text-control-sm mr-2 whitespace-nowrap font-medium text-white">
        {t('pms.bulk.selectedCount', { count: selectedIds.size })}
      </span>

      <div className="h-4 w-px bg-app-border-strong mx-1" />

      <button
        type="button"
        onClick={onSelectAll}
        className="app-text-caption whitespace-nowrap px-2 py-1 text-white/60 transition-colors hover:text-white"
      >
        {t('pms.bulk.selectAll', { count: totalCount })}
      </button>
      <button
        type="button"
        onClick={onDeselectAll}
        className="app-text-caption whitespace-nowrap px-2 py-1 text-white/60 transition-colors hover:text-white"
      >
        {t('pms.bulk.selectNone')}
      </button>

      <div className="h-4 w-px bg-app-border-strong mx-1" />

      {/* Status */}
      <ActionDropdown label={t('pms.filter.statusLabel')}>
        {(close) => (
          <>
            {statusOptions.map((opt) => (
              <button
                key={opt.value}
                type="button"
                onClick={() => {
                  exec(
                    buildBulkActionPayload({
                      type: 'status',
                      status: opt.value,
                    }),
                  );
                  close();
                }}
                className="app-text-control-sm flex w-full items-center gap-2 px-3 py-1.5 text-left text-app-ink hover:bg-app-surface-hover"
              >
                <StatusIconGlyph
                  label={opt.label}
                  status={opt.value}
                  taskListStatuses={taskListStatuses}
                />
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
            {PRIORITY_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                type="button"
                onClick={() => {
                  exec(
                    buildBulkActionPayload({
                      type: 'priority',
                      priority: opt.value,
                    }),
                  );
                  close();
                }}
                className="app-text-control-sm w-full px-3 py-1.5 text-left text-app-ink hover:bg-app-surface-hover"
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
            <div className="px-2 py-1">
              <input
                aria-label={t('pms.searchUser')}
                className="app-field-input-sm bg-app-surface-sidebar py-1.5"
                onChange={(event) => setAssigneeQuery(event.target.value)}
                placeholder={t('pms.searchUser')}
                value={assigneeQuery}
              />
            </div>
            <button
              type="button"
              onClick={() => {
                exec(
                  buildBulkActionPayload({
                    type: 'assignee',
                    assigneeId: null,
                  }),
                );
                close();
              }}
              className="app-text-control-sm w-full px-3 py-1.5 text-left text-app-ink/50 hover:bg-app-surface-hover"
            >
              {t('pms.bulk.unassign')}
            </button>
            {assigneeOptions.map((member) => (
              <UserOptionRow
                key={member.user_id}
                currentUserId={user?.id}
                currentUserLabel={t('pms.taskDetail.me')}
                density="compact"
                onClick={() => {
                  exec(
                    buildBulkActionPayload({
                      type: 'assignee',
                      assigneeId: member.user_id,
                    }),
                  );
                  close();
                }}
                user={member}
              />
            ))}
            {assigneeOptions.length === 0 ? (
              <p className="app-text-caption px-3 py-2 text-app-ink/40">
                {t('pms.noMatchingUsers')}
              </p>
            ) : null}
          </>
        )}
      </ActionDropdown>

      {/* Labels */}
      {labels.length > 0 && (
        <ActionDropdown label={t('pms.bulk.labelsLabel')}>
          {(close) => (
            <>
              <div className="app-text-overline px-3 py-1 text-app-ink/40">
                {t('common:actions.add')}
              </div>
              {labelActions.add.map((action) => (
                <button
                  key={action.key}
                  type="button"
                  onClick={() => {
                    exec(action.payload);
                    close();
                  }}
                  className="app-text-control-sm flex w-full items-center gap-2 px-3 py-1.5 text-left text-app-ink hover:bg-app-surface-hover"
                >
                  <span
                    className="size-2 shrink-0 rounded-full"
                    style={{ backgroundColor: action.label.color }}
                  />
                  {action.label.name}
                </button>
              ))}
              <hr className="border-app-border my-1" />
              <div className="app-text-overline px-3 py-1 text-app-ink/40">
                {t('pms.bulk.remove')}
              </div>
              {labelActions.remove.map((action) => (
                <button
                  key={action.key}
                  type="button"
                  onClick={() => {
                    exec(action.payload);
                    close();
                  }}
                  className="app-text-control-sm flex w-full items-center gap-2 px-3 py-1.5 text-left text-app-danger-text/70 hover:bg-app-surface-hover"
                >
                  <span
                    className="size-2 shrink-0 rounded-full"
                    style={{ backgroundColor: action.label.color }}
                  />
                  {action.label.name}
                </button>
              ))}
            </>
          )}
        </ActionDropdown>
      )}

      <div className="h-4 w-px bg-app-border-strong mx-1" />

      {/* Archive */}
      <button
        type="button"
        onClick={() => exec(buildBulkActionPayload({ type: 'archive' }))}
        disabled={loading}
        className="app-text-control-sm flex items-center gap-1 rounded px-3 py-1.5 text-white/60 transition-colors hover:bg-white/10 hover:text-yellow-400"
      >
        <Archive size={13} />
        {t('common:actions.archive')}
      </button>
      <button
        type="button"
        onClick={() => exec(buildBulkActionPayload({ type: 'restore' }))}
        disabled={loading}
        className="app-text-control-sm flex items-center gap-1 rounded px-3 py-1.5 text-white/60 transition-colors hover:bg-white/10 hover:text-app-success-text"
      >
        <Archive size={13} />
        {t('pms.bulk.restore')}
      </button>

      {/* Delete */}
      {confirmDelete ? (
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => {
              exec(buildBulkActionPayload({ type: 'delete' }));
              setConfirmDelete(false);
            }}
            disabled={loading}
            className="app-text-control-sm rounded px-3 py-1.5 font-medium text-app-danger-text transition-colors hover:bg-app-danger/20"
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
          className="app-text-control-sm flex items-center gap-1 rounded px-3 py-1.5 text-white/60 transition-colors hover:bg-white/10 hover:text-app-danger-text"
        >
          <Trash2 size={13} />
          {t('common:actions.delete')}
        </button>
      )}

      <div className="h-4 w-px bg-app-border-strong mx-1" />

      {/* Close */}
      <button
        type="button"
        onClick={onDeselectAll}
        className="p-1 text-white/40 hover:text-white transition-colors"
        aria-label={t('pms.bulk.closeSelection')}
      >
        <X size={14} />
      </button>
    </div>
  );
};
