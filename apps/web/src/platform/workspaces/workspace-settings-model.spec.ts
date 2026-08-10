import { describe, expect, it } from 'vitest';

import type { WorkspaceItem } from '@/src/platform/admin/admin-api';
import type { AuthUser, WorkspaceSummary } from '@/src/platform/auth/auth-api';
import {
  INITIAL_WORKSPACE_SETTINGS_STATE,
  buildWorkspaceDetailCapabilities,
  buildWorkspaceSettingsTitle,
  canManageWorkspaceSettings,
  selectCurrentWorkspaceSummary,
  shouldLoadWorkspaceSettings,
  workspaceSettingsReducer,
} from './workspace-settings-model';

function workspace(overrides: Partial<WorkspaceItem> = {}): WorkspaceItem {
  return {
    active: true,
    created_at: null,
    description: 'Workspace description',
    doc_count: 0,
    id: 'workspace-hq',
    key: 'hq',
    meeting_count: 0,
    member_count: 0,
    name: 'HQ',
    team_count: 0,
    updated_at: null,
    ...overrides,
  };
}

function summary(overrides: Partial<WorkspaceSummary> = {}): WorkspaceSummary {
  return {
    id: 'workspace-hq',
    slug: 'hq',
    name: 'HQ Summary',
    role: 'member',
    ...overrides,
  };
}

function user(overrides: Partial<AuthUser> = {}): AuthUser {
  return {
    id: 'user-1',
    login_id: 'member',
    email: 'member@ai-do.local',
    full_name: 'AI-DO Member',
    display_name: 'AI-DO Member',
    status: 'active',
    theme_preference: 'system',
    locale: 'ko-KR',
    time_zone: 'Asia/Seoul',
    date_format: 'korean',
    primary_org_unit: null,
    workspaces: [summary()],
    workspace_roles: [],
    system_roles: [],
    must_change_password: false,
    ...overrides,
  };
}

describe('workspaceSettingsReducer', () => {
  it('projects load transitions without clearing messages except where existing behavior does', () => {
    const withMessage = {
      ...INITIAL_WORKSPACE_SETTINGS_STATE,
      message: 'Saved',
    };

    expect(
      workspaceSettingsReducer(withMessage, { type: 'load-started' }),
    ).toEqual({
      ...withMessage,
      loading: true,
      error: null,
    });

    expect(
      workspaceSettingsReducer(withMessage, {
        type: 'load-succeeded',
        workspace: workspace({ name: 'Loaded HQ' }),
      }),
    ).toEqual({
      ...withMessage,
      workspace: workspace({ name: 'Loaded HQ' }),
      loading: false,
    });

    expect(
      workspaceSettingsReducer(withMessage, {
        type: 'load-failed',
        error: 'Could not load',
      }),
    ).toEqual({
      ...withMessage,
      loading: false,
      error: 'Could not load',
    });
  });

  it('projects skip, workspace change, and flash transitions', () => {
    const loadedWorkspace = workspace({ name: 'Loaded HQ' });
    const base = {
      ...INITIAL_WORKSPACE_SETTINGS_STATE,
      workspace: loadedWorkspace,
      loading: true,
      error: 'Previous error',
      message: 'Previous message',
    };

    expect(workspaceSettingsReducer(base, { type: 'load-skipped' })).toEqual({
      ...base,
      loading: false,
    });
    expect(
      workspaceSettingsReducer(base, {
        type: 'workspace-changed',
        workspace: workspace({ name: 'Changed HQ' }),
      }),
    ).toEqual({
      ...base,
      workspace: workspace({ name: 'Changed HQ' }),
    });
    expect(
      workspaceSettingsReducer(base, {
        type: 'flash-success',
        message: 'Saved',
      }),
    ).toEqual({
      ...base,
      error: null,
      message: 'Saved',
    });
    expect(workspaceSettingsReducer(base, { type: 'clear-message' })).toEqual({
      ...base,
      message: null,
    });
    expect(
      workspaceSettingsReducer(base, {
        type: 'flash-error',
        error: 'Save failed',
      }),
    ).toEqual({
      ...base,
      message: null,
      error: 'Save failed',
    });
  });
});

describe('workspace settings selectors', () => {
  it('selects the current workspace summary by slug', () => {
    expect(
      selectCurrentWorkspaceSummary(
        [
          summary({ slug: 'alpha', name: 'Alpha' }),
          summary({ slug: 'hq', name: 'HQ' }),
        ],
        'hq',
      ),
    ).toEqual(summary({ name: 'HQ' }));

    expect(selectCurrentWorkspaceSummary(undefined, 'hq')).toBeNull();
    expect(selectCurrentWorkspaceSummary([summary()], undefined)).toBeNull();
  });

  it('allows settings access for platform admins and workspace admins', () => {
    expect(
      canManageWorkspaceSettings(
        user({ system_roles: ['platform_admin'], workspaces: [] }),
        'missing',
        null,
      ),
    ).toBe(true);

    expect(
      canManageWorkspaceSettings(
        user({
          workspaces: [summary({ role: 'admin' })],
        }),
        'hq',
        summary({ role: 'admin' }),
      ),
    ).toBe(true);

    expect(
      canManageWorkspaceSettings(user(), 'hq', summary({ role: 'member' })),
    ).toBe(false);
  });

  it('skips loading when token, slug, or manage access is missing', () => {
    expect(
      shouldLoadWorkspaceSettings({
        token: 'token',
        workspaceSlug: 'hq',
        canManageWorkspace: true,
      }),
    ).toBe(true);

    expect(
      shouldLoadWorkspaceSettings({
        token: null,
        workspaceSlug: 'hq',
        canManageWorkspace: true,
      }),
    ).toBe(false);
    expect(
      shouldLoadWorkspaceSettings({
        token: 'token',
        workspaceSlug: undefined,
        canManageWorkspace: true,
      }),
    ).toBe(false);
    expect(
      shouldLoadWorkspaceSettings({
        token: 'token',
        workspaceSlug: 'hq',
        canManageWorkspace: false,
      }),
    ).toBe(false);
  });

  it('builds the settings title from workspace, summary, then slug', () => {
    expect(
      buildWorkspaceSettingsTitle({
        workspace: workspace({ name: 'Loaded workspace' }),
        summary: summary({ name: 'Summary workspace' }),
        workspaceSlug: 'hq',
      }),
    ).toBe('Loaded workspace');
    expect(
      buildWorkspaceSettingsTitle({
        workspace: null,
        summary: summary({ name: 'Summary workspace' }),
        workspaceSlug: 'hq',
      }),
    ).toBe('Summary workspace');
    expect(
      buildWorkspaceSettingsTitle({
        workspace: null,
        summary: null,
        workspaceSlug: 'hq',
      }),
    ).toBe('hq');
  });

  it('builds workspace detail capabilities with archive and delete disabled', () => {
    expect(
      buildWorkspaceDetailCapabilities({ canBrowseDirectory: true }),
    ).toEqual({
      canEditProfile: true,
      canManageMembers: true,
      canArchive: false,
      canDelete: false,
      canBrowseDirectory: true,
    });
    expect(
      buildWorkspaceDetailCapabilities({ canBrowseDirectory: false }),
    ).toEqual({
      canEditProfile: true,
      canManageMembers: true,
      canArchive: false,
      canDelete: false,
      canBrowseDirectory: false,
    });
  });
});
