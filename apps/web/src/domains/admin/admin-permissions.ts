export const ADMIN_SECTION_ROLES = {
  general: ['platform_admin'],
  people: ['platform_admin'],
  workspaces: ['platform_admin'],
  security: ['platform_admin'],
  audit: ['platform_admin'],
} as const;

export type AdminSection = keyof typeof ADMIN_SECTION_ROLES;

export function hasAnyAdminReadPermission(systemRoles: readonly string[]): boolean {
  const allowedRoles = new Set(Object.values(ADMIN_SECTION_ROLES).flat());
  return systemRoles.some((role) => allowedRoles.has(role));
}

export function hasAdminSectionAccess(
  systemRoles: readonly string[],
  section: AdminSection,
): boolean {
  return ADMIN_SECTION_ROLES[section].some((role) => systemRoles.includes(role));
}

export function getDefaultAdminPath(systemRoles: readonly string[]): string {
  const orderedSections: AdminSection[] = [
    'general',
    'people',
    'workspaces',
    'security',
    'audit',
  ];

  const section = orderedSections.find((item) => hasAdminSectionAccess(systemRoles, item));
  return section ? `/admin/${section}` : '/admin/general';
}
