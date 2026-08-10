import { describe, expect, it } from 'vitest';

import {
  createCoreAdminSectionRegistry,
  defineCoreAdminSections,
} from './admin';

describe('createCoreAdminSectionRegistry', () => {
  const sections = defineCoreAdminSections([
    { id: 'general', path: '/admin/general', roles: ['platform_admin'] },
    {
      id: 'research-policy',
      path: '/admin/research-policy',
      roles: ['platform_admin', 'research_admin'],
    },
  ] as const);

  it('resolves access and default path from section definitions', () => {
    const registry = createCoreAdminSectionRegistry(sections);

    expect(registry.hasAnyAdminReadPermission(['research_admin'])).toBe(true);
    expect(registry.hasAdminSectionAccess(['research_admin'], 'general')).toBe(
      false,
    );
    expect(
      registry.hasAdminSectionAccess(['research_admin'], 'research-policy'),
    ).toBe(true);
    expect(registry.getDefaultAdminPath(['research_admin'])).toBe(
      '/admin/research-policy',
    );
  });

  it('falls back to the first section path when the user has no section role', () => {
    const registry = createCoreAdminSectionRegistry(sections);

    expect(registry.hasAnyAdminReadPermission(['workspace_member'])).toBe(
      false,
    );
    expect(registry.getDefaultAdminPath(['workspace_member'])).toBe(
      '/admin/general',
    );
  });
});
