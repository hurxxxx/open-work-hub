import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { apiFetchJson } from '@/src/platform/api/client';
import { createAuthUser } from '../../../tests/fixtures/company';
import { UserGroupsDialog } from './admin-user-groups-dialog';

const mock = vi.hoisted(() => ({
  t: (key: string) => key,
  confirm: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
}));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: mock.t }) }));
vi.mock('@open-work-hub/ui', async (original) => ({
  ...(await original<typeof import('@open-work-hub/ui')>()),
  useFeedback: () => mock,
  useConfirm: () => ({ confirm: mock.confirm, confirmDialog: null }),
}));
vi.mock('@/src/platform/api/client', () => ({ apiFetchJson: vi.fn() }));

const api = vi.mocked(apiFetchJson);
const local = {
  id: 'local',
  name: 'Project team',
  source: 'local',
  active: true,
};
const hr = { id: 'hr', name: 'HR team', source: 'hr', active: true };
beforeEach(() => {
  vi.clearAllMocks();
  api.mockImplementation(async (path, _token, init) => {
    if (init?.method) return {};
    return {
      items: path.includes('member_user_id=')
        ? [local, hr]
        : [local, { ...local, id: 'other', name: 'New team' }],
      total: 2,
      page: 1,
      page_size: 20,
    };
  });
});
function open(user = createAuthUser({ id: 'person' })) {
  const onEditUser = vi.fn();
  render(
    <UserGroupsDialog
      token="test-token"
      user={user}
      onChanged={vi.fn()}
      onClose={vi.fn()}
      onEditUser={onEditUser}
    />,
  );
  return onEditUser;
}
it('changes only the selected membership and routes HR changes to the user editor', async () => {
  const onEditUser = open();
  fireEvent.click(
    await screen.findByRole('button', { name: 'companyGroups.addMember' }),
  );
  await waitFor(() =>
    expect(api).toHaveBeenCalledWith(
      '/api/v1/admin/groups/other/members/person',
      'test-token',
      { method: 'PUT', body: JSON.stringify({ assigned: true }) },
    ),
  );
  fireEvent.click(
    await screen.findByRole('button', { name: 'companyGroups.editAssignment' }),
  );
  expect(onEditUser).toHaveBeenCalledOnce();
});
it('confirms removal and keeps assignments on cancel', async () => {
  open();
  mock.confirm.mockResolvedValueOnce(false).mockResolvedValueOnce(true);
  fireEvent.click(
    await screen.findByRole('button', { name: 'companyGroups.removeMember' }),
  );
  await waitFor(() => expect(mock.confirm).toHaveBeenCalledOnce());
  expect(api.mock.calls.some((call) => call[2]?.method === 'PUT')).toBe(false);
  await waitFor(() =>
    expect(
      screen
        .getByRole('button', { name: 'companyGroups.removeMember' })
        .hasAttribute('disabled'),
    ).toBe(false),
  );
  fireEvent.click(
    screen.getByRole('button', { name: 'companyGroups.removeMember' }),
  );
  await waitFor(() =>
    expect(api).toHaveBeenCalledWith(
      '/api/v1/admin/groups/local/members/person',
      'test-token',
      { method: 'PUT', body: JSON.stringify({ assigned: false }) },
    ),
  );
});
it('preserves removal but disables new assignments for suspended users', async () => {
  open(createAuthUser({ id: 'person', status: 'suspended' }));
  expect(
    (
      await screen.findByRole('button', { name: 'companyGroups.addMember' })
    ).hasAttribute('disabled'),
  ).toBe(true);
  expect(
    screen
      .getByRole('button', { name: 'companyGroups.removeMember' })
      .hasAttribute('disabled'),
  ).toBe(false);
});
