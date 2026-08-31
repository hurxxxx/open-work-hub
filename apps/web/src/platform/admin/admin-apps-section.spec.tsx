import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  listCompanyAppControls,
  listWorkspaceAppDefaults,
  listWorkspaceAppOverrides,
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
  listCompanyAppControls: vi.fn(),
  listWorkspaceAppDefaults: vi.fn(),
  listWorkspaceAppOverrides: vi.fn(),
  listWorkspaces: vi.fn(),
}));

beforeEach(() => {
  vi.mocked(listCompanyAppControls).mockResolvedValue({ items: [] });
  vi.mocked(listWorkspaceAppDefaults).mockResolvedValue({
    items: [
      {
        app_id: 'workspace-default-app',
        company_enabled: true,
        enabled: true,
        execution_context_kind: 'workspace',
        icon_key: 'box',
        route_base: '/apps/workspace-default-app',
        runtime_enabled: true,
        title: 'Workspace default app',
        updated_at: null,
      },
    ],
  });
  vi.mocked(listWorkspaces).mockResolvedValue([]);
  vi.mocked(listWorkspaceAppOverrides).mockResolvedValue({
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
    expect(listWorkspaceAppDefaults).toHaveBeenCalledWith('test-token');
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
    vi.mocked(listWorkspaceAppOverrides).mockResolvedValue({
      items: [
        {
          app_id: 'workspace-override-app',
          company_enabled: true,
          default_enabled: true,
          effective_enabled: true,
          execution_context_kind: 'workspace',
          icon_key: 'box',
          route_base: '/apps/workspace-override-app',
          runtime_enabled: true,
          title: 'Workspace override app',
          updated_at: null,
          override_enabled: null,
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
        name: 'admin.console.apps.controls.overridesTab',
      }),
      { button: 0, ctrlKey: false },
    );

    expect(await screen.findByText('workspace-override-app')).toBeTruthy();
    expect(
      screen.getByRole('combobox', {
        name: 'admin.console.apps.controls.overrideSelect',
      }),
    ).toBeTruthy();
    expect(screen.getByLabelText('location').textContent).toBe(
      '?tab=overrides',
    );
    expect(listWorkspaces).toHaveBeenCalledWith('test-token');
    expect(listWorkspaceAppOverrides).toHaveBeenCalledWith(
      'test-token',
      'workspace-1',
    );
  });

  it('restores the selected override workspace from the URL after a remount', async () => {
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
      {
        active: true,
        created_at: null,
        description: '',
        doc_count: 0,
        id: 'workspace-2',
        key: 'workspace-two',
        meeting_count: 0,
        member_count: 3,
        name: 'Workspace Two',
        team_count: 0,
        updated_at: null,
      },
    ]);
    vi.mocked(listWorkspaceAppOverrides).mockImplementation(
      async (_token, workspaceId) => ({
        items: [],
        workspace_id: workspaceId,
        workspace_key: workspaceId,
        workspace_name: workspaceId,
      }),
    );

    renderWorkspaceApps(
      '/admin/apps/workspace?tab=overrides&workspace=workspace-2',
    );

    expect(
      await screen.findByRole('heading', { name: 'Workspace Two' }),
    ).toBeTruthy();
    expect(listWorkspaceAppOverrides).toHaveBeenCalledWith(
      'test-token',
      'workspace-2',
    );
    expect(screen.getByLabelText('location').textContent).toBe(
      '?tab=overrides&workspace=workspace-2',
    );

    fireEvent.click(
      screen.getByRole('button', { name: /Workspace One workspace-one/ }),
    );
    expect(screen.getByLabelText('location').textContent).toBe(
      '?tab=overrides&workspace=workspace-1',
    );
    await screen.findByRole('heading', { name: 'Workspace One' });
    expect(listWorkspaceAppOverrides).toHaveBeenCalledWith(
      'test-token',
      'workspace-1',
    );
  });
});
