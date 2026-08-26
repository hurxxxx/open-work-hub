import { describe, expect, it } from 'vitest';

import type { AuthUser } from '@/src/platform/auth/auth-api';
import type { WorkspaceItem } from './admin-api';
import {
  activeWorkspaces,
  workspaceMembershipIdsForUser,
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
  description: 'Delivery',
  active: true,
  member_count: 0,
} as WorkspaceItem;

describe('admin user access model', () => {
  it('selects only active workspaces and preserves catalog order', () => {
    expect(
      activeWorkspaces([
        workspaceAlpha,
        { ...workspaceBeta, active: false },
      ]).map((workspace) => workspace.id),
    ).toEqual([workspaceAlpha.id]);
  });

  it('derives workspace membership IDs from the user projection', () => {
    expect(
      workspaceMembershipIdsForUser({
        workspaces: [
          {
            id: workspaceAlpha.id,
            slug: 'alpha',
            name: 'Alpha',
            role: 'member',
          },
        ],
      } as Pick<AuthUser, 'workspaces'>),
    ).toEqual([workspaceAlpha.id]);
  });
});
