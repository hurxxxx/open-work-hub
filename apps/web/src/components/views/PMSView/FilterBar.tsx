import { useState, useRef, useEffect } from 'react';
import { X, Filter, ChevronDown, Save, BookmarkCheck } from 'lucide-react';
import type { IssueFilterParams, PmsProjectMember, PmsMilestone, PmsLabel } from '@/src/domains/pms/pms-api';

const STATUS_OPTIONS = [
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

interface SavedFilter {
  name: string;
  params: IssueFilterParams;
}

function getStorageKey(projectId: string) {
  return `pms_saved_filters_${projectId}`;
}

function loadSavedFilters(projectId: string): SavedFilter[] {
  try {
    const raw = localStorage.getItem(getStorageKey(projectId));
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveSavedFilters(projectId: string, filters: SavedFilter[]) {
  localStorage.setItem(getStorageKey(projectId), JSON.stringify(filters));
}

function isFilterActive(params: IssueFilterParams): boolean {
  return !!(
    (params.status && params.status.length > 0) ||
    params.priority ||
    params.assignee_id ||
    params.label_id ||
    params.milestone_id ||
    params.due_date_from ||
    params.due_date_to
  );
}

/** Reusable dropdown wrapper. */
function Dropdown({
  label,
  active,
  children,
}: {
  label: string;
  active: boolean;
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
        className={`flex items-center gap-1 px-2.5 py-1 text-[11px] rounded-md border transition-colors ${
          active
            ? 'border-clickup-purple text-clickup-purple bg-clickup-purple/10'
            : 'border-clickup-border text-clickup-text/60 hover:border-clickup-text/30 hover:text-clickup-text'
        }`}
      >
        {label}
        <ChevronDown size={12} />
      </button>
      {open && (
        <div className="absolute top-full left-0 mt-1 z-30 min-w-[180px] bg-clickup-bg border border-clickup-border rounded-lg shadow-xl py-1 max-h-60 overflow-y-auto custom-scrollbar">
          {children(() => setOpen(false))}
        </div>
      )}
    </div>
  );
}

export const FilterBar = ({
  projectId,
  filterParams,
  setFilterParams,
  members,
  milestones,
  labels,
}: {
  projectId: string;
  filterParams: IssueFilterParams;
  setFilterParams: (params: IssueFilterParams) => void;
  members: PmsProjectMember[];
  milestones: PmsMilestone[];
  labels: PmsLabel[];
}) => {
  const [savedFilters, setSavedFilters] = useState<SavedFilter[]>(() => loadSavedFilters(projectId));
  const [saveDialogOpen, setSaveDialogOpen] = useState(false);
  const [filterName, setFilterName] = useState('');

  useEffect(() => {
    setSavedFilters(loadSavedFilters(projectId));
  }, [projectId]);

  const active = isFilterActive(filterParams);

  const clearAll = () => {
    setFilterParams({ q: filterParams.q });
  };

  const handleSave = () => {
    if (!filterName.trim()) return;
    const next = [...savedFilters, { name: filterName.trim(), params: { ...filterParams, q: undefined } }];
    saveSavedFilters(projectId, next);
    setSavedFilters(next);
    setFilterName('');
    setSaveDialogOpen(false);
  };

  const handleDeleteSaved = (idx: number) => {
    const next = savedFilters.filter((_, i) => i !== idx);
    saveSavedFilters(projectId, next);
    setSavedFilters(next);
  };

  const handleLoadSaved = (saved: SavedFilter) => {
    setFilterParams({ ...saved.params, q: filterParams.q });
  };

  // Active filter pills
  const pills: { label: string; clear: () => void }[] = [];
  if (filterParams.status && filterParams.status.length > 0) {
    const statusLabels = filterParams.status.map(s => STATUS_OPTIONS.find(o => o.value === s)?.label ?? s).join(', ');
    pills.push({ label: `Status: ${statusLabels}`, clear: () => setFilterParams({ ...filterParams, status: undefined }) });
  }
  if (filterParams.priority) {
    const pl = PRIORITY_OPTIONS.find(o => o.value === filterParams.priority)?.label ?? filterParams.priority;
    pills.push({ label: `Priority: ${pl}`, clear: () => setFilterParams({ ...filterParams, priority: undefined }) });
  }
  if (filterParams.assignee_id) {
    const name = members.find(m => m.user_id === filterParams.assignee_id)?.full_name ?? 'Unknown';
    pills.push({ label: `Assignee: ${name}`, clear: () => setFilterParams({ ...filterParams, assignee_id: undefined }) });
  }
  if (filterParams.label_id) {
    const name = labels.find(l => l.id === filterParams.label_id)?.name ?? 'Unknown';
    pills.push({ label: `Label: ${name}`, clear: () => setFilterParams({ ...filterParams, label_id: undefined }) });
  }
  if (filterParams.milestone_id) {
    const name = milestones.find(m => m.id === filterParams.milestone_id)?.title ?? 'Unknown';
    pills.push({ label: `Milestone: ${name}`, clear: () => setFilterParams({ ...filterParams, milestone_id: undefined }) });
  }
  if (filterParams.due_date_from || filterParams.due_date_to) {
    const from = filterParams.due_date_from ?? '...';
    const to = filterParams.due_date_to ?? '...';
    pills.push({ label: `Due: ${from} ~ ${to}`, clear: () => setFilterParams({ ...filterParams, due_date_from: undefined, due_date_to: undefined }) });
  }

  return (
    <div className="flex items-center gap-2 flex-wrap px-8 py-2 border-b border-clickup-border bg-clickup-bg/50">
      <Filter size={13} className="text-clickup-text/40 shrink-0" />

      {/* Status (multi-select) */}
      <Dropdown label="Status" active={!!(filterParams.status && filterParams.status.length > 0)}>
        {() => (
          <>
            {STATUS_OPTIONS.map(opt => {
              const checked = filterParams.status?.includes(opt.value) ?? false;
              return (
                <label key={opt.value} className="flex items-center gap-2 px-3 py-1.5 hover:bg-clickup-hover cursor-pointer text-xs text-clickup-text">
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => {
                      const current = filterParams.status ?? [];
                      const next = checked ? current.filter(s => s !== opt.value) : [...current, opt.value];
                      setFilterParams({ ...filterParams, status: next.length > 0 ? next : undefined });
                    }}
                    className="accent-clickup-purple"
                  />
                  {opt.label}
                </label>
              );
            })}
          </>
        )}
      </Dropdown>

      {/* Priority */}
      <Dropdown label="Priority" active={!!filterParams.priority}>
        {(close) => (
          <>
            <button
              onClick={() => { setFilterParams({ ...filterParams, priority: undefined }); close(); }}
              className={`w-full text-left px-3 py-1.5 text-xs hover:bg-clickup-hover ${!filterParams.priority ? 'text-clickup-purple font-medium' : 'text-clickup-text'}`}
            >
              All
            </button>
            {PRIORITY_OPTIONS.map(opt => (
              <button
                key={opt.value}
                onClick={() => { setFilterParams({ ...filterParams, priority: opt.value }); close(); }}
                className={`w-full text-left px-3 py-1.5 text-xs hover:bg-clickup-hover ${filterParams.priority === opt.value ? 'text-clickup-purple font-medium' : 'text-clickup-text'}`}
              >
                {opt.label}
              </button>
            ))}
          </>
        )}
      </Dropdown>

      {/* Assignee */}
      <Dropdown label="Assignee" active={!!filterParams.assignee_id}>
        {(close) => (
          <>
            <button
              onClick={() => { setFilterParams({ ...filterParams, assignee_id: undefined }); close(); }}
              className={`w-full text-left px-3 py-1.5 text-xs hover:bg-clickup-hover ${!filterParams.assignee_id ? 'text-clickup-purple font-medium' : 'text-clickup-text'}`}
            >
              All
            </button>
            {members.map(m => (
              <button
                key={m.user_id}
                onClick={() => { setFilterParams({ ...filterParams, assignee_id: m.user_id }); close(); }}
                className={`w-full text-left px-3 py-1.5 text-xs hover:bg-clickup-hover ${filterParams.assignee_id === m.user_id ? 'text-clickup-purple font-medium' : 'text-clickup-text'}`}
              >
                {m.full_name}
              </button>
            ))}
          </>
        )}
      </Dropdown>

      {/* Label */}
      <Dropdown label="Label" active={!!filterParams.label_id}>
        {(close) => (
          <>
            <button
              onClick={() => { setFilterParams({ ...filterParams, label_id: undefined }); close(); }}
              className={`w-full text-left px-3 py-1.5 text-xs hover:bg-clickup-hover ${!filterParams.label_id ? 'text-clickup-purple font-medium' : 'text-clickup-text'}`}
            >
              All
            </button>
            {labels.map(l => (
              <button
                key={l.id}
                onClick={() => { setFilterParams({ ...filterParams, label_id: l.id }); close(); }}
                className={`w-full text-left px-3 py-1.5 text-xs hover:bg-clickup-hover flex items-center gap-2 ${filterParams.label_id === l.id ? 'text-clickup-purple font-medium' : 'text-clickup-text'}`}
              >
                <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: l.color }} />
                {l.name}
              </button>
            ))}
          </>
        )}
      </Dropdown>

      {/* Milestone */}
      {milestones.length > 0 && (
        <Dropdown label="Milestone" active={!!filterParams.milestone_id}>
          {(close) => (
            <>
              <button
                onClick={() => { setFilterParams({ ...filterParams, milestone_id: undefined }); close(); }}
                className={`w-full text-left px-3 py-1.5 text-xs hover:bg-clickup-hover ${!filterParams.milestone_id ? 'text-clickup-purple font-medium' : 'text-clickup-text'}`}
              >
                All
              </button>
              {milestones.map(m => (
                <button
                  key={m.id}
                  onClick={() => { setFilterParams({ ...filterParams, milestone_id: m.id }); close(); }}
                  className={`w-full text-left px-3 py-1.5 text-xs hover:bg-clickup-hover ${filterParams.milestone_id === m.id ? 'text-clickup-purple font-medium' : 'text-clickup-text'}`}
                >
                  {m.title}
                </button>
              ))}
            </>
          )}
        </Dropdown>
      )}

      {/* Due Date Range */}
      <Dropdown label="Due Date" active={!!(filterParams.due_date_from || filterParams.due_date_to)}>
        {() => (
          <div className="px-3 py-2 space-y-2">
            <label className="block text-[10px] text-clickup-text/50 uppercase font-bold">From</label>
            <input
              type="date"
              value={filterParams.due_date_from ?? ''}
              onChange={e => setFilterParams({ ...filterParams, due_date_from: e.target.value || undefined })}
              className="w-full bg-clickup-sidebar border border-clickup-border rounded px-2 py-1 text-xs text-clickup-text focus:outline-none focus:border-clickup-purple"
            />
            <label className="block text-[10px] text-clickup-text/50 uppercase font-bold">To</label>
            <input
              type="date"
              value={filterParams.due_date_to ?? ''}
              onChange={e => setFilterParams({ ...filterParams, due_date_to: e.target.value || undefined })}
              className="w-full bg-clickup-sidebar border border-clickup-border rounded px-2 py-1 text-xs text-clickup-text focus:outline-none focus:border-clickup-purple"
            />
          </div>
        )}
      </Dropdown>

      {/* Separator + actions */}
      {active && (
        <>
          <div className="h-4 w-px bg-clickup-border mx-1" />
          <button onClick={clearAll} className="text-[11px] text-clickup-text/50 hover:text-clickup-text transition-colors">
            Clear all
          </button>
          <button
            onClick={() => setSaveDialogOpen(true)}
            className="flex items-center gap-1 text-[11px] text-clickup-text/50 hover:text-clickup-purple transition-colors"
          >
            <Save size={11} />
            Save
          </button>
        </>
      )}

      {/* Saved filters */}
      {savedFilters.length > 0 && (
        <Dropdown label={`Saved (${savedFilters.length})`} active={false}>
          {(close) => (
            <>
              {savedFilters.map((sf, idx) => (
                <div key={idx} className="flex items-center justify-between px-3 py-1.5 hover:bg-clickup-hover group">
                  <button
                    onClick={() => { handleLoadSaved(sf); close(); }}
                    className="flex items-center gap-2 text-xs text-clickup-text flex-1 text-left"
                  >
                    <BookmarkCheck size={12} className="text-clickup-purple shrink-0" />
                    {sf.name}
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); handleDeleteSaved(idx); }}
                    className="opacity-0 group-hover:opacity-100 text-clickup-text/30 hover:text-red-400 p-0.5"
                  >
                    <X size={11} />
                  </button>
                </div>
              ))}
            </>
          )}
        </Dropdown>
      )}

      {/* Save dialog */}
      {saveDialogOpen && (
        <div className="flex items-center gap-2 ml-2">
          <input
            type="text"
            value={filterName}
            onChange={e => setFilterName(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') handleSave(); if (e.key === 'Escape') setSaveDialogOpen(false); }}
            placeholder="Filter name..."
            autoFocus
            className="bg-clickup-sidebar border border-clickup-border rounded px-2 py-1 text-xs text-clickup-text focus:outline-none focus:border-clickup-purple w-32"
          />
          <button onClick={handleSave} className="text-[11px] text-clickup-purple hover:text-clickup-purple/80 font-medium">
            Save
          </button>
          <button onClick={() => setSaveDialogOpen(false)} className="text-[11px] text-clickup-text/40 hover:text-clickup-text">
            Cancel
          </button>
        </div>
      )}

      {/* Active filter pills */}
      {pills.length > 0 && (
        <div className="flex items-center gap-1.5 ml-2 flex-wrap">
          {pills.map((pill, idx) => (
            <span key={idx} className="inline-flex items-center gap-1 px-2 py-0.5 bg-clickup-purple/10 text-clickup-purple text-[10px] rounded-full">
              {pill.label}
              <button onClick={pill.clear} className="hover:text-clickup-text transition-colors">
                <X size={10} />
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
};
