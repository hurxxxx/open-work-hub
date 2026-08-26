import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  listAdminAppBarCategories,
  listPlatformAppVisibility,
  listWorkspaceAppVisibility,
  listWorkspaces,
} from './admin-api';
import { AppsSection } from './admin-apps-section';

const testContext = vi.hoisted(() => ({
  reload: vi.fn(),
  reloadGlobalApps: vi.fn(),
  t: (key: string, options?: { defaultValue?: string }) =>
    options?.defaultValue ?? key,
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: testContext.t,
  }),
}));

vi.mock('@open-work-hub/ui', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@open-work-hub/ui')>()),
  useFeedback: () => ({ error: vi.fn(), success: vi.fn() }),
}));

vi.mock('@/src/platform/workspaces/workspace-bootstrap-context', () => ({
  useWorkspaceBootstrapContext: () => ({
    reload: testContext.reload,
    reloadGlobalApps: testContext.reloadGlobalApps,
  }),
}));

vi.mock('./admin-api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./admin-api')>()),
  listAdminAppBarCategories: vi.fn(),
  listPlatformAppVisibility: vi.fn(),
  listWorkspaceAppVisibility: vi.fn(),
  listWorkspaces: vi.fn(),
}));

beforeEach(() => {
  vi.mocked(listAdminAppBarCategories).mockResolvedValue({
    available_apps: [],
    categories: [],
    icon_keys: [],
  });
  vi.mocked(listPlatformAppVisibility).mockResolvedValue({
    items: [
      {
        app_id: 'workspace-default-app',
        availability_scope: 'workspace',
        icon_key: 'box',
        kind: 'launcher_app',
        launcher_personal_tools: false,
        route_base: '/workspace-default-app',
        runtime_enabled: true,
        title: 'Workspace default app',
        updated_at: null,
        visible: true,
        visible_workspace_count: 0,
        visible_workspaces: [],
      },
    ],
  });
  vi.mocked(listWorkspaces).mockResolvedValue([]);
  vi.mocked(listWorkspaceAppVisibility).mockResolvedValue({
    items: [],
    workspace_id: 'unused',
    workspace_key: 'unused',
    workspace_name: 'Unused',
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('AppsSection workspace app defaults', () => {
  function LocationProbe() {
    return <output aria-label="location">{useLocation().search}</output>;
  }

  function renderWorkspaceApps(initialEntry: string) {
    return render(
      <MemoryRouter initialEntries={[initialEntry]}>
        <AppsSection page="workspace" token="test-token" />
        <LocationProbe />
      </MemoryRouter>,
    );
  }

  it('shows workspace app company defaults on the defaults tab', async () => {
    renderWorkspaceApps('/admin/apps/workspace?tab=defaults');

    expect(await screen.findByText('workspace-default-app')).toBeTruthy();
    expect(listPlatformAppVisibility).toHaveBeenCalledWith('test-token');
  });

  it('switches to workspace-specific overrides and keeps the tab in the URL', async () => {
    vi.mocked(listWorkspaces).mockResolvedValue([
      {
        active: true,
        created_at: null,
        description: '',
        doc_count: 0,
        id: 'workspace-1',
        key: 'workspace-one',
        meeting_count: 0,
        member_count: 2,
        name: 'Workspace One',
        team_count: 0,
        updated_at: null,
      },
    ]);
    vi.mocked(listWorkspaceAppVisibility).mockResolvedValue({
      items: [
        {
          app_id: 'workspace-override-app',
          availability_scope: 'workspace',
          effective_visible: true,
          icon_key: 'box',
          kind: 'launcher_app',
          platform_visible: true,
          route_base: '/workspace-override-app',
          runtime_enabled: true,
          title: 'Workspace override app',
          updated_at: null,
          visibility_override: null,
        },
      ],
      workspace_id: 'workspace-1',
      workspace_key: 'workspace-one',
      workspace_name: 'Workspace One',
    });
    renderWorkspaceApps('/admin/apps/workspace?tab=defaults');
    await screen.findByText('workspace-default-app');

    fireEvent.mouseDown(
      screen.getByRole('tab', {
        name: 'admin.console.apps.workspaceOverridesTab',
      }),
      { button: 0, ctrlKey: false },
    );

    expect(await screen.findByText('workspace-override-app')).toBeTruthy();
    expect(screen.getByLabelText('location').textContent).toBe(
      '?tab=overrides',
    );
    expect(listWorkspaces).toHaveBeenCalledWith('test-token');
    expect(listWorkspaceAppVisibility).toHaveBeenCalledWith(
      'test-token',
      'workspace-1',
    );
  });
});
