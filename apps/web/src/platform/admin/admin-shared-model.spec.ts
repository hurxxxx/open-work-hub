import { describe, expect, it } from 'vitest';

import {
  emptySubjectSelection,
  formatStatusLabel,
  formatUserApps,
  removeSubject,
  selectionSize,
  toggleSubject,
} from './admin-shared-model';

describe('admin shared model', () => {
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
