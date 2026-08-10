import { DndContext } from '@dnd-kit/core';
import { SortableContext } from '@dnd-kit/sortable';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import type { PmsTaskList } from '../api/pms-api';
import { SortableListLink } from './SortableListLink';

function taskList(overrides: Partial<PmsTaskList> = {}): PmsTaskList {
  return {
    archived: false,
    created_at: '2026-06-17T00:00:00.000Z',
    description: '',
    folder_id: null,
    folder_name: null,
    id: 'list-1',
    key: 'LIST',
    member_count: 1,
    milestone_count: 0,
    name: 'Launch List',
    overdue_task_count: 0,
    progress: 0,
    role: 'admin',
    sort_order: 0,
    status: 'active',
    status_mode: 'custom',
    task_count: 3,
    team_id: 'space-1',
    team_name: 'Space 1',
    updated_at: '2026-06-17T00:00:00.000Z',
    ...overrides,
  };
}

function renderLink({
  list = taskList(),
  menuOpen = false,
  onDelete = vi.fn(),
  onArchive,
  onRename = vi.fn(),
  onRestore,
  onSettings = vi.fn(),
}: {
  list?: PmsTaskList;
  menuOpen?: boolean;
  onDelete?: () => void;
  onArchive?: () => void;
  onRename?: () => void;
  onRestore?: () => void;
  onSettings?: () => void;
} = {}) {
  const menu = {
    buttonRefs: { current: new Map<string, HTMLButtonElement>() },
    isOpen: menuOpen,
    onClose: vi.fn(),
    onToggle: vi.fn(),
  };

  render(
    <MemoryRouter>
      <DndContext>
        <SortableContext items={[list.id]}>
          <SortableListLink
            activeNavItemId=""
            canDrag={false}
            dropZone={null}
            list={list}
            menu={menu}
            onDelete={onDelete}
            onArchive={onArchive}
            onRename={onRename}
            onRestore={onRestore}
            onSettings={onSettings}
            workspaceSlug="administrator"
          />
        </SortableContext>
      </DndContext>
    </MemoryRouter>,
  );

  return { menu, onArchive, onDelete, onRename, onRestore, onSettings };
}

describe('SortableListLink', () => {
  it('shows settings, rename, and archive actions for active admin lists', () => {
    const onArchive = vi.fn();
    const onRename = vi.fn();
    const onSettings = vi.fn();
    renderLink({ menuOpen: true, onArchive, onRename, onSettings });

    expect(screen.getByRole('button', { name: '리스트 관리' })).not.toBeNull();

    fireEvent.click(screen.getByRole('menuitem', { name: '설정' }));
    expect(onSettings).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('menuitem', { name: '이름 변경' }));
    expect(onRename).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('menuitem', { name: '보관' }));
    expect(onArchive).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('menuitem', { name: '삭제' })).toBeNull();
  });

  it('exposes restore and permanent delete only for archived lists', () => {
    const onDelete = vi.fn();
    const onRestore = vi.fn();
    const archived = renderLink({
      list: taskList({ archived: true, id: 'list-archived' }),
      menuOpen: true,
      onDelete,
      onRename: undefined,
      onRestore,
      onSettings: undefined,
    });
    fireEvent.click(screen.getByRole('menuitem', { name: '복원' }));
    expect(archived.onRestore).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('menuitem', { name: '삭제' }));
    expect(archived.onDelete).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('menuitem', { name: '보관' })).toBeNull();
  });

  it('hides list actions for viewer lists', () => {
    renderLink({
      list: taskList({ role: 'viewer' }),
      menuOpen: true,
    });

    expect(screen.queryByRole('button', { name: '리스트 관리' })).toBeNull();
    expect(screen.queryByRole('button', { name: '삭제' })).toBeNull();
  });

  it('supports keyboard focus, arrow navigation, and Escape', () => {
    const onArchive = vi.fn();
    const { menu } = renderLink({ menuOpen: true, onArchive });
    const settings = screen.getByRole('menuitem', { name: '설정' });
    const rename = screen.getByRole('menuitem', { name: '이름 변경' });

    expect(document.activeElement).toBe(settings);
    fireEvent.keyDown(screen.getByRole('menu'), { key: 'ArrowDown' });
    expect(document.activeElement).toBe(rename);
    fireEvent.keyDown(screen.getByRole('menu'), { key: 'Escape' });
    expect(menu.onClose).toHaveBeenCalledTimes(1);
    expect(document.activeElement).toBe(
      screen.getByRole('button', { name: '리스트 관리' }),
    );
  });
});
