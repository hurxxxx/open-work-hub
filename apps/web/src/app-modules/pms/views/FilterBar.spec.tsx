import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { i18n } from '@/src/platform/i18n/i18n';
import type { PmsTaskListStatus } from '../api/pms-api';
import { FilterBar } from './FilterBar';

const statuses = [
  {
    id: 'status-todo',
    category: 'not_started',
    name: '할 일',
    sort_order: 0,
    color: '#94a3b8',
    slug: 'todo',
  },
  {
    id: 'status-doing',
    category: 'active',
    name: '진행 중',
    sort_order: 1,
    color: '#94a3b8',
    slug: 'doing',
  },
  {
    id: 'status-done',
    category: 'done',
    name: '완료됨',
    sort_order: 2,
    color: '#94a3b8',
    slug: 'done',
  },
  {
    id: 'status-closed',
    category: 'closed',
    name: '종료됨',
    sort_order: 3,
    color: '#94a3b8',
    slug: 'closed',
  },
] satisfies PmsTaskListStatus[];

describe('FilterBar', () => {
  beforeEach(async () => {
    localStorage.clear();
    await i18n.changeLanguage('ko-KR');
  });

  it('checks non-completion statuses on the initial screen', () => {
    render(
      <FilterBar
        filterParams={{ archived_state: 'active' }}
        labels={[]}
        members={[]}
        milestones={[]}
        setFilterParams={vi.fn()}
        taskListId="list-1"
        taskListStatuses={statuses}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: '상태' }));

    expect(
      (screen.getByRole('checkbox', { name: '할 일' }) as HTMLInputElement)
        .checked,
    ).toBe(true);
    expect(
      (screen.getByRole('checkbox', { name: '진행 중' }) as HTMLInputElement)
        .checked,
    ).toBe(true);
    expect(
      (screen.getByRole('checkbox', { name: '완료됨' }) as HTMLInputElement)
        .checked,
    ).toBe(false);
    expect(
      (screen.getByRole('checkbox', { name: '종료됨' }) as HTMLInputElement)
        .checked,
    ).toBe(false);
  });

  it('starts a direct status edit from the effective default selection', () => {
    const setFilterParams = vi.fn();
    render(
      <FilterBar
        filterParams={{ archived_state: 'active' }}
        labels={[]}
        members={[]}
        milestones={[]}
        setFilterParams={setFilterParams}
        taskListId="list-1"
        taskListStatuses={statuses}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: '상태' }));
    fireEvent.click(screen.getByRole('checkbox', { name: '완료됨' }));

    expect(setFilterParams).toHaveBeenCalledWith({
      archived_state: 'active',
      status: ['todo', 'doing', 'done'],
    });
  });

  it('layers the assignee menu above sticky gantt headers', () => {
    render(
      <FilterBar
        filterParams={{ archived_state: 'active' }}
        labels={[]}
        members={[]}
        milestones={[]}
        setFilterParams={vi.fn()}
        taskListId="list-1"
        taskListStatuses={statuses}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: '담당자' }));

    const menu = screen
      .getByRole('textbox', {
        name: '이름, 이메일 또는 부서로 사용자 검색',
      })
      .closest('.absolute');
    expect(menu?.classList.contains('z-[var(--ui-z-popover)]')).toBe(true);
  });
});
