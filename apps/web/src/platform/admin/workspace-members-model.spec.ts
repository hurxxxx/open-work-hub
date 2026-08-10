import { describe, expect, it } from 'vitest';

import type {
  WorkspaceBindingItem,
  WorkspaceMemberCandidate,
  WorkspaceMemberItem,
} from './admin-api';
import type { SubjectSelectionState } from './admin-shared';
import {
  activeWorkspaceMemberSelection,
  createWorkspaceAddMemberState,
  filterWorkspaceMemberCandidates,
  patchWorkspaceAddMemberState,
  previewWorkspaceBindings,
  selectableWorkspaceMemberKeys,
  selectedWorkspaceMemberSubjects,
  sortWorkspaceBindings,
  toggleWorkspaceMemberPageSelection,
  toggleWorkspaceMemberSelectionKey,
  workspaceAddMemberBulkSubjects,
  workspaceMemberBulkRoleSubjects,
  workspaceMemberBulkSubject,
  workspaceMemberBulkSubjects,
  workspaceMemberKey,
  workspaceMemberSubjectIds,
  workspaceMembersAllSelectableSelected,
  workspaceRoleSelectOptions,
} from './workspace-members-model';

function binding(
  overrides: Partial<WorkspaceBindingItem>,
): WorkspaceBindingItem {
  return {
    subject_type: 'user',
    subject_id: 'user-1',
    subject_label: 'Alice',
    subject_secondary: 'alice@example.com',
    role: 'member',
    ...overrides,
  } as WorkspaceBindingItem;
}

function member(overrides: Partial<WorkspaceMemberItem>): WorkspaceMemberItem {
  return {
    subject_type: 'user',
    subject_id: 'user-1',
    subject_label: 'Alice',
    subject_secondary: 'alice@example.com',
    role: 'member',
    user_status: 'active',
    last_login_at: null,
    ...overrides,
  } as WorkspaceMemberItem;
}

function candidate(
  overrides: Partial<WorkspaceMemberCandidate>,
): WorkspaceMemberCandidate {
  return {
    id: 'user-1',
    email: 'alice@example.com',
    full_name: 'Alice',
    status: 'active',
    ...overrides,
  } as WorkspaceMemberCandidate;
}

function selection(ids: readonly string[]): SubjectSelectionState {
  return {
    users: new Map(
      ids.map((id) => [
        id,
        {
          id,
          kind: 'user' as const,
          label: `User ${id}`,
          secondary: `${id}@example.com`,
        },
      ]),
    ),
  };
}

describe('workspace members model', () => {
  it('creates and patches add-member state per workspace', () => {
    const initial = createWorkspaceAddMemberState('workspace-1');

    expect(initial).toMatchObject({
      workspaceId: 'workspace-1',
      panelOpen: false,
      pickerOpen: false,
      role: 'member',
    });
    expect(initial.selection.users.size).toBe(0);

    const selected = selection(['user-1']);
    const patched = patchWorkspaceAddMemberState(
      { ...initial, panelOpen: true, role: 'admin', selection: selected },
      'workspace-1',
      { pickerOpen: true },
    );

    expect(patched).toMatchObject({
      workspaceId: 'workspace-1',
      panelOpen: true,
      pickerOpen: true,
      role: 'admin',
    });
    expect(patched.selection).toBe(selected);

    const resetForNextWorkspace = patchWorkspaceAddMemberState(
      patched,
      'workspace-2',
      { panelOpen: true },
    );

    expect(resetForNextWorkspace).toMatchObject({
      workspaceId: 'workspace-2',
      panelOpen: true,
      pickerOpen: false,
      role: 'member',
    });
    expect(resetForNextWorkspace.selection.users.size).toBe(0);
  });

  it('sorts bindings by role and label, then previews admins first', () => {
    const bindings = [
      binding({
        subject_id: 'member-alpha',
        subject_label: 'Alpha',
        role: 'member',
      }),
      binding({
        subject_id: 'admin-zed',
        subject_label: 'Zed',
        role: 'admin',
      }),
      binding({
        subject_id: 'admin-beta',
        subject_label: 'Beta',
        role: 'admin',
      }),
    ];

    const sorted = sortWorkspaceBindings(bindings, 'en');

    expect(sorted.map((item) => item.subject_id)).toEqual([
      'admin-beta',
      'admin-zed',
      'member-alpha',
    ]);
    expect(previewWorkspaceBindings(sorted, 1).map((item) => item.subject_id))
      .toEqual(['admin-beta']);
    expect(
      previewWorkspaceBindings(
        sortWorkspaceBindings(
          [
            binding({ subject_id: 'member-zed', subject_label: 'Zed' }),
            binding({ subject_id: 'member-beta', subject_label: 'Beta' }),
          ],
          'en',
        ),
        1,
      ).map((item) => item.subject_id),
    ).toEqual(['member-beta']);
  });

  it('derives member IDs, selected subjects, and add payloads', () => {
    const selected = selection(['user-2', 'user-1']);

    expect(
      Array.from(
        workspaceMemberSubjectIds([
          binding({ subject_id: 'user-1' }),
          binding({ subject_id: 'user-2' }),
        ]),
      ),
    ).toEqual(['user-1', 'user-2']);
    expect(selectedWorkspaceMemberSubjects(selected).map((item) => item.id))
      .toEqual(['user-2', 'user-1']);
    expect(workspaceAddMemberBulkSubjects(selected, 'admin')).toEqual([
      { subject_type: 'user', subject_id: 'user-2', role: 'admin' },
      { subject_type: 'user', subject_id: 'user-1', role: 'admin' },
    ]);
  });

  it('filters candidates and normalizes role options for selects', () => {
    expect(
      filterWorkspaceMemberCandidates(
        [
          candidate({ id: 'user-1' }),
          candidate({ id: 'user-2', email: 'two@example.com' }),
        ],
        new Set(['user-1']),
      ).map((item) => item.id),
    ).toEqual(['user-2']);

    expect(
      workspaceRoleSelectOptions([
        { value: 'admin', label: 'Admin', description: 'Can manage members' },
        { value: 'member', label: 'Member', description: 'Can use workspace' },
      ]),
    ).toEqual([
      { value: 'admin', label: 'Admin' },
      { value: 'member', label: 'Member' },
    ]);
  });

  it('builds member keys and bulk payload subjects', () => {
    expect(workspaceMemberKey(member({ subject_id: 'user-1' }))).toBe(
      'user:user-1',
    );
    expect(workspaceMemberBulkSubject('user:user-1')).toEqual({
      subject_type: 'user',
      subject_id: 'user-1',
    });
    expect(
      workspaceMemberBulkSubjects(new Set(['user:user-1', 'user:user-2'])),
    ).toEqual([
      { subject_type: 'user', subject_id: 'user-1' },
      { subject_type: 'user', subject_id: 'user-2' },
    ]);
    expect(workspaceMemberBulkRoleSubjects(['user:user-1'], 'admin')).toEqual([
      { subject_type: 'user', subject_id: 'user-1', role: 'admin' },
    ]);
  });

  it('derives selectable member keys and toggles page selection', () => {
    const selectableKeys = selectableWorkspaceMemberKeys(
      [
        member({ subject_id: 'current-user' }),
        member({ subject_id: 'user-2' }),
        member({ subject_id: 'user-3' }),
      ],
      'current-user',
    );
    const pageKeys = Array.from(selectableKeys);

    expect(pageKeys).toEqual(['user:user-2', 'user:user-3']);
    expect(
      Array.from(
        activeWorkspaceMemberSelection(
          new Set(['user:user-2', 'user:off-page']),
          selectableKeys,
        ),
      ),
    ).toEqual(['user:user-2']);
    expect(
      workspaceMembersAllSelectableSelected(
        pageKeys,
        new Set(['user:user-2']),
      ),
    ).toBe(false);
    expect(
      Array.from(
        toggleWorkspaceMemberSelectionKey(new Set(['user:user-2']), 'user:user-2'),
      ),
    ).toEqual([]);

    const selectedPage = toggleWorkspaceMemberPageSelection(
      new Set(['user:off-page']),
      pageKeys,
      false,
    );

    expect(Array.from(selectedPage)).toEqual([
      'user:off-page',
      'user:user-2',
      'user:user-3',
    ]);
    expect(
      Array.from(toggleWorkspaceMemberPageSelection(selectedPage, pageKeys, true)),
    ).toEqual(['user:off-page']);
    expect(workspaceMembersAllSelectableSelected(pageKeys, selectedPage)).toBe(
      true,
    );
  });
});
