import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { apiFetchJson } from '@/src/platform/api/client';
import { SpaceGroupBindings } from './SpaceGroupBindings';
const state = vi.hoisted(() => ({
  t: (key: string) => key,
  success: vi.fn(),
  error: vi.fn(),
}));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: state.t }) }));
vi.mock('@open-work-hub/ui', async (original) => ({
  ...(await original<typeof import('@open-work-hub/ui')>()),
  useFeedback: () => state,
}));
vi.mock('@/src/platform/api/client', () => ({ apiFetchJson: vi.fn() }));
vi.mock('@/src/platform/directory/DirectoryPicker', () => ({
  DirectoryPicker: ({
    onChange,
    disabled,
  }: {
    onChange: (ids: string[]) => void;
    disabled: boolean;
  }) => (
    <button disabled={disabled} onClick={() => onChange(['group-1'])}>
      choose-group
    </button>
  ),
}));
const row = {
  group_id: 'group-1',
  name: 'Engineering',
  active: true,
  role: 'member',
};
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(apiFetchJson).mockResolvedValue([]);
});
describe('SpaceGroupBindings', () => {
  it('grants an app-owned role without changing content ownership', async () => {
    render(
      <SpaceGroupBindings token="token" resourceId="resource-1" canManage />,
    );
    await waitFor(() =>
      expect(
        (screen.getByText('choose-group') as HTMLButtonElement).disabled,
      ).toBe(false),
    );
    fireEvent.click(screen.getByText('choose-group'));
    fireEvent.change(screen.getByLabelText('groupSharing.role'), {
      target: { value: 'member' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'groupSharing.grant' }));
    await waitFor(() =>
      expect(apiFetchJson).toHaveBeenCalledWith(
        '/api/v1/pms/spaces/resource-1/groups/group-1',
        'token',
        { method: 'PUT', body: JSON.stringify({ role: 'member' }) },
      ),
    );
    expect(state.success).toHaveBeenCalledWith('groupSharing.saved');
  });
  it('exposes no grant or removal controls to a read-only viewer', async () => {
    vi.mocked(apiFetchJson).mockResolvedValue([row]);
    render(
      <SpaceGroupBindings
        token="token"
        resourceId="resource-1"
        canManage={false}
      />,
    );
    await screen.findByText('Engineering');
    expect(screen.queryAllByRole('button')).toHaveLength(0);
    expect(screen.queryAllByRole('combobox')).toHaveLength(0);
  });
  it('removes a group grant and reloads the current list', async () => {
    vi.mocked(apiFetchJson)
      .mockResolvedValueOnce([row])
      .mockResolvedValueOnce(undefined)
      .mockResolvedValue([]);
    render(
      <SpaceGroupBindings token="token" resourceId="resource-1" canManage />,
    );
    await screen.findByText('Engineering');
    fireEvent.click(
      screen.getByRole('button', { name: 'common:actions.remove' }),
    );
    await waitFor(() =>
      expect(apiFetchJson).toHaveBeenCalledWith(
        '/api/v1/pms/spaces/resource-1/groups/group-1',
        'token',
        { method: 'DELETE' },
      ),
    );
    await waitFor(() => expect(screen.queryByText('Engineering')).toBeNull());
  });
  it('ignores stale sharing responses when the resource changes', async () => {
    let resolveOld!: (value: unknown) => void;
    vi.mocked(apiFetchJson)
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveOld = resolve;
          }),
      )
      .mockResolvedValue([]);
    const result = render(
      <SpaceGroupBindings token="token" resourceId="resource-1" canManage />,
    );
    result.rerender(
      <SpaceGroupBindings token="token" resourceId="resource-2" canManage />,
    );
    await screen.findByText('groupSharing.empty');
    await act(async () => resolveOld([row]));
    expect(screen.queryByText('Engineering')).toBeNull();
  });
});

it('never offers owner to groups and reserves group administrators for an explicit owner', async () => {
  const result = render(
    <SpaceGroupBindings token="token" resourceId="resource-1" canManage />,
  );
  await screen.findByText('groupSharing.empty');
  expect(
    screen.queryByRole('option', { name: 'groupSharing.roles.admin' }),
  ).toBeNull();
  expect(
    screen.queryByRole('option', { name: 'groupSharing.roles.owner' }),
  ).toBeNull();
  result.rerender(
    <SpaceGroupBindings
      token="token"
      resourceId="resource-1"
      canManage
      canManageAdmins
    />,
  );
  expect(
    screen.getByRole('option', { name: 'groupSharing.roles.admin' }),
  ).toBeTruthy();
  expect(
    screen.queryByRole('option', { name: 'groupSharing.roles.owner' }),
  ).toBeNull();
});
