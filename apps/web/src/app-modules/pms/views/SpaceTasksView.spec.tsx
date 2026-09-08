import type { ReactNode } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type {
  PmsTask,
  PmsTaskList,
  PmsTaskListGroupBy,
  PmsTaskSort,
  TaskFilterParams,
} from '../api/pms-api';
import { SpaceTasksView } from './SpaceTasksView';
import type { PmsTaskListToolTab } from './pms-view-route';

const mocks = vi.hoisted(() => ({
  getTaskDetail: vi.fn(),
  listAllPmsTaskLists: vi.fn(),
  listAllTaskListTasks: vi.fn(),
  listSpaceMembers: vi.fn(),
  listTaskListLabels: vi.fn(),
  listTaskListMilestones: vi.fn(),
  listTaskListStatuses: vi.fn(),
  reorderTaskListTasks: vi.fn(),
  updateTask: vi.fn(),
}));

vi.mock('@/src/platform/auth/auth-provider', () => ({
  useAuth: () => ({ token: 'token', user: { id: 'user-1' } }),
}));

vi.mock('../api/pms-api', async () => {
  const actual =
    await vi.importActual<typeof import('../api/pms-api')>('../api/pms-api');
  return {
    ...actual,
    getTaskDetail: mocks.getTaskDetail,
    listAllPmsTaskLists: mocks.listAllPmsTaskLists,
    listAllTaskListTasks: mocks.listAllTaskListTasks,
    listSpaceMembers: mocks.listSpaceMembers,
    listTaskListLabels: mocks.listTaskListLabels,
    listTaskListMilestones: mocks.listTaskListMilestones,
    listTaskListStatuses: mocks.listTaskListStatuses,
    reorderTaskListTasks: mocks.reorderTaskListTasks,
    updateTask: mocks.updateTask,
  };
});

vi.mock('./FilterBar', () => ({
  FilterBar: ({
    filterParams,
    setFilterParams,
  }: {
    filterParams: TaskFilterParams;
    setFilterParams: (params: TaskFilterParams) => void;
  }) => (
    <div>
      <span data-testid="filter-query">{filterParams.q ?? ''}</span>
      <button
        data-testid="filter-set-query"
        onClick={() =>
          setFilterParams({ ...filterParams, q: 'space-a-filter' })
        }
        type="button"
      >
        set query
      </button>
    </div>
  ),
}));
vi.mock('./usePmsTaskListChangeSubscription', () => ({
  usePmsTaskListChangeSubscription: () => undefined,
}));

vi.mock('./ListView', () => ({
  ListView: ({
    groupBy,
    onReorderIssues,
    sort,
    tasks,
  }: {
    groupBy?: PmsTaskListGroupBy;
    onReorderIssues?: (
      updates: Array<{
        boardPosition: number;
        parentId?: string | null;
        taskId: string;
      }>,
    ) => Promise<void> | void;
    sort?: PmsTaskSort;
    tasks: PmsTask[];
  }) => (
    <>
      <div
        data-group-by={groupBy}
        data-sort-direction={sort?.direction}
        data-sort-field={sort?.field}
        data-testid="list-view"
      >
        {tasks.map((task) => task.id).join(',')}
      </div>
      <span data-testid={`list-position-${tasks[0]?.list_id}`}>
        {tasks[0]?.board_position ?? 'unset'}
      </span>
      <button
        data-testid={`list-reorder-${tasks[0]?.list_id}`}
        onClick={() =>
          onReorderIssues?.(
            tasks.map((task, index) => ({
              boardPosition: 7 + index,
              parentId: null,
              taskId: task.id,
            })),
          )
        }
        type="button"
      >
        reorder
      </button>
    </>
  ),
}));
vi.mock('./BoardView', () => ({
  BoardView: ({
    tasks,
    onSelectIssue,
    onUpdateIssue,
  }: {
    tasks: PmsTask[];
    onSelectIssue: (task: PmsTask) => void;
    onUpdateIssue?: (taskId: string, payload: Record<string, unknown>) => void;
  }) => (
    <div>
      <div data-testid="board-view">
        {tasks.map((task) => task.id).join(',')}
      </div>
      <button
        data-testid={`board-select-${tasks[0]?.list_id}`}
        onClick={() => tasks[0] && onSelectIssue(tasks[0])}
        type="button"
      >
        select task
      </button>
      <button
        data-testid={`board-update-own-${tasks[0]?.list_id}`}
        onClick={() => onUpdateIssue?.(tasks[0]?.id ?? '', { status: 'open' })}
        type="button"
      >
        update own
      </button>
      <button
        data-testid={`board-update-foreign-${tasks[0]?.list_id}`}
        onClick={() => onUpdateIssue?.('task-list-a', { status: 'open' })}
        type="button"
      >
        update foreign
      </button>
    </div>
  ),
}));
vi.mock('./TaskDetail', () => ({
  TaskDetail: ({ task }: { task: PmsTask }) => (
    <div data-testid="task-detail">{task.id}</div>
  ),
}));
vi.mock('./TaskDetailModal', () => ({
  TaskDetailModal: ({ children }: { children: ReactNode }) => (
    <div>{children}</div>
  ),
}));
vi.mock('./CalendarView', () => ({
  CalendarView: ({ tasks }: { tasks: PmsTask[] }) => (
    <div data-testid="calendar-view">
      {tasks.map((task) => task.id).join(',')}
    </div>
  ),
}));
vi.mock('./GanttView', () => ({
  GanttView: ({ tasks }: { tasks: PmsTask[] }) => (
    <div data-testid="gantt-view">{tasks.map((task) => task.id).join(',')}</div>
  ),
}));
vi.mock('./TableView', () => ({
  TableView: ({ tasks }: { tasks: PmsTask[] }) => (
    <div data-testid="table-view">{tasks.map((task) => task.id).join(',')}</div>
  ),
}));

const list = (overrides: Partial<PmsTaskList>): PmsTaskList =>
  ({
    archived: false,
    folder_id: null,
    folder_name: null,
    id: 'list-1',
    name: 'List',
    role: 'admin',
    sort_order: 0,
    team_id: 'space-1',
    team_name: 'Space One',
    updated_at: '2026-07-17T00:00:00Z',
    ...overrides,
  }) as PmsTaskList;

const task = (listId: string): PmsTask =>
  ({
    id: `task-${listId}`,
    list_id: listId,
    status: 'open',
    title: `Task ${listId}`,
  }) as PmsTask;

describe('SpaceTasksView', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.listAllPmsTaskLists.mockResolvedValue({
      items: [
        list({ id: 'list-a', name: 'List A', sort_order: 1 }),
        list({ id: 'list-b', name: 'List B', sort_order: 2 }),
        list({ archived: true, id: 'list-archived' }),
        list({ id: 'list-other', team_id: 'space-2' }),
      ],
      page: 1,
      page_size: 100,
      total: 4,
    });
    mocks.listSpaceMembers.mockResolvedValue({
      items: [],
      page: 1,
      page_size: 20,
      total: 0,
    });
    mocks.listTaskListStatuses.mockResolvedValue({
      items: [{ category: 'active', name: 'Open', slug: 'open' }],
      mode: 'inherit',
      source: 'space',
    });
    mocks.listTaskListLabels.mockResolvedValue({ items: [] });
    mocks.listTaskListMilestones.mockResolvedValue({ items: [] });
    mocks.reorderTaskListTasks.mockImplementation(
      (
        _token: string,
        listId: string,
        payload: { items: Array<{ board_position: number; task_id: string }> },
      ) =>
        Promise.resolve({
          items: payload.items.map((item) => ({
            ...task(listId),
            board_position: item.board_position,
            id: item.task_id,
          })),
        }),
    );
    mocks.listAllTaskListTasks.mockImplementation(
      (_token: string, listId: string) =>
        Promise.resolve({ items: [task(listId)] }),
    );
    mocks.updateTask.mockImplementation(
      (_token: string, taskId: string, payload: Record<string, unknown>) =>
        Promise.resolve({
          ...task(taskId.replace(/^task-/, '')),
          ...payload,
          id: taskId,
        }),
    );
    mocks.getTaskDetail.mockImplementation((_token: string, taskId: string) =>
      Promise.resolve({ task: task(taskId.replace(/^task-/, '')) }),
    );
  });

  it.each([
    ['list', 'list-view'],
    ['board', 'board-view'],
    ['calendar', 'calendar-view'],
    ['gantt', 'gantt-view'],
    ['table', 'table-view'],
  ] as const)(
    'renders every active list in the space %s view',
    async (activeTab, testId) => {
      renderSpaceTasksView(activeTab);

      await waitFor(() =>
        expect(screen.getAllByTestId(testId)).toHaveLength(2),
      );
      expect(
        screen.getAllByTestId(testId).map((node) => node.textContent),
      ).toEqual(['task-list-a', 'task-list-b']);
      expect(mocks.listAllPmsTaskLists).toHaveBeenCalledWith(
        'token',
        'space-1',
      );
      expect(
        mocks.listTaskListStatuses.mock.calls.map((call) => call[1]),
      ).toEqual(['list-a', 'list-b']);
      expect(screen.queryByText('list-archived')).toBeNull();
      expect(screen.queryByText('list-other')).toBeNull();
    },
  );

  it('renders the space list view ungrouped in custom task order', async () => {
    renderSpaceTasksView('list');

    const listViews = await screen.findAllByTestId('list-view');
    expect(listViews).toHaveLength(2);
    for (const listView of listViews) {
      expect(listView.getAttribute('data-group-by')).toBe('none');
      expect(listView.getAttribute('data-sort-field')).toBe('board_position');
      expect(listView.getAttribute('data-sort-direction')).toBe('asc');
    }
  });

  it('reorders multiple tasks with one batch request and no list refetch', async () => {
    mocks.listAllTaskListTasks.mockImplementation(
      (_token: string, listId: string) =>
        Promise.resolve({
          items:
            listId === 'list-b'
              ? [
                  { ...task(listId), board_position: 1 },
                  {
                    ...task(listId),
                    board_position: 2,
                    id: 'task-list-b-2',
                    title: 'Task list-b 2',
                  },
                ]
              : [task(listId)],
        }),
    );
    renderSpaceTasksView('list');

    await screen.findByTestId('list-reorder-list-b');
    fireEvent.click(screen.getByTestId('list-reorder-list-b'));

    await waitFor(() =>
      expect(mocks.reorderTaskListTasks).toHaveBeenCalledWith(
        'token',
        'list-b',
        {
          items: [
            {
              board_position: 7,
              parent_id: null,
              task_id: 'task-list-b',
            },
            {
              board_position: 8,
              parent_id: null,
              task_id: 'task-list-b-2',
            },
          ],
        },
      ),
    );
    expect(mocks.reorderTaskListTasks).toHaveBeenCalledTimes(1);
    expect(mocks.updateTask).not.toHaveBeenCalled();
    expect(mocks.listAllTaskListTasks).toHaveBeenCalledTimes(2);
    await waitFor(() =>
      expect(screen.getByTestId('list-position-list-b').textContent).toBe('7'),
    );
  });

  it('rejects a board update when the task belongs to another list section', async () => {
    renderSpaceTasksView('board');

    await waitFor(() =>
      expect(screen.getAllByTestId('board-view')).toHaveLength(2),
    );
    fireEvent.click(screen.getByTestId('board-update-foreign-list-b'));
    expect(mocks.updateTask).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId('board-update-own-list-b'));
    await waitFor(() =>
      expect(mocks.updateTask).toHaveBeenCalledWith('token', 'task-list-b', {
        status: 'open',
      }),
    );
  });

  it('closes the selected task when tab navigation removes its task query', async () => {
    renderSpaceTasksView('board');

    await waitFor(() =>
      expect(screen.getAllByTestId('board-view')).toHaveLength(2),
    );
    fireEvent.click(screen.getByTestId('board-select-list-a'));
    expect((await screen.findByTestId('task-detail')).textContent).toBe(
      'task-list-a',
    );

    fireEvent.click(screen.getByRole('button', { name: /Gantt|간트/ }));
    await waitFor(() => expect(screen.queryByTestId('task-detail')).toBeNull());
  });

  it('starts a fresh filter session when the space changes', async () => {
    mocks.listAllPmsTaskLists.mockImplementation(
      (_token: string, requestedSpaceId: string) =>
        Promise.resolve({
          items: [
            list({
              id: `list-${requestedSpaceId}`,
              name: `List ${requestedSpaceId}`,
              team_id: requestedSpaceId,
            }),
          ],
          page: 1,
          page_size: 100,
          total: 1,
        }),
    );
    const view = renderSpaceTasksView('list');

    await screen.findByTestId('filter-query');
    fireEvent.click(screen.getByTestId('filter-set-query'));
    await waitFor(() =>
      expect(screen.getByTestId('filter-query').textContent).toBe(
        'space-a-filter',
      ),
    );

    view.rerender(
      <MemoryRouter>
        <SpaceTasksView
          activeTab="list"
          spaceId="space-2"
          spaceName="Space Two"
        />
      </MemoryRouter>,
    );
    await waitFor(() =>
      expect(screen.getByTestId('filter-query').textContent).toBe(''),
    );
  });
});

function renderSpaceTasksView(activeTab: PmsTaskListToolTab) {
  return render(
    <MemoryRouter>
      <SpaceTasksView
        activeTab={activeTab}
        spaceId="space-1"
        spaceName="Space One"
      />
    </MemoryRouter>,
  );
}
