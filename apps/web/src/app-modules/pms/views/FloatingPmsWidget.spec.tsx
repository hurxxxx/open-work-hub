import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { i18n } from '@/src/platform/i18n/i18n';
import type { PmsTaskList } from '../api/pms-api';
import {
  FloatingPmsWidget,
  useFloatingPmsAssignedSummary,
} from './FloatingPmsWidget';
import { dispatchPmsTaskListChanged } from './pms-events';

const authState = vi.hoisted(() => ({ token: null as string | null }));
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
    const options = props.workspaceOptions as Array<{
      label: string;
      slug: string;
    }>;
    const onWorkspaceSlugChange = props.onWorkspaceSlugChange as (
      workspaceSlug: string,
    ) => void;
    return (
      <div aria-label="new-task-modal" role="dialog">
        <select
          aria-label="new-task-workspace"
          onChange={(event) => onWorkspaceSlugChange(event.target.value)}
          value={props.workspaceSlug as string}
        >
          {options.map((option) => (
            <option key={option.slug} value={option.slug}>
              {option.label}
            </option>
          ))}
        </select>
      </div>
    );
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
    newTaskModalSpy.mockClear();
    pmsApiMocks.listAllPmsTaskLists.mockReset();
    pmsApiMocks.listPersonalPmsAssignedTasks.mockReset();
    pmsApiMocks.listTaskListStatuses.mockReset();
    pmsApiMocks.listTaskListStatuses.mockResolvedValue({ items: [] });
    await i18n.changeLanguage('ko-KR');
  });

  it('moves workspace selection into the new-task modal', async () => {
    authState.token = 'token-1';
    pmsApiMocks.listPersonalPmsAssignedTasks.mockResolvedValue({
      items: [],
      page: 1,
      page_size: 100,
      total: 0,
      workspaces: [
        { id: 'workspace-alpha', name: 'Alpha', slug: 'alpha' },
        { id: 'workspace-beta', name: 'Beta', slug: 'beta' },
      ],
    });
    pmsApiMocks.listAllPmsTaskLists.mockImplementation(
      (_token: string, _teamId: undefined, workspaceSlug: string) =>
        Promise.resolve({
          items: [
            {
              folder_name: null,
              id: `list-${workspaceSlug}`,
              name: 'Backlog',
              role: 'member',
              team_id: `space-${workspaceSlug}`,
              team_name: workspaceSlug === 'alpha' ? 'Alpha' : 'Beta',
            },
          ],
        }),
    );

    render(
      <MemoryRouter initialEntries={['/w/alpha/home']}>
        <FloatingPmsWidget workspaceSlug="alpha" />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(
        (
          screen.getByRole('button', {
            name: '새 태스크',
          }) as HTMLButtonElement
        ).disabled,
      ).toBe(false);
    });
    expect(screen.queryByRole('combobox')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: '새 태스크' }));
    const workspaceSelect = await screen.findByRole('combobox', {
      name: 'new-task-workspace',
    });
    fireEvent.change(workspaceSelect, { target: { value: 'beta' } });

    expect(
      screen.getByRole('dialog', { name: 'new-task-modal' }),
    ).not.toBeNull();
    await waitFor(() => {
      expect(pmsApiMocks.listAllPmsTaskLists).toHaveBeenCalledWith(
        'token-1',
        undefined,
        'beta',
      );
      expect(newTaskModalSpy).toHaveBeenLastCalledWith(
        expect.objectContaining({
          taskListId: 'list-beta',
          workspaceSlug: 'beta',
        }),
      );
    });
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
      workspace: { id: 'workspace-alpha', name: 'Alpha', slug: 'alpha' },
    };
    pmsApiMocks.listPersonalPmsAssignedTasks
      .mockResolvedValueOnce({
        items: [assignedTask],
        page: 1,
        page_size: 100,
        total: 1,
        workspaces: [assignedTask.workspace],
      })
      .mockResolvedValue({
        items: [],
        page: 1,
        page_size: 100,
        total: 0,
        workspaces: [assignedTask.workspace],
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
        <FloatingPmsWidget workspaceSlug="alpha" />
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
        workspaces: [{ id: 'workspace-alpha', name: 'Alpha', slug: 'alpha' }],
      })
      .mockResolvedValue({ items: [], workspaces: [] });

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

  it('opens the full PMS app for the current workspace', () => {
    render(
      <MemoryRouter initialEntries={['/w/team-alpha/home']}>
        <FloatingPmsWidget workspaceSlug="team alpha" />
        <LocationProbe />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'PMS' }));

    expect(screen.getByLabelText('current-location').textContent).toBe(
      '/w/team%20alpha/pms',
    );
  });

  it('disables the PMS shortcut until the workspace is available', () => {
    render(
      <MemoryRouter>
        <FloatingPmsWidget workspaceSlug={null} />
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
