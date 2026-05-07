import { useState, useRef, useEffect } from 'react';
import { X, Filter, ChevronDown, Save, BookmarkCheck, Search } from 'lucide-react';
import { DetailDrawer } from '@ai-do/ui';
import { useTranslation } from 'react-i18next';
import type { IssueFilterParams, PmsTaskListMember, PmsMilestone, PmsLabel, PmsTaskListStatus } from '../api/pms-api';
import {
  createDefaultIssueFilterParams,
  DEFAULT_ISSUE_ARCHIVED_STATE,
} from '../api/pms-filters';

const DEFAULT_statusOptions = [
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

const ARCHIVE_OPTIONS = [
  { value: 'active', labelKey: 'pms.filter.archive.active' },
  { value: 'archived', labelKey: 'pms.filter.archive.archived' },
  { value: 'all', labelKey: 'pms.filter.all' },
] as const;

const FILTER_TRIGGER_CLASS = 'app-text-body-sm flex items-center gap-1 rounded-md border px-3 py-2 transition-colors';
const FILTER_MENU_ITEM_CLASS = 'app-text-body-sm w-full px-3 py-2 text-left hover:bg-app-surface-hover';
const FILTER_CHECKBOX_ITEM_CLASS = 'app-text-body-sm flex cursor-pointer items-center gap-2 px-3 py-2 text-app-ink hover:bg-app-surface-hover';
const FILTER_FIELD_CLASS = 'app-text-body-sm w-full rounded border border-app-border bg-app-surface-sidebar px-2.5 py-2 text-app-ink focus:border-app-accent focus:outline-none';
const FILTER_META_LABEL_CLASS = 'app-text-overline block text-app-ink/50';
const FILTER_INLINE_ACTION_CLASS = 'app-text-caption text-app-ink/50 transition-colors';

interface SavedFilter {
  name: string;
  params: IssueFilterParams;
}

function getStorageKey(taskListId: string) {
  return `pms_saved_filters_${taskListId}`;
}

function loadSavedFilters(taskListId: string): SavedFilter[] {
  try {
    const raw = localStorage.getItem(getStorageKey(taskListId));
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveSavedFilters(taskListId: string, filters: SavedFilter[]) {
  localStorage.setItem(getStorageKey(taskListId), JSON.stringify(filters));
}

function isFilterActive(params: IssueFilterParams): boolean {
  return !!(
    (params.status && params.status.length > 0) ||
    params.priority ||
    params.assignee_id ||
    params.label_id ||
    params.milestone_id ||
    params.start_date_from ||
    params.start_date_to ||
    params.due_date_from ||
    params.due_date_to ||
    (params.archived_state && params.archived_state !== DEFAULT_ISSUE_ARCHIVED_STATE)
  );
}

/** Reusable dropdown wrapper. */
function Dropdown({
  label,
  active,
  children,
  block = false,
}: {
  label: string;
  active: boolean;
  block?: boolean;
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
    <div ref={ref} className={block ? 'relative w-full' : 'relative'}>
      <button
        onClick={() => setOpen(o => !o)}
        className={`${FILTER_TRIGGER_CLASS} ${block ? 'w-full justify-between' : ''} ${
          active
            ? 'border-app-accent text-app-accent bg-app-accent/10'
            : 'border-app-border text-app-ink/60 hover:border-app-ink/30 hover:text-app-ink'
        }`}
      >
        {label}
        <ChevronDown size={12} />
      </button>
      {open && (
        <div className={`${block ? 'left-0 right-0' : 'left-0 min-w-[180px]'} absolute top-full mt-1 z-30 max-h-60 overflow-y-auto rounded-lg border border-app-border bg-app-bg py-1 shadow-xl custom-scrollbar`}>
          {children(() => setOpen(false))}
        </div>
      )}
    </div>
  );
}

export const FilterBar = ({
  taskListId,
  filterParams,
  setFilterParams,
  members,
  milestones,
  labels,
  taskListStatuses,
}: {
  taskListId: string;
  filterParams: IssueFilterParams;
  setFilterParams: (params: IssueFilterParams) => void;
  members: PmsTaskListMember[];
  milestones: PmsMilestone[];
  labels: PmsLabel[];
  taskListStatuses?: PmsTaskListStatus[];
}) => {
  const { t } = useTranslation('apps');
  const statusOptions = taskListStatuses && taskListStatuses.length > 0
    ? taskListStatuses.map(s => ({ value: s.slug, label: s.name }))
    : DEFAULT_statusOptions.map((option) => ({
        value: option.value,
        label: t(option.labelKey),
      }));
  const [savedFilters, setSavedFilters] = useState<SavedFilter[]>(() => loadSavedFilters(taskListId));
  const [saveDialogOpen, setSaveDialogOpen] = useState(false);
  const [mobileFiltersOpen, setMobileFiltersOpen] = useState(false);
  const [filterName, setFilterName] = useState('');

  useEffect(() => {
    setSavedFilters(loadSavedFilters(taskListId));
  }, [taskListId]);

  const active = isFilterActive(filterParams);

  const clearAll = () => {
    setFilterParams(createDefaultIssueFilterParams({ q: filterParams.q }));
  };

  const handleSave = () => {
    if (!filterName.trim()) return;
    const next = [
      ...savedFilters,
      {
        name: filterName.trim(),
        params: createDefaultIssueFilterParams({ ...filterParams, q: undefined }),
      },
    ];
    saveSavedFilters(taskListId, next);
    setSavedFilters(next);
    setFilterName('');
    setSaveDialogOpen(false);
  };

  const handleDeleteSaved = (idx: number) => {
    const next = savedFilters.filter((_, i) => i !== idx);
    saveSavedFilters(taskListId, next);
    setSavedFilters(next);
  };

  const handleLoadSaved = (saved: SavedFilter) => {
    setFilterParams(createDefaultIssueFilterParams({ ...saved.params, q: filterParams.q }));
  };

  // Active filter pills
  const pills: { label: string; clear: () => void }[] = [];
  if (filterParams.status && filterParams.status.length > 0) {
    const statusLabels = filterParams.status.map(s => statusOptions.find(o => o.value === s)?.label ?? s).join(', ');
    pills.push({ label: t('pms.filter.pillStatus', { value: statusLabels }), clear: () => setFilterParams({ ...filterParams, status: undefined }) });
  }
  if (filterParams.priority) {
    const priority = PRIORITY_OPTIONS.find(o => o.value === filterParams.priority);
    const pl = priority ? t(priority.labelKey) : filterParams.priority;
    pills.push({ label: t('pms.filter.pillPriority', { value: pl }), clear: () => setFilterParams({ ...filterParams, priority: undefined }) });
  }
  if (filterParams.assignee_id) {
    const name = members.find(m => m.user_id === filterParams.assignee_id)?.full_name ?? t('common:feedback.unknown');
    pills.push({ label: t('pms.filter.pillAssignee', { value: name }), clear: () => setFilterParams({ ...filterParams, assignee_id: undefined }) });
  }
  if (filterParams.label_id) {
    const name = labels.find(l => l.id === filterParams.label_id)?.name ?? t('common:feedback.unknown');
    pills.push({ label: t('pms.filter.pillLabel', { value: name }), clear: () => setFilterParams({ ...filterParams, label_id: undefined }) });
  }
  if (filterParams.milestone_id) {
    const name = milestones.find(m => m.id === filterParams.milestone_id)?.title ?? t('common:feedback.unknown');
    pills.push({ label: t('pms.filter.pillMilestone', { value: name }), clear: () => setFilterParams({ ...filterParams, milestone_id: undefined }) });
  }
  if (filterParams.start_date_from || filterParams.start_date_to) {
    const from = filterParams.start_date_from ?? '...';
    const to = filterParams.start_date_to ?? '...';
    pills.push({ label: t('pms.filter.pillStart', { from, to }), clear: () => setFilterParams({ ...filterParams, start_date_from: undefined, start_date_to: undefined }) });
  }
  if (filterParams.due_date_from || filterParams.due_date_to) {
    const from = filterParams.due_date_from ?? '...';
    const to = filterParams.due_date_to ?? '...';
    pills.push({ label: t('pms.filter.pillDue', { from, to }), clear: () => setFilterParams({ ...filterParams, due_date_from: undefined, due_date_to: undefined }) });
  }
  if (filterParams.archived_state && filterParams.archived_state !== DEFAULT_ISSUE_ARCHIVED_STATE) {
    const archiveOption = ARCHIVE_OPTIONS.find((option) => option.value === filterParams.archived_state);
    const archiveLabel = archiveOption ? t(archiveOption.labelKey) : filterParams.archived_state;
    pills.push({
      label: t('pms.filter.pillArchive', { value: archiveLabel }),
      clear: () => setFilterParams({ ...filterParams, archived_state: DEFAULT_ISSUE_ARCHIVED_STATE }),
    });
  }

  return (
    <>
      <div className="border-b border-app-border bg-app-bg/70 px-4 py-3 lg:hidden">
        <div className="flex items-center gap-2">
          <div className="app-text-body-sm flex h-10 min-w-0 flex-1 items-center gap-2 rounded-lg border border-app-border bg-app-surface-sidebar px-3 text-app-ink focus-within:border-app-accent">
            <Search size={15} className="shrink-0 text-app-ink/40" />
            <input
              type="text"
              placeholder={t('pms.filter.searchPlaceholder')}
              value={filterParams.q ?? ''}
              onChange={e => setFilterParams({ ...filterParams, q: e.target.value || undefined })}
              className="min-w-0 flex-1 bg-transparent text-inherit focus:outline-none placeholder:text-app-ink/40"
            />
            {filterParams.q && (
              <button
                type="button"
                onClick={() => setFilterParams({ ...filterParams, q: undefined })}
                className="shrink-0 text-app-ink/40 hover:text-app-ink"
                aria-label={t('pms.filter.clearSearch')}
              >
                <X size={13} />
              </button>
            )}
          </div>
          <button
            type="button"
            onClick={() => setMobileFiltersOpen(true)}
            className={`app-text-control-sm flex h-10 shrink-0 items-center gap-1.5 rounded-lg border px-3 ${
              active
                ? 'border-app-accent bg-app-accent/10 text-app-accent'
                : 'border-app-border text-app-ink/70 hover:bg-app-surface-hover hover:text-app-ink'
            }`}
          >
            <Filter size={15} />
            <span>{t('pms.filter.filter')}</span>
            {pills.length > 0 ? (
              <span className="app-text-micro rounded-full bg-app-accent px-1.5 py-0.5 text-app-accent-fg">
                {pills.length}
              </span>
            ) : null}
          </button>
        </div>

        {pills.length > 0 ? (
          <div className="mt-2 flex gap-1.5 overflow-x-auto pb-0.5">
            {pills.map((pill, idx) => (
              <span key={idx} className="app-text-caption inline-flex shrink-0 items-center gap-1 rounded-full bg-app-accent/10 px-2 py-1 text-app-accent">
                {pill.label}
                <button
                  onClick={pill.clear}
                  className="hover:text-app-ink transition-colors"
                  aria-label={t('pms.filter.removeFilter', { label: pill.label })}
                >
                  <X size={10} />
                </button>
              </span>
            ))}
          </div>
        ) : null}
      </div>

      <div className="hidden items-center gap-2 flex-wrap px-6 py-2 border-b border-app-border bg-app-bg/50 lg:flex">
      {/* Search */}
      <div className="app-text-body-sm flex h-8 items-center gap-1.5 rounded-md border border-app-border bg-app-surface-sidebar px-2.5 text-app-ink focus-within:border-app-accent">
        <Search size={13} className="text-app-ink/40 shrink-0" />
        <input
          type="text"
          placeholder={t('pms.filter.searchPlaceholder')}
          value={filterParams.q ?? ''}
          onChange={e => setFilterParams({ ...filterParams, q: e.target.value || undefined })}
          className="w-36 bg-transparent text-inherit focus:outline-none placeholder:text-app-ink/40"
        />
        {filterParams.q && (
          <button
            type="button"
            onClick={() => setFilterParams({ ...filterParams, q: undefined })}
            className="text-app-ink/40 hover:text-app-ink shrink-0"
          >
            <X size={11} />
          </button>
        )}
      </div>
      <div className="h-4 w-px bg-app-border" />

      <Filter size={13} className="text-app-ink/40 shrink-0" />

      {/* Status (multi-select) */}
      <Dropdown label={t('pms.filter.statusLabel')} active={!!(filterParams.status && filterParams.status.length > 0)}>
        {() => (
          <>
            {statusOptions.map(opt => {
              const checked = filterParams.status?.includes(opt.value) ?? false;
              return (
                <label key={opt.value} className={FILTER_CHECKBOX_ITEM_CLASS}>
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => {
                      const current = filterParams.status ?? [];
                      const next = checked ? current.filter(s => s !== opt.value) : [...current, opt.value];
                      setFilterParams({ ...filterParams, status: next.length > 0 ? next : undefined });
                    }}
                    className="accent-app-accent"
                  />
                  {opt.label}
                </label>
              );
            })}
          </>
        )}
      </Dropdown>

      {/* Priority */}
      <Dropdown label={t('pms.filter.priorityLabel')} active={!!filterParams.priority}>
        {(close) => (
          <>
            <button
              onClick={() => { setFilterParams({ ...filterParams, priority: undefined }); close(); }}
              className={`${FILTER_MENU_ITEM_CLASS} ${!filterParams.priority ? 'font-medium text-app-accent' : 'text-app-ink'}`}
            >
              {t('pms.filter.all')}
            </button>
            {PRIORITY_OPTIONS.map(opt => (
              <button
                key={opt.value}
                onClick={() => { setFilterParams({ ...filterParams, priority: opt.value }); close(); }}
                className={`${FILTER_MENU_ITEM_CLASS} ${filterParams.priority === opt.value ? 'font-medium text-app-accent' : 'text-app-ink'}`}
              >
                {t(opt.labelKey)}
              </button>
            ))}
          </>
        )}
      </Dropdown>

      {/* Assignee */}
      <Dropdown label={t('pms.filter.assigneeLabel')} active={!!filterParams.assignee_id}>
        {(close) => (
          <>
            <button
              onClick={() => { setFilterParams({ ...filterParams, assignee_id: undefined }); close(); }}
              className={`${FILTER_MENU_ITEM_CLASS} ${!filterParams.assignee_id ? 'font-medium text-app-accent' : 'text-app-ink'}`}
            >
              {t('pms.filter.all')}
            </button>
            {members.map(m => (
              <button
                key={m.user_id}
                onClick={() => { setFilterParams({ ...filterParams, assignee_id: m.user_id }); close(); }}
                className={`${FILTER_MENU_ITEM_CLASS} ${filterParams.assignee_id === m.user_id ? 'font-medium text-app-accent' : 'text-app-ink'}`}
              >
                {m.full_name}
              </button>
            ))}
          </>
        )}
      </Dropdown>

      {/* Label */}
      <Dropdown label={t('pms.filter.labelLabel')} active={!!filterParams.label_id}>
        {(close) => (
          <>
            <button
              onClick={() => { setFilterParams({ ...filterParams, label_id: undefined }); close(); }}
              className={`${FILTER_MENU_ITEM_CLASS} ${!filterParams.label_id ? 'font-medium text-app-accent' : 'text-app-ink'}`}
            >
              {t('pms.filter.all')}
            </button>
            {labels.map(l => (
              <button
                key={l.id}
                onClick={() => { setFilterParams({ ...filterParams, label_id: l.id }); close(); }}
                className={`${FILTER_MENU_ITEM_CLASS} flex items-center gap-2 ${filterParams.label_id === l.id ? 'font-medium text-app-accent' : 'text-app-ink'}`}
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
        <Dropdown label={t('pms.filter.milestoneLabel')} active={!!filterParams.milestone_id}>
          {(close) => (
            <>
              <button
                onClick={() => { setFilterParams({ ...filterParams, milestone_id: undefined }); close(); }}
                className={`${FILTER_MENU_ITEM_CLASS} ${!filterParams.milestone_id ? 'font-medium text-app-accent' : 'text-app-ink'}`}
              >
                {t('pms.filter.all')}
              </button>
              {milestones.map(m => (
                <button
                  key={m.id}
                  onClick={() => { setFilterParams({ ...filterParams, milestone_id: m.id }); close(); }}
                  className={`${FILTER_MENU_ITEM_CLASS} ${filterParams.milestone_id === m.id ? 'font-medium text-app-accent' : 'text-app-ink'}`}
                >
                  {m.title}
                </button>
              ))}
            </>
          )}
        </Dropdown>
      )}

      {/* Start Date Range */}
      <Dropdown label={t('pms.filter.startDateLabel')} active={!!(filterParams.start_date_from || filterParams.start_date_to)}>
        {() => (
          <div className="px-3 py-2 space-y-2">
            <label className={FILTER_META_LABEL_CLASS}>{t('pms.filter.from')}</label>
            <input
              type="date"
              value={filterParams.start_date_from ?? ''}
              onChange={e => setFilterParams({ ...filterParams, start_date_from: e.target.value || undefined })}
              className={FILTER_FIELD_CLASS}
            />
            <label className={FILTER_META_LABEL_CLASS}>{t('pms.filter.to')}</label>
            <input
              type="date"
              value={filterParams.start_date_to ?? ''}
              onChange={e => setFilterParams({ ...filterParams, start_date_to: e.target.value || undefined })}
              className={FILTER_FIELD_CLASS}
            />
          </div>
        )}
      </Dropdown>

      {/* Due Date Range */}
      <Dropdown label={t('pms.filter.dueDateLabel')} active={!!(filterParams.due_date_from || filterParams.due_date_to)}>
        {() => (
          <div className="px-3 py-2 space-y-2">
            <label className={FILTER_META_LABEL_CLASS}>{t('pms.filter.from')}</label>
            <input
              type="date"
              value={filterParams.due_date_from ?? ''}
              onChange={e => setFilterParams({ ...filterParams, due_date_from: e.target.value || undefined })}
              className={FILTER_FIELD_CLASS}
            />
            <label className={FILTER_META_LABEL_CLASS}>{t('pms.filter.to')}</label>
            <input
              type="date"
              value={filterParams.due_date_to ?? ''}
              onChange={e => setFilterParams({ ...filterParams, due_date_to: e.target.value || undefined })}
              className={FILTER_FIELD_CLASS}
            />
          </div>
        )}
      </Dropdown>

      {/* Archived visibility */}
      <Dropdown
        label={t('pms.filter.archiveLabel')}
        active={!!(filterParams.archived_state && filterParams.archived_state !== DEFAULT_ISSUE_ARCHIVED_STATE)}
      >
        {(close) => (
          <>
            {ARCHIVE_OPTIONS.map((option) => (
              <button
                key={option.value}
                onClick={() => {
                  setFilterParams({ ...filterParams, archived_state: option.value });
                  close();
                }}
                className={`${FILTER_MENU_ITEM_CLASS} ${
                  (filterParams.archived_state ?? DEFAULT_ISSUE_ARCHIVED_STATE) === option.value
                    ? 'font-medium text-app-accent'
                    : 'text-app-ink'
                }`}
              >
                {t(option.labelKey)}
              </button>
            ))}
          </>
        )}
      </Dropdown>

      {/* Separator + actions */}
      {active && (
        <>
          <div className="h-4 w-px bg-app-border mx-1" />
          <button onClick={clearAll} className={`${FILTER_INLINE_ACTION_CLASS} hover:text-app-ink`}>
            {t('pms.filter.clearAll')}
          </button>
          <button
            onClick={() => setSaveDialogOpen(true)}
            className={`${FILTER_INLINE_ACTION_CLASS} flex items-center gap-1 hover:text-app-accent`}
          >
            <Save size={11} />
            {t('common:actions.save')}
          </button>
        </>
      )}

      {/* Saved filters */}
      {savedFilters.length > 0 && (
        <Dropdown label={t('pms.filter.savedCount', { count: savedFilters.length })} active={false}>
          {(close) => (
            <>
              {savedFilters.map((sf, idx) => (
                <div key={idx} className="flex items-center justify-between px-3 py-1.5 hover:bg-app-surface-hover group">
                  <button
                    onClick={() => { handleLoadSaved(sf); close(); }}
                    className="app-text-body-sm flex flex-1 items-center gap-2 text-left text-app-ink"
                  >
                    <BookmarkCheck size={12} className="text-app-accent shrink-0" />
                    {sf.name}
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); handleDeleteSaved(idx); }}
                    className="opacity-0 group-hover:opacity-100 text-app-ink/30 hover:text-red-400 p-0.5"
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
            placeholder={t('pms.filter.filterNamePlaceholder')}
            autoFocus
            className={`${FILTER_FIELD_CLASS} w-32`}
          />
          <button onClick={handleSave} className="app-text-body-sm font-medium text-app-accent hover:text-app-accent/80">
            {t('common:actions.save')}
          </button>
          <button onClick={() => setSaveDialogOpen(false)} className="app-text-body-sm text-app-ink/40 hover:text-app-ink">
            {t('common:actions.cancel')}
          </button>
        </div>
      )}

      {/* Active filter pills */}
      {pills.length > 0 && (
        <div className="flex items-center gap-1.5 ml-2 flex-wrap">
          {pills.map((pill, idx) => (
            <span key={idx} className="app-text-caption inline-flex items-center gap-1 rounded-full bg-app-accent/10 px-2 py-0.5 text-app-accent">
              {pill.label}
              <button
                onClick={pill.clear}
                className="hover:text-app-ink transition-colors"
                aria-label={t('pms.filter.removeFilter', { label: pill.label })}
              >
                <X size={10} />
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
      <DetailDrawer
        actions={
          <div className="flex gap-2">
            <button
              type="button"
              onClick={clearAll}
              className="app-text-control-sm flex-1 rounded-md border border-app-border px-3 py-2 text-app-ink hover:bg-app-surface-hover"
            >
              {t('pms.filter.clear')}
            </button>
            <button
              type="button"
              onClick={() => setMobileFiltersOpen(false)}
              className="app-text-control-sm flex-1 rounded-md bg-app-accent px-3 py-2 text-app-accent-fg"
            >
              {t('pms.filter.done')}
            </button>
          </div>
        }
        closeLabel={t('pms.filter.closeFilters')}
        contentClassName="border-app-border bg-app-bg"
        description={t('pms.filter.drawerDescription')}
        onOpenChange={setMobileFiltersOpen}
        open={mobileFiltersOpen}
        title={t('pms.filter.filters')}
      >
        <div className="space-y-3">
          {pills.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {pills.map((pill, idx) => (
                <span key={idx} className="app-text-caption inline-flex items-center gap-1 rounded-full bg-app-accent/10 px-2 py-1 text-app-accent">
                  {pill.label}
                  <button
                    onClick={pill.clear}
                    className="hover:text-app-ink transition-colors"
                    aria-label={t('pms.filter.removeFilter', { label: pill.label })}
                  >
                    <X size={10} />
                  </button>
                </span>
              ))}
            </div>
          ) : null}

          <Dropdown block label={t('pms.filter.statusLabel')} active={!!(filterParams.status && filterParams.status.length > 0)}>
            {() => (
              <>
                {statusOptions.map(opt => {
                  const checked = filterParams.status?.includes(opt.value) ?? false;
                  return (
                    <label key={opt.value} className={FILTER_CHECKBOX_ITEM_CLASS}>
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => {
                          const current = filterParams.status ?? [];
                          const next = checked ? current.filter(s => s !== opt.value) : [...current, opt.value];
                          setFilterParams({ ...filterParams, status: next.length > 0 ? next : undefined });
                        }}
                        className="accent-app-accent"
                      />
                      {opt.label}
                    </label>
                  );
                })}
              </>
            )}
          </Dropdown>

          <Dropdown block label={t('pms.filter.priorityLabel')} active={!!filterParams.priority}>
            {(close) => (
              <>
                <button
                  onClick={() => { setFilterParams({ ...filterParams, priority: undefined }); close(); }}
                  className={`${FILTER_MENU_ITEM_CLASS} ${!filterParams.priority ? 'font-medium text-app-accent' : 'text-app-ink'}`}
                >
                  {t('pms.filter.all')}
                </button>
                {PRIORITY_OPTIONS.map(opt => (
                  <button
                    key={opt.value}
                    onClick={() => { setFilterParams({ ...filterParams, priority: opt.value }); close(); }}
                    className={`${FILTER_MENU_ITEM_CLASS} ${filterParams.priority === opt.value ? 'font-medium text-app-accent' : 'text-app-ink'}`}
                  >
                    {t(opt.labelKey)}
                  </button>
                ))}
              </>
            )}
          </Dropdown>

          <Dropdown block label={t('pms.filter.assigneeLabel')} active={!!filterParams.assignee_id}>
            {(close) => (
              <>
                <button
                  onClick={() => { setFilterParams({ ...filterParams, assignee_id: undefined }); close(); }}
                  className={`${FILTER_MENU_ITEM_CLASS} ${!filterParams.assignee_id ? 'font-medium text-app-accent' : 'text-app-ink'}`}
                >
                  {t('pms.filter.all')}
                </button>
                {members.map(m => (
                  <button
                    key={m.user_id}
                    onClick={() => { setFilterParams({ ...filterParams, assignee_id: m.user_id }); close(); }}
                    className={`${FILTER_MENU_ITEM_CLASS} ${filterParams.assignee_id === m.user_id ? 'font-medium text-app-accent' : 'text-app-ink'}`}
                  >
                    {m.full_name}
                  </button>
                ))}
              </>
            )}
          </Dropdown>

          <Dropdown block label={t('pms.filter.labelLabel')} active={!!filterParams.label_id}>
            {(close) => (
              <>
                <button
                  onClick={() => { setFilterParams({ ...filterParams, label_id: undefined }); close(); }}
                  className={`${FILTER_MENU_ITEM_CLASS} ${!filterParams.label_id ? 'font-medium text-app-accent' : 'text-app-ink'}`}
                >
                  {t('pms.filter.all')}
                </button>
                {labels.map(l => (
                  <button
                    key={l.id}
                    onClick={() => { setFilterParams({ ...filterParams, label_id: l.id }); close(); }}
                    className={`${FILTER_MENU_ITEM_CLASS} flex items-center gap-2 ${filterParams.label_id === l.id ? 'font-medium text-app-accent' : 'text-app-ink'}`}
                  >
                    <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: l.color }} />
                    {l.name}
                  </button>
                ))}
              </>
            )}
          </Dropdown>

          {milestones.length > 0 && (
            <Dropdown block label={t('pms.filter.milestoneLabel')} active={!!filterParams.milestone_id}>
              {(close) => (
                <>
                  <button
                    onClick={() => { setFilterParams({ ...filterParams, milestone_id: undefined }); close(); }}
                    className={`${FILTER_MENU_ITEM_CLASS} ${!filterParams.milestone_id ? 'font-medium text-app-accent' : 'text-app-ink'}`}
                  >
                    {t('pms.filter.all')}
                  </button>
                  {milestones.map(m => (
                    <button
                      key={m.id}
                      onClick={() => { setFilterParams({ ...filterParams, milestone_id: m.id }); close(); }}
                      className={`${FILTER_MENU_ITEM_CLASS} ${filterParams.milestone_id === m.id ? 'font-medium text-app-accent' : 'text-app-ink'}`}
                    >
                      {m.title}
                    </button>
                  ))}
                </>
              )}
            </Dropdown>
          )}

          <Dropdown block label={t('pms.filter.startDateLabel')} active={!!(filterParams.start_date_from || filterParams.start_date_to)}>
            {() => (
              <div className="px-3 py-2 space-y-2">
                <label className={FILTER_META_LABEL_CLASS}>{t('pms.filter.from')}</label>
                <input
                  type="date"
                  value={filterParams.start_date_from ?? ''}
                  onChange={e => setFilterParams({ ...filterParams, start_date_from: e.target.value || undefined })}
                  className={FILTER_FIELD_CLASS}
                />
                <label className={FILTER_META_LABEL_CLASS}>{t('pms.filter.to')}</label>
                <input
                  type="date"
                  value={filterParams.start_date_to ?? ''}
                  onChange={e => setFilterParams({ ...filterParams, start_date_to: e.target.value || undefined })}
                  className={FILTER_FIELD_CLASS}
                />
              </div>
            )}
          </Dropdown>

          <Dropdown block label={t('pms.filter.dueDateLabel')} active={!!(filterParams.due_date_from || filterParams.due_date_to)}>
            {() => (
              <div className="px-3 py-2 space-y-2">
                <label className={FILTER_META_LABEL_CLASS}>{t('pms.filter.from')}</label>
                <input
                  type="date"
                  value={filterParams.due_date_from ?? ''}
                  onChange={e => setFilterParams({ ...filterParams, due_date_from: e.target.value || undefined })}
                  className={FILTER_FIELD_CLASS}
                />
                <label className={FILTER_META_LABEL_CLASS}>{t('pms.filter.to')}</label>
                <input
                  type="date"
                  value={filterParams.due_date_to ?? ''}
                  onChange={e => setFilterParams({ ...filterParams, due_date_to: e.target.value || undefined })}
                  className={FILTER_FIELD_CLASS}
                />
              </div>
            )}
          </Dropdown>

          <Dropdown
            block
            label={t('pms.filter.archiveLabel')}
            active={!!(filterParams.archived_state && filterParams.archived_state !== DEFAULT_ISSUE_ARCHIVED_STATE)}
          >
            {(close) => (
              <>
                {ARCHIVE_OPTIONS.map((option) => (
                  <button
                    key={option.value}
                    onClick={() => {
                      setFilterParams({ ...filterParams, archived_state: option.value });
                      close();
                    }}
                    className={`${FILTER_MENU_ITEM_CLASS} ${
                      (filterParams.archived_state ?? DEFAULT_ISSUE_ARCHIVED_STATE) === option.value
                        ? 'font-medium text-app-accent'
                        : 'text-app-ink'
                    }`}
                  >
                    {t(option.labelKey)}
                  </button>
                ))}
              </>
            )}
          </Dropdown>

          {active ? (
            <button
              onClick={() => setSaveDialogOpen(true)}
              className={`${FILTER_INLINE_ACTION_CLASS} flex items-center gap-1 hover:text-app-accent`}
            >
              <Save size={11} />
              {t('pms.filter.saveCurrentFilters')}
            </button>
          ) : null}

          {savedFilters.length > 0 ? (
            <Dropdown block label={t('pms.filter.savedCount', { count: savedFilters.length })} active={false}>
              {(close) => (
                <>
                  {savedFilters.map((sf, idx) => (
                    <div key={idx} className="flex items-center justify-between px-3 py-1.5 hover:bg-app-surface-hover group">
                      <button
                        onClick={() => { handleLoadSaved(sf); close(); }}
                        className="app-text-body-sm flex flex-1 items-center gap-2 text-left text-app-ink"
                      >
                        <BookmarkCheck size={12} className="text-app-accent shrink-0" />
                        {sf.name}
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); handleDeleteSaved(idx); }}
                        className="opacity-0 group-hover:opacity-100 text-app-ink/30 hover:text-red-400 p-0.5"
                      >
                        <X size={11} />
                      </button>
                    </div>
                  ))}
                </>
              )}
            </Dropdown>
          ) : null}

          {saveDialogOpen ? (
            <div className="rounded-lg border border-app-border bg-app-surface p-3">
              <input
                type="text"
                value={filterName}
                onChange={e => setFilterName(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') handleSave(); if (e.key === 'Escape') setSaveDialogOpen(false); }}
                placeholder={t('pms.filter.filterNamePlaceholder')}
                autoFocus
                className={FILTER_FIELD_CLASS}
              />
              <div className="mt-2 flex gap-2">
                <button onClick={handleSave} className="app-text-body-sm flex-1 rounded-md bg-app-accent px-3 py-2 font-medium text-app-accent-fg">
                  {t('common:actions.save')}
                </button>
                <button onClick={() => setSaveDialogOpen(false)} className="app-text-body-sm flex-1 rounded-md border border-app-border px-3 py-2 text-app-ink/60 hover:text-app-ink">
                  {t('common:actions.cancel')}
                </button>
              </div>
            </div>
          ) : null}
        </div>
      </DetailDrawer>
    </>
  );
};
