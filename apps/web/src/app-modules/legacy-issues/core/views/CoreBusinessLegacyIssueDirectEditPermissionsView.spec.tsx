import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { CoreBusinessLegacyIssueDirectEditPermissionsView } from './CoreBusinessLegacyIssueDirectEditPermissionsView';

const mocks = vi.hoisted(() => {
  const toastError = vi.fn();
  const toastSuccess = vi.fn();
  return {
    fetchEditors: vi.fn(),
    grantEditor: vi.fn(),
    listWorkspaceMembers: vi.fn(),
    revokeEditor: vi.fn(),
    toast: {
      error: toastError,
      success: toastSuccess,
    },
    toastError,
    toastSuccess,
    translate: (key: string) => key,
  };
});

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: mocks.translate,
  }),
}));

vi.mock('@open-alm/ui', () => ({
  useToast: () => mocks.toast,
}));

vi.mock('@/src/platform/auth/auth-provider', () => ({
  useAuth: () => ({
    token: 'token',
    user: {
      id: 'admin',
      system_roles: ['platform_admin'],
      workspaces: [{ role: 'admin', slug: 'research' }],
    },
  }),
}));

vi.mock('@/src/platform/workspaces/workspace-bootstrap-context', () => ({
  useWorkspaceBootstrapContext: () => ({
    data: {
      nav: [
        { id: 'legacy-issues-aircon' },
        { id: 'legacy-issues-heat-exchanger' },
        { id: 'legacy-issues-interior' },
      ],
      workspace: { id: 'workspace-1' },
    },
  }),
}));

vi.mock('@/src/platform/admin/admin-api', () => ({
  listWorkspaceMembers: mocks.listWorkspaceMembers,
}));

vi.mock('../api/legacy-issue-direct-edit-permissions-api', () => ({
  fetchLegacyIssueModuleDirectEditors: mocks.fetchEditors,
  grantLegacyIssueModuleDirectEditor: mocks.grantEditor,
  revokeLegacyIssueModuleDirectEditor: mocks.revokeEditor,
}));

describe('CoreBusinessLegacyIssueDirectEditPermissionsView', () => {
  beforeEach(() => {
    mocks.fetchEditors.mockReset();
    mocks.grantEditor.mockReset();
    mocks.listWorkspaceMembers.mockReset();
    mocks.revokeEditor.mockReset();
    mocks.toastError.mockReset();
    mocks.toastSuccess.mockReset();
    mocks.fetchEditors.mockResolvedValue({
      items: [
        {
          can_revoke: true,
          active_member: true,
          created_at: '2026-07-23T00:00:00Z',
          display_name: '홍길동',
          email: 'hong@example.com',
          id: 'rule-1',
          module_key: 'aircon',
          role: 'editor',
          updated_at: '2026-07-23T00:00:00Z',
          user_id: 'user-1',
        },
        {
          can_revoke: true,
          active_member: true,
          created_at: '2026-07-23T00:00:00Z',
          display_name: '김영희',
          email: 'kim@example.com',
          id: 'rule-2',
          module_key: 'interior',
          role: 'editor',
          updated_at: '2026-07-23T00:00:00Z',
          user_id: 'user-2',
        },
      ],
    });
    mocks.listWorkspaceMembers.mockResolvedValue({ items: [] });
  });

  it('loads and displays every visible module in one view', async () => {
    renderView();

    expect(
      await screen.findByRole('heading', {
        name: 'shell:nav.legacy-issues-aircon',
      }),
    ).toBeTruthy();
    expect(
      screen.getByRole('heading', {
        name: 'shell:nav.legacy-issues-heat-exchanger',
      }),
    ).toBeTruthy();
    expect(
      screen.getByRole('heading', {
        name: 'shell:nav.legacy-issues-interior',
      }),
    ).toBeTruthy();
    expect(screen.getByText('홍길동')).toBeTruthy();
    expect(screen.getByText('김영희')).toBeTruthy();
    expect(
      screen.queryByLabelText(
        'coreBusiness.directEditPermissions.selectedModule',
      ),
    ).toBeNull();
    expect(mocks.fetchEditors).toHaveBeenCalledTimes(1);
    expect(mocks.fetchEditors).toHaveBeenCalledWith({
      token: 'token',
      workspaceSlug: 'research',
    });
  });

  it('grants a searched user to the module whose card was used', async () => {
    mocks.listWorkspaceMembers.mockResolvedValue({
      items: [
        {
          subject_id: 'user-3',
          subject_label: '박추가',
          subject_secondary: 'park@example.com',
          subject_type: 'user',
          user_status: 'active',
        },
      ],
    });
    mocks.grantEditor.mockResolvedValue({
      can_revoke: true,
      active_member: true,
      created_at: '2026-07-23T00:00:00Z',
      display_name: '박추가',
      email: 'park@example.com',
      id: 'rule-3',
      module_key: 'interior',
      role: 'editor',
      updated_at: '2026-07-23T00:00:00Z',
      user_id: 'user-3',
    });
    renderView();

    await screen.findByRole('heading', {
      name: 'shell:nav.legacy-issues-interior',
    });
    const searchInputs = screen.getAllByLabelText(
      'coreBusiness.directEditPermissions.searchPlaceholder',
    );
    const interiorSearchInput = searchInputs.at(2);
    expect(interiorSearchInput).toBeDefined();
    if (!interiorSearchInput) return;
    fireEvent.focus(interiorSearchInput);
    fireEvent.change(interiorSearchInput, { target: { value: '박추가' } });

    await waitFor(() => {
      expect(mocks.listWorkspaceMembers).toHaveBeenLastCalledWith(
        'token',
        'workspace-1',
        {
          page: 1,
          pageSize: 30,
          q: '박추가',
          subjectType: 'user',
        },
      );
    });
    fireEvent.click(
      await screen.findByRole('button', {
        name: /박추가/,
      }),
    );

    await waitFor(() => {
      expect(mocks.grantEditor).toHaveBeenCalledWith({
        moduleKey: 'interior',
        token: 'token',
        userId: 'user-3',
        workspaceSlug: 'research',
      });
    });
    expect(await screen.findByText('park@example.com')).toBeTruthy();
  });
});

function renderView() {
  return render(
    <MemoryRouter
      initialEntries={[
        '/w/research/legacy-issues/settings/direct-edit-permissions',
      ]}
    >
      <Routes>
        <Route
          path="/w/:workspaceSlug/legacy-issues/settings/direct-edit-permissions"
          element={<CoreBusinessLegacyIssueDirectEditPermissionsView />}
        />
      </Routes>
    </MemoryRouter>,
  );
}
