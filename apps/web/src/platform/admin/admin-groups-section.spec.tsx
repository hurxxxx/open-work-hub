import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { apiFetchJson } from '@/src/platform/api/client';
import { GroupsSection } from './admin-groups-section';
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
vi.mock('@/src/platform/directory/DirectoryPicker', () => ({
  DirectoryPicker: ({
    selectedIds,
    onChange,
    disabled,
  }: {
    selectedIds: string[];
    onChange: (ids: string[]) => void;
    disabled?: boolean;
  }) => (
    <button
      disabled={disabled}
      onClick={() => onChange(selectedIds.filter((id) => id !== 'b'))}
    >
      Remove B
    </button>
  ),
}));
const group = {
  id: 'group',
  name: 'Review group',
  description: '',
  active: true,
  kind: 'manual',
};
const api = vi.mocked(apiFetchJson);
beforeEach(() => {
  vi.clearAllMocks();
  api.mockImplementation(async (path, _token, init) => {
    if (init?.method) return group;
    if (path.includes('/members')) return { user_ids: ['b', 'c'] };
    return { items: [group], total: 1, page: 1, page_size: 50 };
  });
});
async function openGroup() {
  render(<GroupsSection token="test-token" />);
  fireEvent.click(await screen.findByRole('button', { name: 'Review group' }));
  await screen.findByRole('button', { name: 'Remove B' });
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
  it('keeps organization groups and their derived members read only', async () => {
    api.mockImplementation(async (path) =>
      path.includes('/members')
        ? { user_ids: ['b'] }
        : {
            items: [{ ...group, kind: 'organization' }],
            total: 1,
            page: 1,
            page_size: 50,
          },
    );
    await openGroup();
    expect(
      screen.getByRole('button', { name: 'Remove B' }).hasAttribute('disabled'),
    ).toBe(true);
    expect(
      screen.queryByRole('button', { name: 'companyGroups.saveMembers' }),
    ).toBeNull();
    expect(
      screen.queryByRole('button', { name: 'companyGroups.saveDetails' }),
    ).toBeNull();
  });
});
