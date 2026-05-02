import { render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { PmsIssue } from '../api/pms-api';
import { ListView } from './ListView';

function buildIssue(overrides: Partial<PmsIssue> = {}): PmsIssue {
  return {
    id: 'issue-1',
    list_id: 'list-1',
    reference: 'DEMO-1',
    title: '검색 검증 예산 리스크 실행 과제',
    description: null,
    description_blocks: null,
    parent_id: null,
    subtask_count: 0,
    status: 'todo',
    status_label: 'Todo',
    priority: 'high',
    priority_label: 'High',
    assignee_id: 'user-1',
    assignee_name: 'Demo User',
    reporter_id: 'user-1',
    reporter_name: 'Demo User',
    milestone_id: null,
    milestone_title: null,
    start_date: null,
    due_date: '2026-05-13',
    board_position: 1,
    archived: false,
    progress: 0,
    comments_count: 1,
    checklist_total: 3,
    checklist_done: 1,
    estimate_hours: 4,
    time_spent_minutes: 60,
    recurrence_rule: null,
    assignee_ids: ['user-1'],
    assignee_names: ['Demo User'],
    labels: [],
    updated_at: '2026-05-02T00:00:00Z',
    ...overrides,
  };
}

describe('ListView', () => {
  it('renders mobile task cards with clamped task titles', () => {
    const longTitle = '[검색 검증] 온보딩 실행 과제 리스크 실험 과제 11';

    render(
      <ListView
        issues={[buildIssue({ title: longTitle })]}
        onSelectIssue={vi.fn()}
        selectedIds={new Set()}
        onToggleSelect={vi.fn()}
      />,
    );

    const card = screen.getByTestId('mobile-task-card');
    const title = within(card).getByText(longTitle);

    expect(card).toBeTruthy();
    expect(title.className).toContain('line-clamp-2');
    expect(screen.getByTestId('desktop-task-table')).toBeTruthy();
  });
});
