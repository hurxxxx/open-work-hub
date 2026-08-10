import { describe, expect, it } from 'vitest';

import type { WorkspaceBindingItem, WorkspaceItem } from './admin-api';
import {
  addWorkspaceMembershipIds,
  directWorkspaceIdsForUser,
  formatWorkspaceSelectionSummary,
  removeWorkspaceMembershipId,
  selectedWorkspaceMemberships,
  workspaceMembershipAddCandidates,
  workspaceBindingReplacementPayloadForUser,
} from './admin-user-access-model';

const workspaceAlpha = {
  id: 'workspace-alpha',
  key: 'alpha',
  name: 'Alpha',
  description: '',
  active: true,
  member_count: 0,
} as WorkspaceItem;

const workspaceBeta = {
  id: 'workspace-beta',
  key: 'beta',
  name: 'Beta',
  description: '',
  active: true,
  member_count: 0,
} as WorkspaceItem;

describe('admin user access model', () => {
  it('summarizes selected workspaces in workspace order', () => {
    expect(
      formatWorkspaceSelectionSummary(
        [workspaceAlpha, workspaceBeta],
        [workspaceBeta.id, workspaceAlpha.id],
      ),
    ).toBe('Alpha, Beta');
    expect(formatWorkspaceSelectionSummary([workspaceAlpha], [])).toBe('-');
  });

  it('returns selected workspace memberships in workspace order', () => {
    expect(
      selectedWorkspaceMemberships(
        [workspaceAlpha, workspaceBeta],
        [workspaceBeta.id, workspaceAlpha.id],
      ).map((workspace) => workspace.id),
    ).toEqual([workspaceAlpha.id, workspaceBeta.id]);
  });

  it('filters add candidates by current memberships and workspace query', () => {
    expect(
      workspaceMembershipAddCandidates(
        [workspaceAlpha, workspaceBeta],
        [workspaceAlpha.id],
        '',
      ),
    ).toEqual([workspaceBeta]);
    expect(
      workspaceMembershipAddCandidates(
        [workspaceAlpha, workspaceBeta],
        [],
        'bet',
      ),
    ).toEqual([workspaceBeta]);
    expect(
      workspaceMembershipAddCandidates(
        [workspaceAlpha, workspaceBeta],
        [],
        'alpha',
      ),
    ).toEqual([workspaceAlpha]);
  });

  it('adds and removes workspace membership ids without duplicates', () => {
    expect(
      addWorkspaceMembershipIds(
        [workspaceAlpha.id],
        [workspaceBeta.id, workspaceAlpha.id],
      ),
    ).toEqual([workspaceAlpha.id, workspaceBeta.id]);
    expect(
      removeWorkspaceMembershipId(
        [workspaceAlpha.id, workspaceBeta.id],
        workspaceAlpha.id,
      ),
    ).toEqual([workspaceBeta.id]);
  });

  it('derives direct workspace IDs from user bindings only', () => {
    const bindings = [
      {
        subject_type: 'team',
        subject_id: 'user-1',
        role: 'admin',
      },
      {
        subject_type: 'user',
        subject_id: 'user-1',
        role: 'member',
      },
    ] as WorkspaceBindingItem[];

    expect(
      directWorkspaceIdsForUser(
        [
          { workspace: workspaceAlpha, bindings },
          { workspace: workspaceBeta, bindings: [] },
        ],
        'user-1',
      ),
    ).toEqual([workspaceAlpha.id]);
  });

  it('builds workspace replacement payloads preserving existing user roles', () => {
    const bindings = [
      { subject_type: 'user', subject_id: 'other-user', role: 'admin' },
      { subject_type: 'team', subject_id: 'team-1', role: 'member' },
      { subject_type: 'user', subject_id: 'user-1', role: 'owner' },
    ] as WorkspaceBindingItem[];

    expect(
      workspaceBindingReplacementPayloadForUser(bindings, 'user-1', true),
    ).toEqual({
      users: [
        { subject_id: 'other-user', role: 'admin' },
        { subject_id: 'user-1', role: 'owner' },
      ],
    });
    expect(
      workspaceBindingReplacementPayloadForUser([], 'user-1', true),
    ).toEqual({
      users: [{ subject_id: 'user-1', role: 'member' }],
    });
    expect(
      workspaceBindingReplacementPayloadForUser(bindings, 'user-1', false),
    ).toEqual({
      users: [{ subject_id: 'other-user', role: 'admin' }],
    });
  });
});
