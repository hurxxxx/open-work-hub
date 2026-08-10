import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { i18n } from '@/src/platform/i18n';

import {
  createAdminPlatformApiKey,
  listAdminPlatformApiKeys,
  revealAdminPlatformApiKey,
  revokeAdminPlatformApiKey,
  type AdminPlatformApiKeyItem,
} from './admin-platform-api-keys-api';
import { AdminPlatformApiKeysSection } from './admin-platform-api-keys-section';

vi.mock('./admin-platform-api-keys-api', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('./admin-platform-api-keys-api')>();
  return {
    ...actual,
    createAdminPlatformApiKey: vi.fn(),
    listAdminPlatformApiKeys: vi.fn(),
    revealAdminPlatformApiKey: vi.fn(),
    revokeAdminPlatformApiKey: vi.fn(),
  };
});

vi.mock('@/src/components/date/UserDateTime', () => ({
  UserDateTime: ({ value }: { value: string }) => <time>{value}</time>,
}));

const listMock = vi.mocked(listAdminPlatformApiKeys);
const createMock = vi.mocked(createAdminPlatformApiKey);
const revealMock = vi.mocked(revealAdminPlatformApiKey);
const revokeMock = vi.mocked(revokeAdminPlatformApiKey);
const clipboardWriteMock = vi.fn();

const activeKey: AdminPlatformApiKeyItem = {
  id: 'key-1',
  name: '종합검진',
  key_prefix: 'aido_live_abcd',
  scopes: ['hr:read'],
  created_by_name: '관리자',
  created_at: '2026-07-29T01:00:00Z',
  last_used_at: null,
  revoked_at: null,
};

const revokedKey: AdminPlatformApiKeyItem = {
  ...activeKey,
  id: 'key-2',
  name: '이전 연동',
  key_prefix: 'aido_live_old',
  revoked_at: '2026-07-29T02:00:00Z',
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolver) => {
    resolve = resolver;
  });
  return { promise, resolve };
}

describe('AdminPlatformApiKeysSection', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('ko-KR');
    listMock.mockReset();
    createMock.mockReset();
    revealMock.mockReset();
    revokeMock.mockReset();
    clipboardWriteMock.mockReset();
    clipboardWriteMock.mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: clipboardWriteMock },
    });
    listMock.mockResolvedValue({
      available_scopes: ['hr:read'],
      items: [activeKey, revokedKey],
    });
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('renders the dense responsive key inventory and its status', async () => {
    render(<AdminPlatformApiKeysSection token="token" />);

    expect((await screen.findAllByText('aido_live_abcd')).length).toBe(2);
    expect(screen.getAllByText('hr:read').length).toBeGreaterThan(0);
    expect(screen.getAllByText('활성').length).toBeGreaterThan(0);
    expect(screen.getAllByText('폐기됨').length).toBeGreaterThan(0);
    expect(screen.getAllByText('사용 이력 없음').length).toBeGreaterThan(0);
    expect(listMock).toHaveBeenCalledWith('token');
  });

  it('issues a scoped key and clears its secret when the dialog closes', async () => {
    createMock.mockResolvedValue({
      item: {
        ...activeKey,
        id: 'key-created',
        name: '신규 종합검진',
        key_prefix: 'aido_live_new',
      },
      api_key: 'aido-secret-created',
    });

    render(<AdminPlatformApiKeysSection token="token" />);
    await screen.findAllByText('aido_live_abcd');

    fireEvent.click(screen.getByRole('button', { name: 'API 키 발급' }));
    fireEvent.change(screen.getByLabelText('키 이름'), {
      target: { value: ' 신규 종합검진 ' },
    });
    expect(screen.getByRole('checkbox')).toHaveProperty('checked', true);
    fireEvent.click(screen.getByRole('button', { name: '발급' }));

    expect(await screen.findByDisplayValue('aido-secret-created')).toBeTruthy();
    expect(createMock).toHaveBeenCalledWith('token', {
      name: '신규 종합검진',
      scopes: ['hr:read'],
    });
    fireEvent.click(screen.getByRole('button', { name: '복사' }));
    await waitFor(() => {
      expect(clipboardWriteMock).toHaveBeenCalledWith('aido-secret-created');
    });
    expect(screen.getByRole('button', { name: '복사됨' })).toBeTruthy();

    const closeButtons = screen.getAllByRole('button', { name: '닫기' });
    fireEvent.click(closeButtons[closeButtons.length - 1]);

    await waitFor(() => {
      expect(screen.queryByDisplayValue('aido-secret-created')).toBeNull();
    });
    fireEvent.click(screen.getByRole('button', { name: 'API 키 발급' }));
    expect(screen.queryByDisplayValue('aido-secret-created')).toBeNull();
  });

  it('reveals immediately without a password and clears the secret on close', async () => {
    revealMock.mockResolvedValueOnce({
      item: activeKey,
      api_key: 'aido-secret-existing',
    });

    render(<AdminPlatformApiKeysSection token="token" />);
    await screen.findAllByText('aido_live_abcd');

    fireEvent.click(screen.getAllByRole('button', { name: '키 보기' })[0]);

    expect(
      await screen.findByDisplayValue('aido-secret-existing'),
    ).toBeTruthy();
    expect(revealMock).toHaveBeenCalledWith('token', 'key-1');
    expect(screen.queryByLabelText(/비밀번호/)).toBeNull();

    const closeButtons = screen.getAllByRole('button', { name: '닫기' });
    fireEvent.click(closeButtons[closeButtons.length - 1]);
    await waitFor(() => {
      expect(screen.queryByDisplayValue('aido-secret-existing')).toBeNull();
    });

    const pendingReveal =
      deferred<Awaited<ReturnType<typeof revealAdminPlatformApiKey>>>();
    revealMock.mockReturnValueOnce(pendingReveal.promise);
    fireEvent.click(screen.getAllByRole('button', { name: '키 보기' })[0]);
    expect(screen.queryByDisplayValue('aido-secret-existing')).toBeNull();
    const pendingCloseButtons = screen.getAllByRole('button', { name: '닫기' });
    fireEvent.click(pendingCloseButtons[pendingCloseButtons.length - 1]);
    pendingReveal.resolve({
      item: activeKey,
      api_key: 'aido-secret-after-close',
    });
    await waitFor(() => {
      expect(screen.queryByDisplayValue('aido-secret-after-close')).toBeNull();
    });
  });

  it('does not allow the create dialog to close while issuance is pending', async () => {
    const pendingCreate =
      deferred<Awaited<ReturnType<typeof createAdminPlatformApiKey>>>();
    createMock.mockReturnValueOnce(pendingCreate.promise);

    render(<AdminPlatformApiKeysSection token="token" />);
    await screen.findAllByText('aido_live_abcd');

    fireEvent.click(screen.getByRole('button', { name: 'API 키 발급' }));
    fireEvent.change(screen.getByLabelText('키 이름'), {
      target: { value: '진행 중 발급' },
    });
    fireEvent.click(screen.getByRole('button', { name: '발급' }));
    expect(await screen.findByText('발급 중...')).toBeTruthy();

    const closeButtons = screen.getAllByRole('button', { name: '닫기' });
    fireEvent.click(closeButtons[closeButtons.length - 1]);
    expect(screen.getByLabelText('키 이름')).toBeTruthy();
    expect(screen.getByText('발급 중...')).toBeTruthy();

    pendingCreate.resolve({
      item: {
        ...activeKey,
        id: 'pending-created-key',
        name: '진행 중 발급',
      },
      api_key: 'aido-secret-pending-create',
    });
    expect(
      await screen.findByDisplayValue('aido-secret-pending-create'),
    ).toBeTruthy();
  });

  it('revokes an active key and reloads the inventory', async () => {
    revokeMock.mockResolvedValue({});

    render(<AdminPlatformApiKeysSection token="token" />);
    await screen.findAllByText('aido_live_abcd');

    fireEvent.click(screen.getAllByRole('button', { name: '폐기' })[0]);
    fireEvent.click(screen.getByRole('button', { name: '키 폐기' }));

    await waitFor(() => {
      expect(revokeMock).toHaveBeenCalledWith('token', 'key-1');
      expect(listMock).toHaveBeenCalledTimes(2);
    });
  });
});
