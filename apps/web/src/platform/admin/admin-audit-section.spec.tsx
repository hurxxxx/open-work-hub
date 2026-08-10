import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, useLocation } from 'react-router-dom';

import { listAuditLogs } from './admin-api';
import { AuditSection } from './admin-audit-section';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    i18n: { language: 'en-US', resolvedLanguage: 'en-US' },
    t: (key: string) => key,
  }),
}));

vi.mock('@/src/platform/auth/auth-provider', () => ({
  useAuth: () => ({ user: { time_zone: 'UTC' } }),
}));

vi.mock('./admin-api', () => ({
  listAuditLogs: vi.fn(),
}));

const listAuditLogsMock = vi.mocked(listAuditLogs);

function LocationProbe() {
  return <output data-testid="location-search">{useLocation().search}</output>;
}

function renderAuditSection(initialEntry = '/admin/audit') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <AuditSection token="test-token" />
      <LocationProbe />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  listAuditLogsMock.mockResolvedValue({
    items: [],
    limit: 50,
    next_offset: null,
    offset: 0,
    total: 0,
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('AuditSection AI security preset', () => {
  it('reads the AI security scope deep-link and preserves the global defaults', async () => {
    renderAuditSection('/admin/audit?scope=ai-security');

    await waitFor(() =>
      expect(listAuditLogsMock).toHaveBeenLastCalledWith(
        'test-token',
        expect.objectContaining({
          ai_security_blocked_only: undefined,
          ai_security_only: true,
          days: 7,
          limit: 50,
          offset: 0,
        }),
      ),
    );

    expect(
      screen
        .getByRole('button', {
          name: 'admin.console.audit.filters.aiSecurityOnly',
        })
        .getAttribute('aria-pressed'),
    ).toBe('true');
    expect(
      screen
        .getByRole('button', {
          name: 'admin.console.audit.filters.aiSecurityBlockedOnly',
        })
        .getAttribute('aria-pressed'),
    ).toBe('false');
  });

  it('makes blocked-only imply security-only and keeps the URL in sync', async () => {
    renderAuditSection();
    await waitFor(() => expect(listAuditLogsMock).toHaveBeenCalledTimes(1));

    fireEvent.click(
      screen.getByRole('button', {
        name: 'admin.console.audit.filters.aiSecurityBlockedOnly',
      }),
    );

    await waitFor(() =>
      expect(listAuditLogsMock).toHaveBeenLastCalledWith(
        'test-token',
        expect.objectContaining({
          ai_security_blocked_only: true,
          ai_security_only: true,
        }),
      ),
    );
    expect(screen.getByTestId('location-search').textContent).toBe(
      '?scope=ai-security&blocked=true',
    );
    expect(
      screen
        .getByRole('button', {
          name: 'admin.console.audit.filters.aiSecurityOnly',
        })
        .getAttribute('aria-pressed'),
    ).toBe('true');
  });

  it('turns blocked-only off without clearing the security scope, then restores global audit', async () => {
    renderAuditSection('/admin/audit?blocked=true');

    await waitFor(() =>
      expect(listAuditLogsMock).toHaveBeenLastCalledWith(
        'test-token',
        expect.objectContaining({
          ai_security_blocked_only: true,
          ai_security_only: true,
        }),
      ),
    );
    await waitFor(() =>
      expect(screen.getByTestId('location-search').textContent).toBe(
        '?blocked=true&scope=ai-security',
      ),
    );

    fireEvent.click(
      screen.getByRole('button', {
        name: 'admin.console.audit.filters.aiSecurityBlockedOnly',
      }),
    );

    await waitFor(() =>
      expect(listAuditLogsMock).toHaveBeenLastCalledWith(
        'test-token',
        expect.objectContaining({
          ai_security_blocked_only: undefined,
          ai_security_only: true,
        }),
      ),
    );
    expect(screen.getByTestId('location-search').textContent).toBe(
      '?scope=ai-security',
    );

    fireEvent.click(
      screen.getByRole('button', {
        name: 'admin.console.audit.filters.aiSecurityOnly',
      }),
    );

    await waitFor(() =>
      expect(listAuditLogsMock).toHaveBeenLastCalledWith(
        'test-token',
        expect.objectContaining({
          ai_security_blocked_only: undefined,
          ai_security_only: undefined,
        }),
      ),
    );
    expect(screen.getByTestId('location-search').textContent).toBe('');
  });
});
