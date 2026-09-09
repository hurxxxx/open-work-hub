import { DateInput } from '@/src/components/date/DateInput';
import {
  UserOptionAvatar,
  UserOptionRow,
} from '@/src/platform/users/UserSearchMultiSelect';
import {
  selectUserOptionsForPicker,
  userOptionDisplayName,
  type UserOptionLike,
} from '@/src/platform/users/user-option-picker-model';
import { Button } from '@open-work-hub/ui';
import {
  Activity,
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  CalendarDays,
  Check,
  CheckSquare,
  ChevronDown,
  ChevronRight,
  CornerDownRight,
  Ellipsis,
  Eye,
  Flag,
  GitBranch,
  GripVertical,
  Indent,
  Outdent,
  Pencil,
  Plus,
  RotateCcw,
  Search,
  Trash2,
  User2,
  X,
} from 'lucide-react';
import {
  Fragment,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import type {
  PmsStatusCategory,
  PmsTask,
  PmsTaskListGroupBy,
  PmsTaskListMember,
  PmsTaskListStatus,
  PmsTaskSort,
  PmsTaskSortField,
} from '../api/pms-api';
import { DEFAULT_PMS_TASK_SORT } from '../api/pms-api';
import { StatusIconButton, StatusIconGlyph } from './StatusIcon';
import { TaskAssigneeStack } from './TaskAssigneeStack';
import { TaskCard } from './TaskCard';
import {
  buildClearAssigneesPatch,
  buildDatePatch,
  buildToggleAssigneePatch,
  canDropTaskInList,
  dropZoneFromPointer,
  selectedAssigneeIds,
  type TaskDateField,
  type TaskDropZone,
} from './list-view-editing-model';
import { buildAssigneeTaskGroups } from './list-view-grouping-model';
import {
  formatDate,
  getDefaultTaskStatus,
  getStatusLabel,
  getStatusSlugs,
  getStatusTone,
  PRIORITY_COLOR,
} from './pms-constants';
import {
  buildTaskHierarchy,
  getTaskBoardPositionUpdates,
  getTaskRoot,
  sortTasksByHierarchy,
  sortTasksByHierarchyUsingInputOrder,
  type TaskBoardPositionUpdate,
} from './pms-task-hierarchy';

const PRIORITY_OPTIONS = ['low', 'medium', 'high', 'critical'] as const;
const EMPTY_MEMBERS: PmsTaskListMember[] = [];
const TASK_SORT_FIELDS: PmsTaskSortField[] = [
  'board_position',
  'due_date',
  'start_date',
  'created_at',
  'completed_date',
];
const LIST_ACTION_MENU_ITEM_CLASS =
  'app-text-control-sm flex w-full items-center gap-2 whitespace-nowrap px-3 py-1.5 text-left text-app-ink hover:bg-app-surface-hover';

type MemberUserOption = PmsTaskListMember & { id: string };

function memberUserOption(member: PmsTaskListMember): MemberUserOption {
  return { ...member, id: member.user_id };
}

function taskReporterOption(
  task: PmsTask,
  members: readonly PmsTaskListMember[],
): UserOptionLike {
  const member = members.find((item) => item.user_id === task.reporter_id);
  if (member) return memberUserOption(member);
  return {
    id: task.reporter_id,
    email: '',
    full_name: task.reporter_name || task.reporter_id,
  };
}

function isFloatingLayerTarget(target: EventTarget | null): boolean {
  return (
    target instanceof Element &&
    target.closest('[data-ui-floating-layer]') !== null
  );
}

function InlineMenu({
  children,
  trigger,
}: {
  children: (close: () => void) => React.ReactNode;
  trigger: (props: {
    open: boolean;
    toggle: React.MouseEventHandler;
  }) => React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [menuPosition, setMenuPosition] = useState<{
    left: number;
    maxHeight: number;
    top: number;
  } | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handler(event: MouseEvent) {
      const target = event.target as Node;
      if (isFloatingLayerTarget(event.target)) return;
      if (
        ref.current &&
        !ref.current.contains(target) &&
        !menuRef.current?.contains(target)
      ) {
        setOpen(false);
      }
    }
    if (open) document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  useLayoutEffect(() => {
    if (!open || typeof window === 'undefined') {
      setMenuPosition(null);
      return undefined;
    }

    const updatePosition = () => {
      const triggerRect = ref.current?.getBoundingClientRect();
      if (!triggerRect) return;
      const viewportPadding = 8;
      const gutter = 4;
      const menuWidth = menuRef.current?.offsetWidth ?? 190;
      const menuHeight = menuRef.current?.offsetHeight ?? 240;
      const maxHeight = Math.max(160, window.innerHeight - viewportPadding * 2);
      const spaceBelow =
        window.innerHeight - triggerRect.bottom - gutter - viewportPadding;
      const spaceAbove = triggerRect.top - gutter - viewportPadding;
      const shouldOpenAbove =
        menuHeight > spaceBelow && spaceAbove > spaceBelow;
      const top = shouldOpenAbove
        ? Math.max(
            viewportPadding,
            triggerRect.top - Math.min(menuHeight, maxHeight) - gutter,
          )
        : Math.min(
            triggerRect.bottom + gutter,
            window.innerHeight -
              Math.min(menuHeight, maxHeight) -
              viewportPadding,
          );
      const left = Math.min(
        Math.max(viewportPadding, triggerRect.left),
        Math.max(
          viewportPadding,
          window.innerWidth - menuWidth - viewportPadding,
        ),
      );

      setMenuPosition({ left, maxHeight, top });
    };

    updatePosition();
    const raf = window.requestAnimationFrame(updatePosition);
    window.addEventListener('resize', updatePosition);
    window.addEventListener('scroll', updatePosition, true);

    return () => {
      window.cancelAnimationFrame(raf);
      window.removeEventListener('resize', updatePosition);
      window.removeEventListener('scroll', updatePosition, true);
    };
  }, [open]);

  const close = () => setOpen(false);

  return (
    <div
      ref={ref}
      className="relative inline-flex"
      onClick={(event) => event.stopPropagation()}
    >
      {trigger({
        open,
        toggle: (event) => {
          event.stopPropagation();
          setOpen((current) => !current);
        },
      })}
      {open && typeof document !== 'undefined'
        ? createPortal(
            <div
              ref={menuRef}
              className="fixed z-[1000] min-w-[190px] overflow-y-auto rounded-lg border border-app-border bg-app-bg py-1 shadow-xl"
              onClick={(event) => event.stopPropagation()}
              style={{
                left: menuPosition?.left ?? 0,
                maxHeight: menuPosition?.maxHeight ?? 'calc(100vh - 16px)',
                top: menuPosition?.top ?? 0,
                visibility: menuPosition ? 'visible' : 'hidden',
              }}
            >
              {children(close)}
            </div>,
            document.body,
          )
        : null}
    </div>
  );
}

function priorityLabel(priority: string, t: (key: string) => string): string {
  const key = {
    critical: 'pms.priorityCritical',
    high: 'pms.priorityHigh',
    low: 'pms.priorityLow',
    medium: 'pms.priorityMedium',
  }[priority];
  return key ? t(key) : priority;
}

type ListViewProps = {
  tasks: PmsTask[];
  onSelectIssue: (task: PmsTask) => void;
  selectedIds?: Set<string>;
  onToggleSelect?: (taskId: string) => void;
  taskListStatuses?: PmsTaskListStatus[];
  members?: PmsTaskListMember[];
  currentUserId?: string | null;
  canEdit?: boolean;
  onCreateIssue?: (
    title: string,
    parentId: string | null,
  ) => Promise<void> | void;
  onDeleteIssue?: (taskId: string) => Promise<void> | void;
  onUpdateIssue?: (
    taskId: string,
    payload: Record<string, unknown>,
  ) => Promise<void> | void;
  onReorderIssues?: (
    updates: TaskBoardPositionUpdate[],
  ) => Promise<void> | void;
  taskContextLabel?: (task: PmsTask) => string | null;
  showToolbar?: boolean;
  groupBy?: PmsTaskListGroupBy;
  onGroupByChange?: (groupBy: PmsTaskListGroupBy) => void;
  sort?: PmsTaskSort;
  onSortChange?: (sort: PmsTaskSort) => void;
  showCompletedItems?: boolean;
  onShowCompletedItemsChange?: (showCompletedItems: boolean) => void;
  completedItemsControlDisabled?: boolean;
};

export function ListView(props: ListViewProps) {
  return useListViewContent(props);
}

function useListViewContent({
  tasks,
  onSelectIssue,
  selectedIds,
  onToggleSelect,
  taskListStatuses,
  members = EMPTY_MEMBERS,
  currentUserId,
  canEdit = false,
  onCreateIssue,
  onDeleteIssue,
  onUpdateIssue,
  onReorderIssues,
  taskContextLabel,
  showToolbar = true,
  groupBy: controlledGroupBy,
  onGroupByChange,
  sort = DEFAULT_PMS_TASK_SORT,
  onSortChange,
  showCompletedItems = false,
  onShowCompletedItemsChange,
  completedItemsControlDisabled = false,
}: ListViewProps) {
  const { t } = useTranslation('apps');
  const [internalGroupBy, setInternalGroupBy] =
    useState<PmsTaskListGroupBy>('status');
  const groupBy = controlledGroupBy ?? internalGroupBy;
  const [addTarget, setAddTarget] = useState<{
    afterTaskId?: string;
    depth: number;
    parentId: string | null;
  } | null>(null);
  const [draftTitle, setDraftTitle] = useState('');
  const [titleEditTaskId, setTitleEditTaskId] = useState<string | null>(null);
  const [titleEditDraft, setTitleEditDraft] = useState('');
  const [collapsedTaskIds, setCollapsedTaskIds] = useState<Set<string>>(
    new Set(),
  );
  const [internalSelectedIds, setInternalSelectedIds] = useState<Set<string>>(
    new Set(),
  );
  const [dragState, setDragState] = useState<{
    overTaskId: string | null;
    sourceTaskId: string;
    zone: TaskDropZone;
  } | null>(null);
  const [creating, setCreating] = useState(false);
  const [assigneeQuery, setAssigneeQuery] = useState('');
  const hierarchy = buildTaskHierarchy(tasks);
  const orderedIssues =
    sort.field === 'board_position'
      ? sortTasksByHierarchy(tasks)
      : sortTasksByHierarchyUsingInputOrder(tasks);
  const taskIdSet = useMemo(
    () => new Set(tasks.map((task) => task.id)),
    [tasks],
  );
  const effectiveCollapsedTaskIds = useMemo(() => {
    const next = new Set<string>();
    for (const taskId of collapsedTaskIds) {
      if (taskIdSet.has(taskId)) next.add(taskId);
    }
    return next;
  }, [collapsedTaskIds, taskIdSet]);
  const effectiveSelectedIds = useMemo(() => {
    if (selectedIds) return selectedIds;
    const next = new Set<string>();
    for (const taskId of internalSelectedIds) {
      if (taskIdSet.has(taskId)) next.add(taskId);
    }
    return next;
  }, [internalSelectedIds, selectedIds, taskIdSet]);
  const statusOptions = useMemo(() => {
    if (taskListStatuses && taskListStatuses.length > 0) {
      return taskListStatuses.filter((status) => status.slug !== 'backlog');
    }
    return getStatusSlugs().map((slug) => ({
      category: (slug === 'todo'
        ? 'not_started'
        : slug === 'done'
          ? 'done'
          : ['canceled', 'complete'].includes(slug)
            ? 'closed'
            : 'active') as PmsStatusCategory,
      color: '',
      created_at: '',
      id: slug,
      list_id: '',
      name: getStatusLabel(slug),
      slug,
      sort_order: 0,
    }));
  }, [taskListStatuses]);
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

  const editable = canEdit && Boolean(onUpdateIssue);
  const canReorder =
    sort.field === 'board_position' &&
    canEdit &&
    Boolean(onReorderIssues || onUpdateIssue);
  const canCreate = canEdit && Boolean(onCreateIssue);
  const canDelete = canEdit && Boolean(onDeleteIssue);

  const patchIssue = async (
    task: PmsTask,
    payload: Record<string, unknown>,
  ) => {
    if (!editable) return;
    await onUpdateIssue?.(task.id, payload);
  };

  const isHiddenByCollapsedAncestor = (task: PmsTask) => {
    let parent = hierarchy.get(task.id)?.parent ?? null;
    while (parent) {
      if (effectiveCollapsedTaskIds.has(parent.id)) return true;
      parent = hierarchy.get(parent.id)?.parent ?? null;
    }
    return false;
  };

  const visibleOrderedIssues = orderedIssues.filter(
    (task) => !isHiddenByCollapsedAncestor(task),
  );

  const rootForIssue = (task: PmsTask) => getTaskRoot(task, hierarchy);
  const isRootIssue = (task: PmsTask) => rootForIssue(task).id === task.id;
  const setGroupBy = (nextGroupBy: PmsTaskListGroupBy) => {
    if (controlledGroupBy === undefined) setInternalGroupBy(nextGroupBy);
    onGroupByChange?.(nextGroupBy);
  };
  const sortFieldLabels: Record<PmsTaskSortField, string> = {
    board_position: t('pms.list.sortManualOrder'),
    completed_date: t('pms.list.sortCompletedDate'),
    created_at: t('pms.list.sortCreatedDate'),
    due_date: t('pms.list.sortDueDate'),
    start_date: t('pms.list.sortStartDate'),
  };
  const sortDirectionLabel =
    sort.direction === 'asc'
      ? t('pms.list.sortAscending')
      : t('pms.list.sortDescending');
  const selectSortField = (field: PmsTaskSortField) => {
    if (!onSortChange) return;
    if (field === 'board_position') {
      onSortChange(DEFAULT_PMS_TASK_SORT);
      return;
    }
    const direction =
      sort.field === field
        ? sort.direction === 'asc'
          ? 'desc'
          : 'asc'
        : field === 'created_at' || field === 'completed_date'
          ? 'desc'
          : 'asc';
    onSortChange({ direction, field });
  };
  const assigneeGroups = buildAssigneeTaskGroups({
    hierarchy,
    members,
    orderedTasks: orderedIssues,
    unassignedLabel: t('pms.taskDetail.unassigned'),
    visibleTasks: visibleOrderedIssues,
  });

  const toggleIssueSelection = (taskId: string) => {
    if (onToggleSelect) {
      onToggleSelect(taskId);
      return;
    }
    setInternalSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(taskId)) next.delete(taskId);
      else next.add(taskId);
      return next;
    });
  };

  const toggleIssueCollapse = (taskId: string) => {
    setCollapsedTaskIds((current) => {
      const next = new Set(current);
      if (next.has(taskId)) next.delete(taskId);
      else next.add(taskId);
      return next;
    });
  };

  const reorderIssue = async (
    sourceTaskId: string,
    targetTaskId: string,
    zone: TaskDropZone,
  ) => {
    if (!canReorder || sourceTaskId === targetTaskId) return;
    const tasksById = new Map(tasks.map((task) => [task.id, task]));
    const updates = getTaskBoardPositionUpdates({
      groupBy,
      sourceTaskId,
      targetTaskId,
      tasks,
      zone,
    });
    if (updates.length === 0) return;

    if (onReorderIssues) {
      await onReorderIssues(updates);
      return;
    }

    await Promise.all(
      updates.map(({ boardPosition, parentId, taskId }) => {
        const task = tasksById.get(taskId);
        if (!task) return Promise.resolve();
        const payload: Record<string, unknown> = {
          board_position: boardPosition,
        };
        if (parentId !== undefined) payload.parent_id = parentId;
        return patchIssue(task, payload);
      }),
    );
  };

  const handleDragStart = (event: React.DragEvent, task: PmsTask) => {
    if (!canReorder) return;
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', task.id);
    setDragState({ overTaskId: null, sourceTaskId: task.id, zone: 'before' });
  };

  const handleDragOver = (event: React.DragEvent, task: PmsTask) => {
    if (!dragState || dragState.sourceTaskId === task.id) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const zone = dropZoneFromPointer(rect, event.clientY);
    if (
      !canDropTaskInList({
        groupBy,
        sourceTaskId: dragState.sourceTaskId,
        targetTask: task,
        tasks,
        zone,
      })
    ) {
      return;
    }
    event.preventDefault();
    setDragState((current) =>
      current && current.overTaskId === task.id && current.zone === zone
        ? current
        : { overTaskId: task.id, sourceTaskId: dragState.sourceTaskId, zone },
    );
  };

  const handleDrop = (event: React.DragEvent, task: PmsTask) => {
    event.preventDefault();
    const sourceTaskId =
      dragState?.sourceTaskId ?? event.dataTransfer.getData('text/plain');
    const zone = dragState?.overTaskId === task.id ? dragState.zone : 'before';
    setDragState(null);
    void reorderIssue(sourceTaskId, task.id, zone);
  };

  const previousSiblingForIssue = (task: PmsTask) => {
    const siblings = sortTasksByHierarchy(
      tasks.filter(
        (item) => (item.parent_id ?? null) === (task.parent_id ?? null),
      ),
      tasks,
    );
    const index = siblings.findIndex((item) => item.id === task.id);
    return index > 0 ? siblings[index - 1] : null;
  };

  const promoteIssue = (task: PmsTask) => {
    const parent = hierarchy.get(task.id)?.parent ?? null;
    if (!parent) return;
    void reorderIssue(task.id, parent.id, 'after');
  };

  const demoteIssue = (task: PmsTask) => {
    const previousSibling = previousSiblingForIssue(task);
    if (!previousSibling) return;
    void reorderIssue(task.id, previousSibling.id, 'inside');
  };

  const patchDate = (task: PmsTask, field: TaskDateField, value: string) => {
    void patchIssue(task, buildDatePatch(task, field, value));
  };

  const toggleAssignee = (task: PmsTask, userId: string) => {
    void patchIssue(task, buildToggleAssigneePatch(task, userId));
  };

  const clearAssignees = (task: PmsTask) => {
    void patchIssue(task, buildClearAssigneesPatch());
  };

  const startAdd = (
    parentId: string | null,
    depth: number,
    afterTaskId?: string,
  ) => {
    if (!canCreate) return;
    if (parentId) {
      setCollapsedTaskIds((current) => {
        if (!current.has(parentId)) return current;
        const next = new Set(current);
        next.delete(parentId);
        return next;
      });
    }
    setAddTarget({ afterTaskId, depth, parentId });
    setDraftTitle('');
  };

  const submitAdd = async () => {
    if (!canCreate || !addTarget || !draftTitle.trim()) return;
    setCreating(true);
    try {
      await onCreateIssue?.(draftTitle.trim(), addTarget.parentId);
      setAddTarget(null);
      setDraftTitle('');
    } finally {
      setCreating(false);
    }
  };

  const confirmDelete = (task: PmsTask) => {
    if (!canDelete) return;
    if (!window.confirm(t('pms.list.confirmDelete', { title: task.title })))
      return;
    void onDeleteIssue?.(task.id);
  };

  const startTitleEdit = (task: PmsTask) => {
    if (!editable) return;
    setTitleEditTaskId(task.id);
    setTitleEditDraft(task.title);
  };

  const cancelTitleEdit = () => {
    setTitleEditTaskId(null);
    setTitleEditDraft('');
  };

  const commitTitleEdit = async (task: PmsTask) => {
    if (!editable) return;
    const nextTitle = titleEditDraft.trim();
    if (nextTitle.length < 2 || nextTitle === task.title) {
      cancelTitleEdit();
      return;
    }
    cancelTitleEdit();
    await patchIssue(task, { title: nextTitle });
  };

  function getAddInput() {
    if (!addTarget) return null;
    return (
      <div
        className="flex items-center gap-2 rounded-md border border-dashed border-app-border bg-app-surface-sidebar/30 px-3 py-2"
        style={
          addTarget.depth > 0 ? { marginLeft: addTarget.depth * 18 } : undefined
        }
      >
        {addTarget.parentId ? (
          <CornerDownRight size={13} className="text-app-ink/35" />
        ) : null}
        <input
          aria-label={
            addTarget.parentId
              ? t('pms.list.addSubtaskPlaceholder')
              : t('pms.list.addTaskPlaceholder')
          }
          className="app-text-body-sm min-w-0 flex-1 bg-transparent text-app-ink outline-none placeholder:text-app-ink/35"
          disabled={creating}
          onChange={(event) => setDraftTitle(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.nativeEvent.isComposing)
              void submitAdd();
            if (event.key === 'Escape') setAddTarget(null);
          }}
          placeholder={
            addTarget.parentId
              ? t('pms.list.addSubtaskPlaceholder')
              : t('pms.list.addTaskPlaceholder')
          }
          value={draftTitle}
        />
        <Button
          disabled={!draftTitle.trim() || creating}
          onClick={() => void submitAdd()}
          size="dense"
          variant="primary"
        >
          {t('common:actions.add')}
        </Button>
        <Button onClick={() => setAddTarget(null)} size="icon" variant="ghost">
          <X size={14} />
        </Button>
      </div>
    );
  }

  function getStatusControl(task: PmsTask) {
    const label = getStatusLabel(task.status, taskListStatuses);
    if (!editable) {
      return (
        <span className="inline-flex items-center gap-2">
          <StatusIconGlyph
            label={label}
            status={task.status}
            taskListStatuses={taskListStatuses}
          />
          <span className="text-app-ink/60">{label}</span>
        </span>
      );
    }
    return (
      <InlineMenu
        trigger={({ toggle }) => (
          <button
            aria-label={label}
            className="app-text-caption inline-flex h-7 max-w-[8.5rem] items-center gap-1.5 whitespace-nowrap rounded-md border border-app-border bg-app-surface-sidebar px-2 font-semibold text-app-ink/70 transition-colors hover:bg-app-surface-hover"
            onClick={toggle}
            type="button"
          >
            <StatusIconGlyph
              label={label}
              status={task.status}
              taskListStatuses={taskListStatuses}
            />
            <span className="max-w-[7rem] truncate">{label}</span>
          </button>
        )}
      >
        {(close) => (
          <>
            {statusOptions.map((status) => {
              const statusLabel = getStatusLabel(status.slug, taskListStatuses);
              return (
                <button
                  key={status.slug}
                  className="app-text-control-sm flex w-full items-center gap-2 px-3 py-1.5 text-left text-app-ink hover:bg-app-surface-hover"
                  onClick={() => {
                    void patchIssue(task, { status: status.slug });
                    close();
                  }}
                  type="button"
                >
                  <StatusIconGlyph
                    label={statusLabel}
                    status={status.slug}
                    taskListStatuses={taskListStatuses}
                  />
                  {statusLabel}
                </button>
              );
            })}
          </>
        )}
      </InlineMenu>
    );
  }

  function getStatusIconControl(task: PmsTask) {
    const label = getStatusLabel(task.status, taskListStatuses);
    if (!editable) {
      return (
        <StatusIconGlyph
          label={label}
          status={task.status}
          taskListStatuses={taskListStatuses}
        />
      );
    }
    return (
      <InlineMenu
        trigger={({ toggle }) => (
          <StatusIconButton
            className="size-6 rounded-full"
            label={label}
            onClick={toggle}
            status={task.status}
            taskListStatuses={taskListStatuses}
          />
        )}
      >
        {(close) => (
          <>
            {statusOptions.map((status) => {
              const statusLabel = getStatusLabel(status.slug, taskListStatuses);
              return (
                <button
                  key={status.slug}
                  className="app-text-control-sm flex w-full items-center gap-2 px-3 py-1.5 text-left text-app-ink hover:bg-app-surface-hover"
                  onClick={() => {
                    void patchIssue(task, { status: status.slug });
                    close();
                  }}
                  type="button"
                >
                  <StatusIconGlyph
                    label={statusLabel}
                    status={status.slug}
                    taskListStatuses={taskListStatuses}
                  />
                  {statusLabel}
                </button>
              );
            })}
          </>
        )}
      </InlineMenu>
    );
  }

  function getAssigneeControl(task: PmsTask) {
    const selected = new Set(selectedAssigneeIds(task));
    if (!editable) {
      return selected.size > 0 ? (
        <TaskAssigneeStack
          members={members}
          sizeClassName="size-5"
          task={task}
          unassignedLabel={t('pms.taskDetail.unassigned')}
        />
      ) : (
        <User2 size={14} className="text-app-ink/30" />
      );
    }
    return (
      <InlineMenu
        trigger={({ toggle }) => (
          <button
            className="inline-flex h-7 min-w-7 items-center justify-center rounded-md border border-app-border bg-app-surface-sidebar px-1.5 text-app-ink/60 hover:bg-app-surface-hover"
            onClick={toggle}
            type="button"
          >
            {selected.size > 0 ? (
              <TaskAssigneeStack
                members={members}
                sizeClassName="size-5"
                task={task}
                unassignedLabel={t('pms.taskDetail.unassigned')}
              />
            ) : (
              <User2 size={15} />
            )}
          </button>
        )}
      >
        {() => (
          <>
            <div className="px-2 py-1">
              <div className="flex items-center gap-2 rounded-md border border-app-border bg-app-surface-sidebar px-2 py-1.5">
                <Search size={13} className="shrink-0 text-app-ink/40" />
                <input
                  aria-label={t('pms.searchUser')}
                  className="app-text-body-sm min-w-0 flex-1 bg-transparent text-app-ink outline-none placeholder:text-app-ink/35"
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
              className="app-text-control-sm w-full px-3 py-1.5 text-left text-app-ink/50 hover:bg-app-surface-hover"
              onClick={() => clearAssignees(task)}
              type="button"
            >
              {t('pms.taskDetail.unassigned')}
            </button>
            {assigneeOptions.map((member) => (
              <div key={member.user_id} className="relative">
                <input
                  aria-label={member.full_name}
                  checked={selected.has(member.user_id)}
                  className="pointer-events-none absolute right-3 top-1/2 size-3.5 -translate-y-1/2 rounded accent-app-accent"
                  readOnly
                  type="checkbox"
                />
                <UserOptionRow
                  currentUserId={currentUserId}
                  currentUserLabel={t('pms.taskDetail.me')}
                  density="compact"
                  onClick={() => toggleAssignee(task, member.user_id)}
                  selected={false}
                  user={member}
                />
              </div>
            ))}
            {assigneeOptions.length === 0 ? (
              <p className="app-text-caption px-3 py-2 text-app-ink/40">
                {t('pms.noMatchingUsers')}
              </p>
            ) : null}
          </>
        )}
      </InlineMenu>
    );
  }

  function getDateControl(task: PmsTask, field: TaskDateField) {
    const value = task[field];
    const label =
      field === 'start_date'
        ? t('pms.filter.startDateLabel')
        : field === 'due_date'
          ? t('pms.list.dueDate')
          : t('pms.taskDetail.completedDate');
    if (!editable) {
      return (
        <span className="text-app-ink/50">
          {formatDate(value) || t('pms.list.notSet')}
        </span>
      );
    }
    return (
      <InlineMenu
        trigger={({ toggle }) => (
          <button
            aria-label={label}
            className="app-text-caption inline-flex h-7 max-w-[7.75rem] items-center gap-1 whitespace-nowrap rounded-md border border-app-border bg-app-surface-sidebar px-2 text-app-ink/60 hover:bg-app-surface-hover"
            onClick={toggle}
            type="button"
          >
            <CalendarDays size={13} className="shrink-0" />
            <span className="truncate">
              {formatDate(value) || t('pms.list.notSet')}
            </span>
          </button>
        )}
      >
        {(close) => (
          <div className="space-y-2 p-3">
            <DateInput
              aria-label={label}
              className="app-text-body-sm rounded-md border border-app-border bg-app-surface-sidebar px-2 py-1 text-app-ink"
              onValueChange={(nextValue) => {
                patchDate(task, field, nextValue);
                close();
              }}
              value={value ?? ''}
            />
            {value ? (
              <button
                className="app-text-caption text-app-ink/50 hover:text-app-ink"
                onClick={() => {
                  patchDate(task, field, '');
                  close();
                }}
                type="button"
              >
                {t('common:actions.reset')}
              </button>
            ) : null}
          </div>
        )}
      </InlineMenu>
    );
  }

  function getReporterControl(task: PmsTask) {
    const reporter = taskReporterOption(task, members);
    return (
      <span
        className="inline-flex min-w-0 items-center gap-1.5"
        title={userOptionDisplayName(reporter)}
      >
        <UserOptionAvatar sizeClassName="size-5" user={reporter} />
        <span className="min-w-0 truncate text-app-ink/60">
          {userOptionDisplayName(reporter)}
        </span>
      </span>
    );
  }

  function getPriorityControl(task: PmsTask) {
    if (!editable) {
      return (
        <span
          className={`app-text-caption font-semibold ${PRIORITY_COLOR[task.priority] ?? ''}`}
        >
          {task.priority_label}
        </span>
      );
    }
    return (
      <InlineMenu
        trigger={({ toggle }) => (
          <button
            className="app-text-caption inline-flex h-7 max-w-[7.5rem] items-center gap-1 whitespace-nowrap rounded-md border border-app-border bg-app-surface-sidebar px-2 font-semibold hover:bg-app-surface-hover"
            onClick={toggle}
            type="button"
          >
            <Flag
              size={13}
              className={`shrink-0 ${PRIORITY_COLOR[task.priority] ?? 'text-app-ink/40'}`}
            />
            <span className="truncate text-app-ink/60">
              {task.priority_label}
            </span>
          </button>
        )}
      >
        {(close) => (
          <>
            {PRIORITY_OPTIONS.map((priority) => (
              <button
                key={priority}
                className="app-text-control-sm flex w-full items-center gap-2 px-3 py-1.5 text-left text-app-ink hover:bg-app-surface-hover"
                onClick={() => {
                  void patchIssue(task, { priority });
                  close();
                }}
                type="button"
              >
                <Flag size={13} className={PRIORITY_COLOR[priority]} />
                {priorityLabel(priority, t)}
              </button>
            ))}
          </>
        )}
      </InlineMenu>
    );
  }

  function getMobileIssue(task: PmsTask) {
    const issueHierarchy = hierarchy.get(task.id);
    const depth = issueHierarchy?.depth ?? 0;
    const addOpen = addTarget?.afterTaskId === task.id;

    return (
      <div key={task.id} className="space-y-2">
        <TaskCard
          childCount={issueHierarchy?.childCount ?? 0}
          collapseSubtasksLabel={t('pms.list.collapseSubtasks')}
          collapsed={effectiveCollapsedTaskIds.has(task.id)}
          completedDateLabel={t('pms.taskDetail.completedDate')}
          depth={depth}
          expandSubtasksLabel={t('pms.list.expandSubtasks')}
          contextLabel={taskContextLabel?.(task) ?? null}
          members={members}
          task={task}
          onSelectIssue={onSelectIssue}
          onToggleCollapse={toggleIssueCollapse}
          onToggleSelect={toggleIssueSelection}
          selectTaskLabel={(reference) =>
            t('pms.list.selectIssue', { reference })
          }
          selected={effectiveSelectedIds.has(task.id)}
          taskListStatuses={taskListStatuses}
          unassignedLabel={t('pms.taskDetail.unassigned')}
          viewDetailsLabel={(reference) =>
            t('pms.list.viewDetails', { reference })
          }
        />
        {editable || canCreate || canDelete ? (
          <div className="flex justify-end gap-1">
            {getQuickAddSubtaskButton(task, depth, 'label')}
            {getIssueActionsMenu(task, depth)}
          </div>
        ) : null}
        {addOpen ? getAddInput() : null}
      </div>
    );
  }

  function getViewDetailsButton(task: PmsTask) {
    const label = t('pms.list.viewDetails', { reference: task.reference });
    return (
      <button
        aria-label={label}
        className="inline-flex size-7 items-center justify-center rounded-md border border-transparent text-app-ink/50 opacity-0 transition-opacity hover:border-app-border hover:bg-app-surface-sidebar hover:text-app-accent focus:border-app-border focus:bg-app-surface-sidebar focus:text-app-accent focus:opacity-100 focus-visible:opacity-100 group-hover:opacity-100"
        onClick={(event) => {
          event.stopPropagation();
          onSelectIssue(task);
        }}
        title={label}
        type="button"
      >
        <Eye size={15} />
      </button>
    );
  }

  function getQuickAddSubtaskButton(
    task: PmsTask,
    depth: number,
    variant: 'icon' | 'label' = 'icon',
  ) {
    if (!canCreate) return null;
    const label = `${t('pms.list.addSubtask')}: ${task.title}`;
    return (
      <button
        aria-label={label}
        className={
          variant === 'label'
            ? 'app-text-caption inline-flex h-7 items-center gap-1 rounded-md border border-app-border bg-app-surface-sidebar px-2 text-app-ink/60 hover:bg-app-surface-hover hover:text-app-accent'
            : 'inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-app-ink/35 opacity-0 transition-opacity hover:bg-app-surface-hover hover:text-app-accent focus:opacity-100 focus-visible:opacity-100 group-hover:opacity-100'
        }
        onClick={(event) => {
          event.stopPropagation();
          startAdd(task.id, depth + 1, task.id);
        }}
        title={t('pms.list.addSubtask')}
        type="button"
      >
        <Plus size={variant === 'label' ? 13 : 14} />
        {variant === 'label' ? <span>{t('pms.list.addSubtask')}</span> : null}
      </button>
    );
  }

  function getIssueActionsMenu(task: PmsTask, depth: number) {
    if (!editable && !canCreate && !canDelete) return null;
    const parent = hierarchy.get(task.id)?.parent ?? null;
    const previousSibling = previousSiblingForIssue(task);
    return (
      <InlineMenu
        trigger={({ toggle }) => (
          <button
            aria-label={t('pms.table.actions')}
            className="inline-flex size-7 items-center justify-center rounded-md border border-transparent text-app-ink/50 hover:border-app-border hover:bg-app-surface-sidebar hover:text-app-ink"
            onClick={toggle}
            title={t('pms.table.actions')}
            type="button"
          >
            <Ellipsis size={16} />
          </button>
        )}
      >
        {(close) => (
          <>
            <button
              className={LIST_ACTION_MENU_ITEM_CLASS}
              onClick={() => {
                onSelectIssue(task);
                close();
              }}
              type="button"
            >
              <Eye size={14} className="text-app-ink/45" />
              <span>{t('common:actions.open')}</span>
            </button>
            {editable ? (
              <button
                className={LIST_ACTION_MENU_ITEM_CLASS}
                onClick={() => {
                  startTitleEdit(task);
                  close();
                }}
                type="button"
              >
                <Pencil size={14} className="text-app-ink/45" />
                <span>{t('common:actions.rename')}</span>
              </button>
            ) : null}
            {canCreate ? (
              <button
                className={LIST_ACTION_MENU_ITEM_CLASS}
                onClick={() => {
                  startAdd(task.id, depth + 1, task.id);
                  close();
                }}
                type="button"
              >
                <Plus size={14} className="text-app-ink/45" />
                <span>{t('pms.list.addSubtask')}</span>
              </button>
            ) : null}
            {editable && parent ? (
              <button
                className={LIST_ACTION_MENU_ITEM_CLASS}
                onClick={() => {
                  promoteIssue(task);
                  close();
                }}
                type="button"
              >
                <Outdent size={14} className="text-app-ink/45" />
                <span>{t('pms.list.moveToParentLevel')}</span>
              </button>
            ) : null}
            {editable && previousSibling ? (
              <button
                className={LIST_ACTION_MENU_ITEM_CLASS}
                onClick={() => {
                  demoteIssue(task);
                  close();
                }}
                type="button"
              >
                <Indent size={14} className="text-app-ink/45" />
                <span>{t('pms.list.moveUnderPreviousTask')}</span>
              </button>
            ) : null}
            {canDelete ? (
              <button
                className={`${LIST_ACTION_MENU_ITEM_CLASS} text-app-danger hover:bg-app-danger/10`}
                onClick={() => {
                  close();
                  confirmDelete(task);
                }}
                type="button"
              >
                <Trash2 size={14} />
                <span>{t('common:actions.delete')}</span>
              </button>
            ) : null}
          </>
        )}
      </InlineMenu>
    );
  }

  function getAddTableRow(parentId: string | null) {
    if (!addTarget || addTarget.parentId !== parentId) return null;
    const defaultStatus = getDefaultTaskStatus(taskListStatuses);
    const defaultStatusLabel = getStatusLabel(defaultStatus, taskListStatuses);
    return (
      <tr className="bg-app-surface-sidebar/25">
        <td
          aria-label={t('pms.bulk.selectAll', { count: 0 })}
          className="px-4 py-2"
        />
        <td className="px-4 py-2">
          <div
            className="flex min-w-0 items-center gap-2"
            style={
              addTarget.depth > 0
                ? { paddingLeft: addTarget.depth * 18 }
                : undefined
            }
          >
            {addTarget.parentId ? (
              <CornerDownRight size={13} className="shrink-0 text-app-ink/35" />
            ) : null}
            <StatusIconGlyph
              label={defaultStatusLabel}
              status={defaultStatus}
              taskListStatuses={taskListStatuses}
            />
            <input
              aria-label={
                addTarget.parentId
                  ? t('pms.list.addSubtaskPlaceholder')
                  : t('pms.list.addTaskPlaceholder')
              }
              className="app-text-body-sm min-w-0 flex-1 bg-transparent text-app-ink outline-none placeholder:text-app-ink/35"
              disabled={creating}
              onChange={(event) => setDraftTitle(event.target.value)}
              onClick={(event) => event.stopPropagation()}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.nativeEvent.isComposing)
                  void submitAdd();
                if (event.key === 'Escape') setAddTarget(null);
              }}
              placeholder={
                addTarget.parentId
                  ? t('pms.list.addSubtaskPlaceholder')
                  : t('pms.list.addTaskPlaceholder')
              }
              value={draftTitle}
            />
          </div>
        </td>
        <td aria-label={t('pms.list.status')} colSpan={8} />
        <td className="px-4 py-2 text-right">
          <div className="inline-flex items-center gap-1">
            <Button
              onClick={() => setAddTarget(null)}
              size="dense"
              variant="ghost"
            >
              {t('common:actions.cancel')}
            </Button>
            <Button
              disabled={!draftTitle.trim() || creating}
              onClick={() => void submitAdd()}
              size="dense"
              variant="primary"
            >
              {t('common:actions.save')}
            </Button>
          </div>
        </td>
      </tr>
    );
  }

  function getDesktopTable(rows: PmsTask[], showRootAdd = false) {
    const rootAddOpen =
      showRootAdd && addTarget?.parentId === null && !addTarget.afterTaskId;
    return (
      <div className="hidden rounded-lg border border-app-border bg-app-surface-sidebar/20 lg:block">
        <table
          className="app-text-body-sm min-w-[1480px] table-fixed text-left"
          data-testid="desktop-task-table"
        >
          <colgroup>
            <col className="w-16" />
            <col className="w-[25rem]" />
            <col className="w-[5.5rem]" />
            <col className="w-44" />
            <col className="w-[7.5rem]" />
            <col className="w-[7.5rem]" />
            <col className="w-[7.5rem]" />
            <col className="w-28" />
            <col className="w-36" />
            <col className="w-24" />
            <col className="w-14" />
          </colgroup>
          <thead>
            <tr className="app-text-overline border-b border-app-border bg-app-surface-sidebar/50 text-app-ink/50">
              <th className="p-2">
                <span className="sr-only">
                  {t('pms.bulk.selectAll', { count: rows.length })}
                </span>
              </th>
              <th className="px-4 py-2 whitespace-nowrap">
                {t('pms.list.name')}
              </th>
              <th className="px-4 py-2 whitespace-nowrap">
                {t('pms.list.assignee')}
              </th>
              <th className="px-4 py-2 whitespace-nowrap">
                {t('pms.list.reporter')}
              </th>
              <th className="px-4 py-2 whitespace-nowrap">
                {t('pms.filter.startDateLabel')}
              </th>
              <th className="px-4 py-2 whitespace-nowrap">
                {t('pms.list.dueDate')}
              </th>
              <th className="px-4 py-2 whitespace-nowrap">
                {t('pms.taskDetail.completedDate')}
              </th>
              <th className="px-4 py-2 whitespace-nowrap">
                {t('pms.list.priority')}
              </th>
              <th className="px-4 py-2 whitespace-nowrap">
                {t('pms.list.status')}
              </th>
              <th className="px-4 py-2 whitespace-nowrap">
                {t('pms.list.comments')}
              </th>
              <th className="sticky right-0 z-10 border-l border-app-border bg-app-surface-sidebar p-2 text-right">
                {canCreate ? (
                  <button
                    aria-label={t('pms.list.addTask')}
                    className="inline-flex size-7 items-center justify-center rounded-md text-app-ink/50 hover:bg-app-surface-hover hover:text-app-accent"
                    onClick={(event) => {
                      event.stopPropagation();
                      startAdd(null, 0);
                    }}
                    type="button"
                  >
                    <Plus size={15} />
                  </button>
                ) : null}
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-app-border">
            {rootAddOpen ? getAddTableRow(null) : null}
            {rows.map((task) => {
              const issueHierarchy = hierarchy.get(task.id);
              const depth = Math.min(issueHierarchy?.depth ?? 0, 5);
              const addOpen = addTarget?.afterTaskId === task.id;
              const childCount = issueHierarchy?.childCount ?? 0;
              const collapsed = effectiveCollapsedTaskIds.has(task.id);
              const contextLabel = taskContextLabel?.(task) ?? null;
              const dropZone =
                dragState?.overTaskId === task.id ? dragState.zone : null;

              return (
                <Fragment key={task.id}>
                  <tr
                    draggable={false}
                    onDragEnd={() => setDragState(null)}
                    onDragOver={(event) => handleDragOver(event, task)}
                    onDrop={(event) => handleDrop(event, task)}
                    onClick={() => onSelectIssue(task)}
                    className={`group cursor-pointer transition-colors hover:bg-app-surface-hover ${
                      dragState?.sourceTaskId === task.id ? 'opacity-50' : ''
                    } ${
                      dropZone === 'before'
                        ? 'border-t-2 border-app-accent'
                        : dropZone === 'after'
                          ? 'border-b-2 border-app-accent'
                          : dropZone === 'inside'
                            ? 'bg-app-accent/5 outline outline-2 -outline-offset-2 outline-app-accent/60'
                            : ''
                    }`}
                  >
                    <td className="p-2">
                      <div className="flex items-center gap-1">
                        <button
                          aria-label={t('pms.list.dragToReorder')}
                          className={`inline-flex h-6 w-4 shrink-0 items-center justify-center rounded text-app-ink/30 ${
                            canReorder
                              ? 'cursor-grab hover:bg-app-surface-hover hover:text-app-ink active:cursor-grabbing'
                              : 'cursor-not-allowed opacity-40'
                          }`}
                          draggable={canReorder}
                          onClick={(event) => event.stopPropagation()}
                          onDragStart={(event) => handleDragStart(event, task)}
                          title={t('pms.list.dragToReorder')}
                          type="button"
                        >
                          <GripVertical size={13} />
                        </button>
                        <input
                          aria-label={t('pms.list.selectIssue', {
                            reference: task.reference,
                          })}
                          type="checkbox"
                          checked={effectiveSelectedIds.has(task.id)}
                          onChange={(event) => {
                            event.stopPropagation();
                            toggleIssueSelection(task.id);
                          }}
                          onClick={(event) => event.stopPropagation()}
                          className="size-3.5 cursor-pointer rounded accent-app-accent"
                        />
                      </div>
                    </td>
                    <td className="px-4 py-2">
                      <div
                        className="flex min-w-0 flex-col gap-0.5"
                        style={
                          depth > 0 ? { paddingLeft: depth * 18 } : undefined
                        }
                      >
                        <div className="flex min-w-0 items-center gap-2">
                          {depth > 0 ? (
                            <CornerDownRight
                              size={13}
                              className="shrink-0 text-app-ink/35"
                            />
                          ) : null}
                          {childCount > 0 ? (
                            <button
                              aria-label={
                                collapsed
                                  ? t('pms.list.expandSubtasks')
                                  : t('pms.list.collapseSubtasks')
                              }
                              className="inline-flex size-5 shrink-0 items-center justify-center rounded text-app-ink/45 hover:bg-app-surface-hover hover:text-app-ink"
                              data-testid="task-subtask-toggle-slot"
                              onClick={(event) => {
                                event.stopPropagation();
                                toggleIssueCollapse(task.id);
                              }}
                              title={
                                collapsed
                                  ? t('pms.list.expandSubtasks')
                                  : t('pms.list.collapseSubtasks')
                              }
                              type="button"
                            >
                              {collapsed ? (
                                <ChevronRight size={13} />
                              ) : (
                                <ChevronDown size={13} />
                              )}
                            </button>
                          ) : (
                            <span
                              aria-hidden="true"
                              className="size-5 shrink-0"
                              data-testid="task-subtask-toggle-slot"
                            />
                          )}
                          {getStatusIconControl(task)}
                          {titleEditTaskId === task.id ? (
                            <input
                              aria-label={t('pms.list.name')}
                              autoFocus
                              className="app-text-body-sm min-w-0 flex-1 rounded border border-app-accent bg-app-bg px-1.5 py-0.5 font-medium text-app-ink outline-none"
                              maxLength={180}
                              onBlur={() => {
                                void commitTitleEdit(task);
                              }}
                              onChange={(event) =>
                                setTitleEditDraft(event.target.value)
                              }
                              onClick={(event) => event.stopPropagation()}
                              onKeyDown={(event) => {
                                if (
                                  event.key === 'Enter' &&
                                  !event.nativeEvent.isComposing
                                ) {
                                  event.preventDefault();
                                  event.currentTarget.blur();
                                }
                                if (event.key === 'Escape') {
                                  event.preventDefault();
                                  cancelTitleEdit();
                                }
                              }}
                              value={titleEditDraft}
                            />
                          ) : (
                            <button
                              className="min-w-0 flex-1 truncate text-left font-medium text-app-ink hover:text-app-accent"
                              onClick={(event) => {
                                event.stopPropagation();
                                if (editable) startTitleEdit(task);
                                else onSelectIssue(task);
                              }}
                              title={task.title}
                              type="button"
                            >
                              {task.title}
                            </button>
                          )}
                          {childCount > 0 ? (
                            <span className="app-text-micro inline-flex items-center gap-1 text-app-ink/35">
                              <GitBranch size={11} />
                              {childCount}
                            </span>
                          ) : null}
                          {getQuickAddSubtaskButton(task, depth)}
                        </div>
                        {contextLabel ? (
                          <p className="app-text-caption truncate text-app-ink/45">
                            {contextLabel}
                          </p>
                        ) : null}
                      </div>
                    </td>
                    <td className="px-4 py-2 whitespace-nowrap">
                      {getAssigneeControl(task)}
                    </td>
                    <td className="px-4 py-2 whitespace-nowrap">
                      {getReporterControl(task)}
                    </td>
                    <td className="px-4 py-2 whitespace-nowrap">
                      {getDateControl(task, 'start_date')}
                    </td>
                    <td className="px-4 py-2 whitespace-nowrap">
                      {getDateControl(task, 'due_date')}
                    </td>
                    <td className="px-4 py-2 whitespace-nowrap text-app-ink/50">
                      {getDateControl(task, 'completed_date')}
                    </td>
                    <td className="px-4 py-2 whitespace-nowrap">
                      {getPriorityControl(task)}
                    </td>
                    <td className="px-4 py-2 whitespace-nowrap">
                      {getStatusControl(task)}
                    </td>
                    <td className="px-4 py-2 whitespace-nowrap">
                      <span className="text-app-ink/40">
                        {task.comments_count}
                      </span>
                      {task.checklist_total > 0 ? (
                        <span className="app-text-caption ml-2 inline-flex items-center gap-0.5 text-app-ink/40">
                          <CheckSquare size={11} />
                          <span>
                            {task.checklist_done}/{task.checklist_total}
                          </span>
                        </span>
                      ) : null}
                    </td>
                    <td className="sticky right-0 z-10 border-l border-app-border bg-app-surface p-2 text-right transition-colors group-hover:bg-app-surface-hover">
                      <div className="inline-flex items-center justify-end gap-1">
                        {getViewDetailsButton(task)}
                        {getIssueActionsMenu(task, depth)}
                      </div>
                    </td>
                  </tr>
                  {addOpen ? getAddTableRow(task.id) : null}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col gap-5 lg:gap-8">
      {showToolbar ? (
        <div className="app-text-control-sm flex shrink-0 items-center gap-2 overflow-x-auto rounded-md border border-app-border bg-app-surface-sidebar/30 p-2 text-app-ink/60">
          <Button
            aria-pressed={groupBy === 'status'}
            variant={groupBy === 'status' ? 'subtle' : 'ghost'}
            size="dense"
            className="gap-1"
            onClick={() => setGroupBy(groupBy === 'status' ? 'none' : 'status')}
          >
            <Activity size={14} />
            {t('pms.list.groupStatus')}
          </Button>
          <Button
            aria-pressed={groupBy === 'assignee'}
            variant={groupBy === 'assignee' ? 'subtle' : 'ghost'}
            size="dense"
            className="gap-1"
            onClick={() =>
              setGroupBy(groupBy === 'assignee' ? 'none' : 'assignee')
            }
          >
            <User2 size={14} />
            {t('pms.list.groupUser')}
          </Button>
          {onSortChange ? (
            <>
              <span className="h-5 w-px shrink-0 bg-app-border" />
              <InlineMenu
                trigger={({ toggle }) => (
                  <Button
                    aria-label={t('pms.list.sortBy', {
                      field: sortFieldLabels[sort.field],
                    })}
                    variant={
                      sort.field === 'board_position' ? 'ghost' : 'subtle'
                    }
                    size="dense"
                    className="gap-1"
                    onClick={toggle}
                  >
                    <ArrowUpDown size={14} />
                    {t('pms.list.sortBy', {
                      field: sortFieldLabels[sort.field],
                    })}
                    {sort.field === 'board_position' ? null : sort.direction ===
                      'asc' ? (
                      <ArrowUp size={13} />
                    ) : (
                      <ArrowDown size={13} />
                    )}
                  </Button>
                )}
              >
                {(close) => (
                  <>
                    {TASK_SORT_FIELDS.map((field) => {
                      const selected = sort.field === field;
                      return (
                        <button
                          key={field}
                          type="button"
                          className={LIST_ACTION_MENU_ITEM_CLASS}
                          onClick={() => {
                            selectSortField(field);
                            close();
                          }}
                        >
                          <Check
                            size={14}
                            className={selected ? 'opacity-100' : 'opacity-0'}
                          />
                          <span>{sortFieldLabels[field]}</span>
                          {selected && field !== 'board_position' ? (
                            <span className="ml-auto text-app-ink/45">
                              {sortDirectionLabel}
                            </span>
                          ) : null}
                        </button>
                      );
                    })}
                  </>
                )}
              </InlineMenu>
              {sort.field !== 'board_position' ? (
                <Button
                  variant="ghost"
                  size="dense"
                  className="gap-1"
                  onClick={() => onSortChange(DEFAULT_PMS_TASK_SORT)}
                >
                  <RotateCcw size={14} />
                  {t('pms.list.resetSort')}
                </Button>
              ) : null}
            </>
          ) : null}
          {onShowCompletedItemsChange ? (
            <>
              <span className="h-5 w-px shrink-0 bg-app-border" />
              <label
                className={`flex h-7 shrink-0 items-center gap-2 rounded px-2 transition-colors ${
                  completedItemsControlDisabled
                    ? 'cursor-not-allowed opacity-50'
                    : 'cursor-pointer hover:bg-app-surface-hover hover:text-app-ink'
                }`}
              >
                <input
                  type="checkbox"
                  checked={showCompletedItems}
                  disabled={completedItemsControlDisabled}
                  onChange={(event) =>
                    onShowCompletedItemsChange(event.target.checked)
                  }
                  className="size-3.5 rounded accent-app-accent"
                />
                {t('pms.list.showCompletedItems')}
              </label>
            </>
          ) : null}
        </div>
      ) : null}

      <div
        className="custom-scrollbar min-h-0 min-w-0 flex-1 space-y-5 overflow-auto lg:space-y-8"
        data-testid="task-list-scroll-region"
      >
        {groupBy === 'none' ? (
          <>
            <div className="space-y-2 lg:hidden">
              {addTarget?.parentId === null && !addTarget.afterTaskId
                ? getAddInput()
                : null}
              {visibleOrderedIssues.map((task) => getMobileIssue(task))}
            </div>
            {getDesktopTable(visibleOrderedIssues, true)}
          </>
        ) : groupBy === 'status' ? (
          <>
            {addTarget?.parentId === null && !addTarget.afterTaskId
              ? getAddInput()
              : null}
            {statusOptions.map(({ slug: status }) => {
              const statusRootIssues = orderedIssues.filter(
                (task) => isRootIssue(task) && task.status === status,
              );
              const statusIssues = visibleOrderedIssues.filter(
                (task) => rootForIssue(task).status === status,
              );
              if (statusRootIssues.length === 0) return null;
              const statusLabel = getStatusLabel(status, taskListStatuses);

              return (
                <div key={status} className="space-y-2">
                  <div className="flex items-center gap-2 px-2 py-1">
                    <ChevronDown size={14} className="text-app-ink/50" />
                    <span className="inline-flex items-center gap-2 rounded-md border border-app-border bg-app-surface-sidebar px-2 py-1">
                      <StatusIconGlyph
                        label={statusLabel}
                        status={status}
                        taskListStatuses={taskListStatuses}
                      />
                      <span
                        className={`app-text-caption font-semibold ${getStatusTone(status, taskListStatuses) === 'success' ? 'text-app-success' : 'text-app-ink/70'}`}
                      >
                        {statusLabel}
                      </span>
                    </span>
                    <span className="app-text-label text-app-ink/40">
                      {statusRootIssues.length}
                    </span>
                  </div>

                  <div className="space-y-2 lg:hidden">
                    {statusIssues.map((task) => getMobileIssue(task))}
                  </div>

                  {getDesktopTable(statusIssues)}
                </div>
              );
            })}
          </>
        ) : (
          <>
            {addTarget?.parentId === null && !addTarget.afterTaskId
              ? getAddInput()
              : null}
            {assigneeGroups.map((group) => (
              <div
                key={group.key}
                className="space-y-2"
                data-testid={`assignee-task-group-${group.assigneeIds.length > 0 ? group.assigneeIds.join('--') : 'unassigned'}`}
              >
                <div className="flex items-center gap-2 px-2 py-1">
                  <ChevronDown size={14} className="text-app-ink/50" />
                  <span className="inline-flex items-center gap-2 rounded-md border border-app-border bg-app-surface-sidebar px-2 py-1">
                    <User2 size={14} className="text-app-ink/55" />
                    <span className="app-text-caption font-semibold text-app-ink/70">
                      {group.label}
                    </span>
                  </span>
                  <span className="app-text-label text-app-ink/40">
                    {group.rootCount}
                  </span>
                </div>

                <div className="space-y-2 lg:hidden">
                  {group.issues.map((task) => getMobileIssue(task))}
                </div>

                {getDesktopTable(group.issues)}
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  );
}
