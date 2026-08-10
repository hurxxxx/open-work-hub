import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { PmsSpaceMember, PmsUserSummary } from '../api/pms-api';
import {
  DEFAULT_SPACE_MEMBER_ROLE,
  NO_MEMBER_SELECTION,
  useTaskListMembersController,
} from './useTaskListMembersController';

const addSpaceMember = vi.fn();
const removeSpaceMember = vi.fn();
const updateSpaceMemberRole = vi.fn();

vi.mock('../api/pms-api', () => ({
  addSpaceMember: (...args: unknown[]) => addSpaceMember(...args),
  removeSpaceMember: (...args: unknown[]) => removeSpaceMember(...args),
  updateSpaceMemberRole: (...args: unknown[]) => updateSpaceMemberRole(...args),
}));

function member(overrides: Partial<PmsSpaceMember> = {}): PmsSpaceMember {
  return {
    user_id: 'user-1',
    email: 'user-1@example.test',
    full_name: 'User One',
    is_admin: false,
    joined_at: '2026-05-30T00:00:00Z',
    role: 'member',
    ...overrides,
  } as PmsSpaceMember;
}

function user(overrides: Partial<PmsUserSummary> = {}): PmsUserSummary {
  return {
    id: 'user-1',
    email: 'user-1@example.test',
    full_name: 'User One',
    ...overrides,
  } as PmsUserSummary;
}

function renderController(availableUsers: PmsUserSummary[] = [user()]) {
  const onError = vi.fn();
  const onMembersChanged = vi.fn();
  const rendered = renderHook(() =>
    useTaskListMembersController({
      availableUsers,
      candidatePlaceholder: 'Add member',
      errorMessages: {
        addFailed: 'add failed',
        removeFailed: 'remove failed',
        updateRoleFailed: 'update role failed',
      },
      onError,
      onMembersChanged,
      teamId: 'space-1',
      token: 'token-1',
      workspaceSlug: 'workspace',
    }),
  );
  return { ...rendered, onError, onMembersChanged };
}

describe('useTaskListMembersController', () => {
  it('builds candidate options excluding existing members', () => {
    const { result } = renderController([
      user({ id: 'user-1', full_name: 'User One' }),
      user({ id: 'user-2', email: 'user-2@example.test', full_name: 'User Two' }),
    ]);

    act(() => {
      result.current.replaceMembers([member({ user_id: 'user-1' })]);
    });

    expect(result.current.memberCandidateOptions).toEqual([
      { label: 'Add member', value: NO_MEMBER_SELECTION },
      { label: 'User Two (user-2@example.test)', value: 'user-2' },
    ]);
  });

  it('adds members and resets the add form', async () => {
    const added = member({ user_id: 'user-2', full_name: 'User Two' });
    addSpaceMember.mockResolvedValueOnce(added);
    const { onMembersChanged, result } = renderController([
      user({ id: 'user-2', email: 'user-2@example.test', full_name: 'User Two' }),
    ]);

    act(() => {
      result.current.setSelectedUserId('user-2');
      result.current.setSelectedRole('viewer');
    });
    await act(async () => {
      await result.current.handleAddMember();
    });

    expect(addSpaceMember).toHaveBeenCalledWith(
      'token-1',
      'space-1',
      { role: 'viewer', user_id: 'user-2' },
      'workspace',
    );
    expect(result.current.members).toEqual([added]);
    expect(result.current.selectedUserId).toBe(NO_MEMBER_SELECTION);
    expect(result.current.selectedRole).toBe(DEFAULT_SPACE_MEMBER_ROLE);
    expect(onMembersChanged).toHaveBeenCalledWith([added]);
  });

  it('updates roles and removes members through one controller interface', async () => {
    const original = member({ user_id: 'user-1', role: 'member' });
    const updated = member({ user_id: 'user-1', role: 'admin' });
    updateSpaceMemberRole.mockResolvedValueOnce(updated);
    removeSpaceMember.mockResolvedValueOnce(undefined);
    const { onMembersChanged, result } = renderController();

    act(() => {
      result.current.replaceMembers([original]);
    });
    await act(async () => {
      await result.current.handleRoleChange(original.user_id, 'admin');
    });

    expect(updateSpaceMemberRole).toHaveBeenCalledWith(
      'token-1',
      'space-1',
      original.user_id,
      'admin',
      'workspace',
    );
    expect(result.current.members).toEqual([updated]);

    await act(async () => {
      await result.current.handleRemoveMember(updated.user_id);
    });

    expect(removeSpaceMember).toHaveBeenCalledWith(
      'token-1',
      'space-1',
      updated.user_id,
      'workspace',
    );
    expect(result.current.members).toEqual([]);
    expect(onMembersChanged).toHaveBeenLastCalledWith([]);
  });
});
