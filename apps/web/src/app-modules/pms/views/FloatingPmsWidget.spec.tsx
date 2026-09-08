import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { i18n } from '@/src/platform/i18n/i18n';
import type { PmsTaskList } from '../api/pms-api';
import {
  FloatingPmsWidget,
  useFloatingPmsAssignedSummary,
} from './FloatingPmsWidget';
import { dispatchPmsTaskListChanged } from './pms-events';

const authState = vi.hoisted(() => ({
  token: null as string | null,
  admitted: true,
}));
vi.mock('@/src/platform/apps/app-bootstrap-context', () => ({
  useAppAdmission: () => authState.admitted,
}));
const pmsApiMocks = vi.hoisted(() => ({
  listAllPmsTaskLists: vi.fn(),
  listPersonalPmsAssignedTasks: vi.fn(),
  listTaskListStatuses: vi.fn(),
}));
const newTaskModalSpy = vi.hoisted(() => vi.fn());

vi.mock('@/src/platform/auth/auth-provider', () => ({
  useAuth: () => ({ token: authState.token }),
}));

vi.mock('../api/pms-api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/pms-api')>();
  return { ...actual, ...pmsApiMocks };
});

vi.mock('./NewTaskModal', () => ({
  NewTaskModal: (props: Record<string, unknown>) => {
    newTaskModalSpy(props);
    return <div aria-label="new-task-modal" role="dialog" />;
  },
}));

function LocationProbe() {
  const location = useLocation();
  return <output aria-label="current-location">{location.pathname}</output>;
}

function AssignedSummaryProbe() {
  const summary = useFloatingPmsAssignedSummary(authState.token);
  return <output aria-label="assigned-count">{summary.count}</output>;
}

describe('FloatingPmsWidget', () => {
  beforeEach(async () => {
    authState.token = null;
    authState.admitted = true;
    newTaskModalSpy.mockClear();
    pmsApiMocks.listAllPmsTaskLists.mockReset();
    pmsApiMocks.listPersonalPmsAssignedTasks.mockReset();
    pmsApiMocks.listTaskListStatuses.mockReset();
    pmsApiMocks.listTaskListStatuses.mockResolvedValue({ items: [] });
    await i18n.changeLanguage('ko-KR');
  });

  it('loads app-owned task lists directly and opens the selected list', async () => {
    authState.token = 'token-1';
    pmsApiMocks.listPersonalPmsAssignedTasks.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 100,
    });
    pmsApiMocks.listAllPmsTaskLists.mockResolvedValue({
      items: [
        {
          id: 'list-alpha',
          name: 'Backlog',
          role: 'member',
          team_id: 'space-alpha',
          team_name: 'Alpha',
          folder_name: null,
        },
      ],
    });
    render(
      <MemoryRouter>
        <FloatingPmsWidget />
      </MemoryRouter>,
    );
    await waitFor(() =>
      expect(
        (screen.getByRole('button', { name: '새 태스크' }) as HTMLButtonElement)
          .disabled,
      ).toBe(false),
    );
    fireEvent.click(screen.getByRole('button', { name: '새 태스크' }));
    await screen.findByRole('dialog', { name: 'new-task-modal' });
    await waitFor(() =>
      expect(newTaskModalSpy).toHaveBeenLastCalledWith(
        expect.objectContaining({ taskListId: 'list-alpha' }),
      ),
    );
    expect(pmsApiMocks.listAllPmsTaskLists).toHaveBeenCalledWith(
      'token-1',
      undefined,
    );
    expect(newTaskModalSpy.mock.lastCall?.[0]).not.toHaveProperty(
      'workspaceOptions',
    );
  });

  it('marks a create-task open request as consumed after opening the modal', async () => {
    const onCreateTaskOpenRequestHandled = vi.fn();

    render(
      <MemoryRouter>
        <FloatingPmsWidget
          onCreateTaskOpenRequestHandled={onCreateTaskOpenRequestHandled}
          openRequest={{
            detail: {
              mode: 'createTask',
              sourceTodoId: 'todo-1',
              title: 'Todo title',
            },
            id: 7,
          }}
        />
      </MemoryRouter>,
    );

    expect(
      await screen.findByRole('dialog', { name: 'new-task-modal' }),
    ).not.toBeNull();
    expect(onCreateTaskOpenRequestHandled).toHaveBeenCalledWith(7);
  });

  it('reloads and removes tasks when their list is archived', async () => {
    authState.token = 'token-1';
    const assignedTask = {
      due_date: null,
      id: 'task-1',
      list_id: 'list-alpha',
      priority: 'medium',
      status: 'todo',
      title: 'Assigned archive task',
    };
    pmsApiMocks.listPersonalPmsAssignedTasks
      .mockResolvedValueOnce({
        items: [assignedTask],
        page: 1,
        page_size: 100,
        total: 1,
      })
      .mockResolvedValue({
        items: [],
        page: 1,
        page_size: 100,
        total: 0,
      });
    pmsApiMocks.listAllPmsTaskLists.mockResolvedValue({
      items: [
        {
          archived: false,
          id: 'list-alpha',
          name: 'Backlog',
          role: 'member',
          team_id: 'space-alpha',
          team_name: 'Alpha',
        },
      ],
    });

    render(
      <MemoryRouter>
        <FloatingPmsWidget />
      </MemoryRouter>,
    );

    expect(await screen.findByText('Assigned archive task')).not.toBeNull();

    act(() => {
      dispatchPmsTaskListChanged({
        type: 'updated',
        taskList: {
          archived: true,
          id: 'list-alpha',
          name: 'Backlog',
          role: 'member',
          team_id: 'space-alpha',
          team_name: 'Alpha',
        } as PmsTaskList,
      });
    });

    await waitFor(() => {
      expect(screen.queryByText('Assigned archive task')).toBeNull();
      expect(pmsApiMocks.listPersonalPmsAssignedTasks).toHaveBeenCalledTimes(2);
    });
  });

  it('refreshes the shell assigned count after a list change', async () => {
    authState.token = 'token-1';
    pmsApiMocks.listPersonalPmsAssignedTasks
      .mockResolvedValueOnce({
        items: [{ id: 'task-1' }],
      })
      .mockResolvedValue({ items: [] });

    render(<AssignedSummaryProbe />);

    await waitFor(() => {
      expect(screen.getByLabelText('assigned-count').textContent).toBe('1');
    });

    act(() => {
      dispatchPmsTaskListChanged({
        type: 'updated',
        taskList: {
          archived: true,
          id: 'list-alpha',
        } as PmsTaskList,
      });
    });

    await waitFor(() => {
      expect(screen.getByLabelText('assigned-count').textContent).toBe('0');
      expect(pmsApiMocks.listPersonalPmsAssignedTasks).toHaveBeenCalledTimes(2);
    });
  });

  it('opens the full PMS app at the canonical route', () => {
    render(
      <MemoryRouter initialEntries={['/apps/home']}>
        <FloatingPmsWidget />
        <LocationProbe />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'PMS' }));

    expect(screen.getByLabelText('current-location').textContent).toBe(
      '/apps/pms',
    );
  });

  it('disables the PMS shortcut when app admission is denied', () => {
    authState.admitted = false;
    render(
      <MemoryRouter>
        <FloatingPmsWidget />
      </MemoryRouter>,
    );

    expect(
      (
        screen.getByRole('button', {
          name: 'PMS',
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
  });
});
