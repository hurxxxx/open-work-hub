import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { i18n } from '@/src/platform/i18n/i18n';
import type { PmsTask } from '../api/pms-api';
import { TableView } from './TableView';

function task(overrides: Partial<PmsTask> = {}): PmsTask {
  return {
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
    milestone_title: null,
    parent_id: null,
    priority: 'medium',
    priority_label: 'Medium',
    recurrence_rule: null,
    reference: 'TASK-1',
    reporter_id: 'reporter-1',
    reporter_name: 'Riley Park',
    start_date: null,
    status: 'done',
    status_label: 'Done',
    task_number: 1,
    title: 'Completed task',
    updated_at: '2026-06-18T00:00:00Z',
    ...overrides,
  } as PmsTask;
}

describe('TableView', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('ko-KR');
  });

  it('shows completion dates in the desktop table and mobile task card', () => {
    render(
      <TableView
        onSelectIssue={vi.fn()}
        tasks={[task({ completed_date: '2026-06-18' })]}
      />,
    );

    const table = within(screen.getByRole('table'));
    expect(
      table.getByRole('columnheader', { name: '완료일' }),
    ).not.toBeNull();
    expect(table.getByText('2026. 6. 18.')).not.toBeNull();

    const mobileCard = within(screen.getByTestId('mobile-task-card'));
    expect(mobileCard.getByText('완료일')).not.toBeNull();
    expect(mobileCard.getByText('2026. 6. 18.')).not.toBeNull();
  });

  it('updates the completion date from the desktop table', () => {
    const onUpdateIssue = vi.fn();
    render(
      <TableView
        canEdit
        onSelectIssue={vi.fn()}
        onUpdateIssue={onUpdateIssue}
        tasks={[task({ completed_date: '2026-06-18' })]}
      />,
    );

    const table = within(screen.getByRole('table'));
    const input = table.getByRole('textbox', { name: '완료일' });
    fireEvent.change(input, { target: { value: '2026. 6. 20.' } });
    fireEvent.blur(input);

    expect(onUpdateIssue).toHaveBeenCalledWith('task-1', {
      completed_date: '2026-06-20',
    });
  });
});
