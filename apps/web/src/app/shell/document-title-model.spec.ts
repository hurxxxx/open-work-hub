import { describe, expect, it } from 'vitest';

import type { ShellAppId } from '@/src/app-shell';

import { resolveShellDocumentTitle } from './document-title-model';

function t(key: string, options?: Record<string, unknown>): string {
  if (key === 'apps.chatbot') return 'Chatbot';
  if (key === 'apps.settings') return 'Settings';
  if (key === 'documentTitle.profile') return 'Profile';
  if (key === 'launcher.title') return 'App launcher';
  if (key === 'documentTitle.app')
    return `${String(options?.app)} | Open Work Hub`;
  return String(options?.defaultValue ?? key);
}

function title(
  overrides: {
    activeAppId?: ShellAppId;

    apps?: { app_id: string; title: string }[];
  } = {},
): string {
  return resolveShellDocumentTitle({
    activeAppId: overrides.activeAppId ?? 'chatbot',
    t,
    apps: overrides.apps ?? [],
  });
}

describe('document title model', () => {
  it('uses a neutral title for the launcher', () => {
    expect(
      title({
        activeAppId: 'launcher',
      }),
    ).toBe('App launcher | Open Work Hub');
  });

  it('uses platform app titles', () => {
    expect(
      title({
        activeAppId: 'settings',
      }),
    ).toBe('Settings | Open Work Hub');
    expect(
      title({
        activeAppId: 'profile',
      }),
    ).toBe('Profile | Open Work Hub');
  });

  it('uses the settings app title for administration', () => {
    expect(
      title({
        activeAppId: 'settings',
      }),
    ).toBe('Settings | Open Work Hub');
  });

  it('falls back from i18n key to app bootstrap title and app registry title', () => {
    expect(
      title({
        activeAppId: 'custom-app',
        apps: [{ app_id: 'custom-app', title: 'Custom app' }],
      }),
    ).toBe('Custom app | Open Work Hub');
    expect(title({ activeAppId: 'docs' })).toBe('docs | Open Work Hub');
  });

  it('uses app titles consistently for direct app routes', () => {
    expect(title({ activeAppId: 'retrieval-search' })).toBe(
      'retrieval-search | Open Work Hub',
    );
    expect(title()).toBe('Chatbot | Open Work Hub');
  });
});
