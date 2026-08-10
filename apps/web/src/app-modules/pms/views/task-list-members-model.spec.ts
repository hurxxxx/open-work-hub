import { describe, expect, it } from 'vitest';

import type { PmsSpaceMember, PmsUserSummary } from '../api/pms-api';
import {
  NO_MEMBER_SELECTION,
  buildTaskListMemberCandidateOptions,
  canMutateTaskListSettingsMember,
  roleOptionsForTaskListSettings,
} from './task-list-members-model';

function user(overrides: Partial<PmsUserSummary> = {}): PmsUserSummary {
  return {
    id: 'user-1',
    email: 'user-1@example.test',
    full_name: 'User One',
    ...overrides,
  } as PmsUserSummary;
}

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

describe('task list members model', () => {
  it('builds candidate options with a placeholder and excludes existing members', () => {
    expect(
      buildTaskListMemberCandidateOptions({
        availableUsers: [
          user({ id: 'user-1', full_name: 'Existing User' }),
          user({
            id: 'user-2',
            email: 'user-2@example.test',
            full_name: 'User Two',
          }),
        ],
        candidatePlaceholder: 'Add member',
        members: [member({ user_id: 'user-1' })],
      }),
    ).toEqual([
      { value: NO_MEMBER_SELECTION, label: 'Add member' },
      { value: 'user-2', label: 'User Two (user-2@example.test)' },
    ]);
  });

  it('restricts role options for non-owner task list settings managers', () => {
    expect(
      roleOptionsForTaskListSettings(true).map((option) => option.value),
    ).toEqual(['owner', 'admin', 'member', 'viewer']);
    expect(
      roleOptionsForTaskListSettings(false).map((option) => option.value),
    ).toEqual(['member', 'viewer']);
  });

  it('guards self and protected manager mutations', () => {
    expect(
      canMutateTaskListSettingsMember({
        canManageAdmins: true,
        currentUserId: 'self',
        member: member({ role: 'owner', user_id: 'self' }),
      }),
    ).toBe(false);
    expect(
      canMutateTaskListSettingsMember({
        canManageAdmins: false,
        currentUserId: 'other',
        member: member({ role: 'admin', user_id: 'admin' }),
      }),
    ).toBe(false);
    expect(
      canMutateTaskListSettingsMember({
        canManageAdmins: false,
        currentUserId: 'other',
        member: member({ role: 'viewer', user_id: 'viewer' }),
      }),
    ).toBe(true);
    expect(
      canMutateTaskListSettingsMember({
        canManageAdmins: true,
        currentUserId: 'other',
        member: member({ role: 'admin', user_id: 'admin' }),
      }),
    ).toBe(true);
  });
});
