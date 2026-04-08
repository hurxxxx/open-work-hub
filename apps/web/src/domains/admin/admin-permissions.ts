export const ADMIN_READ_PERMISSIONS = [
  'admin.access',
  'user.read',
  'group.read',
  'workspace.read',
  'team.read',
  'feature_policy.read',
  'audit.read',
] as const;

export const ADMIN_SECTION_PERMISSIONS = {
  general: ['admin.access'],
  people: ['user.read'],
  teams: ['team.read'],
  workspaces: ['workspace.read'],
  security: ['group.read', 'feature_policy.read'],
  audit: ['audit.read'],
} as const;

export type AdminSection = keyof typeof ADMIN_SECTION_PERMISSIONS;

export function hasAnyAdminReadPermission(permissions: readonly string[]): boolean {
  return ADMIN_READ_PERMISSIONS.some((permission) => permissions.includes(permission));
}

export function hasAdminSectionAccess(
  permissions: readonly string[],
  section: AdminSection,
): boolean {
  return (
    permissions.includes('admin.access')
    || ADMIN_SECTION_PERMISSIONS[section].some((permission) => permissions.includes(permission))
  );
}

export function getDefaultAdminPath(permissions: readonly string[]): string {
  const orderedSections: AdminSection[] = [
    'general',
    'people',
    'teams',
    'workspaces',
    'security',
    'audit',
  ];

  const section = orderedSections.find((item) => hasAdminSectionAccess(permissions, item));
  return section ? `/admin/${section}` : '/admin/general';
}
