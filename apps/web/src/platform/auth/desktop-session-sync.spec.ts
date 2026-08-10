import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { createDesktopSessionLink } from './auth-api';
import {
  isLocalDesktopSessionHost,
  shouldSuppressDesktopSessionSync,
  syncDesktopLoginSession,
  syncDesktopLogoutSession,
  type DesktopSessionSyncSignal,
} from './desktop-session-sync';

vi.mock('./auth-api', () => ({
  createDesktopSessionLink: vi.fn(),
}));

const createDesktopSessionLinkMock = vi.mocked(createDesktopSessionLink);

const productionSignal: DesktopSessionSyncSignal = {
  env: {
    DEV: false,
    MODE: 'production',
  },
  location: {
    hostname: 'app.example.com',
    origin: 'https://app.example.com',
  },
};

beforeEach(() => {
  document.body.innerHTML = '';
  vi.useFakeTimers();
  createDesktopSessionLinkMock.mockReset();
  createDesktopSessionLinkMock.mockResolvedValue({
    code: 'desktop-code',
    expires_at: '2026-06-01T00:00:00Z',
  });
});

afterEach(() => {
  vi.useRealTimers();
  document.body.innerHTML = '';
});

describe('desktop session sync environment policy', () => {
  it('detects loopback and local development hosts', () => {
    expect(isLocalDesktopSessionHost('localhost')).toBe(true);
    expect(isLocalDesktopSessionHost('127.0.0.1')).toBe(true);
    expect(isLocalDesktopSessionHost('[::1]')).toBe(true);
    expect(isLocalDesktopSessionHost('ai-do.local')).toBe(true);
    expect(isLocalDesktopSessionHost('app.example.com')).toBe(false);
  });

  it('suppresses sync in Vite development mode or local origins', () => {
    expect(
      shouldSuppressDesktopSessionSync({
        env: {
          DEV: true,
          MODE: 'development',
        },
        location: {
          hostname: 'dev.example.com',
          origin: 'https://dev.example.com',
        },
      }),
    ).toBe(true);

    expect(
      shouldSuppressDesktopSessionSync({
        env: {
          DEV: false,
          MODE: 'production',
        },
        location: {
          hostname: '127.0.0.1',
          origin: 'http://127.0.0.1:4200',
        },
      }),
    ).toBe(true);

    expect(shouldSuppressDesktopSessionSync(productionSignal)).toBe(false);
  });
});

describe('desktop session sync', () => {
  it('does not create a desktop session link or open the desktop app in development', async () => {
    await syncDesktopLoginSession('web-token', {
      signal: {
        env: {
          DEV: true,
          MODE: 'development',
        },
        location: {
          hostname: 'dev.example.com',
          origin: 'https://dev.example.com',
        },
      },
    });

    expect(createDesktopSessionLinkMock).not.toHaveBeenCalled();
    expect(document.querySelector('iframe')).toBeNull();
  });

  it('does not open the desktop app on local logout', () => {
    syncDesktopLogoutSession({
      signal: {
        env: {
          DEV: false,
          MODE: 'production',
        },
        location: {
          hostname: 'localhost',
          origin: 'http://localhost:4200',
        },
      },
    });

    expect(document.querySelector('iframe')).toBeNull();
  });

  it('creates a desktop session link and opens the protocol URL in production', async () => {
    await syncDesktopLoginSession('web-token', {
      signal: productionSignal,
    });

    expect(createDesktopSessionLinkMock).toHaveBeenCalledWith('web-token');
    expect(document.querySelector('iframe')?.getAttribute('src')).toBe(
      'ai-do-desktop://auth/sync?server_url=https%3A%2F%2Fapp.example.com&code=desktop-code',
    );

    vi.runOnlyPendingTimers();
    expect(document.querySelector('iframe')).toBeNull();
  });

  it('opens the desktop logout protocol URL in production', () => {
    syncDesktopLogoutSession({
      signal: productionSignal,
    });

    expect(document.querySelector('iframe')?.getAttribute('src')).toBe(
      'ai-do-desktop://auth/logout?server_url=https%3A%2F%2Fapp.example.com',
    );
  });
});
