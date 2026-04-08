import { useState, useRef, useEffect } from 'react';
import { X, ChevronDown, Trash2, Archive } from 'lucide-react';
import { bulkUpdateIssues, type PmsProjectMember, type PmsLabel, type PmsProjectStatus } from '@/src/domains/pms/pms-api';
import { useAuth } from '@/src/domains/auth/auth-provider';

const DEFAULT_STATUS_OPTIONS = [
  { value: 'backlog', label: 'Backlog' },
  { value: 'todo', label: 'Todo' },
  { value: 'in_progress', label: 'In Progress' },
  { value: 'done', label: 'Done' },
  { value: 'canceled', label: 'Canceled' },
] as const;

const PRIORITY_OPTIONS = [
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Medium' },
  { value: 'high', label: 'High' },
  { value: 'critical', label: 'Critical' },
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
        onClick={() => setOpen(o => !o)}
        className="app-text-control-sm flex items-center gap-1 rounded px-3 py-1.5 text-white/80 transition-colors hover:bg-white/10 hover:text-white"
      >
        {label}
        <ChevronDown size={12} />
      </button>
      {open && (
        <div className="absolute bottom-full left-0 mb-1 z-40 min-w-[160px] bg-clickup-bg border border-clickup-border rounded-lg shadow-xl py-1 max-h-48 overflow-y-auto custom-scrollbar">
          {children(() => setOpen(false))}
        </div>
      )}
    </div>
  );
}

export const BulkActionBar = ({
  projectId,
  selectedIds,
  totalCount,
  onSelectAll,
  onDeselectAll,
  onDone,
  members,
  labels,
  projectStatuses,
}: {
  projectId: string;
  selectedIds: Set<string>;
  totalCount: number;
  onSelectAll: () => void;
  onDeselectAll: () => void;
  onDone: () => void;
  members: PmsProjectMember[];
  labels: PmsLabel[];
  projectStatuses?: PmsProjectStatus[];
}) => {
  const statusOptions = projectStatuses && projectStatuses.length > 0
    ? projectStatuses.map(s => ({ value: s.slug, label: s.name }))
    : [...DEFAULT_STATUS_OPTIONS];
  const { token } = useAuth();
  const [loading, setLoading] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const ids = Array.from(selectedIds);

  const exec = async (payload: Record<string, unknown>) => {
    if (!token || ids.length === 0) return;
    setLoading(true);
    try {
      await bulkUpdateIssues(token, projectId, { issue_ids: ids, ...payload });
      onDone();
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-1 px-4 py-2 bg-gray-900 border border-gray-700 rounded-xl shadow-2xl shadow-black/40">
      <span className="app-text-control-sm mr-2 whitespace-nowrap font-medium text-white">
        {selectedIds.size} selected
      </span>

      <div className="h-4 w-px bg-gray-700 mx-1" />

      <button onClick={onSelectAll} className="app-text-caption whitespace-nowrap px-2 py-1 text-white/60 transition-colors hover:text-white">
        All ({totalCount})
      </button>
      <button onClick={onDeselectAll} className="app-text-caption whitespace-nowrap px-2 py-1 text-white/60 transition-colors hover:text-white">
        None
      </button>

      <div className="h-4 w-px bg-gray-700 mx-1" />

      {/* Status */}
      <ActionDropdown label="Status">
        {(close) => (
          <>
            {statusOptions.map(opt => (
              <button
                key={opt.value}
                onClick={() => { exec({ status: opt.value }); close(); }}
                className="app-text-body-sm w-full px-3 py-1.5 text-left text-clickup-text hover:bg-clickup-hover"
              >
                {opt.label}
              </button>
            ))}
          </>
        )}
      </ActionDropdown>

      {/* Priority */}
      <ActionDropdown label="Priority">
        {(close) => (
          <>
            {PRIORITY_OPTIONS.map(opt => (
              <button
                key={opt.value}
                onClick={() => { exec({ priority: opt.value }); close(); }}
                className="app-text-body-sm w-full px-3 py-1.5 text-left text-clickup-text hover:bg-clickup-hover"
              >
                {opt.label}
              </button>
            ))}
          </>
        )}
      </ActionDropdown>

      {/* Assignee */}
      <ActionDropdown label="Assignee">
        {(close) => (
          <>
            <button
              onClick={() => { exec({ assignee_id: null }); close(); }}
              className="app-text-body-sm w-full px-3 py-1.5 text-left text-clickup-text/50 hover:bg-clickup-hover"
            >
              Unassign
            </button>
            {members.map(m => (
              <button
                key={m.user_id}
                onClick={() => { exec({ assignee_id: m.user_id }); close(); }}
                className="app-text-body-sm w-full px-3 py-1.5 text-left text-clickup-text hover:bg-clickup-hover"
              >
                {m.full_name}
              </button>
            ))}
          </>
        )}
      </ActionDropdown>

      {/* Labels */}
      {labels.length > 0 && (
        <ActionDropdown label="Labels">
          {(close) => (
            <>
              <div className="app-text-overline px-3 py-1 text-clickup-text/40">Add</div>
              {labels.map(l => (
                <button
                  key={`add-${l.id}`}
                  onClick={() => { exec({ add_label_ids: [l.id] }); close(); }}
                  className="app-text-body-sm flex w-full items-center gap-2 px-3 py-1.5 text-left text-clickup-text hover:bg-clickup-hover"
                >
                  <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: l.color }} />
                  {l.name}
                </button>
              ))}
              <hr className="border-clickup-border my-1" />
              <div className="app-text-overline px-3 py-1 text-clickup-text/40">Remove</div>
              {labels.map(l => (
                <button
                  key={`rm-${l.id}`}
                  onClick={() => { exec({ remove_label_ids: [l.id] }); close(); }}
                  className="app-text-body-sm flex w-full items-center gap-2 px-3 py-1.5 text-left text-red-400/70 hover:bg-clickup-hover"
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
        onClick={() => exec({ archived: true })}
        disabled={loading}
        className="app-text-control-sm flex items-center gap-1 rounded px-3 py-1.5 text-white/60 transition-colors hover:bg-white/10 hover:text-yellow-400"
      >
        <Archive size={13} />
        Archive
      </button>
      <button
        onClick={() => exec({ archived: false })}
        disabled={loading}
        className="app-text-control-sm flex items-center gap-1 rounded px-3 py-1.5 text-white/60 transition-colors hover:bg-white/10 hover:text-emerald-400"
      >
        <Archive size={13} />
        Restore
      </button>

      {/* Delete */}
      {confirmDelete ? (
        <div className="flex items-center gap-1">
          <button
            onClick={() => { exec({ delete: true }); setConfirmDelete(false); }}
            disabled={loading}
            className="app-text-control-sm rounded px-3 py-1.5 font-medium text-red-400 transition-colors hover:bg-red-500/20"
          >
            Confirm
          </button>
          <button
            onClick={() => setConfirmDelete(false)}
            className="app-text-control-sm px-2 py-1.5 text-white/40 transition-colors hover:text-white"
          >
            Cancel
          </button>
        </div>
      ) : (
        <button
          onClick={() => setConfirmDelete(true)}
          disabled={loading}
          className="app-text-control-sm flex items-center gap-1 rounded px-3 py-1.5 text-white/60 transition-colors hover:bg-white/10 hover:text-red-400"
        >
          <Trash2 size={13} />
          Delete
        </button>
      )}

      <div className="h-4 w-px bg-gray-700 mx-1" />

      {/* Close */}
      <button onClick={onDeselectAll} className="p-1 text-white/40 hover:text-white transition-colors">
        <X size={14} />
      </button>
    </div>
  );
};
