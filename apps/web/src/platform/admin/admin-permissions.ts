import { createCoreAdminSectionRegistry } from '@open-work-hub/core-web/admin';

import { ADMIN_SECTION_DEFINITIONS, type AdminSection } from './admin-sections';

export type { AdminSection } from './admin-sections';

const ADMIN_SECTION_REGISTRY = createCoreAdminSectionRegistry(
  ADMIN_SECTION_DEFINITIONS,
);

export const ADMIN_SECTION_POLICIES = ADMIN_SECTION_REGISTRY.sections;

export type AdminSectionAccessResolver = (
  systemRoles: readonly string[],
  section: string,
) => boolean;

export type DefaultAdminPathResolver = (
  systemRoles: readonly string[],
) => string;

export function hasAnyAdminReadPermission(
  systemRoles: readonly string[],
): boolean {
  return ADMIN_SECTION_REGISTRY.hasAnyAdminReadPermission(systemRoles);
}

export function hasAdminSectionAccess(
  systemRoles: readonly string[],
  section: AdminSection,
): boolean {
  return ADMIN_SECTION_REGISTRY.hasAdminSectionAccess(systemRoles, section);
}

export const hasConfiguredAdminSectionAccess: AdminSectionAccessResolver = (
  systemRoles,
  section,
) => {
  if (!ADMIN_SECTION_REGISTRY.sectionById.has(section as AdminSection)) {
    return false;
  }
  return ADMIN_SECTION_REGISTRY.hasAdminSectionAccess(
    systemRoles,
    section as AdminSection,
  );
};

export function getDefaultAdminPath(systemRoles: readonly string[]): string {
  return ADMIN_SECTION_REGISTRY.getDefaultAdminPath(systemRoles);
}
