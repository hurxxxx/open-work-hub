import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { apiFetchJson } from '@/src/platform/api/client';
import { listCompanyAppControls } from './admin-api';
import { AppsSection } from './admin-apps-section';
const state = vi.hoisted(() => ({
  reload: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
  t: (key: string) => key,
}));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: state.t }) }));
vi.mock('@open-work-hub/ui', async (original) => ({
  ...(await original<typeof import('@open-work-hub/ui')>()),
  useFeedback: () => state,
}));
vi.mock('@/src/platform/apps/app-bootstrap-context', () => ({
  useAppBootstrapContext: () => ({ reload: state.reload }),
}));
vi.mock('@/src/platform/api/client', () => ({ apiFetchJson: vi.fn() }));
vi.mock('./admin-api', () => ({ listCompanyAppControls: vi.fn() }));
vi.mock('@/src/platform/directory/DirectoryPicker', () => ({
  DirectoryPicker: ({
    kind,
    onChange,
    selectedIds,
  }: {
    kind: string;
    onChange: (ids: string[]) => void;
    selectedIds: string[];
  }) => (
    <button onClick={() => onChange([`${kind}-1`])}>
      {kind}:{selectedIds.join(',')}
    </button>
  ),
}));
const policy = (app_id = 'docs') => ({
  app_id,
  enabled: true,
  audience: 'selected',
  user_ids: [],
  group_ids: [],
});
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(listCompanyAppControls).mockResolvedValue({
    items: [
      { app_id: 'docs', title: 'Docs' },
      { app_id: 'pms', title: 'PMS' },
    ],
  } as Awaited<ReturnType<typeof listCompanyAppControls>>);
  vi.mocked(apiFetchJson).mockImplementation(async (path) =>
    policy(String(path).includes('/pms/') ? 'pms' : 'docs'),
  );
});
const renderPolicy = () =>
  render(
    <MemoryRouter>
      <AppsSection token="test-token" page="access" />
    </MemoryRouter>,
  );
describe('company app audience policy editor', () => {
  it('saves master setting and selected users/groups in one request then invalidates bootstrap', async () => {
    renderPolicy();
    await screen.findByRole('button', { name: 'people:' });
    expect(
      screen.getByRole('combobox', { name: /^companyAccess\.app$/ }),
    ).toBeTruthy();
    expect(
      screen.getByRole('combobox', {
        name: /^companyAccess\.audience$/,
      }),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'people:' }));
    fireEvent.click(screen.getByRole('button', { name: 'groups:' }));
    fireEvent.click(screen.getByLabelText('companyAccess.enabled'));
    fireEvent.click(screen.getByRole('button', { name: 'companyAccess.save' }));
    await waitFor(() =>
      expect(apiFetchJson).toHaveBeenCalledWith(
        '/api/v1/admin/apps/docs/access-policy',
        'test-token',
        {
          method: 'PUT',
          body: JSON.stringify({
            enabled: false,
            audience: 'selected',
            user_ids: ['people-1'],
            group_ids: ['groups-1'],
          }),
        },
      ),
    );
    expect(state.reload).toHaveBeenCalledTimes(1);
  });
  it('allows empty selected audiences with an explicit explanation', async () => {
    renderPolicy();
    await screen.findByRole('button', { name: 'companyAccess.save' });
    expect(screen.getByText('companyAccess.selectedRule')).toBeTruthy();
    expect(screen.getByText('companyAccess.resourceRule')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'companyAccess.save' }));
    await waitFor(() =>
      expect(apiFetchJson).toHaveBeenCalledWith(
        '/api/v1/admin/apps/docs/access-policy',
        'test-token',
        {
          method: 'PUT',
          body: JSON.stringify({
            enabled: true,
            audience: 'selected',
            user_ids: [],
            group_ids: [],
          }),
        },
      ),
    );
  });
  it('discards a previous app policy response after changing apps', async () => {
    let resolveOld!: (value: unknown) => void;
    vi.mocked(apiFetchJson).mockImplementation((path) =>
      String(path).includes('/docs/')
        ? new Promise((resolve) => {
            resolveOld = resolve;
          })
        : Promise.resolve({ ...policy('pms'), enabled: false }),
    );
    renderPolicy();
    await waitFor(() => expect(apiFetchJson).toHaveBeenCalledTimes(1));
    fireEvent.change(screen.getByLabelText('companyAccess.app'), {
      target: { value: 'pms' },
    });
    await screen.findByRole('button', { name: 'companyAccess.save' });
    expect(
      (screen.getByLabelText('companyAccess.enabled') as HTMLInputElement)
        .checked,
    ).toBe(false);
    await act(async () => resolveOld({ ...policy('docs'), enabled: true }));
    expect(
      (screen.getByLabelText('companyAccess.enabled') as HTMLInputElement)
        .checked,
    ).toBe(false);
  });
  it('clears grants when switching to all users and reports save failures', async () => {
    renderPolicy();
    await screen.findByRole('button', { name: 'groups:' });
    fireEvent.click(screen.getByRole('button', { name: 'groups:' }));
    fireEvent.change(screen.getByLabelText('companyAccess.audience'), {
      target: { value: 'all' },
    });
    vi.mocked(apiFetchJson).mockRejectedValueOnce(new Error('Save denied'));
    fireEvent.click(screen.getByRole('button', { name: 'companyAccess.save' }));
    await waitFor(() =>
      expect(state.error).toHaveBeenCalledWith('Save denied'),
    );
    expect(state.reload).not.toHaveBeenCalled();
    expect(apiFetchJson).toHaveBeenLastCalledWith(
      '/api/v1/admin/apps/docs/access-policy',
      'test-token',
      {
        method: 'PUT',
        body: JSON.stringify({
          enabled: true,
          audience: 'all',
          user_ids: [],
          group_ids: [],
        }),
      },
    );
  });
});
