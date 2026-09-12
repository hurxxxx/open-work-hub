import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { apiFetchJson } from '@/src/platform/api/client';
import { MemoryRouter } from 'react-router-dom';
import { GroupsSection } from './admin-groups-section';
const mock = vi.hoisted(() => ({
  t: (key: string, values?: { name?: string }) =>
    key === 'companyGroups.removeNamedMember' ? `Remove ${values?.name}` : key,
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
vi.mock('@/src/platform/directory/DirectoryPicker', () => ({
  DirectoryPicker: ({
    selectedIds,
    onChange,
    disabled,
    single,
  }: {
    selectedIds: string[];
    onChange: (ids: string[]) => void;
    disabled?: boolean;
    single?: boolean;
  }) => (
    <button
      disabled={disabled}
      onClick={() => onChange(selectedIds.filter((id) => id !== 'b'))}
    >
      {single ? 'Choose head' : 'Remove B'}
    </button>
  ),
}));
const group = {
  id: 'group',
  name: 'Review group',
  description: '',
  active: true,
  source: 'local',
  membership_mode: 'manual',
};
const api = vi.mocked(apiFetchJson);
beforeEach(() => {
  vi.clearAllMocks();
  api.mockImplementation(async (path, _token, init) => {
    if (init?.method) return group;
    if (path.includes('/members'))
      return {
        user_ids: ['b', 'c'],
        items: [
          {
            id: 'b',
            display_name: 'B',
            login_id: 'bee',
            status: 'active',
            login_blocked: false,
          },
          {
            id: 'c',
            display_name: 'C',
            login_id: 'cee',
            status: 'suspended',
            login_blocked: false,
          },
        ],
      };
    return { items: [group], total: 1, page: 1, page_size: 50 };
  });
});
async function openGroup() {
  render(
    <MemoryRouter>
      <GroupsSection token="test-token" />
    </MemoryRouter>,
  );
  fireEvent.click(await screen.findByRole('button', { name: 'Review group' }));
  await screen.findByText('B');
}
describe('manual group revocation confirmation', () => {
  it('cancels member removal without a request, then persists confirmed removal', async () => {
    await openGroup();
    fireEvent.click(screen.getByRole('button', { name: 'Remove B' }));
    mock.confirm.mockResolvedValueOnce(false);
    fireEvent.click(
      screen.getByRole('button', { name: 'companyGroups.saveMembers' }),
    );
    await waitFor(() => expect(mock.confirm).toHaveBeenCalledTimes(1));
    expect(api.mock.calls.some(([, , init]) => init?.method === 'PUT')).toBe(
      false,
    );
    await waitFor(() =>
      expect(
        screen
          .getByRole('button', { name: 'companyGroups.saveMembers' })
          .hasAttribute('disabled'),
      ).toBe(false),
    );
    mock.confirm.mockResolvedValueOnce(true);
    fireEvent.click(
      screen.getByRole('button', { name: 'companyGroups.saveMembers' }),
    );
    await waitFor(() =>
      expect(api).toHaveBeenCalledWith(
        '/api/v1/admin/groups/group/members',
        'test-token',
        { method: 'PUT', body: JSON.stringify({ user_ids: ['c'] }) },
      ),
    );
    expect(mock.confirm).toHaveBeenCalledWith(
      expect.objectContaining({
        description: 'companyGroups.removeMembersNotice',
        variant: 'danger',
      }),
    );
  });
  it('requires confirmation to deactivate a group and leaves the server unchanged on cancel', async () => {
    await openGroup();
    fireEvent.click(
      screen.getByRole('checkbox', { name: 'companyGroups.active' }),
    );
    mock.confirm.mockResolvedValueOnce(false);
    fireEvent.click(
      screen.getByRole('button', { name: 'companyGroups.saveDetails' }),
    );
    await waitFor(() => expect(mock.confirm).toHaveBeenCalledTimes(1));
    expect(api.mock.calls.some(([, , init]) => init?.method === 'PATCH')).toBe(
      false,
    );
    await waitFor(() =>
      expect(
        screen
          .getByRole('button', { name: 'companyGroups.saveDetails' })
          .hasAttribute('disabled'),
      ).toBe(false),
    );
    mock.confirm.mockResolvedValueOnce(true);
    fireEvent.click(
      screen.getByRole('button', { name: 'companyGroups.saveDetails' }),
    );
    await waitFor(() =>
      expect(api).toHaveBeenCalledWith(
        '/api/v1/admin/groups/group',
        'test-token',
        {
          method: 'PATCH',
          body: JSON.stringify({
            name: 'Review group',
            description: '',
            active: false,
          }),
        },
      ),
    );
  });
  it('allows HR group metadata editing while protecting derived members', async () => {
    api.mockImplementation(async (path) =>
      path.includes('/members')
        ? {
            user_ids: ['b'],
            items: [
              {
                id: 'b',
                display_name: 'B',
                login_id: 'bee',
                status: 'active',
                login_blocked: false,
              },
            ],
          }
        : {
            items: [
              {
                ...group,
                source: 'hr',
                membership_mode: 'hr_assignment',
                slug: 'review',
                unit_type: 'department',
              },
            ],
            total: 1,
            page: 1,
            page_size: 50,
          },
    );
    await openGroup();
    expect(screen.queryByRole('button', { name: 'Remove B' })).toBeNull();
    expect(
      screen.queryByRole('button', { name: 'companyGroups.addMembers' }),
    ).toBeNull();
    expect(
      screen.queryByRole('button', { name: 'companyGroups.saveMembers' }),
    ).toBeNull();
    expect(
      screen.getByRole('button', { name: 'companyGroups.saveDetails' }),
    ).toBeTruthy();
  });
});

it('clears results on a failed source change and retries that source', async () => {
  render(
    <MemoryRouter>
      <GroupsSection token="test-token" />
    </MemoryRouter>,
  );
  await screen.findByRole('button', { name: 'Review group' });
  api.mockRejectedValueOnce(new Error('Group loading failed'));
  fireEvent.change(
    screen.getByRole('combobox', { name: 'companyGroups.source' }),
    { target: { value: 'hr' } },
  );
  await screen.findByRole('alert');
  expect(screen.queryByRole('button', { name: 'Review group' })).toBeNull();
  expect(screen.queryByText('directory.noResults')).toBeNull();
  api.mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 50 });
  fireEvent.click(screen.getByRole('button', { name: 'directory.retry' }));
  await screen.findByText('directory.noResults');
  expect(api.mock.calls.at(-1)?.[0]).toContain('source=hr');
});

it('ignores an old list response after changing the source filter', async () => {
  let finishOld: ((value: unknown) => void) | undefined;
  api.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finishOld = resolve;
      }),
  );
  render(
    <MemoryRouter>
      <GroupsSection token="test-token" />
    </MemoryRouter>,
  );
  await waitFor(() => expect(api).toHaveBeenCalledTimes(1));
  api.mockResolvedValueOnce({
    items: [
      {
        ...group,
        id: 'hr',
        name: 'HR group',
        source: 'hr',
        membership_mode: 'hr_assignment',
      },
    ],
    total: 1,
    page: 1,
    page_size: 50,
  });
  fireEvent.change(
    screen.getByRole('combobox', { name: 'companyGroups.source' }),
    { target: { value: 'hr' } },
  );
  await screen.findByRole('button', { name: 'HR group' });
  await act(async () =>
    finishOld?.({ items: [group], total: 1, page: 1, page_size: 50 }),
  );
  expect(screen.queryByRole('button', { name: 'Review group' })).toBeNull();
  expect(screen.getByRole('button', { name: 'HR group' })).toBeTruthy();
});
