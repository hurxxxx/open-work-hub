import { describe, expect, it } from 'vitest';
import { FileText } from 'lucide-react';
import { docsManifest } from '@/src/app-modules/docs/manifest';
import type { NavItem } from '@/src/app/shell/navigation-types';
import {
  buildAppEntryPath,
  buildAppPath,
  getAppIdFromPath,
  resolveAppInvocationHref,
  resolveNavItemHref,
} from './app-links';
const nav = (overrides: Partial<NavItem> = {}): NavItem => ({
  id: 'docs-all',
  title: 'Docs',
  icon: FileText,
  category: 'Collaboration',
  appId: 'docs',
  ...overrides,
});
describe('canonical company app navigation', () => {
  it('identifies declared app and resource routes without an outer container', () => {
    expect(getAppIdFromPath('/apps/docs')).toBe('docs');
    expect(getAppIdFromPath('/apps/docs/documents/doc-1')).toBe('docs');
    expect(getAppIdFromPath('/apps/unknown')).toBeNull();
    expect(getAppIdFromPath('/apps/docs/workspaces/obsolete')).toBeNull();
  });
  it.each(['docs', 'community', 'pms', 'retrieval-search'])(
    'builds the canonical %s entry',
    (id) => {
      expect(buildAppPath(id)).toBe(`/apps/${id}`);
      expect(buildAppEntryPath(id)).toBe(`/apps/${id}`);
    },
  );
  it.each(['customer-app', '../admin', ''])('rejects undeclared app %s', (id) =>
    expect(() => buildAppPath(id)).toThrow(`Unknown app: ${id}`),
  );
  it('preserves declared query and cross-app navigation', () => {
    expect(
      resolveNavItemHref(
        docsManifest.navItems.find((item) => item.id === 'docs-my') ?? nav(),
      ),
    ).toBe('/apps/docs?view=mine');
    expect(
      resolveNavItemHref(
        nav({ linkAppId: 'meeting', pathSuffix: '?tab=recordings' }),
      ),
    ).toBe('/apps/meeting?tab=recordings');
    expect(
      resolveNavItemHref(nav({ appId: 'files', pathSuffix: '/chat' })),
    ).toBe('/apps/files/chat');
  });
  it('rejects undeclared dynamic suffixes and unknown apps', () => {
    expect(resolveNavItemHref(nav({ appId: 'unknown-app' }))).toBe('/');
    expect(
      resolveNavItemHref(nav({ pathSuffix: '/documents/dynamic-id' })),
    ).toBe('/');
    expect(
      resolveAppInvocationHref(
        nav({ appId: 'settings', absolutePath: '/admin/general' }),
      ),
    ).toBe('/admin/general');
  });
});
