import { createPmsTask } from '../../../../tests/fixtures/pms';
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { PmsTask, PmsTaskListMember } from '../api/pms-api';
import { ListView } from './ListView';

function task(overrides: Partial<PmsTask> = {}): PmsTask {
  return createPmsTask({
    archived: false,
    assignee_id: null,
    assignee_ids: [],
    assignee_name: null,
    assignee_names: [],
    board_position: 1000,
    checklist_done: 0,
    checklist_total: 0,
    comments_count: 0,
    completed_date: null,
    description: '',
    description_blocks: null,
    due_date: null,
    follower_ids: [],
    follower_names: [],
    id: 'task-1',
    labels: [],
    list_id: 'list-1',
    milestone_id: null,
    parent_id: null,
    priority: 'medium',
    priority_label: 'Medium',
    recurrence_rule: null,
    reference: 'TASK-1',
    reporter_id: 'reporter-1',
    reporter_name: 'Riley Park',
    start_date: null,
    status: 'todo',
    status_label: 'To Do',

    title: 'Task with reporter',
    ...overrides,
  });
}

function member(overrides: Partial<PmsTaskListMember> = {}): PmsTaskListMember {
  return {
    email: 'riley@example.test',
    full_name: 'Riley Park',
    is_admin: false,
    joined_at: '2026-06-10T00:00:00.000Z',
    role: 'member',
    user_id: 'reporter-1',
    ...overrides,
  };
}

function dataTransfer() {
  const store = new Map<string, string>();
  return {
    effectAllowed: '',
    getData: vi.fn((type: string) => store.get(type) ?? ''),
    setData: vi.fn((type: string, value: string) => {
      store.set(type, value);
    }),
  };
}

describe('ListView', () => {
  it('keeps the desktop horizontal scrollbar on the bounded list viewport', () => {
    render(<ListView onSelectIssue={vi.fn()} tasks={[task()]} />);

    const scrollRegion = screen.getByTestId('task-list-scroll-region');
    expect(scrollRegion.className).toContain('min-h-0');
    expect(scrollRegion.className).toContain('min-w-0');
    expect(scrollRegion.className).toContain('flex-1');
    expect(scrollRegion.className).toContain('overflow-auto');

    const tableContainer =
      screen.getByTestId('desktop-task-table').parentElement;
    expect(tableContainer?.className).not.toContain('overflow-x-auto');
  });

  it('switches between status, assignee, and ungrouped modes without a duplicate add button', () => {
    const onGroupByChange = vi.fn();
    render(
      <ListView
        onGroupByChange={onGroupByChange}
        onSelectIssue={vi.fn()}
        tasks={[task()]}
      />,
    );

    expect(screen.queryByText('업무 추가')).toBeNull();
    const statusButton = screen.getByRole('button', { name: '그룹: 상태' });
    const userButton = screen.getByRole('button', { name: '그룹: 사용자' });
    expect(statusButton.getAttribute('aria-pressed')).toBe('true');

    fireEvent.click(userButton);
    expect(userButton.getAttribute('aria-pressed')).toBe('true');
    expect(statusButton.getAttribute('aria-pressed')).toBe('false');
    fireEvent.click(userButton);

    expect(onGroupByChange).toHaveBeenNthCalledWith(1, 'assignee');
    expect(onGroupByChange).toHaveBeenNthCalledWith(2, 'none');
  });

  it('selects date sorting, toggles direction, and resets to custom order', () => {
    const onSortChange = vi.fn();
    const { rerender } = render(
      <ListView
        onSelectIssue={vi.fn()}
        onSortChange={onSortChange}
        tasks={[task()]}
      />,
    );

    fireEvent.click(
      screen.getByRole('button', { name: '정렬: 사용자 지정 순서' }),
    );
    fireEvent.click(screen.getByRole('button', { name: '마감일' }));
    expect(onSortChange).toHaveBeenLastCalledWith({
      direction: 'asc',
      field: 'due_date',
    });

    rerender(
      <ListView
        onSelectIssue={vi.fn()}
        onSortChange={onSortChange}
        sort={{ direction: 'asc', field: 'due_date' }}
        tasks={[task()]}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: '정렬: 마감일' }));
    fireEvent.click(screen.getByRole('button', { name: /^마감일/ }));
    expect(onSortChange).toHaveBeenLastCalledWith({
      direction: 'desc',
      field: 'due_date',
    });

    fireEvent.click(screen.getByRole('button', { name: '정렬 초기화' }));
    expect(onSortChange).toHaveBeenLastCalledWith({
      direction: 'asc',
      field: 'board_position',
    });
  });

  it('toggles completed items from the grouping and sorting toolbar', () => {
    const onShowCompletedItemsChange = vi.fn();
    const { rerender } = render(
      <ListView
        onSelectIssue={vi.fn()}
        onShowCompletedItemsChange={onShowCompletedItemsChange}
        showCompletedItems={false}
        tasks={[task()]}
      />,
    );

    fireEvent.click(screen.getByRole('checkbox', { name: '완료항목 표시' }));
    expect(onShowCompletedItemsChange).toHaveBeenCalledWith(true);

    rerender(
      <ListView
        onSelectIssue={vi.fn()}
        onShowCompletedItemsChange={onShowCompletedItemsChange}
        showCompletedItems
        tasks={[task()]}
      />,
    );
    expect(
      (
        screen.getByRole('checkbox', {
          name: '완료항목 표시',
        }) as HTMLInputElement
      ).checked,
    ).toBe(true);

    fireEvent.click(screen.getByRole('checkbox', { name: '완료항목 표시' }));
    expect(onShowCompletedItemsChange).toHaveBeenLastCalledWith(false);
  });

  it('disables the completed-items control until status metadata is ready', () => {
    render(
      <ListView
        completedItemsControlDisabled
        onSelectIssue={vi.fn()}
        onShowCompletedItemsChange={vi.fn()}
        tasks={[task()]}
      />,
    );

    expect(
      (
        screen.getByRole('checkbox', {
          name: '완료항목 표시',
        }) as HTMLInputElement
      ).disabled,
    ).toBe(true);
  });

  it('groups a task hierarchy by the root task primary assignee', () => {
    render(
      <ListView
        groupBy="assignee"
        members={[
          member({ full_name: 'Alice Kim', user_id: 'user-1' }),
          member({ full_name: 'Bob Lee', user_id: 'user-2' }),
        ]}
        onSelectIssue={vi.fn()}
        tasks={[
          task({
            assignee_id: 'user-1',
            assignee_ids: ['user-1'],
            assignee_name: 'Alice Kim',
            assignee_names: ['Alice Kim'],
            id: 'root-1',
            title: 'Alice root',
          }),
          task({
            assignee_id: 'user-2',
            assignee_ids: ['user-2'],
            assignee_name: 'Bob Lee',
            assignee_names: ['Bob Lee'],
            board_position: 2000,
            id: 'child-1',
            parent_id: 'root-1',
            title: 'Child assigned to Bob',
          }),
          task({
            assignee_id: 'user-2',
            assignee_ids: ['user-2'],
            assignee_name: 'Bob Lee',
            assignee_names: ['Bob Lee'],
            board_position: 3000,
            id: 'root-2',
            title: 'Bob root',
          }),
          task({
            board_position: 4000,
            id: 'root-3',
            title: 'Unassigned root',
          }),
        ]}
      />,
    );

    const aliceGroup = within(screen.getByTestId('assignee-task-group-user-1'));
    expect(aliceGroup.getAllByText('Alice root')).not.toHaveLength(0);
    expect(aliceGroup.getAllByText('Child assigned to Bob')).not.toHaveLength(
      0,
    );
    expect(
      within(screen.getByTestId('assignee-task-group-user-2')).queryByText(
        'Child assigned to Bob',
      ),
    ).toBeNull();
    const unassignedGroup = within(
      screen.getByTestId('assignee-task-group-unassigned'),
    );
    expect(unassignedGroup.getAllByText('Unassigned root')).not.toHaveLength(0);
    expect(unassignedGroup.queryByText('pms.unassigned')).toBeNull();
  });

  it('shows task reporter names in the desktop reporter column', () => {
    render(
      <ListView
        members={[member()]}
        onSelectIssue={vi.fn()}
        tasks={[task()]}
      />,
    );

    const table = within(screen.getByTestId('desktop-task-table'));
    expect(table.getByText('Riley Park')).not.toBeNull();
  });

  it('shows completion dates in the desktop table and mobile task card', () => {
    render(
      <ListView
        onSelectIssue={vi.fn()}
        tasks={[task({ completed_date: '2026-06-18' })]}
      />,
    );

    const table = within(screen.getByTestId('desktop-task-table'));
    expect(table.getByRole('columnheader', { name: '완료일' })).not.toBeNull();
    expect(table.getByText('2026. 6. 18.')).not.toBeNull();

    const mobileCard = within(screen.getByTestId('mobile-task-card'));
    expect(mobileCard.getByText('완료일')).not.toBeNull();
    expect(mobileCard.getByText('2026. 6. 18.')).not.toBeNull();
  });

  it('updates the completion date from the desktop list', async () => {
    const onUpdateIssue = vi.fn().mockResolvedValue(undefined);
    render(
      <ListView
        canEdit
        onSelectIssue={vi.fn()}
        onUpdateIssue={onUpdateIssue}
        tasks={[task({ completed_date: '2026-06-18' })]}
      />,
    );

    const table = within(screen.getByTestId('desktop-task-table'));
    fireEvent.click(table.getByRole('button', { name: '완료일' }));
    const input = screen.getByRole('textbox', { name: '완료일' });
    fireEvent.change(input, { target: { value: '2026. 6. 20.' } });
    fireEvent.blur(input);

    await waitFor(() => {
      expect(onUpdateIssue).toHaveBeenCalledWith('task-1', {
        completed_date: '2026-06-20',
      });
    });
  });

  it('uses the batch reorder callback instead of per-task updates when provided', async () => {
    const onReorderIssues = vi.fn().mockResolvedValue(undefined);
    const onUpdateIssue = vi.fn().mockResolvedValue(undefined);
    render(
      <ListView
        canEdit
        onReorderIssues={onReorderIssues}
        onSelectIssue={vi.fn()}
        onUpdateIssue={onUpdateIssue}
        tasks={[
          task({
            board_position: 1000,
            id: 'task-1',
            reference: 'TASK-1',

            title: 'First',
          }),
          task({
            board_position: 2000,
            id: 'task-2',
            reference: 'TASK-2',

            title: 'Second',
          }),
          task({
            board_position: 3000,
            id: 'task-3',
            reference: 'TASK-3',

            title: 'Third',
          }),
        ]}
      />,
    );

    const dragData = dataTransfer();
    const firstDragHandle = screen.getAllByRole('button', {
      name: '드래그해서 순서 이동',
    })[0];
    const table = within(screen.getByTestId('desktop-task-table'));
    const thirdRow = table.getByRole('button', { name: 'Third' }).closest('tr');
    expect(thirdRow).not.toBeNull();

    fireEvent.dragStart(firstDragHandle, { dataTransfer: dragData });
    fireEvent.drop(thirdRow as HTMLTableRowElement, { dataTransfer: dragData });

    await waitFor(() => {
      expect(onReorderIssues).toHaveBeenCalledTimes(1);
    });
    expect(onReorderIssues).toHaveBeenCalledWith([
      { boardPosition: 2500, taskId: 'task-1' },
    ]);
    expect(onUpdateIssue).not.toHaveBeenCalled();
  });
});
