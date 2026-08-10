import { describe, expect, it } from 'vitest';

import {
  emptySubjectSelection,
  formatStatusLabel,
  formatUserApps,
  getWorkspaceRoleLabel,
  getWorkspaceRoleOptions,
  removeSubject,
  selectionSize,
  toggleSubject,
} from './admin-shared-model';

describe('admin shared model', () => {
  it('formats workspace role options and fallback labels', () => {
    const t = (key: string) => `translated:${key}`;

    expect(getWorkspaceRoleOptions(t)).toEqual([
      {
        value: 'admin',
        label: 'translated:apps:admin.shared.roles.admin.label',
        description: 'translated:apps:admin.shared.roles.admin.description',
      },
      {
        value: 'member',
        label: 'translated:apps:admin.shared.roles.member.label',
        description: 'translated:apps:admin.shared.roles.member.description',
      },
    ]);
    expect(getWorkspaceRoleLabel('owner', t)).toBe('owner');
  });

  it('formats status and app labels', () => {
    const t = (key: string) => `translated:${key}`;

    expect(formatStatusLabel('active', t)).toBe(
      'translated:apps:admin.shared.status.active',
    );
    expect(formatStatusLabel('', t)).toBe('-');
    expect(formatUserApps({ system_roles: [] })).toBe('-');
    expect(formatUserApps({ system_roles: ['admin'] })).toBe('Admin');
  });

  it('toggles and removes selected subjects without mutating previous state', () => {
    const subject = {
      id: 'user-1',
      kind: 'user' as const,
      label: 'User One',
    };
    const empty = emptySubjectSelection();
    const selected = toggleSubject(empty, subject);
    const toggledOff = toggleSubject(selected, subject);
    const selectedAgain = toggleSubject(empty, subject);
    const removed = removeSubject(selectedAgain, 'user', 'user-1');

    expect(selectionSize(empty)).toBe(0);
    expect(selectionSize(selected)).toBe(1);
    expect(selectionSize(toggledOff)).toBe(0);
    expect(selectionSize(removed)).toBe(0);
    expect(selectionSize(selectedAgain)).toBe(1);
  });
});
