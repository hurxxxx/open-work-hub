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
  if (key === 'documentTitle.workspaceApp') {
    return `${String(options?.workspace)} - ${String(options?.app)} | Open Work Hub`;
  }
  return String(options?.defaultValue ?? key);
}

function title(
  overrides: {
    activeAppId?: ShellAppId;
    pathname?: string;

    workspace?: { name: string } | null;
    apps?: { app_id: string; title: string }[];
  } = {},
): string {
  const hasWorkspace = Object.prototype.hasOwnProperty.call(
    overrides,
    'workspace',
  );
  return resolveShellDocumentTitle({
    activeAppId: overrides.activeAppId ?? 'chatbot',
    pathname: overrides.pathname ?? '/apps/chatbot',
    t,
    workspace: hasWorkspace ? overrides.workspace : { name: 'HQ' },
    apps: overrides.apps ?? [],
  });
}

describe('document title model', () => {
  it('uses a neutral title for the launcher', () => {
    expect(
      title({
        activeAppId: 'launcher',
        workspace: null,
      }),
    ).toBe('App launcher | Open Work Hub');
  });

  it('uses platform app titles without an inferred workspace', () => {
    expect(
      title({
        activeAppId: 'settings',
        pathname: '/admin/settings',
        workspace: null,
      }),
    ).toBe('Settings | Open Work Hub');
    expect(
      title({
        activeAppId: 'profile',
        pathname: '/profile',
        workspace: null,
      }),
    ).toBe('Profile | Open Work Hub');
  });

  it('uses the settings app title outside workspace settings routes', () => {
    expect(
      title({
        activeAppId: 'settings',
        pathname: '/admin/users',
        workspace: null,
      }),
    ).toBe('Settings | Open Work Hub');
  });

  it('falls back from i18n key to workspace bootstrap title and app registry title', () => {
    expect(
      title({
        activeAppId: 'workspace-app',
        apps: [{ app_id: 'workspace-app', title: 'Workspace app' }],
      }),
    ).toBe('Workspace app | Open Work Hub');
    expect(title({ activeAppId: 'docs' })).toBe('docs | Open Work Hub');
  });

  it('uses app titles consistently for direct app routes', () => {
    expect(title({ pathname: '/apps/retrieval-search' })).toBe(
      'Chatbot | Open Work Hub',
    );
    expect(title()).toBe('Chatbot | Open Work Hub');
  });
});
