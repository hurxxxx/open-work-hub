import { useState, useRef, useEffect, useMemo } from 'react';
import {
  X,
  Filter,
  ChevronDown,
  Save,
  BookmarkCheck,
  Search,
} from 'lucide-react';
import { DetailDrawer } from '@open-work-hub/ui';
import { useTranslation } from 'react-i18next';
import { DateInput } from '@/src/components/date/DateInput';
import { UserOptionRow } from '@/src/platform/users/UserSearchMultiSelect';
import { selectUserOptionsForPicker } from '@/src/platform/users/user-option-picker-model';
import type {
  TaskFilterParams,
  PmsTaskListMember,
  PmsMilestone,
  PmsLabel,
  PmsTaskListStatus,
} from '../api/pms-api';
import {
  DEFAULT_ISSUE_ARCHIVED_STATE,
  getEffectiveTaskStatusFilter,
} from '../api/pms-filters';
import {
  buildTaskFilterPills,
  createClearedTaskFilterParams,
  createSavedFilter,
  isFilterActive,
  loadSavedFilters,
  paramsFromSavedFilter,
  removeSavedFilterAt,
  saveSavedFilters,
  type FilterBarStatusOption,
  type SavedFilter,
} from './filter-bar-model';

const DEFAULT_statusOptions = [
  {
    value: 'todo',
    category: 'not_started',
    labelKey: 'pms.filter.status.todo',
  },
  {
    value: 'in_progress',
    category: 'active',
    labelKey: 'pms.filter.status.inProgress',
  },
  {
    value: 'review',
    category: 'active',
    labelKey: 'pms.filter.status.review',
  },
  {
    value: 'done',
    category: 'done',
    labelKey: 'pms.filter.status.done',
  },
  {
    value: 'complete',
    category: 'closed',
    labelKey: 'pms.filter.status.complete',
  },
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

const FILTER_TRIGGER_CLASS = 'app-control h-8 shrink-0 px-2.5';
const FILTER_MENU_ITEM_CLASS = 'app-menu-item';
const FILTER_CHECKBOX_ITEM_CLASS = 'app-menu-checkbox-item';
const FILTER_FIELD_CLASS = 'app-field-input-sm bg-app-surface-sidebar';
const FILTER_META_LABEL_CLASS = 'app-text-overline block text-app-ink/50';
const FILTER_INLINE_ACTION_CLASS =
  'app-text-caption text-app-ink/50 transition-colors';

function isFloatingLayerTarget(target: EventTarget | null): boolean {
  return (
    target instanceof Element &&
    target.closest('[data-ui-floating-layer]') !== null
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
      if (isFloatingLayerTarget(e.target)) return;
      if (ref.current && !ref.current.contains(e.target as Node))
        setOpen(false);
    }
    if (open) document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  return (
    <div ref={ref} className={block ? 'relative w-full' : 'relative'}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={`${FILTER_TRIGGER_CLASS} ${block ? 'w-full justify-between' : ''} ${
          active
            ? 'app-control-active'
            : 'border-app-border text-app-ink/60 hover:border-app-ink/30 hover:text-app-ink'
        }`}
      >
        {label}
        <ChevronDown size={12} />
      </button>
      {open && (
        <div
          className={`${block ? 'left-0 right-0' : 'left-0 min-w-[180px]'} absolute top-full z-[var(--ui-z-popover)] mt-1 max-h-60 overflow-y-auto rounded-lg border border-app-border bg-app-bg py-1 shadow-xl custom-scrollbar`}
        >
          {children(() => setOpen(false))}
        </div>
      )}
    </div>
  );
}

type FilterBarProps = {
  taskListId: string;
  filterParams: TaskFilterParams;
  setFilterParams: (params: TaskFilterParams) => void;
  members: PmsTaskListMember[];
  currentUserId?: string | null;
  milestones: PmsMilestone[];
  labels: PmsLabel[];
  taskListStatuses?: PmsTaskListStatus[];
};

type MemberUserOption = PmsTaskListMember & { id: string };

function memberUserOption(member: PmsTaskListMember): MemberUserOption {
  return { ...member, id: member.user_id };
}

export function FilterBar(props: FilterBarProps) {
  const model = useFilterBarModel(props);
  return renderFilterBarContent(model);
}

function useFilterBarModel({
  taskListId,
  filterParams,
  setFilterParams,
  members,
  currentUserId,
  milestones,
  labels,
  taskListStatuses,
}: FilterBarProps) {
  const { t } = useTranslation('apps');
  const configuredStatuses = taskListStatuses ?? [];
  const hasConfiguredStatuses = configuredStatuses.length > 0;
  const statusOptions: FilterBarStatusOption[] = hasConfiguredStatuses
    ? configuredStatuses.map((s) => ({ value: s.slug, label: s.name }))
    : DEFAULT_statusOptions.map((option) => ({
        value: option.value,
        label: t(option.labelKey),
      }));
  const statusDefinitions = hasConfiguredStatuses
    ? configuredStatuses
    : DEFAULT_statusOptions.map((option) => ({
        category: option.category,
        slug: option.value,
      }));
  const selectedStatusSlugs =
    getEffectiveTaskStatusFilter(filterParams.status, statusDefinitions) ?? [];
  const selectedStatusSet = new Set(selectedStatusSlugs);
  const [, refreshSavedFilters] = useState(0);
  const [saveDialogOpen, setSaveDialogOpen] = useState(false);
  const [mobileFiltersOpen, setMobileFiltersOpen] = useState(false);
  const [filterName, setFilterName] = useState('');
  const [assigneeQuery, setAssigneeQuery] = useState('');

  const active = isFilterActive(filterParams);
  const savedFilters = loadSavedFilters(taskListId);

  const clearAll = () => {
    setFilterParams(createClearedTaskFilterParams(filterParams));
  };

  const handleSave = () => {
    const saved = createSavedFilter(filterName, filterParams);
    if (!saved) return;
    const next = [...savedFilters, saved];
    saveSavedFilters(taskListId, next);
    refreshSavedFilters((version) => version + 1);
    setFilterName('');
    setSaveDialogOpen(false);
  };

  const handleDeleteSaved = (idx: number) => {
    const next = removeSavedFilterAt(savedFilters, idx);
    saveSavedFilters(taskListId, next);
    refreshSavedFilters((version) => version + 1);
  };

  const handleLoadSaved = (saved: SavedFilter) => {
    setFilterParams(paramsFromSavedFilter(saved, filterParams));
  };

  const toggleStatus = (status: string) => {
    const next = selectedStatusSet.has(status)
      ? selectedStatusSlugs.filter((selected) => selected !== status)
      : [...selectedStatusSlugs, status];
    setFilterParams({ ...filterParams, status: next });
  };

  const pills = buildTaskFilterPills({
    labels,
    members,
    milestones,
    params: filterParams,
    statusOptions,
    translate: (key, options) => t(key, options),
  }).map((pill) => ({
    label: pill.label,
    clear: () => setFilterParams(pill.clearParams),
  }));
  const assigneeOptions = useMemo(
    () =>
      selectUserOptionsForPicker({
        users: members.map(memberUserOption),
        query: assigneeQuery,
        currentUserId,
        limit: 12,
      }),
    [assigneeQuery, currentUserId, members],
  );

  return {
    active,
    assigneeOptions,
    assigneeQuery,
    clearAll,
    currentUserId,
    filterName,
    filterParams,
    handleDeleteSaved,
    handleLoadSaved,
    handleSave,
    labels,
    members,
    milestones,
    mobileFiltersOpen,
    pills,
    saveDialogOpen,
    savedFilters,
    setAssigneeQuery,
    setFilterName,
    setFilterParams,
    setMobileFiltersOpen,
    setSaveDialogOpen,
    selectedStatusSet,
    statusOptions,
    t,
    toggleStatus,
  };
}

function renderFilterBarContent({
  active,
  assigneeOptions,
  assigneeQuery,
  clearAll,
  currentUserId,
  filterName,
  filterParams,
  handleDeleteSaved,
  handleLoadSaved,
  handleSave,
  labels,
  members,
  milestones,
  mobileFiltersOpen,
  pills,
  saveDialogOpen,
  savedFilters,
  setAssigneeQuery,
  setFilterName,
  setFilterParams,
  setMobileFiltersOpen,
  setSaveDialogOpen,
  selectedStatusSet,
  statusOptions,
  t,
  toggleStatus,
}: ReturnType<typeof useFilterBarModel>) {
  return (
    <>
      <div className="border-b border-app-border bg-app-bg/70 px-4 py-3 lg:hidden">
        <div className="flex items-center gap-2">
          <div className="app-text-body-sm flex h-9 min-w-0 flex-1 items-center gap-2 rounded-lg border border-app-border bg-app-surface-sidebar px-3 text-app-ink focus-within:border-app-accent">
            <Search size={15} className="shrink-0 text-app-ink/40" />
            <input
              type="text"
              aria-label={t('pms.filter.searchPlaceholder')}
              placeholder={t('pms.filter.searchPlaceholder')}
              value={filterParams.q ?? ''}
              onChange={(e) =>
                setFilterParams({
                  ...filterParams,
                  q: e.target.value || undefined,
                })
              }
              className="min-w-0 flex-1 bg-transparent text-inherit focus:outline-none placeholder:text-app-ink/40"
            />
            {filterParams.q && (
              <button
                type="button"
                onClick={() =>
                  setFilterParams({ ...filterParams, q: undefined })
                }
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
            className={`app-control h-9 shrink-0 rounded-lg px-3 ${
              active
                ? 'app-control-active'
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
            {pills.map((pill) => (
              <span
                key={pill.label}
                className="app-text-caption inline-flex shrink-0 items-center gap-1 rounded-full bg-app-accent/10 px-2 py-1 text-app-accent"
              >
                {pill.label}
                <button
                  type="button"
                  onClick={pill.clear}
                  className="hover:text-app-ink transition-colors"
                  aria-label={t('pms.filter.removeFilter', {
                    label: pill.label,
                  })}
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
            aria-label={t('pms.filter.searchPlaceholder')}
            placeholder={t('pms.filter.searchPlaceholder')}
            value={filterParams.q ?? ''}
            onChange={(e) =>
              setFilterParams({
                ...filterParams,
                q: e.target.value || undefined,
              })
            }
            className="w-36 bg-transparent text-inherit focus:outline-none placeholder:text-app-ink/40"
          />
          {filterParams.q && (
            <button
              type="button"
              onClick={() => setFilterParams({ ...filterParams, q: undefined })}
              className="text-app-ink/40 hover:text-app-ink shrink-0"
              aria-label={t('pms.filter.clearSearch')}
            >
              <X size={11} />
            </button>
          )}
        </div>
        <div className="h-4 w-px bg-app-border" />

        <Filter size={13} className="text-app-ink/40 shrink-0" />

        {/* Status (multi-select) */}
        <Dropdown
          label={t('pms.filter.statusLabel')}
          active={selectedStatusSet.size > 0}
        >
          {() => (
            <>
              {statusOptions.map((opt) => {
                const checked = selectedStatusSet.has(opt.value);
                return (
                  <label key={opt.value} className={FILTER_CHECKBOX_ITEM_CLASS}>
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleStatus(opt.value)}
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
        <Dropdown
          label={t('pms.filter.priorityLabel')}
          active={!!filterParams.priority}
        >
          {(close) => (
            <>
              <button
                type="button"
                onClick={() => {
                  setFilterParams({ ...filterParams, priority: undefined });
                  close();
                }}
                className={`${FILTER_MENU_ITEM_CLASS} ${!filterParams.priority ? 'text-app-accent' : 'text-app-ink'}`}
              >
                {t('pms.filter.all')}
              </button>
              {PRIORITY_OPTIONS.map((opt) => (
                <button
                  type="button"
                  key={opt.value}
                  onClick={() => {
                    setFilterParams({ ...filterParams, priority: opt.value });
                    close();
                  }}
                  className={`${FILTER_MENU_ITEM_CLASS} ${filterParams.priority === opt.value ? 'text-app-accent' : 'text-app-ink'}`}
                >
                  {t(opt.labelKey)}
                </button>
              ))}
            </>
          )}
        </Dropdown>

        {/* Assignee */}
        <Dropdown
          label={t('pms.filter.assigneeLabel')}
          active={!!filterParams.assignee_id}
        >
          {(close) => (
            <>
              <div className="px-2 py-1">
                <div className="flex items-center gap-2 rounded-md border border-app-border bg-app-surface-sidebar px-2 py-1.5">
                  <Search size={13} className="shrink-0 text-app-ink/40" />
                  <input
                    aria-label={t('pms.searchUser')}
                    className="app-menu-search-input flex-1"
                    onChange={(event) => setAssigneeQuery(event.target.value)}
                    placeholder={t('pms.searchUser')}
                    value={assigneeQuery}
                  />
                  {assigneeQuery ? (
                    <button
                      aria-label={t('pms.filter.clearSearch')}
                      className="text-app-ink/40 hover:text-app-ink"
                      onClick={() => setAssigneeQuery('')}
                      type="button"
                    >
                      <X size={11} />
                    </button>
                  ) : null}
                </div>
              </div>
              <button
                type="button"
                onClick={() => {
                  setFilterParams({ ...filterParams, assignee_id: undefined });
                  close();
                }}
                className={`${FILTER_MENU_ITEM_CLASS} ${!filterParams.assignee_id ? 'text-app-accent' : 'text-app-ink'}`}
              >
                {t('pms.filter.all')}
              </button>
              {assigneeOptions.map((member) => (
                <UserOptionRow
                  key={member.user_id}
                  currentUserId={currentUserId}
                  currentUserLabel={t('pms.taskDetail.me')}
                  density="compact"
                  onClick={() => {
                    setFilterParams({
                      ...filterParams,
                      assignee_id: member.user_id,
                    });
                    close();
                  }}
                  selected={filterParams.assignee_id === member.user_id}
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
        </Dropdown>

        {/* Label */}
        <Dropdown
          label={t('pms.filter.labelLabel')}
          active={!!filterParams.label_id}
        >
          {(close) => (
            <>
              <button
                type="button"
                onClick={() => {
                  setFilterParams({ ...filterParams, label_id: undefined });
                  close();
                }}
                className={`${FILTER_MENU_ITEM_CLASS} ${!filterParams.label_id ? 'text-app-accent' : 'text-app-ink'}`}
              >
                {t('pms.filter.all')}
              </button>
              {labels.map((l) => (
                <button
                  type="button"
                  key={l.id}
                  onClick={() => {
                    setFilterParams({ ...filterParams, label_id: l.id });
                    close();
                  }}
                  className={`${FILTER_MENU_ITEM_CLASS} flex items-center gap-2 ${filterParams.label_id === l.id ? 'text-app-accent' : 'text-app-ink'}`}
                >
                  <span
                    className="size-2.5 shrink-0 rounded-full"
                    style={{ backgroundColor: l.color }}
                  />
                  {l.name}
                </button>
              ))}
            </>
          )}
        </Dropdown>

        {/* Milestone */}
        {milestones.length > 0 && (
          <Dropdown
            label={t('pms.filter.milestoneLabel')}
            active={!!filterParams.milestone_id}
          >
            {(close) => (
              <>
                <div className="px-2 py-1">
                  <div className="flex items-center gap-2 rounded-md border border-app-border bg-app-surface-sidebar px-2 py-1.5">
                    <Search size={13} className="shrink-0 text-app-ink/40" />
                    <input
                      aria-label={t('pms.searchUser')}
                      className="app-menu-search-input flex-1"
                      onChange={(event) => setAssigneeQuery(event.target.value)}
                      placeholder={t('pms.searchUser')}
                      value={assigneeQuery}
                    />
                    {assigneeQuery ? (
                      <button
                        aria-label={t('pms.filter.clearSearch')}
                        className="text-app-ink/40 hover:text-app-ink"
                        onClick={() => setAssigneeQuery('')}
                        type="button"
                      >
                        <X size={11} />
                      </button>
                    ) : null}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    setFilterParams({
                      ...filterParams,
                      milestone_id: undefined,
                    });
                    close();
                  }}
                  className={`${FILTER_MENU_ITEM_CLASS} ${!filterParams.milestone_id ? 'text-app-accent' : 'text-app-ink'}`}
                >
                  {t('pms.filter.all')}
                </button>
                {milestones.map((m) => (
                  <button
                    type="button"
                    key={m.id}
                    onClick={() => {
                      setFilterParams({ ...filterParams, milestone_id: m.id });
                      close();
                    }}
                    className={`${FILTER_MENU_ITEM_CLASS} ${filterParams.milestone_id === m.id ? 'text-app-accent' : 'text-app-ink'}`}
                  >
                    {m.title}
                  </button>
                ))}
              </>
            )}
          </Dropdown>
        )}

        {/* Start Date Range */}
        <Dropdown
          label={t('pms.filter.startDateLabel')}
          active={
            !!(filterParams.start_date_from || filterParams.start_date_to)
          }
        >
          {() => (
            <div className="px-3 py-2 space-y-2">
              <label className={FILTER_META_LABEL_CLASS}>
                {t('pms.filter.from')}
              </label>
              <DateInput
                value={filterParams.start_date_from ?? ''}
                onValueChange={(value) =>
                  setFilterParams({
                    ...filterParams,
                    start_date_from: value || undefined,
                  })
                }
                className={FILTER_FIELD_CLASS}
              />
              <label className={FILTER_META_LABEL_CLASS}>
                {t('pms.filter.to')}
              </label>
              <DateInput
                value={filterParams.start_date_to ?? ''}
                onValueChange={(value) =>
                  setFilterParams({
                    ...filterParams,
                    start_date_to: value || undefined,
                  })
                }
                className={FILTER_FIELD_CLASS}
              />
            </div>
          )}
        </Dropdown>

        {/* Due Date Range */}
        <Dropdown
          label={t('pms.filter.dueDateLabel')}
          active={!!(filterParams.due_date_from || filterParams.due_date_to)}
        >
          {() => (
            <div className="px-3 py-2 space-y-2">
              <label className={FILTER_META_LABEL_CLASS}>
                {t('pms.filter.from')}
              </label>
              <DateInput
                value={filterParams.due_date_from ?? ''}
                onValueChange={(value) =>
                  setFilterParams({
                    ...filterParams,
                    due_date_from: value || undefined,
                  })
                }
                className={FILTER_FIELD_CLASS}
              />
              <label className={FILTER_META_LABEL_CLASS}>
                {t('pms.filter.to')}
              </label>
              <DateInput
                value={filterParams.due_date_to ?? ''}
                onValueChange={(value) =>
                  setFilterParams({
                    ...filterParams,
                    due_date_to: value || undefined,
                  })
                }
                className={FILTER_FIELD_CLASS}
              />
            </div>
          )}
        </Dropdown>

        {/* Archived visibility */}
        <Dropdown
          label={t('pms.filter.archiveLabel')}
          active={
            !!(
              filterParams.archived_state &&
              filterParams.archived_state !== DEFAULT_ISSUE_ARCHIVED_STATE
            )
          }
        >
          {(close) => (
            <>
              {ARCHIVE_OPTIONS.map((option) => (
                <button
                  type="button"
                  key={option.value}
                  onClick={() => {
                    setFilterParams({
                      ...filterParams,
                      archived_state: option.value,
                    });
                    close();
                  }}
                  className={`${FILTER_MENU_ITEM_CLASS} ${
                    (filterParams.archived_state ??
                      DEFAULT_ISSUE_ARCHIVED_STATE) === option.value
                      ? 'text-app-accent'
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
            <button
              type="button"
              onClick={clearAll}
              className={`${FILTER_INLINE_ACTION_CLASS} hover:text-app-ink`}
            >
              {t('pms.filter.clearAll')}
            </button>
            <button
              type="button"
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
          <Dropdown
            label={t('pms.filter.savedCount', { count: savedFilters.length })}
            active={false}
          >
            {(close) => (
              <>
                {savedFilters.map((sf, idx) => (
                  <div
                    key={`${sf.name}:${JSON.stringify(sf.params)}`}
                    className="flex items-center justify-between px-3 py-1.5 hover:bg-app-surface-hover group"
                  >
                    <button
                      type="button"
                      onClick={() => {
                        handleLoadSaved(sf);
                        close();
                      }}
                      className="app-text-control-sm flex flex-1 items-center gap-2 text-left text-app-ink"
                    >
                      <BookmarkCheck
                        size={12}
                        className="text-app-accent shrink-0"
                      />
                      {sf.name}
                    </button>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDeleteSaved(idx);
                      }}
                      className="opacity-0 group-hover:opacity-100 text-app-ink/30 hover:text-app-danger-text p-0.5"
                      aria-label={t('pms.filter.removeFilter', {
                        label: sf.name,
                      })}
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
              aria-label={t('pms.filter.filterNamePlaceholder')}
              value={filterName}
              onChange={(e) => setFilterName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleSave();
                if (e.key === 'Escape') setSaveDialogOpen(false);
              }}
              placeholder={t('pms.filter.filterNamePlaceholder')}
              className={`${FILTER_FIELD_CLASS} w-32`}
            />
            <button
              type="button"
              onClick={handleSave}
              className="app-text-control-sm text-app-accent hover:text-app-accent/80"
            >
              {t('common:actions.save')}
            </button>
            <button
              type="button"
              onClick={() => setSaveDialogOpen(false)}
              className="app-text-control-sm text-app-ink/40 hover:text-app-ink"
            >
              {t('common:actions.cancel')}
            </button>
          </div>
        )}

        {/* Active filter pills */}
        {pills.length > 0 && (
          <div className="flex items-center gap-1.5 ml-2 flex-wrap">
            {pills.map((pill) => (
              <span
                key={pill.label}
                className="app-text-caption inline-flex items-center gap-1 rounded-full bg-app-accent/10 px-2 py-0.5 text-app-accent"
              >
                {pill.label}
                <button
                  type="button"
                  onClick={pill.clear}
                  className="hover:text-app-ink transition-colors"
                  aria-label={t('pms.filter.removeFilter', {
                    label: pill.label,
                  })}
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
              className="app-control flex-1"
            >
              {t('pms.filter.clear')}
            </button>
            <button
              type="button"
              onClick={() => setMobileFiltersOpen(false)}
              className="app-control-primary flex-1"
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
              {pills.map((pill) => (
                <span
                  key={pill.label}
                  className="app-text-caption inline-flex items-center gap-1 rounded-full bg-app-accent/10 px-2 py-1 text-app-accent"
                >
                  {pill.label}
                  <button
                    type="button"
                    onClick={pill.clear}
                    className="hover:text-app-ink transition-colors"
                    aria-label={t('pms.filter.removeFilter', {
                      label: pill.label,
                    })}
                  >
                    <X size={10} />
                  </button>
                </span>
              ))}
            </div>
          ) : null}

          <Dropdown
            block
            label={t('pms.filter.statusLabel')}
            active={selectedStatusSet.size > 0}
          >
            {() => (
              <>
                {statusOptions.map((opt) => {
                  const checked = selectedStatusSet.has(opt.value);
                  return (
                    <label
                      key={opt.value}
                      className={FILTER_CHECKBOX_ITEM_CLASS}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggleStatus(opt.value)}
                        className="accent-app-accent"
                      />
                      {opt.label}
                    </label>
                  );
                })}
              </>
            )}
          </Dropdown>

          <Dropdown
            block
            label={t('pms.filter.priorityLabel')}
            active={!!filterParams.priority}
          >
            {(close) => (
              <>
                <button
                  type="button"
                  onClick={() => {
                    setFilterParams({ ...filterParams, priority: undefined });
                    close();
                  }}
                  className={`${FILTER_MENU_ITEM_CLASS} ${!filterParams.priority ? 'text-app-accent' : 'text-app-ink'}`}
                >
                  {t('pms.filter.all')}
                </button>
                {PRIORITY_OPTIONS.map((opt) => (
                  <button
                    type="button"
                    key={opt.value}
                    onClick={() => {
                      setFilterParams({ ...filterParams, priority: opt.value });
                      close();
                    }}
                    className={`${FILTER_MENU_ITEM_CLASS} ${filterParams.priority === opt.value ? 'text-app-accent' : 'text-app-ink'}`}
                  >
                    {t(opt.labelKey)}
                  </button>
                ))}
              </>
            )}
          </Dropdown>

          <Dropdown
            block
            label={t('pms.filter.assigneeLabel')}
            active={!!filterParams.assignee_id}
          >
            {(close) => (
              <>
                <button
                  type="button"
                  onClick={() => {
                    setFilterParams({
                      ...filterParams,
                      assignee_id: undefined,
                    });
                    close();
                  }}
                  className={`${FILTER_MENU_ITEM_CLASS} ${!filterParams.assignee_id ? 'text-app-accent' : 'text-app-ink'}`}
                >
                  {t('pms.filter.all')}
                </button>
                {assigneeOptions.map((member) => (
                  <UserOptionRow
                    key={member.user_id}
                    currentUserId={currentUserId}
                    currentUserLabel={t('pms.taskDetail.me')}
                    density="compact"
                    onClick={() => {
                      setFilterParams({
                        ...filterParams,
                        assignee_id: member.user_id,
                      });
                      close();
                    }}
                    selected={filterParams.assignee_id === member.user_id}
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
          </Dropdown>

          <Dropdown
            block
            label={t('pms.filter.labelLabel')}
            active={!!filterParams.label_id}
          >
            {(close) => (
              <>
                <button
                  type="button"
                  onClick={() => {
                    setFilterParams({ ...filterParams, label_id: undefined });
                    close();
                  }}
                  className={`${FILTER_MENU_ITEM_CLASS} ${!filterParams.label_id ? 'text-app-accent' : 'text-app-ink'}`}
                >
                  {t('pms.filter.all')}
                </button>
                {labels.map((l) => (
                  <button
                    type="button"
                    key={l.id}
                    onClick={() => {
                      setFilterParams({ ...filterParams, label_id: l.id });
                      close();
                    }}
                    className={`${FILTER_MENU_ITEM_CLASS} flex items-center gap-2 ${filterParams.label_id === l.id ? 'text-app-accent' : 'text-app-ink'}`}
                  >
                    <span
                      className="size-2.5 shrink-0 rounded-full"
                      style={{ backgroundColor: l.color }}
                    />
                    {l.name}
                  </button>
                ))}
              </>
            )}
          </Dropdown>

          {milestones.length > 0 && (
            <Dropdown
              block
              label={t('pms.filter.milestoneLabel')}
              active={!!filterParams.milestone_id}
            >
              {(close) => (
                <>
                  <button
                    type="button"
                    onClick={() => {
                      setFilterParams({
                        ...filterParams,
                        milestone_id: undefined,
                      });
                      close();
                    }}
                    className={`${FILTER_MENU_ITEM_CLASS} ${!filterParams.milestone_id ? 'text-app-accent' : 'text-app-ink'}`}
                  >
                    {t('pms.filter.all')}
                  </button>
                  {milestones.map((m) => (
                    <button
                      type="button"
                      key={m.id}
                      onClick={() => {
                        setFilterParams({
                          ...filterParams,
                          milestone_id: m.id,
                        });
                        close();
                      }}
                      className={`${FILTER_MENU_ITEM_CLASS} ${filterParams.milestone_id === m.id ? 'text-app-accent' : 'text-app-ink'}`}
                    >
                      {m.title}
                    </button>
                  ))}
                </>
              )}
            </Dropdown>
          )}

          <Dropdown
            block
            label={t('pms.filter.startDateLabel')}
            active={
              !!(filterParams.start_date_from || filterParams.start_date_to)
            }
          >
            {() => (
              <div className="px-3 py-2 space-y-2">
                <label className={FILTER_META_LABEL_CLASS}>
                  {t('pms.filter.from')}
                </label>
                <DateInput
                  value={filterParams.start_date_from ?? ''}
                  onValueChange={(value) =>
                    setFilterParams({
                      ...filterParams,
                      start_date_from: value || undefined,
                    })
                  }
                  className={FILTER_FIELD_CLASS}
                />
                <label className={FILTER_META_LABEL_CLASS}>
                  {t('pms.filter.to')}
                </label>
                <DateInput
                  value={filterParams.start_date_to ?? ''}
                  onValueChange={(value) =>
                    setFilterParams({
                      ...filterParams,
                      start_date_to: value || undefined,
                    })
                  }
                  className={FILTER_FIELD_CLASS}
                />
              </div>
            )}
          </Dropdown>

          <Dropdown
            block
            label={t('pms.filter.dueDateLabel')}
            active={!!(filterParams.due_date_from || filterParams.due_date_to)}
          >
            {() => (
              <div className="px-3 py-2 space-y-2">
                <label className={FILTER_META_LABEL_CLASS}>
                  {t('pms.filter.from')}
                </label>
                <DateInput
                  value={filterParams.due_date_from ?? ''}
                  onValueChange={(value) =>
                    setFilterParams({
                      ...filterParams,
                      due_date_from: value || undefined,
                    })
                  }
                  className={FILTER_FIELD_CLASS}
                />
                <label className={FILTER_META_LABEL_CLASS}>
                  {t('pms.filter.to')}
                </label>
                <DateInput
                  value={filterParams.due_date_to ?? ''}
                  onValueChange={(value) =>
                    setFilterParams({
                      ...filterParams,
                      due_date_to: value || undefined,
                    })
                  }
                  className={FILTER_FIELD_CLASS}
                />
              </div>
            )}
          </Dropdown>

          <Dropdown
            block
            label={t('pms.filter.archiveLabel')}
            active={
              !!(
                filterParams.archived_state &&
                filterParams.archived_state !== DEFAULT_ISSUE_ARCHIVED_STATE
              )
            }
          >
            {(close) => (
              <>
                {ARCHIVE_OPTIONS.map((option) => (
                  <button
                    type="button"
                    key={option.value}
                    onClick={() => {
                      setFilterParams({
                        ...filterParams,
                        archived_state: option.value,
                      });
                      close();
                    }}
                    className={`${FILTER_MENU_ITEM_CLASS} ${
                      (filterParams.archived_state ??
                        DEFAULT_ISSUE_ARCHIVED_STATE) === option.value
                        ? 'text-app-accent'
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
              type="button"
              onClick={() => setSaveDialogOpen(true)}
              className={`${FILTER_INLINE_ACTION_CLASS} flex items-center gap-1 hover:text-app-accent`}
            >
              <Save size={11} />
              {t('pms.filter.saveCurrentFilters')}
            </button>
          ) : null}

          {savedFilters.length > 0 ? (
            <Dropdown
              block
              label={t('pms.filter.savedCount', { count: savedFilters.length })}
              active={false}
            >
              {(close) => (
                <>
                  {savedFilters.map((sf, idx) => (
                    <div
                      key={`${sf.name}:${JSON.stringify(sf.params)}`}
                      className="flex items-center justify-between px-3 py-1.5 hover:bg-app-surface-hover group"
                    >
                      <button
                        type="button"
                        onClick={() => {
                          handleLoadSaved(sf);
                          close();
                        }}
                        className="app-text-control-sm flex flex-1 items-center gap-2 text-left text-app-ink"
                      >
                        <BookmarkCheck
                          size={12}
                          className="text-app-accent shrink-0"
                        />
                        {sf.name}
                      </button>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDeleteSaved(idx);
                        }}
                        className="opacity-0 group-hover:opacity-100 text-app-ink/30 hover:text-app-danger-text p-0.5"
                        aria-label={t('pms.filter.removeFilter', {
                          label: sf.name,
                        })}
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
                aria-label={t('pms.filter.filterNamePlaceholder')}
                value={filterName}
                onChange={(e) => setFilterName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleSave();
                  if (e.key === 'Escape') setSaveDialogOpen(false);
                }}
                placeholder={t('pms.filter.filterNamePlaceholder')}
                className={FILTER_FIELD_CLASS}
              />
              <div className="mt-2 flex gap-2">
                <button
                  type="button"
                  onClick={handleSave}
                  className="app-control-primary flex-1"
                >
                  {t('common:actions.save')}
                </button>
                <button
                  type="button"
                  onClick={() => setSaveDialogOpen(false)}
                  className="app-control flex-1 text-app-ink/60 hover:text-app-ink"
                >
                  {t('common:actions.cancel')}
                </button>
              </div>
            </div>
          ) : null}
        </div>
      </DetailDrawer>
    </>
  );
}
