import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  createPlatformApiKey,
  listPlatformApiKeys,
  revealPlatformApiKey,
} from './admin-api';
import { AdminPlatformApiKeysSection } from './admin-platform-api-keys-section';

const testContext = vi.hoisted(() => ({
  error: vi.fn(),
  success: vi.fn(),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('@open-work-hub/ui', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@open-work-hub/ui')>()),
  useConfirm: () => ({
    confirm: vi.fn().mockResolvedValue(true),
    confirmDialog: null,
  }),
  useFeedback: () => testContext,
}));

vi.mock('@/src/components/date/UserDateTime', () => ({
  UserDateTime: ({ value }: { value: string }) => <time>{value}</time>,
}));

vi.mock('./admin-api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./admin-api')>()),
  createPlatformApiKey: vi.fn(),
  listPlatformApiKeys: vi.fn(),
  revealPlatformApiKey: vi.fn(),
  revokePlatformApiKey: vi.fn(),
}));

const keyItem = {
  id: 'key-1',
  name: 'HR sync',
  key_prefix: 'owh_pk_abcdefghijk',
  scopes: ['organization:read'],
  status: 'active',
  created_by_name: 'Admin',
  created_at: '2026-08-26T00:00:00Z',
  last_used_at: null,
  revoked_at: null,
};

const listResponse = {
  available_scopes: ['organization:read', 'people:read'],
  documentation: {
    swagger_path: '/docs',
    redoc_path: '/redoc',
    openapi_path: '/openapi.json',
  },
  scope_specs: [
    {
      scope: 'organization:read',
      operations: [
        {
          method: 'GET',
          path: '/api/v1/integrations/directory/organization-units',
          operation_id: 'list_directory_organization_units',
          summary: 'List organization units',
          swagger_path: '/docs#organization',
          redoc_path: '/redoc#organization',
        },
      ],
    },
    { scope: 'people:read', operations: [] },
  ],
  items: [keyItem],
};

beforeEach(() => {
  vi.mocked(listPlatformApiKeys).mockResolvedValue(listResponse);
  vi.mocked(revealPlatformApiKey).mockResolvedValue({
    item: keyItem,
    api_key: 'owh_pk_revealed_secret_value',
  });
  vi.mocked(createPlatformApiKey).mockResolvedValue({
    item: keyItem,
    api_key: 'owh_pk_issued_secret_value',
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('AdminPlatformApiKeysSection', () => {
  it('reveals an active key and clears the secret when the dialog closes', async () => {
    render(<AdminPlatformApiKeysSection token="admin-token" />);

    expect(await screen.findByText('HR sync')).toBeTruthy();
    fireEvent.click(
      screen.getByRole('button', { name: 'admin.console.apiKeys.reveal' }),
    );

    expect(
      await screen.findByDisplayValue('owh_pk_revealed_secret_value'),
    ).toBeTruthy();
    const dialog = screen.getByRole('dialog');
    const closeButtons = within(dialog).getAllByRole('button', {
      name: 'common:actions.close',
    });
    const closeButton = closeButtons.at(-1);
    expect(closeButton).toBeDefined();
    if (closeButton) fireEvent.click(closeButton);

    await waitFor(() =>
      expect(
        screen.queryByDisplayValue('owh_pk_revealed_secret_value'),
      ).toBeNull(),
    );
    expect(revealPlatformApiKey).toHaveBeenCalledWith('admin-token', 'key-1');
  });

  it('issues only the selected scopes and opens the secret dialog', async () => {
    render(<AdminPlatformApiKeysSection token="admin-token" />);
    await screen.findByText('HR sync');
    fireEvent.click(
      screen.getByRole('button', { name: 'admin.console.apiKeys.issue' }),
    );

    const issueDialog = screen.getByRole('dialog');
    fireEvent.change(
      within(issueDialog).getByRole('textbox', {
        name: 'admin.console.apiKeys.name',
      }),
      { target: { value: 'Directory mirror' } },
    );
    fireEvent.click(
      within(issueDialog).getByRole('checkbox', {
        name: 'organization:read',
      }),
    );
    fireEvent.click(
      within(issueDialog).getByRole('button', {
        name: 'admin.console.apiKeys.issue',
      }),
    );

    expect(
      await screen.findByDisplayValue('owh_pk_issued_secret_value'),
    ).toBeTruthy();
    expect(createPlatformApiKey).toHaveBeenCalledWith('admin-token', {
      name: 'Directory mirror',
      scopes: ['organization:read'],
    });
  });
});
