import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  listMailAccounts,
  listMailMessages,
  syncMailAccount,
} from './mail-api';

const clientMocks = vi.hoisted(() => ({
  apiFetchJson: vi.fn(),
  apiFetchJsonWithMappedError: vi.fn(),
}));

vi.mock('@/src/platform/api/client', () => clientMocks);
vi.mock('@/src/platform/i18n', () => ({
  i18n: { t: (key: string) => key },
}));

describe('personal Mail API paths', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    clientMocks.apiFetchJsonWithMappedError.mockResolvedValue({});
  });

  it('uses the global API prefix without a workspace slug', async () => {
    await listMailAccounts('token-1');
    await listMailMessages('token-1', { unread: true, limit: 25 });
    await syncMailAccount('token-1', 'account/1');

    expect(
      clientMocks.apiFetchJsonWithMappedError.mock.calls.map(([path]) => path),
    ).toEqual([
      '/api/v1/mail/accounts',
      '/api/v1/mail/messages?unread=true&limit=25',
      '/api/v1/mail/accounts/account%2F1/sync',
    ]);
  });
});
