import { describe, expect, it } from 'vitest';

import {
  getDefaultAdminPath,
  hasAdminSectionAccess,
  hasAnyAdminReadPermission,
  type AdminSection,
} from './admin-permissions';

describe('admin-permissions', () => {
  it('grants every admin section to platform admins', () => {
    const sections: AdminSection[] = [
      'general',
      'people',
      'apps',
      'llm',
      'model-monitoring',
      'document-processing',
      'ai-security',
      'workspaces',
      'community',
      'usage',
      'audit',
    ];

    for (const section of sections) {
      expect(hasAdminSectionAccess(['platform_admin'], section)).toBe(true);
    }
  });

  it('denies admin sections and read permission without an allowed role', () => {
    expect(hasAnyAdminReadPermission([])).toBe(false);
    expect(hasAnyAdminReadPermission(['workspace_admin'])).toBe(false);
    expect(hasAdminSectionAccess(['workspace_admin'], 'people')).toBe(false);
  });

  it('derives read permission and default route from the same section policy order', () => {
    expect(hasAnyAdminReadPermission(['platform_admin'])).toBe(true);
    expect(getDefaultAdminPath(['platform_admin'])).toBe('/admin/general');
    expect(getDefaultAdminPath([])).toBe('/admin/general');
  });
});
